# ruff: noqa: E501
import datetime as _dt
import logging
from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.clinical_event import ClinicalEvent
from app.models.document_model import DocumentModel
from app.models.fhir.medication import Medication
from app.models.fhir.patient import Observation, Patient
from app.services.fhir_helpers import FhirSerializationError, build_meta

logger = logging.getLogger(__name__)

EXPORT_SPEC_TAG = {
    "system": "urn:health-assistant:interop:profile",
    "code": "limited-fhir-r4-inspired",
    "display": "Health Assistant Limited FHIR R4-Inspired Export (Not official ABDM/HL7 certified)",
}


async def export_patient_fhir_bundle(
    db: AsyncSession,
    tenant_id: UUID,
    patient_id: UUID,
) -> dict[str, Any]:
    """Generate a limited, machine-readable FHIR R4-inspired Bundle for a patient.

    Supported Resources and Mappings:
    - Patient: fhir_patients relational row -> FHIR R4 Patient (demographics, gender, birthDate, address, telecom)
    - DocumentReference: documents -> FHIR R4 DocumentReference (filename, status, content attachment, created date)
    - Observation: fhir_observations -> FHIR R4 Observation (LOINC/local code, raw & normalized values, reference ranges, interpretation)
    - MedicationStatement / MedicationRequest: fhir_medications -> FHIR R4 MedicationStatement or MedicationRequest based on intent
    - Condition: clinical_events -> FHIR R4 Condition (clinicalStatus, SNOMED/local code, onsetDateTime, abatementDateTime, source evidence)

    Scope & Limitations:
    - This is a scoped, machine-readable FHIR R4-inspired export from the local relational store.
    - It does NOT claim full official HL7 conformance or certified live ABDM milestone integration.
    """
    # 1. Fetch patient
    pat_res = await db.execute(
        select(Patient).where(
            Patient.id == patient_id,
            Patient.tenant_id == tenant_id,
            Patient.deleted_at.is_(None),
        )
    )
    patient = pat_res.scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    # 2. Fetch associated clinical records
    doc_res = await db.execute(
        select(DocumentModel).where(
            DocumentModel.tenant_id == tenant_id,
            DocumentModel.patient_id == patient_id,
            DocumentModel.deleted_at.is_(None),
        )
    )
    documents = list(doc_res.scalars().all())

    obs_res = await db.execute(
        select(Observation).where(
            Observation.tenant_id == tenant_id,
            Observation.patient_id == patient_id,
            Observation.deleted_at.is_(None),
        )
    )
    observations = list(obs_res.scalars().all())

    med_res = await db.execute(
        select(Medication).where(
            Medication.tenant_id == tenant_id,
            Medication.patient_id == patient_id,
            Medication.deleted_at.is_(None),
        )
    )
    medications = list(med_res.scalars().all())

    ce_res = await db.execute(
        select(ClinicalEvent).where(
            ClinicalEvent.tenant_id == tenant_id,
            ClinicalEvent.patient_id == patient_id,
            ClinicalEvent.deleted_at.is_(None),
        )
    )
    conditions = list(ce_res.scalars().all())

    entries: list[dict[str, Any]] = []

    # Map Patient
    try:
        pat_fhir = patient.to_fhir_dict()
        entries.append(
            {
                "fullUrl": f"urn:uuid:{patient.id}",
                "resource": pat_fhir,
            }
        )
    except FhirSerializationError as e:
        logger.warning(f"Patient {patient.id} FHIR mapping fallback: {e}")
        entries.append(
            {
                "fullUrl": f"urn:uuid:{patient.id}",
                "resource": {
                    "resourceType": "Patient",
                    "id": str(patient.id),
                    "name": patient.name
                    if isinstance(patient.name, list)
                    else [{"text": str(patient.name)}],
                    "gender": patient.gender.value
                    if hasattr(patient.gender, "value")
                    else str(patient.gender),
                },
            }
        )

    # Map DocumentReferences
    for doc in documents:
        try:
            doc_fhir = doc.to_fhir_dict()
            entries.append(
                {
                    "fullUrl": f"urn:uuid:{doc.id}",
                    "resource": doc_fhir,
                }
            )
        except Exception as e:
            logger.warning(f"DocumentReference {doc.id} mapping error: {e}")

    # Map Observations
    for obs in observations:
        try:
            obs_fhir = obs.to_fhir_dict()
            if "subject" not in obs_fhir and (obs.patient_id or patient_id):
                obs_fhir["subject"] = {"reference": f"Patient/{obs.patient_id or patient_id}"}
            # Link source document if present
            if obs.document_id:
                obs_fhir["derivedFrom"] = [{"reference": f"DocumentReference/{obs.document_id}"}]
            entries.append(
                {
                    "fullUrl": f"urn:uuid:{obs.id}",
                    "resource": obs_fhir,
                }
            )
        except Exception as e:
            logger.warning(f"Observation {obs.id} mapping fallback: {e}")
            entries.append(
                {
                    "fullUrl": f"urn:uuid:{obs.id}",
                    "resource": {
                        "resourceType": "Observation",
                        "id": str(obs.id),
                        "status": (obs.status or "final").lower(),
                        "code": obs.code or {"text": "Observation"},
                        "subject": obs.subject or {"reference": f"Patient/{obs.patient_id}"},
                        "valueString": str(
                            obs.normalized_value or obs.raw_value or obs.value_string or ""
                        ),
                    },
                }
            )

    # Map Medications
    for med in medications:
        try:
            med_fhir = med.to_fhir_dict()
            entries.append(
                {
                    "fullUrl": f"urn:uuid:{med.id}",
                    "resource": med_fhir,
                }
            )
        except Exception as e:
            logger.warning(f"Medication {med.id} mapping fallback: {e}")
            entries.append(
                {
                    "fullUrl": f"urn:uuid:{med.id}",
                    "resource": {
                        "resourceType": "MedicationStatement",
                        "id": str(med.id),
                        "status": "active",
                        "medicationCodeableConcept": med.code or {"text": "Medication"},
                        "subject": {"reference": f"Patient/{med.patient_id}"},
                    },
                }
            )

    # Map Conditions
    for cond in conditions:
        try:
            cond_fhir = cond.to_fhir_dict()
            entries.append(
                {
                    "fullUrl": f"urn:uuid:{cond.id}",
                    "resource": cond_fhir,
                }
            )
        except Exception as e:
            logger.warning(f"Condition {cond.id} mapping error: {e}")

    now_iso = _dt.datetime.now(_dt.UTC).isoformat()
    meta = build_meta(
        last_updated=now_iso,
    )
    meta["tag"] = [EXPORT_SPEC_TAG]

    bundle = {
        "resourceType": "Bundle",
        "id": f"export-{patient_id}-{uuid4().hex[:8]}",
        "type": "collection",
        "timestamp": now_iso,
        "meta": meta,
        "total": len(entries),
        "entry": entries,
    }
    return bundle

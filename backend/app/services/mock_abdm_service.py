# ruff: noqa: E501
import datetime as _dt
import hashlib
import json
import logging
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.clinical_event import ClinicalEvent
from app.models.enums import ClinicalEventStatus, CodingSystem, MedicationStatus
from app.models.fhir.medication import Medication
from app.models.fhir.patient import Observation
from app.models.mock_abdm_model import MockAbdmImportRecord
from app.schemas.mock_abdm import (
    MockAbdmConfirmResponse,
    MockAbdmPreviewResponse,
    SyntheticRecordBundle,
)
from app.schemas.user import TokenData
from app.services.audit_service import log_audit_action
from app.services.health_summary_service import invalidate_patient_summaries

logger = logging.getLogger(__name__)


def compute_bundle_checksum(bundle: SyntheticRecordBundle) -> str:
    """Compute a deterministic SHA-256 fingerprint of the synthetic record content."""
    normalized_dict = {
        "external_record_id": bundle.external_record_id,
        "source_system": bundle.source_system,
        "facility_id": bundle.facility_id,
        "observations": [
            {
                "test_name": o.test_name,
                "value": o.value,
                "unit": o.unit,
                "code": o.code,
            }
            for o in sorted(bundle.observations, key=lambda x: x.test_name)
        ],
        "medications": [
            {
                "name": m.name,
                "dosage": m.dosage,
                "frequency": m.frequency,
            }
            for m in sorted(bundle.medications, key=lambda x: x.name)
        ],
        "conditions": [
            {
                "name": c.name,
                "code": c.code,
            }
            for c in sorted(bundle.conditions, key=lambda x: x.name)
        ],
    }
    encoded = json.dumps(normalized_dict, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


async def preview_mock_abdm_record(
    db: AsyncSession,
    tenant_id: UUID,
    patient_id: UUID,
    bundle: SyntheticRecordBundle,
) -> MockAbdmPreviewResponse:
    """Preview a synthetic external ABDM record before import.

    Validates payload, calculates the deduplication checksum, checks whether
    the record was already imported, and previews mapped resources without modifying canonical tables.
    """
    checksum = compute_bundle_checksum(bundle)

    # Check for existing duplicate import
    existing_res = await db.execute(
        select(MockAbdmImportRecord).where(
            MockAbdmImportRecord.tenant_id == tenant_id,
            MockAbdmImportRecord.checksum == checksum,
        )
    )
    existing_import = existing_res.scalar_one_or_none()
    is_duplicate = existing_import is not None
    is_own_patient_duplicate = is_duplicate and existing_import.patient_id == patient_id

    warnings: list[str] = []
    if is_duplicate:
        warnings.append(
            f"Record '{bundle.external_record_id}' was already imported on "
            f"{existing_import.imported_at.isoformat() if existing_import.imported_at else 'previous session'}."
        )

    preview_records = {
        "observations": [o.model_dump() for o in bundle.observations],
        "medications": [m.model_dump() for m in bundle.medications],
        "conditions": [c.model_dump() for c in bundle.conditions],
        "notes": {
            "en": bundle.notes_en,
            "hi": bundle.notes_hi,
        },
    }

    return MockAbdmPreviewResponse(
        is_duplicate=is_duplicate,
        duplicate_import_id=str(existing_import.id) if is_own_patient_duplicate else None,
        checksum=checksum,
        external_record_id=bundle.external_record_id,
        source_system=bundle.source_system,
        facility_name=bundle.facility_name,
        observation_count=len(bundle.observations),
        medication_count=len(bundle.medications),
        condition_count=len(bundle.conditions),
        preview_records=preview_records,
        warnings=warnings,
    )


async def confirm_mock_abdm_import(
    db: AsyncSession,
    tenant_id: UUID,
    patient_id: UUID,
    bundle: SyntheticRecordBundle,
    current_user: TokenData,
) -> MockAbdmConfirmResponse:
    """Confirm and persist a synthetic external record import into the canonical data model.

    Enforces deduplication: if the record with this checksum is already present,
    it rejects duplicate creation and returns the existing import details.
    When new, records are mapped into canonical Observation, Medication, and ClinicalEvent rows
    with source provenance, audit logs, and dependent summary invalidation.
    """
    checksum = compute_bundle_checksum(bundle)

    # 1. Deduplication check
    existing_res = await db.execute(
        select(MockAbdmImportRecord).where(
            MockAbdmImportRecord.tenant_id == tenant_id,
            MockAbdmImportRecord.checksum == checksum,
        )
    )
    existing_import = existing_res.scalar_one_or_none()
    if existing_import:
        is_own = existing_import.patient_id == patient_id
        message = (
            f"Duplicate record rejected: already imported with ID {existing_import.id}"
            if is_own
            else "Duplicate record rejected: this external health record was already imported."
        )
        return MockAbdmConfirmResponse(
            status="duplicate",
            import_id=str(existing_import.id) if is_own else None,
            checksum=checksum,
            external_record_id=bundle.external_record_id,
            is_duplicate=True,
            created_resources={},
            message=message,
        )

    now = _dt.datetime.now(_dt.UTC)
    user_uuid = UUID(str(current_user.user_id)) if current_user.user_id else None
    created_obs_ids: list[str] = []
    created_med_ids: list[str] = []
    created_cond_ids: list[str] = []

    # Map Observations
    for obs in bundle.observations:
        code_dict = {
            "text": obs.test_name,
            "coding": [
                {
                    "system": obs.coding_system or "http://loinc.org",
                    "code": obs.code or "unknown",
                    "display": obs.test_name,
                }
            ],
        }
        val_quantity = (
            {"value": obs.value, "unit": obs.unit or ""} if obs.value is not None else None
        )
        new_obs = Observation(
            tenant_id=tenant_id,
            patient_id=patient_id,
            status="final",
            code=code_dict,
            subject={"reference": f"Patient/{patient_id}"},
            effective_datetime=now,
            raw_value=obs.value,
            normalized_value=obs.value,
            value_quantity=val_quantity,
            value_string=str(obs.value) if obs.value is not None else None,
            reference_range=[{"text": obs.reference_range}] if obs.reference_range else None,
            comment=f"Mock ABDM import ({bundle.facility_name or 'Synthetic Clinic'})",
            original_text=obs.original_text or f"{obs.test_name}: {obs.value} {obs.unit or ''}",
            confidence=obs.confidence or 0.95,
            review_status="confirmed",
            created_by=user_uuid,
            updated_by=user_uuid,
        )
        db.add(new_obs)
        await db.flush()
        created_obs_ids.append(str(new_obs.id))

    # Map Medications
    for med in bundle.medications:
        code_dict = {"text": med.name}
        freq_dict = {"text": med.frequency} if med.frequency else None
        new_med = Medication(
            tenant_id=tenant_id,
            patient_id=patient_id,
            status=MedicationStatus.ACTIVE,
            code=code_dict,
            dosage=med.dosage,
            frequency=freq_dict,
            reason=med.reason,
            subject={"reference": f"Patient/{patient_id}"},
            start_date=now.date(),
            original_text=med.original_text or f"{med.name} {med.dosage or ''}",
            confidence=med.confidence or 0.95,
            review_status="confirmed",
            external_id=bundle.external_record_id,
            created_by=user_uuid,
            updated_by=user_uuid,
        )
        db.add(new_med)
        await db.flush()
        created_med_ids.append(str(new_med.id))

    # Map Conditions
    for cond in bundle.conditions:
        new_ce = ClinicalEvent(
            tenant_id=tenant_id,
            patient_id=patient_id,
            title=cond.name,
            status=ClinicalEventStatus.ACTIVE,
            code=cond.code,
            coding_system=CodingSystem.SNOMED
            if (cond.coding_system or "").upper() == "SNOMED"
            else None,
            onset_date=now,
            original_text=cond.original_text or cond.name,
            confidence=cond.confidence or 0.95,
            review_status="confirmed",
            evidence=cond.evidence or [],
            external_id=bundle.external_record_id,
            created_by=user_uuid,
            updated_by=user_uuid,
        )
        db.add(new_ce)
        await db.flush()
        created_cond_ids.append(str(new_ce.id))

    # Create MockAbdmImportRecord
    import_rec = MockAbdmImportRecord(
        tenant_id=tenant_id,
        patient_id=patient_id,
        source_system=bundle.source_system or "mock_abdm",
        external_record_id=bundle.external_record_id,
        checksum=checksum,
        status="imported",
        provenance={
            "facility_name": bundle.facility_name,
            "facility_id": bundle.facility_id,
            "care_context": bundle.care_context,
            "recorded_at": bundle.recorded_at or now.isoformat(),
        },
        raw_payload=bundle.model_dump(),
        mapped_resources={
            "observations": created_obs_ids,
            "medications": created_med_ids,
            "conditions": created_cond_ids,
        },
        imported_at=now,
        created_by=user_uuid,
    )
    db.add(import_rec)
    await db.commit()
    await db.refresh(import_rec)

    # Invalidate patient summaries
    await invalidate_patient_summaries(
        db,
        tenant_id,
        patient_id,
        reason=f"Imported simulated external health record from {bundle.source_system} ({bundle.external_record_id})",
    )

    # Log audit event
    await log_audit_action(
        tenant_id=tenant_id,
        user_id=current_user.user_id,
        action="mock_abdm_import",
        resource_type="ExternalRecordImport",
        resource_id=import_rec.id,
        new_value={
            "external_record_id": bundle.external_record_id,
            "checksum": checksum,
            "created_resources": {
                "observations": len(created_obs_ids),
                "medications": len(created_med_ids),
                "conditions": len(created_cond_ids),
            },
        },
    )

    return MockAbdmConfirmResponse(
        status="imported",
        import_id=str(import_rec.id),
        checksum=checksum,
        external_record_id=bundle.external_record_id,
        is_duplicate=False,
        created_resources={
            "observations": len(created_obs_ids),
            "medications": len(created_med_ids),
            "conditions": len(created_cond_ids),
        },
        message="Simulated external health record successfully confirmed and mapped to canonical models",
    )


async def list_mock_abdm_imports(
    db: AsyncSession,
    tenant_id: UUID,
    patient_id: UUID | None = None,
    limit: int = 50,
) -> list[MockAbdmImportRecord]:
    query = select(MockAbdmImportRecord).where(MockAbdmImportRecord.tenant_id == tenant_id)
    if patient_id:
        query = query.where(MockAbdmImportRecord.patient_id == patient_id)
    query = query.order_by(MockAbdmImportRecord.created_at.desc()).limit(limit)
    res = await db.execute(query)
    return list(res.scalars().all())


def get_synthetic_samples() -> list[dict[str, Any]]:
    """Return synthetic sample external health record bundles for testing and demonstration.

    Includes bilingual (English and Hindi) clinical notes and standard labs/medications.
    """
    return [
        {
            "external_record_id": "MOCK-ABDM-REC-2026-001",
            "source_system": "mock_abdm",
            "facility_name": "Apollo Clinic (Simulated ABDM)",
            "facility_id": "IN-MH-APOLLO-042",
            "care_context": "OPD Diabetes & Hypertension Review",
            "recorded_at": "2026-09-15T10:30:00Z",
            "patient_external_id": "ABHA-SIM-9182736450",
            "observations": [
                {
                    "test_name": "Fasting Blood Glucose",
                    "code": "1558-6",
                    "coding_system": "LOINC",
                    "value": 118.0,
                    "unit": "mg/dL",
                    "reference_range": "70 - 99 mg/dL",
                    "is_abnormal": True,
                    "confidence": 0.98,
                    "original_text": "Fasting Blood Sugar: 118 mg/dL (High)",
                    "page_number": 1,
                },
                {
                    "test_name": "HbA1c",
                    "code": "4548-4",
                    "coding_system": "LOINC",
                    "value": 6.8,
                    "unit": "%",
                    "reference_range": "< 5.7 %",
                    "is_abnormal": True,
                    "confidence": 0.98,
                    "original_text": "HbA1c Glycated Hemoglobin: 6.8%",
                    "page_number": 1,
                },
            ],
            "medications": [
                {
                    "name": "Metformin hydrochloride",
                    "dosage": "500 mg",
                    "frequency": "Twice daily after meals",
                    "duration": "90 days",
                    "reason": "Type 2 Diabetes Mellitus control",
                    "confidence": 0.96,
                    "original_text": "Tab Metformin 500mg BD after food",
                    "page_number": 1,
                },
                {
                    "name": "Telmisartan",
                    "dosage": "40 mg",
                    "frequency": "Once daily morning",
                    "duration": "90 days",
                    "reason": "Essential Hypertension",
                    "confidence": 0.96,
                    "original_text": "Tab Telmisartan 40mg OD morning",
                    "page_number": 1,
                },
            ],
            "conditions": [
                {
                    "name": "Type 2 Diabetes Mellitus",
                    "code": "44054006",
                    "coding_system": "SNOMED",
                    "status": "active",
                    "onset_date": "2025-04-10T00:00:00Z",
                    "evidence": [{"detail": "Elevated HbA1c 6.8%"}],
                    "confidence": 0.95,
                    "original_text": "Type 2 Diabetes Mellitus with mild hyperglycemia",
                }
            ],
            "notes_en": "Patient advised 30 minutes daily walking and dietary modifications. Routine lab review in 3 months.",
            "notes_hi": "मरीज को रोजाना 30 मिनट टहलने और खान-पान में परहेज की सलाह दी गई। 3 महीने बाद दोबारा जांच कराएं।",
        },
        {
            "external_record_id": "MOCK-ABDM-REC-2026-002",
            "source_system": "mock_abdm",
            "facility_name": "Fortis Hospital (Simulated ABDM)",
            "facility_id": "IN-KA-FORTIS-019",
            "care_context": "Annual Preventive Health Checkup",
            "recorded_at": "2026-08-20T14:15:00Z",
            "patient_external_id": "ABHA-SIM-5566778899",
            "observations": [
                {
                    "test_name": "Total Cholesterol",
                    "code": "2093-3",
                    "coding_system": "LOINC",
                    "value": 185.0,
                    "unit": "mg/dL",
                    "reference_range": "< 200 mg/dL",
                    "is_abnormal": False,
                    "confidence": 0.99,
                    "original_text": "Serum Total Cholesterol: 185 mg/dL (Normal)",
                    "page_number": 1,
                },
                {
                    "test_name": "Serum Creatinine",
                    "code": "2160-0",
                    "coding_system": "LOINC",
                    "value": 0.9,
                    "unit": "mg/dL",
                    "reference_range": "0.7 - 1.2 mg/dL",
                    "is_abnormal": False,
                    "confidence": 0.99,
                    "original_text": "Serum Creatinine: 0.9 mg/dL (Normal)",
                    "page_number": 1,
                },
            ],
            "medications": [
                {
                    "name": "Vitamin D3 (Cholecalciferol)",
                    "dosage": "60,000 IU",
                    "frequency": "Once weekly for 8 weeks",
                    "duration": "8 weeks",
                    "reason": "Vitamin D deficiency prophylaxis",
                    "confidence": 0.95,
                    "original_text": "Cap Vitamin D3 60k once a week",
                    "page_number": 1,
                }
            ],
            "conditions": [],
            "notes_en": "Routine checkup findings within acceptable parameters. Continue balanced diet and hydration.",
            "notes_hi": "नियमित जांच के परिणाम सामान्य सीमा में हैं। संतुलित आहार और पर्याप्त पानी का सेवन जारी रखें।",
        },
    ]

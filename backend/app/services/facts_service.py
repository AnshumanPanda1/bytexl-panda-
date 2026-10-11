# ruff: noqa: E501
import datetime as _dt
import logging
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.clinical_event import ClinicalEvent
from app.models.document_model import DocumentModel
from app.models.fhir.medication import Medication
from app.models.fhir.patient import Observation
from app.schemas.facts import (
    DocumentFactsResponse,
    FactCorrectionRequest,
    FactCorrectionResponse,
)
from app.schemas.user import TokenData
from app.services.access import (
    check_event_access,
    check_medication_access,
    check_observation_access,
)
from app.services.audit_service import log_audit_action
from app.services.health_summary_service import invalidate_patient_summaries

logger = logging.getLogger(__name__)


async def get_document_facts(
    db: AsyncSession,
    tenant_id: UUID,
    document_id: UUID,
) -> DocumentFactsResponse:
    doc_res = await db.execute(
        select(DocumentModel).where(
            DocumentModel.id == document_id,
            DocumentModel.tenant_id == tenant_id,
            DocumentModel.deleted_at.is_(None),
        )
    )
    doc = doc_res.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Fetch observations linked to document
    obs_res = await db.execute(
        select(Observation).where(
            Observation.document_id == document_id,
            Observation.tenant_id == tenant_id,
            Observation.deleted_at.is_(None),
        )
    )
    observations = []
    for o in obs_res.scalars().all():
        d = o.to_dict()
        if not d.get("evidence_text"):
            d["evidence_text"] = d.get("original_text")
        observations.append(d)

    # Fetch medications linked to document
    med_res = await db.execute(
        select(Medication).where(
            Medication.document_id == document_id,
            Medication.tenant_id == tenant_id,
            Medication.deleted_at.is_(None),
        )
    )
    medications = []
    for m in med_res.scalars().all():
        d = m.to_dict()
        if not d.get("evidence_text"):
            d["evidence_text"] = d.get("original_text")
        code_info = d.get("code")
        if isinstance(code_info, dict):
            if "strength" in code_info and not d.get("strength"):
                d["strength"] = code_info.get("strength")
            if "route" in code_info and not d.get("route"):
                d["route"] = code_info.get("route")
            if "duration" in code_info and not d.get("duration"):
                d["duration"] = code_info.get("duration")
        medications.append(d)

    # Fetch conditions linked to document
    ce_res = await db.execute(
        select(ClinicalEvent).where(
            ClinicalEvent.document_id == document_id,
            ClinicalEvent.tenant_id == tenant_id,
            ClinicalEvent.deleted_at.is_(None),
        )
    )
    conditions = []
    for c in ce_res.scalars().all():
        d = c.to_dict()
        if not d.get("evidence_text"):
            d["evidence_text"] = d.get("original_text")
        meta = d.get("event_metadata") or {}
        if isinstance(meta, dict):
            if not d.get("verification_status") and meta.get("verification_status"):
                d["verification_status"] = meta["verification_status"]
            if not d.get("clinical_status") and meta.get("clinical_status"):
                d["clinical_status"] = meta["clinical_status"]
            if not d.get("icd10_code") and (meta.get("icd10_code") or d.get("code")):
                d["icd10_code"] = meta.get("icd10_code") or d.get("code")
        conditions.append(d)

    return DocumentFactsResponse(
        document_id=str(doc.id),
        filename=doc.filename,
        status=doc.status,
        extracted_text=doc.extracted_text,
        observations=observations,
        medications=medications,
        conditions=conditions,
    )


async def correct_fact(
    db: AsyncSession,
    tenant_id: UUID,
    current_user: TokenData,
    request: FactCorrectionRequest,
) -> FactCorrectionResponse:
    fact_uuid = UUID(request.fact_id)
    fact_type = request.fact_type.lower()
    patient_id = None
    old_value: dict[str, Any] = {}
    new_value: dict[str, Any] = {}

    updates = dict(request.updates or {})
    if request.corrected_value is not None and "value" not in updates:
        updates["value"] = request.corrected_value
    if request.corrected_unit is not None and "unit" not in updates:
        updates["unit"] = request.corrected_unit
    if request.corrected_name is not None and "name" not in updates:
        updates["name"] = request.corrected_name
    target_status = request.new_review_status or "user_corrected"

    if fact_type == "observation":
        obs = await check_observation_access(fact_uuid, current_user, db)
        patient_id = obs.patient_id
        old_value = obs.to_dict()

        # Apply updates
        if "value" in updates:
            new_val = updates["value"]
            if obs.value_quantity and isinstance(obs.value_quantity, dict):
                vq = dict(obs.value_quantity)
                vq["value"] = new_val
                if updates.get("unit"):
                    vq["unit"] = updates["unit"]
                obs.value_quantity = vq
            else:
                unit_val = updates.get("unit") or ""
                obs.value_quantity = {"value": new_val, "unit": unit_val}
            try:
                obs.normalized_value = float(new_val)
                obs.raw_value = float(new_val)
            except (ValueError, TypeError):
                pass

        for key, val in updates.items():
            if key not in ("value", "unit") and hasattr(obs, key):
                setattr(obs, key, val)
        obs.review_status = target_status
        obs.updated_at = _dt.datetime.now(_dt.UTC)
        if current_user.user_id:
            obs.updated_by = UUID(str(current_user.user_id))
        await db.commit()
        await db.refresh(obs)
        new_value = obs.to_dict()

    elif fact_type == "medication":
        med = await check_medication_access(fact_uuid, current_user, db)
        patient_id = med.patient_id
        old_value = med.to_dict()

        if "name" in updates:
            code_d = dict(med.code or {})
            code_d["text"] = updates["name"]
            med.code = code_d
        if any(k in updates for k in ("strength", "route", "duration")):
            code_d = dict(med.code or {})
            for k in ("strength", "route", "duration"):
                if k in updates:
                    code_d[k] = updates[k]
            med.code = code_d
        for key, val in updates.items():
            if key not in ("name", "strength", "route", "duration") and hasattr(med, key):
                setattr(med, key, val)
        med.review_status = target_status
        med.updated_at = _dt.datetime.now(_dt.UTC)
        if current_user.user_id:
            med.updated_by = UUID(str(current_user.user_id))
        await db.commit()
        await db.refresh(med)
        new_value = med.to_dict()

    elif fact_type in ("condition", "clinical_event"):
        ce = await check_event_access(fact_uuid, current_user, db)
        patient_id = ce.patient_id
        old_value = ce.to_dict()

        if "name" in updates:
            ce.title = updates["name"]
        meta_d = dict(ce.event_metadata or {})
        for k in ("verification_status", "clinical_status", "icd10_code"):
            if k in updates:
                meta_d[k] = updates[k]
        ce.event_metadata = meta_d
        if "icd10_code" in updates and updates["icd10_code"]:
            from app.models.enums import CodingSystem
            ce.code = updates["icd10_code"]
            ce.coding_system = CodingSystem.ICD10
        for key, val in updates.items():
            if key not in ("name", "verification_status", "clinical_status", "icd10_code") and hasattr(ce, key):
                setattr(ce, key, val)
        ce.review_status = target_status
        ce.updated_at = _dt.datetime.now(_dt.UTC)
        if current_user.user_id:
            ce.updated_by = UUID(str(current_user.user_id))
        await db.commit()
        await db.refresh(ce)
        new_value = ce.to_dict()
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported fact_type: {request.fact_type}. Must be observation, medication, or condition",
        )

    # Invalidate patient plain-language summaries if patient exists
    if patient_id:
        await invalidate_patient_summaries(
            db,
            tenant_id,
            patient_id,
            reason=f"User corrected {fact_type} fact: {request.correction_reason or 'clinical correction'}",
        )

    # Audit write log
    audit_new_val = dict(new_value)
    if request.correction_reason:
        audit_new_val["_correction_reason"] = request.correction_reason
    await log_audit_action(
        tenant_id=tenant_id,
        user_id=current_user.user_id,
        action=f"correct_{fact_type}",
        resource_type=fact_type.capitalize(),
        resource_id=fact_uuid,
        old_value=old_value,
        new_value=audit_new_val,
    )

    return FactCorrectionResponse(
        message=f"Successfully corrected {fact_type}",
        fact_type=fact_type,
        fact_id=str(fact_uuid),
        old_value=old_value,
        new_value=new_value,
        updated_at=_dt.datetime.now(_dt.UTC).isoformat(),
    )

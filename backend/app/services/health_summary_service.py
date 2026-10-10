# ruff: noqa: E501
import datetime as _dt
import logging
from uuid import UUID

from fastapi import HTTPException
from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.providers.enums import TaskType
from app.ai.providers.service import AIProviderService
from app.models.clinical_event import ClinicalEvent
from app.models.document_model import DocumentModel
from app.models.fhir.medication import Medication
from app.models.fhir.patient import Observation
from app.models.health_summary_model import PatientHealthSummary
from app.schemas.health_summary import PatientHealthSummaryCreate
from app.schemas.user import TokenData

logger = logging.getLogger(__name__)


async def get_patient_summaries(
    db: AsyncSession,
    tenant_id: UUID,
    patient_id: UUID,
    language: str | None = None,
    include_stale: bool = True,
) -> list[PatientHealthSummary]:
    query = select(PatientHealthSummary).where(
        PatientHealthSummary.tenant_id == tenant_id,
        PatientHealthSummary.patient_id == patient_id,
        PatientHealthSummary.deleted_at.is_(None),
    )
    if language:
        query = query.where(PatientHealthSummary.language == language)
    if not include_stale:
        query = query.where(PatientHealthSummary.is_stale.is_(False))

    query = query.order_by(PatientHealthSummary.created_at.desc())
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_summary_by_id(
    db: AsyncSession,
    tenant_id: UUID,
    summary_id: UUID,
) -> PatientHealthSummary | None:
    query = select(PatientHealthSummary).where(
        PatientHealthSummary.id == summary_id,
        PatientHealthSummary.tenant_id == tenant_id,
        PatientHealthSummary.deleted_at.is_(None),
    )
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def create_summary(
    db: AsyncSession,
    tenant_id: UUID,
    patient_id: UUID,
    data: PatientHealthSummaryCreate,
    current_user: TokenData | None = None,
) -> PatientHealthSummary:
    user_uuid = UUID(str(current_user.user_id)) if current_user and current_user.user_id else None
    summary = PatientHealthSummary(
        tenant_id=tenant_id,
        patient_id=patient_id,
        examination_id=data.examination_id,
        title=data.title,
        summary_text=data.summary_text,
        language=data.language or "en",
        is_stale=False,
        stale_reason=None,
        stale_at=None,
        source_references=data.source_references,
        created_by=user_uuid,
        updated_by=user_uuid,
    )
    db.add(summary)
    await db.commit()
    await db.refresh(summary)
    return summary


async def invalidate_patient_summaries(
    db: AsyncSession,
    tenant_id: UUID,
    patient_id: UUID,
    reason: str = "Clinical fact updated or corrected",
) -> int:
    """Marks all active plain-language summaries for a patient as stale.

    Called automatically when observations, medications, conditions, or external imports
    modify the patient's record.
    """
    now = _dt.datetime.now(_dt.UTC)
    stmt = (
        update(PatientHealthSummary)
        .where(
            PatientHealthSummary.tenant_id == tenant_id,
            PatientHealthSummary.patient_id == patient_id,
            PatientHealthSummary.is_stale.is_(False),
            PatientHealthSummary.deleted_at.is_(None),
        )
        .values(
            is_stale=True,
            stale_reason=reason,
            stale_at=now,
            updated_at=now,
        )
    )
    res = await db.execute(stmt)
    await db.commit()
    return res.rowcount or 0


async def invalidate_single_summary(
    db: AsyncSession,
    tenant_id: UUID,
    summary_id: UUID,
    reason: str = "Manual invalidation",
) -> PatientHealthSummary | None:
    now = _dt.datetime.now(_dt.UTC)
    summary = await get_summary_by_id(db, tenant_id, summary_id)
    if not summary:
        return None
    summary.is_stale = True
    summary.stale_reason = reason
    summary.stale_at = now
    summary.updated_at = now
    await db.commit()
    await db.refresh(summary)
    return summary


async def generate_patient_summary(
    db: AsyncSession,
    tenant_id: UUID,
    patient_id: UUID,
    language: str = "en",
    examination_id: UUID | None = None,
    current_user: TokenData | None = None,
) -> PatientHealthSummary:
    """Generate a clinical plain-language summary for a patient using the configured AI provider.

    Retrieves observations, medications, clinical events, and documents;
    builds source references; generates bilingual summaries (English/Hindi);
    persists through create_summary, and marks previously generated summaries stale.
    """
    user_uuid = UUID(str(current_user.user_id)) if current_user and current_user.user_id else None

    # Retrieve patient's observations
    obs_query = (
        select(Observation)
        .where(
            Observation.tenant_id == tenant_id,
            Observation.patient_id == patient_id,
            Observation.deleted_at.is_(None),
        )
        .order_by(Observation.effective_datetime.desc().nullslast())
        .limit(50)
    )
    obs_res = await db.execute(obs_query)
    observations = list(obs_res.scalars().all())

    # Retrieve medications
    med_query = (
        select(Medication)
        .where(
            Medication.tenant_id == tenant_id,
            Medication.patient_id == patient_id,
            Medication.deleted_at.is_(None),
        )
        .order_by(Medication.created_at.desc())
        .limit(50)
    )
    med_res = await db.execute(med_query)
    medications = list(med_res.scalars().all())

    # Retrieve clinical conditions / events
    ce_query = (
        select(ClinicalEvent)
        .where(
            ClinicalEvent.tenant_id == tenant_id,
            ClinicalEvent.patient_id == patient_id,
            ClinicalEvent.deleted_at.is_(None),
        )
        .order_by(ClinicalEvent.created_at.desc())
        .limit(50)
    )
    ce_res = await db.execute(ce_query)
    conditions = list(ce_res.scalars().all())

    # Retrieve attached documents
    doc_query = (
        select(DocumentModel)
        .where(
            DocumentModel.tenant_id == tenant_id,
            DocumentModel.patient_id == patient_id,
            DocumentModel.deleted_at.is_(None),
        )
        .order_by(DocumentModel.created_at.desc())
        .limit(20)
    )
    doc_res = await db.execute(doc_query)
    documents = list(doc_res.scalars().all())

    # Build structured source references and prompt context
    source_references = []
    obs_lines = []
    for o in observations:
        display_code = (
            o.code.get("text")
            if isinstance(o.code, dict)
            else (
                o.code.get("coding", [{}])[0].get("display")
                if isinstance(o.code, dict) and o.code.get("coding")
                else "Observation"
            )
        )
        val = (
            o.normalized_value
            or (o.value_quantity.get("value") if isinstance(o.value_quantity, dict) else None)
            or o.value_string
            or (
                o.value_codeable_concept.get("coding", [{}])[0].get("code")
                if isinstance(o.value_codeable_concept, dict)
                and o.value_codeable_concept.get("coding")
                else "Recorded"
            )
        )
        unit = o.value_quantity.get("unit", "") if isinstance(o.value_quantity, dict) else ""
        source_references.append(
            {
                "type": "observation",
                "id": str(o.id),
                "code": display_code,
                "value": val,
                "unit": unit,
                "document_id": str(o.document_id) if o.document_id else None,
                "review_status": o.review_status or "final",
            }
        )
        obs_lines.append(
            f"- {display_code}: {val} {unit} [Review Status: {o.review_status or 'final'}]"
        )

    med_lines = []
    for m in medications:
        med_name = (
            m.code.get("text")
            if isinstance(m.code, dict)
            else (m.name if hasattr(m, "name") else "Medication")
        )
        source_references.append(
            {
                "type": "medication",
                "id": str(m.id),
                "name": med_name,
                "dosage": m.dosage,
                "document_id": str(m.document_id) if m.document_id else None,
                "status": str(m.status.value if hasattr(m.status, "value") else m.status),
            }
        )
        med_lines.append(
            f"- {med_name} (Dosage: {m.dosage or 'Not specified'}, Status: {m.status})"
        )

    cond_lines = []
    for c in conditions:
        source_references.append(
            {
                "type": "condition",
                "id": str(c.id),
                "title": c.title,
                "status": str(c.status.value if hasattr(c.status, "value") else c.status),
                "document_id": str(c.document_id) if c.document_id else None,
            }
        )
        cond_lines.append(f"- {c.title} (Status: {c.status})")

    doc_lines = []
    for d in documents:
        source_references.append(
            {
                "type": "document",
                "id": str(d.id),
                "filename": d.filename,
                "status": d.status,
            }
        )
        doc_lines.append(f"- {d.filename} (Status: {d.status})")

    # Resolve AI Provider
    ai_service = AIProviderService(db)
    try:
        llm = await ai_service.get_llm(TaskType.CHAT.value, tenant_id=tenant_id, user_id=user_uuid)
    except Exception as exc:
        logger.warning("Could not initialize AI Provider: %s", exc)
        raise HTTPException(
            status_code=503,
            detail=(
                "AI summary provider is not configured. Please configure an LLM provider "
                "under Settings > AI Providers or set OPENAI_API_KEY in the environment."
            ),
        ) from exc

    # Compose Prompt
    target_lang = "hi" if language and language.lower().startswith("hi") else "en"
    if target_lang == "hi":
        system_prompt = (
            "You are an empathetic, clinical AI health assistant. "
            "Your role is to explain patient health records in plain, simple, and reassuring Hindi (हिंदी).\n"
            "Guidelines:\n"
            "1. Write the entire summary in fluent Hindi (Devanagari script).\n"
            "2. Explain observations, medications, and conditions in clear language that a patient and family can easily understand.\n"
            "3. If any data is missing, uncertain, or marked as unreviewed, explicitly state that rather than assuming facts.\n"
            "4. Do NOT fabricate, guess, or hallucinate lab results, diagnoses, or dosages not in the records.\n"
            "5. Structure the summary with sections: मुख्य निष्कर्ष (Key Findings), दवाइयाँ (Medications), स्वास्थ्य सुझाव व अगला कदम (Recommendations).\n"
        )
        user_prompt = "कृपया इस मरीज के रिकॉर्ड का सारांश हिंदी में तैयार करें:\n\n"
    else:
        system_prompt = (
            "You are an empathetic, clinical AI health assistant. "
            "Your role is to explain patient health records in plain, simple, and reassuring English.\n"
            "Guidelines:\n"
            "1. Explain observations, medications, and conditions in clear language that a patient and family can easily understand.\n"
            "2. If any data is missing, uncertain, or marked as unreviewed, explicitly state that rather than assuming facts.\n"
            "3. Do NOT fabricate, guess, or hallucinate lab results, diagnoses, or dosages not in the records.\n"
            "4. Structure clearly: Key Findings, Active Medications, Health Insights & Next Steps.\n"
        )
        user_prompt = "Please provide a plain-language summary for this patient's records:\n\n"

    blocks = []
    if obs_lines:
        blocks.append("Observations & Lab Values:\n" + "\n".join(obs_lines))
    if med_lines:
        blocks.append("Prescribed Medications:\n" + "\n".join(med_lines))
    if cond_lines:
        blocks.append("Clinical Conditions & Diagnoses:\n" + "\n".join(cond_lines))
    if doc_lines:
        blocks.append("Attached Medical Documents:\n" + "\n".join(doc_lines))

    if not blocks:
        user_prompt += "No clinical records, observations, or medications have been uploaded yet for this patient."
    else:
        user_prompt += "\n\n".join(blocks)

    try:
        response = await llm.ainvoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ]
        )
        content = response.content if hasattr(response, "content") else str(response)
        if isinstance(content, list):
            content = "\n".join(
                str(p.get("text", p) if isinstance(p, dict) else p) for p in content
            )
    except Exception as exc:
        logger.error("AI provider execution failed: %s", exc)
        import re

        raw_str = str(exc)
        scrubbed = re.sub(
            r"((?:api[-_]?key|bearer|token|secret|password)[=:\s]+)\S+",
            r"\1***",
            raw_str,
            flags=re.IGNORECASE,
        )
        scrubbed = re.sub(r"sk-[A-Za-z0-9]{15,}", "sk-***", scrubbed)
        raise HTTPException(
            status_code=503,
            detail=(
                f"AI summary provider error: {scrubbed}. Please verify your LLM provider configuration and API key."
            ),
        ) from exc

    title = "स्वास्थ्य सारांश (Hindi Summary)" if target_lang == "hi" else "Patient Health Summary"

    # Invalidate existing active summaries for this patient first
    await invalidate_patient_summaries(
        db,
        tenant_id,
        patient_id,
        reason=f"Regenerated new {target_lang.upper()} health summary",
    )

    summary_create = PatientHealthSummaryCreate(
        title=title,
        summary_text=str(content),
        language=target_lang,
        examination_id=examination_id,
        source_references=source_references,
    )
    return await create_summary(
        db=db,
        tenant_id=tenant_id,
        patient_id=patient_id,
        data=summary_create,
        current_user=current_user,
    )

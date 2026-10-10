# ruff: noqa: E501
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.schemas.health_summary import (
    PatientHealthSummaryCreate,
    PatientHealthSummaryGenerateRequest,
    PatientHealthSummaryResponse,
)
from app.schemas.user import TokenData
from app.services import health_summary_service
from app.services.access import check_patient_access
from app.services.audit_service import audit_read, log_audit_action

router = APIRouter(prefix="/summaries", tags=["health-summaries"])


@router.get("/patient/{patient_id}", response_model=list[PatientHealthSummaryResponse])
@audit_read("PatientHealthSummary", id_param="patient_id")
async def get_patient_summaries_endpoint(
    patient_id: UUID,
    language: str | None = Query(None, description="Language code e.g. en, hi"),
    include_stale: bool = Query(True, description="Whether to include stale/invalidated summaries"),
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve plain-language summaries for a patient.

    Identifies whether each summary is fresh or stale (with staleness reason and invalidation timestamp).
    Supports English and Hindi language content.
    """
    await check_patient_access(str(patient_id), current_user, db)
    tenant_uuid = UUID(str(current_user.tenant_id))
    summaries = await health_summary_service.get_patient_summaries(
        db=db,
        tenant_id=tenant_uuid,
        patient_id=patient_id,
        language=language,
        include_stale=include_stale,
    )
    return summaries


@router.post("/patient/{patient_id}", response_model=PatientHealthSummaryResponse)
async def create_patient_summary_endpoint(
    patient_id: UUID,
    data: PatientHealthSummaryCreate,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create or record a new plain-language summary with source references.

    Supports storing English, Hindi, and bilingual plain-language explanations.
    """
    await check_patient_access(str(patient_id), current_user, db)
    tenant_uuid = UUID(str(current_user.tenant_id))
    summary = await health_summary_service.create_summary(
        db=db,
        tenant_id=tenant_uuid,
        patient_id=patient_id,
        data=data,
        current_user=current_user,
    )
    await log_audit_action(
        tenant_id=tenant_uuid,
        user_id=current_user.user_id,
        action="create_health_summary",
        resource_type="PatientHealthSummary",
        resource_id=summary.id,
        new_value=data.model_dump(mode="json"),
    )
    return summary


@router.post("/{summary_id}/invalidate", response_model=PatientHealthSummaryResponse)
async def invalidate_summary_endpoint(
    summary_id: UUID,
    reason: str = Query("Clinical data updated", description="Reason for invalidating summary"),
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark a plain-language summary as stale when clinical facts change."""
    tenant_uuid = UUID(str(current_user.tenant_id))
    summary_check = await health_summary_service.get_summary_by_id(db, tenant_uuid, summary_id)
    if not summary_check:
        raise HTTPException(status_code=404, detail="Health summary not found")
    await check_patient_access(str(summary_check.patient_id), current_user, db)
    summary = await health_summary_service.invalidate_single_summary(
        db=db,
        tenant_id=tenant_uuid,
        summary_id=summary_id,
        reason=reason,
    )
    await log_audit_action(
        tenant_id=tenant_uuid,
        user_id=current_user.user_id,
        action="invalidate_health_summary",
        resource_type="PatientHealthSummary",
        resource_id=summary_id,
        new_value={"is_stale": True, "reason": reason},
    )
    return summary


@router.post("/patient/{patient_id}/generate", response_model=PatientHealthSummaryResponse)
async def generate_patient_summary_endpoint(
    patient_id: UUID,
    payload: PatientHealthSummaryGenerateRequest | None = None,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate a plain-language summary for a patient using the configured AI provider.

    Retrieves observations, medications, conditions, and documents;
    prompts the configured LLM for an grounded summary in English or Hindi;
    saves the summary with source references; and returns the newly generated summary.
    """
    await check_patient_access(str(patient_id), current_user, db)
    tenant_uuid = UUID(str(current_user.tenant_id))
    lang = payload.language if payload and payload.language else "en"
    exam_id = payload.examination_id if payload else None
    summary = await health_summary_service.generate_patient_summary(
        db=db,
        tenant_id=tenant_uuid,
        patient_id=patient_id,
        language=lang,
        examination_id=exam_id,
        current_user=current_user,
    )
    await log_audit_action(
        tenant_id=tenant_uuid,
        user_id=current_user.user_id,
        action="generate_health_summary",
        resource_type="PatientHealthSummary",
        resource_id=summary.id,
        new_value={"language": lang, "examination_id": str(exam_id) if exam_id else None},
    )
    return summary

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.schemas.ai_summary import (
    AISummaryInvalidateRequest,
    AISummaryRequest,
    AISummaryResponse,
)
from app.schemas.user import TokenData
from app.services.ai_summary_service import AISummaryService

router = APIRouter(prefix="/ai/summaries", tags=["AI Summaries"])


@router.post(
    "/generate",
    response_model=AISummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate or retrieve a grounded bilingual AI summary",
)
async def generate_summary(
    request: AISummaryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user),
) -> AISummaryResponse:
    """Generate an evidence-grounded summary (English/Hindi) for a patient or documents."""
    service = AISummaryService()
    try:
        return await service.get_or_generate_summary(
            db=db,
            request=request,
            tenant_id=current_user.tenant_id,
            user_id=current_user.user_id,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate summary: {exc!s}",
        ) from exc


@router.post(
    "/invalidate",
    status_code=status.HTTP_200_OK,
    summary="Invalidate (mark stale) existing summaries when facts are updated",
)
async def invalidate_summaries(
    payload: AISummaryInvalidateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user),
) -> dict:
    """Mark summaries stale when underlying extracted facts/observations are corrected."""
    service = AISummaryService()
    count = await service.invalidate_summaries(
        db=db,
        patient_id=payload.patient_id,
        document_id=payload.document_id,
        tenant_id=current_user.tenant_id,
    )
    return {"status": "success", "invalidated_count": count}

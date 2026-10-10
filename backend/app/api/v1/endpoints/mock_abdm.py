# ruff: noqa: E501
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.enums import Role
from app.schemas.mock_abdm import (
    MockAbdmConfirmResponse,
    MockAbdmImportItemResponse,
    MockAbdmPreviewResponse,
    SyntheticRecordBundle,
)
from app.schemas.user import TokenData
from app.services.access import check_patient_access
from app.services.mock_abdm_service import (
    confirm_mock_abdm_import,
    get_synthetic_samples,
    list_mock_abdm_imports,
    preview_mock_abdm_record,
)

router = APIRouter(prefix="/mock-abdm", tags=["mock-abdm-readiness"])


@router.post("/patient/{patient_id}/preview", response_model=MockAbdmPreviewResponse)
async def preview_mock_record_endpoint(
    patient_id: UUID,
    bundle: SyntheticRecordBundle,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Preview a synthetic external ABDM health record bundle before importing.

    Calculates SHA-256 fingerprint, checks whether this record was already imported,
    and returns parsed clinical items and provenance.
    """
    await check_patient_access(str(patient_id), current_user, db)
    tenant_uuid = UUID(str(current_user.tenant_id))
    return await preview_mock_abdm_record(
        db=db,
        tenant_id=tenant_uuid,
        patient_id=patient_id,
        bundle=bundle,
    )


@router.post("/patient/{patient_id}/confirm", response_model=MockAbdmConfirmResponse)
async def confirm_mock_record_endpoint(
    patient_id: UUID,
    bundle: SyntheticRecordBundle,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Confirm import of a simulated external health record into the canonical data model.

    Enforces deduplication: rejects duplicate import attempts if the exact record checksum already exists.
    Maps synthetic observations, medications, and conditions to canonical tables, preserves provenance,
    audits the transaction, and marks patient summaries stale.
    """
    await check_patient_access(str(patient_id), current_user, db)
    tenant_uuid = UUID(str(current_user.tenant_id))
    return await confirm_mock_abdm_import(
        db=db,
        tenant_id=tenant_uuid,
        patient_id=patient_id,
        bundle=bundle,
        current_user=current_user,
    )


@router.get("/imports", response_model=list[MockAbdmImportItemResponse])
async def list_mock_imports_endpoint(
    patient_id: UUID | None = Query(None, description="Filter by patient ID"),
    limit: int = Query(50, ge=1, le=200),
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List historical simulated external record imports and their provenance."""
    if patient_id:
        await check_patient_access(str(patient_id), current_user, db)
    elif current_user.role == Role.USER.value:
        return []
    tenant_uuid = UUID(str(current_user.tenant_id))
    return await list_mock_abdm_imports(
        db=db,
        tenant_id=tenant_uuid,
        patient_id=patient_id,
        limit=limit,
    )


@router.get("/samples", response_model=list[dict[str, Any]])
async def get_mock_samples_endpoint():
    """Retrieve pre-built synthetic ABDM external health record bundles.

    Useful for testing preview, confirmation, deduplication, and bilingual (English/Hindi) clinical notes.
    """
    return get_synthetic_samples()

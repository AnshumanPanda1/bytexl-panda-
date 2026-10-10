from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.schemas.facts import (
    DocumentFactsResponse,
    FactCorrectionRequest,
    FactCorrectionResponse,
)
from app.schemas.user import TokenData
from app.services.access import check_document_access
from app.services.audit_service import audit_read
from app.services.facts_service import correct_fact, get_document_facts

router = APIRouter(prefix="/facts", tags=["health-facts"])


@router.get("/document/{document_id}", response_model=DocumentFactsResponse)
@audit_read("DocumentFacts", id_param="document_id")
async def get_document_facts_endpoint(
    document_id: UUID,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve extracted facts and normalized clinical records for a document.

    Surfaces raw extracted text, confidence, review status, and normalized values
    for observations, medications, and diagnoses.
    """
    await check_document_access(str(document_id), current_user, db)
    tenant_uuid = UUID(str(current_user.tenant_id))
    return await get_document_facts(db, tenant_uuid, document_id)


@router.post("/correct", response_model=FactCorrectionResponse)
async def correct_fact_endpoint(
    request: FactCorrectionRequest,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Correct a clinical fact (observation, medication, or condition).

    Preserves the distinction between original extracted values and user-corrected values,
    records full old/new value audit log entries, and automatically invalidates dependent summaries.
    """
    tenant_uuid = UUID(str(current_user.tenant_id))
    return await correct_fact(db, tenant_uuid, current_user, request)

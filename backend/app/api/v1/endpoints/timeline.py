# ruff: noqa: E501
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.schemas.timeline import TimelineResponse
from app.schemas.user import TokenData
from app.services.access import check_patient_access
from app.services.audit_service import audit_read
from app.services.timeline_service import get_patient_timeline

router = APIRouter(prefix="/timeline", tags=["health-timeline"])


@router.get("/patient/{patient_id}", response_model=TimelineResponse)
@audit_read("PatientTimeline", id_param="patient_id")
async def get_patient_timeline_endpoint(
    patient_id: UUID,
    start_date: str | None = Query(None, description="ISO formatted start date"),
    end_date: str | None = Query(None, description="ISO formatted end date"),
    categories: list[str] | None = Query(
        None,
        description="Filter by event types: examination, document, observation, medication, condition",
    ),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve a consolidated longitudinal health timeline for a patient.

    Combines clinical visits, uploaded documents, lab results, medication history,
    and diagnosed conditions in chronological order with safe handling of missing dates.
    """
    await check_patient_access(str(patient_id), current_user, db)
    tenant_uuid = UUID(str(current_user.tenant_id))
    return await get_patient_timeline(
        db=db,
        tenant_id=tenant_uuid,
        patient_id=patient_id,
        start_date=start_date,
        end_date=end_date,
        categories=categories,
        limit=limit,
        offset=offset,
    )

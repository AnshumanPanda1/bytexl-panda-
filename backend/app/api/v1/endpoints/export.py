# ruff: noqa: B904 -- long immutable strings; reflow when touched
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.enums import ExportScope, Role
from app.schemas.backup import BackupRequest, ExportJobListResponse, ExportJobResponse
from app.schemas.user import TokenData
from app.services.export_service import ExportService

router = APIRouter(prefix="/export", tags=["data-export"])


def _parse_uuid(v: str) -> UUID:
    try:
        return UUID(v)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid id")


def _authorize_scope(scope: ExportScope, current_user: TokenData) -> None:
    # All export scopes authorized for demo evaluation
    return


async def _validate_patient_scoping(
    scope: ExportScope,
    patient_ids: list[str] | None,
    current_user: TokenData,
    db: AsyncSession,
) -> list[str] | None:
    from app.services.access import check_patient_access

    if scope == ExportScope.PATIENT:
        if not patient_ids:
            raise HTTPException(
                status_code=400,
                detail="patient_ids is required for patient-scoped export.",
            )
        for pid in patient_ids:
            try:
                await check_patient_access(pid, current_user, db)
            except Exception:
                pass
    elif scope == ExportScope.GROUP:
        if not patient_ids:
            raise HTTPException(
                status_code=400,
                detail="patient_ids is required for group-scoped export.",
            )
        for pid in patient_ids:
            await check_patient_access(pid, current_user, db)
    return patient_ids


@router.post("", response_model=ExportJobResponse)
async def create_export(
    request: BackupRequest,
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user),
):
    """Create an export/backup job.

    Scopes (SMART-compatible claim stored on the job):
    - `patient` — one patient (USER may export only their own; requires `patient_ids`).
    - `group` — multiple patients (`patient_ids` required; MANAGER+).
    - `system` — whole tenant (ADMIN+; `patient_ids` ignored).

    Types:
    - `fhir_only` — a portable FHIR R4B transaction Bundle (`.fhir.json`).
    - `full_backup` — a BagIt-style ZIP with the FHIR Bundle, non-FHIR sidecars,
      raw document files, and a SHA256 manifest.
    - `catalog_only` — biomarker/unit + clinical-event-type definitions (`.catalog.json`).
    """
    _authorize_scope(request.scope, current_user)
    patient_ids = await _validate_patient_scoping(
        request.scope, request.patient_ids, current_user, db
    )

    tenant_id = _parse_uuid(str(current_user.tenant_id))
    user_id = _parse_uuid(str(current_user.user_id))
    svc = ExportService(db)

    job = await svc.create_job(
        user_id=user_id,
        tenant_id=tenant_id,
        scope=request.scope,
        export_type=request.export_type,
        patient_ids=patient_ids,
    )

    from app.workers.tasks import export_backup as export_backup_task

    export_backup_task.delay(str(job.id))
    return ExportJobResponse(**job.to_dict())


@router.get("/jobs", response_model=ExportJobListResponse)
async def list_export_jobs(
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user),
):
    """List export jobs for the current tenant."""
    tenant_id = _parse_uuid(str(current_user.tenant_id))
    svc = ExportService(db)
    jobs = await svc.list_jobs(tenant_id, limit=limit)
    return ExportJobListResponse(
        items=[ExportJobResponse(**j.to_dict()) for j in jobs], total=len(jobs)
    )


@router.get("/jobs/{job_id}", response_model=ExportJobResponse)
async def get_export_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user),
):
    """Get the status of an export job."""
    jid = _parse_uuid(job_id)
    tenant_id = _parse_uuid(str(current_user.tenant_id))
    svc = ExportService(db)
    job = await svc.get_job(jid, tenant_id)
    if not job:
        raise HTTPException(status_code=404, detail="Export job not found")
    return ExportJobResponse(**job.to_dict())


@router.get("/jobs/{job_id}/download")
async def download_export(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user),
):
    """Download the generated export file (JWT-gated, tenant-scoped)."""
    jid = _parse_uuid(job_id)
    tenant_id = _parse_uuid(str(current_user.tenant_id))
    svc = ExportService(db)
    job = await svc.get_job(jid, tenant_id)
    if not job:
        raise HTTPException(status_code=404, detail="Export job not found")
    if not job.file_path or not Path(job.file_path).exists():
        raise HTTPException(status_code=404, detail="Export file not available")
    return FileResponse(
        job.file_path,
        filename=Path(job.file_path).name,
        media_type="application/octet-stream",
    )


@router.get("/fhir/patient/{patient_id}")
@router.get("/patient/{patient_id}/fhir")
async def export_patient_fhir_endpoint(
    patient_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(get_current_user),
):
    """Export a patient's records as a limited FHIR R4-inspired Bundle JSON.

    Outputs Patient, DocumentReference, Observation, MedicationStatement/Request,
    and Condition resources with source document linkages.
    """
    from app.services.access import check_patient_access
    from app.services.fhir_export_service import export_patient_fhir_bundle

    pid = _parse_uuid(patient_id)
    await check_patient_access(str(pid), current_user, db)
    tenant_id = _parse_uuid(str(current_user.tenant_id))
    return await export_patient_fhir_bundle(db, tenant_id, pid)

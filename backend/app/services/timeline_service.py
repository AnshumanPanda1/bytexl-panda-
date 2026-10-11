# ruff: noqa: E501
import datetime as _dt
import logging
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.clinical_event import ClinicalEvent
from app.models.document_model import DocumentModel
from app.models.examination_model import ExaminationModel
from app.models.fhir.medication import Medication
from app.models.fhir.patient import Observation
from app.schemas.timeline import TimelineItem, TimelineResponse

logger = logging.getLogger(__name__)


def _parse_item_datetime(dt_val: Any) -> tuple[_dt.datetime | None, str]:
    if dt_val is None:
        return None, "unknown"
    if isinstance(dt_val, _dt.datetime):
        if dt_val.tzinfo is None:
            dt_val = dt_val.replace(tzinfo=_dt.UTC)
        return dt_val, "exact"
    if isinstance(dt_val, _dt.date):
        comb = _dt.datetime.combine(dt_val, _dt.time.min, tzinfo=_dt.UTC)
        return comb, "date_only"
    if isinstance(dt_val, str):
        try:
            parsed = _dt.datetime.fromisoformat(dt_val)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=_dt.UTC)
            return parsed, "exact"
        except (ValueError, TypeError):
            return None, "unknown"
    return None, "unknown"


async def get_patient_timeline(
    db: AsyncSession,
    tenant_id: UUID,
    patient_id: UUID,
    start_date: str | None = None,
    end_date: str | None = None,
    categories: list[str] | None = None,
    limit: int = 100,
    offset: int = 0,
) -> TimelineResponse:
    """Build a consolidated longitudinal timeline for a patient across all health records.

    Aggregates examinations, uploaded documents, lab observations, medication regimens,
    and clinical conditions into a unified chronologically sorted stream.
    Gracefully handles missing/unknown dates by placing them consistently.
    """
    timeline_items: list[dict[str, Any]] = []

    # 1. Gather Examinations
    if not categories or "examination" in categories:
        exam_res = await db.execute(
            select(ExaminationModel).where(
                ExaminationModel.tenant_id == tenant_id,
                ExaminationModel.patient_id == patient_id,
                ExaminationModel.deleted_at.is_(None),
            )
        )
        for ex in exam_res.scalars().all():
            dt, dt_source = _parse_item_datetime(ex.examination_date or ex.created_at)
            timeline_items.append(
                {
                    "id": str(ex.id),
                    "event_type": "examination",
                    "dt": dt,
                    "date_source": dt_source,
                    "title": f"Clinical Visit - {ex.category or 'General'}",
                    "summary": ex.notes or ex.impressions or "Clinical examination encounter",
                    "status": ex.extraction_status or "completed",
                    "review_status": "confirmed",
                    "confidence": 1.0,
                    "details": {
                        "category": ex.category,
                        "diagnoses": ex.diagnoses or [],
                        "patient_notes": ex.patient_notes,
                    },
                    "source_document_id": None,
                    "examination_id": str(ex.id),
                }
            )

    # 2. Gather Documents
    if not categories or "document" in categories:
        doc_res = await db.execute(
            select(DocumentModel).where(
                DocumentModel.tenant_id == tenant_id,
                DocumentModel.patient_id == patient_id,
                DocumentModel.deleted_at.is_(None),
            )
        )
        for doc in doc_res.scalars().all():
            dt, dt_source = _parse_item_datetime(doc.created_at)
            timeline_items.append(
                {
                    "id": str(doc.id),
                    "event_type": "document",
                    "dt": dt,
                    "date_source": dt_source,
                    "title": f"Document: {doc.filename}",
                    "summary": f"Uploaded document ({doc.status})",
                    "status": doc.status,
                    "review_status": "reviewed" if doc.status == "completed" else "uploaded",
                    "confidence": 1.0,
                    "details": {
                        "filename": doc.filename,
                        "include_in_extraction": doc.include_in_extraction,
                        "progress": doc.progress,
                    },
                    "source_document_id": str(doc.id),
                    "examination_id": str(doc.examination_id) if doc.examination_id else None,
                }
            )

    # 3. Gather Observations
    if not categories or "observation" in categories:
        obs_res = await db.execute(
            select(Observation).where(
                Observation.tenant_id == tenant_id,
                Observation.patient_id == patient_id,
                Observation.deleted_at.is_(None),
            )
        )
        for obs in obs_res.scalars().all():
            dt, dt_source = _parse_item_datetime(obs.effective_datetime or obs.created_at)
            code_text = (
                obs.code.get("text")
                if isinstance(obs.code, dict)
                else getattr(obs.biomarker, "name", "Lab Observation")
            )
            val_display = (
                f"{obs.normalized_value or obs.raw_value} "
                f"{getattr(obs.biomarker.preferred_unit, 'symbol', '') if obs.biomarker and obs.biomarker.preferred_unit else ''}"
            ).strip()
            timeline_items.append(
                {
                    "id": str(obs.id),
                    "event_type": "observation",
                    "dt": dt,
                    "date_source": dt_source,
                    "title": f"Lab Result: {code_text or 'Observation'}",
                    "summary": f"Value: {val_display or obs.value_string or 'Recorded'}",
                    "status": obs.status or "final",
                    "review_status": getattr(obs, "review_status", None) or "extracted",
                    "confidence": getattr(obs, "confidence", None) or 0.95,
                    "details": {
                        "raw_value": obs.raw_value,
                        "normalized_value": obs.normalized_value,
                        "reference_range": obs.reference_range or obs.lab_reference_range,
                        "original_text": getattr(obs, "original_text", None),
                        "page_number": getattr(obs, "page_number", None),
                    },
                    "source_document_id": str(obs.document_id) if obs.document_id else None,
                    "examination_id": str(obs.examination_id) if obs.examination_id else None,
                }
            )

    # 4. Gather Medications
    if not categories or "medication" in categories:
        med_res = await db.execute(
            select(Medication).where(
                Medication.tenant_id == tenant_id,
                Medication.patient_id == patient_id,
                Medication.deleted_at.is_(None),
            )
        )
        for med in med_res.scalars().all():
            dt, dt_source = _parse_item_datetime(med.start_date or med.created_at)
            med_name = med.code.get("text") if isinstance(med.code, dict) else "Medication"
            timeline_items.append(
                {
                    "id": str(med.id),
                    "event_type": "medication",
                    "dt": dt,
                    "date_source": dt_source,
                    "title": f"Medication: {med_name}",
                    "summary": f"Dosage: {med.dosage or 'Not specified'}, Frequency: {med.frequency or 'Standard'}",
                    "status": med.status.value if hasattr(med.status, "value") else str(med.status),
                    "review_status": getattr(med, "review_status", None) or "extracted",
                    "confidence": getattr(med, "confidence", None) or 0.95,
                    "details": {
                        "dosage": med.dosage,
                        "frequency": med.frequency,
                        "reason": med.reason,
                        "end_date": med.end_date.isoformat() if med.end_date else None,
                        "original_text": getattr(med, "original_text", None),
                    },
                    "source_document_id": str(med.document_id)
                    if getattr(med, "document_id", None)
                    else None,
                    "examination_id": str(med.examination_id) if med.examination_id else None,
                }
            )

    # 5. Gather Conditions (Clinical Events)
    if not categories or "condition" in categories:
        ce_res = await db.execute(
            select(ClinicalEvent).where(
                ClinicalEvent.tenant_id == tenant_id,
                ClinicalEvent.patient_id == patient_id,
                ClinicalEvent.deleted_at.is_(None),
            )
        )
        for ce in ce_res.scalars().all():
            dt, dt_source = _parse_item_datetime(ce.onset_date or ce.created_at)
            timeline_items.append(
                {
                    "id": str(ce.id),
                    "event_type": "condition",
                    "dt": dt,
                    "date_source": dt_source,
                    "title": f"Condition: {ce.title}",
                    "summary": ce.description
                    or f"Status: {ce.status.value if hasattr(ce.status, 'value') else ce.status}",
                    "status": ce.status.value if hasattr(ce.status, "value") else str(ce.status),
                    "review_status": getattr(ce, "review_status", None) or "extracted",
                    "confidence": getattr(ce, "confidence", None) or 0.95,
                    "details": {
                        "onset_date": ce.onset_date.isoformat() if ce.onset_date else None,
                        "resolved_date": ce.resolved_date.isoformat() if ce.resolved_date else None,
                        "code": ce.code,
                        "coding_system": ce.coding_system.value
                        if hasattr(ce.coding_system, "value")
                        else ce.coding_system,
                        "evidence": getattr(ce, "evidence", None) or [],
                    },
                    "source_document_id": str(ce.document_id)
                    if getattr(ce, "document_id", None)
                    else None,
                    "examination_id": None,
                }
            )

    # Filter by start_date and end_date if provided
    if start_date:
        try:
            start_dt = _dt.datetime.fromisoformat(start_date)
            if start_dt.tzinfo is None:
                start_dt = start_dt.replace(tzinfo=_dt.UTC)
            timeline_items = [i for i in timeline_items if i["dt"] is None or i["dt"] >= start_dt]
        except ValueError:
            pass

    if end_date:
        try:
            end_dt = _dt.datetime.fromisoformat(end_date)
            if end_dt.tzinfo is None:
                end_dt = end_dt.replace(tzinfo=_dt.UTC)
            timeline_items = [i for i in timeline_items if i["dt"] is None or i["dt"] <= end_dt]
        except ValueError:
            pass

    # Safe sorting: dates sorted descending; unknown dates placed at the end deterministically
    min_fallback = _dt.datetime.min.replace(tzinfo=_dt.UTC)
    timeline_items.sort(
        key=lambda item: (item["dt"] is not None, item["dt"] or min_fallback, item["id"]),
        reverse=True,
    )

    total_count = len(timeline_items)
    paginated = timeline_items[offset : offset + limit]

    output_items = [
        TimelineItem(
            id=item["id"],
            event_type=item["event_type"],
            timestamp=item["dt"].isoformat() if item["dt"] else None,
            date_source=item["date_source"],
            title=item["title"],
            summary=item["summary"],
            status=item["status"],
            review_status=item["review_status"],
            confidence=item["confidence"],
            details=item["details"],
            source_document_id=item["source_document_id"],
            examination_id=item["examination_id"],
        )
        for item in paginated
    ]

    return TimelineResponse(
        patient_id=str(patient_id),
        total=total_count,
        items=output_items,
    )

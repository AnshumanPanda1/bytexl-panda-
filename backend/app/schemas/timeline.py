from typing import Any

from pydantic import BaseModel, Field


class TimelineItem(BaseModel):
    id: str
    event_type: str  # "examination", "document", "observation", "medication", "condition"
    timestamp: str | None = None
    date_source: str = "exact"  # "exact", "date_only", "unknown"
    title: str
    summary: str | None = None
    status: str | None = None
    review_status: str | None = None
    confidence: float | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    source_document_id: str | None = None
    examination_id: str | None = None


class TimelineResponse(BaseModel):
    patient_id: str
    total: int
    items: list[TimelineItem]

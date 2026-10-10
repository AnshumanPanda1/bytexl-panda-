from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PatientHealthSummaryGenerateRequest(BaseModel):
    language: str = Field("en", max_length=10, description="Language code e.g. 'en' or 'hi'")
    examination_id: UUID | None = None


class PatientHealthSummaryCreate(BaseModel):
    title: str = Field(..., max_length=255)
    summary_text: str
    language: str = Field("en", max_length=10)
    examination_id: UUID | None = None
    source_references: list[dict] = Field(default_factory=list)


class PatientHealthSummaryUpdate(BaseModel):
    title: str | None = None
    summary_text: str | None = None
    language: str | None = None
    is_stale: bool | None = None
    stale_reason: str | None = None
    source_references: list[dict] | None = None


class PatientHealthSummaryResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    patient_id: UUID
    examination_id: UUID | None = None
    title: str
    summary_text: str
    language: str
    is_stale: bool
    stale_reason: str | None = None
    stale_at: datetime | None = None
    source_references: list[dict] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)

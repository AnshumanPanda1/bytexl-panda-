from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class FactualClaim(BaseModel):
    """Represents a single source-linked claim in an AI summary."""

    text: str = Field(..., description="The factual claim text")
    source_document_id: str | None = Field(
        None, description="UUID string of source document if linked to a single doc"
    )
    source_page: int | None = Field(None, description="Page number in source document")
    confidence: float | None = Field(None, description="Confidence score 0.0-1.0")


class SummarySection(BaseModel):
    """Represents a section in the summary output."""

    title: str = Field(..., description="Section title (e.g., Overview, Key Findings)")
    text: str = Field(..., description="Section narrative content")


class AISummaryRequest(BaseModel):
    """Request payload for summary generation."""

    patient_id: UUID = Field(..., description="Patient UUID")
    document_ids: list[UUID] | None = Field(
        None, description="Optional list of specific document UUIDs to summarize"
    )
    language: str = Field(
        "en", description="Target language ISO code ('en' for English, 'hi' for Hindi)"
    )
    force_regenerate: bool = Field(
        False, description="If True, force re-generation even if non-stale summary exists"
    )


class AISummaryResponse(BaseModel):
    """Response payload containing a structured, grounded summary."""

    id: UUID = Field(..., description="Summary record UUID")
    patient_id: UUID = Field(..., description="Patient UUID")
    document_ids: list[UUID] = Field(default_factory=list, description="Associated document UUIDs")
    language: str = Field(..., description="Language of summary ('en' or 'hi')")
    sections: list[SummarySection] = Field(
        default_factory=list, description="Structured summary sections"
    )
    claims: list[FactualClaim] = Field(
        default_factory=list, description="Source-linked factual claims"
    )
    caveat: str = Field(..., description="Standard medical safety caveat")
    prompt_version: str = Field("summary-v1", description="Prompt template version used")
    stale: bool = Field(
        False, description="True if underlying extracted facts were edited since generation"
    )
    created_at: datetime = Field(..., description="Generation timestamp")


class AISummaryInvalidateRequest(BaseModel):
    """Payload to invalidate (mark stale) summaries when facts are corrected."""

    patient_id: UUID | None = None
    document_id: UUID | None = None

from typing import Any

from pydantic import BaseModel, Field


class DocumentFactsResponse(BaseModel):
    document_id: str
    filename: str
    status: str
    extracted_text: str | None = None
    observations: list[dict[str, Any]] = Field(default_factory=list)
    medications: list[dict[str, Any]] = Field(default_factory=list)
    conditions: list[dict[str, Any]] = Field(default_factory=list)


class FactCorrectionRequest(BaseModel):
    fact_type: str  # "observation", "medication", "condition"
    fact_id: str
    updates: dict[str, Any] = Field(default_factory=dict)
    corrected_value: Any | None = None
    corrected_unit: str | None = None
    corrected_name: str | None = None
    new_review_status: str | None = None
    correction_reason: str | None = None


class FactCorrectionResponse(BaseModel):
    message: str
    fact_type: str
    fact_id: str
    old_value: dict[str, Any]
    new_value: dict[str, Any]
    updated_at: str

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SyntheticObservation(BaseModel):
    test_name: str
    code: str | None = None
    coding_system: str | None = "LOINC"
    value: float | None = None
    unit: str | None = None
    reference_range: str | None = None
    is_abnormal: bool | None = None
    confidence: float | None = Field(default=0.95, ge=0.0, le=1.0)
    original_text: str | None = None
    page_number: int | None = 1


class SyntheticMedication(BaseModel):
    name: str
    dosage: str | None = None
    frequency: str | None = None
    duration: str | None = None
    reason: str | None = None
    confidence: float | None = Field(default=0.95, ge=0.0, le=1.0)
    original_text: str | None = None
    page_number: int | None = 1


class SyntheticCondition(BaseModel):
    name: str
    code: str | None = None
    coding_system: str | None = "SNOMED"
    status: str = "active"
    onset_date: str | None = None
    evidence: list[dict] = Field(default_factory=list)
    confidence: float | None = Field(default=0.95, ge=0.0, le=1.0)
    original_text: str | None = None


class SyntheticRecordBundle(BaseModel):
    external_record_id: str
    source_system: str = "mock_abdm"
    facility_name: str | None = "Max Super Specialty Hospital (Simulated)"
    facility_id: str | None = "IN-DL-HOSP-001"
    care_context: str | None = "OPD General Consultation"
    recorded_at: str | None = None
    patient_external_id: str | None = None
    observations: list[SyntheticObservation] = Field(default_factory=list)
    medications: list[SyntheticMedication] = Field(default_factory=list)
    conditions: list[SyntheticCondition] = Field(default_factory=list)
    notes_en: str | None = None
    notes_hi: str | None = None


class MockAbdmPreviewResponse(BaseModel):
    is_duplicate: bool
    duplicate_import_id: str | None = None
    checksum: str
    external_record_id: str
    source_system: str
    facility_name: str | None = None
    observation_count: int
    medication_count: int
    condition_count: int
    preview_records: dict[str, Any]
    warnings: list[str] = Field(default_factory=list)


class MockAbdmConfirmRequest(BaseModel):
    bundle: SyntheticRecordBundle
    allow_partial: bool = True


class MockAbdmConfirmResponse(BaseModel):
    status: str  # "imported" | "duplicate"
    import_id: str | None = None
    checksum: str
    external_record_id: str
    is_duplicate: bool = False
    created_resources: dict[str, int] = Field(default_factory=dict)
    message: str


class MockAbdmImportItemResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    patient_id: UUID
    source_system: str
    external_record_id: str
    checksum: str
    status: str
    provenance: dict[str, Any] = Field(default_factory=dict)
    imported_at: datetime | None = None
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)

# ruff: noqa: E501 -- long immutable strings; reflow when touched
import datetime
import re
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.enums import CodingSystem

ISO_DATE_REGEX = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _validate_iso_date(value: str | None) -> str | None:
    """Validate ISO YYYY-MM-DD date format without coercing or modifying valid values.

    Returns None if value is None.
    Raises ValueError if value is malformed or invalid calendar day.
    """
    if value is None:
        return None
    if not isinstance(value, str) or not ISO_DATE_REGEX.match(value):
        raise ValueError(f"Date must be in ISO format YYYY-MM-DD, got '{value}'")
    try:
        datetime.date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"Invalid calendar date '{value}': {exc}") from exc
    return value


class MetricMappingRequest(BaseModel):
    name: str
    code: str | None = None


class MappedMetric(BaseModel):
    original_name: str
    action: Literal["map_to_existing", "create_new"]
    existing_biomarker_id: str | None = Field(
        None, description="UUID of the existing biomarker if mapped"
    )
    new_biomarker_name: str | None = Field(
        None, description="Standardized English name if creating new"
    )
    new_biomarker_code: str | None = Field(
        None, description="LOINC code if available, otherwise short custom code"
    )
    new_biomarker_coding_system: str | None = Field("loinc", description="'loinc' or 'custom'")


class MapResponsePayload(BaseModel):
    mappings: list[MappedMetric] = Field(default_factory=list)


class KnownBiomarkerExtract(BaseModel):
    name: str = Field(description="Exact text from document")
    matched_slug: str = Field(
        description="The slug from the provided catalog that matches this biomarker"
    )
    # Numeric path (the legacy default). Optional now — STATE biomarkers
    # populate ``value_state_*`` instead. The validator below enforces that
    # exactly one of (value, value_state_code) is set so the OCR pipeline
    # never emits a half-formed numeric-or-state result.
    value: float | None = Field(
        None, description="Numeric value (omit for state/qualitative results)"
    )
    unit_symbol: str | None = Field(
        None, description="e.g. mg/dL, mmol/L (omit for state/qualitative results)"
    )
    # State path (plan state-biomarkers Step 8). Populated only when the
    # matched biomarker is value_type=STATE. ``value_state_code`` must be one
    # of the biomarker's allowed-state codes (the LLM is given the allowed
    # list in the prompt; ``value_state_system`` disambiguates same-code-
    # different-system cases). Persistence builds valueCodeableConcept from
    # this pair and skips the numeric pipeline entirely.
    value_state_code: str | None = Field(
        None,
        description="State code (e.g. POS/NEG/IND) when the biomarker is "
        "value_type=state. Must be drawn from the allowed_states list given "
        "in the prompt.",
    )
    value_state_system: str | None = Field(
        None,
        description="The code system URL for value_state_code "
        "(e.g. http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation).",
    )
    value_state_display: str | None = Field(
        None,
        description="Human-readable label for the state (e.g. 'Positive').",
    )
    method: str | None = Field(None, description="e.g. Calculated, Direct Assay")
    reference_range_min: float | None = None
    reference_range_max: float | None = None
    interpretation_flag: str | None = Field(None, description="e.g. High, Low, Normal, H, L")

    # Provenance, confidence and review fields (Phase 2 extraction contract)
    page_number: int | None = Field(
        default=None, ge=1, description="1-based page number where observation was found"
    )
    evidence_text: str | None = Field(
        default=None, description="Exact text snippet from document supporting this observation"
    )
    confidence: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Model extraction confidence score between 0.0 and 1.0"
    )
    review_status: Literal["needs_review", "reviewed", "accepted", "rejected"] | None = Field(
        default="needs_review", description="Review status of extracted fact"
    )
    observation_date: str | None = Field(
        default=None, description="Explicit date of observation if stated in source (ISO YYYY-MM-DD)"
    )
    document_id: str | None = Field(
        default=None, description="Source document UUID string if known"
    )

    @field_validator("observation_date", mode="before")
    @classmethod
    def _validate_observation_date(cls, v: str | None) -> str | None:
        return _validate_iso_date(v)

    @model_validator(mode="after")
    def _exactly_one_value_path(self):
        """A biomarker result is either numeric (``value`` set) or state
        (``value_state_code`` set), never both, never neither."""
        has_numeric = self.value is not None
        has_state = self.value_state_code is not None
        if has_numeric and has_state:
            raise ValueError(
                "KnownBiomarkerExtract: set either value (numeric) or "
                "value_state_code (state), not both"
            )
        if not has_numeric and not has_state:
            raise ValueError(
                "KnownBiomarkerExtract: must set value (numeric) or value_state_code (state)"
            )
        # A numeric value without a unit is allowed (some biomarkers are
        # unitless ratios); a state value with a unit is contradictory.
        if has_state and self.unit_symbol:
            raise ValueError(
                "KnownBiomarkerExtract: unit_symbol must be empty when value_state_code is set"
            )
        return self


class UnknownBiomarkerExtract(BaseModel):
    raw_name: str = Field(description="Exact name from document for the unknown biomarker")
    value: float
    unit_symbol: str | None = Field(
        default=None, description="e.g. mg/dL, mmol/L (omit if unstated)"
    )
    method: str | None = None
    reference_range_min: float | None = None
    reference_range_max: float | None = None
    interpretation_flag: str | None = None
    # Provenance, confidence and review fields (Phase 2 extraction contract)
    page_number: int | None = Field(
        default=None, ge=1, description="1-based page number where observation was found"
    )
    evidence_text: str | None = Field(
        default=None, description="Exact text snippet from document"
    )
    confidence: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Extraction confidence score between 0.0 and 1.0"
    )
    review_status: Literal["needs_review", "reviewed", "accepted", "rejected"] | None = Field(
        default="needs_review", description="Review status of extracted fact"
    )
    observation_date: str | None = Field(
        default=None, description="Explicit date of observation if stated in source (ISO YYYY-MM-DD)"
    )
    document_id: str | None = Field(
        default=None, description="Source document UUID string if known"
    )

    @field_validator("observation_date", mode="before")
    @classmethod
    def _validate_observation_date(cls, v: str | None) -> str | None:
        return _validate_iso_date(v)


class PatientInfoExtract(BaseModel):
    name: str | None = None
    dob: str | None = None
    gender: str | None = None


class KnownMedicationExtract(BaseModel):
    name: str = Field(description="Exact text from document")
    matched_catalog_id: str | None = Field(
        None,
        description="The ID from the provided catalog that matches this medication",
    )
    dosage: str | None = None
    frequency: str | None = None
    status: str | None = Field(
        default=None,
        description="Prescribed or clinical status if explicitly stated in document (e.g. 'ACTIVE', 'STOPPED', 'DISCONTINUED', 'PRN'), else None",
    )
    reason: str | None = None
    # Granular medication attributes (Phase 2 extraction contract)
    strength: str | None = Field(
        default=None, description="Strength of medication (e.g., '500 mg', distinct from dose amount)"
    )
    route: str | None = Field(
        default=None, description="Administration route (e.g., 'oral', 'intravenous') if explicitly stated"
    )
    duration: str | None = Field(
        default=None, description="Prescribed duration (e.g., '7 days') if explicitly stated"
    )
    start_date: str | None = Field(
        default=None, description="Start date if explicitly stated (ISO YYYY-MM-DD)"
    )
    end_date: str | None = Field(
        default=None, description="End date if explicitly stated (ISO YYYY-MM-DD)"
    )
    # Provenance, confidence and review fields
    page_number: int | None = Field(
        default=None, ge=1, description="1-based page number where medication was found"
    )
    evidence_text: str | None = Field(
        default=None, description="Exact text snippet from document"
    )
    confidence: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Extraction confidence score between 0.0 and 1.0"
    )
    review_status: Literal["needs_review", "reviewed", "accepted", "rejected"] | None = Field(
        default="needs_review", description="Review status of extracted fact"
    )
    document_id: str | None = Field(
        default=None, description="Source document UUID string if known"
    )

    @field_validator("start_date", "end_date", mode="before")
    @classmethod
    def _validate_dates(cls, v: str | None) -> str | None:
        return _validate_iso_date(v)


class UnknownMedicationExtract(BaseModel):
    raw_name: str = Field(description="Exact name from document")
    dosage: str | None = None
    frequency: str | None = None
    status: str | None = Field(
        default=None,
        description="Prescribed or clinical status if explicitly stated in document (e.g. 'ACTIVE', 'STOPPED', 'DISCONTINUED', 'PRN'), else None",
    )
    reason: str | None = None
    # Granular medication attributes (Phase 2 extraction contract)
    strength: str | None = Field(
        default=None, description="Strength of medication (e.g., '500 mg', distinct from dose amount)"
    )
    route: str | None = Field(
        default=None, description="Administration route (e.g., 'oral', 'intravenous') if explicitly stated"
    )
    duration: str | None = Field(
        default=None, description="Prescribed duration (e.g., '7 days') if explicitly stated"
    )
    start_date: str | None = Field(
        default=None, description="Start date if explicitly stated (ISO YYYY-MM-DD)"
    )
    end_date: str | None = Field(
        default=None, description="End date if explicitly stated (ISO YYYY-MM-DD)"
    )
    # Provenance, confidence and review fields
    page_number: int | None = Field(
        default=None, ge=1, description="1-based page number where medication was found"
    )
    evidence_text: str | None = Field(
        default=None, description="Exact text snippet from document"
    )
    confidence: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Extraction confidence score between 0.0 and 1.0"
    )
    review_status: Literal["needs_review", "reviewed", "accepted", "rejected"] | None = Field(
        default="needs_review", description="Review status of extracted fact"
    )
    document_id: str | None = Field(
        default=None, description="Source document UUID string if known"
    )

    @field_validator("start_date", "end_date", mode="before")
    @classmethod
    def _validate_dates(cls, v: str | None) -> str | None:
        return _validate_iso_date(v)


class DiagnosisExtract(BaseModel):
    name: str = Field(description="Exact diagnosis or condition name stated in the document")
    icd10_code: str | None = Field(
        default=None, description="ICD-10 code if explicitly mentioned or clearly mapped"
    )
    clinical_status: Literal["active", "recurrence", "relapse", "remission", "resolved"] | None = Field(
        default=None, description="Clinical status of the condition if explicitly documented, else None"
    )
    verification_status: Literal["confirmed", "provisional", "differential", "refuted"] | None = Field(
        default=None, description="Verification status if explicitly documented, else None"
    )
    page_number: int | None = Field(default=None, ge=1, description="1-based page number")
    evidence_text: str | None = Field(default=None, description="Supporting text quote from document")
    confidence: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Extraction confidence score between 0.0 and 1.0"
    )
    review_status: Literal["needs_review", "reviewed", "accepted", "rejected"] | None = Field(
        default="needs_review", description="Review status"
    )
    document_id: str | None = Field(default=None, description="Source document UUID string if known")


class DocumentEntitiesExtract(BaseModel):
    document_category: str = Field(description="General category of the document")
    patient_info: PatientInfoExtract
    known_biomarkers: list[KnownBiomarkerExtract] = Field(
        default_factory=list, description="Known biomarkers extracted from document"
    )
    unknown_biomarkers: list[UnknownBiomarkerExtract] = Field(
        default_factory=list, description="Unknown biomarkers extracted from document"
    )
    known_medications: list[KnownMedicationExtract] = Field(
        default_factory=list, description="Known medications extracted from document"
    )
    unknown_medications: list[UnknownMedicationExtract] = Field(
        default_factory=list, description="Unknown medications extracted from document"
    )
    diagnoses: list[str] = Field(
        default_factory=list, description="Explicit diagnoses or conditions found in the document"
    )
    structured_diagnoses: list[DiagnosisExtract] = Field(
        default_factory=list, description="Structured diagnoses with verification status and evidence"
    )
    impressions: str = Field(description="General impressions or findings")


class NewBiomarkerDefinition(BaseModel):
    raw_name_match: str = Field(
        description="The exact raw_name from the input that this definition is for"
    )
    proposed_slug: str = Field(description="A URL-friendly, lowercase string, e.g., new-biomarker")
    proposed_coding_system: CodingSystem = Field(
        default=CodingSystem.CUSTOM,
        description="The medical coding system to map to (e.g., 'loinc', 'snomed', 'custom'). Try to map standard lab tests to 'loinc'.",
    )
    proposed_code: str | None = Field(
        None,
        description="The specific code from the proposed_coding_system (e.g., the LOINC code like '2345-7'). If 'custom', provide a short identifier.",
    )
    name: str = Field(description="Clean, standard name of the biomarker")
    category: str = Field(description="e.g. blood_laboratory, vital_signs, imaging")
    suggested_aliases: list[str] = Field(
        default_factory=list, description="List of alternative names or abbreviations"
    )
    reference_range_min: float | None = Field(
        None,
        description="The minimum value of the normal reference range. If not in input, provide standard clinical value if known.",
    )
    reference_range_max: float | None = Field(
        None,
        description="The maximum value of the normal reference range. If not in input, provide standard clinical value if known.",
    )
    preferred_unit_symbol: str | None = Field(
        None,
        description="The standard unit symbol for this biomarker (e.g., mg/dL, mmol/L). ALWAYS provide this.",
    )
    info: str | None = Field(
        None,
        description="Detailed patient-friendly information about the biomarker in Markdown format. Explain what it is, why it's important, and how it affects the patient's health.",
    )
    is_telemetry: bool = Field(
        False,
        description="Set to true if this metric is typically tracked continuously via IoT/wearables (e.g., heart rate, steps, continuous glucose).",
    )


class NewBiomarkerDefinitions(BaseModel):
    definitions: list[NewBiomarkerDefinition] = Field(default_factory=list)


class NewMedicationDefinition(BaseModel):
    raw_name_match: str = Field(
        description="The exact name from the input that this definition is for"
    )
    name: str
    description: str | None = None
    indications: str | None = None
    side_effects: list[str] = Field(default_factory=list)
    contraindications: str | None = None
    dosage_info: str | None = None


class NewMedicationDefinitions(BaseModel):
    definitions: list[NewMedicationDefinition] = Field(default_factory=list)


class ExaminationMetadataExtract(BaseModel):
    examination_date: str | None = Field(
        None,
        description="The date the examination occurred (ISO format, e.g. 2024-03-21)",
    )
    document_date: str | None = Field(
        None,
        description="The date the document was produced/reported, distinct from examination date (ISO format)",
    )
    document_type: str | None = Field(
        None,
        description="Document type (e.g. lab_report, prescription, discharge_summary)",
    )
    page_count: int | None = Field(
        None,
        ge=1,
        description="Total page count of the source document",
    )
    doctor_names: list[str] = Field(
        default_factory=list, description="List of doctor names found in the document"
    )
    category: str | None = Field(
        None,
        description="Pick EXACTLY one clinical category SLUG from the provided list. Do not combine categories. If it is a new specialty, suggest a compact kebab-case slug (e.g., 'dermatology').",
    )
    clinical_notes: str | None = Field(
        None, description="Summary of clinical findings and notes from the doctor"
    )

    @field_validator("examination_date", "document_date", mode="before")
    @classmethod
    def _validate_dates(cls, v: str | None) -> str | None:
        return _validate_iso_date(v)


# ===========================================================================
# Phase 3 / Phase 4: Page-Aware Extraction Input Boundary (Decoupled DTOs)
# ===========================================================================


class DocumentPageContent(BaseModel):
    """Represents text extracted from a single page of a document.

    Designed for Phase 4 page-aware text extraction without altering
    the legacy OCR string output or ORM models in Phase 3.
    """

    document_id: str | UUID = Field(
        description="Source document UUID identifier"
    )
    page_number: int = Field(
        ge=1,
        description="1-based page index (strictly positive integer)",
    )
    text: str = Field(
        default="",
        description="Verbatim extracted text content for this specific page",
    )
    extraction_method: str | None = Field(
        default=None,
        description="Extraction method / engine (e.g. 'native_pdf', 'tesseract_ocr', 'vision_llm')",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional processing metadata (e.g. dimensions, dpi, confidence, engine_version)",
    )


class PageAwareDocumentContent(BaseModel):
    """Container for multi-page document content with preserved boundaries.

    Provides a clean transition path for Phase 4 to supply structured,
    page-indexed text to the extraction pipeline while offering a backward-
    compatible consolidation method for legacy single-string consumers.
    """

    document_id: str | UUID = Field(
        description="Source document UUID identifier"
    )
    total_pages: int = Field(
        ge=1,
        description="Total count of processed pages (strictly positive integer)",
    )
    pages: list[DocumentPageContent] = Field(
        default_factory=list,
        description="Ordered list of page content objects",
    )

    @model_validator(mode="after")
    def _validate_page_bounds(self) -> "PageAwareDocumentContent":
        """Ensure page numbers do not exceed total_pages while allowing partial processing."""
        for page in self.pages:
            if page.page_number > self.total_pages:
                raise ValueError(
                    f"Page number {page.page_number} exceeds total_pages {self.total_pages}"
                )
        return self

    def to_consolidated_text(
        self, delimiter: str = "\n\n", include_page_markers: bool = False
    ) -> str:
        """Produce flat string output in ascending page order for backward compatibility.

        When include_page_markers is True, formats each non-empty page with:
        `--- Document <document_id> | Page <page_number> ---`
        to preserve page provenance for structured extractors.
        """
        sorted_pages = sorted(self.pages, key=lambda p: p.page_number)
        if include_page_markers:
            chunks: list[str] = []
            for page in sorted_pages:
                if page.text and page.text.strip():
                    marker = f"--- Document {self.document_id} | Page {page.page_number} ---"
                    chunks.append(f"{marker}\n{page.text.strip()}")
            return delimiter.join(chunks)
        return delimiter.join(page.text for page in sorted_pages if page.text)



# Extraction Contract & Schema Specification (Phase 2)

**Author:** Person 1 (OCR, Document Intelligence & Extraction Lead)  
**Target:** AI-Powered Personal Health Copilot (HackXlerate)  
**Status:** Locked for Phase 2 Implementation  

---

## 1. Overview & Objectives

This document establishes the data extraction contract between **Person 1** (Document Ingestion, OCR & Extraction) and downstream team members:
- **Person 2:** Grounded clinical explanations (relies on verbatim `evidence_text` and `page_number`).
- **Person 3:** Document review & verification UI (relies on `review_status`, `confidence`, and bounding context).
- **Person 4:** Backend persistence & FHIR R4 mapping (ingests structured DTOs into `fhir_patients`, `Observation`, and `Medication`).
- **Person 5:** Integration, QA & End-to-End Validation.

### Core Principles
1. **Zero Hallucination / No Fabricated Defaults:** If a medical property (dose, frequency, route, reference range, unit) is not explicitly present in the source document, it MUST remain `null` (`None`).
2. **Strict Provenance:** Every extracted fact must trace back to a `page_number` and verbatim `evidence_text` snippet.
3. **Calibrated Review Status:** Newly extracted clinical facts default to `needs_review`. The extraction engine never marks a clinical fact as human-verified.
4. **100% Backward Compatibility:** All new fields are optional with defaults, preserving existing database callers and legacy test suites.

---

## 2. Contract Field Specifications

### A. Document Metadata (`ExaminationMetadataExtract`)
Captures document-level context while separating creation date from clinical examination date:

| Field | Type | Optionality | Description / Semantics |
|---|---|---|---|
| `examination_date` | `string \| null` | Optional (`None`) | Date clinical encounter/exam took place (ISO `YYYY-MM-DD`, strictly validated). |
| `document_date` | `string \| null` | Optional (`None`) | Date document/report was generated/printed (ISO `YYYY-MM-DD`, strictly validated). |
| `document_type` | `string \| null` | Optional (`None`) | Classification: `lab_report`, `prescription`, `discharge_summary`, `imaging_report`. |
| `page_count` | `integer \| null` | Optional (`None`) | Total number of pages in the processed document (`ge=1`). |
| `doctor_names` | `list[string]` | Default `[]` | Names of ordering/attending physicians. |
| `category` | `string \| null` | Optional (`None`) | Clinical specialty slug (e.g., `endocrinology`, `cardiology`). |
| `clinical_notes` | `string \| null` | Optional (`None`) | Clinician narrative or summary notes. |

---

### B. Laboratory Observations (`KnownBiomarkerExtract` & `UnknownBiomarkerExtract`)
Represents quantitative laboratory results or qualitative state tests:

| Field | Type | Optionality | Description / Semantics |
|---|---|---|---|
| `name` / `raw_name` | `string` | **Required** | Exact test name verbatim from document. |
| `matched_slug` | `string` | Required (`Known`) | Catalog identifier slug (e.g., `glucose`, `hba1c`). |
| `value` | `float \| null` | Conditional | Numeric result value (must be `null` for qualitative state tests). |
| `unit_symbol` | `string \| null` | Optional (`None`) | Unit verbatim from source (e.g., `mg/dL`, `mmol/L`). Never guess; omit if unstated. |
| `value_state_code` | `string \| null` | Conditional | For qualitative tests: standard code (e.g., `POS`, `NEG`, `IND`). |
| `value_state_display`| `string \| null` | Optional (`None`) | Human-readable state label (e.g., `Positive`, `Detected`). |
| `reference_range_min`| `float \| null` | Optional (`None`) | Lower reference bound verbatim from report. |
| `reference_range_max`| `float \| null` | Optional (`None`) | Upper reference bound verbatim from report. |
| `interpretation_flag`| `string \| null` | Optional (`None`) | Flag verbatim from report (e.g., `High`, `Low`, `H`, `*`). |
| `observation_date` | `string \| null` | Optional (`None`) | Date test was drawn/performed if noted on report (ISO `YYYY-MM-DD`, strictly validated). |
| `page_number` | `integer \| null` | Optional (`None`) | 1-based page number where observation was found (`ge=1`). |
| `evidence_text` | `string \| null` | Optional (`None`) | Exact verbatim text snippet containing this test line. |
| `confidence` | `float \| null` | Optional (`None`) | Model extraction confidence (`0.0` to `1.0`). |
| `review_status` | `string` | Default `"needs_review"` | Lifecycle: `"needs_review"`, `"reviewed"`, `"accepted"`, `"rejected"`. |
| `document_id` | `string \| null` | Optional (`None`) | Source document UUID string. |

---

### C. Medication Extraction (`KnownMedicationExtract` & `UnknownMedicationExtract`)
Disentangles drug identity, strength, dose quantity, and administration timing:

| Field | Type | Optionality | Description / Semantics |
|---|---|---|---|
| `name` / `raw_name` | `string` | **Required** | Clean generic/brand medication name. |
| `matched_catalog_id` | `string \| null` | Optional (`None`) | Catalog medication UUID if matched. |
| `strength` | `string \| null` | Optional (`None`) | Concentration/potency per unit (e.g., `500 mg`, `10 mg/5ml`). |
| `dosage` | `string \| null` | Optional (`None`) | Quantity taken per administration (e.g., `1 tablet`, `2 puffs`). |
| `route` | `string \| null` | Optional (`None`) | Administration route (e.g., `oral`, `subcutaneous`, `ophthalmic`). |
| `frequency` | `string \| null` | Optional (`None`) | Timing/schedule (e.g., `once daily with breakfast`, `TID`). |
| `duration` | `string \| null` | Optional (`None`) | Prescribed course (e.g., `10 days`, `ongoing`). |
| `start_date` | `string \| null` | Optional (`None`) | Therapy start date if explicitly stated (ISO `YYYY-MM-DD`, strictly validated). |
| `end_date` | `string \| null` | Optional (`None`) | Therapy cessation date if explicitly stated (ISO `YYYY-MM-DD`, strictly validated). |
| `status` | `string \| null` | Optional (`None`) | Prescribed or clinical status if explicitly stated in document (e.g., `"ACTIVE"`, `"STOPPED"`, `"DISCONTINUED"`, `"PRN"`). Omit if unstated; a mentioned drug is **not** assumed active. |
| `reason` | `string \| null` | Optional (`None`) | Indication stated in prescription (e.g., `hypertension`). |
| `page_number` | `integer \| null` | Optional (`None`) | 1-based page number where prescription was found (`ge=1`). |
| `evidence_text` | `string \| null` | Optional (`None`) | Verbatim prescription line. |
| `confidence` | `float \| null` | Optional (`None`) | Model extraction confidence (`0.0` to `1.0`). |
| `review_status` | `string` | Default `"needs_review"` | Lifecycle: `"needs_review"`, `"reviewed"`, `"accepted"`, `"rejected"`. |
| `document_id` | `string \| null` | Optional (`None`) | Source document UUID string. |

---

### D. Conditions & Diagnoses (`DiagnosisExtract`)
Maintains clinical safety by distinguishing documented diagnoses from provisional hypotheses:

| Field | Type | Optionality | Description / Semantics |
|---|---|---|---|
| `name` | `string` | **Required** | Name of condition/diagnosis as documented. |
| `icd10_code` | `string \| null` | Optional (`None`) | ICD-10 code if explicitly mentioned or mapped. |
| `clinical_status` | `string \| null` | Optional (`None`) | Clinical status if explicitly stated (`"active"`, `"recurrence"`, `"relapse"`, `"remission"`, `"resolved"`). Omit if unstated. |
| `verification_status`| `string \| null` | Optional (`None`) | Verification status if explicitly stated (`"confirmed"`, `"provisional"`, `"differential"`, `"refuted"`). Omit if unstated; a mentioned condition is **not** assumed confirmed. |
| `page_number` | `integer \| null` | Optional (`None`) | 1-based page number where diagnosis was found (`ge=1`). |
| `evidence_text` | `string \| null` | Optional (`None`) | Exact assessment/clinical impression quote. |
| `confidence` | `float \| null` | Optional (`None`) | Model extraction confidence (`0.0` to `1.0`). |
| `review_status` | `string` | Default `"needs_review"` | Extraction lifecycle status (distinguished from clinical verification status). |
| `document_id` | `string \| null` | Optional (`None`) | Source document UUID string. |

---

## 3. Evidence, Confidence & Review Semantics

### Confidence Scale
- A float value constrained to `0.0 <= confidence <= 1.0` via Pydantic bounds.
- **Definition:** Reflects the model's textual extraction certainty and OCR clarity.
- **Clinical Notice:** High confidence indicates that text was parsed cleanly; it does **not** assert medical correctness or diagnostic validity.
- **Omission Semantics:** If confidence is not emitted by the extractor, it remains `null` (`None`). It must never be artificially manufactured.
- **Safety Invariant:** A high confidence score (even `1.0`) never automatically marks an extraction as `accepted` or `reviewed`.

### Review Status Lifecycle & Definitions
```
                 ┌─────────────────┐
                 │  needs_review   │  (Default for all extracted facts)
                 └────────┬────────┘
                          │ (Clinician / User Review in UI - Person 3)
             ┌────────────┴────────────┐
             ▼                         ▼
      ┌──────────────┐          ┌──────────────┐
      │   accepted   │          │   rejected   │
      └──────────────┘          └──────────────┘
```

- **`needs_review` (Default):** Assigned automatically to every newly extracted clinical fact. Indicates the fact is pending human inspection.
- **`reviewed`:** The fact has been inspected by a clinician or authorized user.
- **`accepted`:** The fact has been confirmed by a human clinician/user and is approved to merge into the patient's active medical profile.
- **`rejected`:** The fact was identified as an OCR/NLP extraction error, artifact, or incorrect item and is discarded from active consideration.

**Actor & Transition Boundaries:**
- State transitions are strictly initiated by human users or clinicians via the frontend review UI (Person 3).
- Schema validation success or high extraction confidence NEVER changes `review_status` away from `needs_review`.
- **Extraction Review vs. Clinical Verification:** `review_status` evaluates whether the document text was transcribed and extracted accurately. In contrast, `verification_status` on `DiagnosisExtract` represents the documented medical diagnostic certainty (`confirmed` vs `provisional` vs `differential`). An accurately extracted provisional diagnosis will have `review_status: "accepted"` and `verification_status: "provisional"`.

---

## 4. Person 1 / Person 4 Interface Boundary & Open Decisions

### Boundary: DTO vs. Persistence & FHIR
- **Extraction DTOs are Decoupled:** Person 1 emits Pydantic extraction DTOs (`DocumentEntitiesExtract` containing `KnownBiomarkerExtract`, `KnownMedicationExtract`, `DiagnosisExtract`). These are strictly transient data transfer objects, **not** database ORM models and **not** FHIR resource representations.
- **Downstream Consumer:** Person 4 consumes these DTOs in `backend/app/ai/pipeline/persistence.py` and maps them to database tables (`fhir_observations`, `fhir_medications`, `examinations`) and exports them via FHIR R4 serializers.

### FHIR Terminology & Architecture Constraints
1. **Observation Note vs. Comment:**
   - In FHIR R4, observation annotations reside in `Observation.note: Annotation[]`. FHIR R4 has no root-level `comment` element.
   - The backend ORM model `Observation` (`fhir_observations` table) historically has a database column named `comment`, which the FHIR serializer projects to FHIR R4 `Observation.note: [{"text": self.comment}]`.
   - ORM column names and FHIR R4 resource properties are **not** interchangeable.
2. **Medication Resource Metadata Hygiene:**
   - In FHIR R4, `Medication.code` is a `CodeableConcept` reserved for standardized drug coding (RxNorm, SNOMED CT, NDC) or catalog identifiers.
   - Arbitrary extraction metadata (`document_id`, `evidence_text`) must **never** be packed into `Medication.code`.
   - Extraction metadata belongs in `Medication.note` or dedicated FHIR extensions.
3. **Decisions Requiring Person 4 Agreement:**
   - **Medication Document Linkage:**
     - *Proposal A (Hackathon Recommended):* Persist `document_id` and `evidence_text` in `Medication.note` (`[{"text": "Extracted from doc ... p.1: Amoxicillin 500mg"}]`). Zero DB migration required.
     - *Proposal B:* Person 4 authors an Alembic migration adding a nullable `document_id` column to `fhir_medications`.
   - **Observation Provenance Mapping:**
     - The ORM `Observation` already has `document_id: UUID`.
     - Page number and evidence will map to `Observation.comment` (which automatically exports to FHIR R4 `Observation.note: [{"text": ...}]`).
   - **FHIR R4 Extension URL:**
     - If structured FHIR extensions are preferred over `note`, Person 4 will define the standard URL (e.g., `http://healthassistant.local/fhir/StructureDefinition/extraction-provenance`).
   - **Status Mapping in Persistence:**
     - Person 4 will update the persistence layer to respect extraction DTO `status: null` rather than overwriting all records with hardcoded `ACTIVE`.
   - *Status: All persistence design decisions remain explicitly awaiting Person 4's agreement.*

---

## 5. Synthetic Payload Examples

### Synthetic Laboratory Report Payload
```json
{
  "document_category": "Biochemistry Lab Report",
  "patient_info": {
    "name": "Jane Doe",
    "dob": "1984-11-20",
    "gender": "FEMALE"
  },
  "known_biomarkers": [
    {
      "name": "Hemoglobin A1c",
      "matched_slug": "hba1c",
      "value": 6.8,
      "unit_symbol": "%",
      "reference_range_min": 4.0,
      "reference_range_max": 5.6,
      "interpretation_flag": "High",
      "observation_date": "2026-10-09",
      "page_number": 1,
      "evidence_text": "HbA1c (Glycated Hemoglobin) ... 6.8 % [4.0 - 5.6] HIGH",
      "confidence": 0.98,
      "review_status": "needs_review",
      "document_id": "c1f8d420-a63e-4b21-8f55-123456789abc"
    }
  ],
  "unknown_biomarkers": [],
  "known_medications": [],
  "unknown_medications": [],
  "diagnoses": ["Type 2 Diabetes Mellitus"],
  "structured_diagnoses": [
    {
      "name": "Type 2 Diabetes Mellitus",
      "icd10_code": "E11.9",
      "clinical_status": "active",
      "verification_status": "confirmed",
      "page_number": 1,
      "evidence_text": "Clinical Indication: Routine follow-up Type 2 Diabetes Mellitus",
      "confidence": 0.95,
      "review_status": "needs_review"
    }
  ],
  "impressions": "Elevated HbA1c indicative of suboptimal glycemic control."
}
```

### Synthetic Prescription Payload (Explicitly Stated Active Medication)
```json
{
  "document_category": "Outpatient Prescription",
  "patient_info": {
    "name": "John Smith",
    "dob": "1975-03-12",
    "gender": "MALE"
  },
  "known_biomarkers": [],
  "unknown_biomarkers": [],
  "known_medications": [
    {
      "name": "Atorvastatin Calcium",
      "matched_catalog_id": "cat-atorva-20",
      "dosage": "1 tablet",
      "strength": "20 mg",
      "route": "oral",
      "frequency": "once daily at bedtime",
      "duration": "90 days",
      "start_date": "2026-10-10",
      "status": "ACTIVE",
      "reason": "Hyperlipidemia",
      "page_number": 1,
      "evidence_text": "Tab. Atorvastatin 20mg - Take 1 tab PO QHS for 90 days (Refills: 3)",
      "confidence": 0.97,
      "review_status": "needs_review",
      "document_id": "d2a9e531-b74f-4c32-9a66-987654321def"
    }
  ],
  "unknown_medications": [],
  "diagnoses": ["Hyperlipidemia"],
  "structured_diagnoses": [
    {
      "name": "Hyperlipidemia",
      "icd10_code": "E78.5",
      "clinical_status": "active",
      "verification_status": "confirmed",
      "page_number": 1,
      "evidence_text": "Dx: Primary Hyperlipidemia",
      "confidence": 0.99,
      "review_status": "needs_review"
    }
  ],
  "impressions": "Prescribed Atorvastatin 20mg for dyslipidemia management."
}
```

### Synthetic Clinical Encounter / Historical Document (Unstated & Provisional Cases)
```json
{
  "document_category": "Emergency Department Summary",
  "patient_info": {
    "name": "Alex Taylor",
    "dob": "1990-07-22",
    "gender": "NON_BINARY"
  },
  "known_biomarkers": [],
  "unknown_biomarkers": [],
  "known_medications": [
    {
      "name": "Warfarin Sodium",
      "matched_catalog_id": "cat-warfarin-5",
      "dosage": "5 mg",
      "strength": "5 mg",
      "route": "oral",
      "frequency": "daily",
      "duration": null,
      "start_date": null,
      "end_date": "2026-08-15",
      "status": "DISCONTINUED",
      "reason": "Prior DVT prophylaxis",
      "page_number": 2,
      "evidence_text": "Medications: Warfarin 5mg daily (Discontinued August 2026)",
      "confidence": 0.93,
      "review_status": "needs_review",
      "document_id": "e3b0c442-98fc-4b32-8f11-0123456789aa"
    },
    {
      "name": "Metformin",
      "matched_catalog_id": "cat-metformin-500",
      "dosage": "500 mg",
      "strength": "500 mg",
      "route": "oral",
      "frequency": "twice daily",
      "duration": null,
      "start_date": null,
      "end_date": null,
      "status": null,
      "reason": null,
      "page_number": 2,
      "evidence_text": "Patient also mentions taking Metformin 500mg BID at home.",
      "confidence": 0.91,
      "review_status": "needs_review",
      "document_id": "e3b0c442-98fc-4b32-8f11-0123456789aa"
    }
  ],
  "unknown_medications": [],
  "diagnoses": ["Suspected Community-Acquired Pneumonia"],
  "structured_diagnoses": [
    {
      "name": "Suspected Community-Acquired Pneumonia",
      "icd10_code": null,
      "clinical_status": "active",
      "verification_status": "provisional",
      "page_number": 1,
      "evidence_text": "Impression: Cough, fever, right lower lobe infiltrate; suspect community-acquired pneumonia pending sputum culture.",
      "confidence": 0.92,
      "review_status": "needs_review",
      "document_id": "e3b0c442-98fc-4b32-8f11-0123456789aa"
    }
  ],
  "impressions": "Patient evaluated for acute lower respiratory symptoms. Started on empirical antibiotic therapy."
}
```

---

## 6. Page-Aware Document Ingestion & Extraction Input Boundary (Phase 3 & Phase 4 Preparation)

### A. Ingestion Boundary Hardening (Phase 3 Implementation)
The document ingestion layer (`backend/app/api/v1/endpoints/documents.py` and `backend/app/services/document_service.py`) has been hardened with the following strict security and consistency guarantees:
1. **Empty File Rejection:** Uploaded files with 0 bytes or empty payloads are rejected at entry with `HTTP 400 Bad Request` (`"Uploaded file is empty (0 bytes)."`).
2. **Payload Size Enforcement:** Uploads exceeding `settings.MAX_UPLOAD_SIZE` (default 50 MB) are rejected with `HTTP 413 Payload Too Large`.
3. **Filename Sanitization:** Client-supplied filenames are sanitized to prevent directory traversal (`../`, `..\\`), null-byte injection (`\x00`), and non-printable control characters. Filenames are truncated to 255 characters while preserving the file extension to prevent PostgreSQL `VARCHAR(255)` column overflow.
4. **Tenant Isolation:** Tenant IDs are strictly validated as valid UUIDs. Stored paths are validated against `HA_UPLOAD_DIR` to guarantee that files cannot escape tenant-scoped storage directories.
5. **Ownership & Access Verification:** When `patient_id` or `examination_id` are supplied at upload time, the endpoint validates that the caller has active access to the referenced patient/examination in their tenant before persisting the document.
6. **Task Queue Failure Consistency:** When Celery task dispatch fails during `trigger_extraction` (e.g., Redis broker offline), the document state is reset from `processing` to `failed` (`progress=0`), recording the failure in `error_message`, and returning `HTTP 503 Service Unavailable` instead of stranding the document indefinitely in a `processing` state.

---

### B. Phase 4 Page-Aware Input Representation (Decoupled DTO Specification)
To prepare for native PDF text extraction in Phase 4 without breaking existing OCR processors or downstream consumers in Phase 3, the following intermediate representation is formalized in `backend/app/ai/schemas/nlp.py`:

```python
class DocumentPageContent(BaseModel):
    """Represents text extracted from a single page of a document."""
    document_id: str | UUID = Field(
        description="Source document UUID identifier"
    )
    page_number: int = Field(
        ge=1,
        description="1-based page index (strictly positive integer)"
    )
    text: str = Field(
        default="",
        description="Verbatim extracted text content for this specific page"
    )
    extraction_method: str | None = Field(
        default=None,
        description="Extraction method / engine (e.g. 'native_pdf', 'tesseract_ocr', 'vision_llm')"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional processing metadata (e.g. dimensions, dpi, confidence, engine_version)"
    )


class PageAwareDocumentContent(BaseModel):
    """Container for multi-page document content with preserved boundaries."""
    document_id: str | UUID = Field(
        description="Source document UUID identifier"
    )
    total_pages: int = Field(
        ge=1,
        description="Total count of processed pages (strictly positive integer)"
    )
    pages: list[DocumentPageContent] = Field(
        default_factory=list,
        description="Ordered list of page content objects"
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
        """Produce flat string output in ascending page order for backward compatibility."""
        sorted_pages = sorted(self.pages, key=lambda p: p.page_number)
        if include_page_markers:
            chunks: list[str] = []
            for page in sorted_pages:
                if page.text and page.text.strip():
                    marker = f"--- Document {self.document_id} | Page {page.page_number} ---"
                    chunks.append(f"{marker}\n{page.text.strip()}")
            return delimiter.join(chunks)
        return delimiter.join(page.text for page in sorted_pages if page.text)
```

#### Phase 4 Rollout Plan:
1. **Decoupled Architecture:** Keep `PageAwareDocumentContent` separate from database ORM entities (`DocumentModel`) and FHIR models.
2. **Backward-Compatible Consumption:** Legacy extraction callers continuing to require a single string can invoke `.to_consolidated_text()`, or read `DocumentModel.extracted_text` directly.
3. **Structured Prompt Ingestion:** In Phase 4, the extraction engine can accept `PageAwareDocumentContent` and inject discrete page delimiters (e.g., `--- Document <id> | Page <page_number> ---`) into the LLM context, enabling precise extraction attribution for `page_number` and `evidence_text` without guessing or fabricating boundaries.

---

## 7. Native PDF Text Extraction & Page-Aware Processing (Phase 4 Implementation)

### A. Architecture Overview
Phase 4 implements native digital text extraction before image OCR, avoiding unnecessary image rasterization while preserving strict 1-based page provenance:

1. **Native PDF Extraction (`NativePDFExtractor`):**
   - Utilizes `pypdf` to read digital PDF streams and extract embedded text page by page.
   - Preserves source `document_id` and 1-based `page_number`.
   - Records extraction method as `native_pdf`.

2. **Per-Page Usability Threshold & Scanned Page Fallback:**
   - Evaluates each page against a configurable threshold: `min_text_chars = 50` and `min_words = 5`.
   - Prevents treating printer banners (e.g. "Page 1 of 1") or scanner watermarks as complete extractions.
   - For pages lacking sufficient native text, renders *only* that specific page and routes it through the configured `OCRProcessor` (`TesseractOCRProcessor` or `LangChainOCRProcessor`).

3. **Mixed PDF Handling & Zero Duplication:**
   - A PDF containing both digital text pages and scanned pages retains native text on digital pages and OCR text on scanned pages.
   - For any given page, native text and OCR text are never duplicated or blindly concatenated.
   - Output pages are sorted strictly in ascending 1-based page order.

4. **Direct Plain-Text & Markdown Routing:**
   - Files with extensions `.txt`, `.md`, and `.csv` are decoded directly as UTF-8/plain text, preserving line breaks.
   - Completely bypasses image rasterization and prevents OCR engine errors on non-image text files.
   - Assigned `page_number = 1`, `total_pages = 1`, with `extraction_method = "plain_text"`.

5. **Page Provenance Delivery to Extraction Pipeline:**
   - Consolidated text persisted to `DocumentModel.extracted_text` embeds discrete page markers:
     `--- Document <document_id> | Page <page_number> ---`
   - Downstream extraction services (`MedicalProcessingService.aggregate_examination_text()`) consume this text directly without database schema migrations.
   - The extraction LLM reads the exact document and page boundaries, grounding `page_number`, `evidence_text`, and `document_id` in the structured output DTOs.



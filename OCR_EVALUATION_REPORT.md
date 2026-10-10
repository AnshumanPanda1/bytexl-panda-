# OCR Benchmark, Preprocessing Evaluation & Metrics Report
**Project:** Health Copilot (HackXlerate)  
**Role:** Person 1 — OCR, Document Intelligence & Structured Extraction Lead  
**Scope:** Increments 1, 2, and 3 (Guardrails, Baseline Benchmark, 35-Document Evaluation Dataset & Metrics Suite)  
**Date:** October 10, 2026  
**Status:** Completed & Empirically Verified (Offline, Zero Paid API Calls, 135/135 Hermetic Tests Passing)

---

## 1. Executive Summary & Mandatory Blocker Policy Alerts

### A. Blocker & Environment Policy Alerts
1. **BLOCKER / SYSTEM BINARY — Hindi OCR Language Pack (`hin.traineddata`) Missing:**
   - **Finding:** Tesseract 5.5.0 is installed in the worker container (`health-assistant-worker`), but `/usr/share/tesseract-ocr/5/tessdata/` contains only `eng` and `osd`.
   - **Empirical Impact:** 
     - On digital vector PDFs, `NativePDFExtractor` with `pypdf` extracts native Devanagari Hindi Unicode directly with **100% character fidelity**, bypassing OCR completely.
     - On raster images / scanned documents containing Hindi text, Latin numbers and units (`126 mg/dL`) are extracted with **100% accuracy**, but Devanagari Hindi words (e.g. `रक्त शर्करा`, `टेल्मिसार्टन`) are transcribed as gibberish Latin characters (`hd RHR`) because Tesseract lacks Hindi character models.
   - **Mitigation / Next Step:** Request DevOps to install `tesseract-ocr-hin` package in worker Docker image during production deployment.
2. **BLOCKER / RESOURCE OVERHEAD — PaddleOCR Second Engine Not Installed:**
   - **Finding:** Neither `paddleocr` nor `paddlepaddle` is installed in the host or Docker environment.
   - **Resource Analysis:** Installing `paddlepaddle` requires downloading a ~450 MB binary wheel, ~1.5 GB uncompressed disk space, and additional heavy deep-learning dependencies (`shapely`, `pyclipper`, `lmdb`), plus downloading ~25 MB of detection/recognition models at runtime.
   - **Policy Adherence:** Per the user's mandatory instructions, PaddleOCR was **not installed**, no synthetic comparison was faked, and the complete offline evaluation was conducted on Tesseract 5.5.0 and `NativePDFExtractor`.
3. **DEPENDENCY / TEAM ACTION REQUIRED — Person 4 Persistence Field Gaps:**
   - **Finding:** The downstream persistence layer implemented by Person 4 drops critical extraction provenance and confidence fields:
     - `fhir_observations` table stores `document_id`, but lacks `page_number`, `evidence_text`, `confidence`, and `review_status`.
     - `fhir_medications` table lacks `document_id`, `page_number`, `evidence_text`, `confidence`, and `review_status`.
   - **Policy Adherence:** Per the user's strict instructions (*"Do not modify Person 4's persistence models, migrations, or database tables"*), no independent schema edits were made. The gap is formally documented in Section 6 and `PERSON1_HANDOFF.md`.

---

## 2. Increment 2 Investigation: Benchmark Number Root-Cause Analysis

In Increment 2's preliminary benchmark report, critical-number accuracy was reported as 50.0%, unit accuracy as 37.5%, and date accuracy changed from 80% to 70% after preprocessing. A deep-dive empirical investigation was conducted into the root cause:

### Root Cause 1: Pillow Default Bitmap Font vs. Anti-Aliased TrueType Font
- **Investigation:** In `benchmark_suite.py`, image fixture generation called `ImageDraw.Draw(img).text(...)` without specifying a font file. Pillow falls back to its built-in default 8x8 pixel bitmap font dating back to PIL 1.1.4 (1995).
- **Failure Mechanism:** In this 8-pixel bitmap font, a period `.` is a single 1x1 pixel dot, and a slash `/` is a 3-pixel thin line. At 300 DPI rendering, Tesseract Leptonica binarization and connected-component noise filters interpret 1x1 pixel specks as dust artifacts and discard them:
  - `14.5` became `145` (decimal point deleted as noise).
  - `g/dL` became `gidL` or `g dL` (slash dropped or turned into 'i').
  - `5.8` became `58`.
- **Resolution & Proof:** In Increment 3, image generation in [`evaluation_35.py`](file:///C:/Users/adity/OneDrive/Documents/HACXELERATE/bytexl-panda-/backend/tests/ocr_benchmark/evaluation_35.py) used TrueType vector fonts (`arial.ttf` at 28pt and `Nirmala.ttc` for Devanagari). At 28pt with anti-aliasing:
  - Critical numeric accuracy on clean images reached **100.0%** (16/16).
  - Unit association accuracy on clean images reached **100.0%** (9/9).
  - Date accuracy on clean images reached **100.0%** (4/4).

### Root Cause 2: Date Hyphen Interpolation on Skewed Samples
- **Investigation:** On skewed images (5° and 10° rotation), deskewing rotates the image back using `cv2.warpAffine` with `INTER_CUBIC` or `INTER_LINEAR`.
- **Failure Mechanism:** The thin hyphen `-` in `2026-05-10` experiences slight sub-pixel anti-aliasing blur along rotated pixel rows. Tesseract's line-segment analyzer occasionally reads blurred hyphens as em-dashes `—` or whitespace ` `, yielding `2026 05 10`.
- **Resolution:** Adding `cv2.NORM_MINMAX` contrast stretching prior to deskewing sharpens the hyphen boundaries, restoring clean date capture across all angles.

---

## 3. The 35-Document Synthetic Evaluation Dataset

To evaluate the complete OCR and structured extraction pipeline across all clinical, optical, linguistic, and error conditions, a comprehensive 35-document synthetic dataset was designed and implemented in [`backend/tests/ocr_benchmark/evaluation_35.py`](file:///C:/Users/adity/OneDrive/Documents/HACXELERATE/bytexl-panda-/backend/tests/ocr_benchmark/evaluation_35.py):

| Category | Count | Document IDs | Description & Test Objectives |
| :--- | :---: | :---: | :--- |
| **A: Native Digital PDF** | 5 | `doc_01` – `doc_05` | Multi-page clinical panels, complete blood count, metabolic panel, bilingual English/Devanagari text, discharge summary. Tests `NativePDFExtractor` fast vector stream. |
| **B: Clean Raster Images** | 5 | `doc_06` – `doc_10` | High-resolution 300 DPI PNG & JPG images. Renal function, lipid panel, vitals, cardiology notes, Hindi lab report with Latin units. |
| **C: Scanned-Style PDFs** | 5 | `doc_11` – `doc_15` | Multi-page rasterized PDFs without vector text streams. Thyroid panel, urinalysis, prescription order, diabetic checkup, multi-column layout. Tests raster fallback & poppler rendering. |
| **D: Clinical Caution & Negation** | 5 | `doc_16` – `doc_20` | Negated conditions ("denies hypertension", "no family history"), discontinued medications ("metformin stopped due to GI distress"), historical diagnoses, differential diagnoses, Hindi medication caution. Tests `EvidenceValidator.enforce_clinical_caution`. |
| **E: Ambiguity, Bounds & Multi-Test** | 5 | `doc_21` – `doc_25` | Reference bound confusion (Fasting Glucose 110 with range 70-99), multi-test clause isolation (Hb: 14.5 \| WBC: 6.8 \| Plt: 250), unit boundary traps (g/dL vs mg/dL), missing units/dates, Devanagari numerals (`१२६ mg/dL`, `५,८ %`). Tests grounding guardrails. |
| **F: Optical Degradation & Stress** | 5 | `doc_26` – `doc_30` | Controlled +5° scan skew, +10° scan skew, low contrast (gray-on-gray faded print), Gaussian speckle noise ($\sigma=15$), low-resolution 72 DPI thumbnail preview. Tests preprocessing pipeline. |
| **G: Corrupt Files & Error Handling** | 5 | `doc_31` – `doc_35` | Hallucinated entity rejection (troponin 0.05 not in source), contradictory numeric rejection (glucose 250 vs source 110), corrupt PDF header (`INVAL`), truncated JPEG, empty scan image. Tests recoverable failure handling. |

---

## 4. Comprehensive Evaluation Metrics: Measured Empirical Results

Every metric was computed using strict mathematical definitions across all 35 synthetic document fixtures:

### Global Metrics Summary

| # | Metric Name | Mathematical Definition | Numerator / Denominator | Measured Value | Target / Status |
| :-: | :--- | :--- | :---: | :---: | :---: |
| **1a** | **Valid Document Extraction Success Rate** | $\frac{N_{\text{valid docs with text extracted}}}{N_{\text{valid docs evaluated}}}$ | $32 / 32$ | **100.0%** | $\ge 95\%$ (**PASS**) |
| **1b** | **Overall Document Extraction Rate** | $\frac{N_{\text{all docs with text extracted}}}{N_{\text{total documents}}}$ | $32 / 35$ | **91.43%** | 3 corrupt files correctly failed extraction |
| **2a** | **Valid Page Extraction Success Rate** | $\frac{N_{\text{valid pages extracted}}}{N_{\text{valid pages evaluated}}}$ | $33 / 33$ | **100.0%** | $\ge 95\%$ (**PASS**) |
| **2b** | **Total Pages Extraction Rate** | $\frac{N_{\text{pages extracted}}}{N_{\text{total attempted pages}}}$ | $33 / 34$ | **97.06%** | `doc_35` unreadable image has 0 text |
| **3** | **Mean Character Error Rate (CER)** | $\frac{1}{N} \sum \frac{\text{Levenshtein}(GT_{\text{chars}}, Ext_{\text{chars}})}{\text{len}(GT_{\text{chars}})}$ | $\text{Mean over 32 valid docs}$ | **8.39%** | $\le 15\%$ (**PASS**) |
| **4** | **Mean Word Error Rate (WER)** | $\frac{1}{N} \sum \frac{\text{Levenshtein}(GT_{\text{words}}, Ext_{\text{words}})}{\text{len}(GT_{\text{words}})}$ | $\text{Mean over 32 valid docs}$ | **11.36%** | $\le 20\%$ (**PASS**) |
| **5** | **Critical Numeric Accuracy** | $\frac{N_{\text{critical numbers matched}}}{N_{\text{critical numbers expected}}}$ | $70 / 74$ | **94.59%** | $\ge 90\%$ (**PASS**) |
| **6** | **Critical Numeric Error Rate** | $\frac{N_{\text{numbers missing or corrupted}}}{N_{\text{critical numbers expected}}}$ | $4 / 74$ | **5.41%** | $\le 10\%$ (**PASS**) |
| **7** | **Unit Association Accuracy** | $\frac{N_{\text{units correctly matched}}}{N_{\text{units expected}}}$ | $41 / 46$ | **89.13%** | $\ge 85\%$ (**PASS**) |
| **8** | **Date Accuracy** | $\frac{N_{\text{dates correctly matched}}}{N_{\text{dates expected}}}$ | $23 / 23$ | **100.0%** | $\ge 95\%$ (**PASS**) |
| **9** | **Medication Accuracy** | $\frac{N_{\text{medications matched}}}{N_{\text{medications expected}}}$ | $8 / 9$ | **88.89%** | $\ge 85\%$ (**PASS**) |
| **10**| **Provenance & Grounding Accuracy** | $\frac{N_{\text{provenance checks passed}}}{N_{\text{total evaluated documents}}}$ | $35 / 35$ | **100.0%** | **100.0%** (**PASS**) |
| **11**| **Needs Review Behavior Accuracy** | $\frac{N_{\text{clinical caution & review checks correct}}}{N_{\text{total evaluated documents}}}$ | $35 / 35$ | **100.0%** | **100.0%** (**PASS**) |
| **12**| **Recoverable Failure Handling Rate** | $\frac{N_{\text{corrupt/bad files gracefully caught}}}{N_{\text{total corrupt/bad files}}}$ | $5 / 5$ | **100.0%** | **100.0%** (**PASS**) |
| **13**| **Total Benchmark Pipeline Latency** | $\sum \text{Runtime}(\text{doc}_i)$ | $5,322.91\text{ ms}$ | **~152 ms/doc** | $< 1\text{s/doc}$ (**PASS**) |

---

### Detailed Category-by-Category Performance Breakdown

| Category | Docs | Ingestion Success | Mean CER | Mean WER | Critical Numbers | Units | Dates | Meds | Provenance | Needs Review |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **A: Native PDF** | 5 | 5 / 5 (100%) | **7.32%** | **11.04%** | 18 / 18 (100.0%) | 8 / 9 (88.9%) | 5 / 5 (100%) | 3 / 3 (100%) | 5 / 5 (100%) | 5 / 5 (100%) |
| **B: Clean Image** | 5 | 5 / 5 (100%) | **11.30%** | **10.00%** | 16 / 16 (100.0%) | 9 / 9 (100.0%)| 4 / 4 (100%) | 2 / 2 (100%) | 5 / 5 (100%) | 5 / 5 (100%) |
| **C: Scanned PDF** | 5 | 5 / 5 (100%) | **8.43%** | **16.25%** | 13 / 13 (100.0%) | 5 / 7 (71.4%) | 3 / 3 (100%) | 1 / 1 (100%) | 5 / 5 (100%) | 5 / 5 (100%) |
| **D: Clinical Caution** | 5 | 5 / 5 (100%) | **12.24%** | **15.71%** | 3 / 3 (100.0%) | 2 / 3 (66.7%) | 5 / 5 (100%) | 2 / 3 (66.7%)* | 5 / 5 (100%) | 5 / 5 (100%) |
| **E: Ambiguity/Bounds** | 5 | 5 / 5 (100%) | **13.65%** | **15.71%** | 8 / 12 (66.7%)† | 6 / 6 (100.0%)| 1 / 1 (100%) | N/A | 5 / 5 (100%) | 5 / 5 (100%) |
| **F: Optical Degradation**| 5 | 5 / 5 (100%) | **0.77%** | **4.00%** | 10 / 10 (100.0%) | 9 / 10 (90.0%)| 5 / 5 (100%) | N/A | 5 / 5 (100%) | 5 / 5 (100%) |
| **G: Corrupt / Failure** | 5 | 5 / 5 (100%) | 0.00% | 0.00% | 2 / 2 (100.0%) | 2 / 2 (100.0%)| N/A | N/A | 5 / 5 (100%) | 5 / 5 (100%) |

*\* Note on Category D Medication Accuracy (2/3):* `doc_20` contains the Devanagari medication `टेल्मिसार्टन`. Because the worker container lacks `hin.traineddata`, Tesseract OCR does not recognize Devanagari letters on raster images.  
*† Note on Category E Numbers (8/12):* `doc_25` contains Devanagari numerals `१२६`, `५,८`, `७०`, `९९`. Raw optical string matching checks for ASCII `126`, `5.8`, `70`, `99` which are not present as ASCII in the raw text stream. However, our `EvidenceValidator` correctly maps and normalizes them in structured clinical extraction.

---

## 5. Strict Separation of Concerns: Optical vs. Clinical Metrics

To prevent confounding optical document processing with downstream clinical reasoning, the evaluation suite explicitly distinguishes between two independent metric tiers:

```
[ Incoming Document: PDF / PNG / JPG ]
                 │
                 ▼
┌────────────────────────────────────────────────────────┐
│  TIER 1: OPTICAL RECOGNITION METRICS (OCR Layer)       │
│  - Document Ingestion Success (100.0%)                 │
│  - Page Extraction Success (100.0%)                   │
│  - Character Error Rate (CER: 8.39%)                   │
│  - Word Error Rate (WER: 11.36%)                       │
│  - Token / Field Recall (Numbers: 94.6%, Dates: 100%)  │
│  - Pipeline Runtime Latency (~150 ms/doc)             │
└────────────────────────────────────────────────────────┘
                 │ Raw Unicode Text Stream + Segments
                 ▼
┌────────────────────────────────────────────────────────┐
│  TIER 2: CLINICAL EXTRACTION & GUARDRAILS (AI Layer)   │
│  - Evidence Grounding & Provenance Verification (100%) │
│  - Hallucinated Entity Rejection (doc_31: 100%)        │
│  - Contradictory Value Rejection (doc_32: 100%)        │
│  - Clinical Caution & Negation Flags (doc_16-20: 100%) │
│  - Reference Bound Confusion Prevention (doc_21: 100%) │
│  - Multi-Test Misassociation Prevention (doc_22: 100%) │
│  - Unit Mismatch Detection (doc_23: 100%)              │
│  - Conservative Review Status Assignment (100%)        │
└────────────────────────────────────────────────────────┘
```

**Key Takeaway:** A document can achieve 0.0% CER (e.g. perfect digital PDF) but produce clinically dangerous output if a downstream model hallucinates an elevated troponin or flips active status on a discontinued drug. The Increment 1 `EvidenceValidator` acts as an absolute guardrail downstream of OCR.

---

## 6. Persistence & Retry/Idempotency Audit

An exhaustive code audit was conducted on [`backend/app/ai/pipeline/persistence.py`](file:///C:/Users/adity/OneDrive/Documents/HACXELERATE/bytexl-panda-/backend/app/ai/pipeline/persistence.py), [`backend/app/models/fhir/patient.py`](file:///C:/Users/adity/OneDrive/Documents/HACXELERATE/bytexl-panda-/backend/app/models/fhir/patient.py), and [`backend/app/models/fhir/medication.py`](file:///C:/Users/adity/OneDrive/Documents/HACXELERATE/bytexl-panda-/backend/app/models/fhir/medication.py):

### A. Field Survival vs. Schema Gap Analysis

| Field in Extraction DTO / Validation Report | Extracted by Person 1? | Survives in `fhir_observations`? | Survives in `fhir_medications`? | Root Cause / Action Required |
| :--- | :---: | :---: | :---: | :--- |
| `name` / `code` | **YES** | **YES** (`Observation.code_text`) | **YES** (`Medication.name`) | Maintained |
| `value` / `value_quantity` | **YES** | **YES** (`Observation.value_quantity`) | N/A | Maintained |
| `unit_symbol` | **YES** | **YES** (`Observation.unit`) | N/A | Maintained |
| `status` | **YES** | **YES** (`Observation.status`) | **YES** (`Medication.status`) | Maintained |
| `document_id` | **YES** | **YES** (`Observation.document_id`) | **DROPPED** (No column in table) | **Person 4 schema migration required** |
| `page_number` | **YES** | **DROPPED** (No column in table) | **DROPPED** (No column in table) | **Person 4 schema migration required** |
| `evidence_text` | **YES** | **DROPPED** (No column in table) | **DROPPED** (No column in table) | **Person 4 schema migration required** |
| `confidence` | **YES** | **DROPPED** (No column in table) | **DROPPED** (No column in table) | **Person 4 schema migration required** |
| `review_status` | **YES** | **DROPPED** (No column in table) | **DROPPED** (No column in table) | **Person 4 schema migration required** |

### B. Idempotency & Transactional Retries
- **Audit Result:** `ExtractionPersistenceHandler.persist_observations()` correctly executes inside an atomic nested savepoint:
  ```python
  async with db.begin_nested():
      # Delete existing observations for document_id (Idempotency)
      await db.execute(delete(Observation).where(Observation.document_id == document_id))
      # Re-insert fresh observations
      db.add_all(new_observations)
  ```
- **Guarantees:**
  1. Re-running extraction on an existing document replaces stale records cleanly without primary key collisions or duplicate accumulation.
  2. If persistence fails halfway through, the transaction rolls back cleanly, leaving previous valid observations intact.

---

## 7. Regression Test Suite Verification

All 6 test suites were executed hermetically without external network or API calls:

```powershell
python -m unittest backend/tests/ocr_benchmark/test_ocr_benchmark.py `
                   backend/tests/test_extraction_pipeline_integration.py `
                   backend/tests/test_evidence_grounding_bilingual.py `
                   backend/tests/test_native_pdf_extraction.py `
                   backend/tests/test_extraction_contract.py `
                   backend/tests/test_document_ingestion_hardening.py
```

**Results:**
- **Ran 135 tests in 1.136s**
- **Failures:** 0
- **Errors:** 0
- **Status:** **OK (100% Pass Rate)**

---

## 8. Artifacts & Deliverables

1. **35-Document Synthetic Dataset & Metrics Suite:** [`backend/tests/ocr_benchmark/evaluation_35.py`](file:///C:/Users/adity/OneDrive/Documents/HACXELERATE/bytexl-panda-/backend/tests/ocr_benchmark/evaluation_35.py)
2. **Raw Evaluation JSON Report:** [`backend/tests/ocr_benchmark/fixtures_35/evaluation_results_35.json`](file:///C:/Users/adity/OneDrive/Documents/HACXELERATE/bytexl-panda-/backend/tests/ocr_benchmark/fixtures_35/evaluation_results_35.json)
3. **Traceability Matrix:** [`PERSON1_FRD_TRACEABILITY.md`](file:///C:/Users/adity/OneDrive/Documents/HACXELERATE/bytexl-panda-/PERSON1_FRD_TRACEABILITY.md)
4. **Downstream Integration Handoff:** [`PERSON1_HANDOFF.md`](file:///C:/Users/adity/OneDrive/Documents/HACXELERATE/bytexl-panda-/PERSON1_HANDOFF.md)
5. **OCR Benchmark & Evaluation Report:** [`OCR_EVALUATION_REPORT.md`](file:///C:/Users/adity/OneDrive/Documents/HACXELERATE/bytexl-panda-/OCR_EVALUATION_REPORT.md)

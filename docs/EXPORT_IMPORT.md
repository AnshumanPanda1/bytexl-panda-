# Export & Import (Backup)

Health Assistant can export and re-import data as **backup files**, at three scopes and in three formats. Exports are FHIR R4B-conformant and integrity-checked; imports are validated with [`fhir.resources`](https://pypi.org/project/fhir.resources/) and upserted by natural key with automatic id remapping across tenants.

> **Files**: `backend/app/services/{export_service,import_service,fhir_converter}.py`, `backend/app/api/v1/endpoints/{export,import_data}.py`, `backend/app/workers/tasks.py` (`export_backup`, `import_backup`), `backend/app/models/export_import_job.py`, `backend/app/schemas/backup.py`.

---

## 1. Scopes

Scopes mirror the FHIR [Bulk Data Access](https://hl7.org/fhir/uv/bulkdata/) levels. Each scope is stored on the export job as a **SMART-compatible scope string** (`smart_scope`) — these are vocabulary-only claims enforced by the platform's existing RBAC + tenant isolation; no separate OAuth2 authorization server is required.

| Scope | SMART claim | Who can request | Coverage |
|---|---|---|---|
| `patient` | `patient/*.rs` | `USER` (single own patient), `MANAGER`, `ADMIN`, `SYSTEM_ADMIN` | One patient (`patient_ids` required, single id for `USER`) |
| `group` | `system/*.rs` | `MANAGER`, `ADMIN`, `SYSTEM_ADMIN` | Multiple patients (`patient_ids` required) |
| `system` | `system/*.cruds` | `ADMIN`, `SYSTEM_ADMIN` | Whole tenant (`patient_ids` ignored) |

`SYSTEM_ADMIN` bypasses all role checks (existing behaviour).

---

## 2. Export types

| Type | File | Contents |
|---|---|---|
| `fhir_only` | `<job_id>.fhir.json` | A single **FHIR R4B `Bundle`** (`type: transaction`). Portable to any FHIR server. Resources: `Patient`, `Observation`, `MedicationStatement`, `AllergyIntolerance`, `DiagnosticReport`, `Organization`, `Practitioner`, `DocumentReference` (metadata only — no inline binaries). No telemetry, no integrations, no AI config. |
| `full_backup` | `<job_id>.zip` | A **BagIt-style ZIP** containing the FHIR Bundle plus non-FHIR sidecars, raw document files, and a SHA256 manifest. Re-importing this ZIP restores the tenant/patient. |
| `catalog_only` | `<job_id>.catalog.json` | Biomarker/unit definitions, medication/allergy catalogs + clinical-event-type `metadata_schema` definitions. Cross-tenant portable (use to seed a new deployment). |

### ZIP layout (`full_backup`)

```
<job_id>.zip
├── manifest.json              # BackupManifest: schema_version, exported_at, tenant_id, fhir_version, scope, export_type, smart_scope, counts{}, files[]{path,sha256,size}, options, notes
├── manifest-sha256.txt        # <sha256>  <path>  (BagIt-style, one line per file)
├── bag-info.txt               # tenant id, job id, export timestamp, schema/FHIR version, smart scope
├── fhir/
│   └── bundle.json            # the FHIR R4B transaction Bundle (clinical core)
├── nonfhir/
│   ├── examinations.json
│   ├── clinical_events.json
│   ├── clinical_event_types.json
│   ├── biomarker_definitions.json
│   ├── medication_catalog.json
│   ├── allergy_catalog.json
│   ├── documents.json         # document metadata + _archive_path mapping
│   ├── telemetry.json         # group/system scope only (see §5)
│   ├── integrations.json      # user_integrations incl. encrypted user_config + OAuth tokens
│   ├── notification_triggers.json
│   └── ai_config.json         # system scope + include_ai_config only (restore not supported in v1)
└── documents/                 # raw uploaded files (not base64), referenced by documents.json
    └── <doc_id>.<ext>
```

---

## 3. Endpoints

All under `/api/v1`, JWT-auth required.

### Export

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/export` | Create an export job (body: `BackupRequest`). Enqueues `export_backup` Celery task. Returns `ExportJobResponse`. |
| `GET` | `/export/jobs` | List export jobs for the current tenant. |
| `GET` | `/export/jobs/{job_id}` | Get job status (`PENDING` → `PROCESSING` → `COMPLETED`/`FAILED`/`PARTIAL`). |
| `GET` | `/export/jobs/{job_id}/download` | Download the generated file (JWT-gated, tenant-scoped). |

**`POST /export` body:**
```json
{
  "scope": "patient",
  "export_type": "full_backup",
  "patient_ids": ["<uuid>"],
  "include_documents": true,
  "include_telemetry": true,
  "include_integrations": true,
  "include_ai_config": false
}
```

### Import

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/import/backup` | Upload a ZIP **or** a bare `bundle.json`/`catalog.json`. Enqueues `import_backup` Celery task. Returns `ImportJobResponse`. |
| `GET` | `/import/jobs/{job_id}` | Get backup-import job status + `restore_result` (created/updated counts, manifest verification). |
| `POST` | `/import/fhir` | Synchronous FHIR Bundle import (smaller bundles, no job tracking). |
| `POST` | `/import/csv` | CSV import (legacy). |
| `POST` | `/import/ocr` | OCR extraction (legacy). |

**`POST /import/backup`** — multipart `file` field. The server detects the format:
- ZIP → verifies manifest SHA256, restores FHIR bundle + sidecars + documents.
- Bare JSON with `resourceType: "Bundle"` → restores as a FHIR transaction.
- Bare JSON with `units`/`biomarkers` keys → upserts the ontology catalog.

---

## 4. FHIR conversion & validation

- **Library**: `fhir.resources==8.2.0` (R4B sub-package, Pydantic-v2-native). Provides *structural* validation (types, cardinality, JSON shape) without a terminology server.
- **`services/fhir_converter.py`** converts ORM `to_dict()` output (snake_case + app extensions) to canonical FHIR R4B JSON and back:
  - App-only fields (`tenant_id`, `user_id`, `biomarker_id`, `normalized_value`, `dashboard_layout`, `org_type`, …) are stripped from the FHIR output.
  - `Patient.mrn` → `identifier[{system: "urn:healthassistant:mrn"}]`.
  - Enum casing normalized (`Gender.FEMALE` → `"female"`; `MedicationStatus.ACTIVE` → `"active"`).
  - `Medication` ORM → FHIR `MedicationStatement`; `DoctorModel` → FHIR `Practitioner`.
  - Cardinality fixes for R4B: `Organization.type`, `DiagnosticReport.conclusionCode`/`presentedForm`/`category` wrapped as lists; `Observation.comment` → `note`; `MedicationStatement.timing.repeat.timeOfDay` padded to `HH:MM:SS`. (`Observation.interpretation` is now stored natively as the canonical FHIR `0..*` CodeableConcept list — JSONB column — so export is a pass-through; `Observation.component` is also stored + exported natively.)
- Every exported resource carries `meta.versionId`, `meta.lastUpdated`, `meta.source`, and a provenance `meta.tag` (`{system: "https://healthassistant.local/fhir/export", code: "ha-export"}`).
- On import, each entry is validated with `fhir.resources.R4B.get_fhir_model_class(rt).model_validate(...)`; invalid entries are recorded as errors and skipped. All 13 importable FHIR resource types are handled (`Patient`, `Observation`, `MedicationStatement`, `MedicationRequest`, `AllergyIntolerance`, `DiagnosticReport`, `Organization`, `Practitioner`, `Condition`, `Encounter`, `Device`, `Communication`, `Provenance`; `DocumentReference` is intentionally skipped on import with a warning since binary content lives in the `documents/` sidecar). The FHIR R4 facade exposes 19 resource types overall — see [FHIR_R4_FACADE.md](FHIR_R4_FACADE.md).

---

## 5. Data integrity

- **SHA256 manifest**: `manifest.json` lists every file with its `sha256` + `size`; `manifest-sha256.txt` is the BagIt-style `"<sha256>  <path>"` duplicate. On import, each file's hash is recomputed and compared → `manifest_verified` flag on the result.
- **Provenance tag**: every FHIR resource carries the `ha-export` `meta.tag`; importers can check it to confirm origin.
- **Round-trip**: export serializes via `fhir.resources`; import validates with the same R4B classes, so the schema is shared. Pydantic field equality + hash match is the integrity guarantee.

---

## 6. Restore behaviour & caveats

- **Transaction verb routing**: the import path honors each entry's `request.method` (FHIR transaction Bundles). `PUT Type/<id>` updates an existing same-tenant row or creates one **with the supplied id** (not a random UUID); `POST` + `ifNoneExist` performs a conditional create (skipped when a match exists — Patient `identifier` → `mrn` lookup today; unsupported forms log a warning and create rather than silently treating "couldn't match" as "no match"); `DELETE` soft-deletes (idempotent on missing id). Entries with no `request` block default to `POST` (create-new) — the historical behaviour. This makes round-tripping third-party EHR / SMART transaction Bundles preserve referential integrity.
- **Upsert by id with cross-tenant remapping**: for each FHIR resource, if the imported `id` already exists **in the same tenant** → update in place; if it exists in a **different tenant** → generate a new UUID, record the remap, **and surface a warning** in the ImportJob result (e.g. `"Patient/<id> already exists in tenant <other>; created new with id <new>"`) so collisions are visible. All reference-bearing fields (`subject`/`patient`/`performer`/`partOf`/`context`/`encounter`/`author`/`device`/`specimen`/`sender`/`recipient`) are rewritten through the remap dict; bare `urn:uuid:` references are routed to the correct resource type via a `FIELD_HINT_TO_TYPE` map + bundle look-ahead (ambiguous hints like `sender`/`recipient` are resolved by finding the referenced resource's type in the bundle).
- **Provenance per entry**: every created/updated/deleted entry records a `Provenance` resource (best-effort — never aborts the import) with the `CREATE`/`UPDATE`/`DELETE` activity code, the importing user as the agent, and an `ImportJob/<id>` reference in `entity_inputs` so bulk-import Provenance is distinguishable from facade-write Provenance.
- **`BundleRestoreResult`**: `ImportService.restore_fhir_bundle` returns a dataclass with `created`/`updated`/`deleted`/`skipped`/`errors`/`warnings`/`id_remap` fields (attribute access). *Breaking change* (was a 5-tuple prior to v0.3.0).
- **Telemetry**: for **patient** scope, telemetry is **excluded** (telemetry rows are tenant-scoped; a note is written to the manifest). For `group`/`system` scope, all tenant telemetry is included. On restore, telemetry rows are re-inserted with the destination tenant id.
- **Documents**: raw files are archived under `documents/<doc_id>.<ext>`; on restore they're written back to `HA_UPLOAD_DIR/<tenant_id>/<new-uuid>.<ext>` and `DocumentModel.file_path` is rebased. OCR `extracted_text`/`entities` are preserved (no re-OCR needed).
- **Integrations**: `user_integrations.user_config` is exported **with Fernet-encrypted secrets intact** (the `{"_encrypted": ...}` tokens) plus plaintext OAuth `access_token`/`refresh_token`. **Restoring on a deployment with a different `HA_DATA_KEY` will leave secrets undecryptable** — the rows import, but the integration will fail to authenticate. A warning is added if `HA_DATA_KEY` is unset on the target. Never use the `mask_fields` helper in the export path.
- **AI config** (`ai_config.json`): exported only when `scope=system` and `include_ai_config=true`. **Restore is not supported in v1** (export-only) — a warning is recorded. `api_key` values are exported as-is (they're already plaintext in the DB).
- **Clinical event types / categories**: upserted by `slug` (only inserted if missing; existing definitions are not overwritten).
- **Biomarker catalog**: delegated to `CatalogImportService.import_catalog` (upsert by `slug`/`symbol`).

---

## 7. Job lifecycle (Celery)

Export/import are **async Celery tasks** (long jobs don't block the request):
1. `POST /export` (or `/import/backup`) creates an `ExportJobModel`/`ImportJobModel` row (`PENDING`) and calls `export_backup.delay(job_id)` / `import_backup.delay(job_id, archive_path, user_id)`.
2. The task binds a fresh session to the **worker-scoped shared engine** via `get_async_session()` (the engine is a singleton with `NullPool`, never disposed per task), runs `ExportService.run_export` / `ImportService.run_import`, and updates the job row (`PROCESSING` → `COMPLETED`/`PARTIAL`/`FAILED`).
3. The import task deletes the temp upload file in `finally`.
4. Poll `GET /export/jobs/{id}` (or `/import/jobs/{id}`) for progress; download via `GET /export/jobs/{id}/download`.

Generated files are written to `HA_UPLOAD_DIR/exports/<tenant_id>/`. There is no automatic retention/cleanup yet (admin should prune old exports).

---

## 8. Adding it to a new deployment

`fhir.resources` is in `backend/pyproject.toml`. The `export_jobs` and `import_jobs` tables are created by the consolidated Alembic baseline (`8ddb7ef7ca4d`). Run `alembic upgrade head` after pulling.

---

## 9. Frontend UI

Admins reach the feature at **Settings → Export & Import** (`/settings/export-import`, `ADMIN`+). Two tabs — Export (scope, includes, trigger) and Import (upload, dry-run, history) — with a confirmation modal before any mutating run. Job progress polls live from the jobs tables; no page reload needed.

---

## 10. Patient FHIR Export & Mock ABHA/ABDM Readiness (Person 4)

In addition to asynchronous bulk exports, the platform provides direct synchronous FHIR R4-inspired export and simulated ABDM interoperability endpoints:

### A. Patient FHIR R4-Inspired Bundle Export
- **Endpoints**:
  - `GET /api/v1/export/fhir/patient/{patient_id}`
  - `GET /api/v1/patients/{patient_id}/fhir-export`
- **Output**: Valid JSON `Bundle` of type `collection` labeled with meta-tag `urn:health-assistant:interop:profile#limited-fhir-r4-inspired`.
- **Supported Resources**:
  - `Patient`: Demographics, MRN, gender, birth date.
  - `DocumentReference`: Uploaded source medical records.
  - `Observation`: Vital signs, biomarker values, reference ranges, interpretation, and source document link.
  - `MedicationStatement` / `MedicationRequest`: Prescriptions, dosages, frequencies.
  - `Condition`: Diagnoses, clinical status, onset dates, and source document/evidence references (`clinical_events`).
- **Scope & Limitations**:
  - Scoped strictly to relational data available in the tenant database.
  - Clearly tagged as a limited, machine-readable export; does NOT claim official ABDM or HL7 conformance certification.

### B. Mock ABHA/ABDM Simulation
- **Endpoints**:
  - `POST /api/v1/mock-abdm/patient/{patient_id}/preview`: Computes deterministic SHA-256 fingerprint, previews observations/medications/conditions, checks whether the record was previously imported, and returns preview records without database mutations.
  - `POST /api/v1/mock-abdm/patient/{patient_id}/confirm`: Persists synthetic records into canonical tables (`Observation`, `Medication`, `ClinicalEvent`), logs an `AuditEvent`, tracks provenance (`mock_abdm`), and rejects duplicate submissions (status: `duplicate` with existing record ID).
  - `GET /api/v1/mock-abdm/imports`: Returns tenant import history.
  - `GET /api/v1/mock-abdm/samples`: Returns pre-packaged bilingual synthetic bundles (English and Hindi).
- **Simulation Boundary**:
  - Strictly synthetic data using provider identifier `mock_abdm`.
  - No real ABHA identifiers or live ABDM gateway connectivity is utilized or required.

### C. Clinical Facts & Health Summary Staleness
- **Facts Retrieval & Correction**:
  - `GET /api/v1/facts/document/{document_id}` (`GET /api/v1/documents/{document_id}/facts`): Aggregates extracted facts with `original_text`, `confidence`, and `review_status`.
  - `POST /api/v1/facts/correct`: Applies user corrections, preserving `original_text` untouched, updating normalized values, creating an `AuditEvent`, and marking dependent patient summaries as stale.
- **Health Summaries**:
  - `GET /api/v1/summaries/patient/{patient_id}`: Returns summaries with `is_stale`, `stale_reason`, and `stale_at`.
  - `POST /api/v1/summaries/patient/{patient_id}`: Stores plain-language summaries in English (`en`) and Hindi (`hi`).
  - `POST /api/v1/summaries/{summary_id}/invalidate`: Explicit invalidation.

---

### D. Versioned Data-Contract Examples (v1.0)

#### 1. Limited FHIR R4-Inspired Bundle Export (`GET /api/v1/export/patient/{patient_id}/fhir`)
```json
{
  "resourceType": "Bundle",
  "id": "export-c5559436-2a9a-4288-a890-c0748bf7fc8a-a1b2c3d4",
  "type": "collection",
  "timestamp": "2026-10-10T10:15:00.000000Z",
  "meta": {
    "versionId": "1.0",
    "lastUpdated": "2026-10-10T10:15:00.000000Z",
    "tag": [
      {
        "system": "urn:health-assistant:interop:profile",
        "code": "limited-fhir-r4-inspired",
        "display": "Health Assistant Limited FHIR R4-Inspired Export (Not official ABDM/HL7 certified)"
      }
    ]
  },
  "total": 5,
  "entry": [
    {
      "fullUrl": "urn:uuid:c5559436-2a9a-4288-a890-c0748bf7fc8a",
      "resource": {
        "resourceType": "Patient",
        "id": "c5559436-2a9a-4288-a890-c0748bf7fc8a",
        "name": [{ "family": "Sharma", "given": ["Rohit"] }],
        "gender": "male",
        "birthDate": "1988-04-30"
      }
    },
    {
      "fullUrl": "urn:uuid:d1111111-2222-3333-4444-555555555555",
      "resource": {
        "resourceType": "DocumentReference",
        "id": "d1111111-2222-3333-4444-555555555555",
        "status": "current",
        "docStatus": "final",
        "subject": { "reference": "Patient/c5559436-2a9a-4288-a890-c0748bf7fc8a" },
        "content": [{ "attachment": { "title": "lab_report.pdf", "url": "urn:ha-document:d1111111-2222-3333-4444-555555555555" } }]
      }
    },
    {
      "fullUrl": "urn:uuid:e2222222-3333-4444-5555-666666666666",
      "resource": {
        "resourceType": "Observation",
        "id": "e2222222-3333-4444-5555-666666666666",
        "status": "final",
        "code": { "text": "Fasting Plasma Glucose", "coding": [{ "system": "http://loinc.org", "code": "1558-6" }] },
        "subject": { "reference": "Patient/c5559436-2a9a-4288-a890-c0748bf7fc8a" },
        "valueQuantity": { "value": 115.0, "unit": "mg/dL" },
        "derivedFrom": [{ "reference": "DocumentReference/d1111111-2222-3333-4444-555555555555" }]
      }
    },
    {
      "fullUrl": "urn:uuid:f3333333-4444-5555-6666-777777777777",
      "resource": {
        "resourceType": "MedicationStatement",
        "id": "f3333333-4444-5555-6666-777777777777",
        "status": "active",
        "medicationCodeableConcept": { "text": "Metformin 500mg" },
        "subject": { "reference": "Patient/c5559436-2a9a-4288-a890-c0748bf7fc8a" },
        "dosage": [{ "text": "Once daily with dinner" }]
      }
    },
    {
      "fullUrl": "urn:uuid:a4444444-5555-6666-7777-888888888888",
      "resource": {
        "resourceType": "Condition",
        "id": "a4444444-5555-6666-7777-888888888888",
        "clinicalStatus": { "coding": [{ "code": "active" }] },
        "code": { "text": "Impaired Fasting Glycemia" },
        "subject": { "reference": "Patient/c5559436-2a9a-4288-a890-c0748bf7fc8a" },
        "evidence": [{ "detail": [{ "reference": "DocumentReference/d1111111-2222-3333-4444-555555555555" }] }]
      }
    }
  ]
}
```

#### 2. Mock ABDM Synthetic Bundle Payload (`POST /api/v1/mock-abdm/patient/{patient_id}/confirm`)
```json
{
  "external_record_id": "SIM-RECORD-2026-001",
  "source_system": "mock_abdm",
  "facility_name": "Apollo Clinic (Simulated)",
  "facility_id": "IN-DL-SIM-01",
  "care_context": "OPD Consultation",
  "recorded_at": "2026-10-10T10:00:00Z",
  "observations": [
    {
      "test_name": "Fasting Plasma Glucose",
      "code": "1558-6",
      "coding_system": "LOINC",
      "value": 118.0,
      "unit": "mg/dL",
      "reference_range": "70 - 100 mg/dL",
      "confidence": 0.98,
      "original_text": "FBS: 118 mg/dL"
    }
  ],
  "medications": [
    {
      "name": "Metformin HCl",
      "dosage": "500 mg",
      "frequency": "Once daily with dinner",
      "confidence": 0.95
    }
  ],
  "conditions": [
    {
      "name": "Impaired Fasting Glucose",
      "status": "active",
      "confidence": 0.90
    }
  ],
  "notes_en": "Patient advised to maintain low-glycemic diet.",
  "notes_hi": "मरीज को कम ग्लाइसेमिक आहार बनाए रखने की सलाह दी गई।"
}
```

#### 3. Fact Correction Request & Response (`POST /api/v1/facts/correct`)
**Request**:
```json
{
  "fact_type": "observation",
  "fact_id": "e2222222-3333-4444-5555-666666666666",
  "corrected_value": 112.0,
  "corrected_unit": "mg/dL",
  "correction_reason": "Clinician verified Fasting Glucose adjustment following manual strip verification",
  "new_review_status": "verified"
}
```
**Response**:
```json
{
  "fact_type": "observation",
  "fact_id": "e2222222-3333-4444-5555-666666666666",
  "old_value": { "normalized_value": 118.0, "review_status": "extracted" },
  "new_value": { "normalized_value": 112.0, "review_status": "verified", "_correction_reason": "Clinician verified Fasting Glucose adjustment following manual strip verification" },
  "invalidated_summaries_count": 1,
  "message": "Fact corrected and audit logged successfully"
}
```

#### 4. Bilingual Health Summary (`GET /api/v1/summaries/patient/{patient_id}`)
```json
[
  {
    "id": "s1111111-2222-3333-4444-555555555555",
    "patient_id": "c5559436-2a9a-4288-a890-c0748bf7fc8a",
    "title": "Comprehensive Health Overview",
    "summary_text": "Patient has impaired fasting glucose (112 mg/dL) managed with Metformin 500mg. Kidney function and blood pressure remain within normal parameters.",
    "language": "en",
    "is_stale": false,
    "stale_reason": null,
    "source_references": [
      { "type": "observation", "id": "e2222222-3333-4444-5555-666666666666", "name": "Fasting Plasma Glucose", "value": 112.0 },
      { "type": "medication", "id": "f3333333-4444-5555-6666-777777777777", "name": "Metformin HCl" }
    ],
    "created_at": "2026-10-10T10:15:00Z"
  },
  {
    "id": "s2222222-3333-4444-5555-666666666666",
    "patient_id": "c5559436-2a9a-4288-a890-c0748bf7fc8a",
    "title": "स्वास्थ्य अवलोकन",
    "summary_text": "मरीज का फास्टिंग ग्लूकोज (112 mg/dL) मेटफॉर्मिन 500mg द्वारा नियंत्रित है। रक्तचाप और अन्य परीक्षण सामान्य सीमा में हैं।",
    "language": "hi",
    "is_stale": false,
    "stale_reason": null,
    "source_references": [
      { "type": "observation", "id": "e2222222-3333-4444-5555-666666666666", "name": "Fasting Plasma Glucose", "value": 112.0 }
    ],
    "created_at": "2026-10-10T10:15:00Z"
  }
]
```

---

### E. Documented API Error Codes

| Status Code | Error Classification | Scenario | Behavior & Guarantee |
|:---|:---|:---|:---|
| **400 Bad Request** | `ValidationError` | Group export missing `patient_ids`; invalid request payload structure | Reject before DB execution with specific missing-field detail. |
| **401 Unauthorized** | `AuthenticationError` | Missing, expired, or improperly signed JWT | Reject request immediately; HttpOnly cookie rotation required. |
| **403 Forbidden** | `AuthorizationError` | `Role.USER` attempting to read or write another patient's timeline, facts, summaries, or exports | Access denied with explicit error; patient ownership check strictly enforced. |
| **404 Not Found** | `NotFoundError` | Target patient, document, or record belongs to another tenant or does not exist | Tenant isolation returns 404 (zero information leak regarding other tenants' records). |
| **409 Conflict** | `DuplicateRecordError` | Mock ABDM bundle with identical SHA-256 checksum confirmed again | Returns `status: "duplicate"` with `is_duplicate: true`; no duplicate clinical rows inserted. |
| **422 Unprocessable** | `PydanticValidationError` | Request body fields violate type, range, or regex constraints | Standard FastAPI validation error specifying parameter location. |
| **503 Service Unavail** | `UpstreamProviderError` | AI summary provider unconfigured, unreachable, or upstream timeout | Preserves clear error status without mock fabrication; upstream API keys and tokens scrubbed. |


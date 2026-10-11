# Changelog

All notable changes to MediBot are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Image upload support (`.png`, `.jpg`, `.jpeg`) alongside existing document formats in the examination upload panel.
- Unified fallback AI credential resolution for OCR (`LangChainOCRProcessor`) and NLP extraction (`LangChainStructuredExtractor`) supporting Groq and OpenAI-compatible providers.

### Changed
- Complete minimalist UI redesign across the frontend: refined dark-theme color palette, clean typography, compact sticky headers, and consistent card spacing.
- Streamlined examination creation workflow with instant image preview, progress tracking, and resilient multipart upload.
- Simplified patient detail, document explorer, and AI assistant interfaces.

### Fixed
- Resolved duplicate `return (` syntax error in authentication view (`Login.tsx`).
- Resolved missing credentials error during asynchronous document OCR extraction tasks.

## [1.0.0] - 2026-10-10

### Initial Release — AI-Powered Personal Health Copilot

#### Features
- **Document Ingestion & Extraction (Person 1)**:
  - Processing for medical records, lab reports, and prescriptions.
  - OCR extraction with structured field mapping, confidence scoring, and review flags.
- **AI-Powered Bilingual Summaries (Person 2)**:
  - Grounded clinical summarization in English and Hindi using Groq LPU inference.
  - Strict clinical safety guards (no hallucinated reference ranges or diagnoses).
  - Multi-provider support (Groq, Google Gemini, OpenRouter) with offline fallback.
  - Automatic cache invalidation when facts are edited or new documents arrive.
- **Frontend & Bilingual UX (Person 3)**:
  - Streamlined health copilot interface in English and Hindi.
  - Interactive fact review screen with source document provenance and confidence badges.
  - Simplified navigation focused on patient copilot workflows.
- **Canonical Health Models, Interoperability & Timeline (Person 4)**:
  - Extended canonical health models (`Observation`, `Medication`, `ClinicalEvent`) with provenance and raw text retention.
  - Patient health timeline aggregating visits, lab observations, medications, and conditions (`GET /api/v1/timeline/patient/{patient_id}`).
  - Document facts extraction and audited corrections with summary invalidation (`POST /api/v1/facts/correct`).
  - Machine-readable HL7 FHIR R4 JSON Bundle export (`GET /api/v1/export/fhir/patient/{patient_id}`).
  - Simulated ABHA/ABDM preview and confirmation workflow with deterministic SHA-256 deduplication.
- **DevOps, Security & Packaging (Person 5)**:
  - Tenant isolation enforcement across all clinical endpoints.
  - Docker Compose orchestration for full-stack local and server deployment.

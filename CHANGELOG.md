# Changelog

All notable changes to MediBot are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-10-10

### Initial Release — AI-Powered Personal Health Copilot

#### Features
- **Document Ingestion & Extraction**:
  - Processing for medical records, lab reports, and prescriptions.
  - OCR extraction with structured field mapping, confidence scoring, and review flags.
- **AI-Powered Bilingual Summaries (Person 2)**:
  - Grounded clinical summarization in English and Hindi using Groq LPU inference.
  - Strict clinical safety guards (no hallucinated reference ranges or diagnoses).
  - Multi-provider support (Groq, Google Gemini, OpenRouter) with offline fallback.
  - Automatic cache invalidation when facts are edited or new documents arrive.
- **Patient Health Timeline**:
  - Chronological tracking of clinical observations, labs, and vitals.
- **Interoperability & Standards**:
  - HL7 FHIR R4 JSON Bundle export.
  - Simulated ABHA record import and preview flow with clear simulation boundaries.
- **Modern Bilingual UX**:
  - English and Hindi language switching.
  - Interactive fact review screen with source document provenance and snippets.

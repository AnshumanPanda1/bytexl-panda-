"""Unit tests for Phase 5 evidence-grounded structured extraction and bilingual support.

Covers:
1. A supported observation with valid evidence and page provenance.
2. A hallucinated evidence passage rejected or flagged.
3. An incorrect page number rejected or flagged.
4. Identical text appearing on multiple pages without arbitrary attribution.
5. Evidence that belongs to a different document.
6. Missing dates, units, medication frequency, and clinical status.
7. Hindi evidence preserved without unintended translation.
8. Mixed-language prescriptions and laboratory values.
9. Numeric values and units retained correctly.
10. Conservative review status for ambiguous findings.
11. Malformed or incomplete LLM output handled safely.
12. Compatibility with existing extraction contract tests.
"""

import os
import sys
import unittest
import uuid

# Ensure backend root is on Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.ai.pipeline.evidence_validator import (
    EvidenceValidator,
    PageSegment,
    ValidationOutcome,
    ValidationReport,
    normalize_evidence_text,
)
from app.ai.schemas.nlp import (
    DiagnosisExtract,
    DocumentEntitiesExtract,
    KnownBiomarkerExtract,
    KnownMedicationExtract,
    PatientInfoExtract,
    UnknownBiomarkerExtract,
    UnknownMedicationExtract,
)


class TestEvidenceValidationCore(unittest.TestCase):
    """Core evidence grounding and provenance validation tests."""

    def setUp(self):
        self.validator = EvidenceValidator()
        self.doc1_id = "11111111-1111-1111-1111-111111111111"
        self.doc2_id = "22222222-2222-2222-2222-222222222222"

        self.cumulative_text = (
            f"--- Document {self.doc1_id} | Page 1 ---\n"
            "Patient: Rajesh Sharma | DOB: 1978-04-15\n"
            "Complete Blood Count\n"
            "Hemoglobin: 14.5 g/dL (Reference: 13.0 - 17.0)\n"
            "WBC: 6.8 K/uL\n"
            "General Status: Normal\n\n"
            f"--- Document {self.doc1_id} | Page 2 ---\n"
            "Metabolic Panel\n"
            "Fasting Blood Glucose: 110 mg/dL (Reference: 70 - 99)\n"
            "HbA1c: 6.5%\n"
            "Clinical Impression: Impaired Fasting Glucose\n"
            "General Status: Normal\n\n"
            f"--- Document {self.doc2_id} | Page 1 ---\n"
            "Prescription Summary\n"
            "Rx: Metformin 500mg oral daily with evening meal\n"
            "Platelets: 250 K/uL\n"
        )

    def test_supported_observation_valid_evidence_and_page_provenance(self):
        """Case 1: Observation with valid evidence snippet and exact page number is verified."""
        bio = KnownBiomarkerExtract(
            name="Hemoglobin",
            matched_slug="hemoglobin",
            value=14.5,
            unit_symbol="g/dL",
            reference_range_min=13.0,
            reference_range_max=17.0,
            document_id=self.doc1_id,
            page_number=1,
            evidence_text="Hemoglobin: 14.5 g/dL (Reference: 13.0 - 17.0)",
            confidence=0.95,
            review_status="needs_review",
        )

        segments = self.validator.parse_page_segments(self.cumulative_text)
        outcome = self.validator.validate_single_entity(bio, segments)

        self.assertTrue(outcome.is_valid)
        self.assertEqual(outcome.reason, "verified")
        self.assertEqual(outcome.verified_document_id, self.doc1_id)
        self.assertEqual(outcome.verified_page_number, 1)
        self.assertEqual(bio.review_status, "needs_review")
        self.assertEqual(bio.confidence, 0.95)

    def test_hallucinated_evidence_passage_flagged(self):
        """Case 2: Hallucinated evidence text not found in source text is flagged and penalized."""
        bio = KnownBiomarkerExtract(
            name="Cholesterol",
            matched_slug="cholesterol",
            value=240.0,
            unit_symbol="mg/dL",
            document_id=self.doc1_id,
            page_number=1,
            evidence_text="Total Cholesterol: 240 mg/dL (Severely Elevated)",  # Hallucinated snippet
            confidence=0.9,
            review_status="needs_review",
        )

        segments = self.validator.parse_page_segments(self.cumulative_text)
        outcome = self.validator.validate_single_entity(bio, segments)

        self.assertFalse(outcome.is_valid)
        self.assertEqual(outcome.reason, "hallucinated_evidence")
        self.assertEqual(bio.review_status, "needs_review")
        # Confidence must be capped/penalized
        self.assertLessEqual(bio.confidence, 0.2)
        # Original evidence text is preserved verbatim without alteration
        self.assertEqual(bio.evidence_text, "Total Cholesterol: 240 mg/dL (Severely Elevated)")

    def test_incorrect_page_number_flagged(self):
        """Case 3: Model cites page 1 when the evidence is on page 2; citation is flagged."""
        bio = KnownBiomarkerExtract(
            name="Glucose",
            matched_slug="glucose",
            value=110.0,
            unit_symbol="mg/dL",
            document_id=self.doc1_id,
            page_number=1,  # Incorrect page; Glucose is on page 2!
            evidence_text="Fasting Blood Glucose: 110 mg/dL (Reference: 70 - 99)",
            confidence=0.88,
            review_status="needs_review",
        )

        segments = self.validator.parse_page_segments(self.cumulative_text)
        outcome = self.validator.validate_single_entity(bio, segments)

        self.assertFalse(outcome.is_valid)
        self.assertEqual(outcome.reason, "page_mismatch")
        self.assertEqual(bio.review_status, "needs_review")
        self.assertLessEqual(bio.confidence, 0.4)

    def test_identical_text_on_multiple_pages_unambiguous_rejection(self):
        """Case 4: Identical text on multiple pages is flagged as ambiguous without arbitrary attribution."""
        diag = DiagnosisExtract(
            name="Normal Findings",
            document_id=self.doc1_id,
            page_number=2,
            evidence_text="General Status: Normal",  # Appears on Doc 1 Page 2 AND Doc 2 Page 1!
            confidence=0.85,
            review_status="needs_review",
        )

        segments = self.validator.parse_page_segments(self.cumulative_text)
        outcome = self.validator.validate_single_entity(diag, segments)

        self.assertFalse(outcome.is_valid)
        self.assertEqual(outcome.reason, "ambiguous_multi_page")
        self.assertEqual(diag.review_status, "needs_review")

    def test_evidence_belonging_to_different_document_flagged(self):
        """Case 5: Evidence present only in Doc 2 cannot be attributed to Doc 1."""
        bio = KnownBiomarkerExtract(
            name="Platelets",
            matched_slug="platelets",
            value=250.0,
            unit_symbol="K/uL",
            document_id=self.doc1_id,  # Claims Doc 1, but Platelets is ONLY in Doc 2!
            page_number=1,
            evidence_text="Platelets: 250 K/uL",
            confidence=0.9,
            review_status="needs_review",
        )

        segments = self.validator.parse_page_segments(self.cumulative_text)
        outcome = self.validator.validate_single_entity(bio, segments)

        self.assertFalse(outcome.is_valid)
        self.assertEqual(outcome.reason, "cross_document_misattribution")
        self.assertEqual(bio.review_status, "needs_review")
        self.assertLessEqual(bio.confidence, 0.3)
        # Does not silently overwrite doc_id to doc 2
        self.assertEqual(bio.document_id, self.doc1_id)

    def test_missing_evidence_flagged(self):
        """Entities with missing or empty evidence text are flagged immediately."""
        bio = KnownBiomarkerExtract(
            name="WBC",
            matched_slug="wbc",
            value=6.8,
            unit_symbol="K/uL",
            document_id=self.doc1_id,
            page_number=1,
            evidence_text="",  # Empty evidence
            confidence=0.8,
            review_status="needs_review",
        )

        segments = self.validator.parse_page_segments(self.cumulative_text)
        outcome = self.validator.validate_single_entity(bio, segments)

        self.assertFalse(outcome.is_valid)
        self.assertEqual(outcome.reason, "missing_evidence")
        self.assertEqual(bio.review_status, "needs_review")
        self.assertLessEqual(bio.confidence, 0.4)


class TestClinicalCautionAndDefaults(unittest.TestCase):
    """Tests for clinical caution, ungrounded status resets, and conservative defaults."""

    def setUp(self):
        self.validator = EvidenceValidator()

    def test_missing_dates_units_frequency_and_clinical_status(self):
        """Case 6: Missing properties remain strictly None without fabrication."""
        med = KnownMedicationExtract(
            name="Metformin",
            matched_catalog_id="med-101",
            strength="500 mg",
            dosage=None,
            route=None,
            frequency=None,  # Missing frequency remains None
            start_date=None,  # Missing date remains None
            end_date=None,
            status=None,  # Missing status remains None (never assumed ACTIVE)
            page_number=1,
            evidence_text="Metformin 500 mg",
            review_status="needs_review",
        )

        self.assertIsNone(med.dosage)
        self.assertIsNone(med.frequency)
        self.assertIsNone(med.start_date)
        self.assertIsNone(med.status)

        bio = KnownBiomarkerExtract(
            name="BUN/Creatinine Ratio",
            matched_slug="bun-cr-ratio",
            value=16.5,
            unit_symbol=None,  # Unitless ratio remains None
            observation_date=None,  # Missing date remains None
        )
        self.assertIsNone(bio.unit_symbol)
        self.assertIsNone(bio.observation_date)

    def test_ungrounded_medication_status_reset(self):
        """Medication status set to ACTIVE without explicit text evidence is reset to None."""
        med = KnownMedicationExtract(
            name="Atorvastatin",
            matched_catalog_id="med-202",
            status="ACTIVE",  # Model fabricated active status
            evidence_text="Atorvastatin 20mg at bedtime",  # No mention of 'active', 'ongoing', 'चालू'
        )

        self.validator.enforce_clinical_caution(med)
        self.assertIsNone(med.status)

    def test_grounded_medication_status_preserved(self):
        """Explicitly documented medication status is preserved."""
        med = KnownMedicationExtract(
            name="Lisinopril",
            matched_catalog_id="med-303",
            status="DISCONTINUED",
            evidence_text="Lisinopril 10mg discontinued due to cough",
        )

        self.validator.enforce_clinical_caution(med)
        self.assertEqual(med.status, "DISCONTINUED")

    def test_ungrounded_diagnosis_verification_status_reset(self):
        """Diagnosis verification status set to confirmed without evidence is reset to None."""
        diag = DiagnosisExtract(
            name="Type 2 Diabetes Mellitus",
            verification_status="confirmed",  # Model assumed confirmed
            clinical_status="active",  # Model assumed active
            evidence_text="Assessment: Type 2 Diabetes Mellitus",  # No explicit 'confirmed' or 'active' keyword
        )

        self.validator.enforce_clinical_caution(diag)
        self.assertIsNone(diag.verification_status)
        self.assertIsNone(diag.clinical_status)

    def test_grounded_diagnosis_verification_status_preserved(self):
        """Explicitly documented diagnosis verification status is preserved."""
        diag = DiagnosisExtract(
            name="Celiac Disease",
            verification_status="provisional",
            clinical_status="active",
            evidence_text="Provisional diagnosis: active Celiac Disease pending biopsy",
        )

        self.validator.enforce_clinical_caution(diag)
        self.assertEqual(diag.verification_status, "provisional")
        self.assertEqual(diag.clinical_status, "active")

    def test_conservative_review_status_never_auto_promoted(self):
        """Case 10: Extraction engine never marks an entity as accepted or reviewed."""
        bio = KnownBiomarkerExtract(
            name="Glucose",
            matched_slug="glucose",
            value=100.0,
            review_status="accepted",  # Simulated unauthorized promotion
        )

        self.validator.enforce_clinical_caution(bio)
        self.assertEqual(bio.review_status, "needs_review")


class TestBilingualSupport(unittest.TestCase):
    """Tests for Hindi and mixed-language documents, Unicode NFKC, and evidence preservation."""

    def setUp(self):
        self.validator = EvidenceValidator()
        self.doc_id = "33333333-3333-3333-3333-333333333333"

        self.hindi_document_text = (
            f"--- Document {self.doc_id} | Page 1 ---\n"
            "रोगी का नाम: सुरेश पटेल | उम्र: ४५ वर्ष\n"
            "प्रयोगशाला रिपोर्ट (Laboratory Report)\n"
            "रक्त शर्करा (Fasting Blood Glucose): 126 mg/dL (सामान्य: 70 - 99)\n"
            "एचबीए1सी (HbA1c): 7.2%\n"
            "निदान: उच्च रक्तचाप (Hypertension)\n\n"
            f"--- Document {self.doc_id} | Page 2 ---\n"
            "पर्चा (Prescription)\n"
            "दवा: Metformin 500 मि.ग्रा. दिन में दो बार भोजन के बाद (BID)\n"
            "स्थिति: चालू (Active)\n"
            "दवा: Telmisartan 40 mg प्रतिदिन सुबह (Daily)\n"
        )

    def test_hindi_evidence_preserved_verbatim(self):
        """Case 7: Hindi evidence snippet is matched via Unicode NFKC and retained in Devanagari script."""
        bio = KnownBiomarkerExtract(
            name="रक्त शर्करा",
            matched_slug="glucose",
            value=126.0,
            unit_symbol="mg/dL",
            document_id=self.doc_id,
            page_number=1,
            evidence_text="रक्त शर्करा (Fasting Blood Glucose): 126 mg/dL (सामान्य: 70 - 99)",
            confidence=0.92,
            review_status="needs_review",
        )

        segments = self.validator.parse_page_segments(self.hindi_document_text)
        outcome = self.validator.validate_single_entity(bio, segments)

        self.assertTrue(outcome.is_valid)
        self.assertEqual(outcome.reason, "verified")
        self.assertEqual(outcome.verified_page_number, 1)
        # Original Hindi evidence text must NOT be translated or modified
        self.assertEqual(bio.evidence_text, "रक्त शर्करा (Fasting Blood Glucose): 126 mg/dL (सामान्य: 70 - 99)")
        self.assertEqual(bio.name, "रक्त शर्करा")

    def test_mixed_language_prescription_and_laboratory_values(self):
        """Case 8: Mixed Hindi/Latin text prescription preserves original evidence and dosage."""
        med = KnownMedicationExtract(
            name="Metformin",
            matched_catalog_id="med-metformin",
            strength="500 मि.ग्रा.",
            dosage="500 मि.ग्रा.",
            frequency="दिन में दो बार भोजन के बाद (BID)",
            status="ACTIVE",
            document_id=self.doc_id,
            page_number=2,
            evidence_text="दवा: Metformin 500 मि.ग्रा. दिन में दो बार भोजन के बाद (BID)\nस्थिति: चालू (Active)",
            confidence=0.94,
            review_status="needs_review",
        )

        segments = self.validator.parse_page_segments(self.hindi_document_text)
        outcome = self.validator.validate_single_entity(med, segments)

        self.assertTrue(outcome.is_valid)
        self.assertEqual(outcome.reason, "verified")
        self.assertEqual(outcome.verified_page_number, 2)
        # Latin medication name and Devanagari instructions preserved
        self.assertEqual(med.name, "Metformin")
        self.assertEqual(med.dosage, "500 मि.ग्रा.")
        self.assertEqual(med.frequency, "दिन में दो बार भोजन के बाद (BID)")
        self.assertEqual(med.status, "ACTIVE")

    def test_numeric_values_and_units_retained_correctly(self):
        """Case 9: Numeric values and diverse unit symbols are preserved without alteration."""
        bio1 = KnownBiomarkerExtract(
            name="HbA1c",
            matched_slug="hba1c",
            value=7.2,
            unit_symbol="%",
            document_id=self.doc_id,
            page_number=1,
            evidence_text="एचबीए1सी (HbA1c): 7.2%",
            confidence=0.95,
        )

        segments = self.validator.parse_page_segments(self.hindi_document_text)
        outcome = self.validator.validate_single_entity(bio1, segments)

        self.assertTrue(outcome.is_valid)
        self.assertEqual(bio1.value, 7.2)
        self.assertEqual(bio1.unit_symbol, "%")

    def test_unicode_normalization_handles_combining_characters(self):
        """Normalization handles Devanagari composite glyphs and irregular whitespace gracefully."""
        # Composed vs decomposed string simulation
        composed = "रक्त शर्करा"
        decomposed = normalize_evidence_text("रक्त   \t\n  शर्करा")
        self.assertEqual(normalize_evidence_text(composed), decomposed)


class TestMalformedOutputAndContractCompatibility(unittest.TestCase):
    """Tests for malformed LLM outputs, batch validation, and contract integrity."""

    def setUp(self):
        self.validator = EvidenceValidator()

    def test_malformed_incomplete_llm_output_handled_safely(self):
        """Case 11: Partially populated or incomplete DocumentEntitiesExtract does not crash validator."""
        malformed_doc = DocumentEntitiesExtract(
            document_category="general_report",
            patient_info=PatientInfoExtract(name=None, dob=None, gender=None),
            known_biomarkers=[
                KnownBiomarkerExtract(
                    name="Incomplete Test",
                    matched_slug="unknown",
                    value=50.0,
                    evidence_text=None,  # Missing evidence
                    page_number=None,  # Missing page
                    document_id=None,  # Missing doc
                )
            ],
            unknown_biomarkers=[],
            known_medications=[
                KnownMedicationExtract(
                    name="Incomplete Med",
                    evidence_text="",  # Empty evidence
                    status="ACTIVE",  # Ungrounded status
                )
            ],
            unknown_medications=[],
            diagnoses=[],
            structured_diagnoses=[],
            impressions="Incomplete extraction",
        )

        report = self.validator.validate_document_entities(malformed_doc, cumulative_text="")

        self.assertIsInstance(report, ValidationReport)
        self.assertEqual(report.total_entities, 2)
        self.assertEqual(report.valid_count, 0)
        self.assertEqual(report.flagged_count, 2)
        # Status was cleaned by clinical caution
        self.assertIsNone(malformed_doc.known_medications[0].status)

    def test_compatibility_with_extraction_contract(self):
        """Case 12: Schemas adhere to contracts/EXTRACTION_CONTRACT.md constraints."""
        bio = KnownBiomarkerExtract(
            name="Blood Glucose",
            matched_slug="glucose",
            value=105.0,
            unit_symbol="mg/dL",
            observation_date="2026-05-10",  # ISO date
            page_number=1,
            evidence_text="Blood Glucose: 105 mg/dL",
            confidence=0.9,
            review_status="needs_review",
        )

        self.assertEqual(bio.observation_date, "2026-05-10")
        self.assertEqual(bio.review_status, "needs_review")
        self.assertEqual(bio.page_number, 1)

    def test_batch_validation_synchronizes_diagnoses(self):
        """Batch validation populates flat diagnoses strings from structured_diagnoses."""
        doc_id = str(uuid.uuid4())
        text = f"--- Document {doc_id} | Page 1 ---\nAssessment: Essential Hypertension"

        diag = DiagnosisExtract(
            name="Essential Hypertension",
            page_number=1,
            document_id=doc_id,
            evidence_text="Assessment: Essential Hypertension",
        )

        payload = DocumentEntitiesExtract(
            document_category="clinical_note",
            patient_info=PatientInfoExtract(),
            diagnoses=[],  # Empty flat list
            structured_diagnoses=[diag],
            impressions="Hypertension noted",
        )

        report = self.validator.validate_document_entities(payload, cumulative_text=text)

        self.assertEqual(report.valid_count, 1)
        self.assertEqual(payload.diagnoses, ["Essential Hypertension"])


class TestPhase5BValidatorEnforcementAudit(unittest.TestCase):
    """Phase 5B targeted audit: provenance authority, contradiction detection, and serialization."""

    def setUp(self):
        self.validator = EvidenceValidator()
        self.doc1_id = "11111111-1111-1111-1111-111111111111"
        self.doc2_id = "22222222-2222-2222-2222-222222222222"

        self.cumulative_text = (
            f"--- Document {self.doc1_id} | Page 1 ---\n"
            "Clinical Assessment\n"
            "Fasting Blood Glucose: 99 mg/dL\n"
            "Common Header Note\n\n"
            f"--- Document {self.doc1_id} | Page 2 ---\n"
            "Progress Note\n"
            "HbA1c: 5.6%\n"
            "Common Header Note\n\n"
            f"--- Document {self.doc2_id} | Page 1 ---\n"
            "Cardiology Consult\n"
            "Common Header Note\n"
            "Lipid Panel: Total Cholesterol 180 mg/dL\n"
        )

    # 1. Authoritative Provenance Tests
    def test_plausible_but_nonexistent_document_id(self):
        """Claimed document ID not present in the ingested document index is flagged."""
        nonexistent_id = "99999999-9999-9999-9999-999999999999"
        bio = KnownBiomarkerExtract(
            name="Glucose",
            matched_slug="glucose",
            value=99.0,
            document_id=nonexistent_id,
            page_number=1,
            evidence_text="Fasting Blood Glucose: 99 mg/dL",
        )
        segments = self.validator.parse_page_segments(self.cumulative_text)
        outcome = self.validator.validate_single_entity(bio, segments)

        self.assertFalse(outcome.is_valid)
        self.assertEqual(outcome.reason, "nonexistent_document_id")
        self.assertEqual(bio.review_status, "needs_review")
        self.assertLessEqual(bio.confidence, 0.2)

    def test_identical_evidence_in_two_documents(self):
        """Identical text appearing in two separate documents is flagged as ambiguous across documents."""
        diag = DiagnosisExtract(
            name="Common Note",
            document_id=self.doc1_id,
            page_number=1,
            evidence_text="Common Header Note",
        )
        segments = self.validator.parse_page_segments(self.cumulative_text)
        outcome = self.validator.validate_single_entity(diag, segments)

        self.assertFalse(outcome.is_valid)
        self.assertEqual(outcome.reason, "ambiguous_multi_document")
        self.assertEqual(diag.review_status, "needs_review")
        self.assertLessEqual(diag.confidence, 0.4)

    def test_missing_or_malformed_page_markers(self):
        """Un-chunked text with missing markers creates single segment and rejects out-of-bounds page citations."""
        plain_text = "Fasting Blood Glucose: 95 mg/dL\nNormal findings"
        bio = KnownBiomarkerExtract(
            name="Glucose",
            matched_slug="glucose",
            value=95.0,
            page_number=5,  # Claimed page 5 on a single-page unchunked doc
            evidence_text="Fasting Blood Glucose: 95 mg/dL",
        )
        segments = self.validator.parse_page_segments(plain_text)
        outcome = self.validator.validate_single_entity(bio, segments)

        self.assertFalse(outcome.is_valid)
        self.assertEqual(outcome.reason, "page_mismatch")

    # 2. Clinical Contradictions and Negation Tests
    def test_medication_discontinued_incorrectly_extracted_as_active(self):
        """Medication discontinued in source but extracted as ACTIVE is reset to None and flagged."""
        med = KnownMedicationExtract(
            name="Metformin",
            status="ACTIVE",  # Incorrect extraction
            evidence_text="Medication discontinued: Metformin 500mg BID due to renal insufficiency",
        )
        self.validator.enforce_clinical_caution(med)
        self.assertIsNone(med.status)
        self.assertEqual(med.review_status, "needs_review")
        self.assertLessEqual(med.confidence, 0.3)

    def test_no_evidence_of_hypertension_incorrectly_extracted_as_confirmed(self):
        """Negated condition ('no evidence of...') incorrectly marked confirmed is reset to None and penalized."""
        diag = DiagnosisExtract(
            name="Hypertension",
            verification_status="confirmed",  # Incorrect extraction
            clinical_status="active",
            evidence_text="Patient had 24hr Holter monitoring; no evidence of hypertension found",
        )
        self.validator.enforce_clinical_caution(diag)
        self.assertIsNone(diag.verification_status)
        self.assertIsNone(diag.clinical_status)
        self.assertEqual(diag.review_status, "needs_review")
        self.assertLessEqual(diag.confidence, 0.2)

    def test_differential_diagnosis_incorrectly_marked_confirmed(self):
        """Differential diagnosis marked confirmed is reset to None and flagged."""
        diag = DiagnosisExtract(
            name="Rheumatoid Arthritis",
            verification_status="confirmed",  # Incorrect extraction
            evidence_text="Differential diagnosis: Rheumatoid Arthritis vs Psoriatic Arthritis",
        )
        self.validator.enforce_clinical_caution(diag)
        self.assertIsNone(diag.verification_status)
        self.assertEqual(diag.review_status, "needs_review")
        self.assertLessEqual(diag.confidence, 0.3)

    def test_historical_medication_incorrectly_marked_active(self):
        """Historical / prior medication marked ACTIVE is reset to None and flagged."""
        med = KnownMedicationExtract(
            name="Prednisone",
            status="ACTIVE",  # Incorrect extraction
            evidence_text="Past history of Prednisone 10mg daily 2 years ago, completed course",
        )
        self.validator.enforce_clinical_caution(med)
        self.assertIsNone(med.status)
        self.assertEqual(med.review_status, "needs_review")
        self.assertLessEqual(med.confidence, 0.3)

    def test_status_absent_from_document_remains_none(self):
        """When source contains no status phrasing, status remains None."""
        med = KnownMedicationExtract(
            name="Atorvastatin",
            status="ACTIVE",  # Fabricated
            evidence_text="Atorvastatin 20mg at night",
        )
        self.validator.enforce_clinical_caution(med)
        self.assertIsNone(med.status)

    def test_source_containing_contradictory_statements(self):
        """Contradictory evidence (both continue and stop) resets status and enforces review."""
        med = KnownMedicationExtract(
            name="Aspirin",
            status="ACTIVE",
            evidence_text="Advised to continue Aspirin initially, but subsequently stopped after bleed",
        )
        self.validator.enforce_clinical_caution(med)
        self.assertIsNone(med.status)
        self.assertEqual(med.review_status, "needs_review")

    def test_valid_medication_and_diagnosis_genuinely_supported(self):
        """Genuinely documented active medication and confirmed diagnosis are preserved."""
        med = KnownMedicationExtract(
            name="Metformin",
            status="ACTIVE",
            evidence_text="Patient is currently active on Metformin 500mg daily",
        )
        self.validator.enforce_clinical_caution(med)
        self.assertEqual(med.status, "ACTIVE")

        diag = DiagnosisExtract(
            name="Type 2 Diabetes",
            verification_status="confirmed",
            clinical_status="active",
            evidence_text="Confirmed diagnosis: acute active Type 2 Diabetes",
        )
        self.validator.enforce_clinical_caution(diag)
        self.assertEqual(diag.verification_status, "confirmed")
        self.assertEqual(diag.clinical_status, "active")

    # 3. Bilingual Negation and Contradiction Tests
    def test_hindi_negation_and_discontinuation(self):
        """Hindi negation ('नहीं है') and discontinuation ('बंद') reset ungrounded statuses."""
        diag = DiagnosisExtract(
            name="उच्च रक्तचाप",
            verification_status="confirmed",
            evidence_text="रक्तचाप सामान्य: उच्च रक्तचाप नहीं है (No hypertension)",
        )
        self.validator.enforce_clinical_caution(diag)
        self.assertIsNone(diag.verification_status)

        med = KnownMedicationExtract(
            name="टेल्मिसार्टन",
            status="ACTIVE",
            evidence_text="दवा: टेल्मिसार्टन 40 मि.ग्रा. बंद कर दिया (Stopped)",
        )
        self.validator.enforce_clinical_caution(med)
        self.assertIsNone(med.status)

    # 4. Downstream Serialization & Invariants
    def test_validation_report_counts_invariant(self):
        """Report invariant: total_entities == valid_count + flagged_count."""
        doc_id = str(uuid.uuid4())
        text = f"--- Document {doc_id} | Page 1 ---\nGlucose: 100 mg/dL"

        entities = DocumentEntitiesExtract(
            document_category="lab_report",
            patient_info=PatientInfoExtract(),
            known_biomarkers=[
                KnownBiomarkerExtract(
                    name="Glucose",
                    matched_slug="glucose",
                    value=100.0,
                    document_id=doc_id,
                    page_number=1,
                    evidence_text="Glucose: 100 mg/dL",
                ),
                KnownBiomarkerExtract(
                    name="Hallucinated",
                    matched_slug="hba1c",
                    value=7.0,
                    document_id=doc_id,
                    page_number=1,
                    evidence_text="HbA1c: 7.0%",  # Not in text
                ),
            ],
            impressions="Lab report",
        )
        report = self.validator.validate_document_entities(entities, cumulative_text=text)

        self.assertEqual(report.total_entities, 2)
        self.assertEqual(report.valid_count, 1)
        self.assertEqual(report.flagged_count, 1)
        self.assertEqual(report.total_entities, report.valid_count + report.flagged_count)

    def test_confidence_penalties_survive_serialization(self):
        """Confidence penalties and review status survive Pydantic model serialization."""
        bio = KnownBiomarkerExtract(
            name="Fake",
            matched_slug="fake",
            value=50.0,
            evidence_text="Nonexistent evidence line",
        )
        segments = self.validator.parse_page_segments("Some unrelated text")
        outcome = self.validator.validate_single_entity(bio, segments)

        self.assertFalse(outcome.is_valid)
        self.assertLessEqual(bio.confidence, 0.2)
        self.assertEqual(bio.review_status, "needs_review")

        # Serialize to dict and reload
        dumped = bio.model_dump()
        reloaded = KnownBiomarkerExtract.model_validate(dumped)

        self.assertEqual(reloaded.confidence, bio.confidence)
        self.assertEqual(reloaded.review_status, "needs_review")

    def test_safe_fallback_on_validation_exception(self):
        """Exceptions in validation fail safely without unhandled crashes."""
        class ExplodingEntity:
            @property
            def evidence_text(self):
                raise RuntimeError("Simulated internal error during evaluation")

        broken_entity = ExplodingEntity()
        segments = self.validator.parse_page_segments("Sample text")
        outcome = self.validator.validate_single_entity(broken_entity, segments)

        self.assertFalse(outcome.is_valid)
        self.assertEqual(outcome.reason, "validation_error")


class TestIncrement1NumericAndUnitGroundingGuardrails(unittest.TestCase):
    """Increment 1: Numeric & Unit Grounding Guardrails.

    Verifies that:
    1. Decimal values (5.8 and 5,8) are matched correctly without silently altering text or value.
    2. Contradictory numeric values are flagged with numeric_value_mismatch and penalized.
    3. Unit mismatches (e.g. mg/dL vs g/dL, /uL vs K/uL) are boundary-guarded against substring false positives.
    4. Missing values, ranges, and units pass safely without ungrounded errors.
    5. Bilingual Hindi Devanagari numerals and units are preserved and matched.
    6. Multiple numbers in one snippet distinguish actual result from reference bounds (value_reference_confusion).
    7. Multi-test snippets correctly associate values with the right test and flag multi_test_misassociation.
    8. Acronym numbers (e.g. 1 in HbA1c, 3 in Vitamin D3, 19-9 in CA 19-9) are not confused with result values.
    9. Contradictory reference ranges are caught and flagged.
    """

    def setUp(self):
        self.validator = EvidenceValidator()
        self.doc_id = "44444444-4444-4444-4444-444444444444"

    def test_decimal_values_dot_and_comma_without_altering_meaning(self):
        """1. Correct decimal values such as 5.8 and 5,8 are matched without mutating text or value."""
        text_dot = f"--- Document {self.doc_id} | Page 1 ---\nHbA1c: 5.8%"
        bio_dot = KnownBiomarkerExtract(
            name="HbA1c",
            matched_slug="hba1c",
            value=5.8,
            unit_symbol="%",
            document_id=self.doc_id,
            page_number=1,
            evidence_text="HbA1c: 5.8%",
            confidence=0.95,
        )
        segs_dot = self.validator.parse_page_segments(text_dot)
        outcome_dot = self.validator.validate_single_entity(bio_dot, segs_dot)
        self.assertTrue(outcome_dot.is_valid)
        self.assertEqual(outcome_dot.reason, "verified")
        self.assertEqual(bio_dot.value, 5.8)
        self.assertEqual(bio_dot.evidence_text, "HbA1c: 5.8%")

        # Decimal comma format: "5,8%"
        text_comma = f"--- Document {self.doc_id} | Page 1 ---\nHbA1c: 5,8%"
        bio_comma = KnownBiomarkerExtract(
            name="HbA1c",
            matched_slug="hba1c",
            value=5.8,
            unit_symbol="%",
            document_id=self.doc_id,
            page_number=1,
            evidence_text="HbA1c: 5,8%",
            confidence=0.95,
        )
        segs_comma = self.validator.parse_page_segments(text_comma)
        outcome_comma = self.validator.validate_single_entity(bio_comma, segs_comma)
        self.assertTrue(outcome_comma.is_valid)
        self.assertEqual(outcome_comma.reason, "verified")
        # Ensure neither evidence_text nor numeric value was silently rewritten
        self.assertEqual(bio_comma.value, 5.8)
        self.assertEqual(bio_comma.evidence_text, "HbA1c: 5,8%")

        # European comma in blood count: "14,5 g/dL"
        text_euro = f"--- Document {self.doc_id} | Page 1 ---\nHemoglobin: 14,5 g/dL"
        bio_euro = KnownBiomarkerExtract(
            name="Hemoglobin",
            matched_slug="hemoglobin",
            value=14.5,
            unit_symbol="g/dL",
            document_id=self.doc_id,
            page_number=1,
            evidence_text="Hemoglobin: 14,5 g/dL",
            confidence=0.95,
        )
        segs_euro = self.validator.parse_page_segments(text_euro)
        outcome_euro = self.validator.validate_single_entity(bio_euro, segs_euro)
        self.assertTrue(outcome_euro.is_valid)
        self.assertEqual(bio_euro.value, 14.5)
        self.assertEqual(bio_euro.evidence_text, "Hemoglobin: 14,5 g/dL")

    def test_values_contradicting_source_snippet_flagged_and_penalized(self):
        """2. Contradictory numeric values are flagged with numeric_value_mismatch and penalized."""
        text = f"--- Document {self.doc_id} | Page 1 ---\nHemoglobin: 14.5 g/dL (Reference: 13.0 - 17.0)"
        bio_contradict = KnownBiomarkerExtract(
            name="Hemoglobin",
            matched_slug="hemoglobin",
            value=250.0,  # Contradicts source value of 14.5
            unit_symbol="g/dL",
            document_id=self.doc_id,
            page_number=1,
            evidence_text="Hemoglobin: 14.5 g/dL (Reference: 13.0 - 17.0)",
            confidence=0.9,
            review_status="needs_review",
        )
        segs = self.validator.parse_page_segments(text)
        outcome = self.validator.validate_single_entity(bio_contradict, segs)

        self.assertFalse(outcome.is_valid)
        self.assertEqual(outcome.reason, "numeric_value_mismatch")
        self.assertEqual(bio_contradict.review_status, "needs_review")
        self.assertLessEqual(bio_contradict.confidence, 0.35)
        # Value must not be silently rewritten to match source
        self.assertEqual(bio_contradict.value, 250.0)

    def test_unit_mismatch_boundary_guarded(self):
        """3. Unit mismatches (mg/dL vs g/dL) are boundary-guarded against substring false positives."""
        text = f"--- Document {self.doc_id} | Page 1 ---\nFasting Blood Glucose: 110 mg/dL"
        segs = self.validator.parse_page_segments(text)

        # "g/dL" is a naive substring of "mg/dL", but semantically a 100x unit error!
        bio_mismatch = KnownBiomarkerExtract(
            name="Glucose",
            matched_slug="glucose",
            value=110.0,
            unit_symbol="g/dL",  # Wrong unit!
            document_id=self.doc_id,
            page_number=1,
            evidence_text="Fasting Blood Glucose: 110 mg/dL",
            confidence=0.92,
        )
        outcome = self.validator.validate_single_entity(bio_mismatch, segs)
        self.assertFalse(outcome.is_valid)
        self.assertEqual(outcome.reason, "unit_mismatch")
        self.assertEqual(bio_mismatch.review_status, "needs_review")
        self.assertLessEqual(bio_mismatch.confidence, 0.35)

        # "dL" alone vs "mg/dL"
        bio_dl = KnownBiomarkerExtract(
            name="Glucose",
            matched_slug="glucose",
            value=110.0,
            unit_symbol="dL",  # Volume instead of concentration
            document_id=self.doc_id,
            page_number=1,
            evidence_text="Fasting Blood Glucose: 110 mg/dL",
        )
        outcome_dl = self.validator.validate_single_entity(bio_dl, segs)
        self.assertFalse(outcome_dl.is_valid)
        self.assertEqual(outcome_dl.reason, "unit_mismatch")

        # Correct unit matches
        bio_correct = KnownBiomarkerExtract(
            name="Glucose",
            matched_slug="glucose",
            value=110.0,
            unit_symbol="mg/dL",
            document_id=self.doc_id,
            page_number=1,
            evidence_text="Fasting Blood Glucose: 110 mg/dL",
            confidence=0.92,
        )
        outcome_correct = self.validator.validate_single_entity(bio_correct, segs)
        self.assertTrue(outcome_correct.is_valid)
        self.assertEqual(outcome_correct.reason, "verified")

    def test_missing_values_ranges_and_units_pass_safely(self):
        """4. Missing values, ranges, and units remain None and pass safely."""
        # Unitless ratio observation
        text_ratio = f"--- Document {self.doc_id} | Page 1 ---\nBUN/Creatinine Ratio: 16.5"
        bio_ratio = KnownBiomarkerExtract(
            name="BUN/Creatinine Ratio",
            matched_slug="bun-cr-ratio",
            value=16.5,
            unit_symbol=None,  # Unitless ratio
            reference_range_min=None,
            reference_range_max=None,
            document_id=self.doc_id,
            page_number=1,
            evidence_text="BUN/Creatinine Ratio: 16.5",
        )
        segs_ratio = self.validator.parse_page_segments(text_ratio)
        outcome_ratio = self.validator.validate_single_entity(bio_ratio, segs_ratio)
        self.assertTrue(outcome_ratio.is_valid)
        self.assertEqual(outcome_ratio.reason, "verified")
        self.assertIsNone(bio_ratio.unit_symbol)
        self.assertIsNone(bio_ratio.reference_range_min)

        # Qualitative state observation (value=None, value_state_code="POS")
        text_qual = f"--- Document {self.doc_id} | Page 1 ---\nCOVID-19 Rapid Antigen: Positive"
        bio_qual = KnownBiomarkerExtract(
            name="COVID-19 Rapid Antigen",
            matched_slug="covid-19-antigen",
            value=None,
            value_state_code="POS",
            value_state_display="Positive",
            unit_symbol=None,
            document_id=self.doc_id,
            page_number=1,
            evidence_text="COVID-19 Rapid Antigen: Positive",
        )
        segs_qual = self.validator.parse_page_segments(text_qual)
        outcome_qual = self.validator.validate_single_entity(bio_qual, segs_qual)
        self.assertTrue(outcome_qual.is_valid)
        self.assertEqual(outcome_qual.reason, "verified")

    def test_bilingual_hindi_devanagari_numerals_and_units(self):
        """5. Bilingual Hindi evidence with Devanagari numerals and units is verified."""
        text_hindi = (
            f"--- Document {self.doc_id} | Page 1 ---\n"
            "रक्त शर्करा (Fasting Blood Glucose): १२६ mg/dL (सामान्य: ७० - ९९)\n"
            "एचबीए1सी (HbA1c): ५,८ %\n"
            "दवा: Metformin 500 मि.ग्रा. प्रतिदिन\n"
        )
        segs = self.validator.parse_page_segments(text_hindi)

        # Devanagari numerals: १२६ matches 126.0
        bio_fbg = KnownBiomarkerExtract(
            name="रक्त शर्करा",
            matched_slug="glucose",
            value=126.0,
            unit_symbol="mg/dL",
            document_id=self.doc_id,
            page_number=1,
            evidence_text="रक्त शर्करा (Fasting Blood Glucose): १२६ mg/dL (सामान्य: ७० - ९९)",
        )
        outcome_fbg = self.validator.validate_single_entity(bio_fbg, segs)
        self.assertTrue(outcome_fbg.is_valid)
        self.assertEqual(outcome_fbg.reason, "verified")
        # Evidence text retains Devanagari script without mutation
        self.assertIn("१२६", bio_fbg.evidence_text)

        # Devanagari comma decimal: ५,८ matches 5.8
        bio_hba1c = KnownBiomarkerExtract(
            name="एचबीए1सी",
            matched_slug="hba1c",
            value=5.8,
            unit_symbol="%",
            document_id=self.doc_id,
            page_number=1,
            evidence_text="एचबीए1सी (HbA1c): ५,८ %",
        )
        outcome_hba1c = self.validator.validate_single_entity(bio_hba1c, segs)
        self.assertTrue(outcome_hba1c.is_valid)
        self.assertEqual(outcome_hba1c.reason, "verified")

        # Hindi medication unit equivalence: 500 mg matches "500 मि.ग्रा."
        med = KnownMedicationExtract(
            name="Metformin",
            matched_catalog_id="med-101",
            strength="500 mg",
            document_id=self.doc_id,
            page_number=1,
            evidence_text="दवा: Metformin 500 मि.ग्रा. प्रतिदिन",
        )
        outcome_med = self.validator.validate_single_entity(med, segs)
        self.assertTrue(outcome_med.is_valid)
        self.assertEqual(outcome_med.reason, "verified")

        # Hindi medication strength contradiction
        med_bad = KnownMedicationExtract(
            name="Metformin",
            matched_catalog_id="med-101",
            strength="250 mg",  # Document states 500 मि.ग्रा.
            document_id=self.doc_id,
            page_number=1,
            evidence_text="दवा: Metformin 500 मि.ग्रा. प्रतिदिन",
        )
        outcome_med_bad = self.validator.validate_single_entity(med_bad, segs)
        self.assertFalse(outcome_med_bad.is_valid)
        self.assertEqual(outcome_med_bad.reason, "medication_strength_mismatch")

    def test_multiple_numbers_and_reference_range_confusion(self):
        """6. Multiple numbers in snippet distinguish actual result from reference bounds."""
        text = f"--- Document {self.doc_id} | Page 1 ---\nFasting Blood Glucose: 110 mg/dL (Reference: 70 - 99)"
        segs = self.validator.parse_page_segments(text)

        # Extracted value 70.0 is the lower reference range bound, NOT the test result!
        bio_ref_low = KnownBiomarkerExtract(
            name="Glucose",
            matched_slug="glucose",
            value=70.0,
            unit_symbol="mg/dL",
            document_id=self.doc_id,
            page_number=1,
            evidence_text="Fasting Blood Glucose: 110 mg/dL (Reference: 70 - 99)",
            confidence=0.85,
        )
        outcome_ref_low = self.validator.validate_single_entity(bio_ref_low, segs)
        self.assertFalse(outcome_ref_low.is_valid)
        self.assertEqual(outcome_ref_low.reason, "value_reference_confusion")
        self.assertEqual(bio_ref_low.review_status, "needs_review")
        self.assertLessEqual(bio_ref_low.confidence, 0.35)

        # Extracted value 99.0 is the upper reference range bound
        bio_ref_high = KnownBiomarkerExtract(
            name="Glucose",
            matched_slug="glucose",
            value=99.0,
            unit_symbol="mg/dL",
            document_id=self.doc_id,
            page_number=1,
            evidence_text="Fasting Blood Glucose: 110 mg/dL (Reference: 70 - 99)",
        )
        outcome_ref_high = self.validator.validate_single_entity(bio_ref_high, segs)
        self.assertFalse(outcome_ref_high.is_valid)
        self.assertEqual(outcome_ref_high.reason, "value_reference_confusion")

        # Extracted value 110.0 is the genuine result
        bio_result = KnownBiomarkerExtract(
            name="Glucose",
            matched_slug="glucose",
            value=110.0,
            unit_symbol="mg/dL",
            document_id=self.doc_id,
            page_number=1,
            evidence_text="Fasting Blood Glucose: 110 mg/dL (Reference: 70 - 99)",
            confidence=0.95,
        )
        outcome_result = self.validator.validate_single_entity(bio_result, segs)
        self.assertTrue(outcome_result.is_valid)
        self.assertEqual(outcome_result.reason, "verified")

    def test_multiple_tests_in_one_snippet_association(self):
        """7. Multi-test snippets correctly associate values with the right test."""
        text = f"--- Document {self.doc_id} | Page 1 ---\nGlucose: 110 mg/dL ; Cholesterol: 180 mg/dL"
        segs = self.validator.parse_page_segments(text)

        # Glucose entity claiming 180.0 (the cholesterol value)
        bio_cross = KnownBiomarkerExtract(
            name="Glucose",
            matched_slug="glucose",
            value=180.0,  # Belongs to Cholesterol!
            unit_symbol="mg/dL",
            document_id=self.doc_id,
            page_number=1,
            evidence_text="Glucose: 110 mg/dL ; Cholesterol: 180 mg/dL",
        )
        outcome_cross = self.validator.validate_single_entity(bio_cross, segs)
        self.assertFalse(outcome_cross.is_valid)
        self.assertEqual(outcome_cross.reason, "multi_test_misassociation")
        self.assertEqual(bio_cross.review_status, "needs_review")

        # Glucose entity claiming its correct value 110.0
        bio_correct = KnownBiomarkerExtract(
            name="Glucose",
            matched_slug="glucose",
            value=110.0,
            unit_symbol="mg/dL",
            document_id=self.doc_id,
            page_number=1,
            evidence_text="Glucose: 110 mg/dL ; Cholesterol: 180 mg/dL",
        )
        outcome_correct = self.validator.validate_single_entity(bio_correct, segs)
        self.assertTrue(outcome_correct.is_valid)
        self.assertEqual(outcome_correct.reason, "verified")

        # Multi-pipe snippet with 3 tests
        text_pipe = f"--- Document {self.doc_id} | Page 1 ---\nHemoglobin: 14.5 g/dL | WBC: 6.8 K/uL | Platelets: 250 K/uL"
        segs_pipe = self.validator.parse_page_segments(text_pipe)

        # Hemoglobin claiming Platelets value of 250
        bio_pipe_cross = KnownBiomarkerExtract(
            name="Hemoglobin",
            matched_slug="hemoglobin",
            value=250.0,
            unit_symbol="g/dL",
            document_id=self.doc_id,
            page_number=1,
            evidence_text="Hemoglobin: 14.5 g/dL | WBC: 6.8 K/uL | Platelets: 250 K/uL",
        )
        outcome_pipe_cross = self.validator.validate_single_entity(bio_pipe_cross, segs_pipe)
        self.assertFalse(outcome_pipe_cross.is_valid)
        self.assertEqual(outcome_pipe_cross.reason, "multi_test_misassociation")

    def test_test_acronym_numbers_not_confused_with_values(self):
        """8. Acronym numbers (e.g. 1 in HbA1c, 3 in Vitamin D3) are masked from result values."""
        text = f"--- Document {self.doc_id} | Page 1 ---\nHbA1c: 6.5% (Reference: 4.0 - 5.6%)\nVitamin D3: 32.0 ng/mL"
        segs = self.validator.parse_page_segments(text)

        # Model picking 1 from HbA1c acronym instead of result
        bio_hba1c_acronym = KnownBiomarkerExtract(
            name="HbA1c",
            matched_slug="hba1c",
            value=1.0,
            unit_symbol="%",
            document_id=self.doc_id,
            page_number=1,
            evidence_text="HbA1c: 6.5% (Reference: 4.0 - 5.6%)",
        )
        outcome_hba1c = self.validator.validate_single_entity(bio_hba1c_acronym, segs)
        self.assertFalse(outcome_hba1c.is_valid)
        self.assertEqual(outcome_hba1c.reason, "numeric_value_mismatch")

        # Model picking 3 from Vitamin D3 acronym instead of result
        bio_d3_acronym = KnownBiomarkerExtract(
            name="Vitamin D3",
            matched_slug="vitamin-d",
            value=3.0,
            unit_symbol="ng/mL",
            document_id=self.doc_id,
            page_number=1,
            evidence_text="Vitamin D3: 32.0 ng/mL",
        )
        outcome_d3 = self.validator.validate_single_entity(bio_d3_acronym, segs)
        self.assertFalse(outcome_d3.is_valid)
        self.assertEqual(outcome_d3.reason, "numeric_value_mismatch")

        # Correct Vitamin D3 value 32.0
        bio_d3_correct = KnownBiomarkerExtract(
            name="Vitamin D3",
            matched_slug="vitamin-d",
            value=32.0,
            unit_symbol="ng/mL",
            document_id=self.doc_id,
            page_number=1,
            evidence_text="Vitamin D3: 32.0 ng/mL",
        )
        outcome_d3_correct = self.validator.validate_single_entity(bio_d3_correct, segs)
        self.assertTrue(outcome_d3_correct.is_valid)
        self.assertEqual(outcome_d3_correct.reason, "verified")

    def test_contradictory_reference_range_flagged(self):
        """9. Extracted reference range that contradicts the source snippet is flagged."""
        text = f"--- Document {self.doc_id} | Page 1 ---\nHemoglobin: 14.5 g/dL (Reference: 13.0 - 17.0)"
        segs = self.validator.parse_page_segments(text)

        # Entity claiming a completely wrong reference range
        bio_wrong_ref = KnownBiomarkerExtract(
            name="Hemoglobin",
            matched_slug="hemoglobin",
            value=14.5,
            unit_symbol="g/dL",
            reference_range_min=50.0,  # Contradicts 13.0
            reference_range_max=100.0,  # Contradicts 17.0
            document_id=self.doc_id,
            page_number=1,
            evidence_text="Hemoglobin: 14.5 g/dL (Reference: 13.0 - 17.0)",
        )
        outcome_wrong_ref = self.validator.validate_single_entity(bio_wrong_ref, segs)
        self.assertFalse(outcome_wrong_ref.is_valid)
        self.assertEqual(outcome_wrong_ref.reason, "numeric_value_mismatch")

        # Entity claiming the matching reference range
        bio_good_ref = KnownBiomarkerExtract(
            name="Hemoglobin",
            matched_slug="hemoglobin",
            value=14.5,
            unit_symbol="g/dL",
            reference_range_min=13.0,
            reference_range_max=17.0,
            document_id=self.doc_id,
            page_number=1,
            evidence_text="Hemoglobin: 14.5 g/dL (Reference: 13.0 - 17.0)",
        )
        outcome_good_ref = self.validator.validate_single_entity(bio_good_ref, segs)
        self.assertTrue(outcome_good_ref.is_valid)
        self.assertEqual(outcome_good_ref.reason, "verified")


if __name__ == "__main__":
    unittest.main()

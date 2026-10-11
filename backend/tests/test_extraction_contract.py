"""Focused schema contract validation tests for Person 1 (Extraction Lead).

Verifies the locked Phase 2 extraction data contract:
1. Backward compatibility for legacy extraction payloads.
2. Optionality of new provenance, confidence, and review metadata.
3. Strict bounds validation for confidence scores (0.0 <= c <= 1.0).
4. Distinction between medication strength, dosage, frequency, and duration.
5. Preservation of missing/null clinical values without fabrication.
6. Default 'needs_review' status for unverified extractions.
7. Support for structured diagnoses alongside legacy string lists.

Safe to execute with both `python -m unittest` and `pytest`.
"""

import os
import sys
import unittest

# Ensure backend root is on Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from pydantic import ValidationError

from app.ai.schemas.nlp import (
    DiagnosisExtract,
    DocumentEntitiesExtract,
    KnownBiomarkerExtract,
    KnownMedicationExtract,
    PatientInfoExtract,
    UnknownBiomarkerExtract,
    UnknownMedicationExtract,
    ExaminationMetadataExtract,
)


class TestExtractionContract(unittest.TestCase):
    """Test suite verifying the Phase 2 Extraction Contract."""

    def test_legacy_biomarker_payload_backward_compatibility(self):
        """Legacy payloads without provenance/confidence must remain fully valid."""
        payload = {
            "name": "Serum Glucose",
            "matched_slug": "glucose",
            "value": 98.6,
            "unit_symbol": "mg/dL",
            "reference_range_min": 70.0,
            "reference_range_max": 99.0,
            "interpretation_flag": "Normal",
        }
        bio = KnownBiomarkerExtract(**payload)
        self.assertEqual(bio.name, "Serum Glucose")
        self.assertEqual(bio.value, 98.6)
        self.assertEqual(bio.unit_symbol, "mg/dL")
        # New contract fields must have safe non-breaking defaults
        self.assertIsNone(bio.page_number)
        self.assertIsNone(bio.evidence_text)
        self.assertIsNone(bio.confidence)
        self.assertEqual(bio.review_status, "needs_review")
        self.assertIsNone(bio.document_id)

    def test_state_biomarker_representation(self):
        """Categorical/state observations (e.g. Rapid Strep Positive) are supported."""
        bio = KnownBiomarkerExtract(
            name="Rapid Strep Test",
            matched_slug="strep-a-antigen",
            value_state_code="POS",
            value_state_system="http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation",
            value_state_display="Positive",
            page_number=1,
            evidence_text="Strep A Screen: POSITIVE",
            confidence=0.99,
            review_status="needs_review",
        )
        self.assertIsNone(bio.value)
        self.assertEqual(bio.value_state_code, "POS")
        self.assertEqual(bio.page_number, 1)
        self.assertEqual(bio.confidence, 0.99)

    def test_confidence_score_bounds_validation(self):
        """Confidence score must strictly enforce range [0.0, 1.0]."""
        # Valid boundary values
        bio_0 = KnownBiomarkerExtract(name="Albumin", matched_slug="albumin", value=4.2, confidence=0.0)
        bio_1 = KnownBiomarkerExtract(name="Albumin", matched_slug="albumin", value=4.2, confidence=1.0)
        self.assertEqual(bio_0.confidence, 0.0)
        self.assertEqual(bio_1.confidence, 1.0)

        # Invalid: below 0.0
        with self.assertRaises(ValidationError):
            KnownBiomarkerExtract(name="Albumin", matched_slug="albumin", value=4.2, confidence=-0.05)

        # Invalid: above 1.0
        with self.assertRaises(ValidationError):
            KnownBiomarkerExtract(name="Albumin", matched_slug="albumin", value=4.2, confidence=1.05)

    def test_missing_ranges_and_units_remain_none(self):
        """Missing reference ranges or units must remain None without guessing."""
        bio = KnownBiomarkerExtract(
            name="Custom Research Marker",
            matched_slug="crm-marker",
            value=12.5,
            # unit_symbol omitted
            # reference_range_min / max omitted
        )
        self.assertIsNone(bio.unit_symbol)
        self.assertIsNone(bio.reference_range_min)
        self.assertIsNone(bio.reference_range_max)
        self.assertIsNone(bio.interpretation_flag)

    def test_medication_granularity_and_distinction(self):
        """Medication strength, dose amount, route, frequency, and duration remain distinct."""
        med = KnownMedicationExtract(
            name="Amoxicillin Trihydrate",
            matched_catalog_id="catalog-amox-500",
            dosage="1 capsule",
            strength="500 mg",
            route="oral",
            frequency="three times daily",
            duration="10 days",
            start_date="2026-10-10",
            end_date="2026-10-20",
            reason="Acute Otitis Media",
            page_number=1,
            evidence_text="Rx: Amoxicillin 500mg. Sig: 1 cap PO TID x 10 days for otitis media.",
            confidence=0.96,
            review_status="needs_review",
            document_id="doc-999-uuid",
        )
        self.assertEqual(med.dosage, "1 capsule")
        self.assertEqual(med.strength, "500 mg")
        self.assertEqual(med.route, "oral")
        self.assertEqual(med.frequency, "three times daily")
        self.assertEqual(med.duration, "10 days")
        self.assertEqual(med.review_status, "needs_review")
        self.assertEqual(med.page_number, 1)

    def test_ambiguous_medication_instruction_not_fabricated(self):
        """Ambiguous prescription notes must not fabricate route, dates, or strength."""
        med = KnownMedicationExtract(
            name="Paracetamol",
            dosage="as needed",
            # route, duration, start_date left null
        )
        self.assertIsNone(med.strength)
        self.assertIsNone(med.route)
        self.assertIsNone(med.duration)
        self.assertIsNone(med.start_date)
        self.assertIsNone(med.end_date)
        self.assertEqual(med.dosage, "as needed")

    def test_review_status_defaults_to_needs_review(self):
        """Newly extracted clinical facts must default to 'needs_review'."""
        bio = KnownBiomarkerExtract(name="Potassium", matched_slug="potassium", value=4.1)
        med = KnownMedicationExtract(name="Lisinopril")
        diag = DiagnosisExtract(name="Essential Hypertension")

        self.assertEqual(bio.review_status, "needs_review")
        self.assertEqual(med.review_status, "needs_review")
        self.assertEqual(diag.review_status, "needs_review")

    def test_structured_diagnosis_and_backward_compatible_list(self):
        """DocumentEntitiesExtract supports both legacy string list and structured diagnoses."""
        diag_struct = DiagnosisExtract(
            name="Type 2 Diabetes Mellitus without complications",
            icd10_code="E11.9",
            clinical_status="active",
            verification_status="confirmed",
            page_number=2,
            evidence_text="Assessment: T2DM, stable on Metformin",
            confidence=0.94,
        )

        entities = DocumentEntitiesExtract(
            document_category="Discharge Summary",
            patient_info=PatientInfoExtract(name="John Doe", dob="1980-05-15", gender="MALE"),
            known_biomarkers=[],
            unknown_biomarkers=[],
            known_medications=[],
            unknown_medications=[],
            diagnoses=["Type 2 Diabetes Mellitus without complications"],
            structured_diagnoses=[diag_struct],
            impressions="Patient discharged in stable condition.",
        )

        # Legacy consumers using entities.diagnoses (list of str) succeed
        self.assertEqual(entities.diagnoses, ["Type 2 Diabetes Mellitus without complications"])
        # New consumers using entities.structured_diagnoses succeed
        self.assertEqual(len(entities.structured_diagnoses), 1)
        self.assertEqual(entities.structured_diagnoses[0].icd10_code, "E11.9")
        self.assertEqual(entities.structured_diagnoses[0].verification_status, "confirmed")

    def test_examination_metadata_extended_fields(self):
        """ExaminationMetadataExtract distinguishes document date from exam date."""
        meta = ExaminationMetadataExtract(
            examination_date="2026-10-08",
            document_date="2026-10-09",
            document_type="lab_report",
            page_count=3,
            doctor_names=["Dr. Sharma"],
            category="endocrinology",
            clinical_notes="Follow-up glycemic evaluation.",
        )
        self.assertEqual(meta.examination_date, "2026-10-08")
        self.assertEqual(meta.document_date, "2026-10-09")
        self.assertEqual(meta.document_type, "lab_report")
        self.assertEqual(meta.page_count, 3)

    def test_medication_status_unstated_remains_none(self):
        """A medication mentioned in a document must not automatically be presumed active."""
        med_known = KnownMedicationExtract(name="Metformin")
        med_unknown = UnknownMedicationExtract(raw_name="Uncataloged Medicine")

        self.assertIsNone(med_known.status)
        self.assertIsNone(med_unknown.status)

    def test_medication_status_explicit_and_discontinued_preserved(self):
        """Explicitly documented medication statuses (e.g. DISCONTINUED, STOPPED, ACTIVE) are preserved."""
        med_stopped = KnownMedicationExtract(name="Warfarin", status="DISCONTINUED")
        med_active = UnknownMedicationExtract(raw_name="Lisinopril", status="ACTIVE")

        self.assertEqual(med_stopped.status, "DISCONTINUED")
        self.assertEqual(med_active.status, "ACTIVE")

    def test_diagnosis_status_unstated_remains_none(self):
        """A diagnosis extracted from a document must not automatically be presumed confirmed or active."""
        diag = DiagnosisExtract(name="Abdominal pain")
        self.assertIsNone(diag.clinical_status)
        self.assertIsNone(diag.verification_status)
        # Review status defaults to needs_review, independent of clinical verification
        self.assertEqual(diag.review_status, "needs_review")

    def test_diagnosis_status_explicit_preserved(self):
        """Explicitly stated clinical_status and verification_status are preserved verbatim."""
        diag_prov = DiagnosisExtract(
            name="Suspected Pneumonia",
            clinical_status="active",
            verification_status="provisional",
        )
        self.assertEqual(diag_prov.clinical_status, "active")
        self.assertEqual(diag_prov.verification_status, "provisional")

        diag_res = DiagnosisExtract(
            name="Acute Appendicitis",
            clinical_status="resolved",
            verification_status="confirmed",
        )
        self.assertEqual(diag_res.clinical_status, "resolved")
        self.assertEqual(diag_res.verification_status, "confirmed")

    def test_date_validation_iso_format_accepted(self):
        """Valid ISO YYYY-MM-DD dates are accepted across all date fields."""
        bio = KnownBiomarkerExtract(
            name="HbA1c", matched_slug="hba1c", value=5.7, observation_date="2026-10-10"
        )
        med = KnownMedicationExtract(
            name="Amoxicillin", start_date="2026-10-01", end_date="2026-10-11"
        )
        meta = ExaminationMetadataExtract(
            examination_date="2026-09-30", document_date="2026-10-02"
        )
        self.assertEqual(bio.observation_date, "2026-10-10")
        self.assertEqual(med.start_date, "2026-10-01")
        self.assertEqual(med.end_date, "2026-10-11")
        self.assertEqual(meta.examination_date, "2026-09-30")
        self.assertEqual(meta.document_date, "2026-10-02")

    def test_date_validation_invalid_formats_and_calendar_rejected(self):
        """Malformed date strings or invalid calendar dates raise ValidationError."""
        invalid_dates = ["2026/10/10", "10-10-2026", "2026-02-30", "2026-13-01", "not-a-date", ""]

        for bad in invalid_dates:
            with self.assertRaises(ValidationError, msg=f"Should reject {bad} on KnownBiomarkerExtract"):
                KnownBiomarkerExtract(name="Glucose", matched_slug="glucose", value=90.0, observation_date=bad)

            with self.assertRaises(ValidationError, msg=f"Should reject {bad} on KnownMedicationExtract start_date"):
                KnownMedicationExtract(name="Aspirin", start_date=bad)

            with self.assertRaises(ValidationError, msg=f"Should reject {bad} on ExaminationMetadataExtract"):
                ExaminationMetadataExtract(examination_date=bad)

    def test_missing_dates_remain_none(self):
        """Missing or omitted dates must remain None without fabricating a value."""
        bio = KnownBiomarkerExtract(name="Urea", matched_slug="urea", value=20.0)
        med = KnownMedicationExtract(name="Aspirin")
        meta = ExaminationMetadataExtract()

        self.assertIsNone(bio.observation_date)
        self.assertIsNone(med.start_date)
        self.assertIsNone(med.end_date)
        self.assertIsNone(meta.examination_date)
        self.assertIsNone(meta.document_date)

    def test_page_number_and_page_count_bounds_validation(self):
        """Page numbers and page count must be >= 1 (1-based positive integers)."""
        bio_valid = KnownBiomarkerExtract(name="Glucose", matched_slug="glucose", value=90.0, page_number=1)
        self.assertEqual(bio_valid.page_number, 1)

        for invalid_page in [0, -1, -5]:
            with self.assertRaises(ValidationError):
                KnownBiomarkerExtract(name="Glucose", matched_slug="glucose", value=90.0, page_number=invalid_page)
            with self.assertRaises(ValidationError):
                KnownMedicationExtract(name="Aspirin", page_number=invalid_page)
            with self.assertRaises(ValidationError):
                DiagnosisExtract(name="Asthma", page_number=invalid_page)
            with self.assertRaises(ValidationError):
                ExaminationMetadataExtract(page_count=invalid_page)

    def test_high_confidence_does_not_alter_review_status(self):
        """A confidence score (even 1.0) must never automatically transition review_status to accepted."""
        bio = KnownBiomarkerExtract(
            name="Sodium", matched_slug="sodium", value=140.0, confidence=1.0
        )
        med = KnownMedicationExtract(name="Amlodipine", confidence=0.99)
        diag = DiagnosisExtract(name="Hypertension", confidence=1.0)

        self.assertEqual(bio.review_status, "needs_review")
        self.assertEqual(med.review_status, "needs_review")
        self.assertEqual(diag.review_status, "needs_review")

    def test_mutable_defaults_do_not_leak_state(self):
        """Entities instantiated with default lists must not share state between instances."""
        doc1 = DocumentEntitiesExtract(
            document_category="Lab",
            patient_info=PatientInfoExtract(name="Patient A"),
            impressions="Impression A",
        )
        doc2 = DocumentEntitiesExtract(
            document_category="Rx",
            patient_info=PatientInfoExtract(name="Patient B"),
            impressions="Impression B",
        )

        doc1.diagnoses.append("Condition X")
        doc1.known_biomarkers.append(
            KnownBiomarkerExtract(name="Calcium", matched_slug="calcium", value=9.5)
        )

        self.assertEqual(len(doc1.diagnoses), 1)
        self.assertEqual(len(doc1.known_biomarkers), 1)
        self.assertEqual(len(doc2.diagnoses), 0)
        self.assertEqual(len(doc2.known_biomarkers), 0)

    def test_unknown_biomarker_optional_unit_and_observation_date(self):
        """UnknownBiomarkerExtract supports optional unit and observation_date validation."""
        bio = UnknownBiomarkerExtract(
            raw_name="Novel Peptide",
            value=15.4,
            observation_date="2026-10-10",
            # unit_symbol omitted
        )
        self.assertEqual(bio.value, 15.4)
        self.assertIsNone(bio.unit_symbol)
        self.assertEqual(bio.observation_date, "2026-10-10")
        self.assertEqual(bio.review_status, "needs_review")


if __name__ == "__main__":
    unittest.main()

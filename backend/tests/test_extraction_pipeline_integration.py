"""Integration tests for Phase 6 extraction pipeline integration verification.

Validates the full orchestration across:
- OCR document consolidation and page markers
- MedicalProcessingService.run_extraction_pipeline()
- EvidenceValidator.validate_document_entities()
- Pass 2 ontology processing
- Downstream persistence handoff
- Multi-document overlapping text attribution
"""

import datetime
import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import uuid

# Ensure backend root is on Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Provide hermetic stubs for heavy or circular worker dependencies in non-docker test environment
for _stub_mod in ("langchain_openai", "celery", "celery.utils", "celery.utils.log", "app.workers.task_logger"):
    if _stub_mod not in sys.modules:
        sys.modules[_stub_mod] = MagicMock()

from app.ai.pipeline.evidence_validator import (
    EvidenceValidator,
    PageSegment,
    ValidationOutcome,
    ValidationReport,
)
from app.ai.pipeline.service import MedicalProcessingService
from app.ai.schemas.nlp import (
    DiagnosisExtract,
    DocumentEntitiesExtract,
    KnownBiomarkerExtract,
    KnownMedicationExtract,
    PatientInfoExtract,
    UnknownBiomarkerExtract,
    UnknownMedicationExtract,
)
from app.models.document_model import DocumentModel
from app.models.examination_model import ExaminationModel


class TestServicePipelineOrchestration(unittest.IsolatedAsyncioTestCase):
    """Verifies that MedicalProcessingService executes evidence validation before Pass 2 and persistence."""

    async def asyncSetUp(self):
        self.exam_id = uuid.uuid4()
        self.doc1_id = uuid.uuid4()
        self.tenant_id = uuid.uuid4()

        # Synthetic Examination model
        self.mock_exam = ExaminationModel(
            id=self.exam_id,
            tenant_id=self.tenant_id,
            examination_date=datetime.date(2026, 6, 15),
            auto_extract_metadata=False,
            diagnoses=[],
            impressions="",
        )

        # Synthetic Document with section markers
        self.doc1_text = (
            f"--- Document {self.doc1_id} | Page 1 ---\n"
            "Clinical Laboratory Report\n"
            "Fasting Blood Glucose: 110 mg/dL (Reference: 70 - 99)\n\n"
            f"--- Document {self.doc1_id} | Page 2 ---\n"
            "Physician Progress Note\n"
            "Prescription: Metformin discontinued due to nausea\n"
            "Assessment: 24hr Holter normal, no evidence of hypertension found\n"
        )
        self.mock_doc1 = DocumentModel(
            id=self.doc1_id,
            examination_id=self.exam_id,
            tenant_id=self.tenant_id,
            extracted_text=self.doc1_text,
            include_in_extraction=True,
            status="completed",
        )

    async def test_run_extraction_pipeline_executes_evidence_validation_before_pass2_and_persistence(self):
        """Verify the exact execution sequence: Pass 1 -> Evidence Validation -> Pass 2 -> Persistence."""
        mock_db = AsyncMock()

        # Mock DB queries
        def mock_execute(query, *args, **kwargs):
            q_str = str(query).lower()
            res = MagicMock()
            if "from examinations" in q_str:
                res.scalar_one_or_none.return_value = self.mock_exam
                res.scalars.return_value.all.return_value = [self.mock_exam]
            elif "from documents" in q_str:
                res.scalars.return_value.all.return_value = [self.mock_doc1]
            elif "from biomarker_definitions" in q_str or "from fhir_medications" in q_str:
                res.scalars.return_value.all.return_value = []
            else:
                res.scalar_one_or_none.return_value = None
                res.scalars.return_value.all.return_value = []
            return res

        mock_db.execute.side_effect = mock_execute
        mock_db.commit = AsyncMock()
        mock_db.flush = AsyncMock()
        mock_db.refresh = AsyncMock()

        # Mock TaskLogger and TaskProgressTracker
        mock_task_logger = AsyncMock()
        mock_progress_tracker = AsyncMock()

        # Mock Pass 1 LLM response with one grounded item and two contradictory items
        pass1_entities = DocumentEntitiesExtract(
            document_category="general_report",
            patient_info=PatientInfoExtract(),
            known_biomarkers=[
                KnownBiomarkerExtract(
                    name="Glucose",
                    matched_slug="glucose",
                    value=110.0,
                    unit_symbol="mg/dL",
                    document_id=str(self.doc1_id),
                    page_number=1,
                    evidence_text="Fasting Blood Glucose: 110 mg/dL (Reference: 70 - 99)",
                    confidence=0.95,
                    review_status="needs_review",
                )
            ],
            unknown_biomarkers=[
                UnknownBiomarkerExtract(
                    raw_name="Troponin",
                    value=0.05,
                    unit_symbol="ng/mL",
                    document_id=str(self.doc1_id),
                    page_number=1,
                    evidence_text="Troponin I elevated at 0.05 ng/mL",  # Hallucinated evidence not in doc
                    confidence=0.9,
                )
            ],
            known_medications=[
                KnownMedicationExtract(
                    name="Metformin",
                    matched_catalog_id="med-101",
                    status="ACTIVE",  # Model falsely extracted active despite discontinuation
                    document_id=str(self.doc1_id),
                    page_number=2,
                    evidence_text="Prescription: Metformin discontinued due to nausea",
                )
            ],
            unknown_medications=[],
            diagnoses=[],
            structured_diagnoses=[
                DiagnosisExtract(
                    name="Hypertension",
                    verification_status="confirmed",  # Model falsely extracted confirmed despite negation
                    document_id=str(self.doc1_id),
                    page_number=2,
                    evidence_text="Assessment: 24hr Holter normal, no evidence of hypertension found",
                )
            ],
            impressions="Clinical evaluation completed",
        )

        mock_nlp_extractor = AsyncMock()
        mock_nlp_extractor.parse_document_pass_1.return_value = pass1_entities

        service = MedicalProcessingService(mock_db)
        service.get_clinical_context = AsyncMock(
            return_value={"reference_data": {}, "biomarker_catalog": [], "medication_catalog": []}
        )
        service.ai_provider_service.get_nlp_extractor = AsyncMock(return_value=mock_nlp_extractor)

        # Mock delegates
        service._process_unknown_biomarkers = AsyncMock()
        service._process_unknown_medications = AsyncMock()
        persisted_data_capture = []

        async def capture_persist(exam, parsed_data, docs_with_text, slug_map, med_name_map):
            persisted_data_capture.append(parsed_data)

        service._persist_results = capture_persist

        # Execute the orchestrator
        result = await service.run_extraction_pipeline(
            self.exam_id, mock_task_logger, mock_progress_tracker
        )

        self.assertEqual(result["status"], "completed")

        # 1. Assert Evidence Validation was logged in progress
        validation_logged = False
        for call_item in mock_task_logger.log_progress.call_args_list:
            if call_item.args and call_item.args[0] == "evidence_validation_completed":
                validation_logged = True
                self.assertEqual(call_item.kwargs.get("valid_count"), 3)  # Glucose, Metformin, Diag have valid text provenance
                self.assertEqual(call_item.kwargs.get("flagged_count"), 1)  # Hallucinated Troponin flagged
        self.assertTrue(validation_logged, "Evidence validation progress was not logged")

        # 2. Assert that the persisted entities retained validation enforcement
        self.assertEqual(len(persisted_data_capture), 1)
        persisted_entities = persisted_data_capture[0]

        # Valid lab: retained provenance and evidence
        bio = persisted_entities.known_biomarkers[0]
        self.assertEqual(bio.name, "Glucose")
        self.assertEqual(bio.page_number, 1)
        self.assertEqual(bio.document_id, str(self.doc1_id))
        self.assertEqual(bio.review_status, "needs_review")

        # Hallucinated biomarker: confidence penalized downward and needs_review
        troponin = persisted_entities.unknown_biomarkers[0]
        self.assertEqual(troponin.raw_name, "Troponin")
        self.assertLessEqual(troponin.confidence, 0.4)
        self.assertEqual(troponin.review_status, "needs_review")

        # Contradicted medication: ACTIVE status was reset to None
        med = persisted_entities.known_medications[0]
        self.assertEqual(med.name, "Metformin")
        self.assertIsNone(med.status, "Discontinued medication status was not reset to None")
        self.assertEqual(med.review_status, "needs_review")

        # Negated diagnosis: confirmed status was reset to None
        diag = persisted_entities.structured_diagnoses[0]
        self.assertEqual(diag.name, "Hypertension")
        self.assertIsNone(diag.verification_status, "Negated diagnosis verification status was not reset to None")
        self.assertEqual(diag.review_status, "needs_review")


class TestDownstreamTransformationsAndSafety(unittest.TestCase):
    """Tests the 12 Phase 6 downstream transformation and invariant cases."""

    def setUp(self):
        self.validator = EvidenceValidator()
        self.doc_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        self.sample_text = (
            f"--- Document {self.doc_id} | Page 1 ---\n"
            "Complete Blood Count\n"
            "Hemoglobin: 14.2 g/dL\n"
            "Rx: Metformin discontinued\n"
            "Assessment: no evidence of hypertension\n"
        )

    def test_case_1_grounded_lab_retains_evidence_and_provenance(self):
        """Case 1: Grounded laboratory result retains evidence and source provenance."""
        bio = KnownBiomarkerExtract(
            name="Hemoglobin",
            matched_slug="hemoglobin",
            value=14.2,
            unit_symbol="g/dL",
            document_id=self.doc_id,
            page_number=1,
            evidence_text="Hemoglobin: 14.2 g/dL",
            confidence=0.95,
            review_status="needs_review",
        )
        segments = self.validator.parse_page_segments(self.sample_text)
        outcome = self.validator.validate_single_entity(bio, segments)

        self.assertTrue(outcome.is_valid)
        self.assertEqual(outcome.reason, "verified")
        self.assertEqual(bio.document_id, self.doc_id)
        self.assertEqual(bio.page_number, 1)
        self.assertEqual(bio.evidence_text, "Hemoglobin: 14.2 g/dL")

    def test_case_2_hallucinated_lab_value_flagged_cannot_become_trusted(self):
        """Case 2: Hallucinated laboratory value is flagged and cannot become a trusted fact."""
        bio = KnownBiomarkerExtract(
            name="Platelets",
            matched_slug="platelets",
            value=350.0,
            unit_symbol="K/uL",
            document_id=self.doc_id,
            page_number=1,
            evidence_text="Platelets: 350 K/uL (Elevated)",  # Hallucinated
            confidence=0.9,
            review_status="needs_review",
        )
        segments = self.validator.parse_page_segments(self.sample_text)
        outcome = self.validator.validate_single_entity(bio, segments)

        self.assertFalse(outcome.is_valid)
        self.assertEqual(outcome.reason, "hallucinated_evidence")
        self.assertLessEqual(bio.confidence, 0.2)
        self.assertEqual(bio.review_status, "needs_review")

    def test_case_3_discontinued_medication_marked_active_reset(self):
        """Case 3: Medication marked active despite explicit discontinuation remains conservative."""
        med = KnownMedicationExtract(
            name="Metformin",
            status="ACTIVE",
            evidence_text="Rx: Metformin discontinued",
        )
        self.validator.enforce_clinical_caution(med)
        self.assertIsNone(med.status)
        self.assertEqual(med.review_status, "needs_review")

    def test_case_4_negated_diagnosis_cannot_become_confirmed(self):
        """Case 4: Negated diagnosis cannot silently become confirmed."""
        diag = DiagnosisExtract(
            name="Hypertension",
            verification_status="confirmed",
            clinical_status="active",
            evidence_text="Assessment: no evidence of hypertension",
        )
        self.validator.enforce_clinical_caution(diag)
        self.assertIsNone(diag.verification_status)
        self.assertIsNone(diag.clinical_status)
        self.assertEqual(diag.review_status, "needs_review")

    def test_case_5_nonexistent_document_id_rejected(self):
        """Case 5: Nonexistent document ID cannot be accepted as valid provenance."""
        bio = KnownBiomarkerExtract(
            name="Hemoglobin",
            matched_slug="hemoglobin",
            value=14.2,
            document_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",  # Nonexistent
            page_number=1,
            evidence_text="Hemoglobin: 14.2 g/dL",
        )
        segments = self.validator.parse_page_segments(self.sample_text)
        outcome = self.validator.validate_single_entity(bio, segments)

        self.assertFalse(outcome.is_valid)
        self.assertEqual(outcome.reason, "nonexistent_document_id")

    def test_case_6_ambiguous_page_citation_remains_flagged(self):
        """Case 6: Ambiguous / mismatched page citation remains flagged."""
        bio = KnownBiomarkerExtract(
            name="Hemoglobin",
            matched_slug="hemoglobin",
            value=14.2,
            document_id=self.doc_id,
            page_number=3,  # Page 3 does not exist (sample only has page 1)
            evidence_text="Hemoglobin: 14.2 g/dL",
        )
        segments = self.validator.parse_page_segments(self.sample_text)
        outcome = self.validator.validate_single_entity(bio, segments)

        self.assertFalse(outcome.is_valid)
        self.assertEqual(outcome.reason, "page_mismatch")

    def test_case_7_missing_units_dates_and_statuses_remain_unknown(self):
        """Case 7: Missing units, dates, and statuses remain unknown."""
        bio = KnownBiomarkerExtract(
            name="Ratio",
            matched_slug="ratio",
            value=1.5,
            unit_symbol=None,
            observation_date=None,
        )
        self.assertIsNone(bio.unit_symbol)
        self.assertIsNone(bio.observation_date)

        med = KnownMedicationExtract(name="Drug", status=None, frequency=None)
        self.assertIsNone(med.status)
        self.assertIsNone(med.frequency)

    def test_case_8_hindi_and_mixed_language_evidence_preserved_verbatim(self):
        """Case 8: Hindi and mixed-language evidence remains in original source wording."""
        hindi_text = (
            f"--- Document {self.doc_id} | Page 1 ---\n"
            "रक्त शर्करा (Fasting Blood Sugar): 115 mg/dL\n"
            "दवा: Metformin 500 मि.ग्रा. प्रतिदिन\n"
        )
        bio = KnownBiomarkerExtract(
            name="रक्त शर्करा",
            matched_slug="glucose",
            value=115.0,
            unit_symbol="mg/dL",
            document_id=self.doc_id,
            page_number=1,
            evidence_text="रक्त शर्करा (Fasting Blood Sugar): 115 mg/dL",
        )
        segments = self.validator.parse_page_segments(hindi_text)
        outcome = self.validator.validate_single_entity(bio, segments)

        self.assertTrue(outcome.is_valid)
        self.assertEqual(bio.name, "रक्त शर्करा")
        self.assertEqual(bio.evidence_text, "रक्त शर्करा (Fasting Blood Sugar): 115 mg/dL")

    def test_case_9_malformed_pass1_output_fails_safely(self):
        """Case 9: Malformed Pass 1 output fails safely without unhandled crashes."""
        malformed = DocumentEntitiesExtract(
            document_category="note",
            patient_info=PatientInfoExtract(),
            known_biomarkers=[
                KnownBiomarkerExtract(
                    name="Missing Details",
                    matched_slug="unknown",
                    value=10.0,
                    evidence_text=None,
                )
            ],
            impressions="",
        )
        report = self.validator.validate_document_entities(malformed, cumulative_text="")
        self.assertEqual(report.total_entities, 1)
        self.assertEqual(report.valid_count, 0)
        self.assertEqual(report.flagged_count, 1)

    def test_case_10_validation_exception_does_not_trigger_unvalidated_fallback(self):
        """Case 10: Validation exceptions fail safely to flagged state."""
        class ExplodingEntity:
            @property
            def evidence_text(self):
                raise RuntimeError("Hardware/memory error")

        outcome = self.validator.validate_single_entity(ExplodingEntity(), [])
        self.assertFalse(outcome.is_valid)
        self.assertEqual(outcome.reason, "validation_error")

    def test_case_11_serialization_preserves_review_states_and_penalties(self):
        """Case 11: Serialization and DTO reconstruction preserve review states and confidence penalties."""
        bio = KnownBiomarkerExtract(
            name="Test",
            matched_slug="test",
            value=10.0,
            confidence=0.2,
            review_status="needs_review",
            document_id=self.doc_id,
            page_number=1,
        )
        dumped = bio.model_dump()
        restored = KnownBiomarkerExtract.model_validate(dumped)

        self.assertEqual(restored.confidence, 0.2)
        self.assertEqual(restored.review_status, "needs_review")

    def test_case_12_validation_report_counts_match_actual_entities(self):
        """Case 12: Validation report counts match total == valid + flagged."""
        payload = DocumentEntitiesExtract(
            document_category="report",
            patient_info=PatientInfoExtract(),
            known_biomarkers=[
                KnownBiomarkerExtract(
                    name="Hemoglobin",
                    matched_slug="hemoglobin",
                    value=14.2,
                    document_id=self.doc_id,
                    page_number=1,
                    evidence_text="Hemoglobin: 14.2 g/dL",
                ),
                KnownBiomarkerExtract(
                    name="Hallucinated",
                    matched_slug="hba1c",
                    value=5.0,
                    evidence_text="Not in document",
                ),
            ],
            impressions="Summary",
        )
        report = self.validator.validate_document_entities(payload, cumulative_text=self.sample_text)
        self.assertEqual(report.total_entities, 2)
        self.assertEqual(report.valid_count, 1)
        self.assertEqual(report.flagged_count, 1)
        self.assertEqual(report.total_entities, report.valid_count + report.flagged_count)


class TestCorpusAttributionWithOverlappingText(unittest.TestCase):
    """Verifies provenance against multi-document corpora with overlapping text."""

    def setUp(self):
        self.validator = EvidenceValidator()
        self.doc1_id = "11111111-1111-1111-1111-111111111111"
        self.doc2_id = "22222222-2222-2222-2222-222222222222"

        self.multi_doc_corpus = (
            f"--- Document {self.doc1_id} | Page 1 ---\n"
            "Report: Annual Physical\n"
            "Clinic Name: Apollo Health Center\n"
            "Pulse: 72 bpm\n\n"
            f"--- Document {self.doc1_id} | Page 2 ---\n"
            "Laboratory Addendum\n"
            "Clinic Name: Apollo Health Center\n"
            "Fasting Glucose: 95 mg/dL\n\n"
            f"--- Document {self.doc2_id} | Page 1 ---\n"
            "Hospital Discharge Summary\n"
            "Clinic Name: Apollo Health Center\n"
            "Cardiac Troponin: Negative\n"
        )

    def test_identical_text_across_documents_flagged_conservatively(self):
        """Text appearing across multiple documents is flagged as ambiguous_multi_document."""
        diag = DiagnosisExtract(
            name="Apollo Note",
            document_id=self.doc1_id,
            page_number=1,
            evidence_text="Clinic Name: Apollo Health Center",
        )
        segments = self.validator.parse_page_segments(self.multi_doc_corpus)
        outcome = self.validator.validate_single_entity(diag, segments)

        self.assertFalse(outcome.is_valid)
        self.assertEqual(outcome.reason, "ambiguous_multi_document")
        self.assertEqual(diag.review_status, "needs_review")

    def test_identical_text_across_pages_in_same_document_flagged(self):
        """Text appearing on multiple pages within the same document is flagged as ambiguous_multi_page."""
        corpus = (
            f"--- Document {self.doc1_id} | Page 1 ---\n"
            "Status: Stable\n\n"
            f"--- Document {self.doc1_id} | Page 2 ---\n"
            "Status: Stable\n"
        )
        diag = DiagnosisExtract(
            name="Stability",
            document_id=self.doc1_id,
            page_number=1,
            evidence_text="Status: Stable",
        )
        segments = self.validator.parse_page_segments(corpus)
        outcome = self.validator.validate_single_entity(diag, segments)

        self.assertFalse(outcome.is_valid)
        self.assertEqual(outcome.reason, "ambiguous_multi_page")
        self.assertEqual(diag.review_status, "needs_review")

    def test_evidence_only_in_doc2_cannot_be_attributed_to_doc1(self):
        """Evidence present only in Doc 2 cannot be attributed to Doc 1."""
        bio = KnownBiomarkerExtract(
            name="Troponin",
            matched_slug="troponin",
            value=None,
            value_state_code="NEG",
            document_id=self.doc1_id,  # Claims Doc 1, but Troponin is ONLY in Doc 2
            page_number=1,
            evidence_text="Cardiac Troponin: Negative",
        )
        segments = self.validator.parse_page_segments(self.multi_doc_corpus)
        outcome = self.validator.validate_single_entity(bio, segments)

        self.assertFalse(outcome.is_valid)
        self.assertEqual(outcome.reason, "cross_document_misattribution")
        self.assertEqual(bio.document_id, self.doc1_id)

    def test_missing_page_markers_does_not_invent_provenance(self):
        """Un-chunked text without page markers attributes to single segment and flags out-of-range page."""
        plain = "Fasting Blood Sugar: 100 mg/dL"
        bio = KnownBiomarkerExtract(
            name="FBS",
            matched_slug="glucose",
            value=100.0,
            page_number=2,  # Claims page 2 on un-chunked 1-page text
            evidence_text="Fasting Blood Sugar: 100 mg/dL",
        )
        segments = self.validator.parse_page_segments(plain)
        outcome = self.validator.validate_single_entity(bio, segments)

        self.assertFalse(outcome.is_valid)
        self.assertEqual(outcome.reason, "page_mismatch")


if __name__ == "__main__":
    unittest.main()

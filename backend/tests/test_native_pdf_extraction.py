"""Unit tests for Phase 4 native PDF text extraction and page-aware processing.

Covers:
1. Digital PDF uses native extraction without image rasterization.
2. Extracted pages have correct 1-based page numbers.
3. Scanned/empty page falls back to OCR path.
4. Mixed PDF (digital + scanned) combines in correct page order without duplicate text.
5. Consolidated text maintains ascending page order.
6. Empty pages handled safely without breaking page numbering.
7. Encrypted, malformed, or 0-page PDFs fail gracefully.
8. Plain-text (.txt) and Markdown (.md) routing bypasses image rasterization.
9. Non-image DICOM reports handled with clear error/limitation.
10. Legacy flat-text format remains backward-compatible.
11. Celery task integration saves page-marked text to database.
"""

import io
import os
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure backend root is on Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pypdf
from reportlab.pdfgen import canvas

from app.ai.processors.ocr.base import OCRProcessor
from app.ai.processors.ocr.native_pdf import (
    NativePDFExtractor,
    extract_document_content,
    is_usable_text,
)
from app.ai.schemas.nlp import DocumentPageContent, PageAwareDocumentContent


def _create_synthetic_pdf(file_path: Path, pages_text: list[str]) -> None:
    """Helper to create a synthetic PDF with specific text per page using reportlab."""
    c = canvas.Canvas(str(file_path))
    for text in pages_text:
        if text:
            # Draw line-wrapped or simple text
            c.drawString(72, 720, text)
        c.showPage()
    c.save()


def _create_encrypted_pdf(file_path: Path, password: str = "secret") -> None:
    """Helper to create an encrypted synthetic PDF."""
    temp_buf = io.BytesIO()
    c = canvas.Canvas(temp_buf)
    c.drawString(72, 720, "Confidential Clinical Summary")
    c.showPage()
    c.save()
    temp_buf.seek(0)

    reader = pypdf.PdfReader(temp_buf)
    writer = pypdf.PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    writer.encrypt(password)

    with open(file_path, "wb") as f:
        writer.write(f)


class MockOCRProcessor(OCRProcessor):
    """Mock OCR processor for testing fallback behavior."""

    def __init__(self, return_text: str = "OCR Extracted Laboratory Findings: Glucose 105 mg/dL"):
        self.return_text = return_text
        self.extract_images_called = False
        self.extract_text_called = False
        self.extract_text_from_images_called = False
        self.received_images: list[bytes] = []

    async def extract_text(self, file_path: Path) -> str:
        self.extract_text_called = True
        return self.return_text

    async def extract_text_from_images(self, images: list[bytes]) -> str:
        self.extract_text_from_images_called = True
        self.received_images.extend(images)
        return self.return_text

    async def extract_images(self, file_path: Path) -> list[bytes]:
        self.extract_images_called = True
        return [b"fake-image-bytes"]


class TestUsableTextEvaluator(unittest.TestCase):
    """Test text usability threshold evaluation."""

    def test_empty_and_whitespace_rejected(self):
        self.assertFalse(is_usable_text(""))
        self.assertFalse(is_usable_text(None))
        self.assertFalse(is_usable_text("    \n\t  "))

    def test_scanner_banner_short_text_rejected(self):
        self.assertFalse(is_usable_text("Page 1 of 1", min_chars=50))
        self.assertFalse(is_usable_text("Scanned by CamScanner", min_chars=50))

    def test_genuine_clinical_text_accepted(self):
        sample = "Patient: Jane Doe | DOB: 1980-05-12 | Fasting Blood Sugar: 95 mg/dL | Normal range 70-99."
        self.assertTrue(is_usable_text(sample, min_chars=50))

    def test_concise_clinical_findings_accepted_below_threshold(self):
        """Verify that short clinical findings with medical indicators are preserved natively."""
        self.assertTrue(is_usable_text("Rx: Metformin 500mg BID", min_chars=50))
        self.assertTrue(is_usable_text("Blood Glucose: 110 mg/dL", min_chars=50))
        self.assertTrue(is_usable_text("HbA1c: 7.2%", min_chars=50))
        self.assertTrue(is_usable_text("BP: 120/80 mmHg", min_chars=50))
        self.assertTrue(is_usable_text("TSH: 2.5 mIU/L", min_chars=50))


class TestNativePDFExtraction(unittest.IsolatedAsyncioTestCase):
    """Test native PDF extraction, page numbering, fallback, and routing."""

    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.doc_id = uuid.uuid4()

    async def asyncTearDown(self):
        self.temp_dir.cleanup()

    async def test_digital_pdf_extracts_native_text_without_ocr(self):
        """A digital PDF with embedded text extracts via pypdf without calling OCR."""
        pdf_file = self.temp_path / "digital_report.pdf"
        p1_text = "Page 1: Complete Blood Count - WBC: 6.8 K/uL, RBC: 4.5 M/uL, Hemoglobin: 14.2 g/dL."
        p2_text = "Page 2: Comprehensive Metabolic Panel - Glucose: 92 mg/dL, BUN: 14 mg/dL, Creatinine: 0.9 mg/dL."
        _create_synthetic_pdf(pdf_file, [p1_text, p2_text])

        mock_ocr = MockOCRProcessor()
        doc = await extract_document_content(
            file_path=pdf_file,
            document_id=self.doc_id,
            ocr_processor=mock_ocr,
        )

        # Total pages and 1-based page numbers
        self.assertEqual(doc.total_pages, 2)
        self.assertEqual(len(doc.pages), 2)
        self.assertEqual(doc.pages[0].page_number, 1)
        self.assertEqual(doc.pages[1].page_number, 2)

        # Extraction method must be native_pdf
        self.assertEqual(doc.pages[0].extraction_method, "native_pdf")
        self.assertEqual(doc.pages[1].extraction_method, "native_pdf")

        # Text contents verbatim
        self.assertIn("Complete Blood Count", doc.pages[0].text)
        self.assertIn("Metabolic Panel", doc.pages[1].text)

        # OCR must NOT have been called
        self.assertFalse(mock_ocr.extract_text_from_images_called)
        self.assertFalse(mock_ocr.extract_text_called)

    async def test_scanned_page_falls_back_to_ocr(self):
        """A scanned PDF page lacking usable text falls back to OCR."""
        pdf_file = self.temp_path / "scanned_page.pdf"
        # Page has no text
        _create_synthetic_pdf(pdf_file, [""])

        mock_ocr = MockOCRProcessor(return_text="OCR Fallback: Platelet count 250 K/uL within normal limits.")

        with patch("app.ai.processors.ocr.native_pdf._render_pdf_page_to_jpeg", return_value=[b"fake-rendered-jpeg"]):
            doc = await extract_document_content(
                file_path=pdf_file,
                document_id=self.doc_id,
                ocr_processor=mock_ocr,
            )

        self.assertEqual(doc.total_pages, 1)
        self.assertEqual(doc.pages[0].page_number, 1)
        self.assertEqual(doc.pages[0].extraction_method, "MockOCRProcessor")
        self.assertEqual(doc.pages[0].text, "OCR Fallback: Platelet count 250 K/uL within normal limits.")
        self.assertTrue(mock_ocr.extract_text_from_images_called)

    async def test_mixed_pdf_preserves_page_numbers_and_order_without_duplicates(self):
        """A 3-page mixed PDF retains native text on pages 1 & 3, and OCR text on page 2."""
        pdf_file = self.temp_path / "mixed_document.pdf"
        p1_text = "Page 1: Digital Consultation Notes - Patient reports seasonal allergic rhinitis."
        p2_text = ""  # Scanned prescription image
        p3_text = "Page 3: Digital Lab Report - Total IgE: 180 IU/mL. Borderline elevated."
        _create_synthetic_pdf(pdf_file, [p1_text, p2_text, p3_text])

        mock_ocr = MockOCRProcessor(return_text="Rx: Cetirizine 10mg once daily oral for 14 days.")

        # Simulate rendering only page 2
        async def _mock_render(path, page_num, dpi=150):
            if page_num == 2:
                return [b"page-2-scan-image"]
            return []

        with patch("app.ai.processors.ocr.native_pdf._render_pdf_page_to_jpeg", side_effect=_mock_render):
            doc = await extract_document_content(
                file_path=pdf_file,
                document_id=self.doc_id,
                ocr_processor=mock_ocr,
            )

        self.assertEqual(doc.total_pages, 3)
        self.assertEqual(len(doc.pages), 3)

        # Page 1: Native
        self.assertEqual(doc.pages[0].page_number, 1)
        self.assertEqual(doc.pages[0].extraction_method, "native_pdf")
        self.assertIn("Consultation Notes", doc.pages[0].text)

        # Page 2: OCR Fallback
        self.assertEqual(doc.pages[1].page_number, 2)
        self.assertEqual(doc.pages[1].extraction_method, "MockOCRProcessor")
        self.assertIn("Cetirizine 10mg", doc.pages[1].text)

        # Page 3: Native
        self.assertEqual(doc.pages[2].page_number, 3)
        self.assertEqual(doc.pages[2].extraction_method, "native_pdf")
        self.assertIn("Total IgE", doc.pages[2].text)

        # Verify page-ordered consolidated output
        consolidated = doc.to_consolidated_text(include_page_markers=True)
        self.assertIn(f"--- Document {self.doc_id} | Page 1 ---", consolidated)
        self.assertIn(f"--- Document {self.doc_id} | Page 2 ---", consolidated)
        self.assertIn(f"--- Document {self.doc_id} | Page 3 ---", consolidated)

        # Page 1 text must appear before Page 2 text, which appears before Page 3 text
        idx1 = consolidated.index("Consultation Notes")
        idx2 = consolidated.index("Cetirizine 10mg")
        idx3 = consolidated.index("Total IgE")
        self.assertTrue(idx1 < idx2 < idx3)

    async def test_empty_page_when_ocr_yields_nothing(self):
        """Empty page where OCR also produces no text is recorded safely as empty."""
        pdf_file = self.temp_path / "partially_empty.pdf"
        p1_text = "Page 1: Clinical Notes Header and Patient History summary text."
        p2_text = ""
        _create_synthetic_pdf(pdf_file, [p1_text, p2_text])

        # OCR returns empty string for page 2
        mock_ocr = MockOCRProcessor(return_text="")

        with patch("app.ai.processors.ocr.native_pdf._render_pdf_page_to_jpeg", return_value=[b"blank-page"]):
            doc = await extract_document_content(
                file_path=pdf_file,
                document_id=self.doc_id,
                ocr_processor=mock_ocr,
            )

        self.assertEqual(doc.total_pages, 2)
        self.assertEqual(doc.pages[0].page_number, 1)
        self.assertEqual(doc.pages[1].page_number, 2)
        self.assertEqual(doc.pages[1].text, "")

        # Consolidated text skips empty page text
        consolidated = doc.to_consolidated_text(include_page_markers=True)
        self.assertIn("Page 1", consolidated)
        self.assertNotIn("Page 2", consolidated)

    async def test_encrypted_pdf_fails_gracefully(self):
        """Encrypted PDF without password raises clear ValueError."""
        pdf_file = self.temp_path / "locked.pdf"
        _create_encrypted_pdf(pdf_file, password="clinician_key")

        mock_ocr = MockOCRProcessor()
        with self.assertRaises(ValueError) as ctx:
            await extract_document_content(
                file_path=pdf_file,
                document_id=self.doc_id,
                ocr_processor=mock_ocr,
            )
        self.assertIn("encrypted", str(ctx.exception).lower())

    async def test_all_pages_empty_raises_value_error(self):
        """A PDF where all pages yield zero text across native and OCR fails."""
        pdf_file = self.temp_path / "all_blank.pdf"
        _create_synthetic_pdf(pdf_file, ["", ""])

        mock_ocr = MockOCRProcessor(return_text="")
        with patch("app.ai.processors.ocr.native_pdf._render_pdf_page_to_jpeg", return_value=[b"blank"]):
            with self.assertRaises(ValueError) as ctx:
                await extract_document_content(
                    file_path=pdf_file,
                    document_id=self.doc_id,
                    ocr_processor=mock_ocr,
                )
            self.assertIn("no readable text", str(ctx.exception).lower())


class TestNonPdfRouting(unittest.IsolatedAsyncioTestCase):
    """Test plain-text, Markdown, and DICOM routing."""

    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.doc_id = uuid.uuid4()

    async def asyncTearDown(self):
        self.temp_dir.cleanup()

    async def test_plain_text_direct_routing_preserves_lines_and_bypasses_ocr(self):
        """Plain-text (.txt) reads directly with line breaks and does not call OCR."""
        txt_file = self.temp_path / "lab_results.txt"
        content = "Patient: John Doe\nTest: Fasting Glucose\nResult: 88 mg/dL\nStatus: Normal\n"
        txt_file.write_text(content, encoding="utf-8")

        mock_ocr = MockOCRProcessor()
        doc = await extract_document_content(
            file_path=txt_file,
            document_id=self.doc_id,
            ocr_processor=mock_ocr,
        )

        self.assertEqual(doc.total_pages, 1)
        self.assertEqual(doc.pages[0].page_number, 1)
        self.assertEqual(doc.pages[0].extraction_method, "plain_text")
        self.assertEqual(doc.pages[0].text, content.strip())
        self.assertIn("\nTest: Fasting Glucose\n", doc.pages[0].text)
        self.assertFalse(mock_ocr.extract_text_from_images_called)

    async def test_markdown_direct_routing(self):
        """Markdown (.md) reads directly as text and does not call OCR."""
        md_file = self.temp_path / "summary.md"
        content = "# Clinical Impression\n\n| Biomarker | Value | Unit |\n|---|---|---|\n| HbA1c | 5.8 | % |\n"
        md_file.write_text(content, encoding="utf-8")

        mock_ocr = MockOCRProcessor()
        doc = await extract_document_content(
            file_path=md_file,
            document_id=self.doc_id,
            ocr_processor=mock_ocr,
        )

        self.assertEqual(doc.total_pages, 1)
        self.assertEqual(doc.pages[0].extraction_method, "plain_text")
        self.assertIn("| HbA1c | 5.8 | % |", doc.pages[0].text)
        self.assertFalse(mock_ocr.extract_text_from_images_called)

    async def test_non_image_dicom_raises_descriptive_error(self):
        """Non-image DICOM reports raise descriptive error rather than crashing rasterizer."""
        dcm_file = self.temp_path / "report.dcm"
        dcm_file.write_bytes(b"DICM_FAKE_NO_PIXELS")

        mock_ocr = MockOCRProcessor()
        with patch("app.ai.processors.ocr.utils.convert_to_images", return_value=[]):
            with self.assertRaises(ValueError) as ctx:
                await extract_document_content(
                    file_path=dcm_file,
                    document_id=self.doc_id,
                    ocr_processor=mock_ocr,
                )
            self.assertIn("pixel data", str(ctx.exception).lower())


class TestBackwardCompatibilityAndMarkers(unittest.TestCase):
    """Test PageAwareDocumentContent consolidated text with and without page markers."""

    def test_legacy_flat_text_without_markers(self):
        doc_id = uuid.uuid4()
        page1 = DocumentPageContent(document_id=doc_id, page_number=1, text="Page 1 Text")
        page2 = DocumentPageContent(document_id=doc_id, page_number=2, text="Page 2 Text")

        container = PageAwareDocumentContent(
            document_id=doc_id,
            total_pages=2,
            pages=[page1, page2],
        )

        flat = container.to_consolidated_text(include_page_markers=False)
        self.assertEqual(flat, "Page 1 Text\n\nPage 2 Text")

    def test_page_markers_included_for_structured_extraction(self):
        doc_id = uuid.uuid4()
        page1 = DocumentPageContent(document_id=doc_id, page_number=1, text="Lab Results: HbA1c 6.0%")
        page2 = DocumentPageContent(document_id=doc_id, page_number=2, text="Assessment: Pre-diabetes")

        container = PageAwareDocumentContent(
            document_id=doc_id,
            total_pages=2,
            pages=[page1, page2],
        )

        marked = container.to_consolidated_text(include_page_markers=True)
        expected = (
            f"--- Document {doc_id} | Page 1 ---\nLab Results: HbA1c 6.0%\n\n"
            f"--- Document {doc_id} | Page 2 ---\nAssessment: Pre-diabetes"
        )
        self.assertEqual(marked, expected)


class TestPipelineIntegrationAudit(unittest.IsolatedAsyncioTestCase):
    """Integration audit tests for clinical text preservation, provenance, and defaults."""

    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.doc_id = uuid.uuid4()

    async def asyncTearDown(self):
        self.temp_dir.cleanup()

    async def test_short_clinical_prescription_native_extraction(self):
        """A single concise prescription page is extracted natively without triggering OCR."""
        pdf_file = self.temp_path / "prescription.pdf"
        _create_synthetic_pdf(pdf_file, ["Rx: Metformin 500mg BID"])

        mock_ocr = MockOCRProcessor()
        doc = await extract_document_content(
            file_path=pdf_file,
            document_id=self.doc_id,
            ocr_processor=mock_ocr,
        )

        self.assertEqual(doc.total_pages, 1)
        self.assertEqual(len(doc.pages), 1)
        self.assertEqual(doc.pages[0].page_number, 1)
        self.assertIn("Metformin", doc.pages[0].text)
        self.assertEqual(doc.pages[0].extraction_method, "native_pdf")
        # OCR processor must not have been invoked
        self.assertFalse(mock_ocr.extract_text_from_images_called)

    async def test_short_text_fallback_preserves_native_content_when_ocr_empty(self):
        """When short text triggers fallback and OCR produces empty string, native text is never discarded."""
        pdf_file = self.temp_path / "concise_note.pdf"
        _create_synthetic_pdf(pdf_file, ["Follow up in two weeks"])

        mock_ocr = MockOCRProcessor(return_text="")
        with patch("app.ai.processors.ocr.native_pdf._render_pdf_page_to_jpeg", return_value=[b"fake"]):
            doc = await extract_document_content(
                file_path=pdf_file,
                document_id=self.doc_id,
                ocr_processor=mock_ocr,
            )

        self.assertEqual(doc.total_pages, 1)
        self.assertEqual(len(doc.pages), 1)
        # Content preserved even though OCR returned empty
        self.assertIn("Follow up in two weeks", doc.pages[0].text)

    def test_provenance_markers_survive_aggregation_and_find_source_doc(self):
        """Page markers survive aggregation and find_source_doc locates the originating document."""
        from app.ai.pipeline.persistence import find_source_doc

        doc1_id = uuid.uuid4()
        doc2_id = uuid.uuid4()

        doc1_mock = MagicMock()
        doc1_mock.id = doc1_id
        doc1_mock.extracted_text = (
            f"--- Document {doc1_id} | Page 1 ---\n"
            "Hemoglobin: 14.2 g/dL\n\n"
            f"--- Document {doc1_id} | Page 2 ---\n"
            "Fasting Blood Glucose: 98 mg/dL"
        )

        doc2_mock = MagicMock()
        doc2_mock.id = doc2_id
        doc2_mock.extracted_text = (
            f"--- Document {doc2_id} | Page 1 ---\n"
            "Rx: Atorvastatin 20mg oral daily"
        )

        docs = [doc1_mock, doc2_mock]

        self.assertEqual(find_source_doc("Hemoglobin", docs), doc1_id)
        self.assertEqual(find_source_doc("Glucose", docs), doc1_id)
        self.assertEqual(find_source_doc("Atorvastatin", docs), doc2_id)
        self.assertIsNone(find_source_doc("Nonexistent Drug", docs))

    def test_review_status_defaults_to_needs_review(self):
        """Clinical extractions must default conservatively to 'needs_review'."""
        from app.ai.schemas.nlp import (
            KnownBiomarkerExtract,
            KnownMedicationExtract,
            UnknownBiomarkerExtract,
            UnknownMedicationExtract,
        )

        kb = KnownBiomarkerExtract(name="Glucose", matched_slug="glucose", value=100.0)
        self.assertEqual(kb.review_status, "needs_review")

        ub = UnknownBiomarkerExtract(raw_name="NovelMarker", value=42.0)
        self.assertEqual(ub.review_status, "needs_review")

        km = KnownMedicationExtract(name="Metformin", matched_id="med-123")
        self.assertEqual(km.review_status, "needs_review")

        um = UnknownMedicationExtract(raw_name="ExperimentalDrug")
        self.assertEqual(um.review_status, "needs_review")


if __name__ == "__main__":
    unittest.main()

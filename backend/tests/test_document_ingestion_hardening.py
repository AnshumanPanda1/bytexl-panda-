"""Unit tests for Phase 3 document ingestion hardening and page-aware boundary models.

Covers:
- Filename sanitization against path traversal, control characters, and length overflow.
- Upload extension allowlist validation.
- Empty (0-byte) content rejection (HTTP 400).
- Oversized upload content rejection (HTTP 413).
- Invalid tenant ID format rejection (HTTP 400).
- Task queue dispatch failure handling and document state consistency (HTTP 503).
- Page-aware extraction input boundary schemas (DocumentPageContent, PageAwareDocumentContent).
"""

import os
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure backend root is on Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi import HTTPException
from pydantic import ValidationError

from app.ai.schemas.nlp import DocumentPageContent, PageAwareDocumentContent
from app.core.config import settings
from app.services.document_service import (
    ALLOWED_UPLOAD_EXTENSIONS,
    _read_capped,
    _sanitize_filename,
    _validate_upload_extension,
    ingest_document_bytes,
    trigger_extraction,
)


class TestDocumentFilenameSanitization(unittest.TestCase):
    """Test _sanitize_filename against path traversal and malformed names."""

    def test_normal_filename_preserved(self):
        self.assertEqual(_sanitize_filename("lab_report.pdf"), "lab_report.pdf")
        self.assertEqual(_sanitize_filename("chest_xray.png"), "chest_xray.png")

    def test_unix_path_traversal_stripped(self):
        self.assertEqual(_sanitize_filename("../../etc/passwd.pdf"), "passwd.pdf")
        self.assertEqual(_sanitize_filename("/var/log/syslog.txt"), "syslog.txt")

    def test_windows_path_traversal_stripped(self):
        self.assertEqual(_sanitize_filename("..\\..\\windows\\system32\\calc.png"), "calc.png")
        self.assertEqual(_sanitize_filename("C:\\Users\\victim\\data.pdf"), "data.pdf")

    def test_null_bytes_and_control_chars_stripped(self):
        self.assertEqual(_sanitize_filename("malicious\x00file.pdf"), "maliciousfile.pdf")
        self.assertEqual(_sanitize_filename("test\r\nline.txt"), "testline.txt")

    def test_empty_and_whitespace_filename_fallback(self):
        self.assertEqual(_sanitize_filename(""), "unnamed_document")
        self.assertEqual(_sanitize_filename(None), "unnamed_document")
        self.assertEqual(_sanitize_filename("   "), "unnamed_document")

    def test_dotfile_extension_handling(self):
        # Dotfiles like .pdf should not be blanked out
        result = _sanitize_filename(".pdf")
        self.assertTrue(result.endswith(".pdf"))

    def test_max_length_truncation_preserves_extension(self):
        long_stem = "a" * 300
        filename = f"{long_stem}.pdf"
        sanitized = _sanitize_filename(filename)
        self.assertLessEqual(len(sanitized), 255)
        self.assertTrue(sanitized.endswith(".pdf"))
        self.assertTrue(sanitized.startswith("a"))


class TestUploadExtensionValidation(unittest.TestCase):
    """Test _validate_upload_extension for allowed and disallowed extensions."""

    def test_allowed_extensions_pass(self):
        for ext in [".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".webp", ".bmp", ".gif", ".txt", ".md", ".dcm"]:
            self.assertIn(ext, ALLOWED_UPLOAD_EXTENSIONS)
            result = _validate_upload_extension(f"sample{ext}")
            self.assertEqual(result, ext)

    def test_disallowed_extensions_rejected(self):
        disallowed = [".exe", ".sh", ".svg", ".html", ".htm", ".xml", ".js", ".py"]
        for ext in disallowed:
            with self.assertRaises(HTTPException) as ctx:
                _validate_upload_extension(f"malicious{ext}")
            self.assertEqual(ctx.exception.status_code, 400)
            self.assertIn("Unsupported file type", ctx.exception.detail)

    def test_missing_extension_rejected(self):
        with self.assertRaises(HTTPException) as ctx:
            _validate_upload_extension("no_extension_file")
        self.assertEqual(ctx.exception.status_code, 400)


class TestDocumentIngestionHardening(unittest.IsolatedAsyncioTestCase):
    """Test ingest_document_bytes input validation and failure resilience."""

    async def asyncSetUp(self):
        self.tenant_id = uuid.uuid4()
        self.user_id = uuid.uuid4()
        self.db_mock = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        self.db_mock.execute.return_value = mock_result
        self.db_mock.commit = AsyncMock()
        self.db_mock.add = MagicMock()
        self.db_mock.refresh = AsyncMock()

    async def test_empty_content_rejected(self):
        with self.assertRaises(HTTPException) as ctx:
            await ingest_document_bytes(
                filename="empty.pdf",
                content=b"",
                content_type="application/pdf",
                tenant_id=self.tenant_id,
                patient_id=None,
                owner_id=self.user_id,
                db=self.db_mock,
            )
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("empty", ctx.exception.detail.lower())

    async def test_oversized_content_rejected(self):
        fake_content = b"x" * 100

        with patch.object(settings, "MAX_UPLOAD_SIZE", 0):  # limit to 0 MB
            with self.assertRaises(HTTPException) as ctx:
                await ingest_document_bytes(
                    filename="large.pdf",
                    content=fake_content,
                    content_type="application/pdf",
                    tenant_id=self.tenant_id,
                    patient_id=None,
                    owner_id=self.user_id,
                    db=self.db_mock,
                )
            self.assertEqual(ctx.exception.status_code, 413)
            self.assertIn("too large", ctx.exception.detail.lower())

    async def test_invalid_tenant_id_rejected(self):
        with self.assertRaises(HTTPException) as ctx:
            await ingest_document_bytes(
                filename="test.pdf",
                content=b"%PDF-1.4 test",
                content_type="application/pdf",
                tenant_id="invalid-uuid-string",
                patient_id=None,
                owner_id=self.user_id,
                db=self.db_mock,
            )
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("tenant", ctx.exception.detail.lower())

    async def test_successful_ingestion_with_sanitized_filename(self):
        mock_ai_tasks = MagicMock()
        mock_celery = MagicMock()
        mock_ai_tasks.ocr_document = mock_celery

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            with patch("app.services.document_service.HA_UPLOAD_DIR", temp_path):
                with patch("app.services.document_service.assert_valid_fhir"):
                    with patch.dict("sys.modules", {"app.workers": MagicMock(), "app.workers.ai_tasks": mock_ai_tasks}):
                        doc = await ingest_document_bytes(
                            filename="../../dirty/traversal/report.pdf",
                            content=b"%PDF-1.4 test content\n%%EOF",
                            content_type="application/pdf",
                            tenant_id=self.tenant_id,
                            patient_id=None,
                            owner_id=self.user_id,
                            db=self.db_mock,
                            include_in_extraction=False,
                        )

                        # Filename must be sanitized
                        self.assertEqual(doc.filename, "report.pdf")
                        self.assertEqual(doc.status, "uploaded")
                        self.assertEqual(doc.progress, 0)
                        self.assertFalse(doc.include_in_extraction)
                        # Celery must NOT be dispatched when include_in_extraction is False
                        mock_celery.apply_async.assert_not_called()
                        # File must exist on disk
                        self.assertTrue(Path(doc.file_path).exists())
                        self.assertEqual(Path(doc.file_path).read_bytes(), b"%PDF-1.4 test content\n%%EOF")

    async def test_ingestion_dispatches_ocr_when_include_in_extraction_is_true(self):
        mock_ai_tasks = MagicMock()
        mock_celery = MagicMock()
        mock_ai_tasks.ocr_document = mock_celery

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            with patch("app.services.document_service.HA_UPLOAD_DIR", temp_path):
                with patch("app.services.document_service.assert_valid_fhir"):
                    with patch.dict("sys.modules", {"app.workers": MagicMock(), "app.workers.ai_tasks": mock_ai_tasks}):
                        doc = await ingest_document_bytes(
                            filename="valid_report.pdf",
                            content=b"%PDF-1.4 valid\n%%EOF",
                            content_type="application/pdf",
                            tenant_id=self.tenant_id,
                            patient_id=None,
                            owner_id=self.user_id,
                            db=self.db_mock,
                            include_in_extraction=True,
                        )

                        self.assertTrue(doc.include_in_extraction)
                        mock_celery.apply_async.assert_called_once()
                        call_args = mock_celery.apply_async.call_args[1]["args"]
                        self.assertEqual(call_args[0], str(doc.id))


class _MockChunkStream:
    def __init__(self, chunks: list[bytes]):
        self._chunks = list(chunks)

    async def read(self, size: int = -1) -> bytes:
        if self._chunks:
            return self._chunks.pop(0)
        return b""


class TestReadCapped(unittest.IsolatedAsyncioTestCase):
    """Test chunked upload reading with size cap enforcement."""

    async def test_read_capped_within_limit(self):
        stream = _MockChunkStream([b"hello ", b"world"])
        result = await _read_capped(stream, max_bytes=100)
        self.assertEqual(result, b"hello world")

    async def test_read_capped_exceeding_limit_raises_413(self):
        stream = _MockChunkStream([b"chunk1_", b"chunk2_excessive"])
        with self.assertRaises(HTTPException) as ctx:
            await _read_capped(stream, max_bytes=10)
        self.assertEqual(ctx.exception.status_code, 413)


class TestExtractionDispatchFailureResilience(unittest.IsolatedAsyncioTestCase):
    """Test Celery dispatch failure handling in trigger_extraction."""

    async def test_nonexistent_document_raises_404(self):
        db_mock = AsyncMock()
        with patch("app.services.document_service.get_document", return_value=None):
            with self.assertRaises(HTTPException) as ctx:
                await trigger_extraction("nonexistent-id", db_mock)
            self.assertEqual(ctx.exception.status_code, 404)

    async def test_celery_broker_failure_marks_document_failed_and_raises_503(self):
        mock_doc = MagicMock()
        mock_doc.id = uuid.uuid4()
        mock_doc.file_path = "/tmp/test.pdf"
        mock_doc.tenant_id = uuid.uuid4()
        mock_doc.owner_id = uuid.uuid4()
        mock_doc.status = "uploaded"
        mock_doc.progress = 0
        mock_doc.error_message = None

        db_mock = AsyncMock()
        db_mock.commit = AsyncMock()

        mock_ai_tasks = MagicMock()
        mock_task = MagicMock()
        mock_task.apply_async.side_effect = ConnectionError("Redis broker unreachable")
        mock_ai_tasks.ocr_document = mock_task

        with patch("app.services.document_service.get_document", return_value=mock_doc):
            with patch.dict("sys.modules", {"app.workers": MagicMock(), "app.workers.ai_tasks": mock_ai_tasks}):
                with self.assertRaises(HTTPException) as ctx:
                    await trigger_extraction(str(mock_doc.id), db_mock)

                self.assertEqual(ctx.exception.status_code, 503)
                self.assertIn("Task queue unavailable", ctx.exception.detail)
                # Document status must be reset to failed, not left stuck in processing
                self.assertEqual(mock_doc.status, "failed")
                self.assertEqual(mock_doc.progress, 0)
                self.assertIsNotNone(mock_doc.error_message)
                self.assertIn("Redis broker unreachable", mock_doc.error_message)


class TestPageAwareBoundarySchemas(unittest.TestCase):
    """Test Phase 4 page-aware boundary models (DocumentPageContent, PageAwareDocumentContent)."""

    def test_document_page_content_instantiation(self):
        page = DocumentPageContent(
            document_id=str(uuid.uuid4()),
            page_number=1,
            text="Patient blood sugar: 110 mg/dL",
            extraction_method="tesseract_ocr",
            metadata={"dpi": 300, "confidence": 0.95},
        )
        self.assertEqual(page.page_number, 1)
        self.assertEqual(page.text, "Patient blood sugar: 110 mg/dL")
        self.assertEqual(page.extraction_method, "tesseract_ocr")

    def test_document_page_content_rejects_non_positive_page_number(self):
        with self.assertRaises(ValidationError):
            DocumentPageContent(
                document_id=str(uuid.uuid4()),
                page_number=0,  # ge=1 required
                text="Invalid page index",
            )

    def test_page_aware_document_content_consolidation(self):
        doc_id = str(uuid.uuid4())
        page1 = DocumentPageContent(document_id=doc_id, page_number=1, text="Header: Lab Report")
        page2 = DocumentPageContent(document_id=doc_id, page_number=2, text="Results: Normal")

        container = PageAwareDocumentContent(
            document_id=doc_id,
            total_pages=2,
            pages=[page1, page2],
        )

        self.assertEqual(container.total_pages, 2)
        self.assertEqual(len(container.pages), 2)
        consolidated = container.to_consolidated_text()
        self.assertEqual(consolidated, "Header: Lab Report\n\nResults: Normal")

        custom_delim = container.to_consolidated_text(delimiter=" | ")
        self.assertEqual(custom_delim, "Header: Lab Report | Results: Normal")

    def test_out_of_order_pages_consolidated_in_page_order(self):
        doc_id = str(uuid.uuid4())
        page1 = DocumentPageContent(document_id=doc_id, page_number=1, text="Page One")
        page2 = DocumentPageContent(document_id=doc_id, page_number=2, text="Page Two")

        # Constructed out of order (e.g. from asynchronous parallel OCR workers)
        container = PageAwareDocumentContent(
            document_id=doc_id,
            total_pages=2,
            pages=[page2, page1],
        )

        consolidated = container.to_consolidated_text()
        self.assertEqual(consolidated, "Page One\n\nPage Two")

    def test_empty_pages_permitted(self):
        doc_id = str(uuid.uuid4())
        blank_page = DocumentPageContent(document_id=doc_id, page_number=1, text="")
        page2 = DocumentPageContent(document_id=doc_id, page_number=2, text="Content")

        container = PageAwareDocumentContent(
            document_id=doc_id,
            total_pages=2,
            pages=[blank_page, page2],
        )
        self.assertEqual(container.to_consolidated_text(), "Content")

    def test_partial_processing_permitted(self):
        doc_id = str(uuid.uuid4())
        page1 = DocumentPageContent(document_id=doc_id, page_number=1, text="First Page Only")

        # Document has 10 total pages, but only page 1 extracted in this batch
        container = PageAwareDocumentContent(
            document_id=doc_id,
            total_pages=10,
            pages=[page1],
        )
        self.assertEqual(container.total_pages, 10)
        self.assertEqual(len(container.pages), 1)

    def test_page_number_exceeding_total_pages_rejected(self):
        doc_id = str(uuid.uuid4())
        page_exceeding = DocumentPageContent(document_id=doc_id, page_number=5, text="Page 5")

        with self.assertRaises(ValidationError) as ctx:
            PageAwareDocumentContent(
                document_id=doc_id,
                total_pages=2,
                pages=[page_exceeding],
            )
        self.assertIn("exceeds total_pages", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()

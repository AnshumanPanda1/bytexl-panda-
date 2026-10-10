"""Native PDF text extraction and page-aware document routing.

Extracts embedded text directly from digital PDFs using pypdf without
unnecessary rasterization, while falling back to image-based OCR on a
per-page basis for scanned pages or pages without usable digital text.

Also provides direct text decoding for plain-text and Markdown inputs
without image conversion.
"""

import io
import logging
from pathlib import Path
import re
from typing import Any
from uuid import UUID

from app.ai.processors.ocr.base import OCRProcessor
from app.ai.schemas.nlp import DocumentPageContent, PageAwareDocumentContent

logger = logging.getLogger(__name__)

try:
    import pypdf

    HAS_PYPDF = True
except ImportError:
    pypdf = None  # type: ignore
    HAS_PYPDF = False

try:
    from pdf2image import convert_from_path

    HAS_PDF2IMAGE = True
except ImportError:
    convert_from_path = None  # type: ignore
    HAS_PDF2IMAGE = False


_CLINICAL_PATTERN = re.compile(
    r"(?:"
    r"\b(?:rx|tab|cap|capsule|tablet|mg|mcg|ug|g/dl|mg/dl|mmol|iu|miu|u/l|bid|tid|qid|prn|po|daily)\b"
    r"|\b(?:glucose|hba1c|hemoglobin|creatinine|cholesterol|tsh|wbc|rbc|platelets|bp|hr|spo2)\b"
    r"|\b(?:diagnos|impress|prescrib|medicat|patient|doctor|dr\.|clinic|hospital)\b"
    r"|\d+\s*(?:mg|mcg|g/dl|mg/dl|mmol/l|miu/l|u/l|%|mmhg)"
    r")",
    re.IGNORECASE,
)


def is_usable_text(text: str | None, min_chars: int = 50, min_words: int = 5) -> bool:
    """Determine whether extracted text represents usable digital content rather than
    a scanner watermark, header banner, or whitespace artifact.

    Accepts text that meets standard length thresholds, or concise clinical text
    (>= 10 chars, >= 2 words) containing medical indicators, dosages, units, or
    diagnostic terms, preventing premature fallback on short digital findings.
    """
    if not text:
        return False
    clean = text.strip()
    words = [w for w in clean.split() if any(c.isalnum() for c in w)]
    if len(clean) >= min_chars and len(words) >= min_words:
        return True
    # Clinical text preservation: preserve short findings, abnormal values, and prescriptions
    if len(clean) >= 10 and len(words) >= 2 and _CLINICAL_PATTERN.search(clean):
        return True
    return False


async def _render_pdf_page_to_jpeg(file_path: Path, page_number: int, dpi: int = 150) -> list[bytes]:
    """Render a single 1-based PDF page to JPEG bytes for fallback OCR."""
    if HAS_PDF2IMAGE and convert_from_path is not None:
        try:
            images = convert_from_path(
                file_path,
                dpi=dpi,
                first_page=page_number,
                last_page=page_number,
            )
            result: list[bytes] = []
            for img in images:
                if img.mode != "RGB":
                    img = img.convert("RGB")
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=90, optimize=True)
                result.append(buf.getvalue())
            return result
        except Exception as e:
            logger.warning("pdf2image rendering failed for page %d of %s: %s", page_number, file_path.name, e)
    return []


class NativePDFExtractor:
    """Extracts text from PDFs using pypdf with page-level OCR fallback."""

    def __init__(self, min_text_chars: int = 50):
        self.min_text_chars = min_text_chars

    async def extract_pdf(
        self,
        file_path: Path,
        document_id: str | UUID,
        ocr_processor: OCRProcessor | None = None,
    ) -> PageAwareDocumentContent:
        """Extract text from a PDF document, preserving 1-based page boundaries.

        - Extracts native text from each page.
        - Evaluates each page against ``self.min_text_chars``.
        - Falls back to ``ocr_processor`` only on pages lacking usable text.
        - Never duplicates native and OCR text for the same page.
        - Preserves sequential 1-based page numbers.
        """
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        if not HAS_PYPDF or pypdf is None:
            logger.warning("pypdf not available; falling back to full-document OCR for %s", file_path.name)
            if ocr_processor is None:
                raise ValueError("pypdf is not installed and no OCR processor was provided")
            return await _ocr_fallback_full_pdf(file_path, document_id, ocr_processor)

        try:
            reader = pypdf.PdfReader(str(file_path))
        except Exception as e:
            logger.warning("pypdf failed to read %s: %s. Attempting full-document OCR fallback.", file_path.name, e)
            if ocr_processor is not None:
                return await _ocr_fallback_full_pdf(file_path, document_id, ocr_processor)
            raise ValueError(f"Unable to read PDF file: {e}") from e

        if reader.is_encrypted:
            try:
                decrypted = reader.decrypt("")
                if not decrypted:
                    raise ValueError(f"PDF {file_path.name} is encrypted and password-protected")
            except Exception as e:
                raise ValueError(f"PDF {file_path.name} is encrypted and cannot be opened: {e}") from e

        total_pages = len(reader.pages)
        if total_pages == 0:
            raise ValueError(f"PDF document {file_path.name} contains 0 pages")

        pages_content: list[DocumentPageContent] = []

        for idx, page in enumerate(reader.pages):
            page_num = idx + 1
            try:
                extracted = page.extract_text() or ""
            except Exception as e:
                logger.warning("Native text extraction failed for page %d of %s: %s", page_num, file_path.name, e)
                extracted = ""

            clean_text = extracted.strip()

            if is_usable_text(clean_text, min_chars=self.min_text_chars):
                # Digital page with usable native text
                pages_content.append(
                    DocumentPageContent(
                        document_id=document_id,
                        page_number=page_num,
                        text=clean_text,
                        extraction_method="native_pdf",
                        metadata={"char_count": len(clean_text)},
                    )
                )
            else:
                # Page lacks sufficient native text; attempt OCR fallback
                ocr_text = ""
                ocr_method = "empty_page"

                if ocr_processor is not None:
                    # 1. Try rendering exact page with pdf2image
                    page_images = await _render_pdf_page_to_jpeg(file_path, page_num)
                    if page_images:
                        try:
                            raw_ocr = await ocr_processor.extract_text_from_images(page_images)
                            if raw_ocr and raw_ocr.strip():
                                ocr_text = raw_ocr.strip()
                                ocr_method = ocr_processor.__class__.__name__
                        except Exception as ocr_err:
                            logger.warning(
                                "OCR fallback failed on page %d of %s: %s", page_num, file_path.name, ocr_err
                            )

                    # 2. If pdf2image yielded nothing, check embedded images in pypdf
                    if not ocr_text and hasattr(page, "images") and len(page.images) > 0:
                        try:
                            embedded_bytes = [img.data for img in page.images if hasattr(img, "data")]
                            if embedded_bytes:
                                raw_ocr = await ocr_processor.extract_text_from_images(embedded_bytes)
                                if raw_ocr and raw_ocr.strip():
                                    ocr_text = raw_ocr.strip()
                                    ocr_method = ocr_processor.__class__.__name__
                        except Exception as emb_err:
                            logger.debug(
                                "Embedded image OCR failed on page %d of %s: %s", page_num, file_path.name, emb_err
                            )

                # Candidate selection: OCR text wins if found; else keep native text if present, else empty
                final_text = ocr_text if ocr_text else clean_text
                final_method = (
                    ocr_method
                    if ocr_text
                    else ("native_pdf" if clean_text else "empty_page")
                )

                pages_content.append(
                    DocumentPageContent(
                        document_id=document_id,
                        page_number=page_num,
                        text=final_text,
                        extraction_method=final_method,
                        metadata={
                            "fallback_attempted": True,
                            "char_count": len(final_text),
                        },
                    )
                )

        pages_content.sort(key=lambda p: p.page_number)

        # Ensure that at least one page produced text across the entire document
        has_any_text = any(len(p.text.strip()) > 0 for p in pages_content)
        if not has_any_text:
            raise ValueError(f"Document {file_path.name} contains no readable text across all {total_pages} pages")

        return PageAwareDocumentContent(
            document_id=document_id,
            total_pages=total_pages,
            pages=pages_content,
        )


async def _ocr_fallback_full_pdf(
    file_path: Path, document_id: str | UUID, ocr_processor: OCRProcessor
) -> PageAwareDocumentContent:
    """Full-document OCR fallback when pypdf cannot read the PDF structure."""
    from app.ai.processors.ocr.utils import convert_to_images

    images = await convert_to_images(file_path)
    if not images:
        raise ValueError(f"Could not convert PDF {file_path.name} to images for OCR fallback")

    pages: list[DocumentPageContent] = []
    for idx, img_bytes in enumerate(images):
        page_num = idx + 1
        page_text = await ocr_processor.extract_text_from_images([img_bytes])
        pages.append(
            DocumentPageContent(
                document_id=document_id,
                page_number=page_num,
                text=page_text.strip() if page_text else "",
                extraction_method=ocr_processor.__class__.__name__,
                metadata={"full_document_fallback": True},
            )
        )

    has_any_text = any(len(p.text.strip()) > 0 for p in pages)
    if not has_any_text:
        raise ValueError(f"OCR extracted no readable text from {file_path.name}")

    return PageAwareDocumentContent(
        document_id=document_id,
        total_pages=len(pages),
        pages=pages,
    )


def _extract_plain_text(file_path: Path, document_id: str | UUID) -> PageAwareDocumentContent:
    """Read plain-text or Markdown document directly without image rasterization."""
    content = ""
    used_encoding = "utf-8"
    encodings = ["utf-8", "utf-8-sig", "latin-1", "cp1252"]

    for enc in encodings:
        try:
            with open(file_path, encoding=enc) as f:
                content = f.read()
            used_encoding = enc
            break
        except (UnicodeDecodeError, LookupError):
            continue

    clean = content.strip()
    if not clean:
        raise ValueError(f"Text document {file_path.name} is empty")

    page = DocumentPageContent(
        document_id=document_id,
        page_number=1,
        text=clean,
        extraction_method="plain_text",
        metadata={"encoding": used_encoding, "char_count": len(clean)},
    )
    return PageAwareDocumentContent(
        document_id=document_id,
        total_pages=1,
        pages=[page],
    )


async def _extract_image_document(
    file_path: Path, document_id: str | UUID, ocr_processor: OCRProcessor
) -> PageAwareDocumentContent:
    """Process single or multi-frame raster images (PNG, JPG, TIFF, DICOM) via OCR."""
    from app.ai.processors.ocr.utils import convert_to_images

    images = await convert_to_images(file_path)
    if not images:
        if file_path.suffix.lower() == ".dcm":
            raise ValueError(
                f"DICOM file {file_path.name} has no pixel data for image extraction. "
                "Structured reports require metadata endpoint extraction."
            )
        raise ValueError(f"Could not convert {file_path.name} to images for OCR")

    pages: list[DocumentPageContent] = []
    for idx, img_bytes in enumerate(images):
        page_num = idx + 1
        page_text = await ocr_processor.extract_text_from_images([img_bytes])
        pages.append(
            DocumentPageContent(
                document_id=document_id,
                page_number=page_num,
                text=page_text.strip() if page_text else "",
                extraction_method=ocr_processor.__class__.__name__,
                metadata={"frame_index": idx},
            )
        )

    has_any_text = any(len(p.text.strip()) > 0 for p in pages)
    if not has_any_text:
        raise ValueError(f"OCR extracted no text from {file_path.name}")

    return PageAwareDocumentContent(
        document_id=document_id,
        total_pages=len(pages),
        pages=pages,
    )


async def extract_document_content(
    file_path: Path,
    document_id: str | UUID,
    ocr_processor: OCRProcessor | None = None,
    min_text_chars: int = 50,
) -> PageAwareDocumentContent:
    """Extract page-aware text from any supported document format.

    - PDFs: Uses native PDF text extraction via pypdf where usable, with
      per-page fallback to ocr_processor for scanned or empty pages.
    - Plain-text / Markdown (.txt, .md, .csv): Decoded directly without rasterization.
    - Images (.png, .jpg, .tiff, etc.) / DICOM: Processed per frame via ocr_processor.
    """
    suffix = file_path.suffix.lower()

    if suffix == ".pdf":
        extractor = NativePDFExtractor(min_text_chars=min_text_chars)
        return await extractor.extract_pdf(file_path, document_id, ocr_processor)

    if suffix in [".txt", ".md", ".csv"]:
        return _extract_plain_text(file_path, document_id)

    if ocr_processor is None:
        raise ValueError(f"OCR processor required for raster/image format '{suffix}'")

    return await _extract_image_document(file_path, document_id, ocr_processor)

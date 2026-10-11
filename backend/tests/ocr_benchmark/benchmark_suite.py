"""OCR Benchmark & Preprocessing Evaluation Suite.

Evaluates local OCR engines (Tesseract 5.5.0 and NativePDFExtractor) across
reproducible synthetic nonclinical documents (digital PDF, scanned PDF, PNG, JPG,
bilingual Hindi) under clean, skewed, low-contrast, noisy, and low-res conditions.

Measures:
- Extraction success rate
- Character Error Rate (CER) via normalized Levenshtein distance
- Word Error Rate (WER) via token-level Levenshtein distance
- Field accuracy: critical numbers, decimal points, units, and dates
- Per-sample and total execution runtime (ms)
- Comparative evaluation of preprocessing: deskew, contrast normalization, rescaling
"""

from dataclasses import dataclass, field
import io
import json
import logging
import os
from pathlib import Path
import re
import subprocess
import time
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas

logger = logging.getLogger(__name__)

# Standard Levenshtein distance for strings or token sequences
def levenshtein_distance(seq1: str | list[str], seq2: str | list[str]) -> int:
    """Compute Levenshtein edit distance between two sequences."""
    if len(seq1) < len(seq2):
        return levenshtein_distance(seq2, seq1)
    if len(seq2) == 0:
        return len(seq1)
    previous_row = list(range(len(seq2) + 1))
    for i, c1 in enumerate(seq1):
        current_row = [i + 1]
        for j, c2 in enumerate(seq2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]


def compute_cer(reference: str, hypothesis: str) -> float:
    """Compute Character Error Rate (CER).

    Formula: Levenshtein(reference_chars, hypothesis_chars) / len(reference_chars).
    Returns float clamped between 0.0 and 1.0 (or >1.0 if severe insertions).
    """
    ref_norm = re.sub(r"\s+", " ", reference).strip()
    hyp_norm = re.sub(r"\s+", " ", hypothesis).strip()
    if not ref_norm:
        return 0.0 if not hyp_norm else 1.0
    dist = levenshtein_distance(ref_norm, hyp_norm)
    return round(dist / len(ref_norm), 4)


def compute_wer(reference: str, hypothesis: str) -> float:
    """Compute Word Error Rate (WER).

    Formula: Levenshtein(reference_tokens, hypothesis_tokens) / len(reference_tokens).
    """
    ref_words = reference.strip().split()
    hyp_words = hypothesis.strip().split()
    if not ref_words:
        return 0.0 if not hyp_words else 1.0
    dist = levenshtein_distance(ref_words, hyp_words)
    return round(dist / len(ref_words), 4)


def evaluate_field_accuracy(expected_tokens: list[str], extracted_text: str) -> tuple[int, int, float]:
    """Check how many expected critical tokens (numbers, units, dates) appear in extracted text.

    Returns (matched_count, total_count, accuracy_fraction).
    """
    if not expected_tokens:
        return (0, 0, 1.0)
    matched = 0
    text_clean = extracted_text.lower()
    for tok in expected_tokens:
        tok_clean = tok.lower()
        # Word or boundary matching
        if re.search(rf"(?<![A-Za-z0-9]){re.escape(tok_clean)}(?![A-Za-z0-9])", text_clean):
            matched += 1
        elif tok_clean in text_clean:
            matched += 1
    return (matched, len(expected_tokens), round(matched / len(expected_tokens), 4))


# ---------------------------------------------------------------------------
# Preprocessing Pipeline (Deskew, Linear Contrast Stretching, Rescaling)
# ---------------------------------------------------------------------------

def deskew_image(cv_img: np.ndarray) -> tuple[np.ndarray, float]:
    """Detect and correct rotation skew angle between -30 and +30 degrees."""
    if len(cv_img.shape) == 3:
        gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
    else:
        gray = cv_img.copy()

    thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]
    coords = np.column_stack(np.where(thresh > 0))
    if len(coords) < 20:
        return cv_img, 0.0

    rect = cv2.minAreaRect(coords)
    angle = rect[-1]
    if angle < -45:
        angle = -(90 + angle)
    elif angle > 45:
        angle = 90 - angle
    else:
        angle = -angle

    if 0.5 <= abs(angle) <= 35.0:
        (h, w) = cv_img.shape[:2]
        center = (w // 2, h // 2)
        M = cv2.getRotationMatrix2D(center, angle, 1.0)
        rotated = cv2.warpAffine(
            cv_img,
            M,
            (w, h),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=(255, 255, 255) if len(cv_img.shape) == 3 else 255,
        )
        return rotated, round(angle, 2)
    return cv_img, 0.0


def normalize_contrast(cv_img: np.ndarray) -> np.ndarray:
    """Normalize contrast using min-max linear stretching without threshold clipping."""
    if len(cv_img.shape) == 3:
        gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
    else:
        gray = cv_img.copy()
    stretched = cv2.normalize(gray, None, alpha=0, beta=255, norm_type=cv2.NORM_MINMAX)
    return stretched


def rescale_image(cv_img: np.ndarray, target_height: int = 300) -> tuple[np.ndarray, float]:
    """Upscale low-resolution image to optimal OCR height (300+ pixels per line/block)."""
    h, w = cv_img.shape[:2]
    if h < target_height:
        scale = max(2.0, target_height / h)
        new_w = int(w * scale)
        new_h = int(h * scale)
        upscaled = cv2.resize(cv_img, (new_w, new_h), interpolation=cv2.INTER_CUBIC)
        return upscaled, scale
    return cv_img, 1.0


def preprocess_image_bytes(image_bytes: bytes) -> bytes:
    """Apply the unified preprocessing pipeline to raw image bytes:
    1. Decode image with OpenCV
    2. Correct rotation skew
    3. Normalize linear contrast
    4. Upscale if low-resolution (<300px height)
    5. Re-encode to clean PNG
    """
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        return image_bytes

    # 1. Deskew
    deskewed, _ = deskew_image(img)
    # 2. Linear contrast stretch
    contrast_norm = normalize_contrast(deskewed)
    # 3. Rescale if small
    rescaled, _ = rescale_image(contrast_norm, target_height=300)

    # Encode back to PNG
    success, encoded = cv2.imencode(".png", rescaled)
    if success:
        return encoded.tobytes()
    return image_bytes


# ---------------------------------------------------------------------------
# Tesseract Execution Bridge (using Docker Worker container)
# ---------------------------------------------------------------------------

def run_tesseract_ocr(image_bytes: bytes, lang: str = "eng", dpi: int = 300) -> str:
    """Execute Tesseract 5.5.0 inside the health-assistant-worker container via stdin pipe."""
    try:
        proc = subprocess.run(
            [
                "docker",
                "exec",
                "-i",
                "health-assistant-worker",
                "tesseract",
                "stdin",
                "stdout",
                "-l",
                lang,
                "--dpi",
                str(dpi),
            ],
            input=image_bytes,
            capture_output=True,
            timeout=15,
        )
        if proc.returncode == 0:
            return proc.stdout.decode("utf-8", errors="ignore").strip()
        else:
            err = proc.stderr.decode("utf-8", errors="ignore")
            logger.warning("Tesseract process error: %s", err)
            return ""
    except Exception as exc:
        logger.error("Failed to run Tesseract container bridge: %s", exc)
        return ""


# ---------------------------------------------------------------------------
# Synthetic Benchmark Fixture Generator
# ---------------------------------------------------------------------------

@dataclass
class BenchmarkFixture:
    fixture_id: str
    file_path: Path
    file_type: str  # "pdf_digital", "pdf_scanned", "image_png", "image_jpg"
    description: str
    expected_text: str
    expected_numbers: list[str]
    expected_units: list[str]
    expected_dates: list[str]
    degradation_type: str = "clean"


def create_synthetic_fixtures(output_dir: Path) -> list[BenchmarkFixture]:
    """Generate reproducible synthetic nonclinical document fixtures."""
    output_dir.mkdir(parents=True, exist_ok=True)
    fixtures: list[BenchmarkFixture] = []

    # Standard English Nonclinical Report Text
    eng_text = (
        "Nonclinical Examination Summary\n"
        "Date: 2026-05-10\n"
        "Hemoglobin: 14.5 g/dL (Reference: 13.0 - 17.0)\n"
        "Fasting Blood Glucose: 110 mg/dL (Reference: 70 - 99)\n"
        "HbA1c: 5.8%\n"
        "Platelets: 250 K/uL"
    )
    eng_numbers = ["14.5", "110", "5.8", "250", "13.0", "17.0", "70", "99"]
    eng_units = ["g/dL", "mg/dL", "%", "K/uL"]
    eng_dates = ["2026-05-10"]

    # 1. Clean Digital PDF (embedded text)
    dig_pdf_path = output_dir / "clean_digital.pdf"
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    y = 750
    for line in eng_text.split("\n"):
        c.drawString(50, y, line)
        y -= 25
    c.save()
    dig_pdf_path.write_bytes(buf.getvalue())
    fixtures.append(
        BenchmarkFixture(
            fixture_id="clean_digital_pdf",
            file_path=dig_pdf_path,
            file_type="pdf_digital",
            description="Native PDF with embedded digital text",
            expected_text=eng_text,
            expected_numbers=eng_numbers,
            expected_units=eng_units,
            expected_dates=eng_dates,
            degradation_type="clean",
        )
    )

    # Base Clean Image Generation (300 DPI equivalent)
    clean_img = Image.new("RGB", (900, 300), color="white")
    d = ImageDraw.Draw(clean_img)
    y = 30
    for line in eng_text.split("\n"):
        d.text((30, y), line, fill="black")
        y += 40

    # 2. Clean PNG Image
    clean_png_path = output_dir / "clean_sample.png"
    clean_img.save(clean_png_path, format="PNG")
    fixtures.append(
        BenchmarkFixture(
            fixture_id="clean_png",
            file_path=clean_png_path,
            file_type="image_png",
            description="Clean 300-DPI PNG image",
            expected_text=eng_text,
            expected_numbers=eng_numbers,
            expected_units=eng_units,
            expected_dates=eng_dates,
            degradation_type="clean",
        )
    )

    # 3. Clean JPEG Image
    clean_jpg_path = output_dir / "clean_sample.jpg"
    clean_img.save(clean_jpg_path, format="JPEG", quality=95)
    fixtures.append(
        BenchmarkFixture(
            fixture_id="clean_jpg",
            file_path=clean_jpg_path,
            file_type="image_jpg",
            description="Clean high-quality JPEG image",
            expected_text=eng_text,
            expected_numbers=eng_numbers,
            expected_units=eng_units,
            expected_dates=eng_dates,
            degradation_type="clean",
        )
    )

    # 4. Clean Scanned-style PDF (image embedded without text layer)
    scanned_pdf_path = output_dir / "clean_scanned.pdf"
    scanned_buf = io.BytesIO()
    c = canvas.Canvas(scanned_buf)
    # Draw image onto canvas
    img_temp_buf = io.BytesIO()
    clean_img.save(img_temp_buf, format="PNG")
    img_temp_buf.seek(0)
    from reportlab.lib.utils import ImageReader
    c.drawImage(ImageReader(img_temp_buf), 50, 450, width=500, height=200)
    c.save()
    scanned_pdf_path.write_bytes(scanned_buf.getvalue())
    fixtures.append(
        BenchmarkFixture(
            fixture_id="clean_scanned_pdf",
            file_path=scanned_pdf_path,
            file_type="pdf_scanned",
            description="Scanned-style PDF containing raster image without text layer",
            expected_text=eng_text,
            expected_numbers=eng_numbers,
            expected_units=eng_units,
            expected_dates=eng_dates,
            degradation_type="scanned",
        )
    )

    # 5. Bilingual Hindi Clean Image
    hindi_font_path = "C:/Windows/Fonts/Nirmala.ttc"
    has_hindi_font = os.path.exists(hindi_font_path)
    hindi_text = (
        "रक्त शर्करा: 126 mg/dL\n"
        "एचबीए1सी: 5.8 %\n"
        "दवा: 500 mg"
    )
    hindi_img = Image.new("RGB", (900, 250), color="white")
    d_hi = ImageDraw.Draw(hindi_img)
    if has_hindi_font:
        try:
            h_font = ImageFont.truetype(hindi_font_path, 32)
            d_hi.text((30, 30), hindi_text, font=h_font, fill="black")
        except Exception:
            d_hi.text((30, 30), hindi_text, fill="black")
    else:
        d_hi.text((30, 30), hindi_text, fill="black")

    hindi_png_path = output_dir / "hindi_sample.png"
    hindi_img.save(hindi_png_path, format="PNG")
    fixtures.append(
        BenchmarkFixture(
            fixture_id="hindi_bilingual_png",
            file_path=hindi_png_path,
            file_type="image_png",
            description="Bilingual Devanagari Hindi text rendered with Nirmala font",
            expected_text=hindi_text,
            expected_numbers=["126", "5.8", "500"],
            expected_units=["mg/dL", "%", "mg"],
            expected_dates=[],
            degradation_type="bilingual",
        )
    )

    # 6. Skewed Image (+5 degrees rotation)
    skew5_img = clean_img.rotate(5, resample=Image.Resampling.BICUBIC, expand=True, fillcolor="white")
    skew5_path = output_dir / "skewed_5deg.png"
    skew5_img.save(skew5_path, format="PNG")
    fixtures.append(
        BenchmarkFixture(
            fixture_id="skewed_5deg_png",
            file_path=skew5_path,
            file_type="image_png",
            description="Controlled +5 degree scan rotation skew",
            expected_text=eng_text,
            expected_numbers=eng_numbers,
            expected_units=eng_units,
            expected_dates=eng_dates,
            degradation_type="skew",
        )
    )

    # 7. Skewed Image (+10 degrees rotation)
    skew10_img = clean_img.rotate(10, resample=Image.Resampling.BICUBIC, expand=True, fillcolor="white")
    skew10_path = output_dir / "skewed_10deg.png"
    skew10_img.save(skew10_path, format="PNG")
    fixtures.append(
        BenchmarkFixture(
            fixture_id="skewed_10deg_png",
            file_path=skew10_path,
            file_type="image_png",
            description="Controlled +10 degree scan rotation skew",
            expected_text=eng_text,
            expected_numbers=eng_numbers,
            expected_units=eng_units,
            expected_dates=eng_dates,
            degradation_type="skew",
        )
    )

    # 8. Low-Contrast Faded Scan (gray text on light gray background)
    low_con_img = Image.new("RGB", (900, 300), color=(220, 220, 220))
    d_lc = ImageDraw.Draw(low_con_img)
    y = 30
    for line in eng_text.split("\n"):
        d_lc.text((30, y), line, fill=(150, 150, 150))
        y += 40
    low_con_path = output_dir / "low_contrast.png"
    low_con_img.save(low_con_path, format="PNG")
    fixtures.append(
        BenchmarkFixture(
            fixture_id="low_contrast_png",
            file_path=low_con_path,
            file_type="image_png",
            description="Low-contrast faded scan simulation",
            expected_text=eng_text,
            expected_numbers=eng_numbers,
            expected_units=eng_units,
            expected_dates=eng_dates,
            degradation_type="contrast",
        )
    )

    # 9. Noisy Scan (speckle / Gaussian noise degradation)
    noisy_np = np.array(clean_img).astype(np.float32)
    noise = np.random.normal(0, 15, noisy_np.shape)
    noisy_np = np.clip(noisy_np + noise, 0, 255).astype(np.uint8)
    noisy_img = Image.fromarray(noisy_np)
    noisy_path = output_dir / "noisy_speckle.png"
    noisy_img.save(noisy_path, format="PNG")
    fixtures.append(
        BenchmarkFixture(
            fixture_id="noisy_speckle_png",
            file_path=noisy_path,
            file_type="image_png",
            description="Noisy scanner speckle simulation",
            expected_text=eng_text,
            expected_numbers=eng_numbers,
            expected_units=eng_units,
            expected_dates=eng_dates,
            degradation_type="noise",
        )
    )

    # 10. Low-Resolution 72-DPI Scan (small dimensions)
    low_res_img = clean_img.resize((360, 120), resample=Image.Resampling.BOX)
    low_res_path = output_dir / "low_res_72dpi.png"
    low_res_img.save(low_res_path, format="PNG")
    fixtures.append(
        BenchmarkFixture(
            fixture_id="low_res_72dpi_png",
            file_path=low_res_path,
            file_type="image_png",
            description="Low-resolution 72-DPI preview image",
            expected_text=eng_text,
            expected_numbers=eng_numbers,
            expected_units=eng_units,
            expected_dates=eng_dates,
            degradation_type="resolution",
        )
    )

    return fixtures


# ---------------------------------------------------------------------------
# Benchmark Evaluation Execution
# ---------------------------------------------------------------------------

@dataclass
class SampleEvaluationResult:
    fixture_id: str
    description: str
    degradation_type: str
    mode: str  # "baseline" or "preprocessed"
    success: bool
    cer: float
    wer: float
    number_accuracy: float
    unit_accuracy: float
    date_accuracy: float
    runtime_ms: float
    extracted_text_preview: str


def evaluate_sample(fixture: BenchmarkFixture, preprocess: bool = False) -> SampleEvaluationResult:
    """Run extraction on a single fixture and compute comprehensive metrics."""
    t0 = time.perf_counter()
    extracted_text = ""
    mode_name = "preprocessed" if preprocess else "baseline"

    try:
        # Case 1: Digital PDF
        if fixture.file_type == "pdf_digital":
            reader = PdfReader(fixture.file_path)
            extracted_text = "\n".join([p.extract_text() or "" for p in reader.pages]).strip()

        # Case 2: Scanned PDF
        elif fixture.file_type == "pdf_scanned":
            # Extract image bytes from PDF using pypdf image reader or native rendering
            reader = PdfReader(fixture.file_path)
            images: list[bytes] = []
            for p in reader.pages:
                for img_obj in p.images:
                    images.append(img_obj.data)

            combined_text = []
            for img_bytes in images:
                if preprocess:
                    img_bytes = preprocess_image_bytes(img_bytes)
                page_text = run_tesseract_ocr(img_bytes, lang="eng", dpi=300)
                if page_text:
                    combined_text.append(page_text)
            extracted_text = "\n\n".join(combined_text).strip()

        # Case 3: Image files (PNG, JPG)
        else:
            raw_bytes = fixture.file_path.read_bytes()
            if preprocess:
                raw_bytes = preprocess_image_bytes(raw_bytes)
            extracted_text = run_tesseract_ocr(raw_bytes, lang="eng", dpi=300)

        elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
        success = bool(extracted_text.strip())

    except Exception as err:
        logger.error("Evaluation failure on %s: %s", fixture.fixture_id, err)
        elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
        extracted_text = ""
        success = False

    # Compute CER & WER
    cer = compute_cer(fixture.expected_text, extracted_text)
    wer = compute_wer(fixture.expected_text, extracted_text)

    # Compute Field Accuracies
    _, _, num_acc = evaluate_field_accuracy(fixture.expected_numbers, extracted_text)
    _, _, unit_acc = evaluate_field_accuracy(fixture.expected_units, extracted_text)
    _, _, date_acc = evaluate_field_accuracy(fixture.expected_dates, extracted_text)

    preview = (extracted_text.replace("\n", " ")[:60] + "...") if len(extracted_text) > 60 else extracted_text

    return SampleEvaluationResult(
        fixture_id=fixture.fixture_id,
        description=fixture.description,
        degradation_type=fixture.degradation_type,
        mode=mode_name,
        success=success,
        cer=cer,
        wer=wer,
        number_accuracy=num_acc,
        unit_accuracy=unit_acc,
        date_accuracy=date_acc,
        runtime_ms=elapsed_ms,
        extracted_text_preview=preview,
    )


def run_full_benchmark(output_dir: Path | None = None) -> dict[str, Any]:
    """Execute the full benchmark suite across all fixtures and modes."""
    if output_dir is None:
        output_dir = Path(__file__).parent / "fixtures"

    fixtures = create_synthetic_fixtures(output_dir)
    results: list[SampleEvaluationResult] = []

    for fix in fixtures:
        # Run Baseline
        res_baseline = evaluate_sample(fix, preprocess=False)
        results.append(res_baseline)

        # Run Preprocessed
        res_preprocessed = evaluate_sample(fix, preprocess=True)
        results.append(res_preprocessed)

    # Aggregate summaries
    baseline_results = [r for r in results if r.mode == "baseline"]
    preprocessed_results = [r for r in results if r.mode == "preprocessed"]

    def avg(lst: list[float]) -> float:
        return round(sum(lst) / len(lst), 4) if lst else 0.0

    summary = {
        "total_fixtures": len(fixtures),
        "total_evaluations": len(results),
        "baseline": {
            "success_rate": round(sum(1 for r in baseline_results if r.success) / len(baseline_results), 4),
            "mean_cer": avg([r.cer for r in baseline_results]),
            "mean_wer": avg([r.wer for r in baseline_results]),
            "mean_number_accuracy": avg([r.number_accuracy for r in baseline_results]),
            "mean_unit_accuracy": avg([r.unit_accuracy for r in baseline_results]),
            "mean_date_accuracy": avg([r.date_accuracy for r in baseline_results]),
            "total_runtime_ms": round(sum(r.runtime_ms for r in baseline_results), 2),
        },
        "preprocessed": {
            "success_rate": round(sum(1 for r in preprocessed_results if r.success) / len(preprocessed_results), 4),
            "mean_cer": avg([r.cer for r in preprocessed_results]),
            "mean_wer": avg([r.wer for r in preprocessed_results]),
            "mean_number_accuracy": avg([r.number_accuracy for r in preprocessed_results]),
            "mean_unit_accuracy": avg([r.unit_accuracy for r in preprocessed_results]),
            "mean_date_accuracy": avg([r.date_accuracy for r in preprocessed_results]),
            "total_runtime_ms": round(sum(r.runtime_ms for r in preprocessed_results), 2),
        },
        "detailed_results": [r.__dict__ for r in results],
    }

    return summary


if __name__ == "__main__":
    benchmark_dir = Path(__file__).parent / "fixtures"
    data = run_full_benchmark(benchmark_dir)
    print(json.dumps(data, indent=2))

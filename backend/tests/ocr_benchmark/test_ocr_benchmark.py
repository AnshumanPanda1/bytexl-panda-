"""Unit tests for OCR benchmark suite, metrics, and image preprocessing functions."""

import io
import os
import unittest
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw

from backend.tests.ocr_benchmark.benchmark_suite import (
    compute_cer,
    compute_wer,
    create_synthetic_fixtures,
    deskew_image,
    evaluate_field_accuracy,
    levenshtein_distance,
    normalize_contrast,
    preprocess_image_bytes,
    rescale_image,
)


class TestOCRBenchmarkMetrics(unittest.TestCase):
    """Test mathematical accuracy of CER, WER, and Levenshtein metrics."""

    def test_levenshtein_identical_strings(self):
        """Identical strings have zero distance."""
        self.assertEqual(levenshtein_distance("Hemoglobin: 14.5 g/dL", "Hemoglobin: 14.5 g/dL"), 0)
        self.assertEqual(levenshtein_distance([], []), 0)

    def test_levenshtein_known_distance(self):
        """Standard Levenshtein known edit distances."""
        self.assertEqual(levenshtein_distance("kitten", "sitting"), 3)
        self.assertEqual(levenshtein_distance("14.5", "145"), 1)  # 1 deletion (period)

    def test_compute_cer_zero_for_perfect_match(self):
        """CER is 0.0 for identical text."""
        ref = "Fasting Blood Glucose: 110 mg/dL"
        hyp = "Fasting Blood Glucose: 110 mg/dL"
        self.assertEqual(compute_cer(ref, hyp), 0.0)

    def test_compute_cer_calculates_proportional_error(self):
        """CER calculates correct error fraction."""
        ref = "1234567890"  # length 10
        hyp = "12345X7890"  # 1 substitution -> 0.1
        self.assertEqual(compute_cer(ref, hyp), 0.1)

    def test_compute_wer_token_level(self):
        """WER computes word-level error distance."""
        ref = "Hemoglobin is 14.5 g/dL"
        hyp = "Hemoglobin is 145 g/dL"  # 1 word substitution out of 4 -> 0.25
        self.assertEqual(compute_wer(ref, hyp), 0.25)

    def test_evaluate_field_accuracy_identifies_numbers_and_units(self):
        """Field evaluation matches expected critical numbers, decimals, and units."""
        text = "Laboratory Result: Hemoglobin: 14.5 g/dL, Glucose: 110 mg/dL on 2026-05-10"
        numbers = ["14.5", "110"]
        units = ["g/dL", "mg/dL"]
        dates = ["2026-05-10"]

        matched_n, total_n, acc_n = evaluate_field_accuracy(numbers, text)
        self.assertEqual(matched_n, 2)
        self.assertEqual(acc_n, 1.0)

        matched_u, total_u, acc_u = evaluate_field_accuracy(units, text)
        self.assertEqual(matched_u, 2)
        self.assertEqual(acc_u, 1.0)

        matched_d, total_d, acc_d = evaluate_field_accuracy(dates, text)
        self.assertEqual(matched_d, 1)
        self.assertEqual(acc_d, 1.0)


class TestImagePreprocessingPipeline(unittest.TestCase):
    """Test image preprocessing transformations (deskew, contrast, rescale)."""

    def test_deskew_image_detects_and_corrects_rotation(self):
        """Deskew algorithm detects +5 degree rotation and rotates back."""
        img = Image.new("RGB", (600, 150), color="white")
        d = ImageDraw.Draw(img)
        d.text((30, 40), "Platelets: 250 K/uL Reference: 150-450", fill="black")
        skewed = img.rotate(5, resample=Image.Resampling.BICUBIC, expand=True, fillcolor="white")
        cv_img = cv2.cvtColor(np.array(skewed), cv2.COLOR_RGB2BGR)

        deskewed, detected_angle = deskew_image(cv_img)
        # Detected angle should be approximately -5.0 degrees (within +/- 1.5 deg tolerance)
        self.assertAlmostEqual(detected_angle, -5.0, delta=1.5)
        self.assertEqual(deskewed.shape[0], cv_img.shape[0])

    def test_normalize_contrast_stretches_dynamic_range(self):
        """Contrast normalization stretches min-max range without clipping."""
        # Low contrast image: pixel values between 150 and 200
        low_contrast = np.full((100, 100), 180, dtype=np.uint8)
        low_contrast[30:70, 30:70] = 150
        stretched = normalize_contrast(low_contrast)
        self.assertEqual(stretched.min(), 0)
        self.assertEqual(stretched.max(), 255)

    def test_rescale_image_upscales_small_height(self):
        """Small images are upscaled to 300+ px height for optimal OCR rendering."""
        small_img = np.full((100, 300, 3), 255, dtype=np.uint8)
        upscaled, scale = rescale_image(small_img, target_height=300)
        self.assertGreaterEqual(upscaled.shape[0], 300)
        self.assertGreaterEqual(scale, 2.0)

    def test_preprocess_image_bytes_end_to_end(self):
        """preprocess_image_bytes decodes, processes, and returns valid PNG bytes."""
        img = Image.new("RGB", (400, 80), color="white")
        d = ImageDraw.Draw(img)
        d.text((10, 10), "Test Preprocessing", fill="black")
        buf = io.BytesIO()
        img.save(buf, format="PNG")

        out_bytes = preprocess_image_bytes(buf.getvalue())
        self.assertIsInstance(out_bytes, bytes)
        self.assertGreater(len(out_bytes), 0)


class TestBenchmarkFixtureGeneration(unittest.TestCase):
    """Test that all 10 synthetic fixtures are generated reproducibly."""

    def test_synthetic_fixtures_created_with_expected_formats(self):
        """Generates all 10 benchmark fixtures with ground truth text and metadata."""
        tmp_dir = Path("backend/tests/ocr_benchmark/test_fixtures_tmp")
        fixtures = create_synthetic_fixtures(tmp_dir)

        self.assertEqual(len(fixtures), 10)
        fixture_ids = [f.fixture_id for f in fixtures]
        expected_ids = [
            "clean_digital_pdf",
            "clean_png",
            "clean_jpg",
            "clean_scanned_pdf",
            "hindi_bilingual_png",
            "skewed_5deg_png",
            "skewed_10deg_png",
            "low_contrast_png",
            "noisy_speckle_png",
            "low_res_72dpi_png",
        ]
        for eid in expected_ids:
            self.assertIn(eid, fixture_ids)

        for fix in fixtures:
            self.assertTrue(fix.file_path.exists(), f"File {fix.file_path} must exist")
            self.assertGreater(len(fix.expected_text), 0)

        # Cleanup temporary test fixtures
        for f in fixtures:
            if f.file_path.exists():
                f.file_path.unlink()
        if tmp_dir.exists():
            tmp_dir.rmdir()


if __name__ == "__main__":
    unittest.main()

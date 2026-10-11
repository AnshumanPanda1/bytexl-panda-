from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.services.ai_summary_service import CAVEAT_EN, CAVEAT_HI, AISummaryService


@pytest.mark.asyncio
async def test_p2_01_grounded_summary_has_source_references():
    """P2-01: Verify summary mentions only supplied facts with source references."""
    service = AISummaryService(api_key=None)  # Uses deterministic fallback engine
    patient_id = uuid4()
    doc_id = uuid4()

    facts = [
        {
            "id": "obs-001",
            "fact_type": "HbA1c",
            "value": "5.7",
            "unit": "%",
            "reference_range": "4.0 - 5.6 %",
            "document_id": str(doc_id),
            "page": 1,
        }
    ]

    summary = await service.generate_grounded_summary(
        patient_id=patient_id,
        document_ids=[doc_id],
        facts=facts,
        language="en",
    )

    assert summary.patient_id == patient_id
    assert summary.document_ids == [doc_id]
    assert summary.language == "en"
    assert summary.caveat == CAVEAT_EN
    assert len(summary.claims) == 1

    claim = summary.claims[0]
    assert claim.source_document_id == str(doc_id)
    assert claim.source_page == 1
    assert "HbA1c: 5.7 %" in claim.text
    assert "Reference range: 4.0 - 5.6 %" in claim.text


@pytest.mark.asyncio
async def test_p2_02_no_reference_range_does_not_guess_abnormality():
    """P2-02: Verify test with null reference range is NOT called abnormal or high."""
    service = AISummaryService(api_key=None)
    patient_id = uuid4()
    doc_id = uuid4()

    facts = [
        {
            "id": "obs-002",
            "fact_type": "Serum Creatinine",
            "value": "1.2",
            "unit": "mg/dL",
            "reference_range": None,  # No reference range stated
            "document_id": str(doc_id),
            "page": 1,
        }
    ]

    summary = await service.generate_grounded_summary(
        patient_id=patient_id,
        document_ids=[doc_id],
        facts=facts,
        language="en",
    )

    claim = summary.claims[0]
    assert "No reference range stated in source" in claim.text
    assert "abnormal" not in claim.text.lower()
    assert "high" not in claim.text.lower()


@pytest.mark.asyncio
async def test_p2_03_english_hindi_bilingual_parity_preserves_values_and_units():
    """P2-03: Verify English and Hindi summaries preserve exact numeric values."""
    service = AISummaryService(api_key=None)
    patient_id = uuid4()
    doc_id = uuid4()

    facts = [
        {
            "id": "obs-003",
            "fact_type": "Fasting Blood Glucose",
            "value": "110",
            "unit": "mg/dL",
            "reference_range": "70 - 99 mg/dL",
            "document_id": str(doc_id),
            "page": 1,
        }
    ]

    en_summary = await service.generate_grounded_summary(
        patient_id=patient_id, document_ids=[doc_id], facts=facts, language="en"
    )
    hi_summary = await service.generate_grounded_summary(
        patient_id=patient_id, document_ids=[doc_id], facts=facts, language="hi"
    )

    assert en_summary.language == "en"
    assert hi_summary.language == "hi"
    assert hi_summary.caveat == CAVEAT_HI

    # Both preserve numeric value '110' and unit 'mg/dL'
    assert "110 mg/dL" in en_summary.claims[0].text
    assert "110 mg/dL" in hi_summary.claims[0].text


@pytest.mark.asyncio
async def test_p2_04_provider_failure_fallback_behavior():
    """P2-04: Verify provider failure gracefully falls back to deterministic summary."""
    service = AISummaryService(api_key="mock-api-key")
    patient_id = uuid4()
    doc_id = uuid4()

    facts = [
        {
            "id": "obs-004",
            "fact_type": "Hemoglobin",
            "value": "13.5",
            "unit": "g/dL",
            "reference_range": "12.0 - 15.5 g/dL",
            "document_id": str(doc_id),
            "page": 1,
        }
    ]

    # Simulate LLM provider exception (500 or timeout)
    with patch.object(
        service, "_call_llm_summary_api", side_effect=Exception("Provider 503 Service Unavailable")
    ):
        summary = await service.generate_grounded_summary(
            patient_id=patient_id, document_ids=[doc_id], facts=facts, language="en"
        )

        assert summary is not None
        assert summary.patient_id == patient_id
        assert len(summary.sections) > 0
        assert "Hemoglobin: 13.5 g/dL" in summary.claims[0].text


@pytest.mark.asyncio
async def test_p2_05_summary_invalidation_stale_propagation():
    """P2-05: Verify correcting a fact marks existing summaries stale."""
    service = AISummaryService(api_key=None)
    patient_id = uuid4()

    mock_db = AsyncMock()
    mock_db.execute.return_value.rowcount = 2

    count = await service.invalidate_summaries(mock_db, patient_id=patient_id)
    assert count == 2
    mock_db.execute.assert_called_once()
    mock_db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_p2_06_secret_hygiene():
    """P2-06: Verify secret key is not exposed in public properties or response objects."""
    service = AISummaryService(api_key="secret-key-12345")
    resp = await service.generate_grounded_summary(
        patient_id=uuid4(), document_ids=[], facts=[], language="en"
    )

    resp_dict = resp.model_dump()
    resp_str = str(resp_dict)

    assert "secret-key-12345" not in resp_str
    assert "secret-key-12345" not in resp.caveat

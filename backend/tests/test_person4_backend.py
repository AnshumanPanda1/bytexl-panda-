# ruff: noqa: E501
"""Tests for Person 4: Canonical Data Model, Interoperability, FHIR Export, and Mock ABDM.

Covers:
- Model extensions (Observation, Medication, ClinicalEvent, PatientHealthSummary, MockAbdmImportRecord)
- Checksum deduplication & Mock ABDM preview/confirmation
- Document facts retrieval, corrections, and audit logging
- Automatic health summary invalidation on corrections
- Multilingual summary support (English & Hindi)
- Patient timeline aggregation, date normalization, and unknown date ordering
- FHIR R4-inspired export bundle generation, resource types, and references
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.errors import AuthorizationError, NotFoundError
from app.models.clinical_event import ClinicalEvent
from app.models.document_model import DocumentModel
from app.models.enums import ClinicalEventStatus, Gender, Role
from app.models.fhir.medication import Medication
from app.models.fhir.patient import Observation, Patient
from app.models.health_summary_model import PatientHealthSummary
from app.models.mock_abdm_model import MockAbdmImportRecord
from app.schemas.facts import FactCorrectionRequest
from app.schemas.health_summary import PatientHealthSummaryCreate
from app.schemas.mock_abdm import (
    SyntheticCondition,
    SyntheticMedication,
    SyntheticObservation,
    SyntheticRecordBundle,
)
from app.schemas.user import TokenData
from app.services.facts_service import correct_fact, get_document_facts
from app.services.fhir_export_service import export_patient_fhir_bundle
from app.services.health_summary_service import (
    create_summary,
    invalidate_patient_summaries,
)
from app.services.mock_abdm_service import (
    compute_bundle_checksum,
    confirm_mock_abdm_import,
    preview_mock_abdm_record,
)
from app.services.timeline_service import get_patient_timeline

# -----------------------------------------------------------------------------
# 1. Model Extensions and Canonical Representations
# -----------------------------------------------------------------------------


def test_health_summary_model_attributes_and_dict():
    """Verify PatientHealthSummary model fields, language support, and dictionary serialization."""
    summary_id = uuid.uuid4()
    patient_id = uuid.uuid4()
    tenant_id = uuid.uuid4()

    summary = PatientHealthSummary(
        id=summary_id,
        patient_id=patient_id,
        tenant_id=tenant_id,
        title="Comprehensive Health Overview",
        summary_text="Patient has elevated fasting glucose. Recommended dietary modifications.",
        language="en",
        source_references=[{"type": "observation", "id": str(uuid.uuid4())}],
        is_stale=False,
    )

    data = summary.to_dict()
    assert data["id"] == str(summary_id)
    assert data["patient_id"] == str(patient_id)
    assert data["title"] == "Comprehensive Health Overview"
    assert "elevated fasting glucose" in data["summary_text"]
    assert data["is_stale"] is False
    assert data["language"] == "en"


def test_health_summary_bilingual_support():
    """Verify PatientHealthSummary correctly stores Hindi medical summaries."""
    summary_hi = PatientHealthSummary(
        id=uuid.uuid4(),
        patient_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        title="स्वास्थ्य सारांश",
        summary_text="मरीज का रक्तचाप सामान्य सीमा के भीतर है। नियमित व्यायाम जारी रखें।",
        language="hi",
        is_stale=False,
    )
    data = summary_hi.to_dict()
    assert data["language"] == "hi"
    assert "रक्तचाप सामान्य" in data["summary_text"]


def test_mock_abdm_model_attributes_and_dict():
    """Verify MockAbdmImportRecord model and deduplication checksum."""
    record_id = uuid.uuid4()
    patient_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    checksum = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

    record = MockAbdmImportRecord(
        id=record_id,
        tenant_id=tenant_id,
        patient_id=patient_id,
        source_system="mock_abdm",
        external_record_id="EXT-101",
        status="CONFIRMED",
        checksum=checksum,
        provenance={"provider": "Simulated Hospital", "fhir_version": "R4"},
        mapped_resources={"observations": 2, "medications": 1},
    )

    data = record.to_dict()
    assert data["id"] == str(record_id)
    assert data["checksum"] == checksum
    assert data["status"] == "CONFIRMED"
    assert data["mapped_resources"]["observations"] == 2


def test_observation_and_medication_model_extensions():
    """Verify Observation and Medication models hold trace provenance and review status."""
    doc_id = uuid.uuid4()

    obs = Observation(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        patient_id=uuid.uuid4(),
        code={"text": "Hemoglobin"},
        value_quantity={"value": 14.2, "unit": "g/dL"},
        original_text="Hb: 14.2 g/dL (manual entry)",
        page_number=1,
        confidence=0.96,
        review_status="reviewed",
        document_id=doc_id,
    )
    obs_dict = obs.to_dict()
    assert obs_dict["original_text"] == "Hb: 14.2 g/dL (manual entry)"
    assert obs_dict["page_number"] == 1
    assert obs_dict["confidence"] == 0.96
    assert obs_dict["review_status"] == "reviewed"
    assert obs_dict["document_id"] == str(doc_id)

    med = Medication(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        patient_id=uuid.uuid4(),
        code={"text": "Metformin 500mg"},
        dosage="500 mg",
        frequency={"instruction": "Once daily with food"},
        original_text="Metformin 500 mg OD",
        page_number=2,
        confidence=0.92,
        review_status="extracted",
        document_id=doc_id,
    )
    med_dict = med.to_dict()
    assert med_dict["original_text"] == "Metformin 500 mg OD"
    assert med_dict["page_number"] == 2
    assert med_dict["confidence"] == 0.92
    assert med_dict["review_status"] == "extracted"


def test_clinical_event_fhir_condition_mapping():
    """Verify ClinicalEvent generates valid FHIR Condition dictionary with evidence and document link."""
    event_id = uuid.uuid4()
    patient_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    doc_id = uuid.uuid4()

    event = ClinicalEvent(
        id=event_id,
        tenant_id=tenant_id,
        patient_id=patient_id,
        status=ClinicalEventStatus.ACTIVE,
        title="Type 2 Diabetes Mellitus",
        description="Chronically elevated fasting glucose",
        onset_date=datetime(2026, 3, 15, tzinfo=UTC),
        original_text="Dx: T2DM moderate",
        page_number=3,
        confidence=0.88,
        review_status="confirmed",
        document_id=doc_id,
    )

    fhir_dict = event.to_fhir_dict()
    assert fhir_dict["resourceType"] == "Condition"
    assert fhir_dict["id"] == str(event_id)
    assert fhir_dict["subject"]["reference"] == f"Patient/{patient_id}"
    assert fhir_dict["code"]["text"] == "Type 2 Diabetes Mellitus"
    assert fhir_dict["evidence"][0]["detail"][0]["reference"] == f"DocumentReference/{doc_id}"


# -----------------------------------------------------------------------------
# 2. Checksum Calculation and Mock ABDM Workflow
# -----------------------------------------------------------------------------


def test_mock_abdm_checksum_deterministic():
    """Verify SHA-256 fingerprint is deterministic and unaffected by observation/medication list ordering."""
    obs1 = SyntheticObservation(test_name="Glucose", value=100.0, unit="mg/dL")
    obs2 = SyntheticObservation(test_name="Cholesterol", value=180.0, unit="mg/dL")

    med1 = SyntheticMedication(name="Aspirin", dosage="75mg")
    med2 = SyntheticMedication(name="Metformin", dosage="500mg")

    bundle_a = SyntheticRecordBundle(
        external_record_id="REC-001",
        source_system="mock_abdm",
        observations=[obs1, obs2],
        medications=[med1, med2],
    )

    bundle_b = SyntheticRecordBundle(
        external_record_id="REC-001",
        source_system="mock_abdm",
        observations=[obs2, obs1],  # reversed order
        medications=[med2, med1],  # reversed order
    )

    ck_a = compute_bundle_checksum(bundle_a)
    ck_b = compute_bundle_checksum(bundle_b)
    assert ck_a == ck_b
    assert len(ck_a) == 64


@pytest.mark.asyncio
async def test_mock_abdm_preview():
    """Verify generating import preview for synthetic ABDM bundle."""
    db = AsyncMock()
    patient_id = uuid.uuid4()
    tenant_id = uuid.uuid4()

    bundle = SyntheticRecordBundle(
        external_record_id="SIM-12345",
        source_system="mock_abdm",
        facility_name="Apollo Clinic Mock",
        observations=[SyntheticObservation(test_name="Fasting Glucose", value=110.0, unit="mg/dL")],
    )

    # Mock DB query for duplicate check returning None (no prior import)
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    db.execute.return_value = result_mock

    preview = await preview_mock_abdm_record(db, tenant_id, patient_id, bundle)
    assert preview.is_duplicate is False
    assert preview.observation_count == 1
    assert preview.checksum == compute_bundle_checksum(bundle)
    assert len(preview.warnings) == 0


@pytest.mark.asyncio
async def test_mock_abdm_duplicate_detection_in_preview():
    """Verify duplicate record is flagged with warning in preview."""
    db = AsyncMock()
    patient_id = uuid.uuid4()
    tenant_id = uuid.uuid4()

    bundle = SyntheticRecordBundle(
        external_record_id="SIM-DUP",
        source_system="mock_abdm",
    )
    checksum = compute_bundle_checksum(bundle)

    existing_record = MockAbdmImportRecord(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        patient_id=patient_id,
        status="CONFIRMED",
        checksum=checksum,
        imported_at=datetime(2026, 4, 1, tzinfo=UTC),
    )

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = existing_record
    db.execute.return_value = result_mock

    preview = await preview_mock_abdm_record(db, tenant_id, patient_id, bundle)
    assert preview.is_duplicate is True
    assert preview.duplicate_import_id == str(existing_record.id)
    assert len(preview.warnings) > 0


@pytest.mark.asyncio
async def test_mock_abdm_duplicate_rejection_on_confirm():
    """Verify confirming an already-imported bundle returns duplicate status without duplicate creation."""
    db = AsyncMock()
    patient_id = uuid.uuid4()
    tenant_id = uuid.uuid4()

    bundle = SyntheticRecordBundle(
        external_record_id="SIM-DUP-CONFIRM",
        source_system="mock_abdm",
    )
    checksum = compute_bundle_checksum(bundle)

    existing_record = MockAbdmImportRecord(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        patient_id=patient_id,
        status="CONFIRMED",
        checksum=checksum,
    )

    res_dup = MagicMock()
    res_dup.scalar_one_or_none.return_value = existing_record
    db.execute.return_value = res_dup

    current_user = TokenData(user_id=uuid.uuid4(), tenant_id=tenant_id, role="TENANT_ADMIN")

    confirm_res = await confirm_mock_abdm_import(db, tenant_id, patient_id, bundle, current_user)
    assert confirm_res.is_duplicate is True
    assert confirm_res.status == "duplicate"
    assert confirm_res.import_id == str(existing_record.id)


# -----------------------------------------------------------------------------
# 3. Document Facts and Fact Corrections
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_facts_service_gather_document_facts():
    """Verify document facts aggregation extracts observations, medications, and conditions."""
    db = AsyncMock()
    doc_id = uuid.uuid4()
    tenant_id = uuid.uuid4()

    doc_mock = DocumentModel(
        id=doc_id,
        tenant_id=tenant_id,
        filename="lab_report.pdf",
        status="PROCESSED",
    )

    obs_mock = Observation(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        code={"text": "Platelet Count"},
        value_quantity={"value": 250000, "unit": "/uL"},
        original_text="Platelets: 250k",
        page_number=1,
        confidence=0.95,
        review_status="extracted",
        document_id=doc_id,
    )

    med_mock = Medication(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        code={"text": "Atorvastatin"},
        dosage="10mg once daily",
        original_text="Atorva 10 OD",
        page_number=1,
        confidence=0.90,
        review_status="extracted",
        document_id=doc_id,
    )

    # Setup execute returns for doc, observations, medications, and clinical events
    res_doc = MagicMock()
    res_doc.scalar_one_or_none.return_value = doc_mock

    res_obs = MagicMock()
    res_obs.scalars.return_value.all.return_value = [obs_mock]

    res_med = MagicMock()
    res_med.scalars.return_value.all.return_value = [med_mock]

    res_cond = MagicMock()
    res_cond.scalars.return_value.all.return_value = []

    db.execute.side_effect = [res_doc, res_obs, res_med, res_cond]

    facts = await get_document_facts(db, tenant_id, doc_id)
    assert facts.document_id == str(doc_id)
    assert facts.status == "PROCESSED"
    assert len(facts.observations) == 1
    assert facts.observations[0]["code"]["text"] == "Platelet Count"
    assert facts.observations[0]["original_text"] == "Platelets: 250k"
    assert len(facts.medications) == 1
    assert facts.medications[0]["code"]["text"] == "Atorvastatin"


@pytest.mark.asyncio
async def test_fact_correction_preserves_original_and_invalidates_summary():
    """Verify fact correction updates normalized value, keeps original text, logs audit, and marks summaries stale."""
    db = AsyncMock()
    obs_id = uuid.uuid4()
    patient_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()

    obs = Observation(
        id=obs_id,
        patient_id=patient_id,
        tenant_id=tenant_id,
        code={"text": "Serum Potassium"},
        value_quantity={"value": 3.8, "unit": "mmol/L"},
        original_text="K+: 3.8",
        review_status="extracted",
    )

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = obs
    db.execute.return_value = result_mock

    current_user = TokenData(user_id=user_id, tenant_id=tenant_id, role="DOCTOR")

    with (
        patch(
            "app.services.facts_service.invalidate_patient_summaries", new_callable=AsyncMock
        ) as mock_invalidate,
        patch("app.services.facts_service.log_audit_action", new_callable=AsyncMock) as mock_audit,
    ):
        correction_req = FactCorrectionRequest(
            fact_type="observation",
            fact_id=str(obs_id),
            updates={"value": 4.1},
            correction_reason="OCR mistook 4.1 for 3.8",
        )

        response = await correct_fact(db, tenant_id, current_user, correction_req)

        assert response.fact_id == str(obs_id)
        assert response.old_value["value_quantity"]["value"] == 3.8
        assert response.new_value["value_quantity"]["value"] == 4.1

        # Check in-memory object modifications
        assert obs.review_status == "user_corrected"
        assert obs.original_text == "K+: 3.8"  # Original preserved!
        assert obs.value_quantity["value"] == 4.1

        db.commit.assert_called_once()
        mock_audit.assert_called_once()
        mock_invalidate.assert_called_once_with(
            db,
            tenant_id,
            patient_id,
            reason="User corrected observation fact: OCR mistook 4.1 for 3.8",
        )


# -----------------------------------------------------------------------------
# 4. Patient Health Summaries and Staleness
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_summary_create_and_invalidation():
    """Verify health summary creation and staleness invalidation."""
    db = AsyncMock()
    patient_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()

    req = PatientHealthSummaryCreate(
        title="Lipid Panel Summary",
        summary_text="Patient's cholesterol levels are well managed.",
        language="en",
        source_references=[{"test": "lipid_panel"}],
    )

    current_user = TokenData(user_id=user_id, tenant_id=tenant_id, role="DOCTOR")

    summary = await create_summary(db, tenant_id, patient_id, req, current_user)
    assert summary.patient_id == patient_id
    assert summary.title == req.title
    assert summary.summary_text == req.summary_text
    assert summary.is_stale is False

    # Invalidate patient summaries
    mock_res = MagicMock()
    mock_res.rowcount = 1
    db.execute.return_value = mock_res

    count = await invalidate_patient_summaries(db, tenant_id, patient_id, reason="lab_correction")
    assert count == 1
    db.commit.assert_called()


# -----------------------------------------------------------------------------
# 5. Patient Health Timeline and Date Normalization
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patient_timeline_ordering_and_unknown_dates():
    """Verify timeline aggregates across modules, normalizes dates, and handles unknown dates cleanly."""
    db = AsyncMock()
    patient_id = uuid.uuid4()
    tenant_id = uuid.uuid4()

    # Observation with known date
    obs = Observation(
        id=uuid.uuid4(),
        patient_id=patient_id,
        tenant_id=tenant_id,
        effective_datetime="2026-05-10T08:00:00+00:00",
        code={"text": "Fasting Blood Sugar"},
        value_quantity={"value": 98, "unit": "mg/dL"},
    )

    # Clinical event with earlier date
    event = ClinicalEvent(
        id=uuid.uuid4(),
        patient_id=patient_id,
        tenant_id=tenant_id,
        status=ClinicalEventStatus.ACTIVE,
        title="Appendectomy",
        onset_date=datetime(2025, 11, 20, tzinfo=UTC),
    )

    # Medication with unknown/missing date
    med = Medication(
        id=uuid.uuid4(),
        patient_id=patient_id,
        tenant_id=tenant_id,
        code={"text": "Aspirin 75mg"},
        start_date=None,
    )

    # Mock DB executions in get_patient_timeline:
    # examinations, documents, observations, medications, clinical_events
    db.execute.side_effect = [
        MagicMock(scalars=lambda: MagicMock(all=lambda: [])),  # examinations
        MagicMock(scalars=lambda: MagicMock(all=lambda: [])),  # documents
        MagicMock(scalars=lambda: MagicMock(all=lambda: [obs])),  # observations
        MagicMock(scalars=lambda: MagicMock(all=lambda: [med])),  # medications
        MagicMock(scalars=lambda: MagicMock(all=lambda: [event])),  # conditions
    ]

    timeline_response = await get_patient_timeline(db, tenant_id, patient_id)
    items = timeline_response.items

    assert len(items) == 3
    # Ordered desc by date: 2026-05-10 first, then 2025-11-20, then None (unknown)
    assert "Fasting Blood Sugar" in items[0].title
    assert "2026-05-10" in items[0].timestamp
    assert "Appendectomy" in items[1].title
    assert "2025-11-20" in items[1].timestamp
    assert "Aspirin 75mg" in items[2].title
    assert items[2].timestamp is None
    assert items[2].date_source == "unknown"


# -----------------------------------------------------------------------------
# 6. FHIR-Style R4 Export Bundle Generation
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fhir_export_bundle_generation_and_resource_types():
    """Verify FHIR R4-inspired bundle generation returns valid JSON with correct resourceTypes and references."""
    db = AsyncMock()
    patient_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    doc_id = uuid.uuid4()

    patient = Patient(
        id=patient_id,
        tenant_id=tenant_id,
        name=[{"family": "Sharma", "given": ["Rohit"]}],
        gender=Gender.MALE,
        birth_date=date(1987, 4, 30),
    )

    obs = Observation(
        id=uuid.uuid4(),
        patient_id=patient_id,
        tenant_id=tenant_id,
        status="final",
        code={"text": "Serum Creatinine"},
        value_quantity={"value": 0.9, "unit": "mg/dL"},
        document_id=doc_id,
    )

    med = Medication(
        id=uuid.uuid4(),
        patient_id=patient_id,
        tenant_id=tenant_id,
        code={"text": "Lisinopril 10mg"},
        dosage="1 tablet daily",
        document_id=doc_id,
    )

    event = ClinicalEvent(
        id=uuid.uuid4(),
        patient_id=patient_id,
        tenant_id=tenant_id,
        status=ClinicalEventStatus.ACTIVE,
        title="Primary Hypertension",
        document_id=doc_id,
    )

    # Mock DB executions in export_patient_fhir_bundle:
    # 1. Patient lookup
    # 2. Documents
    # 3. Observations
    # 4. Medications
    # 5. ClinicalEvents (Conditions)
    db.execute.side_effect = [
        MagicMock(scalar_one_or_none=lambda: patient),  # patient
        MagicMock(scalars=lambda: MagicMock(all=lambda: [])),  # documents
        MagicMock(scalars=lambda: MagicMock(all=lambda: [obs])),  # observations
        MagicMock(scalars=lambda: MagicMock(all=lambda: [med])),  # medications
        MagicMock(scalars=lambda: MagicMock(all=lambda: [event])),  # conditions
    ]

    bundle = await export_patient_fhir_bundle(db, tenant_id, patient_id)

    assert bundle["resourceType"] == "Bundle"
    assert bundle["type"] == "collection"
    assert bundle["meta"]["tag"][0]["code"] == "limited-fhir-r4-inspired"

    entries = bundle["entry"]
    assert len(entries) == 4  # Patient, Observation, MedicationStatement, Condition

    resource_types = [e["resource"]["resourceType"] for e in entries]
    assert "Patient" in resource_types
    assert "Observation" in resource_types
    assert "MedicationStatement" in resource_types
    assert "Condition" in resource_types

    # Validate JSON serializability and parseability
    json_str = json.dumps(bundle)
    assert json_str is not None
    parsed = json.loads(json_str)
    assert parsed["id"] == bundle["id"]
    assert parsed["resourceType"] == "Bundle"


# -----------------------------------------------------------------------------
# 7. Security and Tenant Isolation Regression Tests
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_security_correct_fact_unauthorized_user_forbidden():
    """Verify Role.USER cannot correct a fact belonging to a patient they do not own."""
    db = AsyncMock()
    user_tenant = uuid.uuid4()
    caller_user_id = uuid.uuid4()
    other_patient_user_id = uuid.uuid4()

    current_user = TokenData(
        user_id=caller_user_id,
        tenant_id=user_tenant,
        role=Role.USER.value,
        permissions=["observations:write"],
    )

    other_patient = Patient(
        id=uuid.uuid4(),
        tenant_id=user_tenant,
        user_id=other_patient_user_id,
        name=[{"family": "Doe", "given": ["Jane"]}],
    )
    obs = Observation(
        id=uuid.uuid4(),
        tenant_id=user_tenant,
        patient_id=other_patient.id,
        code={"text": "Hemoglobin"},
        value_quantity={"value": 11.2, "unit": "g/dL"},
    )

    # First query in check_observation_access selects obs; second query in check_patient_access selects other_patient
    db.execute.side_effect = [
        MagicMock(scalar_one_or_none=lambda: obs),
        MagicMock(scalar_one_or_none=lambda: other_patient),
    ]

    req = FactCorrectionRequest(
        fact_id=str(obs.id),
        fact_type="observation",
        updates={"value": 12.0},
        reason="Correction attempt",
    )

    with pytest.raises(AuthorizationError) as exc_info:
        await correct_fact(db, user_tenant, current_user, req)
    assert "Access denied" in str(exc_info.value)


@pytest.mark.asyncio
async def test_security_correct_fact_cross_tenant_not_found():
    """Verify cross-tenant fact correction returns NotFoundError (tenant isolation)."""
    db = AsyncMock()
    user_tenant = uuid.uuid4()
    current_user = TokenData(
        user_id=uuid.uuid4(),
        tenant_id=user_tenant,
        role=Role.ADMIN.value,
        permissions=["observations:write"],
    )

    # Cross-tenant query filters by tenant_id, returning None
    db.execute.return_value = MagicMock(scalar_one_or_none=lambda: None)

    req = FactCorrectionRequest(
        fact_id=str(uuid.uuid4()),
        fact_type="observation",
        updates={"value": 14.0},
        reason="Cross-tenant attempt",
    )

    with pytest.raises(NotFoundError):
        await correct_fact(db, user_tenant, current_user, req)


@pytest.mark.asyncio
async def test_security_mock_imports_user_cannot_browse_all_tenant_imports():
    """Verify Role.USER calling list_mock_imports_endpoint without patient_id gets empty list."""
    from app.api.v1.endpoints.mock_abdm import list_mock_imports_endpoint

    db = AsyncMock()
    user_tenant = uuid.uuid4()
    current_user = TokenData(
        user_id=uuid.uuid4(),
        tenant_id=user_tenant,
        role=Role.USER.value,
    )

    res = await list_mock_imports_endpoint(
        patient_id=None,
        limit=50,
        current_user=current_user,
        db=db,
    )
    assert res == []
    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_security_invalidate_summary_unauthorized_user_forbidden():
    """Verify invalidate_summary_endpoint rejects attempts by Role.USER on other patients' summaries."""
    from app.api.v1.endpoints.summaries import invalidate_summary_endpoint

    db = AsyncMock()
    user_tenant = uuid.uuid4()
    caller_user_id = uuid.uuid4()
    other_patient_user_id = uuid.uuid4()

    current_user = TokenData(
        user_id=caller_user_id,
        tenant_id=user_tenant,
        role=Role.USER.value,
    )

    summary_id = uuid.uuid4()
    patient_id = uuid.uuid4()
    summary = PatientHealthSummary(
        id=summary_id,
        patient_id=patient_id,
        tenant_id=user_tenant,
        title="Summary",
        summary_text="Text",
        language="en",
    )
    other_patient = Patient(
        id=patient_id,
        tenant_id=user_tenant,
        user_id=other_patient_user_id,
        name=[{"family": "Doe"}],
    )

    # 1. get_summary_by_id selects summary; 2. check_patient_access selects other_patient
    db.execute.side_effect = [
        MagicMock(scalar_one_or_none=lambda: summary),
        MagicMock(scalar_one_or_none=lambda: other_patient),
    ]

    with pytest.raises(AuthorizationError):
        await invalidate_summary_endpoint(
            summary_id=summary_id,
            reason="Invalidate attempt",
            current_user=current_user,
            db=db,
        )


# -----------------------------------------------------------------------------
# 8. Import Persistence and Preview Isolation
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mock_abdm_preview_does_not_persist_records():
    """Verify mock import preview calculates checksum and counts without calling db.add or db.commit."""
    db = AsyncMock()
    patient_id = uuid.uuid4()
    tenant_id = uuid.uuid4()

    bundle = SyntheticRecordBundle(
        external_record_id="SIM-PREVIEW-ONLY",
        source_system="mock_abdm",
        observations=[SyntheticObservation(test_name="Glucose", value=95.0, unit="mg/dL")],
        medications=[SyntheticMedication(name="Metformin", dosage="500mg")],
        conditions=[SyntheticCondition(name="Pre-diabetes")],
    )

    # Mock DB returns None for existing duplicate
    db.execute.return_value = MagicMock(scalar_one_or_none=lambda: None)

    preview = await preview_mock_abdm_record(db, tenant_id, patient_id, bundle)

    assert preview.is_duplicate is False
    assert preview.observation_count == 1
    assert preview.medication_count == 1
    assert preview.condition_count == 1
    # DB add and commit must NEVER be called during preview
    db.add.assert_not_called()
    db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_mock_abdm_confirm_persists_records_and_invalidates_summary():
    """Verify confirm_mock_abdm_import persists supported resources, logs audit, and marks summaries stale."""
    db = AsyncMock()
    patient_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()

    bundle = SyntheticRecordBundle(
        external_record_id="SIM-FULL-CONFIRM",
        source_system="mock_abdm",
        facility_name="Apollo Clinic Mock",
        observations=[SyntheticObservation(test_name="Fasting Glucose", value=105.0, unit="mg/dL")],
        medications=[SyntheticMedication(name="Glimepiride", dosage="1mg")],
        conditions=[SyntheticCondition(name="Impaired Fasting Glycemia")],
    )

    # 1. Deduplication check returns None
    db.execute.return_value = MagicMock(scalar_one_or_none=lambda: None)

    current_user = TokenData(user_id=user_id, tenant_id=tenant_id, role=Role.ADMIN.value)

    with (
        patch(
            "app.services.mock_abdm_service.invalidate_patient_summaries", new_callable=AsyncMock
        ) as mock_invalidate,
        patch(
            "app.services.mock_abdm_service.log_audit_action", new_callable=AsyncMock
        ) as mock_audit,
    ):
        result = await confirm_mock_abdm_import(db, tenant_id, patient_id, bundle, current_user)

        assert result.status == "imported"
        assert result.is_duplicate is False
        assert "observations" in result.created_resources
        assert "medications" in result.created_resources
        assert "conditions" in result.created_resources

        # Verify db.add was called for Observation, Medication, ClinicalEvent, and MockAbdmImportRecord
        assert db.add.call_count == 4
        db.commit.assert_called_once()
        mock_invalidate.assert_called_once()
        mock_audit.assert_called_once()


# -----------------------------------------------------------------------------
# 8. Document Extraction Persistence & AI Summary Generation Tests
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extraction_persistence_provenance_and_invalidation():
    """Verify document extraction persistence links provenance and invalidates patient summaries."""
    from datetime import datetime

    from app.ai.pipeline.persistence import persist_results
    from app.ai.schemas.nlp import (
        DocumentEntitiesExtract,
        KnownBiomarkerExtract,
        KnownMedicationExtract,
        PatientInfoExtract,
    )
    from app.models.document_model import DocumentModel

    db = AsyncMock()
    # Mock db.begin_nested() sync method returning async context manager
    savepoint = AsyncMock()
    savepoint.__aenter__.return_value = savepoint
    savepoint.__aexit__.return_value = None
    db.begin_nested = MagicMock(return_value=savepoint)

    exam = MagicMock()
    exam.id = uuid.uuid4()
    exam.tenant_id = uuid.uuid4()
    exam.patient_id = uuid.uuid4()
    exam.examination_date = datetime.now(UTC)

    doc_id = uuid.uuid4()
    doc = DocumentModel(
        id=doc_id,
        tenant_id=exam.tenant_id,
        owner_id=uuid.uuid4(),
        filename="lab_report.pdf",
        file_path="/tmp/lab_report.pdf",
        status="processed",
        extracted_text="Hemoglobin level: 14.5 g/dL. Metformin 500mg. Diagnosis: Type 2 Diabetes.",
    )

    # Empty existing conditions/medications/biomarkers in DB query
    db.execute.return_value = MagicMock(
        scalars=lambda: MagicMock(all=lambda: []),
        scalar_one_or_none=lambda: None,
    )

    bio_extract = KnownBiomarkerExtract(
        matched_slug="hemoglobin",
        name="Hemoglobin",
        value=14.5,
        unit_symbol="g/dL",
        page_number=1,
        confidence=0.98,
    )

    med_extract = KnownMedicationExtract(
        name="Metformin",
        dosage="500mg",
        page_number=1,
        confidence=0.95,
    )

    parsed = DocumentEntitiesExtract(
        document_category="laboratory",
        patient_info=PatientInfoExtract(patient_name="John Doe"),
        known_biomarkers=[bio_extract],
        unknown_biomarkers=[],
        known_medications=[med_extract],
        unknown_medications=[],
        diagnoses=["Type 2 Diabetes"],
        impressions="Normal tests",
    )

    with patch(
        "app.services.health_summary_service.invalidate_patient_summaries",
        new_callable=AsyncMock,
    ) as mock_invalidate:
        await persist_results(db, exam, parsed, [doc])

        # Verify db.add was called for Observation, Medication, and ClinicalEvent
        assert db.add.call_count >= 3

        added_items = [call.args[0] for call in db.add.call_args_list]
        observations = [item for item in added_items if isinstance(item, Observation)]
        medications = [item for item in added_items if isinstance(item, Medication)]
        events = [item for item in added_items if isinstance(item, ClinicalEvent)]

        assert len(observations) == 1
        assert observations[0].document_id == doc_id
        assert observations[0].page_number == 1
        assert observations[0].confidence == 0.98
        assert observations[0].review_status == "extracted"

        assert len(medications) == 1
        assert medications[0].document_id == doc_id
        assert medications[0].page_number == 1
        assert medications[0].confidence == 0.95
        assert medications[0].review_status == "extracted"

        assert len(events) == 1
        assert events[0].document_id == doc_id
        assert events[0].title == "Type 2 Diabetes"
        assert events[0].review_status == "extracted"

        # Verify summaries were marked stale
        mock_invalidate.assert_called_once()


@pytest.mark.asyncio
async def test_ai_summary_generation_english_and_hindi():
    """Verify generate_patient_summary builds grounded summaries with source references in en and hi."""
    from app.models.enums import ClinicalEventStatus, MedicationStatus
    from app.services.health_summary_service import generate_patient_summary

    db = AsyncMock()
    tenant_id = uuid.uuid4()
    patient_id = uuid.uuid4()
    user_id = uuid.uuid4()
    current_user = TokenData(user_id=user_id, tenant_id=tenant_id, role=Role.ADMIN.value)

    obs = Observation(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        patient_id=patient_id,
        status="final",
        code={"text": "HbA1c"},
        value_quantity={"value": 6.8, "unit": "%"},
        normalized_value=6.8,
        review_status="verified",
    )
    med = Medication(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        patient_id=patient_id,
        status=MedicationStatus.ACTIVE,
        code={"text": "Metformin"},
        dosage="500mg BID",
    )
    ce = ClinicalEvent(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        patient_id=patient_id,
        title="Type 2 Diabetes Mellitus",
        status=ClinicalEventStatus.ACTIVE,
    )

    # Mock DB executions: observations, medications, conditions, documents
    db.execute.side_effect = [
        MagicMock(scalars=lambda: MagicMock(all=lambda: [obs])),
        MagicMock(scalars=lambda: MagicMock(all=lambda: [med])),
        MagicMock(scalars=lambda: MagicMock(all=lambda: [ce])),
        MagicMock(scalars=lambda: MagicMock(all=lambda: [])),
    ]

    mock_llm = AsyncMock()
    mock_llm.ainvoke.return_value = MagicMock(
        content="Here is a plain-language summary: Your HbA1c is 6.8% and you are taking Metformin."
    )

    with (
        patch("app.services.health_summary_service.AIProviderService") as mock_ai_cls,
        patch(
            "app.services.health_summary_service.invalidate_patient_summaries",
            new_callable=AsyncMock,
        ) as mock_invalidate,
    ):
        mock_ai_cls.return_value.get_llm = AsyncMock(return_value=mock_llm)

        summary = await generate_patient_summary(
            db=db,
            tenant_id=tenant_id,
            patient_id=patient_id,
            language="en",
            current_user=current_user,
        )

        assert summary.patient_id == patient_id
        assert summary.language == "en"
        assert "HbA1c" in summary.summary_text
        assert len(summary.source_references) >= 3
        mock_invalidate.assert_called_once()
        db.add.assert_called_once()
        db.commit.assert_called()


@pytest.mark.asyncio
async def test_ai_summary_generation_unconfigured_error_handling():
    """Verify generate_patient_summary returns 503 when AI provider is unconfigured or fails."""
    from fastapi import HTTPException

    from app.services.health_summary_service import generate_patient_summary

    db = AsyncMock()
    tenant_id = uuid.uuid4()
    patient_id = uuid.uuid4()

    # Mock DB executions
    db.execute.return_value = MagicMock(scalars=lambda: MagicMock(all=lambda: []))

    with patch("app.services.health_summary_service.AIProviderService") as mock_ai_cls:
        mock_ai_cls.return_value.get_llm.side_effect = RuntimeError("OpenAI API key missing")

        with pytest.raises(HTTPException) as exc_info:
            await generate_patient_summary(
                db=db,
                tenant_id=tenant_id,
                patient_id=patient_id,
                language="en",
            )

        assert exc_info.value.status_code == 503
        assert "AI summary provider is not configured" in exc_info.value.detail


# -----------------------------------------------------------------------------
# 9. Phase 3A Security, Reliability & Integrity Audit Regression Tests
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_security_group_export_scoping():
    """Verify ExportScope.GROUP strictly enforces patient_ids requirement and patient access checks."""
    from fastapi import HTTPException

    from app.api.v1.endpoints.export import _validate_patient_scoping
    from app.models.enums import ExportScope

    db = AsyncMock()
    current_user = TokenData(
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        role=Role.MANAGER.value,
    )

    # 1. Missing patient_ids on GROUP export must raise 400
    with pytest.raises(HTTPException) as exc_info:
        await _validate_patient_scoping(
            scope=ExportScope.GROUP,
            patient_ids=None,
            current_user=current_user,
            db=db,
        )
    assert exc_info.value.status_code == 400
    assert "patient_ids is required for group-scoped export" in exc_info.value.detail

    # 2. Provided patient_ids must be checked via check_patient_access
    target_pid = str(uuid.uuid4())
    with patch("app.services.access.check_patient_access", new_callable=AsyncMock) as mock_check:
        res = await _validate_patient_scoping(
            scope=ExportScope.GROUP,
            patient_ids=[target_pid],
            current_user=current_user,
            db=db,
        )
        assert res == [target_pid]
        mock_check.assert_called_once_with(target_pid, current_user, db)


@pytest.mark.asyncio
async def test_security_check_document_access_unowned_patientless_document():
    """Verify check_document_access denies Role.USER access to patientless documents owned by another user."""
    from app.services.access import check_document_access

    db = AsyncMock()
    user_tenant = uuid.uuid4()
    caller_user_id = uuid.uuid4()
    other_user_id = uuid.uuid4()

    current_user = TokenData(
        user_id=caller_user_id,
        tenant_id=user_tenant,
        role=Role.USER.value,
    )

    # Document has no patient_id and is owned by other_user_id
    doc = DocumentModel(
        id=uuid.uuid4(),
        tenant_id=user_tenant,
        patient_id=None,
        owner_id=other_user_id,
        filename="confidential_clinic_memo.pdf",
    )
    db.execute.return_value = MagicMock(scalar_one_or_none=lambda: doc)

    with pytest.raises(AuthorizationError) as exc_info:
        await check_document_access(doc.id, current_user, db)
    assert "Access denied to this document" in str(exc_info.value)


@pytest.mark.asyncio
async def test_security_mock_abdm_duplicate_does_not_leak_other_patient_import_id():
    """Verify duplicate mock ABDM bundle does not leak another patient's import record ID."""
    db = AsyncMock()
    tenant_id = uuid.uuid4()
    patient_a_id = uuid.uuid4()
    patient_b_id = uuid.uuid4()
    other_import_id = uuid.uuid4()

    existing_import = MockAbdmImportRecord(
        id=other_import_id,
        tenant_id=tenant_id,
        patient_id=patient_a_id,
        external_record_id="REC-TEST-DUP-01",
        checksum="dummychecksum12345",
        imported_at=datetime.now(UTC),
    )
    db.execute.return_value = MagicMock(scalar_one_or_none=lambda: existing_import)

    bundle = SyntheticRecordBundle(
        external_record_id="REC-TEST-DUP-01",
        source_system="mock_abdm",
        observations=[],
        medications=[],
        conditions=[],
    )

    # Preview by patient B must mark duplicate but NOT disclose patient A's import ID
    preview = await preview_mock_abdm_record(
        db=db,
        tenant_id=tenant_id,
        patient_id=patient_b_id,
        bundle=bundle,
    )
    assert preview.is_duplicate is True
    assert preview.duplicate_import_id is None

    # Confirm by patient B must reject duplicate without disclosing patient A's import ID
    current_user = TokenData(user_id=uuid.uuid4(), tenant_id=tenant_id, role=Role.ADMIN.value)
    confirm = await confirm_mock_abdm_import(
        db=db,
        tenant_id=tenant_id,
        patient_id=patient_b_id,
        bundle=bundle,
        current_user=current_user,
    )
    assert confirm.is_duplicate is True
    assert confirm.import_id is None
    assert str(other_import_id) not in confirm.message


@pytest.mark.asyncio
async def test_security_ai_summary_provider_error_scrubs_secrets():
    """Verify generate_patient_summary scrubs potential API keys or tokens from 503 error details."""
    from fastapi import HTTPException

    from app.services.health_summary_service import generate_patient_summary

    db = AsyncMock()
    tenant_id = uuid.uuid4()
    patient_id = uuid.uuid4()

    db.execute.return_value = MagicMock(scalars=lambda: MagicMock(all=lambda: []))

    mock_llm = AsyncMock()
    mock_llm.ainvoke.side_effect = RuntimeError(
        "Request failed to https://api.openai.com/v1?api_key=sk-secretKey999888777666555 with auth token=secret_token_val"
    )

    with patch("app.services.health_summary_service.AIProviderService") as mock_ai_cls:
        mock_ai_cls.return_value.get_llm = AsyncMock(return_value=mock_llm)

        with pytest.raises(HTTPException) as exc_info:
            await generate_patient_summary(
                db=db,
                tenant_id=tenant_id,
                patient_id=patient_id,
                language="en",
            )
        assert exc_info.value.status_code == 503
        detail = exc_info.value.detail
        assert "sk-secretKey" not in detail
        assert "secret_token_val" not in detail
        assert "***" in detail


@pytest.mark.asyncio
async def test_clinical_integrity_fact_correction_records_reason_in_audit_new_value():
    """Verify correct_fact retains the clinician's correction reason in the audit log new_value payload."""
    db = AsyncMock()
    user_tenant = uuid.uuid4()
    user_id = uuid.uuid4()
    patient_id = uuid.uuid4()

    current_user = TokenData(
        user_id=user_id,
        tenant_id=user_tenant,
        role=Role.ADMIN.value,
        permissions=["observations:write"],
    )

    obs = Observation(
        id=uuid.uuid4(),
        tenant_id=user_tenant,
        patient_id=patient_id,
        code={"text": "Fasting Glucose"},
        value_quantity={"value": 110.0, "unit": "mg/dL"},
        raw_value=110.0,
        normalized_value=110.0,
    )
    patient = Patient(id=patient_id, tenant_id=user_tenant, user_id=user_id)

    db.execute.side_effect = [
        MagicMock(scalar_one_or_none=lambda: obs),
        MagicMock(scalar_one_or_none=lambda: patient),
        MagicMock(),
    ]

    req = FactCorrectionRequest(
        fact_id=str(obs.id),
        fact_type="observation",
        corrected_value=114.0,
        correction_reason="Clinician adjustment per secondary lab strip",
    )

    with (
        patch("app.services.facts_service.invalidate_patient_summaries", new_callable=AsyncMock),
        patch("app.services.facts_service.log_audit_action", new_callable=AsyncMock) as mock_audit,
    ):
        res = await correct_fact(db, user_tenant, current_user, req)
        assert res.fact_id == str(obs.id)
        mock_audit.assert_called_once()
        audit_kwargs = mock_audit.call_args.kwargs
        assert (
            audit_kwargs["new_value"]["_correction_reason"]
            == "Clinician adjustment per secondary lab strip"
        )


# -----------------------------------------------------------------------------
# 10. Acceptance Gap Verification Tests (Person 4 FRD)
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_e2e_fact_correction_audit_trail_and_summary_invalidation():
    """Verify in one end-to-end test that correcting a fact updates the fact, records audit log, and invalidates patient summaries."""
    from sqlalchemy.sql.dml import Update

    db = AsyncMock()
    user_tenant = uuid.uuid4()
    user_id = uuid.uuid4()
    patient_id = uuid.uuid4()
    obs_id = uuid.uuid4()

    current_user = TokenData(
        user_id=user_id,
        tenant_id=user_tenant,
        role=Role.ADMIN.value,
        permissions=["observations:write"],
    )

    obs = Observation(
        id=obs_id,
        tenant_id=user_tenant,
        patient_id=patient_id,
        code={"text": "Fasting Blood Glucose"},
        value_quantity={"value": 130.0, "unit": "mg/dL"},
        raw_value=130.0,
        normalized_value=130.0,
        original_text="FBG 130",
        review_status="extracted",
    )
    patient = Patient(id=patient_id, tenant_id=user_tenant, user_id=user_id)

    executed_statements = []

    async def mock_execute(statement, *args, **kwargs):
        executed_statements.append(statement)
        m = MagicMock()
        # 1. Observation lookup
        if len(executed_statements) == 1:
            m.scalar_one_or_none.return_value = obs
        # 2. Patient lookup for access check
        elif len(executed_statements) == 2:
            m.scalar_one_or_none.return_value = patient
        # 3. Update summary statement
        else:
            m.rowcount = 1
        return m

    db.execute.side_effect = mock_execute

    req = FactCorrectionRequest(
        fact_id=str(obs_id),
        fact_type="observation",
        corrected_value=112.0,
        correction_reason="Attending physician re-evaluated with lab fasting re-test",
    )

    with patch("app.services.facts_service.log_audit_action", new_callable=AsyncMock) as mock_audit:
        res = await correct_fact(db, user_tenant, current_user, req)

        # 1. Verify fact updated and original preserved
        assert res.fact_id == str(obs_id)
        assert obs.normalized_value == 112.0
        assert obs.original_text == "FBG 130"
        assert obs.review_status == "user_corrected"

        # 2. Verify audit action logged
        mock_audit.assert_called_once()
        audit_call = mock_audit.call_args.kwargs
        assert audit_call["action"] == "correct_observation"
        assert audit_call["old_value"]["normalized_value"] == 130.0
        assert audit_call["new_value"]["normalized_value"] == 112.0
        assert (
            audit_call["new_value"]["_correction_reason"]
            == "Attending physician re-evaluated with lab fasting re-test"
        )

        # 3. Verify summary invalidation executed
        update_stmts = [s for s in executed_statements if isinstance(s, Update)]
        assert len(update_stmts) >= 1
        db.commit.assert_called()


@pytest.mark.asyncio
async def test_fhir_export_bundle_includes_document_reference_and_source_provenance():
    """Verify FHIR export bundle includes DocumentReference with subject link, Observation derivedFrom, and Condition evidence."""
    db = AsyncMock()
    patient_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    doc_id = uuid.uuid4()

    patient = Patient(
        id=patient_id,
        tenant_id=tenant_id,
        name=[{"family": "Verma", "given": ["Sunita"]}],
        gender=Gender.FEMALE,
        birth_date=date(1990, 8, 15),
    )

    doc = DocumentModel(
        id=doc_id,
        tenant_id=tenant_id,
        patient_id=patient_id,
        filename="discharge_summary.pdf",
        file_path="/uploads/discharge_summary.pdf",
        status="completed",
    )

    obs = Observation(
        id=uuid.uuid4(),
        patient_id=patient_id,
        tenant_id=tenant_id,
        status="final",
        code={"text": "Serum Sodium"},
        value_quantity={"value": 138, "unit": "mmol/L"},
        document_id=doc_id,
    )

    med = Medication(
        id=uuid.uuid4(),
        patient_id=patient_id,
        tenant_id=tenant_id,
        code={"text": "Amlodipine 5mg"},
        dosage="5mg daily",
        document_id=doc_id,
    )

    event = ClinicalEvent(
        id=uuid.uuid4(),
        patient_id=patient_id,
        tenant_id=tenant_id,
        status=ClinicalEventStatus.ACTIVE,
        title="Essential Hypertension",
        document_id=doc_id,
    )

    # Mock DB executions in export_patient_fhir_bundle:
    # 1. Patient lookup
    # 2. Documents
    # 3. Observations
    # 4. Medications
    # 5. ClinicalEvents (Conditions)
    db.execute.side_effect = [
        MagicMock(scalar_one_or_none=lambda: patient),
        MagicMock(scalars=lambda: MagicMock(all=lambda: [doc])),
        MagicMock(scalars=lambda: MagicMock(all=lambda: [obs])),
        MagicMock(scalars=lambda: MagicMock(all=lambda: [med])),
        MagicMock(scalars=lambda: MagicMock(all=lambda: [event])),
    ]

    bundle = await export_patient_fhir_bundle(db, tenant_id, patient_id)

    assert bundle["resourceType"] == "Bundle"
    assert bundle["type"] == "collection"
    assert bundle["meta"]["tag"][0]["code"] == "limited-fhir-r4-inspired"

    entries = bundle["entry"]
    assert len(entries) == 5

    res_by_type = {e["resource"]["resourceType"]: e["resource"] for e in entries}
    assert "Patient" in res_by_type
    assert "DocumentReference" in res_by_type
    assert "Observation" in res_by_type
    assert "MedicationStatement" in res_by_type
    assert "Condition" in res_by_type

    # Verify DocumentReference
    doc_res = res_by_type["DocumentReference"]
    assert doc_res["id"] == str(doc_id)
    assert doc_res["subject"]["reference"] == f"Patient/{patient_id}"
    assert doc_res["content"][0]["attachment"]["title"] == "discharge_summary.pdf"

    # Verify Observation derivedFrom link
    obs_res = res_by_type["Observation"]
    assert obs_res["subject"]["reference"] == f"Patient/{patient_id}"
    assert obs_res["derivedFrom"] == [{"reference": f"DocumentReference/{doc_id}"}]

    # Verify Condition evidence link
    cond_res = res_by_type["Condition"]
    assert cond_res["subject"]["reference"] == f"Patient/{patient_id}"
    assert cond_res["evidence"][0]["detail"][0]["reference"] == f"DocumentReference/{doc_id}"


@pytest.mark.asyncio
async def test_mock_abdm_import_persistence_fields_and_idempotency():
    """Verify MockAbdmImportRecord saves source_system and imported_at, and enforces deduplication idempotency."""
    db = AsyncMock()
    patient_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()

    bundle = SyntheticRecordBundle(
        external_record_id="SIM-RECORD-99",
        source_system="mock_abdm",
        facility_name="Simulated Health Center",
        observations=[
            SyntheticObservation(test_name="Total Cholesterol", value=195.0, unit="mg/dL")
        ],
        medications=[SyntheticMedication(name="Atorvastatin", dosage="10mg")],
        conditions=[SyntheticCondition(name="Hyperlipidemia")],
    )
    checksum = compute_bundle_checksum(bundle)

    # 1. First execution: no existing duplicate in DB
    db.execute.return_value = MagicMock(scalar_one_or_none=lambda: None)

    current_user = TokenData(user_id=user_id, tenant_id=tenant_id, role=Role.ADMIN.value)

    with (
        patch(
            "app.services.mock_abdm_service.invalidate_patient_summaries", new_callable=AsyncMock
        ),
        patch("app.services.mock_abdm_service.log_audit_action", new_callable=AsyncMock),
    ):
        result = await confirm_mock_abdm_import(db, tenant_id, patient_id, bundle, current_user)
        assert result.status == "imported"
        assert result.is_duplicate is False

        # Inspect MockAbdmImportRecord added to session
        added_records = [
            call.args[0]
            for call in db.add.call_args_list
            if isinstance(call.args[0], MockAbdmImportRecord)
        ]
        assert len(added_records) == 1
        record = added_records[0]
        assert record.source_system == "mock_abdm"
        assert record.imported_at is not None
        assert record.status == "imported"
        assert record.checksum == checksum
        assert record.patient_id == patient_id
        assert record.tenant_id == tenant_id

        # 2. Retry execution with the same bundle: duplicate detection returns duplicate status idempotently
        existing_record = MockAbdmImportRecord(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            patient_id=patient_id,
            source_system="mock_abdm",
            external_record_id="SIM-RECORD-99",
            checksum=checksum,
            status="imported",
        )
        db.execute.return_value = MagicMock(scalar_one_or_none=lambda: existing_record)

        retry_result = await confirm_mock_abdm_import(
            db, tenant_id, patient_id, bundle, current_user
        )
        assert retry_result.status == "duplicate"
        assert retry_result.is_duplicate is True
        assert retry_result.import_id == str(existing_record.id)


@pytest.mark.asyncio
async def test_pipeline_persistence_retry_idempotency_clears_prior_exam_records():
    """Verify persist_results within savepoint clears prior observations/medications for that exam, avoiding duplicates on retry."""
    from sqlalchemy.sql.dml import Delete

    from app.ai.pipeline.persistence import persist_results
    from app.ai.schemas.nlp import DocumentEntitiesExtract, PatientInfoExtract

    db = AsyncMock()
    savepoint = AsyncMock()
    savepoint.__aenter__.return_value = savepoint
    savepoint.__aexit__.return_value = None
    db.begin_nested = MagicMock(return_value=savepoint)

    exam = MagicMock()
    exam.id = uuid.uuid4()
    exam.tenant_id = uuid.uuid4()
    exam.patient_id = uuid.uuid4()
    exam.examination_date = date.today()

    parsed = DocumentEntitiesExtract(
        document_category="laboratory",
        patient_info=PatientInfoExtract(patient_name="John Doe"),
        known_biomarkers=[],
        unknown_biomarkers=[],
        known_medications=[],
        unknown_medications=[],
        diagnoses=[],
        impressions="No findings",
    )

    executed_statements = []

    async def mock_execute(stmt, *args, **kwargs):
        executed_statements.append(stmt)
        return MagicMock(scalars=lambda: MagicMock(all=lambda: []))

    db.execute.side_effect = mock_execute

    with patch(
        "app.services.health_summary_service.invalidate_patient_summaries", new_callable=AsyncMock
    ):
        await persist_results(db, exam, parsed, [])

        delete_stmts = [s for s in executed_statements if isinstance(s, Delete)]
        assert len(delete_stmts) == 2  # Deletes observations and medications for exam.id
        db.begin_nested.assert_called_once()


@pytest.mark.asyncio
async def test_security_export_patient_fhir_cross_tenant_returns_404():
    """Verify exporting patient FHIR bundle across tenants returns 404."""
    from fastapi import HTTPException

    from app.services.fhir_export_service import export_patient_fhir_bundle

    db = AsyncMock()
    tenant_a = uuid.uuid4()
    patient_id = uuid.uuid4()

    # Query filters by (Patient.id == patient_id, Patient.tenant_id == tenant_a), returns None
    db.execute.return_value = MagicMock(scalar_one_or_none=lambda: None)

    with pytest.raises(HTTPException) as exc_info:
        await export_patient_fhir_bundle(db, tenant_a, patient_id)
    assert exc_info.value.status_code == 404
    assert "Patient not found" in exc_info.value.detail


@pytest.mark.asyncio
async def test_security_export_patient_fhir_unauthorized_user_forbidden():
    """Verify Role.USER cannot export FHIR bundle for a patient owned by someone else."""
    from app.api.v1.endpoints.export import export_patient_fhir_endpoint

    db = AsyncMock()
    tenant_id = uuid.uuid4()
    caller_id = uuid.uuid4()
    other_owner_id = uuid.uuid4()
    patient_id = uuid.uuid4()

    current_user = TokenData(
        user_id=caller_id,
        tenant_id=tenant_id,
        role=Role.USER.value,
    )

    other_patient = Patient(
        id=patient_id,
        tenant_id=tenant_id,
        user_id=other_owner_id,
        name=[{"family": "Sharma"}],
    )
    db.execute.return_value = MagicMock(scalar_one_or_none=lambda: other_patient)

    with pytest.raises(AuthorizationError) as exc_info:
        await export_patient_fhir_endpoint(
            patient_id=str(patient_id),
            db=db,
            current_user=current_user,
        )
    assert "Access denied" in str(exc_info.value)


@pytest.mark.asyncio
async def test_security_timeline_unauthorized_user_forbidden():
    """Verify Role.USER cannot read health timeline for a patient owned by someone else."""
    from app.api.v1.endpoints.timeline import get_patient_timeline_endpoint

    db = AsyncMock()
    tenant_id = uuid.uuid4()
    caller_id = uuid.uuid4()
    other_owner_id = uuid.uuid4()
    patient_id = uuid.uuid4()

    current_user = TokenData(
        user_id=caller_id,
        tenant_id=tenant_id,
        role=Role.USER.value,
    )

    other_patient = Patient(
        id=patient_id,
        tenant_id=tenant_id,
        user_id=other_owner_id,
        name=[{"family": "Kapoor"}],
    )
    db.execute.return_value = MagicMock(scalar_one_or_none=lambda: other_patient)

    with pytest.raises(AuthorizationError) as exc_info:
        await get_patient_timeline_endpoint(
            patient_id=patient_id,
            current_user=current_user,
            db=db,
        )
    assert "Access denied" in str(exc_info.value)


@pytest.mark.asyncio
async def test_security_mock_abdm_preview_and_confirm_unauthorized_user_forbidden():
    """Verify Role.USER cannot preview or confirm mock ABDM records for another patient."""
    from app.api.v1.endpoints.mock_abdm import (
        confirm_mock_record_endpoint,
        preview_mock_record_endpoint,
    )

    db = AsyncMock()
    tenant_id = uuid.uuid4()
    caller_id = uuid.uuid4()
    other_owner_id = uuid.uuid4()
    patient_id = uuid.uuid4()

    current_user = TokenData(
        user_id=caller_id,
        tenant_id=tenant_id,
        role=Role.USER.value,
    )

    other_patient = Patient(
        id=patient_id,
        tenant_id=tenant_id,
        user_id=other_owner_id,
        name=[{"family": "Gupta"}],
    )
    db.execute.return_value = MagicMock(scalar_one_or_none=lambda: other_patient)

    bundle = SyntheticRecordBundle(
        external_record_id="SIM-UNAUTH",
        source_system="mock_abdm",
    )

    # 1. Preview check
    with pytest.raises(AuthorizationError) as exc_preview:
        await preview_mock_record_endpoint(
            patient_id=patient_id,
            bundle=bundle,
            current_user=current_user,
            db=db,
        )
    assert "Access denied" in str(exc_preview.value)

    # 2. Confirm check
    with pytest.raises(AuthorizationError) as exc_confirm:
        await confirm_mock_record_endpoint(
            patient_id=patient_id,
            bundle=bundle,
            current_user=current_user,
            db=db,
        )
    assert "Access denied" in str(exc_confirm.value)

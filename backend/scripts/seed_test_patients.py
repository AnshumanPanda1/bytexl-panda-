#!/usr/bin/env python3
"""Seed comprehensive test patients into MediBot for demonstrations.

This script loads the 4 clinical test patient personas from:
  backend/data/seeds/test_patients.json
and idempotently creates or updates them in the database:
  1. Rajesh Sharma (52M) - Metabolic Syndrome, T2DM, Hypertension, Dyslipidemia
  2. Priya Nair (34F) - Moderate Persistent Asthma, Allergic Rhinitis, Inhaler therapy
  3. Amit Patel (41M) - Primary Hypothyroidism, Severe Vitamin D Deficiency
  4. Sunita Deshmukh (68F) - Geriatric Osteoarthritis, MCI, Medication Reconciliation

Usage:
  python scripts/seed_test_patients.py
"""

import asyncio
import json
import os
import sys
from datetime import UTC, datetime, date
from pathlib import Path
from uuid import UUID

current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(current_dir)
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from sqlalchemy import select, delete
from app.core.database import AsyncSessionLocal
from app.models.tenant_model import TenantModel
from app.models.user_model import UserModel
from app.models.fhir.patient import Patient, Observation
from app.models.fhir.medication import Medication, MedicationStatus
from app.models.clinical_event import ClinicalEvent
from app.models.enums import ClinicalEventStatus, CodingSystem, Gender
from app.models.health_summary_model import PatientHealthSummary


async def seed_test_patients():
    seeds_file = Path(backend_dir) / "data" / "seeds" / "test_patients.json"
    if not seeds_file.exists():
        print(f"Error: Seeds file not found at {seeds_file}")
        sys.exit(1)

    with open(seeds_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    patients_data = data.get("patients", [])
    print(f"Found {len(patients_data)} test patients to seed.")

    async with AsyncSessionLocal() as session:
        # 1. Ensure a default demo tenant exists
        tenant_id = UUID("11111111-1111-4111-8111-111111111111")
        tenant_res = await session.execute(select(TenantModel).where(TenantModel.id == tenant_id))
        tenant = tenant_res.scalar_one_or_none()
        if not tenant:
            tenant = TenantModel(
                id=tenant_id,
                name="MediBot Clinical Center",
                slug="medibot-demo",
            )
            session.add(tenant)
            await session.commit()
            print("Created default tenant: MediBot Clinical Center")

        # 2. Iterate each patient and populate their records
        for p_info in patients_data:
            pid = UUID(p_info["id"])
            full_name = f"{' '.join(p_info['name']['given'])} {p_info['name']['family']}"
            print(f"\nProcessing patient: {full_name} (MRN: {p_info.get('mrn')})")

            # Check existing patient
            p_res = await session.execute(select(Patient).where(Patient.id == pid))
            gender_val = Gender(p_info.get("gender", "unknown").upper()) if p_info.get("gender") else Gender.UNKNOWN
            patient = p_res.scalar_one_or_none()
            if not patient:
                patient = Patient(
                    id=pid,
                    tenant_id=tenant_id,
                    mrn=p_info.get("mrn"),
                    name=p_info["name"],
                    gender=gender_val,
                    birth_date=date.fromisoformat(p_info["birth_date"]) if p_info.get("birth_date") else None,
                    deceased_boolean=False,
                    address=p_info.get("address"),
                    telecom=p_info.get("telecom"),
                    emergency_contact=p_info.get("emergency_contact"),
                )
                session.add(patient)
            else:
                patient.name = p_info["name"]
                patient.mrn = p_info.get("mrn")
                patient.gender = gender_val

            await session.flush()

            # Clean and recreate demo clinical records for consistency
            await session.execute(delete(Observation).where(Observation.patient_id == pid))
            await session.execute(delete(Medication).where(Medication.patient_id == pid))
            await session.execute(delete(ClinicalEvent).where(ClinicalEvent.patient_id == pid))
            await session.execute(delete(PatientHealthSummary).where(PatientHealthSummary.patient_id == pid))

            # Add Conditions
            for c in p_info.get("conditions", []):
                ce = ClinicalEvent(
                    patient_id=pid,
                    tenant_id=tenant_id,
                    title=c["title"],
                    code=c.get("code"),
                    coding_system=CodingSystem.CUSTOM if c.get("code") else None,
                    status=ClinicalEventStatus.ACTIVE if c.get("status") == "active" else ClinicalEventStatus.RESOLVED,
                    review_status="verified",
                    confidence=0.99,
                    original_text=c["title"],
                    event_metadata={
                        "verification_status": c.get("verification_status", "confirmed"),
                        "clinical_status": c.get("status", "active"),
                        "icd10_code": c.get("code"),
                    },
                    onset_date=datetime.fromisoformat(c["onset_date"] + "T00:00:00+00:00") if c.get("onset_date") else None,
                )
                session.add(ce)

            # Add Medications
            for m in p_info.get("medications", []):
                st = MedicationStatus.ACTIVE if m.get("status") == "active" else MedicationStatus.STOPPED
                med = Medication(
                    patient_id=pid,
                    tenant_id=tenant_id,
                    status=st,
                    code={"text": m["name"], "strength": m.get("dosage"), "route": m.get("route")},
                    dosage=m.get("dosage"),
                    original_text=m["name"],
                    confidence=0.98,
                    review_status="verified",
                    start_date=date.fromisoformat(m["start_date"]) if m.get("start_date") else None,
                    end_date=date.fromisoformat(m["end_date"]) if m.get("end_date") else None,
                    reason=f"{m['name']} prescribed therapy",
                )
                session.add(med)

            # Add Biomarkers
            for b in p_info.get("biomarkers", []):
                obs = Observation(
                    patient_id=pid,
                    tenant_id=tenant_id,
                    subject={"reference": f"Patient/{pid}"},
                    status="final",
                    code={"text": b["name"]},
                    value_quantity={"value": b["value"], "unit": b["unit"]},
                    normalized_value=float(b["value"]),
                    raw_value=float(b["value"]),
                    original_text=f"{b['name']}: {b['value']} {b['unit']}",
                    confidence=0.97,
                    review_status="verified",
                    effective_datetime=datetime.now(UTC),
                )
                session.add(obs)

            # Add Bilingual AI Summaries
            ai_sum = p_info.get("ai_summary", {})
            if ai_sum:
                if ai_sum.get("en"):
                    session.add(
                        PatientHealthSummary(
                            patient_id=pid,
                            tenant_id=tenant_id,
                            title="Clinical Health Summary (English)",
                            summary_text=ai_sum["en"],
                            language="en",
                            is_stale=False,
                        )
                    )
                if ai_sum.get("hi"):
                    session.add(
                        PatientHealthSummary(
                            patient_id=pid,
                            tenant_id=tenant_id,
                            title="क्लिनिकल स्वास्थ्य सारांश (Hindi)",
                            summary_text=ai_sum["hi"],
                            language="hi",
                            is_stale=False,
                        )
                    )

            await session.commit()
            print(f"  -> Seeded {len(p_info.get('conditions', []))} conditions, {len(p_info.get('medications', []))} medications, {len(p_info.get('biomarkers', []))} observations for {full_name}")

    print("\nAll test patients seeded successfully!")


if __name__ == "__main__":
    try:
        asyncio.run(seed_test_patients())
    except Exception as e:
        print(f"Note on running seed_test_patients directly: {e}")
        print("Test patients are also persisted in backend/data/seeds/test_patients.json and frontend/src/data/testPatients.ts for offline/demo use.")

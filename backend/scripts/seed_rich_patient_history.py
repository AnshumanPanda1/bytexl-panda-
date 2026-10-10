#!/usr/bin/env python3
"""Seed comprehensive 12-month historical records across all demo patients in MediBot.

Populates 4-5 historical chronological records for:
1. Rajesh Kumar Sharma (Hero Patient - Type 2 Diabetes, Hypertension, Dyslipidemia)
2. Priya Nair (Moderate Asthma, Allergic Rhinitis, Iron Deficiency Anemia)
3. Amit Ramesh Patel (NAFLD / Fatty Liver, Hyperuricemia / Gout, Pre-diabetes)
4. Sunita Anand Deshmukh (Severe Osteoporosis, Osteoarthritis, Stage 2 CKD)

Each record includes:
- Chronological encounters (ExaminationModel)
- Real uploadable documents (PDFs, images, handwritten clinical notes from fixtures)
- Extracted text with human-in-the-loop review statuses
- Chronological Biomarker trajectory (Observation)
- Titrated Medication history (Medication)
- Clinical Events & Diagnoses (ClinicalEvent)
- Synthesized Bilingual AI Summaries (English & Hindi)
"""

import asyncio
import os
import shutil
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(current_dir)
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from sqlalchemy import delete, select
from app.core.database import AsyncSessionLocal
from app.models.clinical_event import ClinicalEvent
from app.models.doctor_model import DoctorModel
from app.models.document_model import DocumentModel
from app.models.enums import ClinicalEventStatus, CodingSystem, Gender, MedicationStatus, OrganizationType
from app.models.examination_model import ExaminationModel
from app.models.fhir.medication import Medication
from app.models.fhir.organization import OrganizationModel
from app.models.fhir.patient import Observation, Patient
from app.models.health_summary_model import PatientHealthSummary
from app.models.tenant_model import TenantModel
from app.services.document_service import HA_UPLOAD_DIR

TENANT_ID = UUID("11111111-1111-4111-8111-111111111111")
ADMIN_USER_ID = UUID("00000000-0000-0000-0000-000000000001")


async def run_seed():
    print("=== Starting MediBot Comprehensive Patient History Seeder ===")

    fixtures_dir = Path(backend_dir) / "tests" / "ocr_benchmark"
    fixtures_35_dir = fixtures_dir / "fixtures_35"
    fixtures_basic_dir = fixtures_dir / "fixtures"

    tenant_upload_dir = Path(HA_UPLOAD_DIR) / str(TENANT_ID)
    tenant_upload_dir.mkdir(parents=True, exist_ok=True)
    print(f"Upload directory: {tenant_upload_dir}")

    async with AsyncSessionLocal() as session:
        # 1. Ensure Tenant
        tenant = await session.get(TenantModel, TENANT_ID)
        if not tenant:
            tenant = TenantModel(
                id=TENANT_ID,
                name="MediBot Clinical Center",
                slug="medibot-demo",
            )
            session.add(tenant)
            await session.commit()
            print("Created tenant: MediBot Clinical Center")

        # 2. Ensure Organizations
        orgs_data = [
            {
                "id": UUID("22222222-2222-4222-8222-222222222201"),
                "name": "Apollo Hospitals Indraprastha",
                "org_type": OrganizationType.HOSPITAL,
                "address": [{"city": "New Delhi", "state": "Delhi", "country": "India", "line": ["Sarita Vihar, Delhi Mathura Road"]}],
                "telecom": [{"system": "phone", "value": "+91 11 2692 5858"}],
            },
            {
                "id": UUID("22222222-2222-4222-8222-222222222202"),
                "name": "Fortis Memorial Research Institute",
                "org_type": OrganizationType.HOSPITAL,
                "address": [{"city": "Gurugram", "state": "Haryana", "country": "India", "line": ["Sector 44, Opposite HUDA City Centre"]}],
                "telecom": [{"system": "phone", "value": "+91 124 496 2200"}],
            },
            {
                "id": UUID("22222222-2222-4222-8222-222222222203"),
                "name": "Manipal Hospital",
                "org_type": OrganizationType.HOSPITAL,
                "address": [{"city": "Bengaluru", "state": "Karnataka", "country": "India", "line": ["98 HAL Old Airport Rd"]}],
                "telecom": [{"system": "phone", "value": "+91 80 2502 4444"}],
            },
        ]

        for o in orgs_data:
            existing_org = await session.get(OrganizationModel, o["id"])
            if not existing_org:
                new_org = OrganizationModel(
                    id=o["id"],
                    tenant_id=TENANT_ID,
                    name=o["name"],
                    org_type=o["org_type"],
                    address=o["address"],
                    telecom=o["telecom"],
                    active=True,
                )
                session.add(new_org)
        await session.commit()
        print("Ensured 3 clinical healthcare organizations.")

        # 3. Ensure Doctors
        docs_data = [
            {
                "id": UUID("44444444-4444-4444-8444-444444444401"),
                "name": "Dr. Arvind Gupta, MD (Endocrinology)",
                "license_number": "DMC-24819",
                "phone": "+91 98100 11223",
                "email": "dr.arvind.gupta@apollo.example.com",
            },
            {
                "id": UUID("44444444-4444-4444-8444-444444444402"),
                "name": "Dr. Meera Reddy, MD, DM (Cardiology)",
                "license_number": "DMC-31904",
                "phone": "+91 98101 22334",
                "email": "dr.meera.reddy@fortis.example.com",
            },
            {
                "id": UUID("44444444-4444-4444-8444-444444444403"),
                "name": "Dr. Vikram Malhotra, MD (Pulmonology)",
                "license_number": "KMC-41829",
                "phone": "+91 98450 33445",
                "email": "dr.vikram.m@manipal.example.com",
            },
            {
                "id": UUID("44444444-4444-4444-8444-444444444404"),
                "name": "Dr. Sneha Kulkarni, MD, DNB (Rheumatology)",
                "license_number": "MMC-51920",
                "phone": "+91 98220 44556",
                "email": "dr.sneha.k@rubyhall.example.com",
            },
        ]

        for d in docs_data:
            existing_doc = await session.get(DoctorModel, d["id"])
            if not existing_doc:
                new_doc = DoctorModel(
                    id=d["id"],
                    tenant_id=TENANT_ID,
                    name=d["name"],
                    license_number=d["license_number"],
                    phone=d["phone"],
                    email=d["email"],
                )
                session.add(new_doc)
        await session.commit()
        print("Ensured 4 specialized physicians.")

        # 4. Helper function to copy fixture file to storage
        def copy_sample_file(fixture_name: str, doc_uuid: UUID, preferred_ext: str = ".pdf") -> tuple[Path, str, int]:
            source_file = None
            candidates = [
                fixtures_35_dir / fixture_name,
                fixtures_basic_dir / fixture_name,
                Path(backend_dir) / "data" / "seeds" / fixture_name,
            ]
            for c in candidates:
                if c.exists():
                    source_file = c
                    break

            if not source_file:
                # Fallback to any existing fixture
                for alt in (fixtures_35_dir, fixtures_basic_dir):
                    matched = list(alt.glob(f"*{preferred_ext}"))
                    if matched:
                        source_file = matched[0]
                        break

            ext = source_file.suffix if source_file else preferred_ext
            dest_file = tenant_upload_dir / f"{doc_uuid}{ext}"

            if source_file and source_file.exists():
                shutil.copyfile(source_file, dest_file)
            else:
                # Create minimal text/pdf payload
                with open(dest_file, "wb") as f:
                    f.write(b"%PDF-1.4 Minimal MediBot Test Document\n%%EOF")

            file_size = dest_file.stat().st_size
            content_type = "application/pdf" if ext == ".pdf" else ("image/png" if ext == ".png" else "image/jpeg")
            return dest_file, content_type, file_size

        # 5. Define comprehensive patient histories
        patients_config = [
            {
                "id": UUID("33333333-3333-4333-8333-333333333301"),
                "name": {"given": ["Rajesh", "Kumar"], "family": "Sharma"},
                "gender": Gender.MALE,
                "birth_date": date(1974, 5, 12),
                "mrn": "MRN-100234",
                "address": [{"city": "New Delhi", "state": "Delhi", "country": "India", "line": ["B-42 Hauz Khas"]}],
                "telecom": [{"system": "phone", "value": "+91 98765 43210"}],
                "emergency_contact": {"name": "Sunita Sharma", "relationship": "Spouse", "phone": "+91 98765 43211"},
                "conditions": [
                    {"title": "Type 2 Diabetes Mellitus without complications", "code": "E11.9", "onset": "2022-04-10", "status": ClinicalEventStatus.ACTIVE},
                    {"title": "Essential (Primary) Hypertension", "code": "I10", "onset": "2021-08-15", "status": ClinicalEventStatus.ACTIVE},
                    {"title": "Mixed Hyperlipidemia", "code": "E78.2", "onset": "2023-01-20", "status": ClinicalEventStatus.ACTIVE},
                ],
                "encounters": [
                    {
                        "date": date(2025, 10, 15),
                        "org_id": UUID("22222222-2222-4222-8222-222222222201"),
                        "doctor_id": UUID("44444444-4444-4444-8444-444444444401"),
                        "notes": "Initial Comprehensive Endocrine Workup. Patient presented with persistent fatigue, polydipsia, and elevated blood pressure (152/96 mmHg). Fasting hyperglycemia confirmed. Commenced Metformin 500mg BID and Telmisartan 40mg OD.",
                        "doc_filename": "OPD_Prescription_Initial_Oct2025.pdf",
                        "fixture": "doc_03_native_prescription_active.pdf",
                        "doc_text": "APOLLO HOSPITALS INDRAPRASTHA\nDepartment of Endocrinology & Metabolism\nPatient: Rajesh Kumar Sharma (52M) | MRN: MRN-100234\nDate: 15-Oct-2025\n\nClinical Assessment: Type 2 Diabetes Mellitus (Uncontrolled), Essential HTN Stage 2.\nBP: 152/96 mmHg | Weight: 84.5 kg | BMI: 28.6\n\nPrescription:\n1. Tab Metformin Hydrochloride 500 mg - 1 tab twice daily after meals (M/N)\n2. Tab Telmisartan 40 mg - 1 tab once daily after breakfast\n\nAdvice: Strict diabetic diet, cut refined sugars, 30 min brisk walk daily. Recheck HbA1c and Lipids in 3 months.",
                        "biomarkers": [
                            {"name": "HbA1c", "value": 8.6, "unit": "%", "interp": "High"},
                            {"name": "Fasting Blood Glucose", "value": 184.0, "unit": "mg/dL", "interp": "High"},
                            {"name": "Post-Prandial Glucose", "value": 260.0, "unit": "mg/dL", "interp": "High"},
                            {"name": "Blood Pressure Systolic", "value": 152.0, "unit": "mmHg", "interp": "High"},
                            {"name": "Blood Pressure Diastolic", "value": 96.0, "unit": "mmHg", "interp": "High"},
                            {"name": "LDL Cholesterol", "value": 165.0, "unit": "mg/dL", "interp": "High"},
                            {"name": "Serum Creatinine", "value": 1.10, "unit": "mg/dL", "interp": "Normal"},
                            {"name": "eGFR", "value": 80.0, "unit": "mL/min/1.73m2", "interp": "Normal"},
                        ],
                        "meds": [
                            {"name": "Metformin Hydrochloride 500mg", "dosage": "500 mg", "status": MedicationStatus.ACTIVE, "start": date(2025, 10, 15), "end": date(2026, 1, 20)},
                            {"name": "Telmisartan 40mg", "dosage": "40 mg", "status": MedicationStatus.ACTIVE, "start": date(2025, 10, 15), "end": None},
                        ],
                    },
                    {
                        "date": date(2026, 1, 20),
                        "org_id": UUID("22222222-2222-4222-8222-222222222201"),
                        "doctor_id": UUID("44444444-4444-4444-8444-444444444401"),
                        "notes": "Quarterly Diabetes Review. HbA1c improved to 8.1% but remains above target. Fasting glucose 156 mg/dL. Titrated Metformin to 1000mg BID and initiated Atorvastatin 10mg at bedtime for dyslipidemia.",
                        "doc_filename": "Biochemistry_Panel_Jan2026.pdf",
                        "fixture": "doc_02_native_metabolic_comma.pdf",
                        "doc_text": "LAL PATHLABS CLINICAL BIOCHEMISTRY REPORT\nPatient: Rajesh Kumar Sharma | Date: 20-Jan-2026\n\nHbA1c (Glycosylated Hemoglobin): 8.1 % [Ref: 4.0 - 5.6%]\nEstimated Average Glucose (eAG): 186 mg/dL\nFasting Blood Sugar: 156.0 mg/dL [Ref: 70 - 100]\nPost Prandial Blood Sugar: 212.0 mg/dL [Ref: < 140]\nTotal Cholesterol: 228 mg/dL\nLDL Cholesterol: 150 mg/dL [Optimal < 100]\nTriglycerides: 198 mg/dL [Ref < 150]\nSerum Creatinine: 1.05 mg/dL",
                        "biomarkers": [
                            {"name": "HbA1c", "value": 8.1, "unit": "%", "interp": "High"},
                            {"name": "Fasting Blood Glucose", "value": 156.0, "unit": "mg/dL", "interp": "High"},
                            {"name": "Post-Prandial Glucose", "value": 212.0, "unit": "mg/dL", "interp": "High"},
                            {"name": "Blood Pressure Systolic", "value": 140.0, "unit": "mmHg", "interp": "High"},
                            {"name": "Blood Pressure Diastolic", "value": 88.0, "unit": "mmHg", "interp": "High"},
                            {"name": "LDL Cholesterol", "value": 150.0, "unit": "mg/dL", "interp": "High"},
                            {"name": "Serum Creatinine", "value": 1.05, "unit": "mg/dL", "interp": "Normal"},
                        ],
                        "meds": [
                            {"name": "Metformin Hydrochloride 1000mg", "dosage": "1000 mg", "status": MedicationStatus.ACTIVE, "start": date(2026, 1, 20), "end": None},
                            {"name": "Atorvastatin 10mg", "dosage": "10 mg", "status": MedicationStatus.ACTIVE, "start": date(2026, 1, 20), "end": date(2026, 7, 22)},
                        ],
                    },
                    {
                        "date": date(2026, 4, 18),
                        "org_id": UUID("22222222-2222-4222-8222-222222222202"),
                        "doctor_id": UUID("44444444-4444-4444-8444-444444444402"),
                        "notes": "Cardiovascular Risk & Lifestyle Consultation. Blood pressure under good control at 132/84 mmHg. Patient reports consistent adherence to low-GI diet. HbA1c trending down to 7.5%.",
                        "doc_filename": "Handwritten_Cardiology_OPD_Apr2026.png",
                        "fixture": "doc_07_clean_jpg_prescription.jpg",
                        "doc_text": "FORTIS MEMORIAL RESEARCH INSTITUTE\nCardiology & Lifestyle Clinic\nPt: Rajesh Sharma (52M) | Date: 18/04/2026\nRx:\n- Cont. Tab Metformin 1000mg BD\n- Cont. Tab Telmisartan 40mg OD\n- Cont. Tab Atorvastatin 10mg HS\nAdvice: ECG Normal Sinus Rhythm. Treadmill test deferred. Continue walking 45 mins/day.",
                        "biomarkers": [
                            {"name": "HbA1c", "value": 7.5, "unit": "%", "interp": "High"},
                            {"name": "Fasting Blood Glucose", "value": 134.0, "unit": "mg/dL", "interp": "High"},
                            {"name": "Post-Prandial Glucose", "value": 178.0, "unit": "mg/dL", "interp": "High"},
                            {"name": "Blood Pressure Systolic", "value": 132.0, "unit": "mmHg", "interp": "Normal"},
                            {"name": "Blood Pressure Diastolic", "value": 84.0, "unit": "mmHg", "interp": "Normal"},
                            {"name": "LDL Cholesterol", "value": 128.0, "unit": "mg/dL", "interp": "High"},
                            {"name": "Serum Creatinine", "value": 1.02, "unit": "mg/dL", "interp": "Normal"},
                        ],
                        "meds": [],
                    },
                    {
                        "date": date(2026, 7, 22),
                        "org_id": UUID("22222222-2222-4222-8222-222222222201"),
                        "doctor_id": UUID("44444444-4444-4444-8444-444444444401"),
                        "notes": "Quarterly Metabolic Re-evaluation. Excellent progress noted: HbA1c decreased to 7.1%. Fasting glucose 118 mg/dL. Escalated Atorvastatin to 20mg for tighter LDL target (< 100 mg/dL).",
                        "doc_filename": "Metabolic_Panel_Jul2026.pdf",
                        "fixture": "doc_04_native_hindi_bilingual.pdf",
                        "doc_text": "APOLLO HOSPITALS BILINGUAL LAB REPORT / अपोलो अस्पताल जांच रिपोर्ट\nPatient: Rajesh Kumar Sharma | Date: 22-Jul-2026\n\nHbA1c: 7.1 % (Significant reduction / महत्वपूर्ण सुधार)\nFasting Blood Sugar / फास्टिंग ब्लड शुगर: 118 mg/dL\nPost-Prandial Glucose / भोजन उपरांत ग्लूकोज: 152 mg/dL\nTotal Cholesterol / कुल कोलेस्ट्रॉल: 184 mg/dL\nLDL Cholesterol: 105 mg/dL\nSerum Creatinine / सीरम क्रिएटिनिन: 0.98 mg/dL\neGFR: 86 mL/min/1.73m2",
                        "biomarkers": [
                            {"name": "HbA1c", "value": 7.1, "unit": "%", "interp": "High"},
                            {"name": "Fasting Blood Glucose", "value": 118.0, "unit": "mg/dL", "interp": "High"},
                            {"name": "Post-Prandial Glucose", "value": 152.0, "unit": "mg/dL", "interp": "High"},
                            {"name": "Blood Pressure Systolic", "value": 126.0, "unit": "mmHg", "interp": "Normal"},
                            {"name": "Blood Pressure Diastolic", "value": 80.0, "unit": "mmHg", "interp": "Normal"},
                            {"name": "LDL Cholesterol", "value": 105.0, "unit": "mg/dL", "interp": "Normal"},
                            {"name": "Serum Creatinine", "value": 0.98, "unit": "mg/dL", "interp": "Normal"},
                        ],
                        "meds": [
                            {"name": "Atorvastatin 20mg", "dosage": "20 mg", "status": MedicationStatus.ACTIVE, "start": date(2026, 7, 22), "end": None},
                        ],
                    },
                    {
                        "date": date(2026, 10, 5),
                        "org_id": UUID("22222222-2222-4222-8222-222222222201"),
                        "doctor_id": UUID("44444444-4444-4444-8444-444444444401"),
                        "notes": "Annual Endocrinology Synthesis & Glycemic Target Celebration. HbA1c reached 6.8% (Target < 7.0 achieved!). BP optimal at 122/78 mmHg. Renal function completely stable (eGFR 88). Continue triple therapy regimen.",
                        "doc_filename": "Annual_Endocrinology_Summary_Oct2026.pdf",
                        "fixture": "doc_01_native_cbc_english.pdf",
                        "doc_text": "APOLLO HOSPITALS ENDOCRINOLOGY CLINICAL SUMMARY\nPatient: Rajesh Kumar Sharma (52M) | MRN: MRN-100234\nReview Date: 05-Oct-2026\n\n12-MONTH TRAJECTORY OVERVIEW:\n- HbA1c: 8.6% (Oct 2025) -> 8.1% (Jan 2026) -> 7.5% (Apr 2026) -> 7.1% (Jul 2026) -> 6.8% (Oct 2026)\n- Fasting Blood Glucose: 184 mg/dL -> 104 mg/dL\n- Blood Pressure: 152/96 mmHg -> 122/78 mmHg\n- LDL Cholesterol: 165 mg/dL -> 92 mg/dL\n\nActive Medications:\n1. Metformin Hydrochloride 1000mg BID (PO)\n2. Telmisartan 40mg OD (PO)\n3. Atorvastatin 20mg OD HS (PO)\nStatus: Glycemic target successfully achieved. Annual retinal screening clear.",
                        "biomarkers": [
                            {"name": "HbA1c", "value": 6.8, "unit": "%", "interp": "Normal"},
                            {"name": "Fasting Blood Glucose", "value": 104.0, "unit": "mg/dL", "interp": "Normal"},
                            {"name": "Post-Prandial Glucose", "value": 138.0, "unit": "mg/dL", "interp": "Normal"},
                            {"name": "Blood Pressure Systolic", "value": 122.0, "unit": "mmHg", "interp": "Normal"},
                            {"name": "Blood Pressure Diastolic", "value": 78.0, "unit": "mmHg", "interp": "Normal"},
                            {"name": "LDL Cholesterol", "value": 92.0, "unit": "mg/dL", "interp": "Normal"},
                            {"name": "Serum Creatinine", "value": 0.95, "unit": "mg/dL", "interp": "Normal"},
                            {"name": "eGFR", "value": 88.0, "unit": "mL/min/1.73m2", "interp": "Normal"},
                        ],
                        "meds": [],
                    },
                ],
                "ai_summary_en": "Rajesh Kumar Sharma has achieved significant clinical improvement over the past 12 months. His HbA1c has successfully decreased from an initial 8.6% to 6.8% (target achieved) under Metformin 1000mg BID. Blood pressure is well-controlled at 122/78 mmHg on Telmisartan 40mg daily, and LDL cholesterol has normalized to 92 mg/dL on Atorvastatin 20mg. Renal function remains preserved with an eGFR of 88 mL/min/1.73m2.",
                "ai_summary_hi": "राजेश कुमार शर्मा ने पिछले 12 महीनों में महत्वपूर्ण स्वास्थ्य सुधार हासिल किया है। उनका HbA1c मेटफॉर्मिन 1000mg BID के तहत 8.6% से घटकर 6.8% पर आ गया है (लक्ष्य हासिल हुआ)। टेलमिसार्टन 40mg के साथ रक्तचाप 122/78 mmHg पर पूरी तरह नियंत्रित है और एलडीएल कोलेस्ट्रॉल 92 mg/dL पर सामान्य हो गया है। किडनी की कार्यक्षमता (eGFR 88) स्थिर और सुरक्षित है।",
            },
            {
                "id": UUID("33333333-3333-4333-8333-333333333302"),
                "name": {"given": ["Priya"], "family": "Nair"},
                "gender": Gender.FEMALE,
                "birth_date": date(1992, 8, 23),
                "mrn": "MRN-100582",
                "address": [{"city": "Bengaluru", "state": "Karnataka", "country": "India", "line": ["14th Cross, Indiranagar"]}],
                "telecom": [{"system": "phone", "value": "+91 98112 34567"}],
                "emergency_contact": {"name": "Karthik Nair", "relationship": "Brother", "phone": "+91 98112 34568"},
                "conditions": [
                    {"title": "Moderate Persistent Asthma with acute exacerbation", "code": "J45.41", "onset": "2020-09-14", "status": ClinicalEventStatus.ACTIVE},
                    {"title": "Iron Deficiency Anemia", "code": "D50.9", "onset": "2023-06-11", "status": ClinicalEventStatus.ACTIVE},
                    {"title": "Vitamin D Deficiency", "code": "E55.9", "onset": "2023-06-11", "status": ClinicalEventStatus.ACTIVE},
                ],
                "encounters": [
                    {
                        "date": date(2025, 11, 10),
                        "org_id": UUID("22222222-2222-4222-8222-222222222203"),
                        "doctor_id": UUID("44444444-4444-4444-8444-444444444403"),
                        "notes": "Emergency Pulmonology Evaluation. Acute bronchospasm triggered by seasonal pollen in Bengaluru. Peak flow dropped to 280 L/min. Severe fatigue and pallor noted. Laboratory tests reveal microcytic anemia (Hb 9.8 g/dL) and Vitamin D deficiency (11 ng/mL).",
                        "doc_filename": "Emergency_Pulmonology_Nov2025.pdf",
                        "fixture": "doc_06_clean_png_lab_panel.png",
                        "doc_text": "MANIPAL HOSPITALS BENGALURU\nDepartment of Pulmonary Medicine\nPatient: Priya Nair (34F) | MRN: MRN-100582 | Date: 10-Nov-2025\n\nDiagnosis: Acute Asthma Exacerbation, Iron Deficiency Anemia.\nPEF: 280 L/min | SpO2: 94% on room air\nPrescription:\n1. Budesonide/Formoterol Turbuhaler 400/12 mcg - 2 puffs twice daily\n2. Oral Prednisolone 20mg - OD for 5 days\n3. Ferrous Ascorbate 100mg - OD after lunch\n4. Cholecalciferol 60,000 IU - 1 sachet weekly for 8 weeks",
                        "biomarkers": [
                            {"name": "Peak Expiratory Flow", "value": 280.0, "unit": "L/min", "interp": "Low"},
                            {"name": "Hemoglobin", "value": 9.8, "unit": "g/dL", "interp": "Low"},
                            {"name": "Serum Ferritin", "value": 12.0, "unit": "ng/mL", "interp": "Low"},
                            {"name": "Vitamin D (25-OH)", "value": 11.0, "unit": "ng/mL", "interp": "Low"},
                            {"name": "Absolute Eosinophil Count", "value": 620.0, "unit": "cells/mcL", "interp": "High"},
                        ],
                        "meds": [
                            {"name": "Budesonide/Formoterol 400/12 mcg", "dosage": "400/12 mcg", "status": MedicationStatus.ACTIVE, "start": date(2025, 11, 10), "end": date(2026, 6, 15)},
                            {"name": "Ferrous Ascorbate 100mg", "dosage": "100 mg", "status": MedicationStatus.ACTIVE, "start": date(2025, 11, 10), "end": None},
                            {"name": "Cholecalciferol 60000 IU", "dosage": "60,000 IU", "status": MedicationStatus.ACTIVE, "start": date(2025, 11, 10), "end": None},
                        ],
                    },
                    {
                        "date": date(2026, 1, 28),
                        "org_id": UUID("22222222-2222-4222-8222-222222222203"),
                        "doctor_id": UUID("44444444-4444-4444-8444-444444444403"),
                        "notes": "Post-Exacerbation Respiratory Follow-up. Wheezing resolved. PEF improved to 340 L/min. Hemoglobin rising (10.6 g/dL). Oral steroid taper completed.",
                        "doc_filename": "Hematology_Followup_Jan2026.pdf",
                        "fixture": "doc_11_scanned_pdf_cbc.pdf",
                        "doc_text": "MANIPAL HOSPITALS HEMATOLOGY REPORT\nPatient: Priya Nair | Date: 28-Jan-2026\n\nHemoglobin: 10.6 g/dL [Ref 12.0 - 15.0]\nRBC Count: 4.1 mil/mcL\nMCV: 76 fL (Microcytic)\nSerum Ferritin: 22 ng/mL [Ref 15 - 150]\nVitamin D: 22 ng/mL\nPEF: 340 L/min",
                        "biomarkers": [
                            {"name": "Peak Expiratory Flow", "value": 340.0, "unit": "L/min", "interp": "Low"},
                            {"name": "Hemoglobin", "value": 10.6, "unit": "g/dL", "interp": "Low"},
                            {"name": "Serum Ferritin", "value": 22.0, "unit": "ng/mL", "interp": "Normal"},
                            {"name": "Vitamin D (25-OH)", "value": 22.0, "unit": "ng/mL", "interp": "Low"},
                            {"name": "Absolute Eosinophil Count", "value": 480.0, "unit": "cells/mcL", "interp": "Normal"},
                        ],
                        "meds": [],
                    },
                    {
                        "date": date(2026, 4, 15),
                        "org_id": UUID("22222222-2222-4222-8222-222222222203"),
                        "doctor_id": UUID("44444444-4444-4444-8444-444444444403"),
                        "notes": "Spirometry & Allergy Panel. FEV1 84% of predicted. Significant improvement in daytime and nocturnal cough symptoms. Ferritin increased to 34 ng/mL.",
                        "doc_filename": "Spirometry_Report_Apr2026.pdf",
                        "fixture": "clean_digital.pdf",
                        "doc_text": "PULMONARY FUNCTION TEST (PFT) REPORT\nPatient: Priya Nair (34F) | Date: 15-Apr-2026\n\nFEV1: 2.65 L (84% predicted)\nFVC: 3.20 L (88% predicted)\nFEV1/FVC Ratio: 0.83 (Normal)\nPEF: 385 L/min\nHemoglobin: 11.8 g/dL\nVitamin D: 34 ng/mL (Sufficient)",
                        "biomarkers": [
                            {"name": "Peak Expiratory Flow", "value": 385.0, "unit": "L/min", "interp": "Normal"},
                            {"name": "Hemoglobin", "value": 11.8, "unit": "g/dL", "interp": "Normal"},
                            {"name": "Serum Ferritin", "value": 34.0, "unit": "ng/mL", "interp": "Normal"},
                            {"name": "Vitamin D (25-OH)", "value": 34.0, "unit": "ng/mL", "interp": "Normal"},
                            {"name": "Absolute Eosinophil Count", "value": 350.0, "unit": "cells/mcL", "interp": "Normal"},
                        ],
                        "meds": [],
                    },
                    {
                        "date": date(2026, 6, 15),
                        "org_id": UUID("22222222-2222-4222-8222-222222222203"),
                        "doctor_id": UUID("44444444-4444-4444-8444-444444444403"),
                        "notes": "Therapy Step-Down Review. Asthma symptom score: fully controlled. Step down Budesonide/Formoterol to 200/6 mcg BID.",
                        "doc_filename": "StepDown_Prescription_Jun2026.pdf",
                        "fixture": "doc_07_clean_jpg_prescription.jpg",
                        "doc_text": "MANIPAL HOSPITALS PULMONOLOGY\nDate: 15-Jun-2026 | Pt: Priya Nair\nRx Step-Down:\n1. Budesonide/Formoterol 200/6 mcg - 2 puffs BID\n2. Continue Ferrous Ascorbate 100mg\n3. Cholecalciferol maintenance: 1 sachet monthly\nPEF: 420 L/min (Normal baseline restored).",
                        "biomarkers": [
                            {"name": "Peak Expiratory Flow", "value": 420.0, "unit": "L/min", "interp": "Normal"},
                            {"name": "Hemoglobin", "value": 12.5, "unit": "g/dL", "interp": "Normal"},
                            {"name": "Serum Ferritin", "value": 42.0, "unit": "ng/mL", "interp": "Normal"},
                            {"name": "Vitamin D (25-OH)", "value": 40.0, "unit": "ng/mL", "interp": "Normal"},
                            {"name": "Absolute Eosinophil Count", "value": 260.0, "unit": "cells/mcL", "interp": "Normal"},
                        ],
                        "meds": [
                            {"name": "Budesonide/Formoterol 200/6 mcg", "dosage": "200/6 mcg", "status": MedicationStatus.ACTIVE, "start": date(2026, 6, 15), "end": None},
                        ],
                    },
                    {
                        "date": date(2026, 9, 30),
                        "org_id": UUID("22222222-2222-4222-8222-222222222203"),
                        "doctor_id": UUID("44444444-4444-4444-8444-444444444403"),
                        "notes": "Comprehensive Annual Respiratory & Hematologic Summary. Hemoglobin completely normalized at 13.2 g/dL. Ferritin 52 ng/mL. Peak flow stable at 450 L/min with zero rescue inhaler usage over 90 days.",
                        "doc_filename": "Annual_Respiratory_Panel_Sep2026.pdf",
                        "fixture": "doc_01_native_cbc_english.pdf",
                        "doc_text": "MANIPAL HOSPITALS ANNUAL SUMMARY REPORT\nPatient: Priya Nair (34F) | MRN: MRN-100582 | Date: 30-Sep-2026\n\n10-Month Status:\n- Peak Expiratory Flow: 280 L/min -> 450 L/min (Restored)\n- Hemoglobin: 9.8 g/dL -> 13.2 g/dL (Anemia resolved)\n- Ferritin: 12 ng/mL -> 52 ng/mL\n- Vitamin D: 11 ng/mL -> 46 ng/mL\nAssessment: Asthma in complete clinical remission on maintenance controller therapy.",
                        "biomarkers": [
                            {"name": "Peak Expiratory Flow", "value": 450.0, "unit": "L/min", "interp": "Normal"},
                            {"name": "Hemoglobin", "value": 13.2, "unit": "g/dL", "interp": "Normal"},
                            {"name": "Serum Ferritin", "value": 52.0, "unit": "ng/mL", "interp": "Normal"},
                            {"name": "Vitamin D (25-OH)", "value": 46.0, "unit": "ng/mL", "interp": "Normal"},
                            {"name": "Absolute Eosinophil Count", "value": 220.0, "unit": "cells/mcL", "interp": "Normal"},
                        ],
                        "meds": [],
                    },
                ],
                "ai_summary_en": "Priya Nair has achieved complete remission of respiratory symptoms following step-down inhaler therapy (Budesonide/Formoterol 200/6 mcg). Her Peak Expiratory Flow has recovered from 280 L/min to 450 L/min. Iron deficiency anemia has resolved with Hemoglobin rising from 9.8 to 13.2 g/dL and ferritin normalizing to 52 ng/mL. Vitamin D levels are now fully replete at 46 ng/mL.",
                "ai_summary_hi": "प्रिया नायर ने श्वास संबंधी लक्षणों में पूर्ण सुधार हासिल किया है। उनका पीक एक्सपायरेटरी फ्लो (PEF) 280 L/min से बढ़कर 450 L/min हो गया है। एनीमिया पूरी तरह ठीक हो गया है—हीमोग्लोबिन 9.8 से बढ़कर 13.2 g/dL और सीरम फेरिटिन 52 ng/mL पर सामान्य हो गया है। विटामिन डी का स्तर अब 46 ng/mL पर सुरक्षित है।",
            },
            {
                "id": UUID("33333333-3333-4333-8333-333333333303"),
                "name": {"given": ["Amit", "Ramesh"], "family": "Patel"},
                "gender": Gender.MALE,
                "birth_date": date(1985, 2, 14),
                "mrn": "MRN-100791",
                "address": [{"city": "Ahmedabad", "state": "Gujarat", "country": "India", "line": ["Navrangpura, Near University"]}],
                "telecom": [{"system": "phone", "value": "+91 98220 12345"}],
                "emergency_contact": {"name": "Bhavna Patel", "relationship": "Spouse", "phone": "+91 98220 12346"},
                "conditions": [
                    {"title": "Non-Alcoholic Fatty Liver Disease (Grade 2 Steatosis)", "code": "K76.0", "onset": "2023-03-10", "status": ClinicalEventStatus.ACTIVE},
                    {"title": "Hyperuricemia with Gouty Arthritis", "code": "M10.9", "onset": "2024-01-15", "status": ClinicalEventStatus.ACTIVE},
                    {"title": "Impaired Fasting Glucose (Pre-diabetes)", "code": "R73.01", "onset": "2024-01-15", "status": ClinicalEventStatus.ACTIVE},
                ],
                "encounters": [
                    {
                        "date": date(2025, 11, 15),
                        "org_id": UUID("22222222-2222-4222-8222-222222222201"),
                        "doctor_id": UUID("44444444-4444-4444-8444-444444444401"),
                        "notes": "Acute Gout Flare & Hepatic Evaluation. Severe pain in right 1st MTP joint. High serum uric acid (9.4 mg/dL) and transaminitis (ALT 88 U/L, AST 65 U/L). Commenced Febuxostat 40mg OD and short-course Colchicine.",
                        "doc_filename": "Liver_UricAcid_Nov2025.pdf",
                        "fixture": "doc_02_native_metabolic_comma.pdf",
                        "doc_text": "APOLLO HOSPITALS HEPATIC & METABOLIC PANEL\nPatient: Amit Ramesh Patel (41M) | Date: 15-Nov-2025\n\nSerum Uric Acid: 9.4 mg/dL [High, Ref 3.5 - 7.2]\nALT (SGPT): 88 U/L [High, Ref < 45]\nAST (SGOT): 65 U/L [High, Ref < 40]\nFasting Blood Sugar: 118 mg/dL [Pre-diabetes]\nHbA1c: 6.2 %\nTriglycerides: 240 mg/dL [High]",
                        "biomarkers": [
                            {"name": "Serum Uric Acid", "value": 9.4, "unit": "mg/dL", "interp": "High"},
                            {"name": "ALT (SGPT)", "value": 88.0, "unit": "U/L", "interp": "High"},
                            {"name": "AST (SGOT)", "value": 65.0, "unit": "U/L", "interp": "High"},
                            {"name": "Fasting Blood Glucose", "value": 118.0, "unit": "mg/dL", "interp": "High"},
                            {"name": "HbA1c", "value": 6.2, "unit": "%", "interp": "High"},
                        ],
                        "meds": [
                            {"name": "Febuxostat 40mg", "dosage": "40 mg", "status": MedicationStatus.ACTIVE, "start": date(2025, 11, 15), "end": None},
                            {"name": "Colchicine 0.5mg", "dosage": "0.5 mg", "status": MedicationStatus.STOPPED, "start": date(2025, 11, 15), "end": date(2025, 12, 1)},
                        ],
                    },
                    {
                        "date": date(2026, 2, 20),
                        "org_id": UUID("22222222-2222-4222-8222-222222222201"),
                        "doctor_id": UUID("44444444-4444-4444-8444-444444444401"),
                        "notes": "Follow-up Metabolic Review. Gout symptoms subsided. Uric acid down to 7.6 mg/dL. ALT reduced to 70 U/L.",
                        "doc_filename": "Followup_LFT_Feb2026.pdf",
                        "fixture": "doc_06_clean_png_lab_panel.png",
                        "doc_text": "LAB REPORT: LFT & URIC ACID\nPatient: Amit Patel | Date: 20-Feb-2026\nSerum Uric Acid: 7.6 mg/dL\nALT: 70 U/L | AST: 52 U/L\nFasting Blood Sugar: 112 mg/dL",
                        "biomarkers": [
                            {"name": "Serum Uric Acid", "value": 7.6, "unit": "mg/dL", "interp": "High"},
                            {"name": "ALT (SGPT)", "value": 70.0, "unit": "U/L", "interp": "High"},
                            {"name": "AST (SGOT)", "value": 52.0, "unit": "U/L", "interp": "High"},
                            {"name": "Fasting Blood Glucose", "value": 112.0, "unit": "mg/dL", "interp": "High"},
                        ],
                        "meds": [],
                    },
                    {
                        "date": date(2026, 5, 22),
                        "org_id": UUID("22222222-2222-4222-8222-222222222201"),
                        "doctor_id": UUID("44444444-4444-4444-8444-444444444401"),
                        "notes": "Mid-Year Hepatic Panel. Patient reports 4kg weight reduction through calorie restriction and alcohol abstinence. ALT down to 54 U/L. Uric acid 6.6 mg/dL.",
                        "doc_filename": "MidYear_Hepatic_May2026.pdf",
                        "fixture": "clean_digital.pdf",
                        "doc_text": "HEPATIC PANEL & LIPIDS\nPatient: Amit Patel (41M) | Date: 22-May-2026\nUric Acid: 6.6 mg/dL\nALT: 54 U/L | AST: 42 U/L\nHbA1c: 5.9 % (Improved glycemic control)\nTriglycerides: 185 mg/dL",
                        "biomarkers": [
                            {"name": "Serum Uric Acid", "value": 6.6, "unit": "mg/dL", "interp": "Normal"},
                            {"name": "ALT (SGPT)", "value": 54.0, "unit": "U/L", "interp": "High"},
                            {"name": "AST (SGOT)", "value": 42.0, "unit": "U/L", "interp": "High"},
                            {"name": "HbA1c", "value": 5.9, "unit": "%", "interp": "Normal"},
                            {"name": "Fasting Blood Glucose", "value": 105.0, "unit": "mg/dL", "interp": "Normal"},
                        ],
                        "meds": [],
                    },
                    {
                        "date": date(2026, 8, 10),
                        "org_id": UUID("22222222-2222-4222-8222-222222222201"),
                        "doctor_id": UUID("44444444-4444-4444-8444-444444444401"),
                        "notes": "Ultrasound Liver & Followup. Hepatic steatosis downgraded from Grade 2 to Grade 1. Uric acid 6.0 mg/dL.",
                        "doc_filename": "USG_Liver_Followup_Aug2026.pdf",
                        "fixture": "doc_07_clean_jpg_prescription.jpg",
                        "doc_text": "APOLLO RADIOLOGY & HEPATOLOGY\nDate: 10-Aug-2026 | Pt: Amit Patel\nUSG Abdomen: Mild diffuse fatty infiltration (Grade 1 steatosis). Normal portal vein.\nSerum Uric Acid: 6.0 mg/dL\nALT: 40 U/L (Normal) | AST: 32 U/L (Normal)",
                        "biomarkers": [
                            {"name": "Serum Uric Acid", "value": 6.0, "unit": "mg/dL", "interp": "Normal"},
                            {"name": "ALT (SGPT)", "value": 40.0, "unit": "U/L", "interp": "Normal"},
                            {"name": "AST (SGOT)", "value": 32.0, "unit": "U/L", "interp": "Normal"},
                            {"name": "Fasting Blood Glucose", "value": 100.0, "unit": "mg/dL", "interp": "Normal"},
                        ],
                        "meds": [],
                    },
                    {
                        "date": date(2026, 10, 2),
                        "org_id": UUID("22222222-2222-4222-8222-222222222201"),
                        "doctor_id": UUID("44444444-4444-4444-8444-444444444401"),
                        "notes": "Annual Synthesis: All metabolic and hepatic markers within normal clinical limits. Uric acid 5.4 mg/dL. ALT 30 U/L. HbA1c 5.6%. Pre-diabetes resolved.",
                        "doc_filename": "Annual_Metabolic_Oct2026.pdf",
                        "fixture": "doc_01_native_cbc_english.pdf",
                        "doc_text": "ANNUAL METABOLIC COMPILATION REPORT\nPatient: Amit Ramesh Patel (41M) | Date: 02-Oct-2026\nTrajectory:\n- Uric Acid: 9.4 -> 5.4 mg/dL (Resolved)\n- ALT: 88 -> 30 U/L (Normal)\n- AST: 65 -> 25 U/L (Normal)\n- HbA1c: 6.2% -> 5.6% (Normal)\n- Fasting Glucose: 118 -> 95 mg/dL\nNo further gout attacks. Continue Febuxostat 40mg OD.",
                        "biomarkers": [
                            {"name": "Serum Uric Acid", "value": 5.4, "unit": "mg/dL", "interp": "Normal"},
                            {"name": "ALT (SGPT)", "value": 30.0, "unit": "U/L", "interp": "Normal"},
                            {"name": "AST (SGOT)", "value": 25.0, "unit": "U/L", "interp": "Normal"},
                            {"name": "Fasting Blood Glucose", "value": 95.0, "unit": "mg/dL", "interp": "Normal"},
                            {"name": "HbA1c", "value": 5.6, "unit": "%", "interp": "Normal"},
                        ],
                        "meds": [],
                    },
                ],
                "ai_summary_en": "Amit Patel demonstrates sustained normalization of liver enzymes and purine metabolism. Serum Uric Acid decreased from 9.4 mg/dL to 5.4 mg/dL on Febuxostat 40mg, with zero gout recurrences. Liver transaminases normalized from ALT 88 U/L to 30 U/L following lifestyle modification and weight loss. Glycemic markers have normalized to HbA1c 5.6%.",
                "ai_summary_hi": "अमित पटेल के लिवर एंजाइम और यूरिक एसिड पूरी तरह सामान्य हो गए हैं। फेबुक्सोस्टेट 40mg के साथ सीरम यूरिक एसिड 9.4 से घटकर 5.4 mg/dL पर आ गया है, जिससे गठिया का दर्द समाप्त हो गया है। लिवर एंजाइम (ALT) 88 से घटकर 30 U/L हो गए हैं और HbA1c 5.6% पर सामान्य स्तर पर है।",
            },
            {
                "id": UUID("33333333-3333-4333-8333-333333333304"),
                "name": {"given": ["Sunita", "Anand"], "family": "Deshmukh"},
                "gender": Gender.FEMALE,
                "birth_date": date(1958, 11, 30),
                "mrn": "MRN-100915",
                "address": [{"city": "Pune", "state": "Maharashtra", "country": "India", "line": ["Kothrud, Flat 402"]}],
                "telecom": [{"system": "phone", "value": "+91 98450 67890"}],
                "emergency_contact": {"name": "Rohit Deshmukh", "relationship": "Son", "phone": "+91 98450 67891"},
                "conditions": [
                    {"title": "Severe Postmenopausal Osteoporosis", "code": "M81.0", "onset": "2021-05-18", "status": ClinicalEventStatus.ACTIVE},
                    {"title": "Primary Osteoarthritis of Bilateral Knees", "code": "M17.0", "onset": "2022-09-04", "status": ClinicalEventStatus.ACTIVE},
                    {"title": "Chronic Kidney Disease Stage 2 with Mild Hypertension", "code": "N18.2", "onset": "2023-10-12", "status": ClinicalEventStatus.ACTIVE},
                ],
                "encounters": [
                    {
                        "date": date(2025, 10, 25),
                        "org_id": UUID("22222222-2222-4222-8222-222222222202"),
                        "doctor_id": UUID("44444444-4444-4444-8444-444444444404"),
                        "notes": "Geriatric Rheumatology Review & DEXA Evaluation. Lumbar T-score -3.1, Femoral neck -2.7. High fall and fracture risk. Serum creatinine 1.28 mg/dL (eGFR 51 mL/min). Amlodipine 5mg started for BP 148/92 mmHg.",
                        "doc_filename": "DEXA_Rheumatology_Oct2025.pdf",
                        "fixture": "doc_02_native_metabolic_comma.pdf",
                        "doc_text": "RUBY HALL CLINIC RHEUMATOLOGY & BONE DENSITY\nPatient: Sunita Deshmukh (67F) | Date: 25-Oct-2025\n\nDEXA T-score: Lumbar Spine L1-L4: -3.1 | Femoral Neck: -2.7\nCalcium: 8.6 mg/dL [Ref 8.8 - 10.2]\nVitamin D: 14 ng/mL [Deficient]\nSerum Creatinine: 1.28 mg/dL\neGFR: 51 mL/min/1.73m2\nBP: 148/92 mmHg\nRx: Zolendronic Acid 5mg IV annual infusion, Amlodipine 5mg OD, Calcium 500mg + D3 1000 IU.",
                        "biomarkers": [
                            {"name": "Serum Calcium", "value": 8.6, "unit": "mg/dL", "interp": "Low"},
                            {"name": "Vitamin D (25-OH)", "value": 14.0, "unit": "ng/mL", "interp": "Low"},
                            {"name": "Serum Creatinine", "value": 1.28, "unit": "mg/dL", "interp": "High"},
                            {"name": "eGFR", "value": 51.0, "unit": "mL/min/1.73m2", "interp": "Low"},
                            {"name": "Blood Pressure Systolic", "value": 148.0, "unit": "mmHg", "interp": "High"},
                            {"name": "Blood Pressure Diastolic", "value": 92.0, "unit": "mmHg", "interp": "High"},
                        ],
                        "meds": [
                            {"name": "Amlodipine 5mg", "dosage": "5 mg", "status": MedicationStatus.ACTIVE, "start": date(2025, 10, 25), "end": None},
                            {"name": "Calcium Carbonate 500mg + D3", "dosage": "500 mg", "status": MedicationStatus.ACTIVE, "start": date(2025, 10, 25), "end": None},
                            {"name": "Zoledronic Acid 5mg IV", "dosage": "5 mg", "status": MedicationStatus.ACTIVE, "start": date(2025, 10, 25), "end": None},
                        ],
                    },
                    {
                        "date": date(2026, 1, 15),
                        "org_id": UUID("22222222-2222-4222-8222-222222222202"),
                        "doctor_id": UUID("44444444-4444-4444-8444-444444444404"),
                        "notes": "Post-Infusion Renal & Electrolyte Monitoring. Creatinine improved to 1.22 mg/dL. Calcium stable at 9.1 mg/dL. Blood pressure improved to 136/84 mmHg on Amlodipine.",
                        "doc_filename": "Renal_Electrolytes_Jan2026.pdf",
                        "fixture": "doc_06_clean_png_lab_panel.png",
                        "doc_text": "LAB REPORT: RENAL & ELECTROLYTES\nPatient: Sunita Deshmukh | Date: 15-Jan-2026\nSerum Creatinine: 1.22 mg/dL\neGFR: 54 mL/min/1.73m2\nCalcium: 9.1 mg/dL\nVitamin D: 28 ng/mL\nBP: 136/84 mmHg",
                        "biomarkers": [
                            {"name": "Serum Calcium", "value": 9.1, "unit": "mg/dL", "interp": "Normal"},
                            {"name": "Vitamin D (25-OH)", "value": 28.0, "unit": "ng/mL", "interp": "Normal"},
                            {"name": "Serum Creatinine", "value": 1.22, "unit": "mg/dL", "interp": "Normal"},
                            {"name": "eGFR", "value": 54.0, "unit": "mL/min/1.73m2", "interp": "Normal"},
                            {"name": "Blood Pressure Systolic", "value": 136.0, "unit": "mmHg", "interp": "Normal"},
                            {"name": "Blood Pressure Diastolic", "value": 84.0, "unit": "mmHg", "interp": "Normal"},
                        ],
                        "meds": [],
                    },
                    {
                        "date": date(2026, 4, 10),
                        "org_id": UUID("22222222-2222-4222-8222-222222222202"),
                        "doctor_id": UUID("44444444-4444-4444-8444-444444444404"),
                        "notes": "Bilateral Knee Osteoarthritis Evaluation. Viscosupplementation administered. Physical therapy initiated for quadriceps strengthening.",
                        "doc_filename": "Orthopedic_Viscosupplementation_Apr2026.pdf",
                        "fixture": "doc_07_clean_jpg_prescription.jpg",
                        "doc_text": "ORTHOPEDIC CLINIC CONSULT\nDate: 10-Apr-2026 | Pt: Sunita Deshmukh (67F)\nProcedure: Intra-articular Hyaluronic acid injection bilateral knees.\nBP: 132/80 mmHg | Creatinine: 1.18 mg/dL\nAdvice: Avoid high-impact loading; low-impact aquatic therapy recommended.",
                        "biomarkers": [
                            {"name": "Serum Calcium", "value": 9.3, "unit": "mg/dL", "interp": "Normal"},
                            {"name": "Serum Creatinine", "value": 1.18, "unit": "mg/dL", "interp": "Normal"},
                            {"name": "eGFR", "value": 56.0, "unit": "mL/min/1.73m2", "interp": "Normal"},
                            {"name": "Blood Pressure Systolic", "value": 132.0, "unit": "mmHg", "interp": "Normal"},
                            {"name": "Blood Pressure Diastolic", "value": 80.0, "unit": "mmHg", "interp": "Normal"},
                        ],
                        "meds": [],
                    },
                    {
                        "date": date(2026, 7, 14),
                        "org_id": UUID("22222222-2222-4222-8222-222222222202"),
                        "doctor_id": UUID("44444444-4444-4444-8444-444444444404"),
                        "notes": "Quarterly Bone Health & Renal Re-check. Serum Calcium 9.4 mg/dL. Vitamin D 42 ng/mL. Creatinine 1.15 mg/dL (eGFR 58 mL/min). Good joint mobility reported.",
                        "doc_filename": "Bone_Metabolism_Jul2026.pdf",
                        "fixture": "clean_digital.pdf",
                        "doc_text": "BONE MINERAL & RENAL PROFILE\nPatient: Sunita Deshmukh | Date: 14-Jul-2026\nCalcium: 9.4 mg/dL\nVitamin D (25-OH): 42 ng/mL\nSerum Creatinine: 1.15 mg/dL\neGFR: 58 mL/min/1.73m2\nBlood Pressure: 128/78 mmHg",
                        "biomarkers": [
                            {"name": "Serum Calcium", "value": 9.4, "unit": "mg/dL", "interp": "Normal"},
                            {"name": "Vitamin D (25-OH)", "value": 42.0, "unit": "ng/mL", "interp": "Normal"},
                            {"name": "Serum Creatinine", "value": 1.15, "unit": "mg/dL", "interp": "Normal"},
                            {"name": "eGFR", "value": 58.0, "unit": "mL/min/1.73m2", "interp": "Normal"},
                            {"name": "Blood Pressure Systolic", "value": 128.0, "unit": "mmHg", "interp": "Normal"},
                            {"name": "Blood Pressure Diastolic", "value": 78.0, "unit": "mmHg", "interp": "Normal"},
                        ],
                        "meds": [],
                    },
                    {
                        "date": date(2026, 9, 25),
                        "org_id": UUID("22222222-2222-4222-8222-222222222202"),
                        "doctor_id": UUID("44444444-4444-4444-8444-444444444404"),
                        "notes": "Annual Geriatric Mobility & Bone Health Synthesis. Fall risk markedly reduced. Renal markers stabilized (Creatinine 1.12 mg/dL, eGFR 60 mL/min). Blood pressure controlled at 124/76 mmHg. Excellent compliance.",
                        "doc_filename": "Geriatric_Annual_Review_Sep2026.pdf",
                        "fixture": "doc_01_native_cbc_english.pdf",
                        "doc_text": "ANNUAL GERIATRIC MOBILITY & RENAL REVIEW\nPatient: Sunita Anand Deshmukh (67F) | Date: 25-Sep-2026\nProgress Summary:\n- Calcium: 8.6 -> 9.5 mg/dL (Normal)\n- Vitamin D: 14 -> 46 ng/mL (Optimal)\n- Serum Creatinine: 1.28 -> 1.12 mg/dL (eGFR 60 mL/min, stable)\n- Blood Pressure: 148/92 -> 124/76 mmHg\nMobility score: Independence maintained. No fractures or falls over 12 months.",
                        "biomarkers": [
                            {"name": "Serum Calcium", "value": 9.5, "unit": "mg/dL", "interp": "Normal"},
                            {"name": "Vitamin D (25-OH)", "value": 46.0, "unit": "ng/mL", "interp": "Normal"},
                            {"name": "Serum Creatinine", "value": 1.12, "unit": "mg/dL", "interp": "Normal"},
                            {"name": "eGFR", "value": 60.0, "unit": "mL/min/1.73m2", "interp": "Normal"},
                            {"name": "Blood Pressure Systolic", "value": 124.0, "unit": "mmHg", "interp": "Normal"},
                            {"name": "Blood Pressure Diastolic", "value": 76.0, "unit": "mmHg", "interp": "Normal"},
                        ],
                        "meds": [],
                    },
                ],
                "ai_summary_en": "Sunita Anand Deshmukh has achieved stable bone mineral density and well-controlled blood pressure (124/76 mmHg on Amlodipine 5mg). Serum calcium is optimal at 9.5 mg/dL and Vitamin D has reached 46 ng/mL following Zoledronic acid infusion and supplementation. Renal function is stable with serum creatinine improving from 1.28 to 1.12 mg/dL (eGFR 60 mL/min). No fractures or falls reported.",
                "ai_summary_hi": "सुनीता आनंद देशमुख का बोन मिनरल घनत्व स्थिर हो गया है और एम्लोडिपिन 5mg पर रक्तचाप 124/76 mmHg पर नियंत्रित है। जोलेड्रोनिक एसिड और सप्लीमेंट्स के बाद सीरम कैल्शियम 9.5 mg/dL और विटामिन डी 46 ng/mL के सुरक्षित स्तर पर है। किडनी का कार्य (क्रिएटिनिन 1.12, eGFR 60) स्थिर और सुधरा हुआ है। पिछले 12 महीनों में गिरने या फ्रैक्चर की कोई घटना नहीं हुई है।",
            },
        ]

        # 6. Execute Seeding
        for p_cfg in patients_config:
            pid = p_cfg["id"]
            p_name = f"{' '.join(p_cfg['name']['given'])} {p_cfg['name']['family']}"
            print(f"\n---> Populating records for: {p_name} ({pid})")

            # Patient entity
            patient = await session.get(Patient, pid)
            if not patient:
                patient = Patient(
                    id=pid,
                    tenant_id=TENANT_ID,
                    mrn=p_cfg["mrn"],
                    name=p_cfg["name"],
                    gender=p_cfg["gender"],
                    birth_date=p_cfg["birth_date"],
                    address=p_cfg["address"],
                    telecom=p_cfg["telecom"],
                    emergency_contact=p_cfg["emergency_contact"],
                )
                session.add(patient)
            else:
                patient.name = p_cfg["name"]
                patient.gender = p_cfg["gender"]
                patient.birth_date = p_cfg["birth_date"]
                patient.mrn = p_cfg["mrn"]
                patient.address = p_cfg["address"]
                patient.telecom = p_cfg["telecom"]
                patient.emergency_contact = p_cfg["emergency_contact"]

            await session.flush()

            # Clean previous records for clean deterministic demo state
            await session.execute(delete(Observation).where(Observation.patient_id == pid))
            await session.execute(delete(Medication).where(Medication.patient_id == pid))
            await session.execute(delete(ClinicalEvent).where(ClinicalEvent.patient_id == pid))
            await session.execute(delete(DocumentModel).where(DocumentModel.patient_id == pid))
            await session.execute(delete(ExaminationModel).where(ExaminationModel.patient_id == pid))
            await session.execute(delete(PatientHealthSummary).where(PatientHealthSummary.patient_id == pid))
            await session.flush()

            # Insert Conditions
            for c in p_cfg["conditions"]:
                ce = ClinicalEvent(
                    patient_id=pid,
                    tenant_id=TENANT_ID,
                    title=c["title"],
                    code=c["code"],
                    coding_system=CodingSystem.CUSTOM,
                    status=c["status"],
                    review_status="verified",
                    confidence=0.99,
                    original_text=c["title"],
                    event_metadata={"icd10": c["code"], "status": "confirmed"},
                    onset_date=datetime.fromisoformat(c["onset"] + "T00:00:00+00:00"),
                )
                session.add(ce)

            # Insert 5 Encounters with Documents & Biomarkers
            for idx, enc in enumerate(p_cfg["encounters"]):
                exam_id = uuid4()
                exam = ExaminationModel(
                    id=exam_id,
                    tenant_id=TENANT_ID,
                    patient_id=pid,
                    examination_date=enc["date"],
                    organization_id=enc["org_id"],
                    notes=enc["notes"],
                )
                session.add(exam)
                await session.flush()

                # Document entity and file
                doc_id = uuid4()
                fixture_file = enc.get("fixture", "clean_digital.pdf")
                dest_file, ctype, fsize = copy_sample_file(fixture_file, doc_id)

                doc = DocumentModel(
                    id=doc_id,
                    tenant_id=TENANT_ID,
                    patient_id=pid,
                    examination_id=exam_id,
                    owner_id=ADMIN_USER_ID,
                    filename=enc["doc_filename"],
                    file_path=str(dest_file),
                    status="completed",
                    extracted_text=enc["doc_text"],
                    created_at=datetime.combine(enc["date"], datetime.min.time(), tzinfo=UTC),
                )
                session.add(doc)
                await session.flush()

                # Biomarkers (Observations)
                enc_dt = datetime.combine(enc["date"], datetime.min.time(), tzinfo=UTC)
                for b in enc["biomarkers"]:
                    obs = Observation(
                        patient_id=pid,
                        tenant_id=TENANT_ID,
                        examination_id=exam_id,
                        document_id=doc_id,
                        subject={"reference": f"Patient/{pid}"},
                        status="final",
                        code={"text": b["name"]},
                        value_quantity={"value": b["value"], "unit": b["unit"]},
                        normalized_value=float(b["value"]),
                        raw_value=float(b["value"]),
                        original_text=f"{b['name']}: {b['value']} {b['unit']}",
                        confidence=0.98,
                        review_status="verified",
                        effective_datetime=enc_dt,
                        page_number=1,
                    )
                    session.add(obs)

                # Medications for this encounter
                for m in enc.get("meds", []):
                    med = Medication(
                        patient_id=pid,
                        tenant_id=TENANT_ID,
                        examination_id=exam_id,
                        document_id=doc_id,
                        status=m["status"],
                        code={"text": m["name"], "strength": m["dosage"]},
                        dosage=m["dosage"],
                        original_text=m["name"],
                        confidence=0.98,
                        review_status="verified",
                        start_date=m["start"],
                        end_date=m["end"],
                        reason=f"{m['name']} prescribed therapy",
                    )
                    session.add(med)

            # Insert Bilingual AI Summaries
            session.add(
                PatientHealthSummary(
                    patient_id=pid,
                    tenant_id=TENANT_ID,
                    title="Comprehensive Clinical Synthesis (English)",
                    summary_text=p_cfg["ai_summary_en"],
                    language="en",
                    is_stale=False,
                )
            )
            session.add(
                PatientHealthSummary(
                    patient_id=pid,
                    tenant_id=TENANT_ID,
                    title="समग्र क्लिनिकल स्वास्थ्य सारांश (Hindi)",
                    summary_text=p_cfg["ai_summary_hi"],
                    language="hi",
                    is_stale=False,
                )
            )

            await session.commit()
            print(f"  -> Successfully seeded 5 encounters, 5 documents, conditions, medications, and biomarker trajectories for {p_name}")

    print("\n=== All 4 demo patients successfully populated with 12-month historical records! ===")
    export_static_seeds(patients_config)


def export_static_seeds(patients_config):
    """Sync static seed files (test_patients.json and testPatients.ts) for offline/demo reliability."""
    import json

    # 1. Export test_patients.json
    json_path = Path(backend_dir) / "data" / "seeds" / "test_patients.json"
    json_path.parent.mkdir(parents=True, exist_ok=True)

    json_patients = []
    for p in patients_config:
        all_biomarkers = []
        all_meds = []
        all_docs = []
        for enc in p["encounters"]:
            for b in enc["biomarkers"]:
                all_biomarkers.append({
                    "name": b["name"],
                    "value": b["value"],
                    "unit": b["unit"],
                    "interpretation": b["interp"],
                    "effective_datetime": enc["date"].isoformat(),
                })
            for m in enc.get("meds", []):
                all_meds.append({
                    "name": m["name"],
                    "dosage": m["dosage"],
                    "status": "active" if m["status"] == MedicationStatus.ACTIVE else "stopped",
                    "start_date": m["start"].isoformat() if m["start"] else None,
                    "end_date": m["end"].isoformat() if m["end"] else None,
                })
            all_docs.append({
                "filename": enc["doc_filename"],
                "created_at": enc["date"].isoformat(),
                "status": "completed",
                "extracted_text": enc["doc_text"][:200] + "...",
            })

        json_patients.append({
            "id": str(p["id"]),
            "tenant_id": str(TENANT_ID),
            "mrn": p["mrn"],
            "name": p["name"],
            "gender": p["gender"].value if hasattr(p["gender"], "value") else str(p["gender"]),
            "birth_date": p["birth_date"].isoformat(),
            "address": p["address"],
            "telecom": p["telecom"],
            "emergency_contact": p["emergency_contact"],
            "conditions": [
                {
                    "title": c["title"],
                    "code": c["code"],
                    "status": "active" if c["status"] == ClinicalEventStatus.ACTIVE else "resolved",
                    "onset_date": c["onset"],
                }
                for c in p["conditions"]
            ],
            "medications": all_meds,
            "biomarkers": all_biomarkers,
            "documents": all_docs,
            "ai_summary": {
                "en": p["ai_summary_en"],
                "hi": p["ai_summary_hi"],
            },
        })

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"patients": json_patients}, f, indent=2, ensure_ascii=False)
    print(f"Exported static seed data to: {json_path}")

    # 2. Export testPatients.ts for Frontend offline / mock cache
    ts_path = Path(backend_dir).parent / "frontend" / "src" / "data" / "testPatients.ts"
    if ts_path.exists():
        ts_entries = []
        for p in patients_config:
            b_items = []
            m_items = []
            d_items = []
            b_counter = 1
            for enc in p["encounters"]:
                for b in enc["biomarkers"]:
                    slug = b["name"].lower().replace(" ", "-").replace("(", "").replace(")", "").replace("/", "-")
                    b_items.append(f"""      {{
        id: 'bio-{str(p["id"])[:8]}-{b_counter}',
        name: {json.dumps(b["name"])},
        slug: {json.dumps(slug)},
        value: {b["value"]},
        unit: {json.dumps(b["unit"])},
        interpretation: {json.dumps(b["interp"])},
        effective_datetime: '{enc["date"].isoformat()}T09:00:00Z',
        confidence: 0.98,
        page_number: 1,
      }}""")
                    b_counter += 1

                for idx, m in enumerate(enc.get("meds", [])):
                    st_val = "active" if m["status"] == MedicationStatus.ACTIVE else "stopped"
                    m_items.append(f"""      {{
        id: 'med-{str(p["id"])[:8]}-{enc["date"].strftime("%Y%m%d")}-{idx}',
        patient_id: '{str(p["id"])}',
        tenant_id: '{str(TENANT_ID)}',
        status: '{st_val}',
        code: {{ text: {json.dumps(m["name"])} }},
        dosage: {json.dumps(m["dosage"])},
        start_date: '{m["start"].isoformat()}',
        reason: {json.dumps(m["name"] + " therapy")},
        created_at: '{enc["date"].isoformat()}T09:00:00Z',
      }}""")

                d_items.append(f"""      {{
        id: 'doc-{str(p["id"])[:8]}-{enc["date"].strftime("%Y%m%d")}',
        filename: {json.dumps(enc["doc_filename"])},
        status: 'completed',
        document_type: 'clinical_report',
        created_at: '{enc["date"].isoformat()}T09:00:00Z',
        extracted_text: {json.dumps(enc["doc_text"][:300])},
      }}""")

            c_items = []
            for idx, c in enumerate(p["conditions"]):
                st_str = "ClinicalEventStatus.ACTIVE" if c["status"] == ClinicalEventStatus.ACTIVE else "ClinicalEventStatus.RESOLVED"
                c_items.append(f"""      {{
        id: 'cond-{str(p["id"])[:8]}-{idx+1}',
        patient_id: '{str(p["id"])}',
        tenant_id: '{str(TENANT_ID)}',
        title: {json.dumps(c["title"])},
        status: {st_str},
        schedule_kind: ScheduleKind.STATE,
        occurrences: [],
        event_metadata: {{}},
        examinations: [],
        observations: [],
        anatomy_links: [],
        onset_date: '{c["onset"]}T00:00:00Z',
        created_at: '{c["onset"]}T00:00:00Z',
        updated_at: '{c["onset"]}T00:00:00Z',
      }}""")

            ts_entries.append(f"""  {{
    patient: {{
      id: '{str(p["id"])}',
      tenant_id: '{str(TENANT_ID)}',
      mrn: '{p["mrn"]}',
      name: {json.dumps(p["name"])},
      gender: '{p["gender"].value if hasattr(p["gender"], "value") else str(p["gender"])}',
      birth_date: '{p["birth_date"].isoformat()}',
      address: {json.dumps(p["address"])},
      telecom: {json.dumps(p["telecom"])},
      emergency_contact: {json.dumps(p["emergency_contact"])},
    }},
    medications: [
{",\n".join(m_items)}
    ],
    conditions: [
{",\n".join(c_items)}
    ],
    biomarkers: [
{",\n".join(b_items)}
    ],
    aiSummary: {{
      en: {json.dumps(p["ai_summary_en"])},
      hi: {json.dumps(p["ai_summary_hi"])},
    }},
    documents: [
{",\n".join(d_items)}
    ],
  }}""")

        ts_content = f"""import {{ Patient }} from '../types/patient';
import {{ MedicationRecord }} from '../services/medicationService';
import {{ ClinicalEvent, ScheduleKind, ClinicalEventStatus }} from '../services/clinicalEventService';

export interface TestPatientFullData {{
  patient: Patient;
  medications: MedicationRecord[];
  conditions: ClinicalEvent[];
  biomarkers: Array<{{
    id: string;
    name: string;
    slug: string;
    value: number;
    unit: string;
    reference_range_min?: number;
    reference_range_max?: number;
    reference_range_text?: string;
    interpretation?: 'Normal' | 'High' | 'Low' | 'Critical';
    effective_datetime: string;
    page_number?: number;
    confidence?: number;
    evidence_text?: string;
  }}>;
  aiSummary: {{
    en: string;
    hi: string;
  }};
  documents: Array<{{
    id: string;
    filename: string;
    status: string;
    document_type: string;
    created_at: string;
    extracted_text: string;
  }}>;
}}

export const TEST_PATIENTS_DATA: TestPatientFullData[] = [
{",\n".join(ts_entries)}
];

export function getTestPatients(): Patient[] {{
  return TEST_PATIENTS_DATA.map((d) => d.patient);
}}

export function getTestPatientById(id: string): Patient | undefined {{
  return TEST_PATIENTS_DATA.find((d) => d.patient.id === id)?.patient;
}}

export function getTestPatientFullData(id: string): TestPatientFullData | undefined {{
  return TEST_PATIENTS_DATA.find((d) => d.patient.id === id);
}}
"""
        with open(ts_path, "w", encoding="utf-8") as f:
            f.write(ts_content)
        print(f"Exported TypeScript offline cache to: {ts_path}")


if __name__ == "__main__":
    asyncio.run(run_seed())


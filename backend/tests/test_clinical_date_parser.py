import datetime
from app.utils.clinical_date_parser import parse_clinical_date


def test_parse_clinical_date_various_formats():
    assert parse_clinical_date("Patient: Rajesh | Date: 22-Jul-2026\nHbA1c: 7.1%") == datetime.date(2026, 7, 22)
    assert parse_clinical_date("APOLLO HOSPITALS\nScheduled Date: 18-Oct-2026\nPatient: Rajesh") == datetime.date(2026, 10, 18)
    assert parse_clinical_date("Emergency Pulmonology Evaluation | Date: 10-Nov-2025\nPEF: 280") == datetime.date(2025, 11, 10)
    assert parse_clinical_date("MANIPAL HOSPITALS HEMATOLOGY REPORT\nPatient: Priya Nair | Date: 28-Jan-2026") == datetime.date(2026, 1, 28)
    assert parse_clinical_date("ORTHOPEDIC CLINIC CONSULT\nDate: 10-Apr-2026 | Pt: Sunita") == datetime.date(2026, 4, 10)
    assert parse_clinical_date("BONE MINERAL & RENAL PROFILE\nPatient: Sunita Deshmukh | Date: 14-Jul-2026") == datetime.date(2026, 7, 14)
    assert parse_clinical_date("ANNUAL GERIATRIC MOBILITY & RENAL REVIEW\nPatient: Sunita | Date: 25-Sep-2026") == datetime.date(2026, 9, 25)
    assert parse_clinical_date("Collection Date: 15/01/2026") == datetime.date(2026, 1, 15)
    assert parse_clinical_date("Report Date: 2025-05-12") == datetime.date(2025, 5, 12)
    assert parse_clinical_date("Sample Date: 12-04-2026") == datetime.date(2026, 4, 12)
    assert parse_clinical_date("दिनांक: 15-10-2025 | जांच रिपोर्ट") == datetime.date(2025, 10, 15)
    assert parse_clinical_date("Some non-date document without timestamps") is None

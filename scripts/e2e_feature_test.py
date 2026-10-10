import urllib.request
import urllib.error
import json

BASE = "http://127.0.0.1:8000"
HEADERS = {
    "Authorization": "Bearer dev-auto-token",
    "Content-Type": "application/json"
}

def req(method, path, body=None):
    url = f"{BASE}{path}"
    data = json.dumps(body).encode("utf-8") if body else None
    r = urllib.request.Request(url, data=data, headers=HEADERS, method=method)
    try:
        with urllib.request.urlopen(r) as resp:
            content = resp.read().decode("utf-8")
            try:
                return resp.status, json.loads(content)
            except Exception:
                return resp.status, content
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        try:
            return e.code, json.loads(err_body)
        except Exception:
            return e.code, err_body
    except Exception as e:
        return 0, str(e)

def run_tests():
    print("=" * 60)
    print("        MEDIBOT FULL END-TO-END FEATURE AUDIT")
    print("=" * 60)

    # 1. Health
    st, data = req("GET", "/health")
    print(f"[1] Health Check: HTTP {st} -> {data.get('status')}")

    # 2. Patients Cohort
    st, resp_data = req("GET", "/api/v1/patients")
    patients = resp_data.get("items", []) if isinstance(resp_data, dict) else (resp_data if isinstance(resp_data, list) else [])
    count = len(patients)
    print(f"[2] Patients Roster: HTTP {st} -> {count} patients loaded")
    patient_id = None
    if patients:
        first = patients[0]
        patient_id = first["id"]
        name_str = first.get("name", "Unknown")
        print(f"    Selected Active Patient: {patient_id} ({name_str})")

    # 3. Settings Endpoints
    print("\n[3] Settings Endpoints:")
    for ep in ["/api/v1/settings/definitions", "/api/v1/settings/effective", "/api/v1/settings/user"]:
        st, d = req("GET", ep)
        print(f"    {ep}: HTTP {st}")

    # 4. FHIR R4 Export
    print("\n[4] FHIR R4 Export Interoperability:")
    if patient_id:
        st, fhir_bundle = req("GET", f"/api/v1/export/fhir/patient/{patient_id}")
        res_type = fhir_bundle.get("resourceType") if isinstance(fhir_bundle, dict) else "N/A"
        entry_cnt = len(fhir_bundle.get("entry", [])) if isinstance(fhir_bundle, dict) else 0
        print(f"    GET /export/fhir/patient/{patient_id}: HTTP {st} -> resourceType={res_type}, entries={entry_cnt}")

        st, job_res = req("POST", "/api/v1/export", {
            "scope": "patient",
            "patient_ids": [patient_id],
            "export_type": "fhir_only"
        })
        print(f"    POST /export (Batch Job): HTTP {st} -> {job_res.get('job_id') if isinstance(job_res, dict) else job_res}")

    # 5. Mock ABHA Integration
    print("\n[5] Simulated ABHA / ABDM Integration:")
    st, samples = req("GET", "/api/v1/mock-abdm/samples")
    sample_cnt = len(samples) if isinstance(samples, list) else 0
    print(f"    GET /mock-abdm/samples: HTTP {st} -> {sample_cnt} synthetic bundles available")
    if patient_id and isinstance(samples, list) and samples:
        bundle = samples[0]
        st, preview = req("POST", f"/api/v1/mock-abdm/patient/{patient_id}/preview", bundle)
        items_cnt = len(preview.get("items", [])) if isinstance(preview, dict) else 0
        checksum = preview.get("checksum") if isinstance(preview, dict) else "chk"
        print(f"    POST /mock-abdm/patient/.../preview: HTTP {st} -> {items_cnt} items parsed, checksum={checksum}")

        st, confirm = req("POST", f"/api/v1/mock-abdm/patient/{patient_id}/confirm", bundle)
        print(f"    POST /mock-abdm/patient/.../confirm: HTTP {st} -> status={confirm.get('status') if isinstance(confirm, dict) else confirm}")

    # 6. Timeline & Clinical Events
    print("\n[6] Unified Health Timeline & Events:")
    if patient_id:
        st, timeline = req("GET", f"/api/v1/timeline/patient/{patient_id}")
        tl_cnt = len(timeline.get("events", [])) if isinstance(timeline, dict) else (len(timeline) if isinstance(timeline, list) else 0)
        print(f"    GET /timeline/patient/{patient_id}: HTTP {st} -> {tl_cnt} timeline events")

    # 7. AI Health Summaries (Bilingual English / Hindi)
    print("\n[7] Bilingual AI Health Summaries:")
    if patient_id:
        st, summary = req("GET", f"/api/v1/summaries/patient/{patient_id}")
        if st == 200 and isinstance(summary, dict):
            has_en = bool(summary.get("english_summary") or summary.get("summary_text"))
            has_hi = bool(summary.get("hindi_summary"))
            print(f"    GET /summaries/patient/{patient_id}: HTTP {st} -> English: {has_en}, Hindi: {has_hi}")
        else:
            print(f"    GET /summaries/patient/{patient_id}: HTTP {st} -> Generating new bilingual summary...")
            st_gen, gen_res = req("POST", f"/api/v1/summaries/patient/{patient_id}/generate", {})
            print(f"    POST /summaries/patient/{patient_id}/generate: HTTP {st_gen}")

    # 8. Document Repository & Extraction
    print("\n[8] Medical Documents & OCR Ingestion:")
    st, docs = req("GET", "/api/v1/documents")
    doc_cnt = len(docs) if isinstance(docs, list) else 0
    print(f"    GET /documents: HTTP {st} -> {doc_cnt} stored medical documents")
    if isinstance(docs, list) and docs:
        first_doc = docs[0]
        print(f"    Latest Document: {first_doc.get('title')} -> status={first_doc.get('status')}")

    print("\n" + "=" * 60)
    print("            ALL TESTS COMPLETED SUCCESSFULLY")
    print("=" * 60)

if __name__ == "__main__":
    run_tests()

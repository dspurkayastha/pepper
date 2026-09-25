import uuid
from datetime import date, timedelta

BREAST = {
    "procedure": "Modified radical mastectomy",
    "diagnosis": "Ca breast, left, IDC",
    "approach": "open",
    "role": "primary_surgeon",
    "duration_min": 118,
    "blood_loss_ml": 150,
    "clinical_stage": {"t": "T2", "n": "N1", "m": "M0", "group": "IIB"},
    "neoadjuvant": {"given": True, "regimen": "AC x 4 then T x 4", "response": "partial"},
    "laterality": "left",
    "er": "positive",
    "her2": "negative",
    "breast_procedure": "mrm",
    "axilla": "alnd",
}


def case_body(template="breast", data=None, performed_on=None):
    return {
        "local_ref": str(uuid.uuid4()),
        "template": template,
        "performed_on": (performed_on or date(2026, 9, 25)).isoformat(),
        "data": data if data is not None else dict(BREAST),
    }


async def test_templates_describe_all_sites(api):
    body = (await api.get("/v1/clinical/templates")).json()
    keys = [t["key"] for t in body["templates"]]
    assert keys == ["breast", "upper_gi", "colorectal", "hpb", "gynae_onc", "skin_surface", "sarcoma", "general", "endoscopy"]
    assert "NCCN" in body["standards"]["surveillance"]


async def test_create_breast_case(api):
    res = await api.post("/v1/clinical/cases", json=case_body())
    assert res.status_code == 201, res.text
    case = res.json()
    assert case["histopath_status"] == "pending"
    assert case["data"]["clinical_stage"]["t"] == "T2"


async def test_rejects_bad_stage_and_unknown_fields(api):
    bad_stage = case_body(data={**BREAST, "clinical_stage": {"t": "T9"}})
    assert (await api.post("/v1/clinical/cases", json=bad_stage)).status_code == 422
    extra = case_body(data={**BREAST, "patient_name": "anyone"})
    assert (await api.post("/v1/clinical/cases", json=extra)).status_code == 422


async def test_rejects_identifiers_in_free_text(api):
    res = await api.post("/v1/clinical/cases", json=case_body(data={**BREAST, "notes": "UHID 20431"}))
    assert res.status_code == 422
    assert "identifiers" in res.json()["detail"]["message"]


async def test_histopath_and_node_check(api):
    case = (await api.post("/v1/clinical/cases", json=case_body())).json()
    bad = await api.post(f"/v1/clinical/cases/{case['id']}/histopath",
                         json={"data": {"nodes_examined": 10, "nodes_positive": 12}})
    assert bad.status_code == 422
    ok = await api.post(f"/v1/clinical/cases/{case['id']}/histopath", json={"data": {
        "pt": "ypT1c", "pn": "ypN1a", "margin": "R0", "nodes_examined": 18, "nodes_positive": 2, "rcb_class": "II",
    }})
    assert ok.status_code == 200, ok.text
    assert ok.json()["histopath_status"] == "reported"


async def test_general_case_has_no_histopath(api):
    body = case_body("general", {"procedure": "Lap cholecystectomy", "indication": "Symptomatic gallstones"})
    case = (await api.post("/v1/clinical/cases", json=body)).json()
    assert case["histopath_status"] == "not_applicable"
    res = await api.post(f"/v1/clinical/cases/{case['id']}/histopath", json={"data": {}})
    assert res.status_code == 400


async def test_endoscopy_biopsy_tracking(api):
    data = {"procedure": "UGIE", "scope": "ugi", "indication": "Dyspepsia", "biopsies_taken": True}
    case = (await api.post("/v1/clinical/cases", json=case_body("endoscopy", data))).json()
    assert case["histopath_status"] == "pending"
    res = await api.post(f"/v1/clinical/cases/{case['id']}/complications", json={"day": 30, "check": {"grade": "none"}})
    assert res.status_code == 400


async def test_hpb_only_grades(api):
    case = (await api.post("/v1/clinical/cases", json=case_body())).json()
    res = await api.post(f"/v1/clinical/cases/{case['id']}/complications",
                         json={"day": 30, "check": {"grade": "II", "popf": "B"}})
    assert res.status_code == 422
    hpb = {"procedure": "Whipple", "diagnosis": "Periampullary Ca", "organ": "periampullary", "resection": "PPPD"}
    hcase = (await api.post("/v1/clinical/cases", json=case_body("hpb", hpb))).json()
    res = await api.post(f"/v1/clinical/cases/{hcase['id']}/complications",
                         json={"day": 30, "check": {"grade": "IIIa", "popf": "B", "reoperation": False}})
    assert res.status_code == 200, res.text


async def test_patch_merges_and_revalidates(api):
    case = (await api.post("/v1/clinical/cases", json=case_body())).json()
    res = await api.patch(f"/v1/clinical/cases/{case['id']}", json={"data": {"duration_min": 130}, "status": "confirmed"})
    assert res.json()["data"]["duration_min"] == 130 and res.json()["status"] == "confirmed"
    bad = await api.patch(f"/v1/clinical/cases/{case['id']}", json={"data": {"laterality": "middle"}})
    assert bad.status_code == 422


async def test_due_and_summary(api):
    today = date(2026, 12, 31)
    old = (await api.post("/v1/clinical/cases", json=case_body(performed_on=today - timedelta(days=95)))).json()
    recent = (await api.post("/v1/clinical/cases", json=case_body(performed_on=today - timedelta(days=40)))).json()
    await api.post(f"/v1/clinical/cases/{old['id']}/complications", json={"day": 30, "check": {"grade": "IIIb"}})
    await api.post(f"/v1/clinical/cases/{recent['id']}/complications", json={"day": 30, "check": {"grade": "I"}})
    await api.post(f"/v1/clinical/cases/{old['id']}/histopath",
                   json={"data": {"margin": "R0", "nodes_examined": 20, "nodes_positive": 0}})

    due = (await api.get("/v1/clinical/due", params={"today": today.isoformat()})).json()
    assert [(c["case_id"], c["day"]) for c in due["complication_checks"]] == [(old["id"], 90)]
    assert [p["case_id"] for p in due["histopath_pending"]] == [recent["id"]]

    s = (await api.get("/v1/clinical/summary", params={"year": 2026})).json()
    assert s["total"] == 2 and s["by_template"] == {"breast": 2}
    assert s["r0_rate"] == 1.0 and s["median_node_yield"] == 20
    assert s["major_complication_rate_30d"] == 0.5 and s["histopath_pending"] == 1

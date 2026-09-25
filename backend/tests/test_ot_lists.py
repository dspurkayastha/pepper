import json

READ = {
    "list_date": "2026-09-26",
    "items": [
        {"time": "08:00", "procedure": "Modified radical mastectomy, left", "diagnosis": "Ca breast", "age": 52,
         "sex": "F", "side": "left", "template": "breast", "post_nact": True, "notes": "2 units"},
        {"time": None, "procedure": "WLE + sentinel lymph node biopsy", "diagnosis": "Ca breast", "age": 45,
         "sex": "F", "side": None, "template": "breast", "post_nact": False, "notes": "UHID 20431556"},
        {"time": "14:00", "procedure": "Colonoscopy", "diagnosis": None, "age": None, "sex": None, "side": None,
         "template": "endoscopy", "post_nact": False, "notes": None},
    ],
    "warnings": ["Row 3 time partly illegible"],
}


async def test_parse_whatsapp_text(api, fake):
    fake.message_reply = ("end_turn", json.dumps(READ))
    res = await api.post("/v1/ot-lists/parse", json={"source": "whatsapp_text", "text": "Tomorrow OT: 1) MRM..."})
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["list_date"] == "2026-09-26" and len(body["items"]) == 3

    mrm, wle, scope = body["items"]
    labels = [c["label"] for c in mrm["checks"]]
    assert "Tumour clip marked" in labels and "Blood cross-matched" in labels
    assert wle["notes"] is None  # identifier stripped
    assert any("possible identifier" in w for w in body["warnings"])
    assert "Bowel prep" in [c["label"] for c in scope["checks"]]

    call = next(entry[1] for entry in fake.log if entry[0] == "messages.create")
    assert call["model"] == "claude-opus-5"
    assert call["fallbacks"] == "default" and call["betas"] == ["server-side-fallback-2026-07-01"]
    assert call["output_config"]["format"]["type"] == "json_schema"


async def test_parse_photo_sends_image(api, fake):
    fake.message_reply = ("end_turn", json.dumps({**READ, "list_date": None}))
    res = await api.post("/v1/ot-lists/parse", json={
        "source": "paper_photo", "image_b64": "aGVsbG8=", "media_type": "image/jpeg",
    })
    assert res.status_code == 201
    call = next(entry[1] for entry in fake.log if entry[0] == "messages.create")
    assert call["messages"][0]["content"][0]["type"] == "image"

    list_id = res.json()["id"]
    assert (await api.post(f"/v1/ot-lists/{list_id}/confirm", json={})).status_code == 422
    confirmed = await api.post(f"/v1/ot-lists/{list_id}/confirm", json={"list_date": "2026-09-26"})
    assert confirmed.json()["status"] == "confirmed"


async def test_tick_a_check(api, fake):
    fake.message_reply = ("end_turn", json.dumps(READ))
    body = (await api.post("/v1/ot-lists/parse", json={"source": "whatsapp_text", "text": "..."})).json()
    item = body["items"][1]
    res = await api.post(f"/v1/ot-lists/{body['id']}/items/{item['id']}/checks",
                         json={"label": "Lymphoscintigraphy / dye booked", "done": True})
    checks = {c["label"]: c["done"] for c in res.json()["items"][1]["checks"]}
    assert checks["Lymphoscintigraphy / dye booked"] is True


async def test_refusal_and_bad_input(api, fake):
    fake.message_reply = ("refusal", None)
    res = await api.post("/v1/ot-lists/parse", json={"source": "whatsapp_text", "text": "..."})
    assert res.status_code == 422
    res = await api.post("/v1/ot-lists/parse", json={"source": "paper_photo", "image_b64": "eA==", "media_type": "image/tiff"})
    assert res.status_code == 422
    assert (await api.post("/v1/ot-lists/parse", json={"source": "whatsapp_text"})).status_code == 422

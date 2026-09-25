import asyncio
import json

from conftest import ev, text_block

from pepper.agent import runtime

ESCALATE = {
    "lane": "company", "category": "content", "question": "Publish this week's seven posts?",
    "context": "Drafted in your voice.", "blocking": True, "risky": True, "recommendation": "all",
    "options": [{"id": "all", "label": "Publish all 7"}, {"id": "linkedin", "label": "LinkedIn only"}],
}


def idle(id_, reason):
    return ev("session.status_idle", id_, stop_reason={"type": reason})


async def events_of(api, thread_id):
    res = await api.get(f"/v1/threads/{thread_id}/events", params={"follow": "false"})
    assert res.status_code == 200
    out = []
    for block in res.text.strip().split("\n\n"):
        data = next(line[6:] for line in block.splitlines() if line.startswith("data: "))
        out.append(json.loads(data))
    return out


async def test_escalation_round_trip(api, fake):
    def responder(session_id, events):
        first = events[0]
        if first["type"] == "user.message":
            return [
                ev("session.status_running", "e1"),
                ev("agent.tool_use", "e2", name="bash"),
                ev("agent.message", "e3", content=[text_block("Drafted seven posts.")]),
                ev("agent.custom_tool_use", "tu_1", name="escalate", input=ESCALATE),
                idle("e4", "requires_action"),
            ]
        if first["type"] == "user.custom_tool_result":
            return [ev("agent.message", "e5", content=[text_block("Scheduled.")]), idle("e6", "end_turn")]
        return []

    fake.responder = responder
    thread = (await api.post("/v1/threads", json={"title": "Content", "lane": "company"})).json()
    create = next(e[1] for e in fake.log if e[0] == "create_session")
    assert create["agent"] == "agent_1" and create["vault_ids"] == ["vlt_1"]

    res = await api.post(f"/v1/threads/{thread['id']}/messages", json={"text": "Draft this week's posts"})
    assert res.status_code == 202
    await asyncio.wait_for(runtime.pump.wait("sesn_1"), 5)

    # Stream-first: the stream was opened before the message was sent.
    order = [e[0] for e in fake.log if e[0] in ("stream", "send")]
    assert order[:2] == ["stream", "send"]

    kinds = [e["kind"] for e in await events_of(api, thread["id"])]
    assert kinds == ["user", "status", "activity", "text", "decision", "status"]
    assert (await api.get(f"/v1/threads/{thread['id']}")).json()["state"] == "needs_you"

    pending = (await api.get("/v1/decisions")).json()["decisions"]
    assert len(pending) == 1 and pending[0]["risky"] and pending[0]["blocking"]
    decision_id = pending[0]["id"]

    assert (await api.post(f"/v1/decisions/{decision_id}", json={"choice": "nope"})).status_code == 422
    res = await api.post(f"/v1/decisions/{decision_id}", json={"choice": "all", "note": "go"})
    assert res.status_code == 200 and res.json()["status"] == "resolved"
    await asyncio.wait_for(runtime.pump.wait("sesn_1"), 5)

    result = [e for e in fake.log if e[0] == "send"][-1][2][0]
    assert result["type"] == "user.custom_tool_result" and result["custom_tool_use_id"] == "tu_1"
    assert json.loads(result["content"][0]["text"].split(": ", 1)[1])["choice"] == "all"
    assert (await api.get(f"/v1/threads/{thread['id']}")).json()["state"] == "idle"
    assert (await api.post(f"/v1/decisions/{decision_id}", json={"choice": "all"})).status_code == 409

    # Resume: replay only what came after a given event id.
    all_events = await events_of(api, thread["id"])
    res = await api.get(f"/v1/threads/{thread['id']}/events", params={"follow": "false", "after": all_events[-2]["id"]})
    assert res.text.count("data: ") == 1


async def test_notify_is_answered_and_turn_continues(api, fake):
    def responder(session_id, events):
        if events[0]["type"] == "user.message":
            return [
                ev("agent.custom_tool_use", "tu_n", name="notify",
                   input={"lane": "company", "title": "Report ready", "body": "Weekly report is in."}),
                idle("e1", "requires_action"),
            ]
        if events[0]["type"] == "user.custom_tool_result":
            return [ev("agent.message", "e2", content=[text_block("Done.")]), idle("e3", "end_turn")]
        return []

    fake.responder = responder
    thread = (await api.post("/v1/threads", json={"lane": "company", "text": "Write the report"})).json()
    await asyncio.wait_for(runtime.pump.wait("sesn_1"), 5)
    sent = [e[2][0]["type"] for e in fake.log if e[0] == "send"]
    assert sent == ["user.message", "user.custom_tool_result"]
    kinds = [e["kind"] for e in await events_of(api, thread["id"])]
    assert kinds == ["user", "notice", "status", "text", "status"]
    assert (await api.get(f"/v1/threads/{thread['id']}")).json()["state"] == "idle"


async def test_invalid_escalation_is_bounced(api, fake):
    def responder(session_id, events):
        if events[0]["type"] == "user.message":
            return [ev("agent.custom_tool_use", "tu_bad", name="escalate", input={"question": "?"}),
                    idle("e1", "requires_action")]
        return [idle("e2", "end_turn")]

    fake.responder = responder
    await api.post("/v1/threads", json={"lane": "life", "text": "hi"})
    await asyncio.wait_for(runtime.pump.wait("sesn_1"), 5)
    sends = [e[2][0] for e in fake.log if e[0] == "send"]
    assert sends[1]["type"] == "user.custom_tool_result" and "Invalid escalate input" in sends[1]["content"][0]["text"]
    assert (await api.get("/v1/decisions")).json()["decisions"] == []


async def test_scheduled_run_arrives_by_webhook(api, fake):
    fake.session_meta["sesn_sched"] = {"title": "Wednesday content", "metadata": {"lane": "company", "origin": "scheduled"}}
    fake.history["sesn_sched"] = [
        ev("user.define_outcome", "u1"),
        ev("agent.message", "m1", content=[text_block("Batch drafted.")]),
        ev("agent.custom_tool_use", "tu_s", name="escalate", input=ESCALATE),
        idle("i1", "requires_action"),
    ]
    payload = json.dumps({"id": "wh_1", "data": {"type": "session.requires_action", "id": "sesn_sched"}})

    assert (await api.post("/hooks/anthropic", content=payload, headers={"webhook-signature": "bad"})).status_code == 400
    res = await api.post("/hooks/anthropic", content=payload, headers={"webhook-signature": "valid"})
    assert res.status_code == 204

    threads = (await api.get("/v1/threads")).json()["threads"]
    assert [(t["title"], t["origin"], t["state"]) for t in threads] == [("Wednesday content", "scheduled", "needs_you")]
    assert len((await api.get("/v1/decisions")).json()["decisions"]) == 1

    # A retried delivery is ignored, and re-syncing never duplicates the decision.
    await api.post("/hooks/anthropic", content=payload, headers={"webhook-signature": "valid"})
    assert len([e for e in fake.log if e[0] == "list"]) == 1
    await runtime.sync_session("sesn_sched")
    assert len((await api.get("/v1/decisions")).json()["decisions"]) == 1

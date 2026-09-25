# Pepper backend

FastAPI server between the Pepper iOS app and Anthropic Managed Agents. It holds
the case log, reads OT lists, relays Pepper's decisions to the phone, and keeps
every secret server-side or in the Anthropic vault.

## Run

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env            # fill in ANTHROPIC_API_KEY, PEPPER_APP_TOKEN, webhook secret
python scripts/setup_agent.py   # once, and after changing the agent or schedules
uvicorn pepper.main:app --port 8080
pytest                          # 39 tests, no network needed
```

Docker: `docker build -t pepper . && docker run -p 8080:8080 --env-file .env -v pepper-data:/var/lib/pepper pepper`

Register `https://<host>/hooks/anthropic` in Console → Manage → Webhooks for the
`session.*` events. This is how scheduled runs reach the phone.

## How it fits together

| Piece | Where |
|---|---|
| Agent, environment, vault, weekly schedules (Mon/Wed/Fri, IST) | `scripts/setup_agent.py` (control plane, writes `agent_ids.json`) |
| Session streaming (stream-first), event store, SSE with resume | `pepper/agent/runtime.py`, `pepper/api/threads.py` |
| `escalate` / `notify` tools → decisions and pushes | `pepper/agent/tools.py`, `pepper/api/decisions.py` |
| Webhook catch-up for sessions nobody is watching | `pepper/api/webhooks.py` → `runtime.sync_session` |
| Secrets → Anthropic vault (never stored here) | `pepper/api/integrations.py` |
| Case templates (AJCC/FIGO, Clavien-Dindo, ISGPS/ISGLS) | `pepper/clinical/templates.py` |
| Due histopath and complication checks; practice metrics | `pepper/clinical/outcomes.py` |
| OT list from WhatsApp text or photo → cases + prep checklist | `pepper/intake/ot_list.py`, `pepper/clinical/prep.py` |
| Identifier guard for free text | `pepper/privacy.py` |
| Per-device tokens (enrol with the bootstrap secret) | `pepper/security.py`, `pepper/api/devices.py` |

## API (all under `Authorization: Bearer <device token>` except enrol, health and webhooks)

- `POST /v1/devices/enroll` (bootstrap token) · `GET /v1/devices` · `PATCH /v1/devices/me` · `DELETE /v1/devices/{id}`
- `POST /v1/threads` · `GET /v1/threads` · `POST /v1/threads/{id}/messages` · `GET /v1/threads/{id}/events` (SSE; `Last-Event-ID` or `?after=` to resume) · `POST /v1/threads/{id}/archive`
- `GET /v1/decisions` · `POST /v1/decisions/{id}` `{choice, note}`
- `GET /v1/integrations/schema` · `GET|POST /v1/integrations/credentials` · `DELETE /v1/integrations/credentials/{name}`
- `GET /v1/clinical/templates` · `POST|GET /v1/clinical/cases` · `GET|PATCH /v1/clinical/cases/{id}` · `POST /v1/clinical/cases/{id}/histopath` · `POST /v1/clinical/cases/{id}/complications` · `GET /v1/clinical/due` · `GET /v1/clinical/summary`
- `POST /v1/ot-lists/parse` · `GET /v1/ot-lists` · `GET /v1/ot-lists/{id}` · `POST /v1/ot-lists/{id}/items/{item}/checks` · `POST /v1/ot-lists/{id}/confirm`
- `GET /health` · `GET /v1/products` · `POST /hooks/anthropic`

SSE event kinds: `user`, `text`, `activity`, `decision`, `decision_resolved`, `notice`, `status`, `error`.

## Privacy rules enforced here

- Case records carry an opaque `local_ref`; names and hospital numbers stay in the phone's encrypted store.
- Every template rejects unknown fields; free text that looks like an ID, phone number, email or "Mrs X" is rejected (cases) or stripped with a warning (OT lists).
- OT-list photos must be de-identified on the phone before upload.

## Known limits

- SSH keys and Namecheap can't go in the vault (not HTTP / key in URL). They need a backend-run tool (Phase 1).
- Events fan out in-process, so run a single server instance until a shared broker (e.g. Postgres LISTEN/NOTIFY) is added.

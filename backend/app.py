"""
Pepper Backend Relay — FastAPI server that sits between the iOS app and
Anthropic's Managed Agents API.

Why this exists:
- Keeps the Anthropic API key server-side (not embedded in the app)
- Dispatches push notifications when Pepper raises [ESCALATE] blocks
- Runs scheduled Pepper tasks (weekly rhythm) via background scheduler
- Stores credentials encrypted, proxied to Pepper sessions via vaults

Deploy on the Oracle server alongside everything else.
"""

import asyncio
import json
import os
import re
import secrets
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncGenerator

import anthropic
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from cryptography.fernet import Fernet
from fastapi import Depends, FastAPI, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DATA_DIR = Path(os.getenv("PEPPER_DATA_DIR", "/var/lib/pepper"))
AGENT_IDS_PATH = Path(os.getenv("PEPPER_AGENT_IDS", "agent_ids.json"))

# Derived at startup
_fernet: Fernet | None = None
_agent_ids: dict = {}
_apns_tokens: set[str] = set()

# In-memory stores (persist to disk on write)
_escalations: dict[str, dict] = {}  # id -> escalation
_sessions: dict[str, dict] = {}     # session_id -> metadata
_scheduler: AsyncIOScheduler | None = None


def _cleanup_stale_data():
    """Evict old sessions and escalations to prevent unbounded memory growth."""
    max_sessions, max_escalations = 100, 500
    if len(_sessions) > max_sessions:
        sorted_keys = sorted(_sessions, key=lambda k: _sessions[k].get("created", ""))
        for k in sorted_keys[:len(_sessions) - max_sessions]:
            del _sessions[k]
    if len(_escalations) > max_escalations:
        sorted_keys = sorted(_escalations, key=lambda k: _escalations[k].get("timestamp", ""))
        for k in sorted_keys[:len(_escalations) - max_escalations]:
            del _escalations[k]


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def _get_fernet() -> Fernet:
    """Derive Fernet key from PEPPER_SECRET. Must be set at startup."""
    global _fernet
    if _fernet is None:
        secret = os.getenv("PEPPER_SECRET")
        if not secret:
            raise RuntimeError("PEPPER_SECRET not set")
        # Derive a 32-byte key from the secret
        import hashlib, base64
        key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
        _fernet = Fernet(key)
    return _fernet


def _encrypt(value: str) -> str:
    return _get_fernet().encrypt(value.encode()).decode()


def _decrypt(value: str) -> str:
    return _get_fernet().decrypt(value.encode()).decode()


def _load_credentials() -> dict:
    creds_path = DATA_DIR / "credentials.enc.json"
    if not creds_path.exists():
        return {}
    data = json.loads(creds_path.read_text())
    return {k: _decrypt(v) for k, v in data.items()}


def _save_credentials(creds: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    encrypted = {k: _encrypt(v) for k, v in creds.items()}
    (DATA_DIR / "credentials.enc.json").write_text(json.dumps(encrypted, indent=2))


def _load_agent_ids() -> dict:
    """Load agent/environment/vault IDs from deploy output."""
    global _agent_ids
    if AGENT_IDS_PATH.exists():
        _agent_ids = json.loads(AGENT_IDS_PATH.read_text())
    return _agent_ids


# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------

async def verify_token(authorization: str = Header(...)) -> str:
    """Verify the Bearer token matches PEPPER_APP_TOKEN."""
    expected = os.getenv("PEPPER_APP_TOKEN")
    if not expected:
        raise HTTPException(500, "PEPPER_APP_TOKEN not configured on server")
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing Bearer token")
    token = authorization[7:]
    if not secrets.compare_digest(token, expected):
        raise HTTPException(401, "Invalid token")
    return token


# ---------------------------------------------------------------------------
# Anthropic client helpers
# ---------------------------------------------------------------------------

def _get_anthropic_client() -> anthropic.Anthropic:
    creds = _load_credentials()
    api_key = creds.get("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(500, "Anthropic API key not configured")
    return anthropic.Anthropic(api_key=api_key)


def _create_pepper_session(client: anthropic.Anthropic) -> str:
    """Create a new Pepper session with agent/env/vault from agent_ids."""
    ids = _load_agent_ids()
    if not ids.get("agent_id"):
        raise HTTPException(500, "Agent not deployed. Run deploy_agent.py first.")

    kwargs = {
        "agent": ids["agent_id"],
        "environment_id": ids["environment_id"],
    }
    if ids.get("vault_id"):
        kwargs["vault_ids"] = [ids["vault_id"]]

    session = client.beta.sessions.create(**kwargs)
    _sessions[session.id] = {
        "id": session.id,
        "created": datetime.now(timezone.utc).isoformat(),
        "message_count": 0,
        "status": "active",
    }
    return session.id


# ---------------------------------------------------------------------------
# Escalation detection
# ---------------------------------------------------------------------------

_ESCALATE_PATTERN = re.compile(
    r"\[ESCALATE\]\s*—\s*Category:\s*(.+?)$"
    r".*?What:\s*(.+?)$"
    r".*?Context:\s*(.+?)$"
    r".*?(?:Options:\s*(.+?)$)?"
    r".*?Recommendation:\s*(.+?)$"
    r".*?Blocking:\s*(.+?)$",
    re.MULTILINE | re.DOTALL,
)


def _detect_escalations(text: str, session_id: str) -> list[dict]:
    """Parse [ESCALATE] blocks from Pepper's response."""
    if len(text) > 100_000:
        return []
    escalations = []
    for match in _ESCALATE_PATTERN.finditer(text):
        esc = {
            "id": str(uuid.uuid4()),
            "session_id": session_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "category": match.group(1).strip(),
            "what": match.group(2).strip(),
            "context": match.group(3).strip(),
            "options": match.group(4).strip() if match.group(4) else "",
            "recommendation": match.group(5).strip(),
            "blocking": match.group(6).strip().lower() in ("yes", "true"),
            "status": "pending",
        }
        escalations.append(esc)
        _escalations[esc["id"]] = esc
    return escalations


# ---------------------------------------------------------------------------
# Push notifications (APNs)
# ---------------------------------------------------------------------------

async def _send_push_notification(title: str, body: str, data: dict | None = None):
    """Send push notification to all registered devices.
    Uses APNs via the aioapns library if configured, otherwise logs."""
    if not _apns_tokens:
        return

    try:
        from aioapns import APNs, NotificationRequest, PushType
        apns_key_path = os.getenv("APNS_KEY_PATH")
        apns_key_id = os.getenv("APNS_KEY_ID")
        apns_team_id = os.getenv("APNS_TEAM_ID")
        bundle_id = os.getenv("APNS_BUNDLE_ID", "com.sciscribe.pepper")

        if not all([apns_key_path, apns_key_id, apns_team_id]):
            print(f"[PUSH SKIPPED] {title}: {body}")
            return

        apns = APNs(
            key=apns_key_path,
            key_id=apns_key_id,
            team_id=apns_team_id,
            topic=bundle_id,
            use_sandbox=os.getenv("APNS_SANDBOX", "true").lower() == "true",
        )

        for token in _apns_tokens:
            request = NotificationRequest(
                device_token=token,
                message={
                    "aps": {
                        "alert": {"title": title, "body": body},
                        "sound": "default",
                        "badge": sum(1 for e in _escalations.values() if e["status"] == "pending"),
                    },
                    "data": data or {},
                },
                push_type=PushType.ALERT,
            )
            await apns.send_notification(request)

    except ImportError:
        print(f"[PUSH LOG] {title}: {body}")
    except Exception as exc:
        print(f"[PUSH ERROR] {exc}")


# ---------------------------------------------------------------------------
# SSE streaming
# ---------------------------------------------------------------------------

async def _stream_pepper_response(
    client: anthropic.Anthropic,
    session_id: str,
) -> AsyncGenerator[str, None]:
    """Stream Pepper's response as SSE events to the iOS app in real-time."""
    full_text_chunks: list[str] = []
    queue: asyncio.Queue = asyncio.Queue()

    def _blocking_stream():
        """Run in thread — pushes events to the async queue as they arrive."""
        try:
            with client.beta.sessions.events.stream(session_id=session_id) as stream:
                for event in stream:
                    queue.put_nowait(event)
        except Exception as exc:
            queue.put_nowait(exc)
        finally:
            queue.put_nowait(None)  # Sentinel: stream ended

    # Start the blocking stream in a background thread
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, _blocking_stream)

    # Yield SSE events as they arrive from the queue
    while True:
        event = await queue.get()

        if event is None:
            # Stream ended
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            return

        if isinstance(event, Exception):
            yield f"data: {json.dumps({'type': 'error', 'message': str(event)})}\n\n"
            return

        match event.type:
            case "agent.message":
                for block in event.content:
                    if hasattr(block, "text"):
                        full_text_chunks.append(block.text)
                        sse_data = json.dumps({
                            "type": "message",
                            "text": block.text,
                        })
                        yield f"data: {sse_data}\n\n"

            case "agent.thinking":
                yield f"data: {json.dumps({'type': 'thinking'})}\n\n"

            case "agent.tool_use":
                name = getattr(event, "tool_name", getattr(event, "name", "?"))
                yield f"data: {json.dumps({'type': 'tool_use', 'name': name})}\n\n"

            case "agent.mcp_tool_use":
                name = getattr(event, "tool_name", getattr(event, "name", "?"))
                yield f"data: {json.dumps({'type': 'mcp_tool_use', 'name': name})}\n\n"

            case "session.status_idle":
                # Check for escalations in the full response
                full_text = "".join(full_text_chunks)
                escalations = _detect_escalations(full_text, session_id)
                for esc in escalations:
                    yield f"data: {json.dumps({'type': 'escalation', **esc})}\n\n"
                    await _send_push_notification(
                        title=f"[{esc['category']}] Decision needed",
                        body=esc["what"],
                        data={"escalation_id": esc["id"], "session_id": session_id},
                    )
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                return

            case "session.error":
                error_msg = str(getattr(event, "error", "Unknown error"))
                yield f"data: {json.dumps({'type': 'error', 'message': error_msg})}\n\n"
                return

            case "session.status_terminated":
                yield f"data: {json.dumps({'type': 'terminated'})}\n\n"
                return


# ---------------------------------------------------------------------------
# Scheduled tasks (weekly rhythm)
# ---------------------------------------------------------------------------

WEEKLY_TASKS = {
    "monday": (
        "It's Monday. Run your weekly planning routine:\n"
        "1. Check all uptime monitors and report any issues\n"
        "2. Review pending [ESCALATE] items\n"
        "3. Generate the weekly task list based on the 8-week plan\n"
        "4. Identify the top 3 priorities for this week\n"
        "Save the weekly plan to /mnt/session/outputs/weekly_plan.md"
    ),
    "wednesday": (
        "It's Wednesday — content day. Generate this week's content batch:\n"
        "1. 3 LinkedIn posts (mix of thought leadership and product)\n"
        "2. 4 X/Twitter posts (insights, engagement, product mentions)\n"
        "3. Suggest posting schedule for each piece\n"
        "Save all content to /mnt/session/outputs/content_batch.docx\n"
        "[ESCALATE] the batch for Dev's review before publishing."
    ),
    "friday": (
        "It's Friday — review day. Generate the weekly summary:\n"
        "1. Tasks completed this week\n"
        "2. Blockers and issues encountered\n"
        "3. Next week's priorities\n"
        "4. Check domain renewal calendar\n"
        "5. Verify backup integrity\n"
        "6. Update 8-week plan progress tracker\n"
        "Save the report to /mnt/session/outputs/weekly_report.md"
    ),
}


async def _run_scheduled_task(day: str):
    """Execute a scheduled Pepper task and notify Dev."""
    message = WEEKLY_TASKS.get(day)
    if not message:
        return

    try:
        client = _get_anthropic_client()
        session_id = _create_pepper_session(client)

        # Send the task
        client.beta.sessions.events.send(
            session_id=session_id,
            events=[{
                "type": "user.message",
                "content": [{"type": "text", "text": message}],
            }],
        )

        # Collect response
        full_text = []
        with client.beta.sessions.events.stream(session_id=session_id) as stream:
            for event in stream:
                if event.type == "agent.message":
                    for block in event.content:
                        if hasattr(block, "text"):
                            full_text.append(block.text)
                elif event.type == "session.status_idle":
                    break
                elif event.type == "session.error":
                    break

        response = "".join(full_text)

        # Detect and notify escalations
        escalations = _detect_escalations(response, session_id)
        if escalations:
            for esc in escalations:
                await _send_push_notification(
                    title=f"[{esc['category']}] {esc['what'][:50]}",
                    body=esc["recommendation"][:100],
                    data={"escalation_id": esc["id"], "session_id": session_id},
                )
        else:
            await _send_push_notification(
                title=f"Pepper: {day.title()} update ready",
                body=f"Your {day} report is ready. Open the app to review.",
                data={"session_id": session_id},
            )

        # Store session for retrieval
        _sessions[session_id]["scheduled_day"] = day
        _sessions[session_id]["response_preview"] = response[:500]

        client.beta.sessions.archive(session_id=session_id)

    except Exception as exc:
        print(f"[SCHEDULER ERROR] {day}: {exc}")
        await _send_push_notification(
            title="Pepper: Scheduled task failed",
            body=str(exc)[:100],
        )


def _setup_scheduler():
    """Configure the weekly rhythm scheduler."""
    global _scheduler
    _scheduler = AsyncIOScheduler()

    # Monday 9:00 AM IST (3:30 AM UTC)
    _scheduler.add_job(
        _run_scheduled_task, CronTrigger(day_of_week="mon", hour=3, minute=30),
        args=["monday"], id="monday_planning",
    )
    # Wednesday 9:00 AM IST
    _scheduler.add_job(
        _run_scheduled_task, CronTrigger(day_of_week="wed", hour=3, minute=30),
        args=["wednesday"], id="wednesday_content",
    )
    # Friday 5:00 PM IST (11:30 AM UTC)
    _scheduler.add_job(
        _run_scheduled_task, CronTrigger(day_of_week="fri", hour=11, minute=30),
        args=["friday"], id="friday_review",
    )

    # Hourly cleanup of stale in-memory data
    _scheduler.add_job(
        _cleanup_stale_data, CronTrigger(minute=0),
        id="hourly_cleanup",
    )

    _scheduler.start()
    print("[SCHEDULER] Weekly rhythm active: Mon/Wed/Fri + hourly cleanup")


# ---------------------------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    _load_agent_ids()

    # Load saved device tokens
    tokens_path = DATA_DIR / "apns_tokens.json"
    if tokens_path.exists():
        _apns_tokens.update(json.loads(tokens_path.read_text()))

    _setup_scheduler()
    print(f"[STARTUP] Pepper Backend Relay — data: {DATA_DIR}")
    yield
    # Shutdown
    if _scheduler:
        _scheduler.shutdown()


app = FastAPI(
    title="Pepper Backend Relay",
    description="Backend for the Pepper iOS app — proxies to Anthropic Managed Agents",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://sciscribesolutions.com",
        "https://app.sciscribesolutions.com",
    ],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class CredentialInput(BaseModel):
    name: str
    value: str

class MessageInput(BaseModel):
    text: str = Field(..., max_length=50000)

class DeviceTokenInput(BaseModel):
    token: str
    platform: str = "ios"

class EscalationResponse(BaseModel):
    decision: str
    notes: str = ""


# ---------------------------------------------------------------------------
# Routes — Health
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    ids = _load_agent_ids()
    return {
        "status": "ok",
        "agent_deployed": bool(ids.get("agent_id")),
        "scheduler_running": _scheduler is not None and _scheduler.running,
        "device_tokens": len(_apns_tokens),
        "pending_escalations": sum(1 for e in _escalations.values() if e["status"] == "pending"),
    }


# ---------------------------------------------------------------------------
# Routes — Credentials
# ---------------------------------------------------------------------------

@app.post("/api/credentials", dependencies=[Depends(verify_token)])
async def add_credential(cred: CredentialInput):
    creds = _load_credentials()
    creds[cred.name] = cred.value
    _save_credentials(creds)
    return {"status": "saved", "name": cred.name}


@app.get("/api/credentials", dependencies=[Depends(verify_token)])
async def list_credentials():
    creds = _load_credentials()
    return {
        "credentials": [
            {"name": k, "configured": bool(v)} for k, v in creds.items()
        ]
    }


@app.delete("/api/credentials/{name}", dependencies=[Depends(verify_token)])
async def delete_credential(name: str):
    creds = _load_credentials()
    if name in creds:
        del creds[name]
        _save_credentials(creds)
    return {"status": "deleted", "name": name}


# Credential schema — tells the iOS app what to collect
CREDENTIAL_SCHEMA = [
    {
        "tier": 1, "label": "Core",
        "description": "Required for Pepper to function",
        "credentials": [
            {"name": "ANTHROPIC_API_KEY", "label": "Anthropic API Key", "hint": "sk-ant-...", "required": True},
            {"name": "GITHUB_TOKEN", "label": "GitHub Token", "hint": "ghp_...", "required": True},
        ],
    },
    {
        "tier": 2, "label": "Infrastructure",
        "description": "Server and domain management",
        "credentials": [
            {"name": "ORACLE_SSH_KEY", "label": "Oracle Cloud SSH Key", "hint": "Paste private key", "required": False, "multiline": True},
            {"name": "HETZNER_SSH_KEY", "label": "Hetzner SSH Key", "hint": "Paste private key", "required": False, "multiline": True},
            {"name": "NAMECHEAP_API_KEY", "label": "Namecheap API Key", "hint": "API key from Namecheap", "required": False},
            {"name": "VERCEL_TOKEN", "label": "Vercel CLI Token", "hint": "From vercel.com/account/tokens", "required": False},
        ],
    },
    {
        "tier": 3, "label": "Product APIs",
        "description": "APIs for specific products",
        "credentials": [
            {"name": "SARVAM_API_KEY", "label": "Sarvam AI API Key", "hint": "For Aakhyan TTS/translation", "required": False},
            {"name": "CLERK_SECRET_KEY", "label": "Clerk Secret Key", "hint": "For Scribe EDC auth", "required": False},
            {"name": "CLERK_PUBLISHABLE_KEY", "label": "Clerk Publishable Key", "hint": "pk_...", "required": False},
        ],
    },
    {
        "tier": 4, "label": "Marketing",
        "description": "Social media and advertising",
        "credentials": [
            {"name": "LINKEDIN_ACCESS", "label": "LinkedIn Scheduling Tool", "hint": "Buffer/Hootsuite API key", "required": False},
            {"name": "TWITTER_ACCESS", "label": "X/Twitter Access", "hint": "Scheduling tool API key", "required": False},
            {"name": "GOOGLE_ADS_ID", "label": "Google Ads Account ID", "hint": "xxx-xxx-xxxx", "required": False},
        ],
    },
    {
        "tier": 5, "label": "Monitoring",
        "description": "Uptime and analytics",
        "credentials": [
            {"name": "UPTIMEROBOT_API_KEY", "label": "UptimeRobot API Key", "hint": "ur-...", "required": False},
            {"name": "ANALYTICS_SITE_ID", "label": "Analytics Site ID", "hint": "Plausible or GA4 measurement ID", "required": False},
        ],
    },
]


@app.get("/api/credentials/schema")
async def get_credential_schema():
    """Returns the credential schema so the iOS app knows what to collect."""
    creds = _load_credentials()
    schema = json.loads(json.dumps(CREDENTIAL_SCHEMA))  # deep copy
    for tier in schema:
        for cred in tier["credentials"]:
            cred["configured"] = cred["name"] in creds
    return {"schema": schema}


# ---------------------------------------------------------------------------
# Routes — Sessions
# ---------------------------------------------------------------------------

@app.post("/api/sessions", dependencies=[Depends(verify_token)])
async def create_session():
    client = _get_anthropic_client()
    session_id = _create_pepper_session(client)
    return {"session_id": session_id, **_sessions[session_id]}


@app.get("/api/sessions", dependencies=[Depends(verify_token)])
async def list_sessions():
    return {"sessions": list(_sessions.values())}


@app.post("/api/sessions/{session_id}/archive", dependencies=[Depends(verify_token)])
async def archive_session(session_id: str):
    client = _get_anthropic_client()
    client.beta.sessions.archive(session_id=session_id)
    if session_id in _sessions:
        _sessions[session_id]["status"] = "archived"
    return {"status": "archived"}


# ---------------------------------------------------------------------------
# Routes — Messages (the core chat endpoint)
# ---------------------------------------------------------------------------

@app.post("/api/sessions/{session_id}/send", dependencies=[Depends(verify_token)])
async def send_message(session_id: str, msg: MessageInput):
    """Send a message to Pepper and stream the response as SSE."""
    client = _get_anthropic_client()

    # Send the message
    client.beta.sessions.events.send(
        session_id=session_id,
        events=[{
            "type": "user.message",
            "content": [{"type": "text", "text": msg.text}],
        }],
    )

    if session_id in _sessions:
        _sessions[session_id]["message_count"] += 1

    # Stream the response as SSE
    return StreamingResponse(
        _stream_pepper_response(client, session_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# Routes — Quick chat (create session + send in one call)
# ---------------------------------------------------------------------------

@app.post("/api/chat", dependencies=[Depends(verify_token)])
async def quick_chat(msg: MessageInput):
    """Create a session, send a message, and stream. For one-shot queries."""
    client = _get_anthropic_client()
    session_id = _create_pepper_session(client)

    client.beta.sessions.events.send(
        session_id=session_id,
        events=[{
            "type": "user.message",
            "content": [{"type": "text", "text": msg.text}],
        }],
    )

    async def _stream_with_session_id():
        yield f"data: {json.dumps({'type': 'session_created', 'session_id': session_id})}\n\n"
        async for chunk in _stream_pepper_response(client, session_id):
            yield chunk

    return StreamingResponse(
        _stream_with_session_id(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# Routes — Escalations
# ---------------------------------------------------------------------------

@app.get("/api/escalations", dependencies=[Depends(verify_token)])
async def list_escalations(status: str = "pending"):
    filtered = [e for e in _escalations.values() if e["status"] == status]
    return {"escalations": sorted(filtered, key=lambda e: e["timestamp"], reverse=True)}


@app.post("/api/escalations/{esc_id}/respond", dependencies=[Depends(verify_token)])
async def respond_to_escalation(esc_id: str, response: EscalationResponse):
    if esc_id not in _escalations:
        raise HTTPException(404, "Escalation not found")

    esc = _escalations[esc_id]
    esc["status"] = "resolved"
    esc["response"] = response.decision
    esc["response_notes"] = response.notes
    esc["resolved_at"] = datetime.now(timezone.utc).isoformat()

    # Forward the decision to the Pepper session if still active
    session_id = esc.get("session_id")
    if session_id and session_id in _sessions and _sessions[session_id]["status"] == "active":
        try:
            client = _get_anthropic_client()
            client.beta.sessions.events.send(
                session_id=session_id,
                events=[{
                    "type": "user.message",
                    "content": [{"type": "text", "text": (
                        f"Re: escalation [{esc['category']}] {esc['what']}\n"
                        f"Decision: {response.decision}\n"
                        f"Notes: {response.notes}"
                    )}],
                }],
            )
        except Exception as exc:
            print(f"[ESCALATION FORWARD] Could not forward response to session: {exc}")

    return {"status": "resolved", "escalation": esc}


# ---------------------------------------------------------------------------
# Routes — Device tokens (push notifications)
# ---------------------------------------------------------------------------

@app.post("/api/devices", dependencies=[Depends(verify_token)])
async def register_device(device: DeviceTokenInput):
    _apns_tokens.add(device.token)
    # Persist
    (DATA_DIR / "apns_tokens.json").write_text(json.dumps(list(_apns_tokens)))
    return {"status": "registered", "total_devices": len(_apns_tokens)}


@app.delete("/api/devices/{token}", dependencies=[Depends(verify_token)])
async def unregister_device(token: str):
    _apns_tokens.discard(token)
    (DATA_DIR / "apns_tokens.json").write_text(json.dumps(list(_apns_tokens)))
    return {"status": "unregistered"}


# ---------------------------------------------------------------------------
# Routes — Product info (for the dashboard)
# ---------------------------------------------------------------------------

PRODUCTS = [
    {
        "id": "sciscribe",
        "name": "SciScribe",
        "tagline": "Manuscript editing & academic services",
        "status": "active",
        "priority": None,
        "stack": "Website on Hetzner",
        "domain": "sciscribesolutions.com",
        "revenue": True,
        "color": "#4A90D9",
    },
    {
        "id": "aakhyan",
        "name": "Aakhyan",
        "tagline": "AI vernacular patient discharge communications",
        "status": "pilot",
        "priority": "P0",
        "stack": "FastAPI, SQLModel, HTMX, Claude API, Sarvam TTS",
        "domain": "aakhyan.health",
        "revenue": False,
        "color": "#E74C3C",
    },
    {
        "id": "scribe-edc",
        "name": "Scribe EDC",
        "tagline": "Electronic data capture for clinical trials",
        "status": "coded",
        "priority": "P1",
        "stack": "Next.js, PostgreSQL (migrating from Supabase)",
        "domain": "TBD",
        "revenue": False,
        "color": "#2ECC71",
    },
    {
        "id": "apollo",
        "name": "Apollo",
        "tagline": "Automated thesis management for medical PGs",
        "status": "deployed",
        "priority": "P2",
        "stack": "Deployed on Hetzner, not commercialized",
        "domain": "sciscribesolutions.com (subpath)",
        "revenue": False,
        "color": "#F39C12",
    },
    {
        "id": "synthesise",
        "name": "Synthesi.se",
        "tagline": "Automated systematic review platform",
        "status": "development",
        "priority": "P3",
        "stack": "In development",
        "domain": "synthesi.se",
        "revenue": False,
        "color": "#9B59B6",
    },
]


@app.get("/api/products", dependencies=[Depends(verify_token)])
async def get_products():
    return {"products": PRODUCTS}


# ---------------------------------------------------------------------------
# Routes — Scheduler control
# ---------------------------------------------------------------------------

@app.post("/api/scheduler/trigger/{day}", dependencies=[Depends(verify_token)])
async def trigger_scheduled_task(day: str):
    """Manually trigger a scheduled task (monday/wednesday/friday)."""
    if day not in WEEKLY_TASKS:
        raise HTTPException(400, f"Invalid day. Choose: {list(WEEKLY_TASKS.keys())}")
    asyncio.create_task(_run_scheduled_task(day))
    return {"status": "triggered", "day": day}


@app.get("/api/scheduler/status", dependencies=[Depends(verify_token)])
async def scheduler_status():
    if not _scheduler:
        return {"running": False}
    jobs = []
    for job in _scheduler.get_jobs():
        jobs.append({
            "id": job.id,
            "next_run": str(job.next_run_time) if job.next_run_time else None,
        })
    return {"running": _scheduler.running, "jobs": jobs}

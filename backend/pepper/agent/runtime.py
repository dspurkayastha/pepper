"""Bridge between Anthropic Managed Agents sessions and the app.

- `Pump` opens a session's event stream *before* sending anything (stream-first),
  turns each Anthropic event into an app event, stores it, and fans it out to
  open SSE connections. It stops when the turn ends or Pepper is waiting on Dev.
- `sync_session` reads a session's event history instead of the stream. The
  webhook uses it for sessions nobody is watching (scheduled runs). Both paths
  go through `ingest`, which deduplicates by Anthropic event id.
- The `escalate` tool becomes a Decision row; answering it sends the tool
  result back into the same session.
"""

import asyncio
import json
import logging
from collections.abc import Iterable
from datetime import datetime, timezone

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pepper import db, push
from pepper.agent.tools import EscalateInput, NotifyInput
from pepper.anthropic_client import get_client
from pepper.broker import broker
from pepper.config import get_settings
from pepper.models import Decision, Thread, ThreadEvent

log = logging.getLogger("pepper.agent")


class AgentNotConfigured(Exception):
    pass


def _get(obj, name, default=None):
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _text_of(content) -> str:
    parts = []
    for block in content or []:
        if _get(block, "type") == "text":
            parts.append(_get(block, "text", ""))
    return "".join(parts)


def _tool_result(tool_use_id: str, text: str) -> dict:
    return {"type": "user.custom_tool_result", "custom_tool_use_id": tool_use_id, "content": [{"type": "text", "text": text}]}


def decision_view(d: Decision) -> dict:
    return {
        "id": d.id, "thread_id": d.thread_id, "lane": d.lane, "category": d.category, "question": d.question,
        "context": d.context, "options": d.options, "recommendation": d.recommendation, "blocking": d.blocking,
        "risky": d.risky, "status": d.status, "choice": d.choice, "note": d.note,
        "created_at": d.created_at.isoformat() if d.created_at else None,
        "resolved_at": d.resolved_at.isoformat() if d.resolved_at else None,
    }


def event_view(e: ThreadEvent) -> dict:
    return {"id": e.id, "thread_id": e.thread_id, "kind": e.kind, "data": e.data,
            "created_at": e.created_at.isoformat() if e.created_at else None}


async def _thread_for(session: AsyncSession, session_id: str) -> Thread | None:
    return await session.scalar(select(Thread).where(Thread.session_id == session_id))


async def _seen(session: AsyncSession, thread_id: str, source_id: str | None) -> bool:
    if not source_id:
        return False
    found = await session.scalar(
        select(func.count()).select_from(ThreadEvent)
        .where(ThreadEvent.thread_id == thread_id, ThreadEvent.source_event_id == source_id)
    )
    return bool(found)


async def _add(session: AsyncSession, thread: Thread, kind: str, data: dict, source_id: str | None) -> ThreadEvent:
    row = ThreadEvent(thread_id=thread.id, kind=kind, data=data, source_event_id=source_id)
    session.add(row)
    await session.flush()
    return row


async def _pending_decisions(session: AsyncSession, thread_id: str) -> int:
    return await session.scalar(
        select(func.count()).select_from(Decision).where(Decision.thread_id == thread_id, Decision.status == "pending")
    )


async def ingest(session_id: str, events: Iterable) -> bool:
    """Store and publish events. Returns True once the turn is over (or waiting on Dev)."""
    finished = False
    to_publish: list[ThreadEvent] = []
    tool_results: list[dict] = []
    pushes: list[tuple] = []

    async with db.sessionmaker()() as session:
        thread = await _thread_for(session, session_id)
        if thread is None:
            log.warning("events for unknown session %s ignored", session_id)
            return True
        for ev in events:
            etype = _get(ev, "type", "")
            source_id = _get(ev, "id")
            if etype.startswith("user.") or await _seen(session, thread.id, source_id):
                continue

            if etype == "agent.message":
                text = _text_of(_get(ev, "content"))
                if text:
                    to_publish.append(await _add(session, thread, "text", {"text": text}, source_id))

            elif etype in ("agent.tool_use", "agent.mcp_tool_use"):
                data = {"tool": _get(ev, "name", "?")}
                if etype == "agent.mcp_tool_use":
                    data["server"] = _get(ev, "mcp_server_name")
                to_publish.append(await _add(session, thread, "activity", data, source_id))

            elif etype == "agent.custom_tool_use":
                name, raw = _get(ev, "name"), _get(ev, "input") or {}
                if name == "escalate":
                    try:
                        esc = EscalateInput.model_validate(raw)
                    except ValidationError as exc:
                        tool_results.append(_tool_result(source_id, f"Invalid escalate input, fix and retry: {exc.errors()}"))
                        await _add(session, thread, "activity", {"tool": name, "rejected": True}, source_id)
                        continue
                    if await session.scalar(select(Decision).where(Decision.tool_use_id == source_id)) is None:
                        decision = Decision(
                            thread_id=thread.id, tool_use_id=source_id, lane=esc.lane, category=esc.category,
                            question=esc.question, context=esc.context,
                            options=[o.model_dump() for o in esc.options], recommendation=esc.recommendation,
                            blocking=esc.blocking, risky=esc.risky,
                        )
                        session.add(decision)
                        await session.flush()
                        to_publish.append(await _add(session, thread, "decision", decision_view(decision), source_id))
                        pushes.append((
                            "Pepper needs you" if esc.blocking else "A card for you", esc.question,
                            {"decision_id": decision.id, "thread_id": thread.id},
                            "DECISION_RISKY" if esc.risky else "DECISION", esc.blocking,
                        ))
                elif name == "notify":
                    try:
                        note = NotifyInput.model_validate(raw)
                    except ValidationError as exc:
                        tool_results.append(_tool_result(source_id, f"Invalid notify input: {exc.errors()}"))
                        await _add(session, thread, "activity", {"tool": name, "rejected": True}, source_id)
                        continue
                    to_publish.append(await _add(session, thread, "notice", note.model_dump(), source_id))
                    pushes.append((note.title, note.body, {"thread_id": thread.id}, "REPORT_READY", False))
                    tool_results.append(_tool_result(source_id, "Delivered to Dev's phone."))
                else:
                    tool_results.append(_tool_result(source_id, f"Unknown tool {name!r}"))
                    await _add(session, thread, "activity", {"tool": name, "rejected": True}, source_id)

            elif etype == "session.status_running":
                thread.state = "working"
                to_publish.append(await _add(session, thread, "status", {"state": "working"}, source_id))

            elif etype == "session.status_idle":
                reason = _get(_get(ev, "stop_reason"), "type", "end_turn")
                if reason == "requires_action":
                    # Waiting on a decision ends the turn; a notify call we answer ourselves does not.
                    waiting = await _pending_decisions(session, thread.id) > 0
                    state = "needs_you" if waiting else "working"
                    finished = waiting
                elif reason == "budget_reached":
                    state, finished = "needs_you", True
                elif reason == "retries_exhausted":
                    state, finished = "error", True
                else:
                    state, finished = "idle", True
                thread.state = state
                to_publish.append(await _add(session, thread, "status", {"state": state, "stop_reason": reason}, source_id))

            elif etype == "session.error":
                error = _get(ev, "error")
                message = _get(error, "message") or str(error)
                to_publish.append(await _add(session, thread, "error", {"message": message}, source_id))

            elif etype == "session.status_terminated":
                thread.state, finished = "terminated", True
                to_publish.append(await _add(session, thread, "status", {"state": "terminated"}, source_id))

        thread.updated_at = datetime.now(timezone.utc)
        await session.commit()
        views = [event_view(e) for e in to_publish]
        thread_id = thread.id

    for view in views:
        broker.publish(thread_id, view)
    if tool_results:
        await get_client().beta.sessions.events.send(session_id=session_id, events=tool_results)
    for title, body, data, category, urgent in pushes:
        await push.notify(title, body, data, category=category, time_sensitive=urgent)
    return finished


class Pump:
    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def running(self, session_id: str) -> bool:
        task = self._tasks.get(session_id)
        return task is not None and not task.done()

    async def send(self, session_id: str, events: list[dict]) -> None:
        """Make sure the stream is open, then send. The stream sees everything the send triggers."""
        lock = self._locks.setdefault(session_id, asyncio.Lock())
        async with lock:
            if not self.running(session_id):
                ready = asyncio.Event()
                self._tasks[session_id] = asyncio.create_task(self._run(session_id, ready))
                await ready.wait()
            await get_client().beta.sessions.events.send(session_id=session_id, events=events)

    async def _run(self, session_id: str, ready: asyncio.Event) -> None:
        try:
            stream = await get_client().beta.sessions.events.stream(session_id=session_id)
        except Exception:
            log.exception("could not open stream for %s; the webhook will catch up", session_id)
            ready.set()
            return
        ready.set()
        try:
            async with asyncio.timeout(get_settings().pump_timeout_s):
                async with stream:
                    async for ev in stream:
                        if await ingest(session_id, [ev]):
                            break
        except TimeoutError:
            log.warning("pump for %s timed out; the webhook will catch up", session_id)
        except Exception:
            log.exception("stream for %s failed", session_id)
        finally:
            if self._tasks.get(session_id) is asyncio.current_task():
                del self._tasks[session_id]

    async def wait(self, session_id: str) -> None:
        task = self._tasks.get(session_id)
        if task is not None:
            await task


pump = Pump()


async def create_thread(title: str | None, lane: str) -> Thread:
    ids = get_settings().agent_ids()
    if not ids.get("agent_id") or not ids.get("environment_id"):
        raise AgentNotConfigured("Run scripts/setup_agent.py first")
    kwargs: dict = {
        "agent": ids["agent_id"],
        "environment_id": ids["environment_id"],
        "metadata": {"lane": lane, "origin": "app"},
    }
    if title:
        kwargs["title"] = title
    if ids.get("vault_id"):
        kwargs["vault_ids"] = [ids["vault_id"]]
    cents = get_settings().session_budget_usd_cents
    if cents:
        kwargs["budget"] = {"type": "limit", "max_list_cost": {"amount": str(cents), "currency": "USD"}}
    created = await get_client().beta.sessions.create(**kwargs)
    async with db.sessionmaker()() as session:
        thread = Thread(session_id=created.id, title=title, lane=lane, origin="app")
        session.add(thread)
        await session.commit()
        return thread


async def send_message(thread: Thread, text: str) -> dict:
    async with db.sessionmaker()() as session:
        row = ThreadEvent(thread_id=thread.id, kind="user", data={"text": text})
        session.add(row)
        live = await session.get(Thread, thread.id)
        live.state = "working"
        await session.commit()
        view = event_view(row)
    broker.publish(thread.id, view)
    await pump.send(thread.session_id, [{"type": "user.message", "content": [{"type": "text", "text": text}]}])
    return view


async def resolve_decision(decision: Decision, thread: Thread, choice: str, note: str | None) -> dict:
    option = next((o for o in decision.options if o["id"] == choice), None)
    if option is None:
        raise ValueError(f"Unknown option {choice!r}")
    async with db.sessionmaker()() as session:
        live = await session.get(Decision, decision.id)
        if live.status != "pending":
            raise RuntimeError("Decision already resolved")
        live.status, live.choice, live.note = "resolved", choice, note
        live.resolved_at = datetime.now(timezone.utc)
        row = ThreadEvent(thread_id=thread.id, kind="decision_resolved", data={"decision_id": live.id, "choice": choice})
        session.add(row)
        await session.commit()
        view = decision_view(live)
        broker.publish(thread.id, event_view(row))
    answer = {"choice": choice, "label": option["label"], "note": note or ""}
    await pump.send(thread.session_id, [_tool_result(decision.tool_use_id, "Dev decided: " + json.dumps(answer))])
    return view


async def sync_session(session_id: str) -> None:
    """Catch up on a session from its event history (used by the webhook)."""
    client = get_client()
    async with db.sessionmaker()() as session:
        thread = await _thread_for(session, session_id)
        if thread is None:
            info = await client.beta.sessions.retrieve(session_id)
            metadata = _get(info, "metadata") or {}
            thread = Thread(
                session_id=session_id, title=_get(info, "title"),
                lane=metadata.get("lane", "company"), origin=metadata.get("origin", "scheduled"),
            )
            session.add(thread)
            await session.commit()
    if pump.running(session_id):
        return  # the live stream is already ingesting this session
    history = [ev async for ev in client.beta.sessions.events.list(session_id=session_id, order="asc")]
    await ingest(session_id, history)

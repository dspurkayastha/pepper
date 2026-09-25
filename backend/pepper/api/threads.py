import asyncio
import json

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pepper import db as dbmod
from pepper.agent import runtime
from pepper.anthropic_client import get_client
from pepper.broker import broker
from pepper.db import get_db
from pepper.models import Thread, ThreadEvent
from pepper.security import current_device

router = APIRouter(prefix="/v1/threads", tags=["threads"], dependencies=[Depends(current_device)])

KEEPALIVE_S = 15.0


class ThreadCreate(BaseModel):
    title: str | None = Field(None, max_length=200)
    lane: str = Field("company", pattern="^(clinical|company|life)$")
    text: str | None = Field(None, max_length=50000, description="Optional first message")


class MessageInput(BaseModel):
    text: str = Field(..., min_length=1, max_length=50000)


def _view(t: Thread) -> dict:
    return {"id": t.id, "title": t.title, "lane": t.lane, "origin": t.origin, "state": t.state,
            "created_at": t.created_at.isoformat(), "updated_at": t.updated_at.isoformat()}


async def _thread(db: AsyncSession, thread_id: str) -> Thread:
    thread = await db.get(Thread, thread_id)
    if thread is None:
        raise HTTPException(404, "Thread not found")
    return thread


@router.post("", status_code=201)
async def create_thread(body: ThreadCreate):
    try:
        thread = await runtime.create_thread(body.title, body.lane)
    except runtime.AgentNotConfigured as exc:
        raise HTTPException(503, str(exc)) from exc
    if body.text:
        await runtime.send_message(thread, body.text)
    return _view(thread)


@router.get("")
async def list_threads(lane: str | None = None, limit: int = Query(50, le=200), db: AsyncSession = Depends(get_db)):
    query = select(Thread).where(Thread.state != "archived").order_by(Thread.updated_at.desc()).limit(limit)
    if lane:
        query = query.where(Thread.lane == lane)
    return {"threads": [_view(t) for t in (await db.scalars(query)).all()]}


@router.get("/{thread_id}")
async def get_thread(thread_id: str, db: AsyncSession = Depends(get_db)):
    return _view(await _thread(db, thread_id))


@router.post("/{thread_id}/messages", status_code=202)
async def send_message(thread_id: str, body: MessageInput, db: AsyncSession = Depends(get_db)):
    thread = await _thread(db, thread_id)
    if thread.state in ("archived", "terminated"):
        raise HTTPException(409, f"Thread is {thread.state}")
    return await runtime.send_message(thread, body.text)


def _sse(event: dict) -> str:
    return f"id: {event['id']}\nevent: {event['kind']}\ndata: {json.dumps(event)}\n\n"


@router.get("/{thread_id}/events")
async def stream_events(
    thread_id: str,
    after: int | None = Query(None, description="Replay events with id greater than this"),
    follow: bool = Query(True, description="Keep the connection open for live events"),
    last_event_id: str | None = Header(None),
    db: AsyncSession = Depends(get_db),
):
    await _thread(db, thread_id)
    start = after if after is not None else int(last_event_id) if last_event_id and last_event_id.isdigit() else 0

    async def events():
        # Subscribe before the replay query so nothing published in between is lost.
        queue = broker.subscribe(thread_id) if follow else None
        last = start
        try:
            async with dbmod.sessionmaker()() as session:
                rows = (await session.scalars(
                    select(ThreadEvent).where(ThreadEvent.thread_id == thread_id, ThreadEvent.id > start)
                    .order_by(ThreadEvent.id)
                )).all()
            for row in rows:
                last = row.id
                yield _sse(runtime.event_view(row))
            if queue is None:
                return
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=KEEPALIVE_S)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                if event["id"] <= last:
                    continue
                last = event["id"]
                yield _sse(event)
        finally:
            if queue is not None:
                broker.unsubscribe(thread_id, queue)

    return StreamingResponse(
        events(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/{thread_id}/archive")
async def archive(thread_id: str, db: AsyncSession = Depends(get_db)):
    thread = await _thread(db, thread_id)
    await get_client().beta.sessions.archive(session_id=thread.session_id)
    thread.state = "archived"
    await db.commit()
    return _view(thread)

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pepper.agent import runtime
from pepper.db import get_db
from pepper.models import Decision, Thread
from pepper.security import current_device

router = APIRouter(prefix="/v1/decisions", tags=["decisions"], dependencies=[Depends(current_device)])


class DecisionAnswer(BaseModel):
    choice: str = Field(..., min_length=1, max_length=40)
    note: str | None = Field(None, max_length=2000)


@router.get("")
async def list_decisions(status: str = Query("pending", pattern="^(pending|resolved)$"), db: AsyncSession = Depends(get_db)):
    rows = (await db.scalars(
        select(Decision).where(Decision.status == status)
        .order_by(Decision.blocking.desc(), Decision.created_at.desc())
    )).all()
    return {"decisions": [runtime.decision_view(d) for d in rows]}


@router.get("/{decision_id}")
async def get_decision(decision_id: str, db: AsyncSession = Depends(get_db)):
    decision = await db.get(Decision, decision_id)
    if decision is None:
        raise HTTPException(404, "Decision not found")
    return runtime.decision_view(decision)


@router.post("/{decision_id}")
async def answer(decision_id: str, body: DecisionAnswer, db: AsyncSession = Depends(get_db)):
    decision = await db.get(Decision, decision_id)
    if decision is None:
        raise HTTPException(404, "Decision not found")
    if decision.status != "pending":
        raise HTTPException(409, "Decision already resolved")
    thread = await db.get(Thread, decision.thread_id)
    try:
        return await runtime.resolve_decision(decision, thread, body.choice, body.note)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc

"""Anthropic -> Pepper notifications (register the URL in Console -> Manage -> Webhooks).

Payloads are thin (type + id), so we verify, dedupe, then catch up on the
session from its event history. This is how scheduled runs, which no app is
watching, get their decisions and notices into the app.
"""

import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response
from sqlalchemy.exc import IntegrityError

from pepper import db
from pepper.agent import runtime
from pepper.anthropic_client import get_client
from pepper.models import WebhookReceipt

log = logging.getLogger("pepper.webhooks")
router = APIRouter(tags=["webhooks"])

SESSION_EVENTS = {
    "session.requires_action", "session.status_idled", "session.idled", "session.status_terminated",
    "session.budget_reached",
}


@router.post("/hooks/anthropic", status_code=204)
async def anthropic_hook(request: Request, background: BackgroundTasks):
    payload = (await request.body()).decode()
    try:
        # Verifies the HMAC signature and age using ANTHROPIC_WEBHOOK_SIGNING_KEY.
        event = get_client().beta.webhooks.unwrap(payload, headers=dict(request.headers))
    except Exception as exc:
        log.warning("rejected webhook: %s", exc)
        raise HTTPException(400, "Invalid signature") from exc

    async with db.sessionmaker()() as session:
        session.add(WebhookReceipt(event_id=event.id))
        try:
            await session.commit()
        except IntegrityError:
            return Response(status_code=204)  # retry of a delivery we already handled

    if event.data.type in SESSION_EVENTS:
        background.add_task(runtime.sync_session, event.data.id)
    return Response(status_code=204)

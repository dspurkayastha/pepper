"""Per-device bearer tokens.

A device enrols once with the bootstrap secret (PEPPER_APP_TOKEN) and gets its
own token, stored here only as a SHA-256 hash. Revoking a device cuts it off
without touching the others.
"""

import hashlib
import secrets
from datetime import datetime, timezone

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pepper.config import get_settings
from pepper.db import get_db
from pepper.models import Device


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_token() -> str:
    return secrets.token_urlsafe(32)


def _bearer(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing bearer token")
    return authorization[7:]


def require_bootstrap(authorization: str | None = Header(None)) -> None:
    expected = get_settings().app_token
    if not expected:
        raise HTTPException(503, "Enrolment is disabled: PEPPER_APP_TOKEN is not set")
    if not secrets.compare_digest(_bearer(authorization), expected):
        raise HTTPException(401, "Invalid enrolment token")


async def current_device(authorization: str | None = Header(None), db: AsyncSession = Depends(get_db)) -> Device:
    device = await db.scalar(select(Device).where(Device.token_hash == hash_token(_bearer(authorization))))
    if device is None or device.revoked:
        raise HTTPException(401, "Unknown or revoked device")
    device.last_seen_at = datetime.now(timezone.utc)
    await db.commit()
    return device

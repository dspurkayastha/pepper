"""Secrets for the agent, stored in the Anthropic vault.

The server keeps only metadata. The agent's sandbox sees an opaque placeholder
and the real value is substituted at egress, only for the listed hosts and only
in request headers/body. Services that put secrets in the URL (e.g. Namecheap's
query-string ApiKey) or that are not HTTP at all (SSH) cannot be vaulted this
way; they need a dedicated custom tool run by the backend instead.
"""

import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pepper.anthropic_client import get_client
from pepper.config import get_settings
from pepper.db import get_db
from pepper.models import Credential
from pepper.security import current_device

router = APIRouter(prefix="/v1/integrations", tags=["integrations"], dependencies=[Depends(current_device)])

KNOWN = {
    "GITHUB_TOKEN": {"label": "GitHub", "hosts": ["api.github.com", "github.com", "uploads.github.com"]},
    "VERCEL_TOKEN": {"label": "Vercel", "hosts": ["api.vercel.com"]},
    "UPTIMEROBOT_API_KEY": {"label": "UptimeRobot", "hosts": ["api.uptimerobot.com"]},
    "SARVAM_API_KEY": {"label": "Sarvam AI", "hosts": ["api.sarvam.ai"]},
    "CLERK_SECRET_KEY": {"label": "Clerk", "hosts": ["api.clerk.com"]},
    "PLAUSIBLE_API_KEY": {"label": "Plausible", "hosts": ["plausible.io"]},
}
UNSUPPORTED = {
    "SSH keys (Oracle, Hetzner)": "SSH is not HTTP, so vault substitution can't apply. Server access will go through a backend-run tool.",
    "Namecheap": "Namecheap puts the API key in the URL, which vaults never substitute. Needs a backend-run tool.",
}
HOST = re.compile(r"^(\*\.)?[a-z0-9-]+(\.[a-z0-9-]+)+$")


class CredentialInput(BaseModel):
    secret_name: str = Field(..., pattern=r"^[A-Z][A-Z0-9_]{1,79}$")
    value: str = Field(..., min_length=1, max_length=10000)
    allowed_hosts: list[str] | None = Field(None, max_length=20)


def _view(c: Credential) -> dict:
    return {"id": c.id, "secret_name": c.secret_name, "allowed_hosts": c.allowed_hosts,
            "created_at": c.created_at.isoformat()}


def _vault_id() -> str:
    vault_id = get_settings().agent_ids().get("vault_id")
    if not vault_id:
        raise HTTPException(503, "No vault configured: run scripts/setup_agent.py")
    return vault_id


@router.get("/schema")
async def schema(db: AsyncSession = Depends(get_db)):
    have = set((await db.scalars(select(Credential.secret_name))).all())
    return {
        "known": [{"secret_name": k, **v, "configured": k in have} for k, v in KNOWN.items()],
        "unsupported": [{"name": k, "reason": v} for k, v in UNSUPPORTED.items()],
    }


@router.get("/credentials")
async def list_credentials(db: AsyncSession = Depends(get_db)):
    rows = (await db.scalars(select(Credential).order_by(Credential.secret_name))).all()
    return {"credentials": [_view(c) for c in rows]}


@router.post("/credentials", status_code=201)
async def add_credential(body: CredentialInput, db: AsyncSession = Depends(get_db)):
    hosts = body.allowed_hosts or KNOWN.get(body.secret_name, {}).get("hosts")
    if not hosts:
        raise HTTPException(422, "allowed_hosts is required for secrets Pepper doesn't know")
    hosts = [h.lower() for h in hosts]
    bad = [h for h in hosts if not HOST.match(h)]
    if bad:
        raise HTTPException(422, f"Not valid host names: {bad}")
    if await db.scalar(select(Credential).where(Credential.secret_name == body.secret_name)):
        raise HTTPException(409, "Already stored; delete it first to replace it")

    created = await get_client().beta.vaults.credentials.create(
        _vault_id(),
        display_name=KNOWN.get(body.secret_name, {}).get("label", body.secret_name),
        auth={
            "type": "environment_variable",
            "secret_name": body.secret_name,
            "secret_value": body.value,
            "networking": {"type": "limited", "allowed_hosts": hosts},
        },
    )
    row = Credential(secret_name=body.secret_name, vault_credential_id=created.id, allowed_hosts=hosts)
    db.add(row)
    await db.commit()
    return _view(row)


@router.delete("/credentials/{secret_name}")
async def delete_credential(secret_name: str, db: AsyncSession = Depends(get_db)):
    row = await db.scalar(select(Credential).where(Credential.secret_name == secret_name))
    if row is None:
        raise HTTPException(404, "Not stored")
    # Archiving purges the secret in the vault and frees the name for a replacement.
    await get_client().beta.vaults.credentials.archive(row.vault_credential_id, vault_id=_vault_id())
    await db.delete(row)
    await db.commit()
    return {"deleted": secret_name}

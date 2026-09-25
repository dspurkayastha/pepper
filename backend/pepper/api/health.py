from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pepper.config import get_settings
from pepper.db import get_db
from pepper.models import Decision, Device
from pepper.security import current_device

router = APIRouter(tags=["health"])

PRODUCTS = [
    {"id": "sciscribe", "name": "SciScribe", "tagline": "Manuscript editing & academic services",
     "status": "active", "priority": None, "domain": "sciscribesolutions.com", "color": "#4A90D9"},
    {"id": "aakhyan", "name": "Aakhyan", "tagline": "AI vernacular patient discharge communications",
     "status": "pilot", "priority": "P0", "domain": "aakhyan.health", "color": "#E74C3C"},
    {"id": "scribe-edc", "name": "Scribe EDC", "tagline": "Electronic data capture for clinical trials",
     "status": "coded", "priority": "P1", "domain": None, "color": "#2ECC71"},
    {"id": "apollo", "name": "Apollo", "tagline": "Automated thesis management for medical PGs",
     "status": "deployed", "priority": "P2", "domain": "sciscribesolutions.com", "color": "#F39C12"},
    {"id": "synthesise", "name": "Synthesi.se", "tagline": "Automated systematic review platform",
     "status": "development", "priority": "P3", "domain": "synthesi.se", "color": "#9B59B6"},
]


@router.get("/health")
async def health(db: AsyncSession = Depends(get_db)):
    ids = get_settings().agent_ids()
    return {
        "status": "ok",
        "agent_configured": bool(ids.get("agent_id") and ids.get("environment_id")),
        "vault_configured": bool(ids.get("vault_id")),
        "devices": await db.scalar(select(func.count()).select_from(Device).where(Device.revoked.is_(False))),
        "pending_decisions": await db.scalar(
            select(func.count()).select_from(Decision).where(Decision.status == "pending")
        ),
    }


@router.get("/v1/products", dependencies=[Depends(current_device)])
async def products():
    return {"products": PRODUCTS}

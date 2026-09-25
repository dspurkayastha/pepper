from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pepper.db import get_db
from pepper.models import Device
from pepper.security import current_device, hash_token, new_token, require_bootstrap

router = APIRouter(prefix="/v1/devices", tags=["devices"])


class EnrolInput(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    platform: str = Field("ios", max_length=20)
    apns_token: str | None = Field(None, max_length=200)


class DeviceUpdate(BaseModel):
    apns_token: str | None = Field(None, max_length=200)


def _view(d: Device) -> dict:
    return {"id": d.id, "name": d.name, "platform": d.platform, "push_enabled": bool(d.apns_token),
            "revoked": d.revoked, "created_at": d.created_at.isoformat(),
            "last_seen_at": d.last_seen_at.isoformat() if d.last_seen_at else None}


@router.post("/enroll", dependencies=[Depends(require_bootstrap)], status_code=201)
async def enroll(body: EnrolInput, db: AsyncSession = Depends(get_db)):
    token = new_token()
    device = Device(name=body.name, platform=body.platform, apns_token=body.apns_token, token_hash=hash_token(token))
    db.add(device)
    await db.commit()
    # The token is shown exactly once; only its hash is stored.
    return {"device": _view(device), "token": token}


@router.get("")
async def list_devices(_: Device = Depends(current_device), db: AsyncSession = Depends(get_db)):
    devices = (await db.scalars(select(Device).order_by(Device.created_at))).all()
    return {"devices": [_view(d) for d in devices]}


@router.patch("/me")
async def update_me(body: DeviceUpdate, device: Device = Depends(current_device), db: AsyncSession = Depends(get_db)):
    live = await db.get(Device, device.id)
    live.apns_token = body.apns_token
    await db.commit()
    return _view(live)


@router.delete("/{device_id}")
async def revoke(device_id: str, _: Device = Depends(current_device), db: AsyncSession = Depends(get_db)):
    target = await db.get(Device, device_id)
    if target is None:
        raise HTTPException(404, "Device not found")
    target.revoked = True
    target.apns_token = None
    await db.commit()
    return _view(target)

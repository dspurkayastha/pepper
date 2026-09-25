from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, ValidationError, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from pepper.anthropic_client import get_client
from pepper.config import get_settings
from pepper.db import get_db
from pepper.intake import ot_list
from pepper.models import OtList
from pepper.security import current_device

router = APIRouter(prefix="/v1/ot-lists", tags=["ot-lists"], dependencies=[Depends(current_device)])

MAX_IMAGE_B64 = 10 * 1024 * 1024  # ~7.5 MB image


class ParseInput(BaseModel):
    source: str = Field(..., pattern="^(whatsapp_text|paper_photo|screenshot)$")
    text: str | None = Field(None, max_length=20000)
    image_b64: str | None = Field(None, max_length=MAX_IMAGE_B64, description="De-identified on the phone first")
    media_type: str | None = None
    list_date: date | None = None

    @model_validator(mode="after")
    def _one_input(self):
        if not self.text and not self.image_b64:
            raise ValueError("Provide text or image_b64")
        return self


class CheckUpdate(BaseModel):
    label: str = Field(..., min_length=1, max_length=120)
    done: bool


class ConfirmInput(BaseModel):
    list_date: date | None = None


def _view(o: OtList) -> dict:
    return {"id": o.id, "list_date": o.list_date.isoformat() if o.list_date else None, "source": o.source,
            "status": o.status, "items": o.items, "warnings": o.warnings, "created_at": o.created_at.isoformat()}


async def _list(db: AsyncSession, list_id: str) -> OtList:
    row = await db.get(OtList, list_id)
    if row is None:
        raise HTTPException(404, "OT list not found")
    return row


@router.post("/parse", status_code=201)
async def parse(body: ParseInput, db: AsyncSession = Depends(get_db)):
    try:
        parsed = await ot_list.parse(
            get_client(), get_settings().model, text=body.text, image_b64=body.image_b64, media_type=body.media_type,
        )
    except ot_list.IntakeError as exc:
        raise HTTPException(422, str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(502, "The list reader returned something unexpected; try again") from exc
    items, warnings = ot_list.build_items(parsed)
    list_date = body.list_date
    if list_date is None and parsed.list_date:
        try:
            list_date = date.fromisoformat(parsed.list_date)
        except ValueError:
            warnings.append(f"Couldn't read the list date {parsed.list_date!r}")
    row = OtList(source=body.source, list_date=list_date, items=items, warnings=warnings)
    db.add(row)
    await db.commit()
    return _view(row)


@router.get("")
async def list_ot_lists(list_date: date | None = None, db: AsyncSession = Depends(get_db)):
    query = select(OtList).order_by(OtList.created_at.desc()).limit(50)
    if list_date:
        query = query.where(OtList.list_date == list_date)
    return {"ot_lists": [_view(o) for o in (await db.scalars(query)).all()]}


@router.get("/{list_id}")
async def get_ot_list(list_id: str, db: AsyncSession = Depends(get_db)):
    return _view(await _list(db, list_id))


@router.post("/{list_id}/items/{item_id}/checks")
async def set_check(list_id: str, item_id: str, body: CheckUpdate, db: AsyncSession = Depends(get_db)):
    row = await _list(db, list_id)
    item = next((i for i in row.items if i["id"] == item_id), None)
    if item is None:
        raise HTTPException(404, "Item not found")
    check = next((c for c in item["checks"] if c["label"] == body.label), None)
    if check is None:
        item["checks"].append({"label": body.label, "done": body.done})
    else:
        check["done"] = body.done
    flag_modified(row, "items")
    await db.commit()
    return _view(row)


@router.post("/{list_id}/confirm")
async def confirm(list_id: str, body: ConfirmInput, db: AsyncSession = Depends(get_db)):
    row = await _list(db, list_id)
    if body.list_date:
        row.list_date = body.list_date
    if row.list_date is None:
        raise HTTPException(422, "Which day is this list for?")
    row.status = "confirmed"
    await db.commit()
    return _view(row)

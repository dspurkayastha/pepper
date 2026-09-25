import json
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import extract, select
from sqlalchemy.ext.asyncio import AsyncSession

from pepper import privacy
from pepper.clinical import outcomes
from pepper.clinical.templates import TEMPLATES, ComplicationCheck, TemplateKey, describe, initial_histopath_status
from pepper.db import get_db
from pepper.models import Case
from pepper.security import current_device

router = APIRouter(prefix="/v1/clinical", tags=["clinical"], dependencies=[Depends(current_device)])

HPB_ONLY = ("popf", "dge", "pph", "phlf")


class CaseCreate(BaseModel):
    local_ref: uuid.UUID = Field(..., description="Opaque id from the phone's identity store")
    template: TemplateKey
    performed_on: date
    data: dict
    ot_list_item_id: str | None = Field(None, max_length=36)


class CaseUpdate(BaseModel):
    data: dict | None = Field(None, description="Fields to change; merged into the record, then re-validated")
    status: str | None = Field(None, pattern="^(draft|confirmed)$")
    performed_on: date | None = None


class HistopathInput(BaseModel):
    data: dict


class ComplicationInput(BaseModel):
    day: int = Field(..., description="30 or 90")
    check: ComplicationCheck


def _errors(exc: ValidationError) -> list:
    return json.loads(exc.json(include_url=False))


def _validated(model, data: dict) -> dict:
    try:
        parsed = model.model_validate(data)
    except ValidationError as exc:
        raise HTTPException(422, {"message": "Invalid fields", "errors": _errors(exc)}) from exc
    problems = privacy.scan(data)
    if problems:
        raise HTTPException(422, {"message": "Looks like patient identifiers; keep those on the phone", "fields": problems})
    return parsed.model_dump(mode="json", exclude_none=True)


def _view(c: Case) -> dict:
    return {
        "id": c.id, "local_ref": c.local_ref, "template": c.template, "performed_on": c.performed_on.isoformat(),
        "status": c.status, "histopath_status": c.histopath_status, "data": c.data, "histopath": c.histopath,
        "complications": c.complications, "ot_list_item_id": c.ot_list_item_id,
        "created_at": c.created_at.isoformat(), "updated_at": c.updated_at.isoformat(),
    }


async def _case(db: AsyncSession, case_id: str) -> Case:
    case = await db.get(Case, case_id)
    if case is None:
        raise HTTPException(404, "Case not found")
    return case


@router.get("/templates")
async def templates():
    return describe()


@router.post("/cases", status_code=201)
async def create_case(body: CaseCreate, db: AsyncSession = Depends(get_db)):
    template = TEMPLATES[body.template]
    data = _validated(template.record, body.data)
    case = Case(
        local_ref=str(body.local_ref), template=body.template, performed_on=body.performed_on, data=data,
        histopath_status=initial_histopath_status(template, template.record.model_validate(data)),
        ot_list_item_id=body.ot_list_item_id, complications={},
    )
    db.add(case)
    await db.commit()
    return _view(case)


@router.get("/cases")
async def list_cases(
    template: TemplateKey | None = None,
    histopath_status: str | None = Query(None, pattern="^(not_applicable|pending|reported)$"),
    year: int | None = None,
    local_ref: uuid.UUID | None = None,
    limit: int = Query(100, le=500),
    db: AsyncSession = Depends(get_db),
):
    query = select(Case).order_by(Case.performed_on.desc()).limit(limit)
    if template:
        query = query.where(Case.template == template)
    if histopath_status:
        query = query.where(Case.histopath_status == histopath_status)
    if year:
        query = query.where(extract("year", Case.performed_on) == year)
    if local_ref:
        query = query.where(Case.local_ref == str(local_ref))
    return {"cases": [_view(c) for c in (await db.scalars(query)).all()]}


@router.get("/cases/{case_id}")
async def get_case(case_id: str, db: AsyncSession = Depends(get_db)):
    return _view(await _case(db, case_id))


@router.patch("/cases/{case_id}")
async def update_case(case_id: str, body: CaseUpdate, db: AsyncSession = Depends(get_db)):
    case = await _case(db, case_id)
    if body.data is not None:
        template = TEMPLATES[case.template]
        case.data = _validated(template.record, {**case.data, **body.data})
        if case.histopath_status != "reported":
            case.histopath_status = initial_histopath_status(template, template.record.model_validate(case.data))
    if body.status:
        case.status = body.status
    if body.performed_on:
        case.performed_on = body.performed_on
    await db.commit()
    return _view(case)


@router.post("/cases/{case_id}/histopath")
async def add_histopath(case_id: str, body: HistopathInput, db: AsyncSession = Depends(get_db)):
    case = await _case(db, case_id)
    template = TEMPLATES[case.template]
    if template.histopath is None:
        raise HTTPException(400, f"{template.label} cases have no histopathology record")
    report = _validated(template.histopath, body.data)
    if report.get("nodes_positive") is not None and report.get("nodes_examined") is not None \
            and report["nodes_positive"] > report["nodes_examined"]:
        raise HTTPException(422, "More positive nodes than nodes examined")
    case.histopath = report
    case.histopath_status = "reported"
    await db.commit()
    return _view(case)


@router.post("/cases/{case_id}/complications")
async def add_complication_check(case_id: str, body: ComplicationInput, db: AsyncSession = Depends(get_db)):
    case = await _case(db, case_id)
    if body.day not in outcomes.CHECK_DAYS:
        raise HTTPException(422, f"day must be one of {list(outcomes.CHECK_DAYS)}")
    if not TEMPLATES[case.template].complication_checks:
        raise HTTPException(400, "This template has no complication checks")
    check = body.check.model_dump(mode="json", exclude_none=True)
    if case.template != "hpb" and any(k in check for k in HPB_ONLY):
        raise HTTPException(422, "POPF/DGE/PPH/PHLF grades apply to HPB cases only")
    problems = privacy.scan(check)
    if problems:
        raise HTTPException(422, {"message": "Looks like patient identifiers", "fields": problems})
    case.complications = {**(case.complications or {}), str(body.day): check}
    await db.commit()
    return _view(case)


@router.get("/due")
async def due(today: date | None = None, db: AsyncSession = Depends(get_db)):
    cases = (await db.scalars(select(Case))).all()
    return outcomes.due_items(list(cases), today or date.today())


@router.get("/summary")
async def summary(year: int | None = None, db: AsyncSession = Depends(get_db)):
    query = select(Case)
    if year:
        query = query.where(extract("year", Case.performed_on) == year)
    return outcomes.summary(list((await db.scalars(query)).all()))

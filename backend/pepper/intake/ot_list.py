"""Read an OT list from a shared WhatsApp message or a photo of the paper list.

Claude extracts structured cases (no names or hospital numbers); the server then
re-checks every field for identifiers and adds the deterministic prep checklist.
"""

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from pepper import privacy
from pepper.clinical.prep import checklist

TEMPLATE_KEYS = ["breast", "upper_gi", "colorectal", "hpb", "gynae_onc", "skin_surface", "sarcoma", "general", "endoscopy"]
IMAGE_TYPES = ("image/jpeg", "image/png", "image/webp", "image/gif")
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class IntakeError(Exception):
    pass


class ParsedItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    time: str | None = Field(None, description="HH:MM, 24-hour")
    procedure: str
    diagnosis: str | None = None
    age: int | None = None
    sex: Literal["M", "F", "other"] | None = None
    side: Literal["left", "right", "bilateral"] | None = None
    template: Literal[
        "breast", "upper_gi", "colorectal", "hpb", "gynae_onc", "skin_surface", "sarcoma", "general", "endoscopy"
    ]
    post_nact: bool = False
    notes: str | None = None


class ParsedList(BaseModel):
    model_config = ConfigDict(extra="forbid")
    list_date: str | None = Field(None, description="YYYY-MM-DD if the list states a date")
    items: list[ParsedItem]
    warnings: list[str] = []


def _nullable(schema: dict) -> dict:
    return {"anyOf": [schema, {"type": "null"}]}


OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "list_date": _nullable({"type": "string"}),
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "time": _nullable({"type": "string"}),
                    "procedure": {"type": "string"},
                    "diagnosis": _nullable({"type": "string"}),
                    "age": _nullable({"type": "integer"}),
                    "sex": _nullable({"type": "string", "enum": ["M", "F", "other"]}),
                    "side": _nullable({"type": "string", "enum": ["left", "right", "bilateral"]}),
                    "template": {"type": "string", "enum": TEMPLATE_KEYS},
                    "post_nact": {"type": "boolean"},
                    "notes": _nullable({"type": "string"}),
                },
                "required": ["time", "procedure", "diagnosis", "age", "sex", "side", "template", "post_nact", "notes"],
                "additionalProperties": False,
            },
        },
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["list_date", "items", "warnings"],
    "additionalProperties": False,
}

PROMPT = """You are reading an operating-theatre list for a consultant surgical oncologist in India who also does general surgery, minor procedures and endoscopy. The list came from a WhatsApp message or a photo of a handwritten/printed sheet.

Extract one item per scheduled case, in list order.

Privacy rules (strict):
- Never output patient names, initials, hospital/UHID/IP/CR/registration numbers, bed numbers, phone numbers or addresses. Leave them out entirely.
- Age and sex are allowed.

Field rules:
- time: 24-hour HH:MM if a time is given, else null. Serial order without times means null.
- procedure: the operation as written, expanding common abbreviations (MRM = modified radical mastectomy, WLE = wide local excision, SLNB = sentinel lymph node biopsy, BCS = breast-conserving surgery, APR = abdominoperineal resection, LAR = low anterior resection, UGIE/OGD = upper GI endoscopy).
- diagnosis: as written (e.g. "Ca breast", "Ca rectum"), else null.
- template: breast, upper_gi (oesophagus/GEJ/stomach), colorectal, hpb (pancreas/liver/biliary/gallbladder/periampullary), gynae_onc, skin_surface (melanoma, skin cancers, surface lesions), sarcoma, general (non-cancer and minor procedures), endoscopy (all scopies).
- post_nact: true only if the list says the patient had neoadjuvant chemotherapy (post-NACT, post-chemo).
- side: only if stated.
- notes: short operational notes on the list (e.g. "frozen", "HIPEC", "2 units"), else null.
- warnings: anything you could not read or were unsure about, one short sentence each.

If something is illegible, leave the field null and add a warning. Do not guess."""


async def parse(client, model: str, *, text: str | None = None, image_b64: str | None = None,
                media_type: str | None = None) -> ParsedList:
    if not text and not image_b64:
        raise IntakeError("Send the WhatsApp text or a photo of the list")
    content: list[dict] = []
    if image_b64:
        if media_type not in IMAGE_TYPES:
            raise IntakeError(f"Unsupported image type {media_type!r}")
        content.append({"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_b64}})
    prompt = PROMPT
    if text:
        prompt += f"\n\n<ot_list>\n{text}\n</ot_list>"
    content.append({"type": "text", "text": prompt})

    response = await client.beta.messages.create(
        model=model,
        max_tokens=8000,
        betas=[FALLBACK_BETA],
        fallbacks="default",
        output_config={"format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}},
        messages=[{"role": "user", "content": content}],
    )
    if response.stop_reason == "refusal":
        raise IntakeError("The list could not be read (the request was declined)")
    if response.stop_reason == "max_tokens":
        raise IntakeError("The list was too long to read in one go; split it and try again")
    body = next((b.text for b in response.content if b.type == "text"), None)
    if body is None:
        raise IntakeError("No list came back from the reader")
    return ParsedList.model_validate_json(body)


def build_items(parsed: ParsedList) -> tuple[list[dict], list[str]]:
    """Strip anything identifying, attach prep checklists, and give each item an id."""
    items: list[dict] = []
    warnings = list(parsed.warnings)
    for index, item in enumerate(parsed.items, start=1):
        row = item.model_dump()
        for key in ("procedure", "diagnosis", "notes"):
            value = row.get(key)
            if isinstance(value, str) and privacy.find_identifier(value):
                warnings.append(f"Case {index}: removed a possible identifier from {key}")
                row[key] = None if key != "procedure" else "[check procedure]"
        row["id"] = str(uuid.uuid4())
        row["checks"] = [
            {"label": label, "done": False}
            for label in checklist(row["procedure"], row["template"], row["post_nact"])
        ]
        items.append(row)
    for w in list(warnings):
        if privacy.find_identifier(w):
            warnings.remove(w)
    return items, warnings

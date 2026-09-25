"""Custom tools Pepper calls; the backend executes them.

`escalate` replaces the old free-text [ESCALATE] blocks: the session pauses
(stop_reason requires_action) until the decision is answered in the app, so
scheduled runs can be answered too.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

LANES = ["clinical", "company", "life"]
CATEGORIES = ["infra", "content", "email", "money", "code", "clinical_admin", "family", "travel", "other"]


class EscalateOption(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(..., min_length=1, max_length=40)
    label: str = Field(..., min_length=1, max_length=120)
    detail: str | None = Field(None, max_length=300)


class EscalateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lane: Literal["clinical", "company", "life"]
    category: Literal["infra", "content", "email", "money", "code", "clinical_admin", "family", "travel", "other"]
    question: str = Field(..., min_length=3, max_length=300)
    context: str = Field("", max_length=2000)
    options: list[EscalateOption] = Field(..., min_length=1, max_length=5)
    recommendation: str | None = None
    blocking: bool = False
    risky: bool = Field(False, description="Irreversible, public, or spends money: the app asks for Face ID")


class NotifyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lane: Literal["clinical", "company", "life"]
    title: str = Field(..., min_length=1, max_length=80)
    body: str = Field(..., min_length=1, max_length=240)


ESCALATE_TOOL = {
    "type": "custom",
    "name": "escalate",
    "description": (
        "Ask Dev to decide something. Use only when the choice is genuinely theirs: it is irreversible, public, "
        "spends money, touches patients' care, or you are unsure. Give 1-5 concrete options and recommend one. "
        "The session pauses until Dev answers; the answer comes back as this tool's result. "
        "Never include patient names or hospital numbers."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "lane": {"type": "string", "enum": LANES},
            "category": {"type": "string", "enum": CATEGORIES},
            "question": {"type": "string", "description": "One sentence, answerable at a glance"},
            "context": {"type": "string", "description": "What Dev needs to know to decide; short"},
            "options": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "label": {"type": "string"},
                        "detail": {"type": "string"},
                    },
                    "required": ["id", "label"],
                },
            },
            "recommendation": {"type": "string", "description": "id of the recommended option"},
            "blocking": {"type": "boolean", "description": "true if work cannot continue without the answer"},
            "risky": {"type": "boolean", "description": "true if irreversible, public, or spends money"},
        },
        "required": ["lane", "category", "question", "options"],
    },
}

NOTIFY_TOOL = {
    "type": "custom",
    "name": "notify",
    "description": (
        "Tell Dev something that needs no decision (a report is ready, a fix was applied). "
        "Keep it to one line. Use sparingly: most updates belong in the final message."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "lane": {"type": "string", "enum": LANES},
            "title": {"type": "string"},
            "body": {"type": "string"},
        },
        "required": ["lane", "title", "body"],
    },
}

CUSTOM_TOOLS = [ESCALATE_TOOL, NOTIFY_TOOL]

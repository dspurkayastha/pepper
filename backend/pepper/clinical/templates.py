"""Case-record templates.

One schema per template for the operative record (`data`) and one for the
pathology report (`histopath`). Every model forbids unknown fields, so an
identifier cannot slip in under a new key; free text is scanned separately
(see pepper.privacy).

Standards: AJCC TNM (current edition per site), FIGO for gynaecological
cancers, Clavien-Dindo for complications, ISGPS/ISGLS for pancreas and liver,
CAP protocol core elements for pathology.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

T_PATTERN = r"^T(X|is|0|[1-4][a-e]?)$"
N_PATTERN = r"^N(X|0|[1-3][a-c]?)(\((sn|f|mi|i\+|i-)\))?$"
M_PATTERN = r"^M(X|0|1[a-e]?)$"


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# --- shared vocabularies ----------------------------------------------------


class Approach(str, Enum):
    open = "open"
    laparoscopic = "laparoscopic"
    robotic = "robotic"
    endoscopic = "endoscopic"
    hybrid = "hybrid"


class Role(str, Enum):
    primary_surgeon = "primary_surgeon"
    supervising = "supervising"  # resident operating, you scrubbed or supervising
    assisting = "assisting"


class Intent(str, Enum):
    curative = "curative"
    palliative = "palliative"
    diagnostic = "diagnostic"
    not_applicable = "not_applicable"


class Urgency(str, Enum):
    elective = "elective"
    emergency = "emergency"


class Margin(str, Enum):
    R0 = "R0"
    R1 = "R1"
    R2 = "R2"
    RX = "RX"


class ClavienDindo(str, Enum):
    none = "none"
    I = "I"  # noqa: E741
    II = "II"
    IIIa = "IIIa"
    IIIb = "IIIb"
    IVa = "IVa"
    IVb = "IVb"
    V = "V"


MAJOR_COMPLICATION = {ClavienDindo.IIIa, ClavienDindo.IIIb, ClavienDindo.IVa, ClavienDindo.IVb, ClavienDindo.V}


class ClinicalStage(Strict):
    t: str | None = Field(None, pattern=T_PATTERN, description="cT, e.g. T2")
    n: str | None = Field(None, pattern=N_PATTERN, description="cN, e.g. N1")
    m: str | None = Field(None, pattern=M_PATTERN, description="cM, e.g. M0")
    group: str | None = Field(None, max_length=10, description="Stage group, e.g. IIB")


class Neoadjuvant(Strict):
    given: bool
    regimen: str | None = Field(None, max_length=200)
    response: str | None = Field(None, max_length=200, description="Clinical/radiological response")


# --- operative record ----------------------------------------------------------


class BaseRecord(Strict):
    procedure: str = Field(..., min_length=2, max_length=200)
    approach: Approach | None = None
    role: Role | None = None
    urgency: Urgency = Urgency.elective
    duration_min: int | None = Field(None, ge=1, le=1440)
    blood_loss_ml: int | None = Field(None, ge=0, le=20000)
    intra_op_events: str | None = Field(None, max_length=500)
    resident_involved: bool = False
    notes: str | None = Field(None, max_length=2000)


class OncologyRecord(BaseRecord):
    diagnosis: str = Field(..., min_length=2, max_length=200)
    intent: Intent = Intent.curative
    clinical_stage: ClinicalStage | None = None
    neoadjuvant: Neoadjuvant | None = None
    frozen_section: bool | None = None


class BreastRecord(OncologyRecord):
    laterality: Literal["left", "right", "bilateral"]
    er: Literal["positive", "negative", "unknown"] = "unknown"
    pr: Literal["positive", "negative", "unknown"] = "unknown"
    her2: Literal["positive", "negative", "equivocal", "unknown"] = "unknown"
    ki67_percent: int | None = Field(None, ge=0, le=100)
    breast_procedure: Literal["bcs", "simple_mastectomy", "mrm", "skin_sparing", "nipple_sparing", "other"]
    axilla: Literal["none", "slnb", "alnd", "slnb_then_alnd", "tad"] = "none"
    clip_marked: bool | None = None
    reconstruction: Literal["none", "implant", "autologous", "oncoplastic"] = "none"


class UpperGIRecord(OncologyRecord):
    organ: Literal["oesophagus", "gej", "stomach"]
    siewert: Literal["I", "II", "III"] | None = None
    lymphadenectomy: Literal["D1", "D1_plus", "D2", "two_field", "three_field", "none"] | None = None
    anastomosis: str | None = Field(None, max_length=100)
    feeding_jejunostomy: bool = False


class ColorectalRecord(OncologyRecord):
    segment: Literal["right_colon", "transverse", "left_colon", "sigmoid", "rectum", "anal_canal"]
    tumour_height_cm: float | None = Field(None, ge=0, le=30, description="From anal verge, rectal cancers")
    resection: str | None = Field(None, max_length=100)
    stoma: Literal["none", "loop_ileostomy", "end_colostomy", "loop_colostomy", "end_ileostomy"] = "none"


class HPBRecord(OncologyRecord):
    organ: Literal["pancreas", "liver", "bile_duct", "gallbladder", "periampullary"]
    resection: str = Field(..., max_length=100)
    vascular_resection: bool = False


class GynaeOncRecord(OncologyRecord):
    organ: Literal["ovary", "endometrium", "cervix", "vulva", "other"]
    figo_stage: str | None = Field(None, max_length=10)
    pci: int | None = Field(None, ge=0, le=39, description="Peritoneal cancer index")
    cc_score: Literal["CC0", "CC1", "CC2", "CC3"] | None = None
    nodal_dissection: Literal["none", "pelvic", "pelvic_paraaortic", "sentinel"] = "none"
    hipec: bool = False


class SkinSurfaceRecord(OncologyRecord):
    kind: Literal["melanoma", "bcc", "scc", "other"]
    site: str = Field(..., max_length=100)
    slnb: bool = False
    reconstruction: Literal["primary", "flap", "graft", "none"] = "primary"


class SarcomaRecord(OncologyRecord):
    site: str = Field(..., max_length=100)
    size_cm: float | None = Field(None, gt=0, le=100)
    depth: Literal["superficial", "deep"] | None = None
    margin_plan: Literal["wide", "marginal", "planned_close"] | None = None
    neoadjuvant_rt: bool = False
    limb_salvage: bool | None = None


class GeneralRecord(BaseRecord):
    indication: str = Field(..., min_length=2, max_length=200)
    category: Literal["major", "minor"] = "major"


class EndoscopyRecord(Strict):
    procedure: str = Field(..., min_length=2, max_length=200)
    scope: Literal["ugi", "colonoscopy", "sigmoidoscopy", "eus", "ercp", "other"]
    indication: str = Field(..., min_length=2, max_length=200)
    findings: str | None = Field(None, max_length=2000)
    biopsies_taken: bool = False
    therapeutic: str | None = Field(None, max_length=200)
    role: Role | None = None
    urgency: Urgency = Urgency.elective
    notes: str | None = Field(None, max_length=2000)


# --- pathology -----------------------------------------------------------------


class BaseHistopath(Strict):
    histology: str | None = Field(None, max_length=200)
    grade: str | None = Field(None, max_length=20)
    pt: str | None = Field(None, pattern=r"^y?p?" + T_PATTERN[1:])
    pn: str | None = Field(None, pattern=r"^y?p?" + N_PATTERN[1:])
    margin: Margin | None = None
    nodes_examined: int | None = Field(None, ge=0, le=200)
    nodes_positive: int | None = Field(None, ge=0, le=200)
    lvi: bool | None = None
    pni: bool | None = None
    notes: str | None = Field(None, max_length=2000)


class BreastHistopath(BaseHistopath):
    rcb_class: Literal["0", "I", "II", "III"] | None = None
    miller_payne: int | None = Field(None, ge=1, le=5)


class UpperGIHistopath(BaseHistopath):
    trg: str | None = Field(None, max_length=20, description="Tumour regression grade and system used")


class ColorectalHistopath(BaseHistopath):
    tme_quality: Literal["complete", "near_complete", "incomplete"] | None = None
    crm_mm: float | None = Field(None, ge=0, le=100)
    mmr_status: Literal["proficient", "deficient", "unknown"] = "unknown"


class GynaeHistopath(BaseHistopath):
    figo_stage_path: str | None = Field(None, max_length=10)


class SkinHistopath(BaseHistopath):
    breslow_mm: float | None = Field(None, ge=0, le=100)
    ulceration: bool | None = None
    mitoses_per_mm2: float | None = Field(None, ge=0)
    peripheral_margin_mm: float | None = Field(None, ge=0)
    deep_margin_mm: float | None = Field(None, ge=0)


class SarcomaHistopath(BaseHistopath):
    fnclcc_grade: Literal["1", "2", "3"] | None = None
    closest_margin_mm: float | None = Field(None, ge=0)


class EndoscopyHistopath(Strict):
    result: str = Field(..., min_length=2, max_length=2000)


# --- complications ---------------------------------------------------------------


class ComplicationCheck(Strict):
    grade: ClavienDindo
    description: str | None = Field(None, max_length=500)
    readmission: bool = False
    reoperation: bool = False
    # Pancreas (ISGPS) and liver (ISGLS) definitions, HPB cases only.
    popf: Literal["none", "BL", "B", "C"] | None = None
    dge: Literal["none", "A", "B", "C"] | None = None
    pph: Literal["none", "A", "B", "C"] | None = None
    phlf: Literal["none", "A", "B", "C"] | None = None
    anastomotic_leak: bool | None = None


# --- registry ----------------------------------------------------------------------


@dataclass(frozen=True)
class Template:
    key: str
    label: str
    oncology: bool
    record: type[Strict]
    histopath: type[Strict] | None
    complication_checks: bool = True


TEMPLATES: dict[str, Template] = {
    t.key: t
    for t in [
        Template(key="breast", label="Breast", oncology=True, record=BreastRecord, histopath=BreastHistopath),
        Template(key="upper_gi", label="Upper GI", oncology=True, record=UpperGIRecord, histopath=UpperGIHistopath),
        Template(key="colorectal", label="Colorectal", oncology=True, record=ColorectalRecord, histopath=ColorectalHistopath),
        Template(key="hpb", label="HPB", oncology=True, record=HPBRecord, histopath=BaseHistopath),
        Template(key="gynae_onc", label="Gynae-onc", oncology=True, record=GynaeOncRecord, histopath=GynaeHistopath),
        Template(key="skin_surface", label="Skin & surface", oncology=True, record=SkinSurfaceRecord, histopath=SkinHistopath),
        Template(key="sarcoma", label="Sarcoma", oncology=True, record=SarcomaRecord, histopath=SarcomaHistopath),
        Template(key="general", label="General surgery", oncology=False, record=GeneralRecord, histopath=None),
        Template(key="endoscopy", label="Endoscopy", oncology=False, record=EndoscopyRecord, histopath=EndoscopyHistopath, complication_checks=False),
    ]
}

TemplateKey = Literal["breast", "upper_gi", "colorectal", "hpb", "gynae_onc", "skin_surface", "sarcoma", "general", "endoscopy"]

STANDARDS = {
    "staging": "AJCC TNM, current edition per site; FIGO for gynaecological cancers",
    "surveillance": "NCCN by default, with ICMR consensus guidelines shown where they exist; hospital or tumour-board protocol overrides",
    "complications": "Clavien-Dindo; ISGPS (pancreas) and ISGLS (liver) definitions for HPB",
    "pathology": "CAP cancer protocol core elements",
    "complication_check_days": [30, 90],
}


def initial_histopath_status(template: Template, data: Strict) -> str:
    if template.key == "endoscopy":
        return "pending" if getattr(data, "biopsies_taken", False) else "not_applicable"
    if template.oncology:
        return "pending"
    return "not_applicable"


def describe() -> dict:
    """Template JSON schemas and standards, for the app to render forms."""
    return {
        "standards": STANDARDS,
        "templates": [
            {
                "key": t.key,
                "label": t.label,
                "oncology": t.oncology,
                "complication_checks": t.complication_checks,
                "record_schema": t.record.model_json_schema(),
                "histopath_schema": t.histopath.model_json_schema() if t.histopath else None,
            }
            for t in TEMPLATES.values()
        ],
        "complication_schema": ComplicationCheck.model_json_schema(),
    }

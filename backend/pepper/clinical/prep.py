"""Pre-operative prep checklist for an OT-list item.

Deterministic rules keyed on the procedure text and template, so the checklist
is predictable and testable. Pepper (the agent) can add items; these are the
floor.
"""

import re

_MAJOR_RESECTION = re.compile(
    r"mastectomy|\bmrm\b|whipple|pancreat|gastrectom|oesophag|esophag|colectom|hemicolectom|"
    r"anterior resection|\bapr\b|abdominoperineal|hepatectom|liver resection|cytoreduct|debulk|"
    r"hysterectom|wertheim|exenteration|laparotomy|excision of sarcoma|compartment",
    re.I,
)
_SLNB = re.compile(r"sentinel|\bslnb\b", re.I)
_BCS = re.compile(r"\bbcs\b|breast conserv|wide local excision|\bwle\b|lumpectomy", re.I)
_STOMA_LIKELY = re.compile(r"anterior resection|\bapr\b|abdominoperineal|\blar\b|hartmann", re.I)
_HIPEC = re.compile(r"hipec", re.I)
_COLONOSCOPY = re.compile(r"colonoscop|sigmoidoscop", re.I)
_ENDOSCOPY = re.compile(r"scop|\bogd\b|\bugie?\b|\beus\b|\bercp\b", re.I)


def checklist(procedure: str, template: str | None = None, post_nact: bool = False) -> list[str]:
    """Return prep items, most important first. No duplicates."""
    items: list[str] = []

    def add(item: str) -> None:
        if item not in items:
            items.append(item)

    is_endoscopy = template == "endoscopy" or bool(_ENDOSCOPY.search(procedure))
    add("Consent")
    if is_endoscopy:
        add("Nil by mouth confirmed")
        if _COLONOSCOPY.search(procedure):
            add("Bowel prep")
        add("Biopsy request forms")
        return items

    add("Pre-anaesthetic fitness")
    if _MAJOR_RESECTION.search(procedure):
        add("Blood cross-matched")
        add("ICU/HDU bed if needed")
    if _SLNB.search(procedure):
        add("Lymphoscintigraphy / dye booked")
        add("Frozen section requested")
    if _BCS.search(procedure):
        add("Localisation (wire/clip) confirmed")
        add("Frozen section requested")
    if post_nact and (template == "breast" or _BCS.search(procedure) or "mastectomy" in procedure.lower()):
        add("Tumour clip marked")
    if _STOMA_LIKELY.search(procedure):
        add("Stoma site marked")
    if _HIPEC.search(procedure):
        add("HIPEC machine and perfusionist booked")
    if template == "sarcoma":
        add("Biopsy tract marked for excision")
    return items

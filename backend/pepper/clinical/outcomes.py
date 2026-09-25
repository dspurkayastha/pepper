"""Practice metrics and follow-up work computed from the case log."""

from datetime import date, timedelta
from statistics import median

from pepper.clinical.templates import MAJOR_COMPLICATION, TEMPLATES, ClavienDindo
from pepper.models import Case

CHECK_DAYS = (30, 90)


def due_items(cases: list[Case], today: date) -> dict:
    """Histopath reports still pending, and complication checks now due."""
    pending = [c for c in cases if c.histopath_status == "pending"]
    checks = []
    for c in cases:
        if not TEMPLATES[c.template].complication_checks:
            continue
        for days in CHECK_DAYS:
            due_on = c.performed_on + timedelta(days=days)
            if due_on <= today and str(days) not in (c.complications or {}):
                checks.append({"case_id": c.id, "day": days, "due_on": due_on.isoformat(), "template": c.template})
    return {
        "histopath_pending": [
            {"case_id": c.id, "template": c.template, "performed_on": c.performed_on.isoformat(),
             "procedure": c.data.get("procedure")}
            for c in pending
        ],
        "complication_checks": checks,
    }


def summary(cases: list[Case]) -> dict:
    """Headline numbers for the Practice screen. A metric is None when there is no data for it."""
    by_template: dict[str, int] = {}
    for c in cases:
        by_template[c.template] = by_template.get(c.template, 0) + 1

    onc = [c for c in cases if TEMPLATES[c.template].oncology]
    margins = [c.histopath.get("margin") for c in onc if c.histopath and c.histopath.get("margin") not in (None, "RX")]
    yields = [c.histopath["nodes_examined"] for c in onc if c.histopath and c.histopath.get("nodes_examined") is not None]

    graded = [c for c in cases if "30" in (c.complications or {})]
    major = [c for c in graded if ClavienDindo(c.complications["30"]["grade"]) in MAJOR_COMPLICATION]

    return {
        "total": len(cases),
        "by_template": by_template,
        "r0_rate": round(margins.count("R0") / len(margins), 3) if margins else None,
        "r0_denominator": len(margins),
        "median_node_yield": median(yields) if yields else None,
        "node_yield_denominator": len(yields),
        "major_complication_rate_30d": round(len(major) / len(graded), 3) if graded else None,
        "complication_denominator_30d": len(graded),
        "histopath_pending": sum(1 for c in cases if c.histopath_status == "pending"),
    }

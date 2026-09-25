"""Guard against patient identifiers reaching the server.

The phone de-identifies images and keeps names and hospital numbers in its own
encrypted store. This is the server-side backstop for free text: anything that
looks like an identifier is rejected (for case records) or stripped (for
machine-read OT lists).
"""

import re

_DIGIT_RUN = re.compile(r"\d[\d\s/-]*\d")
_DATE = re.compile(r"\d{1,2}[-/]\d{1,2}[-/]\d{2,4}|\d{4}[-/]\d{1,2}[-/]\d{1,2}")

_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("hospital-number label", re.compile(r"\b(uhid|mrn|cr\s*no|ip\s*no|op\s*no|hosp(ital)?\s*no|reg(istration)?\s*no)\b", re.I)),
    ("title followed by a name", re.compile(r"\b(?i:mr|mrs|ms|smt|shri|sri|kumari|master)\.?\s+[A-Z][a-z]+")),
    ("email address", re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")),
]


def find_identifier(text: str) -> str | None:
    """Return a short reason if `text` looks like it contains an identifier."""
    # Long digit runs: hospital numbers, UHID/MRN, phone numbers, Aadhaar. Dates are fine.
    for run in _DIGIT_RUN.findall(text):
        if _DATE.fullmatch(run.strip()):
            continue
        if sum(ch.isdigit() for ch in run) >= 7:
            return "number that looks like an ID or phone"
    for reason, pattern in _PATTERNS:
        if pattern.search(text):
            return reason
    return None


def scan(value: object, path: str = "") -> list[str]:
    """Walk nested data and return 'path: reason' for every suspicious string."""
    problems: list[str] = []
    if isinstance(value, str):
        reason = find_identifier(value)
        if reason:
            problems.append(f"{path or 'value'}: {reason}")
    elif isinstance(value, dict):
        for key, item in value.items():
            problems += scan(item, f"{path}.{key}" if path else str(key))
    elif isinstance(value, list):
        for i, item in enumerate(value):
            problems += scan(item, f"{path}[{i}]")
    return problems

import pytest

from pepper.clinical.prep import checklist
from pepper.privacy import find_identifier, scan


@pytest.mark.parametrize("text", [
    "Mrs Sharma for MRM", "SMT. Devi", "UHID 20431", "IP no 5512", "call 98765 43210",
    "1234 5678 9012", "reach me at dev@example.com",
])
def test_identifiers_are_caught(text):
    assert find_identifier(text)


@pytest.mark.parametrize("text", [
    "cT2 N1 M0, 118 min, EBL 150 mL", "AC x 4 then T x 4", "seen on 25-09-2026", "Ki-67 30%",
    "Ms-positive margins", "D2 lymphadenectomy, 18 nodes",
])
def test_clinical_text_is_allowed(text):
    assert find_identifier(text) is None


def test_scan_reports_paths():
    problems = scan({"notes": "ok", "neoadjuvant": {"regimen": "Mr Kumar's regimen"}})
    assert problems == ["neoadjuvant.regimen: title followed by a name"]


def test_prep_mrm_post_nact():
    items = checklist("Modified radical mastectomy, left", "breast", post_nact=True)
    assert items[:2] == ["Consent", "Pre-anaesthetic fitness"]
    assert "Blood cross-matched" in items and "Tumour clip marked" in items


def test_prep_wle_slnb():
    items = checklist("WLE + sentinel lymph node biopsy", "breast")
    assert "Lymphoscintigraphy / dye booked" in items
    assert "Localisation (wire/clip) confirmed" in items
    assert items.count("Frozen section requested") == 1


def test_prep_endoscopy_and_stoma():
    assert "Bowel prep" in checklist("Colonoscopy", "endoscopy")
    assert "Pre-anaesthetic fitness" not in checklist("Upper GI endoscopy", "endoscopy")
    assert "Stoma site marked" in checklist("Abdominoperineal resection (APR)", "colorectal")
    assert "HIPEC machine and perfusionist booked" in checklist("Cytoreductive surgery + HIPEC", "gynae_onc")

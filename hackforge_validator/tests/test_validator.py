import io, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
from PIL import Image

from validator.comparator import compare
from validator.config import MarkRules, PhotoRules
from validator.marksheet_extractor import ExtractedMark, Extraction, parse_number
from validator.photo_validator import validate_photo


def jpeg(w, h, value=128, noise=30, q=90):
    rng = np.random.default_rng(0)
    a = np.clip(rng.normal(value, noise, (h, w, 3)), 0, 255).astype(np.uint8)
    b = io.BytesIO(); Image.fromarray(a).save(b, "JPEG", quality=q); return b.getvalue()


def status(checks, name):
    return next(c.status for c in checks if c.name == name)


def test_photo_resolution_fail_matches_catalogue_example():
    r = validate_photo(jpeg(180, 220))
    assert status(r, "Photo Resolution") == "FAIL"
    assert "180 × 220" in next(c.details for c in r if c.name == "Photo Resolution")


def test_photo_good_passes_core_checks():
    r = validate_photo(jpeg(420, 540))
    for n in ("File Format", "Photo Resolution", "Photo Aspect Ratio", "Orientation", "Brightness"):
        assert status(r, n) == "PASS"


def test_photo_landscape_and_dark_fail():
    assert status(validate_photo(jpeg(640, 480)), "Orientation") == "FAIL"
    assert status(validate_photo(jpeg(420, 540, value=30, noise=10)), "Brightness") == "FAIL"


def test_corrupt_photo_is_failed_not_crashed():
    assert validate_photo(b"not an image")[0].status == "FAIL"


def test_parse_number_repairs_ocr_confusions():
    assert parse_number("85") == (85, False)
    assert parse_number("8S") == (85, True)
    assert parse_number("O") == (0, True)
    assert parse_number("PASS") is None and parse_number("A+") is None


def _ex(marks, conf=95, repaired=False):
    ex = Extraction()
    for s, v in marks.items():
        ex.marks[s] = ExtractedMark(s, v, 100, conf, repaired, "")
    return ex


FULL = {"Tamil": 80, "English": 92, "Mathematics": 88, "Physics": 70, "Chemistry": 66, "Computer Science": 75}


def test_catalogue_example_mismatch():
    entered = {"marks": {**FULL, "Mathematics": 85}}
    r = compare(entered, _ex(FULL), MarkRules())
    m = next(c for c in r if c.name == "Mathematics Marks")
    assert (m.status, m.entered, m.uploaded) == ("FAIL", "85", "88")
    assert status(r, "English Marks") == "PASS"


def test_low_confidence_difference_goes_to_review_not_fail():
    r = compare({"marks": {**FULL, "Physics": 71}}, _ex({**FULL}, conf=40), MarkRules())
    assert status(r, "Physics Marks") == "REVIEW"


def test_missing_subject_and_completeness():
    sheet = {k: v for k, v in FULL.items() if k != "Chemistry"}
    r = compare({"marks": FULL}, _ex(sheet), MarkRules())
    assert status(r, "Chemistry Marks") == "REVIEW"
    assert status(r, "Mark Sheet Completeness") == "REVIEW"


def test_register_number_one_char_off_is_review():
    ex = _ex(FULL); ex.register_no = "2612345"
    assert status(compare({"marks": FULL, "register_no": "2612346"}, ex), "Register Number") == "REVIEW"
    assert status(compare({"marks": FULL, "register_no": "2699999"}, ex), "Register Number") == "FAIL"


def test_end_to_end_on_generated_sample():
    import json
    from validator import validate_application
    root = Path(__file__).resolve().parents[1] / "samples"
    case = next(c for c in json.loads((root / "manifest.json").read_text())
                if c["truth"]["degradation"] == "clean" and not c["truth"]["problems"])
    rep, _ = validate_application(case["case_id"], case["entered"], (root / case["marksheet"]).read_bytes(),
                                  (root / case["photo"]).read_bytes())
    assert rep.overall == "PASS"

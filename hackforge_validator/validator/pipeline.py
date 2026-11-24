from .config import MarkRules, PhotoRules, SUBJECT_ALIASES, canonical_subject
from .comparator import compare
from .marksheet_extractor import extract_marksheet
from .models import CheckResult, Report
from .photo_validator import validate_photo


def build_report(app_id: str, checks: list) -> Report:
    statuses = {c.status for c in checks}
    overall = "FAIL" if "FAIL" in statuses else "REVIEW" if "REVIEW" in statuses else "PASS"
    reasons = [f"{c.name}: {c.label}" + (f" - {c.details}" if c.details else "")
               for c in checks if c.status != "PASS"]
    return Report(app_id, overall, checks, reasons)


def validate_application(app_id: str, entered: dict, marksheet_bytes: bytes, photo_bytes: bytes,
                         mark_rules: MarkRules = None, photo_rules: PhotoRules = None, on_stage=None):
    """Returns (Report, Extraction|None). Never raises on bad input: it routes to review instead.
    on_stage(message) is called before each stage so a UI can show progress."""
    mark_rules, photo_rules = mark_rules or MarkRules(), photo_rules or PhotoRules()
    note = on_stage or (lambda msg: None)
    checks, extraction, err = [], None, None
    # subject names are matched without caring about capitalisation or spelling variants
    marks = {canonical_subject(k): v for k, v in entered.get("marks", {}).items()}
    entered = {**entered, "marks": marks}
    extras = [s for s in marks if s not in SUBJECT_ALIASES]      # courses the student added themselves

    note("OCR engine: reading the mark sheet")
    try:
        extraction = extract_marksheet(marksheet_bytes, extra_subjects=extras)
    except Exception as exc:                       # unreadable file, OCR crash, ...
        err = exc

    note("Image analyzer: checking the photo")
    photo_checks = validate_photo(photo_bytes, photo_rules)

    note("Mark comparison: matching typed marks with the sheet")
    if err is None:
        try:
            checks += compare(entered, extraction, mark_rules)
        except Exception as exc:
            err = exc
    if err is not None:
        checks.append(CheckResult("Mark Sheet Readable", "REVIEW", "Needs review",
                                  f"Could not process the mark sheet ({err})"))
    checks += photo_checks
    return build_report(app_id, checks), extraction
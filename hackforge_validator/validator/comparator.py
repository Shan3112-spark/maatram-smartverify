"""Cross-check typed form data against what OCR read from the mark sheet."""
from rapidfuzz import fuzz
from rapidfuzz.distance import Levenshtein

import re

from .config import MarkRules, canonical_subject
from .models import CheckResult


def _mark(subject, entered, ex, rules):
    if ex is None:
        return CheckResult(f"{subject} Marks", "REVIEW", "Missing on sheet",
                           "Subject not found on the uploaded mark sheet (or OCR could not read it)",
                           entered=str(entered), uploaded="-")
    unsure = ex.confidence < rules.low_conf_threshold or ex.repaired
    if ex.max_marks and ex.obtained > ex.max_marks:
        return CheckResult(f"{subject} Marks", "REVIEW", "Implausible value",
                           f"Read {ex.obtained}, which exceeds the maximum {ex.max_marks}",
                           str(entered), str(ex.obtained), ex.confidence)
    if entered == ex.obtained:
        return CheckResult(f"{subject} Marks", "PASS", "Match", "", str(entered),
                           str(ex.obtained), ex.confidence)
    if unsure:      # values differ, but OCR itself is not sure -> a human decides
        return CheckResult(f"{subject} Marks", "REVIEW", "Needs review",
                           f"Values differ and OCR confidence is low ({ex.confidence:.0f}%)",
                           str(entered), str(ex.obtained), ex.confidence)
    return CheckResult(f"{subject} Marks", "FAIL", "Mismatch",
                       f"Entered {entered}, sheet shows {ex.obtained}",
                       str(entered), str(ex.obtained), ex.confidence)


def compare(entered: dict, ex, rules: MarkRules = None) -> list:
    """entered = {"name": str, "register_no": str, "marks": {subject: int}}"""
    rules = rules or MarkRules()
    out = []

    # ---- subject marks
    entered_marks = {canonical_subject(k): v for k, v in entered.get("marks", {}).items()}
    for subj in dict.fromkeys(list(rules.required_subjects) + list(entered_marks) + list(ex.marks)):
        e, u = entered_marks.get(subj), ex.marks.get(subj)
        if e is None and u is None:
            continue
        if e is None:
            out.append(CheckResult(f"{subj} Marks", "REVIEW", "Not entered",
                                   "Present on the sheet but missing from the form",
                                   "-", str(u.obtained), u.confidence))
        else:
            out.append(_mark(subj, e, u, rules))

    # ---- completeness
    missing = [s for s in rules.required_subjects if s not in ex.marks]
    out.append(CheckResult("Mark Sheet Completeness", "PASS" if not missing else "REVIEW",
                           "Pass" if not missing else "Incomplete",
                           "All required subjects present" if not missing
                           else "Not found on sheet: " + ", ".join(missing)))

    # ---- internal consistency: does the printed total equal the sum of subjects?
    if ex.total is not None and ex.marks and not missing:
        s = sum(m.obtained for m in ex.marks.values())          # core subjects + any extra courses
        confs = [m.confidence for m in ex.marks.values()] + [ex.total_conf]
        if s == ex.total:
            out.append(CheckResult("Total Consistency", "PASS", "Match",
                                   f"Subjects add up to {s}", confidence=min(confs)))
        else:
            sure = min(confs) >= rules.low_conf_threshold
            out.append(CheckResult("Total Consistency", "FAIL" if sure else "REVIEW",
                                   "Mismatch" if sure else "Needs review",
                                   f"Subjects add up to {s}, but the sheet total reads {ex.total} "
                                   "(a course may be missing from the form, or unreadable)",
                                   uploaded=str(ex.total), confidence=min(confs)))

    # ---- identity fields
    if entered.get("register_no"):
        e = re.sub(r"\s+", "", entered["register_no"]).upper()      # case and spaces never matter
        u = ex.register_no
        if u is None:
            out.append(CheckResult("Register Number", "REVIEW", "Missing on sheet",
                                   "Could not read a register number", e, "-"))
        elif e == u:
            out.append(CheckResult("Register Number", "PASS", "Match", "", e, u, ex.register_conf))
        elif Levenshtein.distance(e, u) <= 1:     # one character off: probably OCR
            out.append(CheckResult("Register Number", "REVIEW", "Needs review",
                                   "Differs by one character (typo or OCR slip)", e, u, ex.register_conf))
        else:
            out.append(CheckResult("Register Number", "FAIL", "Mismatch",
                                   "Register numbers differ", e, u, ex.register_conf))
    if entered.get("name"):
        e = entered["name"].strip()
        u = ex.name
        if u is None:
            out.append(CheckResult("Student Name", "REVIEW", "Missing on sheet",
                                   "Could not read a name", e, "-"))
        else:
            clean = lambda t: re.sub(r"[^a-z0-9 ]", "", t.lower())     # case, dots and commas never matter
            sc = fuzz.token_sort_ratio(clean(e), clean(u))
            if sc >= rules.name_match_pass:
                out.append(CheckResult("Student Name", "PASS", "Match", f"similarity {sc:.0f}%", e, u))
            elif sc >= rules.name_match_review:
                out.append(CheckResult("Student Name", "REVIEW", "Needs review",
                                       f"similarity {sc:.0f}%", e, u))
            else:
                out.append(CheckResult("Student Name", "FAIL", "Mismatch", f"similarity {sc:.0f}%", e, u))
    return out
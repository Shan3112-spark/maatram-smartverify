"""Mark sheet extraction: classical image clean-up + Tesseract OCR + rule-based parsing."""
import re
from dataclasses import dataclass, field
from typing import Optional

import cv2
import numpy as np
import pytesseract
import os, shutil
if not shutil.which("tesseract"):
    for _p in (r"C:\Program Files\Tesseract-OCR\tesseract.exe",
               r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
               os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe")):
        if os.path.exists(_p):
            pytesseract.pytesseract.tesseract_cmd = _p
            break
from rapidfuzz import fuzz

from .config import alias_map

# characters OCR commonly confuses with digits
_FULL_MAP = str.maketrans({"O": "0", "o": "0", "l": "1", "I": "1", "|": "1",
                           "S": "5", "B": "8", "Z": "2"})
_LOOKALIKE_ONLY = set("Oo") | set("lI")


@dataclass
class Word:
    text: str
    conf: float
    left: int
    top: int
    w: int
    h: int

    @property
    def cy(self):
        return self.top + self.h / 2


@dataclass
class Line:
    words: list = field(default_factory=list)

    @property
    def text(self):
        return " ".join(w.text for w in self.words)

    @property
    def mean_conf(self):
        c = [w.conf for w in self.words if w.conf >= 0]
        return float(np.mean(c)) if c else 0.0


@dataclass
class ExtractedMark:
    subject: str
    obtained: int
    max_marks: Optional[int]
    confidence: float
    repaired: bool
    raw_line: str


@dataclass
class Extraction:
    marks: dict = field(default_factory=dict)      # subject -> ExtractedMark
    name: Optional[str] = None
    name_conf: float = 0.0
    register_no: Optional[str] = None
    register_conf: float = 0.0
    total: Optional[int] = None
    total_conf: float = 0.0
    lines: list = field(default_factory=list)      # raw OCR text, for the reviewer


# ---------------------------------------------------------------- pre-processing
def _deskew_angle(binary_inv: np.ndarray) -> float:
    """Projection-profile search: the right angle gives the sharpest row histogram."""
    h, w = binary_inv.shape
    s = 700 / max(h, w)
    small = cv2.resize(binary_inv, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
    c = (small.shape[1] // 2, small.shape[0] // 2)

    def score(angle):
        m = cv2.getRotationMatrix2D(c, angle, 1.0)
        r = cv2.warpAffine(small, m, (small.shape[1], small.shape[0]))
        return float(np.var(r.sum(axis=1)))

    coarse = max(np.arange(-6, 6.01, 0.5), key=score)
    return float(max(np.arange(coarse - 0.5, coarse + 0.51, 0.1), key=score))


def _remove_table_lines(binary_inv: np.ndarray) -> np.ndarray:
    h, w = binary_inv.shape
    horiz = cv2.morphologyEx(binary_inv, cv2.MORPH_OPEN,
                             cv2.getStructuringElement(cv2.MORPH_RECT, (max(40, w // 12), 1)))
    vert = cv2.morphologyEx(binary_inv, cv2.MORPH_OPEN,
                            cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(40, h // 25))))
    lines = cv2.dilate(cv2.bitwise_or(horiz, vert), np.ones((3, 3), np.uint8))
    return cv2.bitwise_and(binary_inv, cv2.bitwise_not(lines))


def preprocess(img_bgr: np.ndarray) -> np.ndarray:
    """Returns a clean black-text-on-white image ready for OCR."""
    grey = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    if grey.shape[1] < 1600:                                   # upscale small scans
        f = 1600 / grey.shape[1]
        grey = cv2.resize(grey, None, fx=f, fy=f, interpolation=cv2.INTER_CUBIC)
    # flatten uneven lighting: divide by a heavily blurred copy of the background
    bg = cv2.medianBlur(cv2.dilate(grey, np.ones((15, 15), np.uint8)), 31)
    flat = cv2.divide(grey, bg, scale=255)
    flat = cv2.fastNlMeansDenoising(flat, None, h=12, templateWindowSize=5, searchWindowSize=15)
    _, inv = cv2.threshold(flat, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    angle = _deskew_angle(inv)
    if abs(angle) > 0.05:
        m = cv2.getRotationMatrix2D((inv.shape[1] / 2, inv.shape[0] / 2), angle, 1.0)
        inv = cv2.warpAffine(inv, m, (inv.shape[1], inv.shape[0]), flags=cv2.INTER_LINEAR)
    inv = _remove_table_lines(inv)
    inv = cv2.morphologyEx(inv, cv2.MORPH_CLOSE, np.ones((2, 2), np.uint8))
    return cv2.bitwise_not(inv)


# ---------------------------------------------------------------------- OCR
def ocr_lines(clean: np.ndarray) -> list:
    d = pytesseract.image_to_data(clean, lang="eng", config="--oem 1 --psm 6",
                                  output_type=pytesseract.Output.DICT)
    words = []
    for i, t in enumerate(d["text"]):
        t = t.strip()
        if t and float(d["conf"][i]) >= 0:
            words.append(Word(t, float(d["conf"][i]), d["left"][i], d["top"][i],
                              d["width"][i], d["height"][i]))
    words.sort(key=lambda w: w.cy)
    lines = []
    for w in words:                      # cluster by vertical position, not Tesseract's blocks
        if lines:
            last = lines[-1]
            cy = np.mean([x.cy for x in last.words])
            hh = np.mean([x.h for x in last.words])
            if abs(w.cy - cy) < 0.6 * max(w.h, hh):
                last.words.append(w)
                continue
        lines.append(Line([w]))
    for ln in lines:
        ln.words.sort(key=lambda w: w.left)
    return lines


# ------------------------------------------------------------------ parsing
def parse_number(tok: str):
    """-> (value, repaired) or None. Repairs typical OCR digit confusions."""
    t = tok.strip(".,:;[](){}")
    if not t:
        return None
    if t.isdigit():
        return int(t), False
    if any(ch.isdigit() for ch in t):
        fixed = t.translate(_FULL_MAP)
        return (int(fixed), True) if fixed.isdigit() else None
    if len(t) <= 3 and set(t) <= _LOOKALIKE_ONLY:
        fixed = t.translate(_FULL_MAP)
        return (int(fixed), True) if fixed.isdigit() else None
    return None


def _letters(s: str) -> str:
    return re.sub(r"[^a-z ]", "", s.lower()).strip()


def _find_subject(tokens: list, aliases_by_subject: dict):
    """Best fuzzy match of 1-3 consecutive *alphabetic* tokens to a known subject.
    Returns (canonical, index just after the subject words)."""
    best = (0.0, None, -1)
    for i in range(len(tokens)):
        for n in (1, 2, 3):
            if i + n > len(tokens):
                continue
            window = tokens[i:i + n]
            if any(any(ch.isdigit() for ch in t.text) for t in window):
                continue                      # numbers are never part of a subject name
            text = _letters(" ".join(t.text for t in window))
            if len(text) < 3:
                continue
            for canon, aliases in aliases_by_subject.items():
                for a in aliases:
                    s = fuzz.ratio(text, a)
                    if s > best[0]:           # strict '>' keeps the shortest window on ties
                        best = (s, canon, i + n)
    return (best[1], best[2]) if best[0] >= 80 else (None, -1)


def parse_lines(lines: list, extra_subjects=()) -> Extraction:
    """extra_subjects: course names the student typed beyond the known list (any capitalisation)."""
    known = alias_map(extra_subjects)
    ex = Extraction(lines=[ln.text for ln in lines])
    for ln in lines:
        toks, low = ln.words, ln.text.lower()

        # --- header fields
        if ex.name is None and "name" in low:
            m = re.search(r"name[^:]*[:\-]\s*(.+)$", ln.text, re.I) or \
                re.search(r"student\s*[:\-]?\s*(.+)$", ln.text, re.I)
            if m:
                ex.name, ex.name_conf = m.group(1).strip(), ln.mean_conf
                continue
        if ex.register_no is None and "regist" in low:
            m = re.search(r"regist\w*\s*(?:no\.?|number)?\s*[:\-]?\s*([A-Za-z0-9]{5,})", ln.text, re.I)
            if m:
                ex.register_no = m.group(1).upper()
                ex.register_conf = float(np.mean([w.conf for w in toks[-1:]])) if toks else 0.0
                continue

        # --- total row
        if fuzz.partial_ratio("total", low) >= 85 and _find_subject(toks, known)[0] is None:
            nums = [parse_number(w.text) for w in toks]
            nums = [(n, w) for n, w in zip(nums, toks) if n]
            if nums:
                (val, rep), w = nums[-1]
                ex.total, ex.total_conf = val, (min(w.conf, 50) if rep else w.conf)
                continue

        # --- subject rows
        canon, end = _find_subject(toks, known)
        if canon is None:
            continue
        found = []
        for w in toks[end:]:
            if set(w.text) <= set("|[]()_-—~"):       # stray table-border fragments
                continue
            n = parse_number(w.text)
            if n is None:
                break
            found.append((n, w))
            if len(found) == 2:
                break
        if not found:
            continue
        (obt, rep), w_obt = found[-1]
        max_marks = found[0][0][0] if len(found) == 2 else None
        conf = min(w_obt.conf, 50.0) if rep else w_obt.conf
        prev = ex.marks.get(canon)
        if prev is None or conf > prev.confidence:
            ex.marks[canon] = ExtractedMark(canon, obt, max_marks, conf, rep, ln.text)
    # A row with a single number in a sheet that has a "Max" column probably lost a cell:
    # the lone number may be the maximum, not the marks obtained -> never trust it.
    if any(m.max_marks for m in ex.marks.values()):
        for m in ex.marks.values():
            if m.max_marks is None:
                m.repaired, m.confidence = True, min(m.confidence, 40.0)
    return ex


def extract_marksheet(image_bytes: bytes, extra_subjects=()) -> Extraction:
    arr = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
    if arr is None:
        raise ValueError("Mark sheet could not be decoded as an image")
    return parse_lines(ocr_lines(preprocess(arr)), extra_subjects)
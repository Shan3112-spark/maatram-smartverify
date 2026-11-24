"""All thresholds live here so the admissions team can tune them without touching code."""
import re
from dataclasses import dataclass


@dataclass
class PhotoRules:
    allowed_formats: tuple = ("JPEG", "PNG")
    min_width: int = 300
    min_height: int = 400
    max_width: int = 4000
    max_height: int = 5000
    min_file_kb: float = 20.0
    max_file_kb: float = 1024.0
    aspect_min: float = 0.70          # width / height (3:4 passport style = 0.75)
    aspect_max: float = 0.85
    require_portrait: bool = True
    brightness_min: float = 70.0      # mean grey level 0-255
    brightness_max: float = 200.0
    min_contrast: float = 25.0        # std-dev of grey level
    min_sharpness: float = 60.0       # variance of Laplacian at normalised size


@dataclass
class MarkRules:
    required_subjects: tuple = ("Tamil", "English", "Mathematics", "Science", "Social Science")
    low_conf_threshold: float = 75.0   # Tesseract word confidence (0-100)
    name_match_pass: float = 85.0      # fuzzy score
    name_match_review: float = 60.0


# canonical subject -> accepted spellings (lower-case, letters only). Matching is NOT case sensitive.
SUBJECT_ALIASES = {
    "Tamil": ["tamil"],
    "English": ["english"],
    "Mathematics": ["mathematics", "maths", "math"],
    "Science": ["science", "general science"],
    "Social Science": ["social science", "social studies", "social sci"],
    "Physics": ["physics"],
    "Chemistry": ["chemistry"],
    "Biology": ["biology"],
    "Computer Science": ["computer science", "computer sci", "comp science"],
    "Hindi": ["hindi"],
}
CORE_SUBJECTS = ("Tamil", "English", "Mathematics", "Science", "Social Science")


def norm_name(text: str) -> str:
    """Lower-case, letters and single spaces only: 'Social  SCIENCE.' -> 'social science'."""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z ]", "", text.lower())).strip()


def canonical_subject(name: str) -> str:
    """Any capitalisation or known spelling -> one canonical name. Unknown names become Title Case."""
    n = norm_name(name)
    for canon, aliases in SUBJECT_ALIASES.items():
        if n == norm_name(canon) or n in aliases:
            return canon
    return n.title()


def alias_map(extra_names=()):
    """Known subjects plus any extra courses the student typed on the form."""
    m = {k: list(v) for k, v in SUBJECT_ALIASES.items()}
    for name in extra_names:
        c = canonical_subject(name)
        if c not in m and norm_name(name):
            m[c] = [norm_name(name)]
    return m
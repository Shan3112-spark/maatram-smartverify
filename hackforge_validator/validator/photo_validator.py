"""Profile photo checks: purely measurable properties (no AI)."""
import io
import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from .config import PhotoRules
from .models import CheckResult


def _chk(name, ok, label_ok, label_bad, details, conf=None):
    return CheckResult(name=name, status="PASS" if ok else "FAIL",
                       label=label_ok if ok else label_bad,
                       details=details, group="photo", confidence=conf)


def validate_photo(data: bytes, rules: PhotoRules = None) -> list:
    rules = rules or PhotoRules()
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except (UnidentifiedImageError, OSError, ValueError):
        return [_chk("Photo readable", False, "Pass", "Fail",
                     "File could not be opened as an image")]

    out = []
    fmt = (img.format or "UNKNOWN").upper()
    out.append(_chk("File Format", fmt in rules.allowed_formats, "Pass", "Fail",
                    f"{fmt}; allowed: {', '.join(rules.allowed_formats)}"))

    kb = len(data) / 1024
    out.append(_chk("File Size", rules.min_file_kb <= kb <= rules.max_file_kb, "Pass", "Fail",
                    f"{kb:.0f} KB; allowed {rules.min_file_kb:.0f}-{rules.max_file_kb:.0f} KB"))

    exif_orient = img.getexif().get(274, 1)
    img = ImageOps.exif_transpose(img).convert("RGB")      # respect camera rotation
    w, h = img.size

    res_ok = (rules.min_width <= w <= rules.max_width) and (rules.min_height <= h <= rules.max_height)
    out.append(_chk("Photo Resolution", res_ok, "Pass", "Fail",
                    f"{w} × {h}; minimum: {rules.min_width} × {rules.min_height}, "
                    f"maximum: {rules.max_width} × {rules.max_height}"))

    ar = w / h
    out.append(_chk("Photo Aspect Ratio", rules.aspect_min <= ar <= rules.aspect_max, "Pass", "Fail",
                    f"{ar:.2f} (width/height); accepted {rules.aspect_min:.2f}-{rules.aspect_max:.2f}"))

    portrait = h >= w
    note = " (EXIF rotation applied)" if exif_orient not in (1, None) else ""
    out.append(_chk("Orientation", portrait or not rules.require_portrait, "Pass", "Fail",
                    ("Portrait" if portrait else "Landscape") + note))

    grey = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2GRAY)
    mean, std = float(grey.mean()), float(grey.std())
    out.append(_chk("Brightness", rules.brightness_min <= mean <= rules.brightness_max, "Pass", "Fail",
                    f"mean grey {mean:.0f}; accepted {rules.brightness_min:.0f}-{rules.brightness_max:.0f}"))
    out.append(_chk("Contrast", std >= rules.min_contrast, "Pass", "Fail",
                    f"std-dev {std:.0f}; minimum {rules.min_contrast:.0f}"))

    # Sharpness: Laplacian variance after resizing to a fixed height so that
    # large and small photos are judged on the same scale.
    scale = 400 / h
    norm = cv2.resize(grey, (max(1, int(w * scale)), 400), interpolation=cv2.INTER_AREA)
    sharp = float(cv2.Laplacian(norm, cv2.CV_64F).var())
    out.append(_chk("Sharpness", sharp >= rules.min_sharpness, "Pass", "Fail",
                    f"Laplacian variance {sharp:.0f}; minimum {rules.min_sharpness:.0f}"))
    return out

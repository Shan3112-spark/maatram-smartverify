"""Creates SYNTHETIC mark sheets + profile photos with known ground truth.
No real student data is used anywhere. Usage:  python generate_synthetic.py --n 36 --out samples
"""
import argparse, json, random
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

SUBJECTS = ["Tamil", "English", "Mathematics", "Physics", "Chemistry", "Computer Science"]
FIRST = ["Priya", "Arun", "Kavya", "Karthik", "Divya", "Suresh", "Meena", "Vignesh", "Lakshmi",
         "Harish", "Nithya", "Gokul", "Revathi", "Sanjay", "Anitha", "Dinesh"]
LAST = ["Kumar", "Raj", "Devi", "Selvam", "Murugan", "Rani", "Babu", "Lakshmanan", "Prakash", "Nair"]
FD = "/usr/share/fonts/truetype/"
FONTS = {"sans": (FD + "dejavu/DejaVuSans.ttf", FD + "dejavu/DejaVuSans-Bold.ttf"),
         "serif": (FD + "dejavu/DejaVuSerif.ttf", FD + "dejavu/DejaVuSerif-Bold.ttf"),
         "lib": (FD + "liberation/LiberationSans-Regular.ttf", FD + "liberation/LiberationSans-Bold.ttf")}
LEVELS = {  # rotation deg, noise sigma, blur radius, brightness, jpeg quality
    "clean": (0.0, 0, 0.0, 1.0, 95), "mild": (1.0, 6, 0.6, 0.95, 85),
    "moderate": (2.0, 12, 1.0, 0.85, 70), "hard": (3.5, 20, 1.5, 0.75, 55)}


def grade(m):
    return "A+" if m >= 90 else "A" if m >= 80 else "B+" if m >= 70 else "B" if m >= 60 else "C"


def render_sheet(layout, name, reg, marks, total, omit=None):
    W, H = 1240, 1754
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    fam = {"A": "sans", "B": "lib", "C": "serif"}[layout]
    reg_f, bold_f = FONTS[fam]
    F = lambda s, b=False: ImageFont.truetype(bold_f if b else reg_f, s)
    d.text((W // 2, 100), "SPECIMEN BOARD OF SCHOOL EXAMINATIONS", font=F(40, True), fill="black", anchor="mm")
    d.text((W // 2, 160), "Statement of Marks (synthetic test document)", font=F(30), fill="black", anchor="mm")
    d.text((110, 300), f"Name of the Student : {name.upper()}", font=F(34), fill="black")
    d.text((110, 370), f"Register No : {reg}", font=F(34), fill="black")

    cols = {"A": [110, 700, 900, 1130], "B": [110, 220, 700, 850, 1000, 1130],
            "C": [110, 640, 790, 940, 1130]}[layout]
    heads = {"A": ["Subject", "Max Marks", "Marks Obtained"],
             "B": ["S.No", "Subject", "Max", "Obtained", "Result"],
             "C": ["Subject", "Max", "Obtained", "Grade"]}[layout]
    rows = [s for s in SUBJECTS if s != omit]
    y0, rh = 480, 84
    nrows = len(rows) + 2
    for r in range(nrows + 1):
        d.line([(cols[0], y0 + r * rh), (cols[-1], y0 + r * rh)], fill="black", width=3)
    for x in cols:
        d.line([(x, y0), (x, y0 + nrows * rh)], fill="black", width=3)
    for i, h in enumerate(heads):
        d.text((cols[i] + 16, y0 + rh // 2), h, font=F(28, True), fill="black", anchor="lm")
    for r, s in enumerate(rows, start=1):
        y = y0 + r * rh + rh // 2
        cells = {"A": [s, "100", str(marks[s])],
                 "B": [str(r), s, "100", str(marks[s]), "PASS"],
                 "C": [s, "100", str(marks[s]), grade(marks[s])]}[layout]
        for i, c in enumerate(cells):
            d.text((cols[i] + 16, y), c, font=F(32), fill="black", anchor="lm")
    y = y0 + (nrows - 1) * rh + rh // 2
    mx = str(100 * len(rows))
    cells = {"A": ["Total", mx, str(total)], "B": ["", "Total", mx, str(total), ""],
             "C": ["Total", mx, str(total), ""]}[layout]
    for i, c in enumerate(cells):
        d.text((cols[i] + 16, y), c, font=F(32, True), fill="black", anchor="lm")
    d.text((W - 110, H - 150), "Controller of Examinations (specimen)", font=F(26), fill="black", anchor="rm")
    return img


def degrade(img, rng, level):
    rot, sigma, blur, bright, q = LEVELS[level]
    a = np.array(img.filter(ImageFilter.GaussianBlur(blur)) if blur else img)
    a = cv2.cvtColor(a, cv2.COLOR_RGB2BGR).astype(np.float32)
    if rot:
        ang = rng.uniform(-rot, rot)
        m = cv2.getRotationMatrix2D((a.shape[1] / 2, a.shape[0] / 2), ang, 1.0)
        a = cv2.warpAffine(a, m, (a.shape[1], a.shape[0]), borderValue=(255, 255, 255))
    a = a * bright + (1 - bright) * 40
    if sigma:
        a += np.random.default_rng(rng.randrange(10**6)).normal(0, sigma, a.shape)
    a = np.clip(a, 0, 255).astype(np.uint8)
    ok, buf = cv2.imencode(".jpg", a, [cv2.IMWRITE_JPEG_QUALITY, q])
    return buf.tobytes()


def make_photo(rng, scenario):
    nrng = np.random.default_rng(rng.randrange(10**6))
    w, h = {"low_res": (180, 220), "landscape": (640, 480), "bad_aspect": (520, 520)}.get(scenario, (420, 540))
    bg = np.zeros((h, w, 3), np.float32)
    bg[:] = [200, 190, 175]
    bg *= (np.linspace(1.0, 0.8, h)[:, None, None])
    img = Image.fromarray(bg.astype(np.uint8))
    d = ImageDraw.Draw(img)
    cx, s = w // 2, min(w, h)
    d.ellipse([cx - .38 * s, h - .30 * s, cx + .38 * s, h + .45 * s], fill=(40, 60, 110))          # shoulders
    d.rectangle([cx - .07 * s, h * .60, cx + .07 * s, h * .78], fill=(176, 126, 98))               # neck
    d.ellipse([cx - .21 * s, h * .20, cx + .21 * s, h * .66], fill=(190, 138, 108))                # face
    d.pieslice([cx - .23 * s, h * .15, cx + .23 * s, h * .52], 180, 360, fill=(30, 22, 20))        # hair
    for ex in (-.08, .08):
        d.ellipse([cx + ex * s - .025 * s, h * .42 - .015 * s, cx + ex * s + .025 * s, h * .42 + .015 * s], fill=(25, 20, 20))
    d.arc([cx - .07 * s, h * .50, cx + .07 * s, h * .58], 20, 160, fill=(120, 50, 50), width=max(2, int(.008 * s)))
    a = np.array(img).astype(np.float32)
    a += nrng.normal(0, 7, a.shape)
    if scenario == "dark":
        a *= 0.28
    img = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    if scenario == "blurry":
        img = img.filter(ImageFilter.GaussianBlur(7))
    import io
    buf = io.BytesIO()
    fmt = "BMP" if scenario == "bad_format" else "JPEG"
    img.save(buf, format=fmt, **({"quality": 90} if fmt == "JPEG" else {}))
    return buf.getvalue(), ("bmp" if fmt == "BMP" else "jpg")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=36)
    ap.add_argument("--out", default="samples")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    rng = random.Random(args.seed)
    out = Path(args.out)
    (out / "sheets").mkdir(parents=True, exist_ok=True)
    (out / "photos").mkdir(exist_ok=True)

    sheet_scn = ["clean_data"] * 11 + ["mark_mismatch"] * 5 + ["missing_subject"] * 2 + ["reg_mismatch"] * 2 + ["bad_total"] * 2
    photo_scn = ["good"] * 11 + ["low_res", "dark", "blurry", "landscape", "bad_aspect", "bad_format"]
    lv = ["clean"] * 5 + ["mild"] * 8 + ["moderate"] * 6 + ["hard"] * 3
    manifest = []
    for i in range(args.n):
        cid = f"C{i + 1:03d}"
        scn = sheet_scn[i % len(sheet_scn)] if i < len(sheet_scn) else rng.choice(sheet_scn)
        pscn = rng.choice(photo_scn)
        level = rng.choice(lv)
        layout = rng.choice("ABC")
        name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
        reg = str(rng.randint(2600000, 2699999))
        marks = {s: rng.randint(35, 99) for s in SUBJECTS}
        sheet_total = sum(marks.values())
        entered = {"name": name, "register_no": reg, "marks": dict(marks)}
        omit = None
        problems = []
        if scn == "mark_mismatch":
            s = rng.choice(SUBJECTS)
            entered["marks"][s] = min(99, marks[s] + rng.choice([-7, -3, 3, 5, 8])) if marks[s] < 95 else marks[s] - 4
            problems.append(f"mark_mismatch:{s}")
        elif scn == "missing_subject":
            omit = rng.choice(SUBJECTS)
            sheet_total -= marks[omit]
            problems.append(f"missing_subject:{omit}")
        elif scn == "reg_mismatch":
            entered["register_no"] = str(int(reg) + rng.choice([111, 4000, 50]))
            problems.append("reg_mismatch")
        elif scn == "bad_total":
            sheet_total += rng.choice([-10, 10, 15])
            problems.append("bad_total")
        if pscn != "good":
            problems.append(f"photo:{pscn}")
        img = render_sheet(layout, name, reg, marks, sheet_total, omit)
        (out / "sheets" / f"{cid}.jpg").write_bytes(degrade(img, rng, level))
        pb, ext = make_photo(rng, pscn)
        (out / "photos" / f"{cid}.{ext}").write_bytes(pb)
        manifest.append({"case_id": cid, "marksheet": f"sheets/{cid}.jpg", "photo": f"photos/{cid}.{ext}",
                         "entered": entered,
                         "truth": {"sheet_marks": {s: m for s, m in marks.items() if s != omit},
                                   "sheet_total": sheet_total, "layout": layout, "degradation": level,
                                   "sheet_scenario": scn, "photo_scenario": pscn, "problems": problems}})
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"Wrote {len(manifest)} synthetic cases to {out}/")


if __name__ == "__main__":
    main()

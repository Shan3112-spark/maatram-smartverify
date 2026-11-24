# Smart Admission Document Validation (MH26-01)
Maatram HackForge 2026-27 · Software · Theme: Maatram Community

Cross-checks the marks a student **typed** against the uploaded **mark sheet**, and checks whether the
**profile photo** meets measurable quality rules. Traditional methods only (OpenCV, Tesseract OCR, Pillow,
fuzzy matching, rules). **No generative AI / LLM** is used, as the problem statement requires.
All test documents are **synthetic**; no real student data was used.

## Run it
```bash
sudo apt install tesseract-ocr          # the OCR engine (macOS: brew install tesseract)
pip install -r requirements.txt
python generate_synthetic.py --n 36 --out samples   # (samples/ already included)
streamlit run app.py                    # demo UI
python evaluate.py                      # accuracy report -> results/
python -m pytest tests                  # unit tests
```

## How it works
```
mark sheet ─> flatten lighting ─> denoise ─> binarise ─> deskew ─> remove table lines ─> Tesseract
          ─> group words into rows ─> fuzzy-match subject names ─> read Max / Obtained numbers
          ─> repair OCR digit confusions (O→0, l→1, S→5 ...) and LOWER the confidence when repaired
typed form + extracted values ─> comparator ─> per-field PASS / FAIL / REVIEW
photo ─> format, size, resolution, aspect ratio, orientation (EXIF-aware), brightness, contrast, sharpness
all checks ─> report (Entered vs Uploaded table) + manual-review queue
```

**Key design choice: confidence-aware decisions.** A difference is only called a **Mismatch** when OCR is
confident (≥ 75% by default). If OCR itself is unsure, or a digit had to be "repaired", the field goes to
**Needs review** instead. This keeps wrong confident verdicts at zero and sends doubtful cases to a human.

Checks performed: per-subject marks · mark sheet completeness · total = sum of subjects (internal
consistency) · register number · student name · 8 photo checks. Unreadable files never crash the run;
they are routed to review.

## Results on the synthetic set (36 applications, 4 scan-quality levels, 3 sheet layouts)
| Metric | Result |
|---|---|
| OCR field accuracy (marks read exactly) | 98.1% (clean 100%, mild 98.8%, moderate 100%, hard 75%*) |
| Applications with a planted problem that were flagged | 100% |
| Problem cases silently auto-passed | 0 |
| Confident-but-wrong OCR reads | 0 |
| Bad photos rejected / good photos wrongly rejected | 100% / 0 |
| Clean applications sent to review (false alarms) | 1 of 14 (a very noisy "hard" scan) |
| Average time per application | ~2.8 s |

\*Only 2 "hard" sheets in this sample, so treat that figure as indicative, not statistical.

## Honest limitations (say these to the judges before they ask)
- Tested on **synthetic** sheets we generated, in 3 layouts. Real board mark sheets differ; the row parser
  needs a layout check on real (consented) samples before deployment.
- Thresholds (photo size, sharpness, brightness, OCR confidence) are **defaults to be calibrated** on the
  organisation's real photos. Sharpness via Laplacian variance is sensitive to sensor noise.
- English OCR only (`eng`). Tamil-script subject names would need the `tam` language pack.
- Photo checks are measurable properties only; there is **no face detection** (possible extension).
- The demo shows a decision-support queue, not an automatic admission decision: a human makes the final call.

## Project map
`validator/` core library · `app.py` Streamlit UI · `generate_synthetic.py` test data with ground truth ·
`evaluate.py` accuracy report · `tests/` · `samples/` · `results/`

# SmartVerify

**Admission document verification for Maatram HackForge 2026-27 (problem statement MH26-01).**

Students submit an application form, a mark sheet and a profile photo. SmartVerify reads the mark sheet with OCR, compares it with the marks the student typed, checks the photo quality, and sends anything doubtful to a verifier who makes the final decision. It uses classical image processing and rules. **No generative AI or LLM is used.**

## Features

**Sign-in and roles**
- Separate **Student sign in** and **Admin sign in**, plus student sign-up
- The role comes from the database, so a student account cannot open the admin portal

**Student portal**
- "Before you apply" guide: how to fill each field, do's and don'ts, photo rules
- Form with Tamil, English, Maths, Science and Social Science, plus **➕ Add another course** for any extra course on the mark sheet
- Instant result with a check table (Entered vs Uploaded) and a status page
- Can correct and resubmit until approved

**Verification engine**
- Mark sheet cleaning (lighting, noise, tilt, table lines) and Tesseract OCR
- Per-subject comparison, mark sheet completeness, total consistency, register number and name
- **Not case sensitive**: names, register numbers, subject and course names
- Confidence-aware decisions: a difference is called a *Mismatch* only when OCR is confident; otherwise it goes to *Needs review*
- Photo checks: format, file size, resolution, aspect ratio, orientation, brightness, contrast, sharpness

**Admin (verifier) portal**
- Dashboard with counts by status and a filter
- Review panel: validation report, exception reasons, photo and mark sheet side by side, OCR text
- Decision: Approve, Reject or Request resubmission, with a note for the student
- Audit log of every decision

**Data**
- SQLite validation database: users, applications, validation results and decisions
- Passwords stored as salted PBKDF2 hashes

## Flow

```
Login -> Role authentication
   |-- Student portal: Application form -> Document upload -> OCR engine -> Image analyzer -> Mark comparison
   |-- Admin portal:   Application dashboard -> Select applicant -> Review panel -> Validation report -> Verifier decision
                          \                         /
                           Validation database -> Application status
```

## Setup

You need **Python 3.12+** and **Tesseract OCR** (a separate program, not a pip package).

1. Install Tesseract. Windows: the UB Mannheim installer, and add `C:\Program Files\Tesseract-OCR` to your PATH. macOS: `brew install tesseract`. Linux: `sudo apt install tesseract-ocr`.
2. Install the Python packages:
   ```
   pip install -r requirements.txt
   ```
3. Start the app:
   ```
   streamlit run smartverify.py
   ```
   On Windows use `py -m pip install -r requirements.txt` and `py -m streamlit run smartverify.py`.

The Maatram theme (yellow, white, black) comes from `.streamlit/config.toml`, so keep that folder.

**First admin login:** `admin` / `admin123`. **Change this before any real use.** Students create their own accounts on the sign-up tab. The database file `smartverify.db` is created automatically on first run.

## Try it with dummy data

1. Sign up as a student and open **Application form**.
2. Enter: name `Shan`, register number `2612345`, marks Tamil 92, English 92, Maths 100, Science 99, Social Science 98.
3. Upload a dummy mark sheet with those values and a portrait passport-style photo (about 3:4, bright and sharp).
4. Submit. Then sign in as admin to review the application and record a decision.

To test the checker, change one mark. You should see a **Mismatch** for that subject.

## Photo rules

| Rule | Accepted |
|---|---|
| Format | JPG or PNG |
| File size | 20 KB to 1 MB |
| Size in pixels | 300 x 400 to 4000 x 5000 |
| Shape | Portrait, width/height between 0.70 and 0.85 (about 3:4) |
| Light and clarity | Brightness 70-200, contrast and sharpness above minimum |

All thresholds are in `validator/config.py`.

## Results on synthetic data

Tested on 36 synthetic applications (mixed scan quality, three sheet layouts, planted errors, mixed capital and small letters, extra courses):

| Metric | Result |
|---|---|
| Mark fields read exactly by OCR | 96.8% |
| Applications with a planted problem that were flagged | 100% (none passed silently) |
| Confident but wrong OCR reads | 0 |
| Bad photos rejected / good photos wrongly rejected | 100% / 0 |
| Average time per application | about 3 seconds |

Reproduce with `python generate_synthetic.py --n 36 --out samples` and then `python evaluate.py`.

## Project structure

```
smartverify.py        Streamlit web app (login, student portal, admin portal)
sv_db.py              SQLite database and authentication
validator/            Verification engine
  config.py             subjects, aliases and all thresholds
  marksheet_extractor.py  image cleaning, OCR, parsing
  comparator.py         entered values vs OCR values
  photo_validator.py    photo quality checks
  pipeline.py           runs the stages and builds the report
tests/                Unit tests
generate_synthetic.py Synthetic mark sheets and photos with ground truth
evaluate.py           Accuracy report
.streamlit/           Maatram theme
```

Run the tests with `python -m pytest tests`. One test needs the sample data, so run `generate_synthetic.py` first.

## Limitations

- Tested on synthetic mark sheets. Real board mark sheets may need parsing adjustments.
- Photo thresholds are defaults and should be tuned on real photos.
- English OCR only. Tamil-script text would need the `tam` Tesseract language pack.
- The login lockout resets when the page reloads, so it is not real brute-force protection.
- A prototype: it supports a human verifier and does not replace one.

## Privacy

Use only synthetic or consented data. Do not commit real students' documents or the `smartverify.db` file.

## License

MIT. See [LICENSE](LICENSE).

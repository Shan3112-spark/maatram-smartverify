"""Streamlit demo:  streamlit run app.py"""
import json
from pathlib import Path

import pandas as pd
import streamlit as st

from validator import MarkRules, PhotoRules, validate_application
from validator.models import LABELS

SAMPLES = Path(__file__).parent / "samples"
SUBJECTS = ["Tamil", "English", "Mathematics", "Physics", "Chemistry", "Computer Science"]

st.set_page_config(page_title="Admission Document Validator", layout="wide")
st.markdown("""<style>
.banner{padding:14px 18px;border-radius:8px;font-size:1.15rem;font-weight:600;margin:6px 0 14px}
.PASS{background:#e6f4ea;color:#14532d}.FAIL{background:#fde8e8;color:#7f1d1d}.REVIEW{background:#fff4d6;color:#7a4b00}
</style>""", unsafe_allow_html=True)
st.title("Smart Admission Document Validation")
st.caption("MH26-01 · Maatram HackForge 2026-27 · rule-based checks: OCR + image processing, no generative AI. "
           "Synthetic documents only.")

manifest = {}
if (SAMPLES / "manifest.json").exists():
    manifest = {c["case_id"]: c for c in json.loads((SAMPLES / "manifest.json").read_text())}

with st.sidebar:
    st.header("Rules (editable)")
    pr, mr = PhotoRules(), MarkRules()
    pr.min_width = st.number_input("Photo min width (px)", 100, 2000, pr.min_width)
    pr.min_height = st.number_input("Photo min height (px)", 100, 2000, pr.min_height)
    pr.min_sharpness = st.slider("Min sharpness", 0, 300, int(pr.min_sharpness))
    mr.low_conf_threshold = st.slider("OCR confidence needed to call a mismatch", 30, 99, int(mr.low_conf_threshold))
    st.caption("Below this confidence a difference goes to manual review instead of being called a mismatch.")


def show_report(rep, ex, sheet_bytes, photo_bytes):
    st.markdown(f'<div class="banner {rep.overall}">{LABELS[rep.overall]} Overall: '
                f'{ {"PASS": "All checks passed", "FAIL": "Discrepancy found: send to exception queue", "REVIEW": "Needs manual review"}[rep.overall] }</div>',
                unsafe_allow_html=True)
    df = pd.DataFrame([{"Validation": c.name, "Result": f"{LABELS[c.status]} {c.label}",
                        "Entered": c.entered or "", "Uploaded": c.uploaded or "",
                        "Details": c.details} for c in rep.checks])
    st.dataframe(df, hide_index=True, width="stretch")
    c1, c2 = st.columns([2, 1])
    c1.image(sheet_bytes, caption="Uploaded mark sheet", width="stretch")
    c2.image(photo_bytes, caption="Uploaded photo", width="stretch")
    if ex:
        with st.expander("What the OCR read (for the reviewer)"):
            st.code("\n".join(ex.lines))
    st.download_button("Download report (JSON)", json.dumps(rep.to_dict(), indent=2),
                       file_name=f"{rep.application_id}_validation.json")


tab1, tab2 = st.tabs(["Check one application", "Batch + exception queue"])

with tab1:
    src = st.radio("Input", ["Synthetic sample", "Upload my own"], horizontal=True)
    entered, sheet_bytes, photo_bytes, app_id = None, None, None, "APP-UPLOAD"
    if src == "Synthetic sample" and manifest:
        cid = st.selectbox("Sample application", list(manifest),
                           format_func=lambda k: f"{k}  ({', '.join(manifest[k]['truth']['problems']) or 'no planted problem'})")
        c = manifest[cid]
        entered, app_id = c["entered"], cid
        sheet_bytes, photo_bytes = (SAMPLES / c["marksheet"]).read_bytes(), (SAMPLES / c["photo"]).read_bytes()
        st.write("**Form data the student typed**", {"name": entered["name"], "register_no": entered["register_no"],
                                                     **entered["marks"]})
    elif src == "Upload my own":
        a, b = st.columns(2)
        up_sheet = a.file_uploader("Mark sheet image", type=["jpg", "jpeg", "png"])
        up_photo = b.file_uploader("Profile photo", type=["jpg", "jpeg", "png", "bmp", "gif", "webp"])
        name = st.text_input("Name")
        reg = st.text_input("Register number")
        cols = st.columns(3)
        marks = {s: cols[i % 3].number_input(s, 0, 100, 0, key=f"m_{s}") for i, s in enumerate(SUBJECTS)}
        entered = {"name": name, "register_no": reg, "marks": marks}
        if up_sheet and up_photo:
            sheet_bytes, photo_bytes = up_sheet.getvalue(), up_photo.getvalue()
    if st.button("Validate", type="primary", disabled=not (entered and sheet_bytes and photo_bytes)):
        with st.spinner("Reading the mark sheet..."):
            rep, ex = validate_application(app_id, entered, sheet_bytes, photo_bytes, mr, pr)
        show_report(rep, ex, sheet_bytes, photo_bytes)

with tab2:
    st.write("Runs every sample application and lists the ones a human must look at.")
    if manifest and st.button("Run batch on all samples"):
        rows, bar = [], st.progress(0.0)
        for i, (cid, c) in enumerate(manifest.items()):
            rep, _ = validate_application(cid, c["entered"], (SAMPLES / c["marksheet"]).read_bytes(),
                                          (SAMPLES / c["photo"]).read_bytes(), mr, pr)
            rows.append({"Application": cid, "Status": f"{LABELS[rep.overall]} {rep.overall}",
                         "Why": "; ".join(rep.reasons) or "-",
                         "Planted problem": ", ".join(c["truth"]["problems"]) or "-"})
            bar.progress((i + 1) / len(manifest))
        df = pd.DataFrame(rows)
        st.metric("Auto-passed", int((df["Status"].str.contains("PASS")).sum()), f"of {len(df)}")
        st.subheader("Manual-review queue")
        st.dataframe(df[~df["Status"].str.contains("PASS")], hide_index=True, width="stretch")
        st.download_button("Download queue (CSV)", df.to_csv(index=False), file_name="exception_queue.csv")
    elif (Path(__file__).parent / "results" / "summary.json").exists():
        st.info("Saved evaluation from `python evaluate.py`:")
        st.json(json.loads((Path(__file__).parent / "results" / "summary.json").read_text()))

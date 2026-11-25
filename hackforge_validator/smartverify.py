"""SmartVerify (Maatram theme): login -> role -> Student portal / Admin portal -> database -> status.
Run:  py -m streamlit run smartverify.py      (needs .streamlit/config.toml for the yellow/white/black theme)
"""
import json, time

import pandas as pd
import streamlit as st

import sv_db as db
from validator import validate_application
from validator.config import CORE_SUBJECTS, canonical_subject
from validator.models import LABELS

CORE = list(CORE_SUBJECTS)                       # Tamil, English, Mathematics, Science, Social Science
SUBJECT_LABEL = {"Mathematics": "Maths"}
MAX_EXTRA = 6
MAX_UPLOAD = 8 * 1024 * 1024
STATUS_LABEL = {db.AUTO_PASSED: "✅ Passed checks", db.NEEDS_REVIEW: "⚠️ Needs review", db.FLAGGED: "❌ Flagged",
                db.APPROVED: "🟢 Approved", db.REJECTED: "🔴 Rejected", db.RESUBMIT: "🔁 Resubmission requested"}
STUDENT_TEXT = {
    db.AUTO_PASSED: "Your documents passed the automatic checks. A verifier will confirm your application.",
    db.NEEDS_REVIEW: "Some points need a human look. A verifier will review them; you don't need to do anything yet.",
    db.FLAGGED: "We found differences between your form and your documents. Check the details below. "
                "You can correct and resubmit. This is not a rejection: a verifier makes the final decision.",
    db.APPROVED: "Your application has been approved.",
    db.REJECTED: "Your application was not approved. See the verifier's note below.",
    db.RESUBMIT: "The verifier asked you to correct something and submit again. See the note below."}

st.set_page_config(page_title="SmartVerify · Maatram", page_icon="✅", layout="wide")
st.markdown("""<style>
:root{--mt-yellow:#FFC20E;--mt-black:#111;}
.block-container{padding-top:1.4rem;max-width:1200px}
.mt-header{background:#000;border-bottom:6px solid var(--mt-yellow);border-radius:10px;padding:16px 24px;
  display:flex;align-items:baseline;gap:14px;margin-bottom:22px;flex-wrap:wrap}
.mt-brand{color:var(--mt-yellow);font-weight:800;font-size:1.7rem;letter-spacing:.5px}
.mt-app{color:#fff;font-weight:600;font-size:1.2rem}
.mt-sub{color:#ccc;font-size:.88rem;margin-left:auto}
h1,h2,h3,h4{color:#000!important}
h1{border-left:8px solid var(--mt-yellow);padding-left:12px}
button[kind="primary"],button[kind="primaryFormSubmit"]{background:var(--mt-yellow)!important;color:#000!important;
  border:2px solid #000!important;font-weight:700!important}
button[kind="primary"]:hover,button[kind="primaryFormSubmit"]:hover{background:#000!important;color:var(--mt-yellow)!important}
button[kind="secondary"]{border:2px solid #000!important;color:#000!important;font-weight:600!important}
.stTabs [data-baseweb="tab"]{font-weight:600;color:#333}
.stTabs [aria-selected="true"]{color:#000!important}
.stTabs [data-baseweb="tab-highlight"]{background-color:var(--mt-yellow)!important;height:4px}
[data-testid="stMetric"]{background:#FFF8DC;border-left:6px solid var(--mt-yellow);padding:10px 14px;border-radius:6px}
[data-testid="stSidebar"]{background:#000}
[data-testid="stSidebar"] *{color:#fff}
[data-testid="stSidebar"] button{background:var(--mt-yellow)!important;border:0!important}
[data-testid="stSidebar"] button *{color:#000!important;font-weight:700}
.banner{padding:14px 18px;border-radius:8px;font-size:1.1rem;font-weight:600;margin:6px 0 14px;border:1px solid rgba(0,0,0,.15)}
.PASS{background:#e6f4ea;color:#14532d}.FAIL{background:#fde8e8;color:#7f1d1d}.REVIEW{background:#fff4d6;color:#7a4b00}
.card{border:1px solid #e5e5e5;border-left:8px solid #000;border-radius:8px;padding:14px 18px;background:#fff;height:100%}
.card.do{border-left-color:#16a34a}.card.dont{border-left-color:#dc2626}.card.tip{border-left-color:var(--mt-yellow);background:#FFFBEA}
.card h4{margin:0 0 8px 0}.card ul{margin:0;padding-left:20px}.card li{margin:5px 0;color:#111}
.step{display:flex;gap:12px;align-items:flex-start;margin:8px 0;color:#111}
.step b.n{background:var(--mt-yellow);color:#000;border:2px solid #000;border-radius:50%;min-width:30px;height:30px;
  display:inline-flex;align-items:center;justify-content:center}
</style>""", unsafe_allow_html=True)
db.init_db()
ss = st.session_state
ss.setdefault("user", None)
ss.setdefault("fails", 0)


def fmt_time(t):
    return time.strftime("%d %b %Y, %H:%M", time.localtime(t))


def header(sub=""):
    st.markdown(f'<div class="mt-header"><span class="mt-brand">maatram</span><span class="mt-app">SmartVerify</span>'
                f'<span class="mt-sub">{sub}</span></div>', unsafe_allow_html=True)


def banner(overall):
    text = {"PASS": "All checks passed", "FAIL": "Discrepancy found", "REVIEW": "Needs manual review"}[overall]
    st.markdown(f'<div class="banner {overall}">{LABELS[overall]} {text}</div>', unsafe_allow_html=True)


def checks_table(report):
    df = pd.DataFrame([{"Validation": c["name"], "Result": f'{LABELS[c["status"]]} {c["label"]}',
                        "Entered": c["entered"] or "", "Uploaded": c["uploaded"] or "", "Details": c["details"]}
                       for c in report["checks"]])
    st.dataframe(df, hide_index=True, width="stretch")


def card(kind, title, items):
    li = "".join(f"<li>{i}</li>" for i in items)
    st.markdown(f'<div class="card {kind}"><h4>{title}</h4><ul>{li}</ul></div>', unsafe_allow_html=True)


def steps(items):
    html = "".join(f'<div class="step"><b class="n">{i}</b><div>{t}</div></div>' for i, t in enumerate(items, 1))
    st.markdown(html, unsafe_allow_html=True)


def logout():
    for k in list(ss.keys()):
        if k.startswith("f_") or k in ("user", "last_report"):
            del ss[k]
    ss["user"] = None


# =============================================================== 1. LOGIN + ROLE AUTHENTICATION
def sign_in_form(kind, other):
    """kind = 'student' or 'admin'. The role is read from the database, never chosen by the user."""
    with st.form(f"login_{kind}"):
        u = st.text_input("Username", key=f"{kind}_user")
        p = st.text_input("Password", type="password", key=f"{kind}_pw")
        go = st.form_submit_button(f"Sign in as {kind}", type="primary")
    if not go:
        return
    if ss.fails >= 5:
        st.error("Too many failed attempts. Reload the page to try again.")
        return
    user = db.authenticate(u, p)
    if user is None:
        ss.fails += 1
        st.error("Wrong username or password")
    elif user["role"] != kind:
        st.error(f"This is not {'an' if kind == 'admin' else 'a'} {kind} account. "
                 f"Please use the {other.capitalize()} sign-in tab.")
    else:
        ss.fails, ss.user = 0, user
        st.rerun()


def login_page():
    header("Admission document verification")
    t_stu, t_adm, t_new = st.tabs(["🎓 Student sign in", "🛡️ Admin sign in", "New student? Sign up"])
    with t_stu:
        sign_in_form("student", "admin")
    with t_adm:
        sign_in_form("admin", "student")
        st.caption("Admin accounts are created by the Maatram office team.")
    with t_new:
        with st.form("signup"):
            n = st.text_input("Full name")
            un = st.text_input("Choose a username")
            pw = st.text_input("Choose a password (6+ characters)", type="password")
            ok = st.form_submit_button("Create student account", type="primary")
        if ok:
            try:
                db.create_user(un, pw, n, "student")      # role is always 'student' here
                st.success("Account created. Go to the Student sign in tab.")
            except ValueError as e:
                st.error(str(e))


# =============================================================== 2a. STUDENT PORTAL
def guidelines_tab():
    st.subheader("Read this before you apply")
    st.write("Applying takes about 5 minutes. Keep your **mark sheet** and a **passport-style photo** ready. "
             "Our system reads your mark sheet and compares it with the marks you type, so small mistakes "
             "can delay your application.")

    st.markdown("#### How to apply")
    steps(["Open the <b>Application form</b> tab.",
           "Type your <b>name</b> and <b>register number</b> as printed on your mark sheet.",
           "Type the <b>marks you obtained</b> in Tamil, English, Maths, Science and Social Science (not the maximum marks).",
           "If your mark sheet has <b>more courses</b>, press <b>➕ Add another course</b> and enter its name and marks.",
           "Upload a clear picture of your <b>mark sheet</b> and your <b>profile photo</b>.",
           "Tick the confirmation box and press <b>Submit for verification</b>. You get an instant check result.",
           "Open <b>My application status</b> to follow it. A verifier makes the final decision."])

    st.markdown("#### How to fill each field")
    st.table(pd.DataFrame([
        ["Full name", "As on the mark sheet: same spelling and same order of names. Capital or small letters both work", "Priya Kumar"],
        ["Register number", "The number next to “Register No”. Capital or small letters both work", "2612345"],
        ["Subject marks", "Marks obtained (not the maximum) for Tamil, English, Maths, Science and Social Science. Do not round or estimate", "88"],
        ["Additional course", "Press ➕ for each extra course printed on your sheet. Type its name as printed. Capital or small letters both work", "Computer Science, 91"],
        ["Mark sheet", "Photo or scan of the whole sheet, JPG or PNG, under 8 MB", "mark_sheet.jpg"],
        ["Profile photo", "Passport-style, portrait, face centred, JPG or PNG", "photo.jpg"]],
        columns=["Field", "What to enter", "Example"]).set_index("Field"))

    c1, c2 = st.columns(2)
    with c1:
        card("do", "✅ Do", [
            "Keep your <b>mark sheet in front of you</b> and copy marks and numbers from it.",
            "Add <b>every extra course</b> that is printed on your mark sheet using ➕.",
            "Take the mark sheet photo in <b>daylight</b>, flat on a table, with all four corners visible.",
            "Make sure <b>name, register number, every subject and the total</b> are readable.",
            "Use a <b>plain, light background</b> for your photo and look straight at the camera.",
            "Check your photo is <b>bright and sharp</b>, not dark or blurry.",
            "Re-check every number before you press Submit.",
            "If the result says “Flagged” or “Needs review”, read the reasons and fix them."])
    with c2:
        card("dont", "❌ Don't", [
            "Don't type marks from <b>memory</b> or guess them.",
            "Don't leave out a course that is <b>printed on your mark sheet</b>.",
            "Don't <b>edit, crop or filter</b> your mark sheet or photo.",
            "Don't upload <b>someone else's</b> documents or photo.",
            "Don't take the photo in a <b>dark room</b>, with glare, shadows or fingers over the text.",
            "Don't use a <b>selfie with filters</b>, sunglasses or a cap.",
            "Don't upload a <b>screenshot or a PDF</b>. Upload an image (JPG or PNG).",
            "Don't share your password with anyone."])

    st.markdown("#### Photo requirements at a glance")
    st.table(pd.DataFrame([
        ["Format", "JPG or PNG"], ["File size", "20 KB to 1 MB"],
        ["Size in pixels", "At least 300 × 400, at most 4000 × 5000"],
        ["Shape", "Portrait, about 3:4 (width divided by height between 0.70 and 0.85)"],
        ["Light and clarity", "Bright enough, good contrast, sharp (not blurry)"]],
        columns=["Rule", "Accepted"]).set_index("Rule"))
    card("tip", "💡 Good to know", [
        "A <b>“Flagged”</b> result is <b>not a rejection</b>. It means something doesn't match, so you can fix it and resubmit.",
        "<b>“Needs review”</b> means our reader wasn't sure, often because the picture isn't clear. A verifier will look, "
        "or you can retake a clearer picture and resubmit.",
        "You can resubmit any time before approval. Your latest submission replaces the old one.",
        "Capital and small letters never matter, in names, register numbers or course names.",
        "Your documents are used only for verifying your application."])


def init_form(existing, user):
    """Fill the form once per saved version, including any extra courses saved earlier."""
    for k in [k for k in ss.keys() if k.startswith("f_x_")]:
        del ss[k]
    marks = json.loads(existing["marks_json"]) if existing else {}
    ss["f_name"] = existing["name"] if existing else user["full_name"]
    ss["f_reg"] = existing["register_no"] if existing else ""
    for s in CORE:
        ss[f"f_m_{s}"] = int(marks.get(s, 0))
    extras = [(k, v) for k, v in marks.items() if k not in CORE]
    ss["f_extra_n"] = len(extras)
    for i, (k, v) in enumerate(extras):
        ss[f"f_x_name_{i}"], ss[f"f_x_mark_{i}"] = k, int(v)


def add_extra():
    i = ss["f_extra_n"]
    if i < MAX_EXTRA:
        ss[f"f_x_name_{i}"], ss[f"f_x_mark_{i}"], ss["f_extra_n"] = "", 0, i + 1


def remove_extra():
    i = ss["f_extra_n"] - 1
    if i >= 0:
        ss.pop(f"f_x_name_{i}", None); ss.pop(f"f_x_mark_{i}", None)
        ss["f_extra_n"] = i


def collect_marks():
    """-> (marks dict keyed by canonical subject name, error message or None)"""
    marks = {s: int(ss[f"f_m_{s}"]) for s in CORE}
    for i in range(ss["f_extra_n"]):
        raw = ss[f"f_x_name_{i}"].strip()
        if not any(ch.isalpha() for ch in raw):
            return None, f"Enter a name for additional course {i + 1}, or remove it with ➖."
        name = canonical_subject(raw)
        if name in marks:
            return None, f"'{raw}' is already on the form. Each course can be added only once."
        marks[name] = int(ss[f"f_x_mark_{i}"])
    return marks, None


def student_portal(user):
    existing = db.get_application_by_student(user["id"])
    init_key = (user["id"], existing["version"] if existing else 0)
    if ss.get("f_init") != init_key:
        init_form(existing, user)
        ss["f_init"] = init_key

    header("Student portal")
    t_guide, t_form, t_status = st.tabs(["📋 Before you apply", "✏️ Application form", "📌 My application status"])
    with t_guide:
        guidelines_tab()

    with t_form:
        locked = existing is not None and existing["status"] == db.APPROVED
        if locked:
            st.success("Your application is approved. No further changes are needed.")
        st.info("First time here? Read the **Before you apply** tab. It explains what to enter and what to avoid.")
        st.subheader("1. Application form")
        c1, c2 = st.columns(2)
        c1.text_input("Full name (as on mark sheet)", key="f_name")
        c2.text_input("Register number", key="f_reg")
        st.caption("Enter the marks you OBTAINED in each subject, copied from your mark sheet. "
                   "Capital or small letters don't matter.")
        cols = st.columns(3)
        for i, s in enumerate(CORE):
            cols[i % 3].number_input(f"{SUBJECT_LABEL.get(s, s)} marks", 0, 100, key=f"f_m_{s}")

        st.markdown("**Additional courses** (only if they are printed on your mark sheet)")
        for i in range(ss["f_extra_n"]):
            a, b = st.columns([3, 1])
            a.text_input(f"Course {i + 1} name", key=f"f_x_name_{i}", placeholder="e.g. Computer Science")
            b.number_input("Marks", 0, 100, key=f"f_x_mark_{i}")
        b1, b2, _ = st.columns([1.3, 1, 3])
        b1.button("➕ Add another course", on_click=add_extra, disabled=locked or ss["f_extra_n"] >= MAX_EXTRA)
        b2.button("➖ Remove last", on_click=remove_extra, disabled=ss["f_extra_n"] == 0)

        st.subheader("2. Document upload")
        u1, u2 = st.columns(2)
        up = ss.get("f_up", 0)
        f_sheet = u1.file_uploader("Mark sheet (JPG or PNG)", type=["jpg", "jpeg", "png"], key=f"f_sheet_{up}",
                                   help="Whole sheet visible, in daylight, flat, all text readable.")
        f_photo = u2.file_uploader("Profile photo (JPG or PNG)", type=["jpg", "jpeg", "png"], key=f"f_photo_{up}",
                                   help="Passport-style, portrait, plain background, bright and sharp.")
        agree = st.checkbox("I have read the guidelines. The details I entered match my documents, "
                            "and the documents are my own.", key="f_agree")
        submitted = st.button("Submit for verification", type="primary", disabled=locked)

        if submitted:
            sheet = f_sheet.getvalue() if f_sheet else None
            photo = f_photo.getvalue() if f_photo else None
            marks, err = collect_marks()
            if not ss["f_name"].strip() or not ss["f_reg"].strip():
                st.error("Enter your name and register number.")
            elif err:
                st.error(err)
            elif sheet is None or photo is None:
                st.error("Upload both the mark sheet and the profile photo.")
            elif len(sheet) > MAX_UPLOAD or len(photo) > MAX_UPLOAD:
                st.error("Each file must be under 8 MB.")
            elif not agree:
                st.error("Please tick the confirmation box before submitting.")
            else:
                entered = {"name": ss["f_name"].strip(), "register_no": ss["f_reg"].strip(), "marks": marks}
                with st.status("Verifying your documents...", expanded=True) as stat:
                    rep, ex = validate_application(f"APP-{user['id']}", entered, sheet, photo,
                                                   on_stage=lambda m: st.write(m))
                    app_id, ver = db.save_application(user["id"], entered["name"], entered["register_no"], marks,
                                                      sheet, photo, db.STATUS_FROM_OVERALL[rep.overall])
                    db.add_validation(app_id, ver, rep, ex)
                    stat.update(label="Verification complete", state="complete")
                ss["f_init"] = (user["id"], ver)       # keep the form as the student typed it
                ss["f_up"] = up + 1                     # empty the upload boxes for a possible resubmission
                ss["last_report"] = rep.to_dict()
                banner(rep.overall)
                checks_table(rep.to_dict())
                st.info("Saved. Open 'My application status' to follow it.")

    with t_status:
        app = db.get_application_by_student(user["id"])
        if app is None:
            st.info("You haven't submitted an application yet.")
            return
        st.subheader(STATUS_LABEL[app["status"]])
        st.write(STUDENT_TEXT[app["status"]])
        st.caption(f"Submission #{app['version']} · {fmt_time(app['submitted_at'])}")
        decisions = db.list_decisions(app["id"])
        if decisions:
            d = decisions[0]
            st.write(f"**Verifier decision:** {d['decision']}" + (f" — {d['note']}" if d["note"] else ""))
        v = db.latest_validation(app["id"])
        if v:
            st.markdown("**Automatic check results**")
            banner(v["overall"])
            checks_table(v["report"])


# =============================================================== 2b. ADMIN PORTAL
def admin_portal(user):
    if user["role"] != "admin":                              # server-side role guard
        st.error("Not allowed")
        return
    header("Verifier portal")
    apps = db.list_applications()
    # ---- application dashboard
    counts = {k: sum(a["status"] == k for a in apps) for k in STATUS_LABEL}
    m = st.columns(7)
    m[0].metric("Applications", len(apps))
    for col, k in zip(m[1:], STATUS_LABEL):
        col.metric(STATUS_LABEL[k].split(" ", 1)[1], counts[k])
    if not apps:
        st.info("No applications yet. They appear here as soon as students submit from their portal.")
        return
    flt = st.multiselect("Filter by status", list(STATUS_LABEL), format_func=lambda k: STATUS_LABEL[k])
    shown = [a for a in apps if not flt or a["status"] in flt]
    if not shown:
        st.warning("No applications match this filter.")
        return
    st.dataframe(pd.DataFrame([{"ID": a["id"], "Name": a["name"], "Register no.": a["register_no"],
                                "Status": STATUS_LABEL[a["status"]], "Submission": a["version"],
                                "Submitted": fmt_time(a["submitted_at"])} for a in shown]),
                 hide_index=True, width="stretch")

    # ---- select applicant -> review panel
    st.divider()
    pick = st.selectbox("Select applicant", [a["id"] for a in shown],
                        format_func=lambda i: next(f"#{a['id']} · {a['name']} · {STATUS_LABEL[a['status']]}"
                                                   for a in shown if a["id"] == i))
    app, val = db.get_application(pick), db.latest_validation(pick)
    st.header(f"Review panel: {app['name']}")
    c1, c2 = st.columns([2, 1])
    with c1:
        st.subheader("Validation report")
        if val:
            banner(val["overall"])
            checks_table(val["report"])
            if val["report"]["reasons"]:
                st.markdown("**Exception reasons**")
                st.markdown("\n".join(f"- {r}" for r in val["report"]["reasons"]))
            with st.expander("What the OCR read"):
                st.code(val["ocr_text"] or "(nothing read)")
    with c2:
        st.image(app["photo"], caption="Profile photo", width="stretch")
    st.image(app["sheet"], caption="Uploaded mark sheet", width="stretch")

    # ---- verifier decision
    st.subheader("Verifier decision")
    for d in db.list_decisions(pick):
        st.caption(f"{fmt_time(d['decided_at'])} · {d['verifier']} · {d['decision']}" + (f" · {d['note']}" if d["note"] else ""))
    with st.form("decision"):
        choice = st.radio("Decision", ["Approve", "Reject", "Request resubmission"], horizontal=True)
        note = st.text_area("Note to the student (required for reject / resubmission)")
        go = st.form_submit_button("Record decision", type="primary")
    if go:
        if choice != "Approve" and not note.strip():
            st.error("Add a short note so the student knows why.")
        else:
            db.add_decision(pick, user["id"], choice, note)
            st.success(f"Recorded: {choice}")
            st.rerun()

    with st.expander("Audit log (all decisions)"):
        log = db.list_decisions()
        st.dataframe(pd.DataFrame(log) if log else pd.DataFrame(columns=["app_id", "verifier", "decision"]),
                     hide_index=True, width="stretch")


# =============================================================== ROUTER
user = ss.user
if user is None:
    login_page()
else:
    with st.sidebar:
        st.markdown("### maatram · SmartVerify")
        st.write(f"{user['full_name']}  \n`{user['role']}`")
        st.button("Log out", on_click=logout)
    (admin_portal if user["role"] == "admin" else student_portal)(user)

"""SmartVerify: validation database (SQLite) + role-based login."""
import hashlib, hmac, json, os, secrets, sqlite3, time
from pathlib import Path

DB_PATH = Path(os.environ.get("SMARTVERIFY_DB", Path(__file__).parent / "smartverify.db"))

AUTO_PASSED, NEEDS_REVIEW, FLAGGED = "AUTO_PASSED", "NEEDS_REVIEW", "FLAGGED"
APPROVED, REJECTED, RESUBMIT = "APPROVED", "REJECTED", "RESUBMIT"
STATUS_FROM_OVERALL = {"PASS": AUTO_PASSED, "REVIEW": NEEDS_REVIEW, "FAIL": FLAGGED}
STATUS_FROM_DECISION = {"Approve": APPROVED, "Reject": REJECTED, "Request resubmission": RESUBMIT}

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, full_name TEXT NOT NULL,
  role TEXT NOT NULL CHECK(role IN ('student','admin')), salt BLOB NOT NULL, pw_hash BLOB NOT NULL,
  created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS applications(
  id INTEGER PRIMARY KEY, student_id INTEGER UNIQUE NOT NULL REFERENCES users(id),
  name TEXT, register_no TEXT, marks_json TEXT, sheet BLOB, photo BLOB,
  status TEXT NOT NULL, version INTEGER NOT NULL, submitted_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS validations(
  id INTEGER PRIMARY KEY, app_id INTEGER NOT NULL REFERENCES applications(id), version INTEGER NOT NULL,
  overall TEXT NOT NULL, report_json TEXT NOT NULL, extracted_json TEXT, ocr_text TEXT, created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS decisions(
  id INTEGER PRIMARY KEY, app_id INTEGER NOT NULL REFERENCES applications(id),
  admin_id INTEGER NOT NULL REFERENCES users(id), decision TEXT NOT NULL, note TEXT, decided_at REAL NOT NULL);
"""


def connect():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    return con


def _hash(password: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)


def create_user(username: str, password: str, full_name: str, role: str = "student") -> int:
    username = username.strip().lower()
    if not username or not full_name.strip():
        raise ValueError("Username and full name are required")
    if len(password) < 6:
        raise ValueError("Password must be at least 6 characters")
    salt = secrets.token_bytes(16)
    with connect() as con:
        try:
            cur = con.execute("INSERT INTO users(username,full_name,role,salt,pw_hash,created_at) VALUES(?,?,?,?,?,?)",
                              (username, full_name.strip(), role, salt, _hash(password, salt), time.time()))
        except sqlite3.IntegrityError:
            raise ValueError("That username is already taken")
        return cur.lastrowid


def init_db():
    with connect() as con:
        con.executescript(SCHEMA)
        has_users = con.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if not has_users:      # demo accounts: change these before any real use
        create_user("admin", "admin123", "Verifier Admin", "admin")
        create_user("student", "student123", "Demo Student", "student")


def authenticate(username: str, password: str):
    """Role comes from the database, never from the client."""
    with connect() as con:
        row = con.execute("SELECT * FROM users WHERE username=?", (username.strip().lower(),)).fetchone()
    if row is None:
        _hash(password, b"x" * 16)                      # keep timing similar for unknown users
        return None
    if hmac.compare_digest(_hash(password, row["salt"]), row["pw_hash"]):
        return {"id": row["id"], "username": row["username"], "full_name": row["full_name"], "role": row["role"]}
    return None


# ------------------------------------------------------------------ applications
def get_application_by_student(student_id: int):
    with connect() as con:
        return con.execute("SELECT * FROM applications WHERE student_id=?", (student_id,)).fetchone()


def get_application(app_id: int):
    with connect() as con:
        return con.execute("SELECT a.*, u.username FROM applications a JOIN users u ON u.id=a.student_id "
                           "WHERE a.id=?", (app_id,)).fetchone()


def save_application(student_id, name, register_no, marks, sheet, photo, status):
    """Insert, or replace on resubmission (version +1). Returns (app_id, version)."""
    with connect() as con:
        row = con.execute("SELECT id, version FROM applications WHERE student_id=?", (student_id,)).fetchone()
        if row:
            ver = row["version"] + 1
            con.execute("UPDATE applications SET name=?,register_no=?,marks_json=?,sheet=?,photo=?,status=?,"
                        "version=?,submitted_at=? WHERE id=?",
                        (name, register_no, json.dumps(marks), sheet, photo, status, ver, time.time(), row["id"]))
            return row["id"], ver
        cur = con.execute("INSERT INTO applications(student_id,name,register_no,marks_json,sheet,photo,status,"
                          "version,submitted_at) VALUES(?,?,?,?,?,?,?,1,?)",
                          (student_id, name, register_no, json.dumps(marks), sheet, photo, status, time.time()))
        return cur.lastrowid, 1


def add_validation(app_id, version, report, extraction):
    ex = None
    if extraction is not None:
        ex = {"name": extraction.name, "register_no": extraction.register_no, "total": extraction.total,
              "marks": {s: {"obtained": m.obtained, "confidence": round(m.confidence), "repaired": m.repaired}
                        for s, m in extraction.marks.items()}}
    with connect() as con:
        con.execute("INSERT INTO validations(app_id,version,overall,report_json,extracted_json,ocr_text,created_at)"
                    " VALUES(?,?,?,?,?,?,?)",
                    (app_id, version, report.overall, json.dumps(report.to_dict()), json.dumps(ex),
                     "\n".join(extraction.lines) if extraction else "", time.time()))


def latest_validation(app_id):
    with connect() as con:
        r = con.execute("SELECT * FROM validations WHERE app_id=? ORDER BY id DESC LIMIT 1", (app_id,)).fetchone()
    if r is None:
        return None
    return {"overall": r["overall"], "report": json.loads(r["report_json"]), "ocr_text": r["ocr_text"],
            "extracted": json.loads(r["extracted_json"] or "null"), "version": r["version"]}


def list_applications():
    with connect() as con:
        return [dict(r) for r in con.execute(
            "SELECT a.id,a.name,a.register_no,a.status,a.version,a.submitted_at,u.username,"
            "(SELECT overall FROM validations v WHERE v.app_id=a.id ORDER BY v.id DESC LIMIT 1) AS overall "
            "FROM applications a JOIN users u ON u.id=a.student_id ORDER BY a.submitted_at DESC")]


def add_decision(app_id, admin_id, decision, note):
    if decision not in STATUS_FROM_DECISION:
        raise ValueError("Unknown decision")
    with connect() as con:
        con.execute("INSERT INTO decisions(app_id,admin_id,decision,note,decided_at) VALUES(?,?,?,?,?)",
                    (app_id, admin_id, decision, note.strip(), time.time()))
        con.execute("UPDATE applications SET status=? WHERE id=?", (STATUS_FROM_DECISION[decision], app_id))


def list_decisions(app_id=None):
    q = ("SELECT d.id,d.app_id,a.name AS applicant,u.full_name AS verifier,d.decision,d.note,d.decided_at "
         "FROM decisions d JOIN applications a ON a.id=d.app_id JOIN users u ON u.id=d.admin_id")
    with connect() as con:
        rows = con.execute(q + (" WHERE d.app_id=?" if app_id else "") + " ORDER BY d.id DESC",
                           (app_id,) if app_id else ()).fetchall()
    return [dict(r) for r in rows]
"""
Seminar Registration & QR Check-In System - barebones prototype.

Run:
    pip install -r requirements.txt
    python app.py
Then open http://127.0.0.1:5000

Email config comes from environment variables (see README.md).
MOCK_EMAIL defaults to True, so nothing is sent until you turn it off.
"""
import os
import sqlite3
import smtplib
import uuid
from datetime import datetime
from email.message import EmailMessage

import qrcode
from flask import Flask, jsonify, render_template, request, url_for, g

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("DB_PATH", os.path.join(BASE_DIR, "seminar.db"))
QR_DIR = os.path.join(BASE_DIR, "static", "qrcodes")

MOCK_EMAIL = os.environ.get("MOCK_EMAIL", "True").lower() in ("1", "true", "yes")
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")  # Gmail: use an App Password
SMTP_FROM = os.environ.get("SMTP_FROM", SMTP_USER)
EVENT_NAME = os.environ.get("EVENT_NAME", "Seminar")

app = Flask(__name__)


# ---------------------------------------------------------------- database
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    os.makedirs(QR_DIR, exist_ok=True)
    with sqlite3.connect(DB_PATH) as db:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS participants (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                participant_id  TEXT UNIQUE NOT NULL,
                full_name       TEXT NOT NULL,
                email           TEXT UNIQUE NOT NULL,
                organization    TEXT,
                contact_number  TEXT,
                qr_path         TEXT,
                registered_at   TEXT NOT NULL,
                checked_in      INTEGER NOT NULL DEFAULT 0,
                checked_in_at   TEXT
            )
            """
        )


# ---------------------------------------------------------------- helpers
def new_participant_id():
    # e.g. SEM-3F9A1C2B7D  (short enough to type into the manual box)
    return "SEM-" + uuid.uuid4().hex[:10].upper()


def make_qr(participant_id):
    """Save a QR PNG encoding the participant_id. Returns the file path."""
    path = os.path.join(QR_DIR, f"{participant_id}.png")
    qrcode.make(participant_id).save(path)
    return path


def send_ticket_email(name, email, participant_id, qr_path):
    """Send the QR ticket. Returns (sent: bool, note: str)."""
    msg = EmailMessage()
    msg["Subject"] = f"Your {EVENT_NAME} ticket ({participant_id})"
    msg["From"] = SMTP_FROM or "noreply@example.com"
    msg["To"] = email
    msg.set_content(
        f"Hi {name},\n\n"
        f"You're registered for {EVENT_NAME}.\n"
        f"Your participant ID is: {participant_id}\n\n"
        f"Show the attached QR code at the registration desk to check in.\n"
    )
    msg.add_alternative(
        f"<p>Hi {name},</p>"
        f"<p>You're registered for <b>{EVENT_NAME}</b>.<br>"
        f"Participant ID: <b>{participant_id}</b></p>"
        f'<p><img src="cid:qrticket" alt="QR ticket" width="250"></p>'
        f"<p>Show this QR code at the registration desk to check in.</p>",
        subtype="html",
    )
    with open(qr_path, "rb") as f:
        png = f.read()
    # inline image for the HTML body + a normal attachment as backup
    msg.get_payload()[1].add_related(png, maintype="image", subtype="png", cid="<qrticket>")
    msg.add_attachment(png, maintype="image", subtype="png", filename=f"{participant_id}.png")

    if MOCK_EMAIL:
        app.logger.warning(
            "[MOCK EMAIL] To=%s Subject=%r QR=%s", email, msg["Subject"], qr_path
        )
        print(f"\n[MOCK EMAIL] to={email} | subject={msg['Subject']} | qr={qr_path}\n")
        return False, "Mock mode: email logged to console, not sent."

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
        return True, f"Ticket emailed to {email}."
    except Exception as exc:  # keep registration even if email fails
        app.logger.error("Email failed: %s", exc)
        return False, f"Registered, but email failed: {exc}"


# ---------------------------------------------------------------- pages
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/scanner")
def scanner():
    return render_template("scanner.html")


@app.route("/attendees")
def attendees():
    rows = get_db().execute(
        "SELECT * FROM participants ORDER BY registered_at DESC"
    ).fetchall()
    return render_template("attendees.html", rows=rows)


# ---------------------------------------------------------------- API
@app.route("/api/register", methods=["POST"])
def api_register():
    data = request.get_json(silent=True) or request.form
    full_name = (data.get("full_name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    organization = (data.get("organization") or "").strip()
    contact_number = (data.get("contact_number") or "").strip()

    if not full_name or not email:
        return jsonify(ok=False, message="Full name and email are required."), 400

    db = get_db()
    if db.execute("SELECT 1 FROM participants WHERE email = ?", (email,)).fetchone():
        return jsonify(ok=False, message="This email is already registered."), 409

    participant_id = new_participant_id()
    qr_path = make_qr(participant_id)
    db.execute(
        """INSERT INTO participants
           (participant_id, full_name, email, organization, contact_number,
            qr_path, registered_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (participant_id, full_name, email, organization, contact_number,
         qr_path, datetime.now().isoformat(timespec="seconds")),
    )
    db.commit()

    sent, note = send_ticket_email(full_name, email, participant_id, qr_path)
    resp = dict(
        ok=True,
        message=f"Registered {full_name}.",
        participant_id=participant_id,
        email_sent=sent,
        email_note=note,
        mock_email=MOCK_EMAIL,
    )
    if MOCK_EMAIL:  # only expose the QR link directly in debug mode
        resp["qr_url"] = url_for("static", filename=f"qrcodes/{participant_id}.png")
    return jsonify(resp), 201


@app.route("/api/checkin", methods=["POST"])
def api_checkin():
    data = request.get_json(silent=True) or request.form
    pid = (data.get("participant_id") or "").strip().upper()
    if not pid:
        return jsonify(status="invalid", message="No ID provided."), 400

    db = get_db()
    row = db.execute(
        "SELECT * FROM participants WHERE participant_id = ?", (pid,)
    ).fetchone()
    if row is None:
        return jsonify(status="invalid", message=f"Invalid: ID {pid} not found."), 404

    if row["checked_in"]:
        return jsonify(
            status="already",
            message=f"Already Checked In: {row['full_name']} (at {row['checked_in_at']})",
            name=row["full_name"],
            checked_in_at=row["checked_in_at"],
        ), 200

    now = datetime.now().isoformat(timespec="seconds")
    # the WHERE checked_in = 0 guard avoids double check-in from two scanners
    cur = db.execute(
        "UPDATE participants SET checked_in = 1, checked_in_at = ? "
        "WHERE participant_id = ? AND checked_in = 0",
        (now, pid),
    )
    db.commit()
    if cur.rowcount == 0:
        return jsonify(status="already", message=f"Already Checked In: {row['full_name']}"), 200

    return jsonify(
        status="success",
        message=f"Success: {row['full_name']} Checked In",
        name=row["full_name"],
        organization=row["organization"],
        checked_in_at=now,
    ), 200


@app.route("/api/participants")
def api_participants():
    rows = get_db().execute(
        "SELECT participant_id, full_name, email, organization, contact_number, "
        "registered_at, checked_in, checked_in_at FROM participants "
        "ORDER BY registered_at DESC"
    ).fetchall()
    return jsonify([dict(r) for r in rows])


init_db()

if __name__ == "__main__":
    print(f"MOCK_EMAIL = {MOCK_EMAIL}")
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", "5000")))

from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from functools import wraps
import os
import uuid
import datetime

app = Flask(__name__)

# without this, browsers hang onto the old style.css for hours after every
# edit - kept off caching so CSS/JS changes always show up on refresh
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0

# needed for login sessions - set FLASK_SECRET_KEY on Azure, this fallback
# is only fine for running locally
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-change-me")

# usernames in this list become superuser on registration
ADMIN_USERNAMES = [u.strip() for u in os.environ.get("ADMIN_USERNAMES", "").split(",") if u.strip()]

AZURE_CONNECTION_STRING = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
USE_AZURE = AZURE_CONNECTION_STRING is not None

# no heartbeat in this many seconds = dashboard shows the Pi as offline
ONLINE_THRESHOLD_SECONDS = 60

# resident profile photos - saved to disk as <username>.<ext>, one per caregiver account
UPLOAD_FOLDER = os.path.join(app.root_path, "static", "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
ALLOWED_PHOTO_EXTENSIONS = {"png", "jpg", "jpeg"}
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5MB upload limit


def allowed_photo(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_PHOTO_EXTENSIONS


def save_resident_photo(username, file):
    safe_username = secure_filename(username)
    ext = file.filename.rsplit(".", 1)[1].lower()
    # clear out any existing photo first, in case they're switching from .png to .jpg etc
    for old_ext in ALLOWED_PHOTO_EXTENSIONS:
        old_path = os.path.join(UPLOAD_FOLDER, f"{safe_username}.{old_ext}")
        if os.path.exists(old_path):
            os.remove(old_path)
    file.save(os.path.join(UPLOAD_FOLDER, f"{safe_username}.{ext}"))


def get_resident_photo(username):
    safe_username = secure_filename(username)
    for ext in ALLOWED_PHOTO_EXTENSIONS:
        if os.path.exists(os.path.join(UPLOAD_FOLDER, f"{safe_username}.{ext}")):
            return f"{safe_username}.{ext}"
    return None

# every field on the resident profile form - one place to add/remove a field
# instead of three (schema, save_resident, and the route that reads the form)
RESIDENT_FIELDS = [
    "name", "preferred_name", "dob", "sex", "preferred_language",
    "height", "weight", "blood_group", "mobility_level", "living_situation",
    "mobile", "address",
    "emergency_contact_name", "emergency_contact_relationship", "emergency_contact_phone",
    "gp", "allergies", "conditions",
    "dietary_requirements", "care_needs"
]

# a resident can have more than one medication, so these live in their own
# table/partition instead of on the resident row - see add_medication() etc.
MEDICATION_FIELDS = ["name", "dosage", "frequency", "time", "when_to_take", "duration", "instructions"]

# ---------------------------------------------------------------
# storage section
# ---------------------------------------------------------------

if USE_AZURE:
    from azure.data.tables import TableServiceClient

    TABLE_NAME = "alerts"
    # all alerts share one partition since this project only ever has one
    # "house" / one Pi sending alerts
    PARTITION_KEY = "alert"

    table_service = TableServiceClient.from_connection_string(AZURE_CONNECTION_STRING)
    table_client = table_service.create_table_if_not_exists(table_name=TABLE_NAME)

    def setup_db():
        # vitals - one row, create it if it's not there yet
        try:
            table_client.get_entity(partition_key="vitals", row_key="current")
        except Exception:
            table_client.create_entity({"PartitionKey": "vitals", "RowKey": "current"})

        # medication reminders - seed the 3 daily doses if none exist yet
        existing = list(table_client.query_entities(query_filter="PartitionKey eq 'medication'"))
        if not existing:
            seed = [("1", "08:00", "Metformin 500mg"), ("2", "13:00", "Metformin 500mg"), ("3", "20:00", "Amlodipine 5mg")]
            for row_key, time, name in seed:
                table_client.create_entity({"PartitionKey": "medication", "RowKey": row_key,
                                             "time": time, "name": name, "taken": False})

    def insert_alert(username, timestamp, severity, message, confidence=None, status="active"):
        table_client.create_entity({
            "PartitionKey": PARTITION_KEY,
            "RowKey": uuid.uuid4().hex,
            "username": username,
            "timestamp": timestamp,
            "severity": severity,
            "message": message,
            "confidence": confidence,  # can be None - Table Storage handles missing/None fields fine
            "status": status
        })

    # def get_alerts(active_only=False):
    #     entities = list(table_client.list_entities())
    #     # reshape into plain dicts with an "id" field so templates can use
    #     # alert["id"] the same way regardless of which storage mode is active
    #     # (Azure calls this RowKey, SQLite calls it id - id is just simpler)
    #     alerts = [{"id": e["RowKey"], "timestamp": e["timestamp"], "severity": e["severity"],
    #                "message": e["message"], "confidence": e.get("confidence"),
    #                "status": e["status"]} for e in entities]
    #     if active_only:
    #         alerts = [a for a in alerts if a["status"] == "active"]
    #     # Table Storage doesn't sort for us, so sort newest-first here
    #     alerts.sort(key=lambda a: a["timestamp"], reverse=True)
    #     return alerts

    def get_alerts(username, active_only=False):
        entities = list(table_client.query_entities(query_filter=f"PartitionKey eq '{PARTITION_KEY}'"))
        # reshape into plain dicts with an "id" field so templates can use
        # alert["id"] the same way regardless of which storage mode is active
        # (Azure calls this RowKey, SQLite calls it id - id is just simpler)
        alerts = [{"id": e["RowKey"], "timestamp": e["timestamp"], "severity": e["severity"],
                "message": e["message"], "confidence": e.get("confidence"),
                "status": e["status"]} for e in entities if e.get("username") == username]
        if active_only:
            alerts = [a for a in alerts if a["status"] == "active"]
        # Table Storage doesn't sort for us, so sort newest-first here
        alerts.sort(key=lambda a: a["timestamp"], reverse=True)
        return alerts

    def set_status(username, row_key, new_status):
        entity = table_client.get_entity(partition_key=PARTITION_KEY, row_key=row_key)
        if entity.get("username") != username:
            return  # not this caregiver's alert, ignore
        entity["status"] = new_status
        table_client.update_entity(entity)

    def delete_alert(username, row_key):
        try:
            entity = table_client.get_entity(partition_key=PARTITION_KEY, row_key=row_key)
            if entity.get("username") == username:
                table_client.delete_entity(partition_key=PARTITION_KEY, row_key=row_key)
        except Exception:
            pass

    def update_heartbeat(timestamp):
        table_client.upsert_entity({
            "PartitionKey": "device",
            "RowKey": "status",
            "last_seen": timestamp
        })

    def get_last_seen():
        try:
            entity = table_client.get_entity(partition_key="device", row_key="status")
            return entity["last_seen"]
        except Exception:
            return None  # no heartbeat received yet

    def get_vitals():
        try:
            entity = table_client.get_entity(partition_key="vitals", row_key="current")
            return dict(entity)
        except Exception:
            return {}

    def update_vitals(fields):
        fields["updated_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entity = {"PartitionKey": "vitals", "RowKey": "current"}
        entity.update(fields)
        table_client.upsert_entity(entity, mode="merge")

    def create_user(username, password_hash, role="user"):
        table_client.create_entity({
            "PartitionKey": "user",
            "RowKey": username,
            "password_hash": password_hash,
            "role": role,
            "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })

    def get_user(username):
        try:
            entity = table_client.get_entity(partition_key="user", row_key=username)
            return dict(entity)
        except Exception:
            return None

    def update_password(username, password_hash):
        entity = table_client.get_entity(partition_key="user", row_key=username)
        entity["password_hash"] = password_hash
        table_client.update_entity(entity)

    def list_users():
        entities = list(table_client.query_entities(query_filter="PartitionKey eq 'user'"))
        users = [{"username": e["RowKey"], "role": e.get("role", "user"),
                  "created_at": e.get("created_at")} for e in entities]
        users.sort(key=lambda u: u["created_at"] or "")
        return users

    def delete_user(username):
        try:
            table_client.delete_entity(partition_key="user", row_key=username)
        except Exception:
            pass
        try:
            table_client.delete_entity(partition_key="resident", row_key=username)
        except Exception:
            pass

    def save_resident(username, fields):
        entity = {"PartitionKey": "resident", "RowKey": username}
        entity.update(fields)
        table_client.upsert_entity(entity)

    def get_resident_row(username):
        try:
            entity = table_client.get_entity(partition_key="resident", row_key=username)
            return dict(entity)
        except Exception:
            return None

    def add_medication(username, fields):
        entity = {"PartitionKey": "resident_medication", "RowKey": uuid.uuid4().hex, "username": username}
        entity.update(fields)
        table_client.create_entity(entity)

    def get_medications(username):
        entities = list(table_client.query_entities(query_filter="PartitionKey eq 'resident_medication'"))
        today = datetime.date.today().isoformat()
        meds = []
        for e in entities:
            if e.get("username") != username:
                continue
            med = {"id": e["RowKey"]}
            med.update({f: e.get(f) for f in MEDICATION_FIELDS})
            med["taken_today"] = e.get("taken_date") == today
            meds.append(med)
        return meds

    def delete_medication(username, med_id):
        try:
            entity = table_client.get_entity(partition_key="resident_medication", row_key=med_id)
            if entity.get("username") == username:
                table_client.delete_entity(partition_key="resident_medication", row_key=med_id)
        except Exception:
            pass

    def update_medication(username, med_id, fields):
        try:
            entity = table_client.get_entity(partition_key="resident_medication", row_key=med_id)
            if entity.get("username") != username:
                return
            entity.update(fields)
            table_client.update_entity(entity)
        except Exception:
            pass

    def toggle_medication_dose(username, med_id):
        try:
            entity = table_client.get_entity(partition_key="resident_medication", row_key=med_id)
            if entity.get("username") != username:
                return
            today = datetime.date.today().isoformat()
            entity["taken_date"] = None if entity.get("taken_date") == today else today
            table_client.update_entity(entity)
        except Exception:
            pass

else:
    import sqlite3

    # anchored to this file's own folder, not wherever "python app.py" gets run
    # from - so the db always ends up in the same place (dashboard/seniorconnect.db)
    # regardless of working directory
    DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seniorconnect.db")

    def get_db():
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row  # lets us access columns by name, e.g. row["severity"]
        return conn

    def setup_db():
        conn = get_db()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                severity TEXT NOT NULL,
                message TEXT,
                confidence REAL,
                status TEXT DEFAULT 'active'
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS device_status (
                id INTEGER PRIMARY KEY,
                last_seen TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS vitals (
                id INTEGER PRIMARY KEY,
                heart_rate TEXT,
                bp_systolic TEXT,
                bp_diastolic TEXT,
                temperature TEXT,
                oxygen TEXT,
                updated_at TEXT
            )
        """)
        conn.execute("INSERT OR IGNORE INTO vitals (id) VALUES (1)")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                role TEXT DEFAULT 'user',
                created_at TEXT
            )
        """)
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS residents (
                username TEXT PRIMARY KEY,
                {", ".join(f"{field} TEXT" for field in RESIDENT_FIELDS)}
            )
        """)
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS resident_medications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                {", ".join(f"{field} TEXT" for field in MEDICATION_FIELDS)},
                taken_date TEXT
            )
        """)
        conn.commit()
        conn.close()

    def insert_alert(username, timestamp, severity, message, confidence=None, status="active"):
        conn = get_db()
        conn.execute(
            "INSERT INTO alerts (username, timestamp, severity, message, confidence, status) VALUES (?, ?, ?, ?, ?, ?)",
            (username, timestamp, severity, message, confidence, status)
        )
        conn.commit()
        conn.close()

    def get_alerts(username, active_only=False):
        conn = get_db()
        if active_only:
            rows = conn.execute(
                "SELECT * FROM alerts WHERE username = ? AND status = 'active' ORDER BY timestamp DESC",
                (username,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM alerts WHERE username = ? ORDER BY timestamp DESC",
                (username,)
            ).fetchall()
        conn.close()
        # wrap rows so templates can use alert["id"] the same way for both modes
        return [{"id": r["id"], "timestamp": r["timestamp"], "severity": r["severity"],
                  "message": r["message"], "confidence": r["confidence"],
                  "status": r["status"]} for r in rows]

    def set_status(username, row_id, new_status):
        conn = get_db()
        conn.execute("UPDATE alerts SET status = ? WHERE id = ? AND username = ?", (new_status, row_id, username))
        conn.commit()
        conn.close()

    def delete_alert(username, row_id):
        conn = get_db()
        conn.execute("DELETE FROM alerts WHERE id = ? AND username = ?", (row_id, username))
        conn.commit()
        conn.close()

    def update_heartbeat(timestamp):
        conn = get_db()
        conn.execute("INSERT OR REPLACE INTO device_status (id, last_seen) VALUES (1, ?)", (timestamp,))
        conn.commit()
        conn.close()

    def get_last_seen():
        conn = get_db()
        row = conn.execute("SELECT last_seen FROM device_status WHERE id = 1").fetchone()
        conn.close()
        return row["last_seen"] if row else None

    def get_vitals():
        conn = get_db()
        row = conn.execute("SELECT * FROM vitals WHERE id = 1").fetchone()
        conn.close()
        return dict(row) if row else {}

    def update_vitals(fields):
        fields = dict(fields)
        fields["updated_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = get_db()
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        conn.execute(f"UPDATE vitals SET {set_clause} WHERE id = 1", list(fields.values()))
        conn.commit()
        conn.close()

    def create_user(username, password_hash, role="user"):
        conn = get_db()
        conn.execute("INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
                      (username, password_hash, role, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        conn.close()

    def get_user(username):
        conn = get_db()
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        conn.close()
        return dict(row) if row else None

    def update_password(username, password_hash):
        conn = get_db()
        conn.execute("UPDATE users SET password_hash = ? WHERE username = ?", (password_hash, username))
        conn.commit()
        conn.close()

    def list_users():
        conn = get_db()
        rows = conn.execute("SELECT username, role, created_at FROM users ORDER BY created_at").fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def delete_user(username):
        conn = get_db()
        conn.execute("DELETE FROM users WHERE username = ?", (username,))
        conn.execute("DELETE FROM residents WHERE username = ?", (username,))
        conn.commit()
        conn.close()

    def save_resident(username, fields):
        conn = get_db()
        exists = conn.execute("SELECT username FROM residents WHERE username = ?", (username,)).fetchone()
        if exists:
            set_clause = ", ".join(f"{f} = ?" for f in RESIDENT_FIELDS)
            conn.execute(f"UPDATE residents SET {set_clause} WHERE username = ?",
                         [fields[f] for f in RESIDENT_FIELDS] + [username])
        else:
            columns = ", ".join(RESIDENT_FIELDS)
            placeholders = ", ".join("?" for _ in RESIDENT_FIELDS)
            conn.execute(f"INSERT INTO residents (username, {columns}) VALUES (?, {placeholders})",
                         [username] + [fields[f] for f in RESIDENT_FIELDS])
        conn.commit()
        conn.close()

    def get_resident_row(username):
        conn = get_db()
        row = conn.execute("SELECT * FROM residents WHERE username = ?", (username,)).fetchone()
        conn.close()
        return dict(row) if row else None

    def add_medication(username, fields):
        conn = get_db()
        columns = ", ".join(MEDICATION_FIELDS)
        placeholders = ", ".join("?" for _ in MEDICATION_FIELDS)
        conn.execute(f"INSERT INTO resident_medications (username, {columns}) VALUES (?, {placeholders})",
                     [username] + [fields[f] for f in MEDICATION_FIELDS])
        conn.commit()
        conn.close()

    def get_medications(username):
        conn = get_db()
        rows = conn.execute("SELECT * FROM resident_medications WHERE username = ? ORDER BY id", (username,)).fetchall()
        conn.close()
        today = datetime.date.today().isoformat()
        meds = []
        for r in rows:
            med = dict(r)
            med["taken_today"] = med.get("taken_date") == today
            meds.append(med)
        return meds

    def delete_medication(username, med_id):
        conn = get_db()
        conn.execute("DELETE FROM resident_medications WHERE id = ? AND username = ?", (med_id, username))
        conn.commit()
        conn.close()

    def update_medication(username, med_id, fields):
        conn = get_db()
        set_clause = ", ".join(f"{f} = ?" for f in MEDICATION_FIELDS)
        conn.execute(f"UPDATE resident_medications SET {set_clause} WHERE id = ? AND username = ?",
                     [fields[f] for f in MEDICATION_FIELDS] + [med_id, username])
        conn.commit()
        conn.close()

    def toggle_medication_dose(username, med_id):
        conn = get_db()
        row = conn.execute("SELECT taken_date FROM resident_medications WHERE id = ? AND username = ?",
                            (med_id, username)).fetchone()
        if row is not None:
            today = datetime.date.today().isoformat()
            new_value = None if row["taken_date"] == today else today
            conn.execute("UPDATE resident_medications SET taken_date = ? WHERE id = ? AND username = ?",
                         (new_value, med_id, username))
            conn.commit()
        conn.close()

# ---------------------------------------------------------------
# routes
# ---------------------------------------------------------------


def login_required(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if "username" not in session:
            return redirect(url_for("login"))
        return view_func(*args, **kwargs)
    return wrapper


def admin_required(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if "username" not in session:
            return redirect(url_for("login"))
        if session.get("role") != "superuser":
            return redirect(url_for("dashboard"))
        return view_func(*args, **kwargs)
    return wrapper


def is_online(last_seen):
    if last_seen is None:
        return False
    last_seen_dt = datetime.datetime.strptime(last_seen, "%Y-%m-%d %H:%M:%S")
    seconds_since = (datetime.datetime.now() - last_seen_dt).total_seconds()
    return seconds_since < ONLINE_THRESHOLD_SECONDS


def format_relative_time(timestamp):
    if timestamp is None:
        return None
    then = datetime.datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
    seconds = int((datetime.datetime.now() - then).total_seconds())
    if seconds < 60:
        return "just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    days = hours // 24
    return f"{days} day{'s' if days != 1 else ''} ago"


def format_relative_time(last_seen):
    if last_seen is None:
        return None
    last_seen_dt = datetime.datetime.strptime(last_seen, "%Y-%m-%d %H:%M:%S")
    seconds = int((datetime.datetime.now() - last_seen_dt).total_seconds())
    if seconds < 60:
        return "just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    days = hours // 24
    return f"{days} day{'s' if days != 1 else ''} ago"


def calculate_age(dob):
    # dob comes from the date input as yyyy-mm-dd - no point asking for age
    # separately when we can work it out from this
    if not dob:
        return None
    try:
        birth = datetime.datetime.strptime(dob, "%Y-%m-%d").date()
    except ValueError:
        return None
    today = datetime.date.today()
    return today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")

        if not username or not password:
            return render_template("register.html", error="Username and password are required")
        if password != confirm:
            return render_template("register.html", error="Passwords don't match")
        if get_user(username):
            return render_template("register.html", error="That username is already taken")

        role = "superuser" if username in ADMIN_USERNAMES else "user"
        create_user(username, generate_password_hash(password), role)
        session["username"] = username
        session["role"] = role
        return redirect(url_for("profile_edit"))

    return render_template("register.html", error=None)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user = get_user(username)
        if user is None or not check_password_hash(user["password_hash"], password):
            return render_template("login.html", error="Incorrect username or password")

        session["username"] = username
        session["role"] = user.get("role", "user")
        return redirect(url_for("dashboard"))

    return render_template("login.html", error=None)


@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    error = None
    success = None

    if request.method == "POST":
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirm = request.form.get("confirm", "")

        user = get_user(session["username"])
        if not check_password_hash(user["password_hash"], current_password):
            error = "Current password is incorrect"
        elif not new_password:
            error = "New password can't be blank"
        elif new_password != confirm:
            error = "New passwords don't match"
        else:
            update_password(session["username"], generate_password_hash(new_password))
            success = "Password updated"

    return render_template("settings.html", error=error, success=success)


@app.route("/logout")
def logout():
    session.pop("username", None)
    session.pop("role", None)
    return redirect(url_for("login"))


@app.route("/admin")
@admin_required
def admin():
    users = list_users()
    for u in users:
        resident = get_resident_row(u["username"])
        u["resident_name"] = resident["name"] if resident else None
    return render_template("admin.html", users=users)


@app.route("/admin/delete/<username>", methods=["POST"])
@admin_required
def admin_delete_user(username):
    if username != session["username"]:
        delete_user(username)
    return redirect(url_for("admin"))


@app.route("/")
@login_required
def dashboard():
    resident = get_resident_row(session["username"])
    if resident is None:
        return redirect(url_for("profile_edit"))

    resident["age"] = calculate_age(resident["dob"])

    lab_results = [
        {"test": "Blood sugar (fasting)", "value": "6.8 mmol/L", "range": "4.0 - 6.0", "status": "high"},
        {"test": "Haemoglobin", "value": "13.2 g/dL", "range": "12.0 - 15.5", "status": "normal"},
        {"test": "White blood cells", "value": "6.4 x10\u2079/L", "range": "4.0 - 11.0", "status": "normal"},
        {"test": "Lymphocytes", "value": "1.8 x10\u2079/L", "range": "1.0 - 3.0", "status": "normal"}
    ]

    activity = [
        {"day": "Mon", "minutes": 29}, {"day": "Tue", "minutes": 38}, {"day": "Wed", "minutes": 19},
        {"day": "Thu", "minutes": 36}, {"day": "Fri", "minutes": 28}, {"day": "Sat", "minutes": 33},
        {"day": "Today", "minutes": 8}
    ]

    vitals = get_vitals()
    medications = get_medications(session["username"])
    doses_taken = len([m for m in medications if m["taken_today"]])
    doses_total = len(medications)
    adherence = round(doses_taken / doses_total * 100) if doses_total else 0

    # not-yet-taken meds first, so the ones still needing action show up
    # without scrolling - only the first 5 render on the dashboard card,
    # the rest are one click away via "Manage all" (Edit Profile)
    medications_sorted = sorted(medications, key=lambda m: m["taken_today"])
    medications_visible = medications_sorted[:5]
    medications_hidden_count = len(medications_sorted) - len(medications_visible)

    vitals_fields = ["heart_rate", "bp_systolic", "temperature", "oxygen"]
    vitals_recorded = sum(1 for f in vitals_fields if vitals.get(f))

    needs_attention = []
    for lab in lab_results:
        if lab["status"] == "high":
            needs_attention.append({
                "severity": "high",
                "kind": "alert",
                "title": lab["test"],
                "detail": "Above configured range",
                "value": lab["value"],
                "note": "Review required"
            })
    if not vitals.get("bp_systolic") or not vitals.get("bp_diastolic"):
        needs_attention.append({
            "severity": "medium",
            "kind": "reminder",
            "title": "Blood pressure",
            "detail": "Not recorded today",
            "value": "--",
            "note": f"Last: {vitals['updated_at']}" if vitals.get("updated_at") else "No reading recorded yet"
        })  

    # last_seen = get_last_seen()

    # return render_template(
    #     "dashboard.html",
    #     resident=resident,
    #     photo=get_resident_photo(session["username"]),
    #     vitals=vitals,
    #     vitals_recorded=vitals_recorded,
    #     doses_taken=doses_taken,
    #     doses_total=doses_total,
    #     adherence=adherence,
    #     needs_attention=needs_attention,
    #     medications=medications_visible,
    #     medications_hidden_count=medications_hidden_count,
    #     activity=activity,
    #     online=is_online(last_seen),
    #     last_seen=format_relative_time(last_seen)
    # )

    last_seen = get_last_seen()

    alerts_all = get_alerts(session["username"], active_only=False)
    today = datetime.date.today().isoformat()
    week_ago = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
    falls_today = len([a for a in alerts_all if a["timestamp"][:10] == today])
    alerts_this_week = [a for a in alerts_all if a["timestamp"][:10] >= week_ago]
    false_alarms_this_week = len([a for a in alerts_this_week if a["status"] == "false_alarm"])
    active_alerts = [a for a in alerts_all if a["status"] == "active"]
    latest_alert = active_alerts[0] if active_alerts else None

    return render_template(
        "dashboard.html",
        resident=resident,
        photo=get_resident_photo(session["username"]),
        vitals=vitals,
        vitals_recorded=vitals_recorded,
        doses_taken=doses_taken,
        doses_total=doses_total,
        adherence=adherence,
        needs_attention=needs_attention,
        medications=medications_visible,
        medications_hidden_count=medications_hidden_count,
        activity=activity,
        online=is_online(last_seen),
        last_seen=format_relative_time(last_seen),
        falls_today=falls_today,
        false_alarms_this_week=false_alarms_this_week,
        alerts_this_week_count=len(alerts_this_week),
        latest_alert=latest_alert
    )


@app.route("/profile")
@login_required
def profile():
    resident = get_resident_row(session["username"])
    if resident is None:
        return redirect(url_for("profile_edit"))

    resident["allergies"] = resident["allergies"].split(",") if resident["allergies"] else []
    resident["conditions"] = resident["conditions"].split(",") if resident["conditions"] else []
    resident["age"] = calculate_age(resident["dob"])

    medications = get_medications(session["username"])

    last_seen = get_last_seen()

    return render_template(
        "profile.html",
        resident=resident,
        medications=medications,
        photo=get_resident_photo(session["username"]),
        online=is_online(last_seen),
        last_seen=format_relative_time(last_seen)
    )


@app.route("/profile/edit", methods=["GET", "POST"])
@login_required
def profile_edit():
    success = None

    if request.method == "POST":
        fields = {f: request.form.get(f, "").strip() for f in RESIDENT_FIELDS}
        save_resident(session["username"], fields)

        photo_file = request.files.get("photo")
        if photo_file and photo_file.filename:
            if allowed_photo(photo_file.filename):
                save_resident_photo(session["username"], photo_file)
            else:
                success = None
                return render_template(
                    "profile_edit.html",
                    resident=get_resident_row(session["username"]),
                    medications=get_medications(session["username"]),
                    photo=get_resident_photo(session["username"]),
                    error="Photo must be a JPG or PNG file",
                    success=success
                )

        success = "Profile saved"

    resident = get_resident_row(session["username"])
    medications = get_medications(session["username"])
    return render_template(
        "profile_edit.html",
        resident=resident,
        medications=medications,
        photo=get_resident_photo(session["username"]),
        error=None,
        success=success
    )


@app.route("/profile/medication/add", methods=["POST"])
@login_required
def add_medication_route():
    fields = {f: request.form.get(f, "").strip() for f in MEDICATION_FIELDS}
    if fields["name"]:  # ignore an empty add (e.g. hitting enter in a blank field)
        add_medication(session["username"], fields)
    return redirect(url_for("profile_edit"))


@app.route("/profile/medication/<med_id>/delete", methods=["POST"])
@login_required
def delete_medication_route(med_id):
    if not USE_AZURE:
        med_id = int(med_id)
    delete_medication(session["username"], med_id)
    return redirect(url_for("profile_edit"))


@app.route("/profile/medication/<med_id>/update", methods=["POST"])
@login_required
def update_medication_route(med_id):
    if not USE_AZURE:
        med_id = int(med_id)
    fields = {f: request.form.get(f, "").strip() for f in MEDICATION_FIELDS}
    update_medication(session["username"], med_id, fields)
    return redirect(url_for("profile_edit"))


# @app.route("/alerts")
# @login_required
# def alerts_page():
#     alerts = get_alerts(active_only=True)
#     last_seen = get_last_seen()
#     return render_template("alerts.html", alerts=alerts, active_count=len(alerts),
#                             online=is_online(last_seen), last_seen=format_relative_time(last_seen))

@app.route("/alerts")
@login_required
def alerts_page():
    alerts = get_alerts(session["username"], active_only=True)
    last_seen = get_last_seen()
    resident = get_resident_row(session["username"])
    return render_template("alerts.html", alerts=alerts, active_count=len(alerts),
                            online=is_online(last_seen), last_seen=format_relative_time(last_seen),
                            resident=resident)


@app.route("/history")
@login_required
def history():
    alerts = get_alerts(session["username"], active_only=False)
    last_seen = get_last_seen()
    return render_template("history.html", alerts=alerts,
                            online=is_online(last_seen), last_seen=format_relative_time(last_seen))


@app.route("/api/alert", methods=["POST"])
def receive_alert():
    # this is the endpoint the Pi (via Azure) sends fall alerts to
    # expected JSON body, e.g. {"username": "mewong3", "severity": "high", "message": "Fall detected, no movement after"}
    data = request.get_json(force=True, silent=True) or {}

    username = data.get("username", "mewong3")  # which caregiver account this alert belongs to
    severity = data.get("severity", "unknown")
    message = data.get("message", "Fall detected")
    confidence = data.get("confidence")  # optional - fine if not sent
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    insert_alert(username, now, severity, message, confidence)

    return jsonify({"status": "ok", "saved_at": now, "storage": "azure" if USE_AZURE else "sqlite"})


@app.route("/api/heartbeat", methods=["POST"])
def heartbeat():
    # Pi pings this every 20-30s just to say it's alive, separate from actual alerts
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    update_heartbeat(now)
    return jsonify({"status": "ok", "last_seen": now})


@app.route("/api/alert/<alert_id>/ack", methods=["POST"])
@login_required
def acknowledge_alert(alert_id):
    # caregiver clicks "Mark as seen" on the dashboard
    # alert_id is a RowKey (string) in Azure mode, or a numeric id (string) in SQLite mode
    if USE_AZURE:
        set_status(session["username"], alert_id, "acknowledged")
    else:
        set_status(session["username"], int(alert_id), "acknowledged")
    return redirect(url_for("alerts_page"))


@app.route("/api/alert/<alert_id>/false_alarm", methods=["POST"])
@login_required
def false_alarm_alert(alert_id):
    # separate from ack so history shows how often the model false-triggers,
    # not just what got looked at
    if USE_AZURE:
        set_status(session["username"], alert_id, "false_alarm")
    else:
        set_status(session["username"], int(alert_id), "false_alarm")
    return redirect(url_for("alerts_page"))


@app.route("/api/alert/<alert_id>/sos", methods=["POST"])
@login_required
def sos_alert(alert_id):
    # caregiver clicks SOS - this build only logs the escalation, it does not
    # actually dial emergency services. A live deployment would integrate with
    # a real dispatch service here.
    if USE_AZURE:
        set_status(session["username"], alert_id, "escalated")
    else:
        set_status(session["username"], int(alert_id), "escalated")
    return redirect(url_for("alerts_page"))


@app.route("/api/vitals/heart", methods=["POST"])
@login_required
def update_heart_rate():
    update_vitals({"heart_rate": request.form.get("heart_rate")})
    return redirect(url_for("dashboard"))


@app.route("/api/vitals/bp", methods=["POST"])
@login_required
def update_bp():
    update_vitals({
        "bp_systolic": request.form.get("bp_systolic"),
        "bp_diastolic": request.form.get("bp_diastolic")
    })
    return redirect(url_for("dashboard"))


@app.route("/api/vitals/temperature", methods=["POST"])
@login_required
def update_temperature():
    update_vitals({"temperature": request.form.get("temperature")})
    return redirect(url_for("dashboard"))


@app.route("/api/vitals/oxygen", methods=["POST"])
@login_required
def update_oxygen():
    update_vitals({"oxygen": request.form.get("oxygen")})
    return redirect(url_for("dashboard"))


@app.route("/api/medication/<med_id>/toggle", methods=["POST"])
@login_required
def toggle_medication(med_id):
    if not USE_AZURE:
        med_id = int(med_id)
    toggle_medication_dose(session["username"], med_id)
    return redirect(url_for("dashboard"))


if __name__ == "__main__":
    setup_db()
    print("Storage mode:", "Azure Table Storage" if USE_AZURE else "local SQLite (no AZURE_STORAGE_CONNECTION_STRING set)")
    app.run(debug=True)
    
import app as sc
from werkzeug.security import generate_password_hash
import datetime

sc.setup_db()

RESIDENT_DATA = {
    "name": "Margaret Ellison",
    "preferred_name": "Margaret",
    "dob": "1948-03-14",
    "sex": "Female",
    "preferred_language": "English",
    "height": "160",
    "weight": "68",
    "blood_group": "O+",
    "mobility_level": "Needs assistance",
    "living_situation": "Lives alone",
    "mobile": "07911 123456",
    "address": "24 Oakwood Drive, Sheffield, S10 3AB",
    "emergency_contact_name": "Helen Ellison",
    "emergency_contact_relationship": "Daughter",
    "emergency_contact_phone": "07922 654321",
    "gp": "Dr. Sarah Whitfield, Broomhill Surgery, Sheffield",
    "allergies": "Penicillin",
    "conditions": "Type 2 diabetes, Hypertension, Osteoporosis, Mild arthritis, History of falls",
    "dietary_requirements": "Low sugar diet",
    "care_needs": "Assistance with mobility, daily medication reminders, fall risk monitoring",
}

MEDICATIONS = [
    {"name": "Metformin", "dosage": "500mg", "frequency": "Twice a day", "time": "08:00",
     "when_to_take": "After breakfast", "duration": "Ongoing", "instructions": "Take with food"},
    {"name": "Metformin", "dosage": "500mg", "frequency": "Twice a day", "time": "13:00",
     "when_to_take": "After lunch", "duration": "Ongoing", "instructions": "Take with food"},
    {"name": "Amlodipine", "dosage": "5mg", "frequency": "Once a day", "time": "20:00",
     "when_to_take": "Bedtime", "duration": "Ongoing", "instructions": "May cause dizziness, monitor for lightheadedness on standing"},
    {"name": "Vitamin D", "dosage": "10mg", "frequency": "Once a day", "time": "08:00",
     "when_to_take": "After breakfast", "duration": "Ongoing", "instructions": "Take with food"},
]

ALERTS = [
    {"days_ago": 2, "hour": 18, "minute": 30, "severity": "high", "message": "Fall detected in living room",
     "confidence": 0.91, "status": "active"},
    {"days_ago": 14, "hour": 15, "minute": 45, "severity": "medium", "message": "Possible fall detected, no movement after 30s",
     "confidence": 0.72, "status": "active"},
    {"days_ago": 28, "hour": 17, "minute": 15, "severity": "low", "message": "Brief fall-like motion detected, no injury reported",
     "confidence": 0.45, "status": "acknowledged"},
]

CAREGIVERS = [f"Caregiver{i:03d}" for i in range(2, 9)]  # Caregiver002 .. Caregiver008
PASSWORD = "demo1234!"

for username in CAREGIVERS:
    if sc.get_user(username) is None:
        sc.create_user(username, generate_password_hash(PASSWORD), role="user")
        print(f"created user {username}")
    else:
        print(f"user {username} already exists, skipping create")

    fields = {f: RESIDENT_DATA.get(f, "") for f in sc.RESIDENT_FIELDS}
    sc.save_resident(username, fields)

    for existing in sc.get_medications(username):
        sc.delete_medication(username, existing["id"])
    for med in MEDICATIONS:
        med_fields = {f: med.get(f, "") for f in sc.MEDICATION_FIELDS}
        sc.add_medication(username, med_fields)

    for existing in sc.get_alerts(username, active_only=False):
        sc.delete_alert(username, existing["id"])
    now = datetime.datetime.now()
    for a in ALERTS:
        day = (now - datetime.timedelta(days=a["days_ago"])).date()
        timestamp = datetime.datetime.combine(day, datetime.time(a["hour"], a["minute"])).strftime("%Y-%m-%d %H:%M:%S")
        sc.insert_alert(username, timestamp, a["severity"], a["message"], a["confidence"], a["status"])

    print(f"seeded resident + {len(MEDICATIONS)} medications + {len(ALERTS)} alerts for {username}")

print("done")
print(f"password for all accounts: {PASSWORD}")

"""
test_all.py — Full test suite for HemasHealth IQ backend.

Tests every feature without needing OpenAI or Supabase.
Run with:  python -m pytest tests/test_all.py -v

Or run directly:  python tests/test_all.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("OPENAI_API_KEY", "sk-test")
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "test-key")

# ── Colours ───────────────────────────────────────────────────────────────────
R      = "\033[0m"
BOLD   = "\033[1m"
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
DIM    = "\033[2m"

passed = []
failed = []

def test(name: str, condition: bool, detail: str = ""):
    if condition:
        passed.append(name)
        print(f"  {GREEN}✅ {name}{R}")
    else:
        failed.append(name)
        print(f"  {RED}❌ {name}{R}")
        if detail:
            print(f"     {RED}{detail}{R}")

def section(title: str):
    print(f"\n{BOLD}{CYAN}{'─'*55}{R}")
    print(f"{BOLD}{CYAN}  {title}{R}")
    print(f"{BOLD}{CYAN}{'─'*55}{R}")


# ─────────────────────────────────────────────────────────────────────────────
# 1. MOCK DATABASE
# ─────────────────────────────────────────────────────────────────────────────
section("1. Mock Database")

from app.db.mock_db import get_db, MockDB

db = get_db()

test("MockDB singleton returns same instance",
     get_db() is db)

test("15 doctors seeded",
     len(db.doctors) == 15)

test("840 slots generated (15 doctors × 7 days × 8 hours)",
     len(db.slots) == 840)

test("All slots start unbooked",
     all(not s["is_booked"] for s in db.slots))

test("2 seed patients exist",
     len(db.patients) == 2)

test("No pre-booked appointments",
     len(db.appointments) == 0)

test("get_doctors filters by specialty",
     len(db.get_doctors(specialty="Cardiology")) == 2)

test("get_doctors filters by location",
     len(db.get_doctors(location="wattala")) == 9)

test("get_doctors filters specialty + location",
     len(db.get_doctors(specialty="Cardiology", location="wattala")) == 1)

test("get_doctor by ID works",
     db.get_doctor("doc-001")["name"] == "Dr. Nimal Perera")

test("get_doctor returns None for unknown ID",
     db.get_doctor("nonexistent") is None)

test("find_patient_by_phone finds Kamal",
     db.find_patient_by_phone("+94771234567")["name"] == "Kamal Jayawardena")

test("find_patient_by_phone normalises spaces",
     db.find_patient_by_phone("+94771234567")["name"] == "Kamal Jayawardena")

test("find_patient_by_phone returns None for unknown",
     db.find_patient_by_phone("+94700000000") is None)

new_p = db.create_patient("Test Patient", "+94700000001", "test@test.com")
test("create_patient returns record with ID",
     new_p["id"] is not None and new_p["name"] == "Test Patient")

test("created patient is findable by phone",
     db.find_patient_by_phone("+94700000001") is not None)


# ─────────────────────────────────────────────────────────────────────────────
# 2. ROUTING TOOL
# ─────────────────────────────────────────────────────────────────────────────
section("2. Symptom Routing Tool")

from app.tools.routing import route_to_specialist

cases = [
    ("chest pain",                    "Cardiology",              False),
    ("migraine",                      "Neurology",               False),
    ("stomach pain and nausea",       "Gastroenterology",        False),
    ("back pain",                     "Orthopedics",             False),
    ("skin rash",                     "Dermatology",             False),
    ("ear pain",                      "ENT",                     False),
    ("blurred vision",                "Ophthalmology",           False),
    ("diabetes checkup",              "Endocrinology",           False),
    ("pregnancy",                     "Obstetrics & Gynecology", False),
    ("child fever",                   "Pediatrics",              False),
    ("general checkup",               "General Medicine",        False),
    ("cannot breathe",                None,                      True),
    ("heart attack",                  None,                      True),
    ("loss of consciousness",         None,                      True),
]

for symptoms, expected_specialty, expected_emergency in cases:
    r = route_to_specialist.invoke({"symptoms": symptoms})
    test(
        f"route: '{symptoms}'",
        r["specialty"] == expected_specialty and r["is_emergency"] == expected_emergency,
        f"got specialty={r['specialty']} emergency={r['is_emergency']}, "
        f"expected specialty={expected_specialty} emergency={expected_emergency}"
    )

r_low = route_to_specialist.invoke({"symptoms": "feel a bit off"})
test("low confidence fallback → General Medicine",
     r_low["specialty"] == "General Medicine" and r_low["confidence"] == "low")


# ─────────────────────────────────────────────────────────────────────────────
# 3. AVAILABILITY TOOL
# ─────────────────────────────────────────────────────────────────────────────
section("3. Availability Tool")

from app.tools.availability import check_availability

a1 = check_availability.invoke({"specialty": "Cardiology", "location": "wattala"})
test("Cardiology/Wattala returns 1 doctor",
     len(a1["doctors"]) == 1)
test("doctor has slots",
     len(a1["doctors"][0]["slots"]) > 0)
test("slots have slot_id and datetime",
     "slot_id" in a1["doctors"][0]["slots"][0] and "datetime" in a1["doctors"][0]["slots"][0])
test("total_slots_found populated",
     a1["total_slots_found"] > 0)

a2 = check_availability.invoke({"specialty": "Ophthalmology", "location": "wattala"})
test("Ophthalmology/Wattala returns 0 doctors (not at this location)",
     len(a2["doctors"]) == 0)

a3 = check_availability.invoke({"specialty": "Ophthalmology", "location": "thalawathugoda"})
test("Ophthalmology/Thalawathugoda returns 1 doctor",
     len(a3["doctors"]) == 1)

a4 = check_availability.invoke({"specialty": "General Medicine", "location": "thalawathugoda"})
test("General Medicine/Thalawathugoda has slots",
     len(a4["doctors"]) > 0)


# ─────────────────────────────────────────────────────────────────────────────
# 4. PATIENT TOOL
# ─────────────────────────────────────────────────────────────────────────────
section("4. Patient Lookup Tool")

from app.tools.patient import lookup_or_create_patient

# Returning patient
p1 = lookup_or_create_patient.invoke({"phone": "+94771234567"})
test("returning patient found by phone",
     p1["patient_id"] == "patient-001")
test("returning patient is_new = False",
     p1["is_new"] == False)
test("returning patient name correct",
     p1["name"] == "Kamal Jayawardena")

# New patient — no name given
p2 = lookup_or_create_patient.invoke({"phone": "+94799999999"})
test("unknown phone with no name returns error",
     p2["error"] is not None and p2["patient_id"] is None)

# New patient — with name
p3 = lookup_or_create_patient.invoke({"phone": "+94799999999", "name": "New Patient", "email": "new@test.com"})
test("new patient created with name",
     p3["patient_id"] is not None and p3["is_new"] == True)
test("new patient name saved correctly",
     p3["name"] == "New Patient")

# Same phone again — should find the newly created patient
p4 = lookup_or_create_patient.invoke({"phone": "+94799999999"})
test("newly created patient found on second lookup",
     p4["patient_id"] == p3["patient_id"] and p4["is_new"] == False)


# ─────────────────────────────────────────────────────────────────────────────
# 5. BOOKING TOOL
# ─────────────────────────────────────────────────────────────────────────────
section("5. Booking Tool")

from app.tools.booking import book_appointment, cancel_appointment, reschedule_appointment

avail = check_availability.invoke({"specialty": "Neurology", "location": "wattala"})
doc   = avail["doctors"][0]
slot1 = doc["slots"][0]
slot2 = doc["slots"][1]
slot3 = doc["slots"][2]

patient = lookup_or_create_patient.invoke({"phone": "+94788888888", "name": "Booking Test"})

# Successful booking
b = book_appointment.invoke({
    "patient_id":       patient["patient_id"],
    "doctor_id":        doc["doctor_id"],
    "slot_id":          slot1["slot_id"],
    "symptoms_summary": "migraines",
})
test("book_appointment returns confirmed",
     b["status"] == "confirmed")
test("appointment_id returned",
     b["appointment_id"] is not None)
test("doctor_name in response",
     b["doctor_name"] is not None)
test("slot_datetime in response",
     b["slot_datetime"] is not None)

appt_id = b["appointment_id"]

# Slot is now locked
b2 = book_appointment.invoke({
    "patient_id":       patient["patient_id"],
    "doctor_id":        doc["doctor_id"],
    "slot_id":          slot1["slot_id"],
    "symptoms_summary": "test double booking",
})
test("double-booking same slot returns failed",
     b2["status"] == "failed")

# Cancel
c = cancel_appointment.invoke({"appointment_id": appt_id})
test("cancel_appointment returns success",
     c["success"] == True)

# Slot is free again after cancel
b3 = book_appointment.invoke({
    "patient_id":       patient["patient_id"],
    "doctor_id":        doc["doctor_id"],
    "slot_id":          slot1["slot_id"],
    "symptoms_summary": "rebook after cancel",
})
test("slot is available again after cancellation",
     b3["status"] == "confirmed")
appt_id2 = b3["appointment_id"]

# Cancel already-cancelled appointment
c2 = cancel_appointment.invoke({"appointment_id": appt_id})
test("cancelling already-cancelled appointment returns error",
     c2["success"] == False)

# Cancel nonexistent
c3 = cancel_appointment.invoke({"appointment_id": "nonexistent-id"})
test("cancelling nonexistent appointment returns error",
     c3["success"] == False)


# ─────────────────────────────────────────────────────────────────────────────
# 6. RESCHEDULE TOOL
# ─────────────────────────────────────────────────────────────────────────────
section("6. Reschedule Tool")

# Book a fresh appointment for reschedule tests
avail2 = check_availability.invoke({"specialty": "Cardiology", "location": "wattala"})
doc2   = avail2["doctors"][0]
s1     = doc2["slots"][0]
s2     = doc2["slots"][1]

patient2 = lookup_or_create_patient.invoke({"phone": "+94777777777", "name": "Reschedule Test"})
bk = book_appointment.invoke({
    "patient_id":       patient2["patient_id"],
    "doctor_id":        doc2["doctor_id"],
    "slot_id":          s1["slot_id"],
    "symptoms_summary": "heart checkup",
})
rid = bk["appointment_id"]

# Reschedule to slot 2
r = reschedule_appointment.invoke({
    "appointment_id": rid,
    "new_slot_id":    s2["slot_id"],
    "new_doctor_id":  doc2["doctor_id"],
})
test("reschedule returns rescheduled status",
     r["status"] == "rescheduled")
test("old_slot_datetime in response",
     r["old_slot_datetime"] is not None)
test("new_slot_datetime in response",
     r["new_slot_datetime"] is not None)
test("appointment_id unchanged after reschedule",
     r["appointment_id"] == rid)

# Verify slot swap in DB
db2 = get_db()
test("old slot freed after reschedule",
     db2.get_slot(s1["slot_id"])["is_booked"] == False)
test("new slot locked after reschedule",
     db2.get_slot(s2["slot_id"])["is_booked"] == True)

# Reschedule to a booked slot — should fail
r2 = reschedule_appointment.invoke({
    "appointment_id": rid,
    "new_slot_id":    s2["slot_id"],  # already booked by this appt
    "new_doctor_id":  doc2["doctor_id"],
})
test("rescheduling to booked slot returns failed",
     r2["status"] == "failed")

# Reschedule nonexistent appointment
r3 = reschedule_appointment.invoke({
    "appointment_id": "nonexistent-id",
    "new_slot_id":    s1["slot_id"],
    "new_doctor_id":  doc2["doctor_id"],
})
test("rescheduling nonexistent appointment returns failed",
     r3["status"] == "failed")


# ─────────────────────────────────────────────────────────────────────────────
# 7. SCHEMAS & UI ACTIONS
# ─────────────────────────────────────────────────────────────────────────────
section("7. Schemas & UIAction Mapping")

from app.models.schemas import UIAction, stage_to_ui_action, BookingState, ChatRequest, ChatResponse

stage_cases = [
    ("intake",      UIAction.SHOW_CHAT),
    ("routing",     UIAction.SHOW_CHAT),
    ("emergency",   UIAction.SHOW_EMERGENCY),
    ("slots_shown", UIAction.SHOW_SLOTS),
    ("collecting",  UIAction.SHOW_PATIENT_FORM),
    ("confirmed",   UIAction.SHOW_PAYMENT),
    ("cancelled",   UIAction.SHOW_CANCELLED),
    ("rescheduled", UIAction.SHOW_RESCHEDULED),
]
for stage, expected_ui in stage_cases:
    test(f"stage '{stage}' → {expected_ui.value}",
         stage_to_ui_action(stage) == expected_ui)

bs = BookingState()
test("BookingState defaults to intake",     bs.stage == "intake")
test("BookingState is_emergency defaults",  bs.is_emergency == False)
test("BookingState all fields present",
     all(hasattr(bs, f) for f in [
         "stage", "is_emergency", "detected_specialty", "preferred_location",
         "selected_slot_id", "selected_slot_datetime", "selected_doctor_id",
         "selected_doctor_name", "patient_id", "appointment_id"
     ]))

# Round-trip
bs2 = BookingState(stage="confirmed", appointment_id="appt-123", patient_id="p-001")
restored = BookingState(**bs2.model_dump())
test("BookingState round-trip (frontend send-back simulation)",
     restored.stage == "confirmed" and restored.appointment_id == "appt-123")

req = ChatRequest(session_id="sess-001", message="hello", history=[], booking_state=BookingState())
test("ChatRequest builds correctly", req.session_id == "sess-001")


# ─────────────────────────────────────────────────────────────────────────────
# 8. DASHBOARD ENDPOINTS (appointments router logic)
# ─────────────────────────────────────────────────────────────────────────────
section("8. Dashboard Appointment Queries")

# Book a few appointments to query
avail3 = check_availability.invoke({"specialty": "General Medicine", "location": "wattala"})
d3 = avail3["doctors"][0]
p5 = lookup_or_create_patient.invoke({"phone": "+94766666666", "name": "Dashboard Test"})

bk1 = book_appointment.invoke({"patient_id": p5["patient_id"], "doctor_id": d3["doctor_id"],
                                "slot_id": d3["slots"][0]["slot_id"], "symptoms_summary": "checkup"})
bk2 = book_appointment.invoke({"patient_id": p5["patient_id"], "doctor_id": d3["doctor_id"],
                                "slot_id": d3["slots"][1]["slot_id"], "symptoms_summary": "followup"})

db3 = get_db()
patient_appts = db3.get_appointments_for_patient(p5["patient_id"])
test("get_appointments_for_patient returns both appointments",
     len(patient_appts) == 2)

confirmed_appts = db3.get_appointments_for_patient(p5["patient_id"], status="confirmed")
test("filter by status=confirmed works",
     len(confirmed_appts) == 2)

cancelled_appts = db3.get_appointments_for_patient(p5["patient_id"], status="cancelled")
test("filter by status=cancelled returns 0",
     len(cancelled_appts) == 0)

all_appts = db3.get_all_appointments()
test("get_all_appointments returns records",
     len(all_appts) > 0)

wattala_appts = db3.get_all_appointments(location="wattala")
test("get_all_appointments filtered by location",
     all(db3.get_doctor(a["doctor_id"])["location"] == "wattala" for a in wattala_appts))


# ─────────────────────────────────────────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────────────────────────────────────────
total = len(passed) + len(failed)
print(f"\n{BOLD}{'═'*55}{R}")
print(f"{BOLD}  RESULTS: {GREEN}{len(passed)} passed{R}{BOLD}  {RED}{len(failed)} failed{R}{BOLD}  / {total} total{R}")
print(f"{BOLD}{'═'*55}{R}")

if failed:
    print(f"\n{RED}{BOLD}  Failed tests:{R}")
    for name in failed:
        print(f"  {RED}• {name}{R}")
    print()
    sys.exit(1)
else:
    print(f"\n{GREEN}{BOLD}  All tests passed ✅{R}\n")
    sys.exit(0)
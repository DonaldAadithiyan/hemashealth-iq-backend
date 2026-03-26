"""
mock_db.py — In-memory placeholder database.

Replaces Supabase during development. The tool files (availability.py,
booking.py, patient.py) import get_db() from here instead of talking to
Supabase directly. When your Supabase DB is ready, you only need to update
this one file (or swap the import in each tool).

Structure mirrors the real Supabase tables exactly.
"""

from datetime import datetime, timedelta, timezone
from copy import deepcopy
import uuid

# ── Helpers ───────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

def _dt(days_ahead: int, hour: int) -> str:
    """Return an ISO datetime string N days from today at a given hour (UTC+5:30)."""
    base = datetime.now(timezone.utc).replace(hour=hour - 5, minute=30, second=0, microsecond=0)
    return (base + timedelta(days=days_ahead)).isoformat()

def _uid() -> str:
    return str(uuid.uuid4())

# ── Static seed data ──────────────────────────────────────────────────────────

_DOCTORS = [
    {"id": "doc-001", "name": "Dr. Nimal Perera",         "specialty": "Cardiology",               "location": "wattala",          "is_active": True},
    {"id": "doc-002", "name": "Dr. Shalini Fernando",     "specialty": "Cardiology",               "location": "thalawathugoda",   "is_active": True},
    {"id": "doc-003", "name": "Dr. Ruwan Jayasinghe",     "specialty": "Neurology",                "location": "wattala",          "is_active": True},
    {"id": "doc-004", "name": "Dr. Amara Silva",          "specialty": "Neurology",                "location": "thalawathugoda",   "is_active": True},
    {"id": "doc-005", "name": "Dr. Priyanka Gunasekara",  "specialty": "General Medicine",         "location": "wattala",          "is_active": True},
    {"id": "doc-006", "name": "Dr. Tharaka Bandara",      "specialty": "General Medicine",         "location": "thalawathugoda",   "is_active": True},
    {"id": "doc-007", "name": "Dr. Dilini Wickramasinghe","specialty": "Orthopedics",              "location": "wattala",          "is_active": True},
    {"id": "doc-008", "name": "Dr. Kasun Rajapaksa",      "specialty": "Gastroenterology",         "location": "wattala",          "is_active": True},
    {"id": "doc-009", "name": "Dr. Nadeesha Herath",      "specialty": "Obstetrics & Gynecology",  "location": "thalawathugoda",   "is_active": True},
    {"id": "doc-010", "name": "Dr. Roshan Mendis",        "specialty": "Dermatology",              "location": "wattala",          "is_active": True},
    {"id": "doc-011", "name": "Dr. Chamara De Silva",     "specialty": "ENT",                      "location": "wattala",          "is_active": True},
    {"id": "doc-012", "name": "Dr. Iresha Wijesekara",    "specialty": "Ophthalmology",            "location": "thalawathugoda",   "is_active": True},
    {"id": "doc-013", "name": "Dr. Suresh Karunaratne",   "specialty": "Endocrinology",            "location": "wattala",          "is_active": True},
    {"id": "doc-014", "name": "Dr. Malika Dissanayake",   "specialty": "Pediatrics",               "location": "thalawathugoda",   "is_active": True},
    {"id": "doc-015", "name": "Dr. Asitha Fonseka",       "specialty": "Urology",                  "location": "wattala",          "is_active": True},
]

def _generate_slots() -> list[dict]:
    """Generate hourly slots 9am–4pm for all doctors for the next 7 days."""
    slots = []
    slot_counter = 1
    for doc in _DOCTORS:
        for day in range(1, 8):
            for hour in range(9, 17):
                slots.append({
                    "id":            f"slot-{slot_counter:04d}",
                    "doctor_id":     doc["id"],
                    "slot_datetime": _dt(day, hour),
                    "is_booked":     False,
                })
                slot_counter += 1
    return slots

_SLOTS: list[dict] = _generate_slots()

_PATIENTS: list[dict] = [
    {
        "id":         "patient-001",
        "name":       "Kamal Jayawardena",
        "phone":      "+94771234567",
        "email":      "kamal@example.com",
        "created_at": _now(),
    },
    {
        "id":         "patient-002",
        "name":       "Nimali Perera",
        "phone":      "+94779876543",
        "email":      "nimali@example.com",
        "created_at": _now(),
    },
]

_APPOINTMENTS: list[dict] = [
    {
        "id":               "appt-001",
        "patient_id":       "patient-001",
        "doctor_id":        "doc-001",
        "slot_id":          "slot-0001",
        "status":           "confirmed",
        "symptoms_summary": "Chest pain and shortness of breath",
        "created_at":       _now(),
    },
]
# Mark that slot as booked in the slots list
for s in _SLOTS:
    if s["id"] == "slot-0001":
        s["is_booked"] = True
        break


# ── DB class — mimics the Supabase client interface used by the tools ─────────

class MockDB:
    """
    Thin in-memory store. Tools call the same methods they will call on the
    real Supabase client, so swapping is a one-line import change.
    """

    def __init__(self):
        # Deep-copy so tests don't bleed into each other
        self.doctors      = deepcopy(_DOCTORS)
        self.slots        = deepcopy(_SLOTS)
        self.patients     = deepcopy(_PATIENTS)
        self.appointments = deepcopy(_APPOINTMENTS)

    # ── Doctors ──────────────────────────────────────────────────────────────

    def get_doctors(
        self,
        specialty: str | None = None,
        location:  str | None = None,
        active_only: bool = True,
    ) -> list[dict]:
        result = self.doctors
        if active_only:
            result = [d for d in result if d["is_active"]]
        if specialty:
            result = [d for d in result if d["specialty"] == specialty]
        if location:
            result = [d for d in result if d["location"] == location.lower()]
        return deepcopy(result)

    def get_doctor(self, doctor_id: str) -> dict | None:
        for d in self.doctors:
            if d["id"] == doctor_id:
                return deepcopy(d)
        return None

    # ── Slots ─────────────────────────────────────────────────────────────────

    def get_available_slots(
        self,
        doctor_ids: list[str],
        after:  str | None = None,
        before: str | None = None,
    ) -> list[dict]:
        result = [
            s for s in self.slots
            if s["doctor_id"] in doctor_ids and not s["is_booked"]
        ]
        if after:
            result = [s for s in result if s["slot_datetime"] >= after]
        if before:
            result = [s for s in result if s["slot_datetime"] <= before]
        return deepcopy(sorted(result, key=lambda s: s["slot_datetime"]))

    def get_slot(self, slot_id: str) -> dict | None:
        for s in self.slots:
            if s["id"] == slot_id:
                return deepcopy(s)
        return None

    def mark_slot_booked(self, slot_id: str, booked: bool = True) -> bool:
        for s in self.slots:
            if s["id"] == slot_id:
                s["is_booked"] = booked
                return True
        return False

    def get_slots_for_doctor_on_date(self, doctor_id: str, date: str) -> list[dict]:
        """date: 'YYYY-MM-DD'"""
        return deepcopy([
            s for s in self.slots
            if s["doctor_id"] == doctor_id and s["slot_datetime"].startswith(date)
        ])

    # ── Patients ──────────────────────────────────────────────────────────────

    def find_patient_by_phone(self, phone: str) -> dict | None:
        phone = phone.strip().replace(" ", "")
        for p in self.patients:
            if p["phone"].replace(" ", "") == phone:
                return deepcopy(p)
        return None

    def find_patient_by_id(self, patient_id: str) -> dict | None:
        for p in self.patients:
            if p["id"] == patient_id:
                return deepcopy(p)
        return None

    def create_patient(self, name: str, phone: str, email: str | None) -> dict:
        patient = {
            "id":         _uid(),
            "name":       name,
            "phone":      phone.strip().replace(" ", ""),
            "email":      email,
            "created_at": _now(),
        }
        self.patients.append(patient)
        return deepcopy(patient)

    # ── Appointments ──────────────────────────────────────────────────────────

    def create_appointment(
        self,
        patient_id:       str,
        doctor_id:        str,
        slot_id:          str,
        symptoms_summary: str,
    ) -> dict:
        appt = {
            "id":               _uid(),
            "patient_id":       patient_id,
            "doctor_id":        doctor_id,
            "slot_id":          slot_id,
            "status":           "confirmed",
            "symptoms_summary": symptoms_summary,
            "created_at":       _now(),
        }
        self.appointments.append(appt)
        return deepcopy(appt)

    def get_appointment(self, appointment_id: str) -> dict | None:
        for a in self.appointments:
            if a["id"] == appointment_id:
                return deepcopy(a)
        return None

    def get_appointments_for_patient(
        self, patient_id: str, status: str | None = None
    ) -> list[dict]:
        result = [a for a in self.appointments if a["patient_id"] == patient_id]
        if status:
            result = [a for a in result if a["status"] == status]
        return deepcopy(sorted(result, key=lambda a: a["created_at"], reverse=True))

    def get_appointments_for_doctor_on_date(
        self, doctor_id: str, date: str
    ) -> list[dict]:
        slot_ids_on_date = {
            s["id"] for s in self.slots
            if s["doctor_id"] == doctor_id and s["slot_datetime"].startswith(date)
        }
        return deepcopy([
            a for a in self.appointments
            if a["slot_id"] in slot_ids_on_date and a["status"] != "cancelled"
        ])

    def get_all_appointments(
        self,
        location: str | None = None,
        status:   str | None = None,
        limit:    int = 50,
    ) -> list[dict]:
        result = self.appointments
        if status:
            result = [a for a in result if a["status"] == status]
        if location:
            doctor_ids_at_location = {
                d["id"] for d in self.doctors if d["location"] == location.lower()
            }
            result = [a for a in result if a["doctor_id"] in doctor_ids_at_location]
        result = sorted(result, key=lambda a: a["created_at"], reverse=True)
        return deepcopy(result[:limit])

    def update_appointment_status(self, appointment_id: str, status: str) -> bool:
        for a in self.appointments:
            if a["id"] == appointment_id:
                a["status"] = status
                return True
        return False


# ── Singleton ─────────────────────────────────────────────────────────────────
# All tools import this one instance.
# Replace this with get_supabase() when your DB is ready.

_db_instance: MockDB | None = None

def get_db() -> MockDB:
    global _db_instance
    if _db_instance is None:
        _db_instance = MockDB()
    return _db_instance
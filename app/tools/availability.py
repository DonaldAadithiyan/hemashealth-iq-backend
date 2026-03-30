"""
availability.py — Check real-time doctor availability.

Data source: app/db/supabase.py
Availability is computed from doctor_availability_rules + exceptions,
not from a slots table (your schema has no slots table).
"""

from datetime import datetime, timedelta, timezone
from langchain_core.tools import tool
from app.db.supabase import get_doctors, get_available_slots


@tool
def check_availability(specialty: str, location: str, date: str | None = None) -> dict:
    """
    Check available appointment slots for a given specialty and hospital location.

    Args:
        specialty: Medical specialty e.g. "Cardiology", "General Medicine"
        location:  Hospital location — "wattala" or "thalawathugoda"
        date:      Optional ISO date "YYYY-MM-DD". Defaults to next 7 days.

    Returns:
        doctors: list of { doctor_id, doctor_name, specialty, location, slots: [...] }
                 Each slot has: slot_id, datetime
        total_slots_found: int
    """
    doctors = get_doctors(specialty=specialty, location=location.lower().strip())
    if not doctors:
        return {"doctors": [], "total_slots_found": 0}

    doctor_ids = [d["id"] for d in doctors]

    now = datetime.now(timezone.utc)
    if date:
        after  = f"{date}T00:00:00+00:00"
        before = f"{date}T23:59:59+00:00"
    else:
        after  = now.isoformat()
        before = (now + timedelta(days=7)).isoformat()

    all_slots = get_available_slots(doctor_ids, after=after, before=before)

    # Group by doctor
    slots_by_doctor: dict[str, list] = {d["id"]: [] for d in doctors}
    for slot in all_slots:
        did = slot["doctor_id"]
        if did in slots_by_doctor:
            slots_by_doctor[did].append({
                "slot_id":  slot["slot_id"],
                "datetime": slot["slot_datetime"],
            })

    result_doctors = []
    for doctor in doctors:
        doc_slots = slots_by_doctor.get(doctor["id"], [])
        if doc_slots:
            result_doctors.append({
                "doctor_id":   doctor["id"],
                "doctor_name": doctor["name"],
                "specialty":   doctor["specialty"],
                "location":    doctor["location"],
                "slots":       doc_slots[:5],
            })

    return {
        "doctors":           result_doctors,
        "total_slots_found": len(all_slots),
    }
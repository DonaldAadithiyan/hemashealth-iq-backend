"""
availability.py — Check real-time doctor availability.

Data source: mock_db.get_db()

TO SWITCH TO SUPABASE:
  Replace `from app.db.mock_db import get_db` with `from app.db.supabase import get_supabase`
  and rewrite the three db.* calls below as Supabase queries.
  The tool's return shape stays identical either way.
"""

from datetime import datetime, timedelta, timezone
from langchain_core.tools import tool
from app.db.mock_db import get_db


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
        total_slots_found: int
    """
    db = get_db()

    doctors = db.get_doctors(specialty=specialty, location=location.lower().strip())
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

    all_slots = db.get_available_slots(doctor_ids, after=after, before=before)

    # Group slots by doctor
    slots_by_doctor: dict[str, list] = {d["id"]: [] for d in doctors}
    for slot in all_slots:
        did = slot["doctor_id"]
        if did in slots_by_doctor:
            slots_by_doctor[did].append(
                {"slot_id": slot["id"], "datetime": slot["slot_datetime"]}
            )

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
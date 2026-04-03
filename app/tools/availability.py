"""
availability.py — Check real-time doctor availability with fallback to related specialties.

If no doctors are found for the requested specialty + location, automatically tries:
  1. Related specialties at the same location
  2. The same specialty at the other location
  3. Related specialties at the other location

Returns a result that tells the agent exactly what was found and why,
so it can explain the recommendation clearly to the patient.
"""

from datetime import datetime, timedelta, timezone
from langchain_core.tools import tool
from app.db.supabase import get_doctors, get_available_slots


# ── Related specialty map ─────────────────────────────────────────────────────
# For each specialty, defines fallback specialties in order of preference.
# General Medicine is the universal fallback for everything.

RELATED_SPECIALTIES: dict[str, list[str]] = {
    "Cardiology":              ["General Medicine"],
    "Neurology":               ["General Medicine"],
    "Orthopedics":             ["General Medicine"],
    "Gastroenterology":        ["General Medicine"],
    "Endocrinology":           ["General Medicine"],
    "Urology":                 ["General Medicine"],
    "Dermatology":             ["General Medicine"],
    "ENT":                     ["General Medicine"],
    "Ophthalmology":           ["General Medicine"],
    "Obstetrics & Gynecology": ["General Medicine"],
    "Pediatrics":              ["General Medicine"],
    "General Medicine":        [],   # no further fallback
}

OTHER_LOCATION = {
    "wattala":       "thalawathugoda",
    "thalawathugoda":"wattala",
}


def _fetch_doctors_with_slots(
    specialty: str,
    location: str,
    after: str,
    before: str,
) -> list[dict]:
    """
    Fetch doctors of a given specialty at a location who have available slots.
    Returns a list of doctor dicts with their slots attached.
    """
    doctors = get_doctors(specialty=specialty, location=location)
    if not doctors:
        return []

    doctor_ids = [d["id"] for d in doctors]
    all_slots  = get_available_slots(doctor_ids, after=after, before=before)

    slots_by_doctor: dict[str, list] = {d["id"]: [] for d in doctors}
    for slot in all_slots:
        did = slot["doctor_id"]
        if did in slots_by_doctor:
            # slot_id key differs between Supabase ("slot_id") and mock_db ("id")
            sid = slot.get("slot_id") or slot.get("id")
            slots_by_doctor[did].append({
                "slot_id":  sid,
                "datetime": slot["slot_datetime"],
            })

    result = []
    for doctor in doctors:
        doc_slots = slots_by_doctor.get(doctor["id"], [])
        if doc_slots:
            result.append({
                "doctor_id":   doctor["id"],
                "doctor_name": doctor["name"],
                "specialty":   doctor["specialty"],
                "location":    doctor["location"],
                "slots":       doc_slots[:5],
            })
    return result


@tool
def check_availability(specialty: str, location: str, date: str | None = None) -> dict:
    """
    Check available appointment slots for a given specialty and hospital location.
    If no slots are found, automatically falls back to related specialties and/or
    the other hospital location before giving up.

    Args:
        specialty: Medical specialty e.g. "Cardiology", "General Medicine"
        location:  Hospital location — "wattala" or "thalawathugoda"
        date:      Optional ISO date "YYYY-MM-DD". Defaults to next 7 days.

    Returns:
        doctors:            list of available doctors with slots
        total_slots_found:  int
        searched_specialty: str  — what specialty was actually found (may differ from requested)
        searched_location:  str  — what location was actually found (may differ from requested)
        fallback_used:      bool — True if a fallback specialty or location was used
        fallback_reason:    str  — human-readable explanation of why fallback was used
                                   e.g. "No Cardiology doctors available at Wattala.
                                         Showing General Medicine doctors instead."
    """
    location  = location.lower().strip()
    now       = datetime.now(timezone.utc)

    if date:
        after  = f"{date}T00:00:00+00:00"
        before = f"{date}T23:59:59+00:00"
    else:
        after  = now.isoformat()
        before = (now + timedelta(days=7)).isoformat()

    other_loc = OTHER_LOCATION.get(location, "")
    related   = RELATED_SPECIALTIES.get(specialty, ["General Medicine"])

    # ── 1. Try exact match: requested specialty + requested location ──────────
    doctors = _fetch_doctors_with_slots(specialty, location, after, before)
    if doctors:
        return {
            "doctors":            doctors,
            "total_slots_found":  sum(len(d["slots"]) for d in doctors),
            "searched_specialty": specialty,
            "searched_location":  location,
            "fallback_used":      False,
            "fallback_reason":    "",
        }

    # ── 2. Try related specialties at same location ───────────────────────────
    for alt_specialty in related:
        doctors = _fetch_doctors_with_slots(alt_specialty, location, after, before)
        if doctors:
            loc_label = location.capitalize()
            return {
                "doctors":            doctors,
                "total_slots_found":  sum(len(d["slots"]) for d in doctors),
                "searched_specialty": alt_specialty,
                "searched_location":  location,
                "fallback_used":      True,
                "fallback_reason": (
                    f"No {specialty} doctors available at {loc_label} — showing {alt_specialty} at {loc_label} instead."
                ),
            }

    # ── 3. Try same specialty at other location ───────────────────────────────
    if other_loc:
        doctors = _fetch_doctors_with_slots(specialty, other_loc, after, before)
        if doctors:
            loc_label       = location.capitalize()
            other_loc_label = other_loc.capitalize()
            return {
                "doctors":            doctors,
                "total_slots_found":  sum(len(d["slots"]) for d in doctors),
                "searched_specialty": specialty,
                "searched_location":  other_loc,
                "fallback_used":      True,
                "fallback_reason": (
                    f"No {specialty} doctors available at {loc_label} — showing {specialty} at {other_loc_label} instead."
                ),
            }

    # ── 4. Try related specialties at other location ──────────────────────────
    if other_loc:
        for alt_specialty in related:
            doctors = _fetch_doctors_with_slots(alt_specialty, other_loc, after, before)
            if doctors:
                loc_label       = location.capitalize()
                other_loc_label = other_loc.capitalize()
                return {
                    "doctors":            doctors,
                    "total_slots_found":  sum(len(d["slots"]) for d in doctors),
                    "searched_specialty": alt_specialty,
                    "searched_location":  other_loc,
                    "fallback_used":      True,
                    "fallback_reason": (
                        f"No {specialty} doctors available at either location — showing {alt_specialty} at {other_loc_label}."
                    ),
                }

    # ── 5. Truly nothing available ────────────────────────────────────────────
    return {
        "doctors":            [],
        "total_slots_found":  0,
        "searched_specialty": specialty,
        "searched_location":  location,
        "fallback_used":      False,
        "fallback_reason": (
            f"No doctors are currently available for {specialty} at either Hemas Hospital location. "
            f"Please call Hemas Hospitals directly at +94 11 788 8888 to speak with our team."
        ),
    }
"""
patient.py — Patient lookup, creation, and history retrieval.

Feature 1 (symptom progression): lookup_or_create_patient now returns
last_visit data for returning patients so the agent can detect recurring symptoms.
"""

from langchain_core.tools import tool
from app.db.supabase import (
    find_patient_by_phone,
    create_patient,
    get_last_appointment_for_patient,
)


@tool
def lookup_or_create_patient(
    phone: str,
    name:  str | None = None,
    email: str | None = None,
) -> dict:
    """
    Look up a patient by phone number. If found, return their record plus
    their last appointment (for symptom progression tracking).
    If not found and name is provided, create a new user + patient record.

    Args:
        phone: Patient's phone number
        name:  Full name — required only for new patient registration
        email: Email address — optional

    Returns:
        patient_id:  str | None
        user_id:     str | None
        name:        str | None
        phone:       str
        email:       str | None
        is_new:      bool
        error:       str | None
        last_visit:  dict | None  — only for returning patients:
                       { appointment_date, reason_for_visit, doctor_name, specialty }
                       Use this to detect recurring/worsening symptoms.
    """
    existing = find_patient_by_phone(phone)
    if existing:
        # Fetch last visit for symptom progression tracking
        last_visit = get_last_appointment_for_patient(existing["id"])
        return {
            "patient_id": existing["id"],
            "user_id":    existing["user_id"],
            "name":       existing["name"],
            "phone":      existing["phone"],
            "email":      existing.get("email"),
            "is_new":     False,
            "error":      None,
            "last_visit": last_visit,
        }

    if not name:
        return {
            "patient_id": None,
            "user_id":    None,
            "name":       None,
            "phone":      phone,
            "email":      None,
            "is_new":     False,
            "error":      "Patient not found. Please provide your full name to register.",
            "last_visit": None,
        }

    new_patient = create_patient(name=name, phone=phone, email=email)
    return {
        "patient_id": new_patient["id"],
        "user_id":    new_patient["user_id"],
        "name":       new_patient["name"],
        "phone":      new_patient["phone"],
        "email":      new_patient.get("email"),
        "is_new":     True,
        "error":      None,
        "last_visit": None,
    }
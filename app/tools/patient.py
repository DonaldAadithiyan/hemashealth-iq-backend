"""
patient.py — Patient lookup and creation against the real Supabase schema.

In your schema, patient info (name, phone, email) lives in the users table.
The patients table holds medical details and links via user_id.
"""

from langchain_core.tools import tool
from app.db.supabase import find_patient_by_phone, create_patient


@tool
def lookup_or_create_patient(
    phone: str,
    name:  str | None = None,
    email: str | None = None,
) -> dict:
    """
    Look up a patient by phone number. If found, return their record.
    If not found and name is provided, create a new user + patient record.

    Args:
        phone: Patient's phone number (unique identifier — lives in users table)
        name:  Full name — required only for new patient registration
        email: Email address — optional

    Returns:
        patient_id: str | None   (patients.id)
        user_id:    str | None   (users.id)
        name:       str | None
        phone:      str
        email:      str | None
        is_new:     bool
        error:      str | None
    """
    existing = find_patient_by_phone(phone)
    if existing:
        return {
            "patient_id": existing["id"],
            "user_id":    existing["user_id"],
            "name":       existing["name"],
            "phone":      existing["phone"],
            "email":      existing.get("email"),
            "is_new":     False,
            "error":      None,
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
    }
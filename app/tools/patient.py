"""
patient.py — Patient lookup and creation.

Data source: mock_db.get_db()

TO SWITCH TO SUPABASE:
  Replace `from app.db.mock_db import get_db` with `from app.db.supabase import get_supabase`
  and rewrite the db.* calls as Supabase queries.
  The tool's return shape stays identical either way.
"""

from langchain_core.tools import tool
from app.db.mock_db import get_db


@tool
def lookup_or_create_patient(
    phone: str,
    name:  str | None = None,
    email: str | None = None,
) -> dict:
    """
    Look up a patient by phone number. If found, return their record.
    If not found and name is provided, create a new patient record.

    Args:
        phone: Patient's phone number (used as unique identifier)
        name:  Full name — required only for new patient registration
        email: Email address — optional

    Returns:
        patient_id: str | None
        name:       str | None
        phone:      str
        email:      str | None
        is_new:     bool
        error:      str | None
    """
    db = get_db()

    existing = db.find_patient_by_phone(phone)
    if existing:
        return {
            "patient_id": existing["id"],
            "name":       existing["name"],
            "phone":      existing["phone"],
            "email":      existing.get("email"),
            "is_new":     False,
            "error":      None,
        }

    if not name:
        return {
            "patient_id": None,
            "name":       None,
            "phone":      phone,
            "email":      None,
            "is_new":     False,
            "error":      "Patient not found. Please provide the patient's full name to register.",
        }

    new_patient = db.create_patient(name=name, phone=phone, email=email)
    return {
        "patient_id": new_patient["id"],
        "name":       new_patient["name"],
        "phone":      new_patient["phone"],
        "email":      new_patient.get("email"),
        "is_new":     True,
        "error":      None,
    }
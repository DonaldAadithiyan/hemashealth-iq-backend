"""
patient.py — Patient lookup, creation, and history retrieval.

Lookup priority:
  1. user_id (Supabase Auth UUID) — fastest, most reliable, use when logged in
  2. phone number — fallback for unauthenticated users
  3. create new patient — when neither matches and name is provided
"""

from langchain_core.tools import tool
from app.db.supabase import (
    find_patient_by_user_id,
    find_patient_by_phone,
    create_patient,
    get_last_appointment_for_patient,
)


@tool
def lookup_or_create_patient(
    user_id: str | None = None,
    phone:   str | None = None,
    name:    str | None = None,
    email:   str | None = None,
) -> dict:
    """
    Look up a patient by user_id (preferred) or phone number (fallback).
    If not found and name is provided, create a new record.

    Args:
        user_id: Supabase Auth user UUID — use this when the user is logged in.
                 This is the preferred lookup method. If provided, phone is ignored.
        phone:   Phone number — fallback when user_id is not available.
        name:    Full name — required only for new patient registration.
        email:   Email address — optional, for new registrations.

    Returns:
        patient_id:  str | None
        user_id:     str | None
        name:        str | None
        phone:       str | None
        is_new:      bool
        error:       str | None
        last_visit:  dict | None  — { appointment_date, reason_for_visit, doctor_name, specialty }
    """

    existing = None

    # ── Priority 1: look up by user_id ────────────────────────────────────
    if user_id:
        existing = find_patient_by_user_id(user_id)

    # ── Priority 2: look up by phone ──────────────────────────────────────
    if existing is None and phone:
        existing = find_patient_by_phone(phone)

    # ── Found — return with last visit ────────────────────────────────────
    if existing:
        last_visit = get_last_appointment_for_patient(existing["id"])
        return {
            "patient_id": existing["id"],
            "user_id":    existing["user_id"],
            "name":       existing["name"],
            "phone":      existing.get("phone"),
            "is_new":     False,
            "error":      None,
            "last_visit": last_visit,
        }

    # ── Not found — need name to register ────────────────────────────────
    if not name:
        return {
            "patient_id": None,
            "user_id":    None,
            "name":       None,
            "phone":      phone,
            "is_new":     False,
            "error":      "Patient not found. Please provide your full name to register.",
            "last_visit": None,
        }

    # ── Create new patient ────────────────────────────────────────────────
    new_patient = create_patient(name=name, phone=phone or "", email=email)
    return {
        "patient_id": new_patient["id"],
        "user_id":    new_patient["user_id"],
        "name":       new_patient["name"],
        "phone":      new_patient.get("phone"),
        "is_new":     True,
        "error":      None,
        "last_visit": None,
    }
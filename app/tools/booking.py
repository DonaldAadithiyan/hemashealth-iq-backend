"""
booking.py — Book, cancel, and reschedule appointments against the real Supabase schema.

Key differences from mock_db version:
  - No slots table. Booking = inserting an appointment row with appointment_date.
  - Conflict check = query for existing confirmed/reserved/paid appointment at same datetime.
  - slot_id is a synthetic string: "doctor_id::YYYY-MM-DDTHH:MM"
  - Rescheduling = updating appointment_date + doctor_id on the existing row.
"""

from langchain_core.tools import tool
from app.db.supabase import (
    create_appointment,
    get_appointment,
    update_appointment_status,
    reschedule_appointment_db,
    get_doctor,
    parse_synthetic_slot_id,
)


@tool
def book_appointment(
    patient_id:       str,
    doctor_id:        str,
    slot_id:          str,
    symptoms_summary: str,
) -> dict:
    """
    Book an appointment. slot_id is the synthetic ID returned by check_availability
    in the format "doctor_id::YYYY-MM-DDTHH:MM".

    Args:
        patient_id:       patients.id UUID
        doctor_id:        doctors.id UUID
        slot_id:          synthetic slot ID from check_availability
        symptoms_summary: short description of the patient's reason for visit

    Returns:
        appointment_id: str | None
        status:         "confirmed" | "failed"
        slot_datetime:  str (ISO)
        doctor_name:    str
        error:          str | None
    """
    # Parse the slot_id to get the actual datetime
    try:
        parsed_doctor_id, appointment_datetime = parse_synthetic_slot_id(slot_id)
    except ValueError as e:
        return {"appointment_id": None, "status": "failed", "error": str(e)}

    # Use the datetime from the slot_id (trust it over doctor_id arg for safety)
    # Append seconds for full ISO format
    if len(appointment_datetime) == 16:
        appointment_datetime += ":00+00:00"

    appt = create_appointment(
        patient_id=patient_id,
        doctor_id=doctor_id,
        appointment_date=appointment_datetime,
        reason_for_visit=symptoms_summary,
    )

    if appt is None:
        return {
            "appointment_id": None,
            "status":         "failed",
            "error":          "That slot was just booked by someone else. Please choose another.",
        }

    doctor     = get_doctor(doctor_id)
    doctor_name = doctor["name"] if doctor else "your doctor"

    return {
        "appointment_id": appt["id"],
        "status":         "confirmed",
        "slot_datetime":  appt["appointment_date"],
        "doctor_name":    doctor_name,
        "error":          None,
    }


@tool
def cancel_appointment(appointment_id: str) -> dict:
    """
    Cancel an existing appointment.

    Args:
        appointment_id: appointments.id UUID

    Returns:
        success: bool
        error:   str | None
    """
    appt = get_appointment(appointment_id)
    if not appt:
        return {"success": False, "error": "Appointment not found."}
    if appt["status"] == "cancelled":
        return {"success": False, "error": "Appointment is already cancelled."}

    update_appointment_status(appointment_id, "cancelled")
    return {"success": True, "error": None}


@tool
def reschedule_appointment(
    appointment_id: str,
    new_slot_id:    str,
    new_doctor_id:  str,
) -> dict:
    """
    Reschedule an existing appointment to a new slot atomically.
    new_slot_id is the synthetic ID from check_availability: "doctor_id::YYYY-MM-DDTHH:MM"

    Args:
        appointment_id: UUID of the existing appointment
        new_slot_id:    synthetic slot ID of the new slot
        new_doctor_id:  doctor UUID for the new slot

    Returns:
        appointment_id:     str  (same ID, updated)
        status:             "rescheduled" | "failed"
        old_slot_datetime:  str
        new_slot_datetime:  str
        doctor_name:        str
        error:              str | None
    """
    appt = get_appointment(appointment_id)
    if not appt:
        return {"appointment_id": None, "status": "failed", "error": "Appointment not found."}
    if appt["status"] == "cancelled":
        return {"appointment_id": None, "status": "failed",
                "error": "Cannot reschedule a cancelled appointment."}

    try:
        _, new_datetime = parse_synthetic_slot_id(new_slot_id)
    except ValueError as e:
        return {"appointment_id": None, "status": "failed", "error": str(e)}

    if len(new_datetime) == 16:
        new_datetime += ":00+00:00"

    old_datetime = appt["appointment_date"]

    reschedule_appointment_db(
        appointment_id=appointment_id,
        new_appointment_date=new_datetime,
        new_doctor_id=new_doctor_id,
    )

    doctor      = get_doctor(new_doctor_id)
    doctor_name = doctor["name"] if doctor else "your doctor"

    return {
        "appointment_id":    appointment_id,
        "status":            "rescheduled",
        "old_slot_datetime": old_datetime,
        "new_slot_datetime": new_datetime,
        "doctor_name":       doctor_name,
        "error":             None,
    }
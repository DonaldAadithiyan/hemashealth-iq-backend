"""
booking.py — Create, cancel, and reschedule appointments.

Data source: mock_db.get_db()

TO SWITCH TO SUPABASE:
  Replace `from app.db.mock_db import get_db` with `from app.db.supabase import get_supabase`
  and rewrite the db.* calls as Supabase queries.
  The tool return shapes stay identical either way.
"""

from langchain_core.tools import tool
from app.db.mock_db import get_db


@tool
def book_appointment(
    patient_id:       str,
    doctor_id:        str,
    slot_id:          str,
    symptoms_summary: str,
) -> dict:
    """
    Confirm and create an appointment. Marks the slot as booked atomically.

    Args:
        patient_id:       UUID of the patient
        doctor_id:        UUID of the doctor
        slot_id:          UUID of the chosen slot
        symptoms_summary: Short plain-text summary of the patient's symptoms

    Returns:
        appointment_id: str | None
        status:         "confirmed" | "failed"
        slot_datetime:  str (ISO)
        doctor_name:    str
        error:          str | None
    """
    db = get_db()

    slot = db.get_slot(slot_id)
    if not slot:
        return {"appointment_id": None, "status": "failed",
                "error": "Slot not found."}
    if slot["is_booked"]:
        return {"appointment_id": None, "status": "failed",
                "error": "That slot was just booked by someone else. Please choose another."}

    appt = db.create_appointment(
        patient_id=patient_id,
        doctor_id=doctor_id,
        slot_id=slot_id,
        symptoms_summary=symptoms_summary,
    )
    db.mark_slot_booked(slot_id, booked=True)

    doctor = db.get_doctor(doctor_id)
    doctor_name = doctor["name"] if doctor else "your doctor"

    return {
        "appointment_id": appt["id"],
        "status":         "confirmed",
        "slot_datetime":  slot["slot_datetime"],
        "doctor_name":    doctor_name,
        "error":          None,
    }


@tool
def cancel_appointment(appointment_id: str) -> dict:
    """
    Cancel an existing appointment and free up its slot.

    Args:
        appointment_id: UUID of the appointment to cancel

    Returns:
        success: bool
        error:   str | None
    """
    db = get_db()

    appt = db.get_appointment(appointment_id)
    if not appt:
        return {"success": False, "error": "Appointment not found."}
    if appt["status"] == "cancelled":
        return {"success": False, "error": "Appointment is already cancelled."}

    db.update_appointment_status(appointment_id, "cancelled")
    db.mark_slot_booked(appt["slot_id"], booked=False)

    return {"success": True, "error": None}


@tool
def reschedule_appointment(
    appointment_id: str,
    new_slot_id:    str,
    new_doctor_id:  str,
) -> dict:
    """
    Reschedule an existing appointment to a new slot atomically.
    Cancels the old slot, books the new one, updates the appointment record.

    Args:
        appointment_id: UUID of the existing appointment to reschedule
        new_slot_id:    UUID of the new slot to move to
        new_doctor_id:  UUID of the doctor for the new slot
                        (may be the same doctor or a different one)

    Returns:
        appointment_id:     str  (same ID, updated)
        status:             "rescheduled" | "failed"
        old_slot_datetime:  str (ISO) — what was freed
        new_slot_datetime:  str (ISO) — what was booked
        doctor_name:        str
        error:              str | None
    """
    db = get_db()

    # 1. Fetch the existing appointment
    appt = db.get_appointment(appointment_id)
    if not appt:
        return {"appointment_id": None, "status": "failed",
                "error": "Appointment not found."}
    if appt["status"] == "cancelled":
        return {"appointment_id": None, "status": "failed",
                "error": "Cannot reschedule a cancelled appointment."}

    # 2. Check the new slot is available
    new_slot = db.get_slot(new_slot_id)
    if not new_slot:
        return {"appointment_id": None, "status": "failed",
                "error": "New slot not found."}
    if new_slot["is_booked"]:
        return {"appointment_id": None, "status": "failed",
                "error": "That slot was just taken by someone else. Please choose another."}

    # 3. Free the old slot
    old_slot = db.get_slot(appt["slot_id"])
    old_slot_datetime = old_slot["slot_datetime"] if old_slot else None
    db.mark_slot_booked(appt["slot_id"], booked=False)

    # 4. Update appointment to new slot + doctor
    db.update_appointment_slot(
        appointment_id=appointment_id,
        new_slot_id=new_slot_id,
        new_doctor_id=new_doctor_id,
    )

    # 5. Mark new slot as booked
    db.mark_slot_booked(new_slot_id, booked=True)

    doctor = db.get_doctor(new_doctor_id)
    doctor_name = doctor["name"] if doctor else "your doctor"

    return {
        "appointment_id":    appointment_id,
        "status":            "rescheduled",
        "old_slot_datetime": old_slot_datetime,
        "new_slot_datetime": new_slot["slot_datetime"],
        "doctor_name":       doctor_name,
        "error":             None,
    }
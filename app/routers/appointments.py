"""
Appointment endpoints consumed by the Next.js dashboards.

Data source: mock_db.get_db()

TO SWITCH TO SUPABASE:
  Replace `from app.db.mock_db import get_db` with your Supabase client
  and rewrite the db.* calls as Supabase queries.

Note: Appointment creation is handled by the AI agent (book_appointment tool).
These endpoints are read + cancel only, for the dashboard UIs.
"""

from datetime import date as dt_date
from fastapi import APIRouter, HTTPException, Query
from app.db.mock_db import get_db
from app.models.schemas import AppointmentOut, CancelRequest, RescheduleRequest, AppointmentStatus

router = APIRouter(prefix="/appointments", tags=["Appointments"])


def _enrich(appt: dict) -> AppointmentOut:
    """Join doctor and slot data onto a raw appointment row."""
    db = get_db()
    doctor = db.get_doctor(appt["doctor_id"]) or {}
    slot   = db.get_slot(appt["slot_id"])   or {}
    return AppointmentOut(
        id               = appt["id"],
        patient_id       = appt["patient_id"],
        doctor_id        = appt["doctor_id"],
        slot_id          = appt["slot_id"],
        status           = AppointmentStatus(appt["status"]),
        symptoms_summary = appt.get("symptoms_summary"),
        created_at       = appt["created_at"],
        doctor_name      = doctor.get("name"),
        doctor_specialty = doctor.get("specialty"),
        slot_datetime    = slot.get("slot_datetime"),
        location         = doctor.get("location"),
    )


@router.get("/{appointment_id}", response_model=AppointmentOut)
def get_appointment(appointment_id: str):
    """Fetch a single appointment by ID."""
    appt = get_db().get_appointment(appointment_id)
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    return _enrich(appt)


@router.get("/patient/{patient_id}", response_model=list[AppointmentOut])
def get_patient_appointments(
    patient_id: str,
    status: str | None = Query(None, description="confirmed | cancelled | completed"),
):
    """All appointments for a patient — used by the Patient Dashboard."""
    appts = get_db().get_appointments_for_patient(patient_id, status=status)
    return [_enrich(a) for a in appts]


@router.get("/doctor/{doctor_id}", response_model=list[AppointmentOut])
def get_doctor_appointments(
    doctor_id: str,
    date: str | None = Query(None, description="YYYY-MM-DD — defaults to today"),
):
    """All appointments for a doctor on a given day — used by the Doctor Dashboard."""
    target = date or str(dt_date.today())
    appts  = get_db().get_appointments_for_doctor_on_date(doctor_id, target)
    return [_enrich(a) for a in appts]


@router.get("/admin/all", response_model=list[AppointmentOut])
def get_all_appointments(
    location: str | None = Query(None, description="wattala | thalawathugoda"),
    status:   str | None = Query(None, description="confirmed | cancelled | completed"),
    limit:    int        = Query(50, le=200),
):
    """All appointments — used by the Admin Dashboard."""
    appts = get_db().get_all_appointments(location=location, status=status, limit=limit)
    return [_enrich(a) for a in appts]


@router.patch("/{appointment_id}/reschedule", response_model=AppointmentOut)
def reschedule_appointment_endpoint(appointment_id: str, body: RescheduleRequest):
    """
    Reschedule an appointment to a new slot from the dashboard.
    Frees the old slot and books the new one atomically.
    """
    db = get_db()

    appt = db.get_appointment(appointment_id)
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if appt["status"] == "cancelled":
        raise HTTPException(status_code=400, detail="Cannot reschedule a cancelled appointment")

    new_slot = db.get_slot(body.new_slot_id)
    if not new_slot:
        raise HTTPException(status_code=404, detail="New slot not found")
    if new_slot["is_booked"]:
        raise HTTPException(status_code=409, detail="That slot is already booked")

    # Free old slot, update appointment, lock new slot
    db.mark_slot_booked(appt["slot_id"], booked=False)
    db.update_appointment_slot(
        appointment_id=appointment_id,
        new_slot_id=body.new_slot_id,
        new_doctor_id=body.new_doctor_id,
    )
    db.mark_slot_booked(body.new_slot_id, booked=True)

    updated = db.get_appointment(appointment_id)
    return _enrich(updated)


@router.delete("/{appointment_id}")
def cancel_appointment_endpoint(appointment_id: str, body: CancelRequest):
    """Cancel an appointment from the dashboard (not via agent)."""
    db   = get_db()
    appt = db.get_appointment(appointment_id)
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if appt["status"] == "cancelled":
        raise HTTPException(status_code=400, detail="Already cancelled")

    db.update_appointment_status(appointment_id, "cancelled")
    db.mark_slot_booked(appt["slot_id"], booked=False)
    return {"success": True, "appointment_id": appointment_id}
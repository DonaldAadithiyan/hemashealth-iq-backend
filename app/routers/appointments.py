"""
Appointment endpoints consumed by the Next.js dashboards.
Data source: app/db/supabase.py — real Supabase schema.
"""

from datetime import date as dt_date
from fastapi import APIRouter, HTTPException, Query
from app.db.supabase import (
    get_appointment,
    get_appointments_for_patient,
    get_appointments_for_doctor_on_date,
    get_all_appointments,
    update_appointment_status,
    reschedule_appointment_db,
    get_doctor,
    parse_synthetic_slot_id,
)
from pydantic import BaseModel
from typing import Optional
from app.models.schemas import AppointmentOut, CancelRequest, RescheduleRequest, AppointmentStatus


class PaymentStatusRequest(BaseModel):
    status:      str            # "paid" | "confirmed"
    payment_ref: Optional[str] = None  # payment gateway transaction ID (Stripe charge ID, PayHere txn, etc.)

router = APIRouter(prefix="/appointments", tags=["Appointments"])


def _enrich(appt: dict) -> AppointmentOut:
    """Join doctor data onto a raw appointment row."""
    doctor = get_doctor(appt["doctor_id"]) or {}
    return AppointmentOut(
        id               = appt["id"],
        patient_id       = appt["patient_id"],
        doctor_id        = appt["doctor_id"],
        appointment_date = appt["appointment_date"],
        status           = AppointmentStatus(appt["status"]),
        reason_for_visit = appt.get("reason_for_visit"),
        notes            = appt.get("notes"),
        created_at       = appt.get("created_at"),
        doctor_name      = doctor.get("name"),
        doctor_specialty = doctor.get("specialty"),
        location         = doctor.get("location"),
    )


@router.get("/{appointment_id}", response_model=AppointmentOut)
def get_appointment_endpoint(appointment_id: str):
    """Fetch a single appointment by ID."""
    appt = get_appointment(appointment_id)
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    return _enrich(appt)


@router.get("/patient/{patient_id}", response_model=list[AppointmentOut])
def get_patient_appointments(
    patient_id: str,
    status: str | None = Query(None, description="reserved | confirmed | paid | cancelled | not_attended"),
):
    """All appointments for a patient — Patient Dashboard."""
    appts = get_appointments_for_patient(patient_id, status=status)
    return [_enrich(a) for a in appts]


@router.get("/doctor/{doctor_id}", response_model=list[AppointmentOut])
def get_doctor_appointments(
    doctor_id: str,
    date: str | None = Query(None, description="YYYY-MM-DD — defaults to today"),
):
    """All appointments for a doctor on a given day — Doctor Dashboard."""
    target = date or str(dt_date.today())
    appts  = get_appointments_for_doctor_on_date(doctor_id, target)
    return [_enrich(a) for a in appts]


@router.get("/admin/all", response_model=list[AppointmentOut])
def get_all_appointments_endpoint(
    location: str | None = Query(None, description="wattala | thalawathugoda"),
    status:   str | None = Query(None, description="reserved | confirmed | paid | cancelled | not_attended"),
    limit:    int        = Query(50, le=200),
):
    """All appointments — Admin Dashboard."""
    appts = get_all_appointments(location=location, status=status, limit=limit)
    return [_enrich(a) for a in appts]


@router.patch("/{appointment_id}/reschedule", response_model=AppointmentOut)
def reschedule_appointment_endpoint(appointment_id: str, body: RescheduleRequest):
    """
    Reschedule an appointment to a new slot from the dashboard.
    new_slot_id must be the synthetic slot ID: "doctor_id::YYYY-MM-DDTHH:MM"
    """
    appt = get_appointment(appointment_id)
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if appt["status"] == "cancelled":
        raise HTTPException(status_code=400, detail="Cannot reschedule a cancelled appointment")

    try:
        _, new_datetime = parse_synthetic_slot_id(body.new_slot_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid slot_id format")

    if len(new_datetime) == 16:
        new_datetime += ":00+00:00"

    reschedule_appointment_db(
        appointment_id=appointment_id,
        new_appointment_date=new_datetime,
        new_doctor_id=body.new_doctor_id,
    )

    updated = get_appointment(appointment_id)
    return _enrich(updated)


@router.patch("/{appointment_id}/status")
def update_payment_status_endpoint(appointment_id: str, body: PaymentStatusRequest):
    """
    Called by the frontend after a successful payment.
    Updates the appointment status in Supabase.

    Called by:
    - Stripe webhook / PayHere callback: status="paid", payment_ref="txn_abc123"
    - Admin confirming: status="confirmed"

    Allowed transitions:
      reserved  → confirmed | paid | cancelled
      confirmed → paid | cancelled
      paid      → completed | cancelled
    """
    appt = get_appointment(appointment_id)
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")

    current = appt["status"]
    new_status = body.status

    # Validate allowed transitions
    allowed = {
        "reserved":  ["confirmed", "paid", "cancelled"],
        "confirmed": ["paid", "cancelled", "completed"],
        "paid":      ["completed", "cancelled"],
    }
    if current not in allowed or new_status not in allowed.get(current, []):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot transition from '{current}' to '{new_status}'"
        )

    # Store payment_ref in notes if provided
    notes = None
    if body.payment_ref:
        notes = f"payment_ref:{body.payment_ref}"

    update_appointment_status(appointment_id, new_status, notes=notes)

    updated = get_appointment(appointment_id)
    return {
        "success":        True,
        "appointment_id": appointment_id,
        "status":         new_status,
        "payment_ref":    body.payment_ref,
    }


@router.delete("/{appointment_id}")
def cancel_appointment_endpoint(appointment_id: str, body: CancelRequest):
    """Cancel an appointment from the dashboard."""
    appt = get_appointment(appointment_id)
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if appt["status"] == "cancelled":
        raise HTTPException(status_code=400, detail="Already cancelled")

    update_appointment_status(appointment_id, "cancelled")
    return {"success": True, "appointment_id": appointment_id}
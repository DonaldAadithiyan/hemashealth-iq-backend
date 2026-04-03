"""
payment.py — Confirm payment and update appointment status.

Called by the agent when the patient sends a payment success message.
Updates the appointment status in Supabase to 'paid'.
"""
from langchain_core.tools import tool
from app.db.supabase import update_appointment_status, get_appointment


@tool
def confirm_payment(
    appointment_id: str,
    payment_ref:    str | None = None,
    pay_at_hospital: bool = False,
) -> dict:
    """
    Confirm an appointment payment — either online or pay-at-hospital.

    Call this when the patient sends any message indicating:
    - Online payment success: "payment successful", "I've paid", "payment done"
    - Pay at hospital: "pay at hospital", "pay on arrival", "i'll pay there"

    Args:
        appointment_id:  The appointment UUID from state
        payment_ref:     Optional payment gateway reference (Stripe/PayHere ID)
        pay_at_hospital: True when patient chose to pay at hospital reception

    Returns:
        success:        bool
        appointment_id: str
        status:         str — "paid" (online) or "confirmed" (pay at hospital)
        error:          str | None
    """
    if not appointment_id:
        return {
            "success":        False,
            "appointment_id": None,
            "status":         None,
            "error":          "No appointment_id in state. Cannot confirm payment.",
        }

    appt = get_appointment(appointment_id)
    if not appt:
        return {
            "success":        False,
            "appointment_id": appointment_id,
            "status":         None,
            "error":          "Appointment not found.",
        }

    # Already in a terminal payment state — idempotent
    if appt["status"] in ("paid", "confirmed"):
        return {
            "success":        True,
            "appointment_id": appointment_id,
            "status":         appt["status"],
            "error":          None,
        }

    # Pay at hospital → status = "confirmed" (will be paid at reception)
    # Online payment → status = "paid"
    new_status = "confirmed" if pay_at_hospital else "paid"
    notes = f"payment_ref:{payment_ref}" if payment_ref else None
    update_appointment_status(appointment_id, new_status, notes=notes)

    return {
        "success":        True,
        "appointment_id": appointment_id,
        "status":         new_status,
        "error":          None,
    }
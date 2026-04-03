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
) -> dict:
    """
    Mark an appointment as paid after the patient confirms payment success.
    Call this when the patient sends any message indicating payment was successful
    (e.g. "payment successful", "I've paid", "payment done").

    Args:
        appointment_id: The appointment UUID from state
        payment_ref:    Optional payment reference from the gateway (e.g. Stripe charge ID)

    Returns:
        success:        bool
        appointment_id: str
        status:         str — "paid"
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

    if appt["status"] == "paid":
        return {
            "success":        True,
            "appointment_id": appointment_id,
            "status":         "paid",
            "error":          None,
        }

    notes = f"payment_ref:{payment_ref}" if payment_ref else None
    update_appointment_status(appointment_id, "paid", notes=notes)

    return {
        "success":        True,
        "appointment_id": appointment_id,
        "status":         "paid",
        "error":          None,
    }
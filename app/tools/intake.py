"""
intake.py — Pre-appointment intake note tool.

Feature 2: After booking is confirmed, the agent calls this tool to write
a structured clinical note to patient_history_events. The doctor sees this
before the patient walks in.

The agent decides what to include:
- If the patient gave rich symptom information → summarise and store immediately
- If information was vague → ask ONE follow-up question, then store whatever is given
- Never ask more than one question

All fields except patient_id and appointment_id are optional — store what you have.
"""

from langchain_core.tools import tool
from app.db.supabase import create_patient_history_event


@tool
def store_intake_note(
    patient_id:           str,
    appointment_id:       str,
    symptoms_summary:     str,
    duration:             str | None = None,
    severity:             str | None = None,
    current_medications:  str | None = None,
    mentions_medication:  bool = False,
    is_recurring:         bool = False,
    previous_visit_note:  str | None = None,
) -> dict:
    """
    Store a structured pre-appointment intake note in patient_history_events.
    The doctor will see this before the consultation.

    Args:
        patient_id:          patients.id UUID
        appointment_id:      appointments.id UUID
        symptoms_summary:    Plain text summary of what the patient described
        duration:            How long they've had the symptoms e.g. "3 days", "2 weeks"
        severity:            Self-reported severity e.g. "mild", "moderate", "severe", "7/10"
        current_medications: Any medications the patient mentioned taking
        mentions_medication: True if patient mentioned any medications (from routing tool)
        is_recurring:        True if this matches a previous visit's reason_for_visit
        previous_visit_note: Short note about the previous visit if recurring
                             e.g. "Patient visited for headaches on March 15"

    Returns:
        success:  bool
        event_id: str | None
        error:    str | None
    """
    # Build structured payload for the doctor
    payload: dict = {
        "symptoms_summary":    symptoms_summary,
        "duration":            duration,
        "severity":            severity,
        "current_medications": current_medications,
        "is_recurring":        is_recurring,
        "previous_visit_note": previous_visit_note,
        "medication_warning":  mentions_medication,
    }
    # Strip None values to keep it clean
    payload = {k: v for k, v in payload.items() if v is not None and v is not False}

    # Build the title shown in the doctor's history view
    parts = [symptoms_summary[:60]]
    if is_recurring:
        parts.append("⚠️ Recurring symptom")
    if mentions_medication:
        parts.append("💊 On medication")
    title = " | ".join(parts)

    # Build description (readable summary for the doctor)
    desc_parts = [f"Symptoms: {symptoms_summary}"]
    if duration:
        desc_parts.append(f"Duration: {duration}")
    if severity:
        desc_parts.append(f"Severity: {severity}")
    if current_medications:
        desc_parts.append(f"Current medications: {current_medications}")
    if is_recurring and previous_visit_note:
        desc_parts.append(f"Note: {previous_visit_note}")
    if mentions_medication:
        desc_parts.append("⚠️ Patient is on medication — please review before prescribing.")
    description = "\n".join(desc_parts)

    result = create_patient_history_event(
        patient_id=patient_id,
        appointment_id=appointment_id,
        event_type="consultation_note",
        title=title,
        description=description,
        payload=payload,
        added_by_role="patient",
    )

    if not result:
        return {"success": False, "event_id": None, "error": "Failed to save intake note."}

    return {"success": True, "event_id": result["id"], "error": None}
from fastapi import APIRouter, HTTPException
from app.models.schemas import (
    ChatRequest, ChatResponse, BookingState, UIAction, stage_to_ui_action,
    EmergencyPayload, LocationPickerPayload, LocationButton,
    SlotsPayload, DoctorSlots, SlotOption,
    PatientFormPayload, LastVisitInfo,
    PaymentPayload, CancelledPayload, RescheduledPayload,
    SpecialtyChoicePayload, SpecialtyChoiceButton,
    PhoneChoicePayload,
    ConfirmBookingPayload,
    LOCATION_LABELS, _format_datetime_label,
)
from app.agents.patient_agent import run_agent
from app.utils.pii_vault import get_vault, clear_vault

router = APIRouter(prefix="/chat", tags=["Chat"])

# ── Static payloads ───────────────────────────────────────────────────────────

_LOCATION_PICKER = LocationPickerPayload(buttons=[
    LocationButton(value="wattala",        label=LOCATION_LABELS["wattala"][0],        address=LOCATION_LABELS["wattala"][1]),
    LocationButton(value="thalawathugoda", label=LOCATION_LABELS["thalawathugoda"][0], address=LOCATION_LABELS["thalawathugoda"][1]),
])

_EMERGENCY = EmergencyPayload()


def _build_payload(action: UIAction, state: BookingState):
    """Build the ui_payload for the given action from state."""

    if action == UIAction.SHOW_EMERGENCY:
        return _EMERGENCY

    if action == UIAction.SHOW_LOCATION_PICKER:
        return _LOCATION_PICKER

    if action == UIAction.SHOW_SLOTS:
        if not state.available_doctors:
            return None
        doctors = []
        for doc in state.available_doctors:
            slot_options = []
            for s in doc.get("slots", []):
                dt = s.get("datetime", "")
                slot_options.append(SlotOption(
                    slot_id  = s.get("slot_id", ""),
                    datetime = dt,
                    label    = _format_datetime_label(dt),
                ))
            doctors.append(DoctorSlots(
                doctor_id   = doc.get("doctor_id", ""),
                doctor_name = doc.get("doctor_name", ""),
                specialty   = doc.get("specialty", ""),
                location    = doc.get("location", ""),
                slots       = slot_options,
            ))
        return SlotsPayload(
            doctors        = doctors,
            fallback_used  = state.fallback_used,
            fallback_reason= state.fallback_reason,
        )

    if action == UIAction.SHOW_PATIENT_FORM:
        last_visit = None
        if state.last_visit_date and state.last_visit_specialty:
            last_visit = LastVisitInfo(
                date        = state.last_visit_date,
                specialty   = state.last_visit_specialty,
                doctor_name = state.last_visit_doctor or "",
            )
        return PatientFormPayload(
            is_returning = state.patient_id is not None,
            patient_name = state.patient_name,
            last_visit   = last_visit,
            is_recurring = state.is_recurring,
        )

    if action == UIAction.SHOW_PAYMENT:
        if not state.appointment_id:
            return None
        loc = state.preferred_location or ""
        loc_label = LOCATION_LABELS.get(loc, (loc, ""))[0] if loc else ""
        dt = state.selected_slot_datetime or ""
        return PaymentPayload(
            appointment_id      = state.appointment_id,
            doctor_name         = state.selected_doctor_name or "",
            specialty           = state.detected_specialty or "",
            datetime            = dt,
            datetime_label      = _format_datetime_label(dt),
            location            = f"Hemas Hospital, {loc_label}",
            mentions_medication = state.mentions_medication,
            is_recurring        = state.is_recurring,
        )

    if action == UIAction.SHOW_CANCELLED:
        if not state.appointment_id:
            return None
        return CancelledPayload(appointment_id=state.appointment_id)

    if action == UIAction.SHOW_PHONE_CHOICE:
        phone = state.user_phone or ""
        # Normalise for display: +94773609683 → 0773609683 style
        display = phone
        return PhoneChoicePayload(
            logged_in_phone = phone,
            logged_in_label = f"Use my number ({display})",
            other_label     = "Use a different number",
        )

    if action == UIAction.SHOW_SPECIALTY_CHOICE:
        options = state.specialty_choice_options or []
        buttons = [
            SpecialtyChoiceButton(
                value    = opt.get("value", ""),
                label    = opt.get("label", ""),
                specialty= opt.get("specialty", ""),
            )
            for opt in options
        ]
        return SpecialtyChoicePayload(
            buttons             = buttons,
            suggested_specialty = state.suggested_specialty or "",
            reason              = state.specialty_choice_reason or "",
        )

    if action == UIAction.SHOW_CONFIRM_BOOKING:
        if not state.pending_slot_id:
            return None
        loc = state.pending_location or state.preferred_location or ""
        loc_label = LOCATION_LABELS.get(loc, (loc, ""))[0] if loc else ""
        dt = state.pending_slot_datetime or ""
        return ConfirmBookingPayload(
            doctor_name    = state.pending_doctor_name or "",
            specialty      = state.pending_specialty or state.detected_specialty or "",
            datetime_label = _format_datetime_label(dt),
            location       = f"Hemas Hospital, {loc_label}",
            slot_id        = state.pending_slot_id,
        )

    if action == UIAction.SHOW_RESCHEDULED:
        if not state.appointment_id:
            return None
        loc = state.preferred_location or ""
        loc_label = LOCATION_LABELS.get(loc, (loc, ""))[0] if loc else ""
        dt = state.selected_slot_datetime or ""
        return RescheduledPayload(
            appointment_id     = state.appointment_id,
            doctor_name        = state.selected_doctor_name or "",
            new_datetime       = dt,
            new_datetime_label = _format_datetime_label(dt),
            location           = f"Hemas Hospital, {loc_label}",
        )

    return None


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.post("", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """
    ## POST /chat

    Send a patient message. Get reply + ui_action + ui_payload + state back.

    ### ui_payload shape per ui_action:

    | ui_action            | ui_payload shape        |
    |----------------------|------------------------|
    | SHOW_CHAT            | null                   |
    | SHOW_EMERGENCY       | EmergencyPayload       |
    | SHOW_LOCATION_PICKER | LocationPickerPayload  |
    | SHOW_SLOTS           | SlotsPayload           |
    | SHOW_PATIENT_FORM    | PatientFormPayload     |
    | SHOW_PAYMENT         | PaymentPayload         |
    | SHOW_CANCELLED       | CancelledPayload       |
    | SHOW_RESCHEDULED     | RescheduledPayload     |

    ### Location picker
    When ui_action == SHOW_LOCATION_PICKER, render two buttons from
    ui_payload.buttons. Send the button's `value` field as the next message.

    ### Slot picker
    When ui_action == SHOW_SLOTS, render slot cards from ui_payload.doctors[].slots.
    Send the slot's `slot_id` as the next message (or let patient type freely).
    """
    try:
        vault  = get_vault(req.session_id)
        bs     = req.booking_state
        # Sync user_phone from request into booking_state
        # Frontend sends it on every request from Supabase auth session
        if req.user_phone and not bs.user_phone:
            bs.user_phone = req.user_phone
        result = await run_agent(
            new_message          = req.message,
            history              = req.history,
            vault                = vault,
            user_phone           = bs.user_phone,
            patient_id           = bs.patient_id,
            preferred_location   = bs.preferred_location,
            current_stage        = bs.stage,
            detected_specialty   = bs.detected_specialty,
            selected_slot_id     = bs.selected_slot_id,
            selected_slot_datetime = bs.selected_slot_datetime,
            selected_doctor_id   = bs.selected_doctor_id,
            selected_doctor_name = bs.selected_doctor_name,
            appointment_id       = bs.appointment_id,
            is_emergency         = bs.is_emergency,
            mentions_medication  = bs.mentions_medication,
            is_recurring         = bs.is_recurring,
            routing_tier              = bs.routing_tier,
            suggested_specialty       = bs.suggested_specialty,
            specialty_choice_pending  = bs.specialty_choice_pending,
            specialty_choice_options  = bs.specialty_choice_options,
            specialty_choice_reason   = bs.specialty_choice_reason,
            pending_slot_id           = bs.pending_slot_id,
            pending_slot_datetime     = bs.pending_slot_datetime,
            pending_doctor_name       = bs.pending_doctor_name,
            pending_doctor_id         = bs.pending_doctor_id,
            pending_specialty         = bs.pending_specialty,
            pending_location          = bs.pending_location,
            available_doctors    = bs.available_doctors,
            fallback_used        = bs.fallback_used,
            fallback_reason      = bs.fallback_reason,
            patient_name         = bs.patient_name,
            last_visit_date      = bs.last_visit_date,
            last_visit_specialty = bs.last_visit_specialty,
            last_visit_doctor    = bs.last_visit_doctor,
            conversation_summary = bs.conversation_summary,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    new_state  = BookingState(**result["state"])
    ui_action  = stage_to_ui_action(new_state.stage)

    # Override: if agent is asking for slot confirmation and pending slot is set,
    # show SHOW_CONFIRM_BOOKING regardless of stage
    if (new_state.stage == "slots_shown"
        and new_state.pending_slot_id
        and new_state.pending_doctor_name):
        ui_action = UIAction.SHOW_CONFIRM_BOOKING

    # Override: show phone choice when user_phone is available and agent just asked for phone
    # Detected when stage transitions to collecting with no patient_id yet
    if (ui_action == UIAction.SHOW_PATIENT_FORM
        and new_state.user_phone
        and not new_state.patient_id
        and new_state.stage == "collecting"):
        # Check if the reply is asking for phone number
        reply_lower = result["reply"].lower()
        if any(kw in reply_lower for kw in ["phone number", "phone", "registered", "number"]):
            ui_action = UIAction.SHOW_PHONE_CHOICE

    ui_payload = _build_payload(ui_action, new_state)

    if new_state.stage == "confirmed":
        clear_vault(req.session_id)

    return ChatResponse(
        session_id = req.session_id,
        reply      = result["reply"],
        ui_action  = ui_action,
        ui_payload = ui_payload,
        state      = new_state,
    )
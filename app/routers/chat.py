from fastapi import APIRouter, HTTPException
from app.models.schemas import (
    ChatRequest, ChatResponse, BookingState, UIAction,
    EmergencyPayload, LocationPickerPayload, LocationButton,
    SlotsPayload, DoctorSlots, SlotOption,
    PatientFormPayload, LastVisitInfo,
    PaymentPayload, CancelledPayload, RescheduledPayload,
    SpecialtyChoicePayload, SpecialtyChoiceButton,
    PhoneChoicePayload, ConfirmBookingPayload,
    LOCATION_LABELS, _format_datetime_label,
)
from app.agents.patient_agent import run_agent
from app.utils.pii_vault import get_vault, clear_vault

router = APIRouter(prefix="/chat", tags=["Chat"])

_LOCATION_PICKER = LocationPickerPayload(buttons=[
    LocationButton(value="wattala",        label=LOCATION_LABELS["wattala"][0],        address=LOCATION_LABELS["wattala"][1]),
    LocationButton(value="thalawathugoda", label=LOCATION_LABELS["thalawathugoda"][0], address=LOCATION_LABELS["thalawathugoda"][1]),
])
_EMERGENCY = EmergencyPayload()


def _decide_ui_action(state: BookingState, reply: str, prev_stage: str) -> UIAction:
    """
    Decide ui_action based on the NEW state, agent reply content, and previous stage.
    This is the single source of truth — driven by what the agent actually said,
    not just what stage we're in.
    """
    stage = state.stage
    reply_lower = reply.lower()

    # ── Terminal states — always correct ──────────────────────────────────
    if stage == "emergency":
        return UIAction.SHOW_EMERGENCY

    if stage == "confirmed":
        # Only show payment card if appointment_id is actually set
        if state.appointment_id:
            return UIAction.SHOW_PAYMENT
        return UIAction.SHOW_CHAT

    if stage == "cancelled":
        return UIAction.SHOW_CANCELLED

    if stage == "rescheduled":
        return UIAction.SHOW_RESCHEDULED

    if stage == "specialty_choice":
        return UIAction.SHOW_SPECIALTY_CHOICE

    # ── Routing — only show location picker when agent is asking for location ──
    if stage == "routing":
        asking_location = any(kw in reply_lower for kw in [
            "which hospital", "which location", "which branch", "wattala or thalawathugoda",
            "can you reach", "prefer to visit"
        ])
        if asking_location:
            return UIAction.SHOW_LOCATION_PICKER
        return UIAction.SHOW_CHAT

    # ── Slots shown — only show slots when agent is presenting them ──────────
    if stage == "slots_shown":
        # Agent presenting slots → show slot cards
        presenting_slots = any(kw in reply_lower for kw in [
            "available slots", "please choose", "choose from", "choose below",
            "options below", "pick a slot", "select a slot", "here are the"
        ])
        if presenting_slots and state.available_doctors:
            return UIAction.SHOW_SLOTS

        # Anything else while in slots_shown → plain chat
        return UIAction.SHOW_CHAT

    # ── Collecting — only show patient form when agent is asking about patient ─
    if stage == "collecting":
        # Phone choice if logged-in phone is available and agent asking for phone
        if state.user_phone and not state.patient_id:
            asking_phone = any(kw in reply_lower for kw in [
                "phone number", "which number", "number should i use",
                "already registered", "check if you", "complete the booking",
                "to complete", "which number", "use?", "number to use",
                "registered with us",
            ])
            # Also fire if reply is short and asking-style (ends with ?)
            if asking_phone or (len(reply_lower) < 120 and reply_lower.strip().endswith("?")):
                return UIAction.SHOW_PHONE_CHOICE

        # Patient form when agent is greeting or asking for name
        asking_patient = any(kw in reply_lower for kw in [
            "welcome back", "welcome to hemas", "full name", "your name",
            "already registered", "new to hemas", "shall i proceed"
        ])
        if asking_patient:
            return UIAction.SHOW_PATIENT_FORM

        return UIAction.SHOW_CHAT

    # ── Intake / clarify / everything else → plain chat ──────────────────────
    return UIAction.SHOW_CHAT


def _build_payload(action: UIAction, state: BookingState):
    """Build ui_payload for the given action. Returns None if data is missing."""

    if action == UIAction.SHOW_EMERGENCY:
        return _EMERGENCY

    if action == UIAction.SHOW_LOCATION_PICKER:
        return _LOCATION_PICKER

    if action == UIAction.SHOW_SPECIALTY_CHOICE:
        options = state.specialty_choice_options or []
        if not options:
            return None
        return SpecialtyChoicePayload(
            buttons=[SpecialtyChoiceButton(
                value=o.get("value",""), label=o.get("label",""), specialty=o.get("specialty","")
            ) for o in options],
            suggested_specialty=state.suggested_specialty or "",
            reason=state.specialty_choice_reason or "",
        )

    if action == UIAction.SHOW_SLOTS:
        if not state.available_doctors:
            return None
        doctors = []
        for doc in state.available_doctors:
            slots = []
            for s in doc.get("slots", []):
                dt = s.get("datetime", "")
                slots.append(SlotOption(
                    slot_id  = s.get("slot_id", ""),
                    datetime = dt,
                    label    = s.get("label") or _format_datetime_label(dt),
                ))
            doctors.append(DoctorSlots(
                doctor_id   = doc.get("doctor_id", ""),
                doctor_name = doc.get("doctor_name", ""),
                specialty   = doc.get("specialty", ""),
                location    = doc.get("location", ""),
                slots       = slots,
            ))
        return SlotsPayload(
            doctors         = doctors,
            fallback_used   = state.fallback_used,
            fallback_reason = state.fallback_reason,
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

    if action == UIAction.SHOW_PHONE_CHOICE:
        if not state.user_phone:
            return None
        phone = state.user_phone
        return PhoneChoicePayload(
            logged_in_phone = phone,
            logged_in_label = f"Use my number ({phone})",
            other_label     = "Use a different number",
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


@router.post("", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """POST /chat — main AI endpoint."""
    try:
        vault = get_vault(req.session_id)
        bs    = req.booking_state

        if req.user_phone and not bs.user_phone:
            bs.user_phone = req.user_phone

        result = await run_agent(
            new_message             = req.message,
            history                 = req.history,
            vault                   = vault,
            user_phone              = bs.user_phone,
            patient_id              = bs.patient_id,
            preferred_location      = bs.preferred_location,
            current_stage           = bs.stage,
            detected_specialty      = bs.detected_specialty,
            selected_slot_id        = bs.selected_slot_id,
            selected_slot_datetime  = bs.selected_slot_datetime,
            selected_doctor_id      = bs.selected_doctor_id,
            selected_doctor_name    = bs.selected_doctor_name,
            appointment_id          = bs.appointment_id,
            is_emergency            = bs.is_emergency,
            mentions_medication     = bs.mentions_medication,
            is_recurring            = bs.is_recurring,
            routing_tier            = bs.routing_tier,
            suggested_specialty     = bs.suggested_specialty,
            specialty_choice_pending= bs.specialty_choice_pending,
            specialty_choice_options= bs.specialty_choice_options,
            specialty_choice_reason = bs.specialty_choice_reason,
            pending_slot_id         = bs.pending_slot_id,
            pending_slot_datetime   = bs.pending_slot_datetime,
            pending_doctor_name     = bs.pending_doctor_name,
            pending_doctor_id       = bs.pending_doctor_id,
            pending_specialty       = bs.pending_specialty,
            pending_location        = bs.pending_location,
            available_doctors       = bs.available_doctors,
            fallback_used           = bs.fallback_used,
            fallback_reason         = bs.fallback_reason,
            patient_name            = bs.patient_name,
            last_visit_date         = bs.last_visit_date,
            last_visit_specialty    = bs.last_visit_specialty,
            last_visit_doctor       = bs.last_visit_doctor,
            navigation_stack        = bs.navigation_stack,
            conversation_summary    = bs.conversation_summary,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    new_state  = BookingState(**result["state"])
    prev_stage = bs.stage
    reply      = result["reply"]

    # Determine ui_action from reply content + state — not just stage
    ui_action  = _decide_ui_action(new_state, reply, prev_stage)
    ui_payload = _build_payload(ui_action, new_state)

    # Safety: if payload is None for a non-chat action, fall back to SHOW_CHAT
    if ui_payload is None and ui_action != UIAction.SHOW_CHAT:
        ui_action = UIAction.SHOW_CHAT

    if new_state.stage == "confirmed":
        clear_vault(req.session_id)

    return ChatResponse(
        session_id = req.session_id,
        reply      = reply,
        ui_action  = ui_action,
        ui_payload = ui_payload,
        state      = new_state,
    )
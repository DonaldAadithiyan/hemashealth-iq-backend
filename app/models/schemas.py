from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


# ── Chat ──────────────────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str       # "user" | "assistant"
    content: str


class UIAction(str, Enum):
    """
    Tells the frontend exactly which UI component to render after each response.
    Read this field on every ChatResponse and switch your UI accordingly.

    SHOW_CHAT          → plain chat bubble, nothing extra
    SHOW_EMERGENCY     → red emergency banner + 1990 call button (block further input until dismissed)
    SHOW_SLOTS         → reply contains slot options — render as selectable cards if you want
    SHOW_PATIENT_FORM  → optionally render a name/phone form instead of free text
    SHOW_CONFIRMATION  → render booking confirmation card with doctor, date, time, location
    SHOW_PAYMENT       → appointment confirmed — trigger payment flow
    SHOW_CANCELLED     → render cancellation confirmation card
    """
    SHOW_CHAT         = "SHOW_CHAT"
    SHOW_EMERGENCY    = "SHOW_EMERGENCY"
    SHOW_SLOTS        = "SHOW_SLOTS"
    SHOW_PATIENT_FORM = "SHOW_PATIENT_FORM"
    SHOW_CONFIRMATION = "SHOW_CONFIRMATION"
    SHOW_PAYMENT      = "SHOW_PAYMENT"
    SHOW_CANCELLED    = "SHOW_CANCELLED"
    SHOW_RESCHEDULED  = "SHOW_RESCHEDULED"


# Map stage → UIAction — single source of truth
_STAGE_TO_UI: dict[str, UIAction] = {
    "intake":      UIAction.SHOW_CHAT,
    "routing":     UIAction.SHOW_CHAT,
    "emergency":   UIAction.SHOW_EMERGENCY,
    "slots_shown": UIAction.SHOW_SLOTS,
    "collecting":  UIAction.SHOW_PATIENT_FORM,
    "confirmed":   UIAction.SHOW_PAYMENT,
    "cancelled":   UIAction.SHOW_CANCELLED,
    "rescheduled": UIAction.SHOW_RESCHEDULED,
}

def stage_to_ui_action(stage: str) -> UIAction:
    return _STAGE_TO_UI.get(stage, UIAction.SHOW_CHAT)


class BookingState(BaseModel):
    """
    Booking context the frontend tracks and sends back on every request.
    Start with all defaults on session open. Update from ChatResponse.state each turn.
    """
    stage: str = "intake"
    is_emergency: bool = False

    detected_specialty:     Optional[str] = None
    preferred_location:     Optional[str] = None   # "wattala" | "thalawathugoda"

    selected_slot_id:       Optional[str] = None
    selected_slot_datetime: Optional[str] = None
    selected_doctor_id:     Optional[str] = None
    selected_doctor_name:   Optional[str] = None

    patient_id:             Optional[str] = None
    appointment_id:         Optional[str] = None


class ChatRequest(BaseModel):
    session_id: str = Field(..., description="UUID for this conversation — generate once on session open")
    message:    str = Field(..., description="Latest message from the patient")
    history:    list[ChatMessage] = Field(
        default=[],
        description="Full conversation so far, NOT including the current message. Frontend maintains this.",
    )
    booking_state: BookingState = Field(
        default_factory=BookingState,
        description="Booking state from the previous response. Send back exactly as received.",
    )


class ChatResponse(BaseModel):
    session_id: str

    reply: str = Field(
        ...,
        description="Agent reply text. Always display this as the assistant chat bubble.",
    )

    ui_action: UIAction = Field(
        ...,
        description=(
            "Tells the frontend which UI to render alongside the reply. "
            "Switch on this field to decide what component to show. "
            "See UIAction enum for all possible values and what each means."
        ),
    )

    state: BookingState = Field(
        ...,
        description="Updated booking state. Store this and send it back as booking_state on the next request.",
    )


# ── Appointments (dashboard endpoints) ───────────────────────────────────────

class AppointmentStatus(str, Enum):
    confirmed = "confirmed"
    cancelled = "cancelled"
    completed = "completed"


class AppointmentOut(BaseModel):
    id:               str
    patient_id:       str
    doctor_id:        str
    slot_id:          str
    status:           AppointmentStatus
    symptoms_summary: Optional[str] = None
    created_at:       str
    doctor_name:      Optional[str] = None
    doctor_specialty: Optional[str] = None
    slot_datetime:    Optional[str] = None
    location:         Optional[str] = None


class CancelRequest(BaseModel):
    cancelled_by: str = Field(..., description="'patient' | 'admin' | 'doctor'")


class RescheduleRequest(BaseModel):
    new_slot_id:   str = Field(..., description="UUID of the new slot to move to")
    new_doctor_id: str = Field(..., description="UUID of the doctor for the new slot")
    rescheduled_by: str = Field(..., description="'patient' | 'admin' | 'doctor'")


class DoctorOut(BaseModel):
    id:        str
    name:      str
    specialty: str
    location:  str
    is_active: bool


class SlotOut(BaseModel):
    id:            str
    doctor_id:     str
    slot_datetime: str
    is_booked:     bool
from pydantic import BaseModel, Field
from typing import Optional, Any
from enum import Enum
from datetime import datetime


# ── Chat ──────────────────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str
    content: str


class UIAction(str, Enum):
    """
    Tells the frontend which component to render alongside the chat bubble.
    Read ui_action on every response and switch on it.
    ui_payload contains the structured data for that component.
    """
    SHOW_CHAT            = "SHOW_CHAT"           # plain chat bubble, no extra component
    SHOW_EMERGENCY       = "SHOW_EMERGENCY"       # red banner + 1990 call button
    SHOW_LOCATION_PICKER = "SHOW_LOCATION_PICKER" # two hospital buttons (Wattala / Thalawathugoda)
    SHOW_SLOTS           = "SHOW_SLOTS"           # slot picker cards
    SHOW_PATIENT_FORM    = "SHOW_PATIENT_FORM"    # returning/new patient info
    SHOW_PAYMENT         = "SHOW_PAYMENT"         # booking confirmation + payment trigger
    SHOW_CANCELLED       = "SHOW_CANCELLED"       # cancellation confirmation
    SHOW_RESCHEDULED       = "SHOW_RESCHEDULED"       # reschedule confirmation
    SHOW_SPECIALTY_CHOICE  = "SHOW_SPECIALTY_CHOICE"  # specialist vs GP choice buttons
    SHOW_CONFIRM_BOOKING   = "SHOW_CONFIRM_BOOKING"   # confirm booking button
    SHOW_PHONE_CHOICE      = "SHOW_PHONE_CHOICE"      # use logged-in number vs different number
    SHOW_PAID              = "SHOW_PAID"              # payment confirmed — show receipt


# ── ui_payload models — one per UIAction ──────────────────────────────────────

class EmergencyPayload(BaseModel):
    hotline:             str  = "1990"
    message:             str  = "This sounds like a medical emergency."
    allow_booking_after: bool = True


class LocationButton(BaseModel):
    value:   str   # "wattala" | "thalawathugoda"  — send this as the next message
    label:   str   # "Hemas Hospital Wattala"
    address: str   # "No. 389, Negombo Road, Wattala"


class LocationPickerPayload(BaseModel):
    buttons: list[LocationButton]


class SlotOption(BaseModel):
    slot_id:  str
    datetime: str
    label:    str   # human-readable e.g. "Wednesday, April 1 at 9:30 AM"


class DoctorSlots(BaseModel):
    doctor_id:   str
    doctor_name: str
    specialty:   str
    location:    str
    slots:       list[SlotOption]


class SlotsPayload(BaseModel):
    doctors:        list[DoctorSlots]
    fallback_used:  bool         = False
    fallback_reason: Optional[str] = None


class LastVisitInfo(BaseModel):
    date:        str
    specialty:   str
    doctor_name: str


class PatientFormPayload(BaseModel):
    is_returning:       bool
    patient_name:       Optional[str]          = None
    last_visit:         Optional[LastVisitInfo] = None
    is_recurring:       bool                   = False


class PaymentPayload(BaseModel):
    appointment_id:     str
    doctor_name:        str
    specialty:          str
    datetime:           str
    datetime_label:     str
    location:           str
    mentions_medication: bool = False
    is_recurring:       bool  = False


class CancelledPayload(BaseModel):
    appointment_id: str


class RescheduledPayload(BaseModel):
    appointment_id:    str
    doctor_name:       str
    new_datetime:      str
    new_datetime_label: str
    location:          str


class NavigationSnapshot(BaseModel):
    """A saved checkpoint of booking state for navigation rewind."""
    stage:                  str
    checkpoint:             str             # "specialty" | "location" | "slot"
    detected_specialty:     Optional[str] = None
    preferred_location:     Optional[str] = None
    available_doctors:      Optional[list] = None
    fallback_used:          bool = False
    fallback_reason:        Optional[str] = None
    pending_slot_id:        Optional[str] = None
    pending_slot_datetime:  Optional[str] = None
    pending_doctor_name:    Optional[str] = None
    pending_doctor_id:      Optional[str] = None
    pending_specialty:      Optional[str] = None
    pending_location:       Optional[str] = None


class PhoneChoicePayload(BaseModel):
    logged_in_phone: str   # e.g. "+94773609683" — send this as next message if tapped
    logged_in_label: str   # e.g. "Use my number (+94773609683)"
    other_label:     str   # e.g. "Use a different number"


class SpecialtyChoiceButton(BaseModel):
    value:    str   # "specialist" | "gp" — send this as next message
    label:    str   # "Book with Neurologist" | "Book with General Medicine"
    specialty: str  # actual specialty string to use


class SpecialtyChoicePayload(BaseModel):
    buttons:            list[SpecialtyChoiceButton]
    suggested_specialty: str
    reason:             str   # e.g. "Your symptoms suggest a possible migraine."


class ConfirmBookingPayload(BaseModel):
    doctor_name:    str
    specialty:      str
    datetime_label: str
    location:       str
    slot_id:        str   # frontend sends this as message when patient confirms

class PaidPayload(BaseModel):
    appointment_id: str
    doctor_name:    str
    datetime_label: str
    location:       str
    specialty:      str


# ── Stage → UIAction map ──────────────────────────────────────────────────────

_STAGE_TO_UI: dict[str, UIAction] = {
    "intake":           UIAction.SHOW_CHAT,
    "routing":          UIAction.SHOW_LOCATION_PICKER,
    "clarify":          UIAction.SHOW_CHAT,   # agent asks one question, no extra component
    "emergency":        UIAction.SHOW_EMERGENCY,
    "slots_shown":      UIAction.SHOW_SLOTS,
    "collecting":       UIAction.SHOW_PATIENT_FORM,
    "confirmed":        UIAction.SHOW_PAYMENT,
    "cancelled":        UIAction.SHOW_CANCELLED,
    "rescheduled":       UIAction.SHOW_RESCHEDULED,
    "specialty_choice":  UIAction.SHOW_SPECIALTY_CHOICE,
    "phone_choice":      UIAction.SHOW_PHONE_CHOICE,
    "paid":              UIAction.SHOW_PAID,
    "confirming":        UIAction.SHOW_CONFIRM_BOOKING,
}

def stage_to_ui_action(stage: str) -> UIAction:
    return _STAGE_TO_UI.get(stage, UIAction.SHOW_CHAT)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _format_datetime_label(iso_str: str) -> str:
    """Convert ISO datetime to human-readable label e.g. 'Wednesday, April 2 at 9:30 AM'"""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.strftime("%A, %B %-d at %-I:%M %p")
    except Exception:
        return iso_str


LOCATION_LABELS = {
    "wattala":        ("Hemas Hospital Wattala",        "No. 389, Negombo Road, Wattala"),
    "thalawathugoda": ("Hemas Hospital Thalawathugoda", "No. 6, Highland Drive, Thalawathugoda, Colombo 10"),
}


# ── BookingState ──────────────────────────────────────────────────────────────

class BookingState(BaseModel):
    stage: str = "intake"
    is_emergency: bool = False

    detected_specialty:     Optional[str] = None
    preferred_location:     Optional[str] = None

    selected_slot_id:       Optional[str] = None
    selected_slot_datetime: Optional[str] = None
    selected_doctor_id:     Optional[str] = None
    selected_doctor_name:   Optional[str] = None

    patient_id:             Optional[str] = None
    appointment_id:         Optional[str] = None
    mentions_medication:    bool = False
    is_recurring:           bool = False
    routing_tier:           Optional[str] = None   # "direct" | "gp_first" | "clarify" | "emergency"
    suggested_specialty:    Optional[str] = None   # for gp_first: specialist GP may refer to
    conversation_summary:   Optional[str] = None

    # Slot data — stored from check_availability result, used to build SHOW_SLOTS payload
    available_doctors:      Optional[list[dict]] = None
    fallback_used:          bool = False
    fallback_reason:        Optional[str] = None

    # Navigation stack — checkpoints for going back
    navigation_stack:       Optional[list] = None

    # Logged-in user's phone — sent by frontend, used to skip phone-number question
    user_phone: Optional[str] = None

    # Specialty choice — pending when agent narrowed down from gp_first
    specialty_choice_pending: bool = False
    specialty_choice_options: Optional[list[dict]] = None   # [{value, label, specialty}]
    specialty_choice_reason:  Optional[str] = None

    # Confirm booking — pending slot details for the confirm button
    pending_slot_id:        Optional[str] = None
    pending_slot_datetime:  Optional[str] = None
    pending_doctor_name:    Optional[str] = None
    pending_doctor_id:      Optional[str] = None
    pending_specialty:      Optional[str] = None
    pending_location:       Optional[str] = None

    # Patient info — stored from lookup result, used to build SHOW_PATIENT_FORM payload
    patient_name:           Optional[str] = None
    last_visit_date:        Optional[str] = None
    last_visit_specialty:   Optional[str] = None
    last_visit_doctor:      Optional[str] = None


class ChatRequest(BaseModel):
    session_id:    str           = Field(..., description="UUID — generate once per conversation")
    message:       str           = Field(..., description="Patient's latest message")
    user_phone:    Optional[str] = Field(None, description="Logged-in user's phone from Supabase auth. Send on every request when available.")
    history:       list[ChatMessage] = Field(default=[])
    booking_state: BookingState  = Field(default_factory=BookingState)


class ChatResponse(BaseModel):
    session_id: str
    reply:      str       = Field(..., description="Always display as assistant chat bubble")
    ui_action:  UIAction  = Field(..., description="Which component to render — switch on this")
    ui_payload: Optional[Any] = Field(None, description="Structured data for the component. Shape depends on ui_action.")
    state:      BookingState  = Field(..., description="Save and send back as booking_state next request")


# ── Appointments ──────────────────────────────────────────────────────────────

class AppointmentStatus(str, Enum):
    reserved     = "reserved"
    confirmed    = "confirmed"
    paid         = "paid"
    cancelled    = "cancelled"
    not_attended = "not_attended"


class AppointmentOut(BaseModel):
    id:               str
    patient_id:       str
    doctor_id:        str
    appointment_date: str
    status:           AppointmentStatus
    reason_for_visit: Optional[str] = None
    notes:            Optional[str] = None
    created_at:       Optional[str] = None
    doctor_name:      Optional[str] = None
    doctor_specialty: Optional[str] = None
    location:         Optional[str] = None


class CancelRequest(BaseModel):
    cancelled_by: str = Field(..., description="'patient' | 'admin' | 'doctor'")


class RescheduleRequest(BaseModel):
    new_slot_id:    str = Field(..., description="Synthetic slot ID: doctor_id::YYYY-MM-DDTHH:MM")
    new_doctor_id:  str = Field(..., description="UUID of the doctor for the new slot")
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
"""
POST /chat — main patient-facing AI endpoint.

How the frontend should use this:

1. On session start, generate a UUID as session_id. Store it.
2. Maintain `history: []` and `booking_state: {}` in frontend state.
3. On every send:
     - Append the user message to history AFTER getting a response (not before)
     - POST { session_id, message, history, booking_state }
     - Display response.reply in the chat UI
     - Save response.state as the new booking_state for the next request
     - Append { role: "user", content: message } and
             { role: "assistant", content: response.reply } to history

4. React to response.state.stage:
     "emergency"   → show red emergency banner, 1990 hotline button
     "slots_shown" → optionally highlight the slot options in the UI
     "confirmed"   → show booking confirmation card, offer payment/receipt
     "cancelled"   → show cancellation confirmation
"""

from fastapi import APIRouter, HTTPException
from app.models.schemas import ChatRequest, ChatResponse, BookingState
from app.agents.patient_agent import run_agent

router = APIRouter(prefix="/chat", tags=["Chat"])


@router.post("", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """
    Send a patient message to the HemasHealth IQ agent.

    The agent will:
    - Analyse symptoms and route to the right specialist
    - Check real-time doctor availability
    - Present available slots
    - Book the appointment once patient confirms
    - Handle emergencies with immediate escalation

    Returns the agent reply + updated booking state.
    """
    try:
        bs = req.booking_state
        result = await run_agent(
            new_message=req.message,
            history=req.history,
            patient_id=bs.patient_id,
            preferred_location=bs.preferred_location,
            current_stage=bs.stage,
            detected_specialty=bs.detected_specialty,
            selected_slot_id=bs.selected_slot_id,
            selected_slot_datetime=bs.selected_slot_datetime,
            selected_doctor_id=bs.selected_doctor_id,
            selected_doctor_name=bs.selected_doctor_name,
            appointment_id=bs.appointment_id,
            is_emergency=bs.is_emergency,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return ChatResponse(
        session_id=req.session_id,
        reply=result["reply"],
        state=BookingState(**result["state"]),
    )
from fastapi import APIRouter, HTTPException
from app.models.schemas import ChatRequest, ChatResponse, BookingState, stage_to_ui_action
from app.agents.patient_agent import run_agent

router = APIRouter(prefix="/chat", tags=["Chat"])


@router.post("", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """
    ## POST /chat — Patient-facing AI endpoint

    Send a patient message, get a reply + UI instruction back.

    ### Context optimization
    History is automatically compressed after 6 turns using a summarizer (gpt-4o-mini).
    The last 4 turns are always kept verbatim. The summary is stored in `state.conversation_summary`
    and must be sent back on every request inside `booking_state` — the frontend does not need to
    understand it, just store and return it.

    ### How to use from Next.js
    ```ts
    const res = await fetch("/chat", {
      method: "POST",
      body: JSON.stringify({
        session_id,      // uuid — generate once per conversation
        message,         // patient's latest message
        history,         // full conversation so far
        booking_state,   // send back exactly what the last response returned
      })
    })
    const { reply, ui_action, state } = await res.json()

    // 1. Display reply as assistant chat bubble
    // 2. Switch on ui_action to render the right component
    // 3. Save state as booking_state for next request
    // 4. Append { role:"user", content: message } and
    //           { role:"assistant", content: reply } to history
    ```

    ### ui_action values
    | Value | What to render |
    |-------|---------------|
    | SHOW_CHAT | Normal chat bubble |
    | SHOW_EMERGENCY | Red banner + 1990 call button |
    | SHOW_SLOTS | Chat bubble + optional slot picker |
    | SHOW_PATIENT_FORM | Chat bubble + name/phone form |
    | SHOW_PAYMENT | Booking confirmation + payment trigger |
    | SHOW_CANCELLED | Cancellation confirmation |
    | SHOW_RESCHEDULED | Reschedule confirmation |
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
            conversation_summary=bs.conversation_summary,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    new_state = BookingState(**result["state"])

    return ChatResponse(
        session_id=req.session_id,
        reply=result["reply"],
        ui_action=stage_to_ui_action(new_state.stage),
        state=new_state,
    )
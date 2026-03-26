from fastapi import APIRouter, HTTPException
from app.models.schemas import ChatRequest, ChatResponse, BookingState, stage_to_ui_action
from app.agents.patient_agent import run_agent

router = APIRouter(prefix="/chat", tags=["Chat"])


@router.post("", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """
    ## POST /chat — Patient-facing AI endpoint

    Send a patient message, get a reply + UI instruction back.

    ### How to use from Next.js

    ```ts
    const res = await fetch("/chat", {
      method: "POST",
      body: JSON.stringify({
        session_id,      // generate once with uuid()
        message,         // patient's typed message
        history,         // full conversation so far
        booking_state,   // send back exactly what last response returned
      })
    })
    const { reply, ui_action, state } = await res.json()

    // 1. Always display `reply` as the assistant chat bubble
    // 2. Switch on `ui_action` to decide what component to render:
    //
    //   SHOW_CHAT         → just the chat bubble, nothing extra
    //   SHOW_EMERGENCY    → red banner + 1990 call button
    //   SHOW_SLOTS        → reply has slot options (render as cards optionally)
    //   SHOW_PATIENT_FORM → render name/phone input form
    //   SHOW_PAYMENT      → appointment confirmed, open payment flow
    //   SHOW_CANCELLED    → show cancellation confirmation card
    //
    // 3. Save `state` → send back as `booking_state` next request
    // 4. Append { role:"user", content: message } and
    //           { role:"assistant", content: reply } to history
    ```
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

    new_state = BookingState(**result["state"])

    return ChatResponse(
        session_id=req.session_id,
        reply=result["reply"],
        ui_action=stage_to_ui_action(new_state.stage),
        state=new_state,
    )
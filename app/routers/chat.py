from fastapi import APIRouter, HTTPException
from app.models.schemas import ChatRequest, ChatResponse, BookingState, stage_to_ui_action
from app.agents.patient_agent import run_agent
from app.utils.pii_vault import get_vault, clear_vault

router = APIRouter(prefix="/chat", tags=["Chat"])


@router.post("", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """
    ## POST /chat — Patient-facing AI endpoint

    PII Safety:
    - A per-session PIIVault is created on first message using session_id.
    - All real patient IDs, appointment IDs, phone numbers are tokenised
      before reaching the LLM. The LLM only sees tokens like :::patient_id_1:::
    - Tokens are unmasked at tool-call time (in-memory only, never logged).
    - The final reply is unmasked so the patient sees their real information.
    - Conversation history stored on the frontend only contains tokens.

    Context optimisation:
    - History is summarised after 6 turns using gpt-4o-mini.
    - Last 4 turns always kept verbatim.
    - Summary stored in booking_state.conversation_summary.

    Usage from Next.js:
    ```ts
    const res = await fetch("/chat", {
      method: "POST",
      body: JSON.stringify({
        session_id,      // uuid — generate once per conversation, keep for vault lookup
        message,
        history,
        booking_state,   // send back exactly what last response returned
      })
    })
    const { reply, ui_action, state } = await res.json()
    // Switch on ui_action to decide what component to render
    // Store state as booking_state for next request
    ```
    """
    try:
        # Get or create the PII vault for this session
        vault = get_vault(req.session_id)

        bs     = req.booking_state
        result = await run_agent(
            new_message=req.message,
            history=req.history,
            vault=vault,
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

    # Clear vault once booking is fully confirmed — no more PII needed for this session
    if new_state.stage == "confirmed":
        clear_vault(req.session_id)

    return ChatResponse(
        session_id=req.session_id,
        reply=result["reply"],
        ui_action=stage_to_ui_action(new_state.stage),
        state=new_state,
    )
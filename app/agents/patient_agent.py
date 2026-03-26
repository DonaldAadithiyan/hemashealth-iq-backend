"""
patient_agent.py

Runs one conversation turn through the LangGraph booking graph.

Design:
  - The frontend is stateless from the backend's perspective.
  - On every request the frontend sends: new message + full history + any known context
    (patient_id from Supabase Auth, preferred_location from profile, etc.)
  - The graph reconstructs full state from this and runs to completion (one AI reply).
  - The response includes: reply text + structured state snapshot for the frontend to act on.
"""

from langchain_core.messages import HumanMessage, AIMessage

from app.graphs.booking_graph import compiled_graph, AgentState
from app.models.schemas import ChatMessage


def _build_state(
    history: list[ChatMessage],
    patient_id: str | None,
    preferred_location: str | None,
    current_stage: str,
    # Pass any booking context the frontend has been tracking
    detected_specialty: str | None = None,
    selected_slot_id: str | None = None,
    selected_slot_datetime: str | None = None,
    selected_doctor_id: str | None = None,
    selected_doctor_name: str | None = None,
    appointment_id: str | None = None,
    is_emergency: bool = False,
) -> AgentState:
    """Convert incoming request into AgentState for the graph."""
    messages = []
    for msg in history:
        if msg.role == "user":
            messages.append(HumanMessage(content=msg.content))
        elif msg.role == "assistant":
            messages.append(AIMessage(content=msg.content))

    return AgentState(
        messages=messages,
        stage=current_stage,
        is_emergency=is_emergency,
        detected_specialty=detected_specialty,
        preferred_location=preferred_location,
        selected_slot_id=selected_slot_id,
        selected_slot_datetime=selected_slot_datetime,
        selected_doctor_id=selected_doctor_id,
        selected_doctor_name=selected_doctor_name,
        patient_id=patient_id,
        appointment_id=appointment_id,
    )


async def run_agent(
    new_message: str,
    history: list[ChatMessage],
    # Context from frontend
    patient_id: str | None = None,
    preferred_location: str | None = None,
    current_stage: str = "intake",
    detected_specialty: str | None = None,
    selected_slot_id: str | None = None,
    selected_slot_datetime: str | None = None,
    selected_doctor_id: str | None = None,
    selected_doctor_name: str | None = None,
    appointment_id: str | None = None,
    is_emergency: bool = False,
) -> dict:
    """
    Run one turn. Returns:
      reply: str                — the agent's message to show the patient
      state: dict               — full booking state snapshot for the frontend
    """
    state = _build_state(
        history=history,
        patient_id=patient_id,
        preferred_location=preferred_location,
        current_stage=current_stage,
        detected_specialty=detected_specialty,
        selected_slot_id=selected_slot_id,
        selected_slot_datetime=selected_slot_datetime,
        selected_doctor_id=selected_doctor_id,
        selected_doctor_name=selected_doctor_name,
        appointment_id=appointment_id,
        is_emergency=is_emergency,
    )

    # Append the new user message before running
    state["messages"].append(HumanMessage(content=new_message))

    result: AgentState = await compiled_graph.ainvoke(state)

    # Extract the last AI reply
    reply = ""
    for msg in reversed(result["messages"]):
        if isinstance(msg, AIMessage) and msg.content:
            reply = msg.content
            break

    # Return state snapshot — frontend stores this and sends it back next turn
    return {
        "reply": reply,
        "state": {
            "stage":                  result.get("stage", "intake"),
            "is_emergency":           result.get("is_emergency", False),
            "detected_specialty":     result.get("detected_specialty"),
            "preferred_location":     result.get("preferred_location"),
            "selected_slot_id":       result.get("selected_slot_id"),
            "selected_slot_datetime": result.get("selected_slot_datetime"),
            "selected_doctor_id":     result.get("selected_doctor_id"),
            "selected_doctor_name":   result.get("selected_doctor_name"),
            "patient_id":             result.get("patient_id"),
            "appointment_id":         result.get("appointment_id"),
        },
    }
"""
patient_agent.py

Runs one conversation turn through the LangGraph booking graph.

Hybrid context strategy (Option 4):
  - If history is short (≤ SUMMARIZE_AFTER_TURNS turns): send everything verbatim
  - If history is long: summarize old turns with gpt-4o-mini, keep last 4 verbatim
  - Summary is stored in BookingState.conversation_summary and accumulates across turns
  - The graph always sees: [system] + [summary message if exists] + [last N verbatim] + [new message]
"""

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from app.graphs.booking_graph import compiled_graph, AgentState
from app.models.schemas import ChatMessage, BookingState
from app.utils.summarizer import (
    should_summarize,
    split_history,
    summarize_messages,
    KEEP_VERBATIM_TURNS,
)


def _to_lc_messages(history: list[ChatMessage]) -> list:
    """Convert frontend ChatMessage list to LangChain message objects."""
    messages = []
    for msg in history:
        if msg.role == "user":
            messages.append(HumanMessage(content=msg.content))
        elif msg.role == "assistant":
            messages.append(AIMessage(content=msg.content))
    return messages


async def _build_context(
    new_message: str,
    history: list[ChatMessage],
    existing_summary: str | None,
) -> tuple[list, str | None]:
    """
    Build the message list to send to the graph this turn.
    Also returns the new summary (if summarization ran) or the existing one.

    Returns:
        messages:    list of LangChain messages (summary injection + verbatim + new)
        new_summary: updated summary string, or None if no summarization ran
    """
    all_messages = _to_lc_messages(history)
    new_summary = existing_summary

    if should_summarize(len(all_messages)):
        to_summarize, to_keep = split_history(all_messages)

        if to_summarize:
            # Run summarizer — cheap gpt-4o-mini call
            new_summary = await summarize_messages(to_summarize, existing_summary)
            messages_to_use = to_keep
        else:
            messages_to_use = all_messages
    else:
        messages_to_use = all_messages

    # Inject summary as a SystemMessage so the LLM treats it as ground truth
    context_messages = []
    if new_summary:
        context_messages.append(
            SystemMessage(content=f"[Conversation so far]\n{new_summary}")
        )

    context_messages.extend(messages_to_use)
    context_messages.append(HumanMessage(content=new_message))

    return context_messages, new_summary


def _build_state(
    messages: list,
    patient_id: str | None,
    preferred_location: str | None,
    current_stage: str,
    detected_specialty: str | None = None,
    selected_slot_id: str | None = None,
    selected_slot_datetime: str | None = None,
    selected_doctor_id: str | None = None,
    selected_doctor_name: str | None = None,
    appointment_id: str | None = None,
    is_emergency: bool = False,
) -> AgentState:
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
    conversation_summary: str | None = None,
) -> dict:
    """
    Run one turn. Returns:
      reply:                str   — agent's message to display
      state:                dict  — full booking state snapshot for the frontend
      conversation_summary: str   — updated summary (store in BookingState)
    """
    # Build optimized context
    context_messages, new_summary = await _build_context(
        new_message=new_message,
        history=history,
        existing_summary=conversation_summary,
    )

    state = _build_state(
        messages=context_messages,
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

    result: AgentState = await compiled_graph.ainvoke(state)

    # Extract last AI reply
    reply = ""
    for msg in reversed(result["messages"]):
        if isinstance(msg, AIMessage) and msg.content:
            reply = msg.content
            break

    return {
        "reply": reply,
        "conversation_summary": new_summary,
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
            "conversation_summary":   new_summary,
        },
    }
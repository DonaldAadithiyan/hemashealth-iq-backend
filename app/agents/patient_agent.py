"""
patient_agent.py — Runs one conversation turn through the booking graph.

PII flow:
  1. BookingState values (patient_id, appointment_id etc.) are registered
     in the vault and replaced with tokens before building LLM context.
  2. The graph runs with tokens only visible to the LLM.
  3. The final AI reply is unmasked before returning to the patient
     (they should see their real appointment ID, doctor name etc.)
  4. History stored on the frontend only ever contains tokens.

Context optimisation (hybrid summariser):
  Old turns are summarised with gpt-4o-mini after SUMMARIZE_AFTER_TURNS turns.
  Last KEEP_VERBATIM_TURNS turns stay verbatim.
"""

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from app.graphs.booking_graph import compiled_graph, AgentState
from app.models.schemas import ChatMessage, BookingState
from app.utils.pii_vault import PIIVault
from app.utils.summarizer import (
    should_summarize,
    split_history,
    summarize_messages,
)


def _to_lc_messages(history: list[ChatMessage]) -> list:
    messages = []
    for msg in history:
        if msg.role == "user":
            messages.append(HumanMessage(content=msg.content))
        elif msg.role == "assistant":
            messages.append(AIMessage(content=msg.content))
    return messages


def _register_booking_state(vault: PIIVault, bs_dict: dict):
    """
    Pre-register all known PII from BookingState into the vault
    so those values are tokenised if they appear in history or context.
    """
    registrations = {
        "patient_id":             bs_dict.get("patient_id"),
        "appointment_id":         bs_dict.get("appointment_id"),
        "doctor_id":              bs_dict.get("selected_doctor_id"),
        "slot_id":                bs_dict.get("selected_slot_id"),
    }
    for label, value in registrations.items():
        if value:
            vault.register(label, value)


async def _build_context(
    new_message: str,
    history: list[ChatMessage],
    existing_summary: str | None,
    vault: PIIVault,
) -> tuple[list, str | None]:
    """
    Build optimised, PII-safe message list for the graph.
    History is already tokenised (frontend stores only tokens).
    New message is masked before sending to LLM.
    """
    all_messages  = _to_lc_messages(history)
    new_summary   = existing_summary

    # Summarise if needed
    if should_summarize(len(all_messages)):
        to_summarize, to_keep = split_history(all_messages)
        if to_summarize:
            new_summary   = await summarize_messages(to_summarize, existing_summary)
            messages_to_use = to_keep
        else:
            messages_to_use = all_messages
    else:
        messages_to_use = all_messages

    context_messages = []

    # Inject summary as a system message
    if new_summary:
        context_messages.append(
            SystemMessage(content=f"[Conversation so far]\n{new_summary}")
        )

    context_messages.extend(messages_to_use)

    # Mask the new user message before it reaches the LLM
    safe_new_message = vault.mask_text(new_message)
    context_messages.append(HumanMessage(content=safe_new_message))

    return context_messages, new_summary


async def run_agent(
    new_message: str,
    history: list[ChatMessage],
    vault: PIIVault,
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
    mentions_medication: bool = False,
    is_recurring: bool = False,
    routing_tier: str | None = None,
    suggested_specialty: str | None = None,
    available_doctors: list | None = None,
    fallback_used: bool = False,
    fallback_reason: str | None = None,
    patient_name: str | None = None,
    last_visit_date: str | None = None,
    last_visit_specialty: str | None = None,
    last_visit_doctor: str | None = None,
    conversation_summary: str | None = None,
) -> dict:
    """
    Run one turn through the booking graph.

    Returns:
        reply:                str  — unmasked reply for the patient
        conversation_summary: str  — updated summary (may contain tokens, not real PII)
        state:                dict — updated booking state (real values, server-side only)
    """
    # Register known PII from current booking state into vault
    bs_dict = {
        "patient_id":         patient_id,
        "appointment_id":     appointment_id,
        "selected_doctor_id": selected_doctor_id,
        "selected_slot_id":   selected_slot_id,
    }
    _register_booking_state(vault, bs_dict)

    # Build PII-safe context
    context_messages, new_summary = await _build_context(
        new_message=new_message,
        history=history,
        existing_summary=conversation_summary,
        vault=vault,
    )

    state = AgentState(
        messages=context_messages,
        stage=current_stage,
        is_emergency=is_emergency,
        mentions_medication=mentions_medication,
        is_recurring=is_recurring,
        routing_tier=routing_tier,
        suggested_specialty=suggested_specialty,
        detected_specialty=detected_specialty,
        preferred_location=preferred_location,
        selected_slot_id=selected_slot_id,
        selected_slot_datetime=selected_slot_datetime,
        selected_doctor_id=selected_doctor_id,
        selected_doctor_name=selected_doctor_name,
        patient_id=patient_id,
        appointment_id=appointment_id,
        available_doctors=available_doctors,
        fallback_used=fallback_used,
        fallback_reason=fallback_reason,
        patient_name=patient_name,
        last_visit_date=last_visit_date,
        last_visit_specialty=last_visit_specialty,
        last_visit_doctor=last_visit_doctor,
        vault=vault,
    )

    result: AgentState = await compiled_graph.ainvoke(state)

    # Extract last AI reply
    raw_reply = ""
    for msg in reversed(result["messages"]):
        if isinstance(msg, AIMessage) and msg.content:
            raw_reply = msg.content
            break

    # Unmask tokens in the reply — the patient sees real values
    reply = vault.unmask_text(raw_reply)

    return {
        "reply":                reply,
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
            "mentions_medication":     result.get("mentions_medication", False),
            "is_recurring":            result.get("is_recurring", False),
            "routing_tier":            result.get("routing_tier"),
            "suggested_specialty":     result.get("suggested_specialty"),
            "available_doctors":       result.get("available_doctors"),
            "fallback_used":           result.get("fallback_used", False),
            "fallback_reason":         result.get("fallback_reason"),
            "patient_name":            result.get("patient_name"),
            "last_visit_date":         result.get("last_visit_date"),
            "last_visit_specialty":    result.get("last_visit_specialty"),
            "last_visit_doctor":       result.get("last_visit_doctor"),
            "conversation_summary":   new_summary,
        },
    }
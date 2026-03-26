"""
HemasHealth IQ — LangGraph Booking Graph

How it works:
  Each patient message triggers one full graph run.
  The frontend sends the FULL conversation history every turn (stateless backend).
  The graph runs: agent → (tools → agent)* → END
  It always ends with an AI reply to the patient.

Stages tracked in state (returned to frontend on every response):
  intake        → patient is describing symptoms
  routing       → route_to_specialist called, specialty identified
  emergency     → red-flag symptoms detected (frontend shows emergency UI)
  slots_shown   → availability shown, waiting for patient to pick
  collecting    → collecting patient name/phone (new patients)
  confirmed     → appointment booked successfully
  cancelled     → appointment cancelled
"""

import json
from typing import Annotated, TypedDict, Any

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from app.config import get_settings
from app.prompts.system_prompt import SYSTEM_PROMPT
from app.tools.routing import route_to_specialist
from app.tools.availability import check_availability
from app.tools.patient import lookup_or_create_patient
from app.tools.booking import book_appointment, cancel_appointment

ALL_TOOLS = [
    route_to_specialist,
    check_availability,
    lookup_or_create_patient,
    book_appointment,
    cancel_appointment,
]


# ── State ─────────────────────────────────────────────────────────────────────

class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]

    # Booking context — built up across turns
    stage: str                       # current conversation stage
    is_emergency: bool

    detected_specialty: str | None   # set after route_to_specialist
    preferred_location: str | None   # wattala | thalawathugoda

    # Slot the patient chose
    selected_slot_id: str | None
    selected_slot_datetime: str | None
    selected_doctor_id: str | None
    selected_doctor_name: str | None

    # Patient
    patient_id: str | None           # set after lookup_or_create_patient

    # Final result
    appointment_id: str | None       # set after book_appointment succeeds


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_tool_message(msg: ToolMessage) -> dict:
    try:
        data = json.loads(msg.content) if isinstance(msg.content, str) else msg.content
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


# ── Build graph ───────────────────────────────────────────────────────────────

def build_graph():
    settings = get_settings()

    llm = ChatOpenAI(
        model="gpt-4o",
        temperature=0.2,
        api_key=settings.openai_api_key,
    ).bind_tools(ALL_TOOLS)

    tool_node = ToolNode(ALL_TOOLS)

    # ── Node: agent ───────────────────────────────────────────────────────────

    def agent_node(state: AgentState) -> dict:
        """LLM decides: call a tool, or reply to the patient and stop."""
        response = llm.invoke([SystemMessage(content=SYSTEM_PROMPT)] + state["messages"])
        return {"messages": [response]}

    # ── Node: tools ───────────────────────────────────────────────────────────

    def tools_node(state: AgentState) -> dict:
        """
        Execute tool calls, then update booking state based on results.
        This is the only place state fields (stage, specialty, etc.) are written.
        """
        result = tool_node.invoke(state)
        tool_messages: list[ToolMessage] = result.get("messages", [])
        extra: dict[str, Any] = {}

        for msg in tool_messages:
            if not isinstance(msg, ToolMessage):
                continue
            data = _parse_tool_message(msg)
            name = getattr(msg, "name", "")

            if name == "route_to_specialist":
                specialty = data.get("specialty")
                is_emergency = data.get("is_emergency", False)
                extra["detected_specialty"] = specialty
                extra["is_emergency"] = is_emergency
                extra["stage"] = "emergency" if is_emergency else "routing"

            elif name == "check_availability":
                # Slots are in the tool message content — the LLM reads and presents them.
                # We just advance the stage so the frontend knows slots were shown.
                extra["stage"] = "slots_shown"

            elif name == "lookup_or_create_patient":
                if data.get("patient_id"):
                    extra["patient_id"] = data["patient_id"]
                    extra["stage"] = "collecting"

            elif name == "book_appointment":
                if data.get("status") == "confirmed":
                    extra["appointment_id"] = data.get("appointment_id")
                    extra["selected_doctor_name"] = data.get("doctor_name")
                    extra["selected_slot_datetime"] = data.get("slot_datetime")
                    extra["stage"] = "confirmed"
                # If failed, stage stays as-is so the LLM can retry/apologise

            elif name == "cancel_appointment":
                if data.get("success"):
                    extra["stage"] = "cancelled"

        return {"messages": tool_messages, **extra}

    # ── Edge: should the agent call more tools or stop? ───────────────────────

    def should_continue(state: AgentState) -> str:
        last = state["messages"][-1]
        if hasattr(last, "tool_calls") and last.tool_calls:
            return "tools"
        return END

    # ── Assemble ──────────────────────────────────────────────────────────────

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tools_node)
    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")

    return graph.compile()


compiled_graph = build_graph()
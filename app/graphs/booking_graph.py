"""
HemasHealth IQ — LangGraph Booking Graph

Flow per turn:
  agent → tools → agent → ... → END
  Always ends with one AI reply to the patient.

Each node prints what it's doing so you can follow along in the terminal.
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
from app.tools.booking import book_appointment, cancel_appointment, reschedule_appointment

ALL_TOOLS = [
    route_to_specialist,
    check_availability,
    lookup_or_create_patient,
    book_appointment,
    cancel_appointment,
    reschedule_appointment,
]

# ── Terminal colours ──────────────────────────────────────────────────────────
R  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
CYAN   = "\033[96m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
MAGENTA= "\033[95m"
RED    = "\033[91m"
BLUE   = "\033[94m"

TOOL_COLOURS = {
    "route_to_specialist":     MAGENTA,
    "check_availability":      BLUE,
    "lookup_or_create_patient":YELLOW,
    "book_appointment":        GREEN,
    "cancel_appointment":      RED,
    "reschedule_appointment":  YELLOW,
}

def _log_node(name: str, colour: str = CYAN):
    print(f"\n{DIM}┌─ NODE: {colour}{BOLD}{name}{R}{DIM} {'─' * (40 - len(name))}┐{R}")

def _log_tool_call(tool_name: str, args: dict):
    c = TOOL_COLOURS.get(tool_name, CYAN)
    print(f"{DIM}│  🔧 TOOL CALL → {c}{BOLD}{tool_name}{R}")
    for k, v in args.items():
        print(f"{DIM}│     {k}: {c}{v}{R}")

def _log_tool_result(tool_name: str, result: dict):
    c = TOOL_COLOURS.get(tool_name, CYAN)
    print(f"{DIM}│  ✅ TOOL RESULT ← {c}{BOLD}{tool_name}{R}")
    for k, v in result.items():
        print(f"{DIM}│     {k}: {v}{R}")

def _log_stage(old: str, new: str):
    if old != new:
        print(f"{DIM}│  📍 STAGE: {YELLOW}{old}{R}{DIM} → {GREEN}{new}{R}")

def _log_node_end():
    print(f"{DIM}└{'─' * 50}┘{R}")


# ── State ─────────────────────────────────────────────────────────────────────

class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    stage: str
    is_emergency: bool
    detected_specialty: str | None
    preferred_location: str | None
    selected_slot_id: str | None
    selected_slot_datetime: str | None
    selected_doctor_id: str | None
    selected_doctor_name: str | None
    patient_id: str | None
    appointment_id: str | None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_tool_msg(msg: ToolMessage) -> dict:
    try:
        data = json.loads(msg.content) if isinstance(msg.content, str) else msg.content
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


# ── Graph ─────────────────────────────────────────────────────────────────────

def build_graph():
    settings = get_settings()

    llm = ChatOpenAI(
        model="gpt-4o",
        temperature=0.2,
        api_key=settings.openai_api_key,
    ).bind_tools(ALL_TOOLS)

    tool_node = ToolNode(ALL_TOOLS)

    # ── Agent node ────────────────────────────────────────────────────────────

    def agent_node(state: AgentState) -> dict:
        _log_node("AGENT", CYAN)
        print(f"{DIM}│  💬 Messages in context: {len(state['messages'])}{R}")
        print(f"{DIM}│  📍 Current stage: {YELLOW}{state.get('stage', 'intake')}{R}")

        response = llm.invoke([SystemMessage(content=SYSTEM_PROMPT)] + state["messages"])

        # Log what the LLM decided to do
        if hasattr(response, "tool_calls") and response.tool_calls:
            for tc in response.tool_calls:
                _log_tool_call(tc["name"], tc.get("args", {}))
        else:
            preview = str(response.content)[:80].replace("\n", " ")
            print(f"{DIM}│  💬 Reply: \"{preview}...\"{R}")

        _log_node_end()
        return {"messages": [response]}

    # ── Tools node ────────────────────────────────────────────────────────────

    def tools_node(state: AgentState) -> dict:
        _log_node("TOOLS", MAGENTA)

        old_stage = state.get("stage", "intake")
        result = tool_node.invoke(state)
        tool_messages: list[ToolMessage] = result.get("messages", [])
        extra: dict[str, Any] = {}

        for msg in tool_messages:
            if not isinstance(msg, ToolMessage):
                continue
            data = _parse_tool_msg(msg)
            name = getattr(msg, "name", "")
            _log_tool_result(name, data)

            if name == "route_to_specialist":
                specialty    = data.get("specialty")
                is_emergency = data.get("is_emergency", False)
                extra["detected_specialty"] = specialty
                extra["is_emergency"]        = is_emergency
                extra["stage"]               = "emergency" if is_emergency else "routing"

            elif name == "check_availability":
                extra["stage"] = "slots_shown"

            elif name == "lookup_or_create_patient":
                if data.get("patient_id"):
                    extra["patient_id"] = data["patient_id"]
                    extra["stage"]      = "collecting"

            elif name == "book_appointment":
                if data.get("status") == "confirmed":
                    extra["appointment_id"]         = data.get("appointment_id")
                    extra["selected_doctor_name"]   = data.get("doctor_name")
                    extra["selected_slot_datetime"] = data.get("slot_datetime")
                    extra["stage"]                  = "confirmed"
                else:
                    print(f"{DIM}│  ⚠️  booking FAILED: {data.get('error')}{R}")

            elif name == "cancel_appointment":
                if data.get("success"):
                    extra["stage"] = "cancelled"

            elif name == "reschedule_appointment":
                if data.get("status") == "rescheduled":
                    extra["selected_slot_datetime"] = data.get("new_slot_datetime")
                    extra["selected_doctor_name"]   = data.get("doctor_name")
                    extra["stage"]                  = "confirmed"

        new_stage = extra.get("stage", old_stage)
        _log_stage(old_stage, new_stage)
        _log_node_end()

        return {"messages": tool_messages, **extra}

    # ── Router ────────────────────────────────────────────────────────────────

    def should_continue(state: AgentState) -> str:
        last = state["messages"][-1]
        if hasattr(last, "tool_calls") and last.tool_calls:
            print(f"{DIM}  ↪ routing to TOOLS{R}")
            return "tools"
        print(f"{DIM}  ↪ routing to END (reply ready){R}")
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
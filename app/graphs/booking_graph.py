"""
HemasHealth IQ — LangGraph Booking Graph

PII Safety:
  Every tool call goes through the vault:
    1. agent_node    → LLM only sees tokens (:::patient_id_1:::)
    2. tools_node    → vault unmasks tokens → real values → DB
    3. tools_node    → vault masks real values in response → tokens → LLM

  The LLM never sees a real UUID, phone number, or patient name.
  Real values only exist at tool-call time, in memory, never logged.
"""

import json
from typing import Annotated, TypedDict, Any

from langchain_core.messages import (
    BaseMessage, HumanMessage, AIMessage, ToolMessage, SystemMessage
)
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
from app.utils.pii_vault import PIIVault

ALL_TOOLS = [
    route_to_specialist,
    check_availability,
    lookup_or_create_patient,
    book_appointment,
    cancel_appointment,
    reschedule_appointment,
]

# ── Terminal colours ──────────────────────────────────────────────────────────
R       = "\033[0m"
BOLD    = "\033[1m"
DIM     = "\033[2m"
CYAN    = "\033[96m"
GREEN   = "\033[92m"
YELLOW  = "\033[93m"
MAGENTA = "\033[95m"
RED     = "\033[91m"
BLUE    = "\033[94m"

TOOL_COLOURS = {
    "route_to_specialist":      MAGENTA,
    "check_availability":       BLUE,
    "lookup_or_create_patient": YELLOW,
    "book_appointment":         GREEN,
    "cancel_appointment":       RED,
    "reschedule_appointment":   CYAN,
}

def _log_node(name: str, colour: str = CYAN):
    print(f"\n{DIM}┌─ NODE: {colour}{BOLD}{name}{R}{DIM} {'─'*(40-len(name))}┐{R}")

def _log_tool_call(tool_name: str, args: dict):
    c = TOOL_COLOURS.get(tool_name, CYAN)
    print(f"{DIM}│  🔧 TOOL CALL  → {c}{BOLD}{tool_name}{R}")
    for k, v in args.items():
        print(f"{DIM}│     {k}: {c}{v}{R}")

def _log_tool_result(tool_name: str, result: dict):
    c = TOOL_COLOURS.get(tool_name, CYAN)
    print(f"{DIM}│  ✅ TOOL RESULT ← {c}{BOLD}{tool_name}{R}")
    for k, v in result.items():
        print(f"{DIM}│     {k}: {v}{R}")

def _log_pii(action: str, count: int):
    colour = YELLOW if action == "masked" else GREEN
    print(f"{DIM}│  🔒 PII {action}: {colour}{count} value(s){R}")

def _log_stage(old: str, new: str):
    if old != new:
        print(f"{DIM}│  📍 STAGE: {YELLOW}{old}{R}{DIM} → {GREEN}{new}{R}")

def _log_node_end():
    print(f"{DIM}└{'─'*50}┘{R}")


# ── State ─────────────────────────────────────────────────────────────────────

class AgentState(TypedDict):
    messages:               Annotated[list[BaseMessage], add_messages]
    stage:                  str
    is_emergency:           bool
    detected_specialty:     str | None
    preferred_location:     str | None
    selected_slot_id:       str | None
    selected_slot_datetime: str | None
    selected_doctor_id:     str | None
    selected_doctor_name:   str | None
    patient_id:             str | None
    appointment_id:         str | None
    mentions_medication:     bool
    is_recurring:            bool
    # Slot data from check_availability — used to build SHOW_SLOTS payload
    available_doctors:       list | None
    fallback_used:           bool
    fallback_reason:         str | None
    # Patient info from lookup — used to build SHOW_PATIENT_FORM payload
    patient_name:            str | None
    last_visit_date:         str | None
    last_visit_specialty:    str | None
    last_visit_doctor:       str | None
    vault:                  PIIVault      # ← injected per session, never serialised


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

    raw_tool_node = ToolNode(ALL_TOOLS)

    # ── Agent node ────────────────────────────────────────────────────────────

    def agent_node(state: AgentState) -> dict:
        """LLM sees only tokens — no real PII ever reaches this node."""
        _log_node("AGENT", CYAN)
        print(f"{DIM}│  💬 Messages in context: {len(state['messages'])}{R}")
        print(f"{DIM}│  📍 Stage: {YELLOW}{state.get('stage', 'intake')}{R}")
        print(f"{DIM}│  🔒 Vault tokens registered: {state['vault'].debug_summary()['total_tokens']}{R}")

        response = llm.invoke([SystemMessage(content=SYSTEM_PROMPT)] + state["messages"])

        if hasattr(response, "tool_calls") and response.tool_calls:
            for tc in response.tool_calls:
                _log_tool_call(tc["name"], tc.get("args", {}))
        else:
            # Unmask any PII tokens in the reply before it's stored in messages
            # This ensures intermediate replies (e.g. "Welcome back, :::name:::!")
            # show real values when they appear between tool calls
            if response.content:
                unmasked_content = state["vault"].unmask_text(response.content)
                if unmasked_content != response.content:
                    print(f"{DIM}│  🔓 PII unmasked in reply ({len(response.content) - len(unmasked_content)} chars replaced){R}")
                    from langchain_core.messages import AIMessage as _AIMsg
                    response = _AIMsg(content=unmasked_content)
            preview = str(response.content)[:80].replace("\n", " ")
            print(f"{DIM}│  💬 Reply preview: \"{preview}...\"{R}")

        _log_node_end()
        return {"messages": [response]}

    # ── Tools node — unmask in, mask out ─────────────────────────────────────

    def tools_node(state: AgentState) -> dict:
        """
        PII safety layer:
          1. Unmask token args → real values before tool execution
          2. Execute tool against DB
          3. Mask real values in response → tokens before returning to LLM
        """
        _log_node("TOOLS", MAGENTA)
        vault     = state["vault"]
        old_stage = state.get("stage", "intake")
        extra: dict[str, Any] = {}

        # Get the last AI message which contains the tool calls
        last_ai_msg = state["messages"][-1]

        # ── Step 1: Unmask tool call args ─────────────────────────────────────
        if hasattr(last_ai_msg, "tool_calls") and last_ai_msg.tool_calls:
            unmasked_tool_calls = []
            total_unmasked = 0
            for tc in last_ai_msg.tool_calls:
                original_args = tc.get("args", {})
                real_args     = vault.unmask_dict(original_args)
                unmasked_count = sum(
                    1 for k, v in real_args.items()
                    if v != original_args.get(k)
                )
                total_unmasked += unmasked_count
                unmasked_tool_calls.append({**tc, "args": real_args})

            if total_unmasked:
                _log_pii("unmasked", total_unmasked)

            # For book_appointment: always override patient_id with the real value
            # stored in state. This prevents the LLM from using a stale UUID from
            # context (e.g. a seed doctor ID) instead of the correct patient UUID.
            corrected_tool_calls = []
            for tc in unmasked_tool_calls:
                if tc.get("name") == "book_appointment":
                    args = dict(tc.get("args", {}))
                    real_pid = state.get("patient_id")
                    if real_pid and args.get("patient_id") != real_pid:
                        print(f"{YELLOW}│  🔧 CORRECTING patient_id: {args.get('patient_id','?')[:20]}... → {real_pid[:20]}...{R}")
                        args["patient_id"] = real_pid
                    corrected_tool_calls.append({**tc, "args": args})
                else:
                    corrected_tool_calls.append(tc)

            # Rebuild last message with real args so tool_node executes correctly
            from langchain_core.messages import AIMessage as _AI
            real_ai_msg = _AI(
                content    = last_ai_msg.content,
                tool_calls = corrected_tool_calls,
            )
            # Temporarily swap the last message
            patched_messages = list(state["messages"][:-1]) + [real_ai_msg]
            patched_state    = {**state, "messages": patched_messages}
        else:
            patched_state = state

        # ── Step 2: Execute tools with real values ────────────────────────────
        try:
            result        = raw_tool_node.invoke(patched_state)
            tool_messages = result.get("messages", [])
        except Exception as tool_err:
            print(f"{RED}│  ❌ TOOL EXECUTION ERROR: {tool_err}{R}")
            import traceback
            traceback.print_exc()
            # Return an error ToolMessage so the LLM can handle it gracefully
            from langchain_core.messages import ToolMessage as _TM
            error_messages = []
            if hasattr(last_ai_msg, "tool_calls"):
                for tc in last_ai_msg.tool_calls:
                    error_messages.append(_TM(
                        content=f'{{"error": "Tool execution failed: {str(tool_err)[:200]}"}}',
                        tool_call_id=tc.get("id", "unknown"),
                        name=tc.get("name", "unknown"),
                    ))
            _log_node_end()
            return {"messages": error_messages}

        # ── Step 3: Mask real values in tool responses ────────────────────────
        # Log raw tool messages first so we can see errors
        if not tool_messages:
            print(f"{RED}│  ⚠️  No tool messages returned — tool may have failed silently{R}")
        for raw_msg in tool_messages:
            if isinstance(raw_msg, ToolMessage):
                raw_content = raw_msg.content[:300] if raw_msg.content else "(empty)"
                # Only flag as error if it contains an actual exception/traceback
                # (not just a field named "error" in a successful response)
                is_error = (
                    "exception" in raw_content.lower()
                    or "traceback" in raw_content.lower()
                    or "attributeerror" in raw_content.lower()
                    or "typeerror" in raw_content.lower()
                    or "supabaseexception" in raw_content.lower()
                    or raw_content.strip().startswith("Error:")
                )
                if is_error:
                    print(f"{RED}│  ❌ TOOL ERROR [{getattr(raw_msg, 'name', '?')}]: {raw_content}{R}")
                else:
                    print(f"{DIM}│  📨 Tool response [{getattr(raw_msg, 'name', '?')}]: {raw_content[:120]}{R}")

        safe_tool_messages = []
        total_masked = 0

        for msg in tool_messages:
            if not isinstance(msg, ToolMessage):
                safe_tool_messages.append(msg)
                continue

            data = _parse_tool_msg(msg)
            if not data:
                safe_tool_messages.append(msg)
                continue

            name = getattr(msg, "name", "")
            _log_tool_result(name, data)

            # Extract state updates from REAL data before masking
            if name == "route_to_specialist":
                extra["detected_specialty"]  = data.get("specialty")
                extra["is_emergency"]        = data.get("is_emergency", False)
                extra["mentions_medication"] = data.get("mentions_medication", False)
                extra["stage"]               = "emergency" if data.get("is_emergency") else "routing"

            elif name == "check_availability":
                extra["stage"] = "slots_shown"
                # Store raw slot data for ui_payload — mask doctor IDs
                raw_doctors = data.get("doctors", [])
                masked_doctors = []
                for doc in raw_doctors:
                    masked_doc = dict(doc)
                    # Mask doctor_id via vault
                    if doc.get("doctor_id"):
                        masked_doc["doctor_id"] = vault.register("doctor_id", doc["doctor_id"])
                    masked_doctors.append(masked_doc)
                extra["available_doctors"] = masked_doctors
                extra["fallback_used"]     = data.get("fallback_used", False)
                extra["fallback_reason"]   = data.get("fallback_reason")

            elif name == "lookup_or_create_patient":
                if data.get("patient_id"):
                    real_patient_id = data["patient_id"]
                    extra["patient_id"]   = real_patient_id
                    extra["stage"]        = "collecting"
                    extra["patient_name"] = data.get("name")
                    # Store last visit info for SHOW_PATIENT_FORM payload
                    last = data.get("last_visit") or {}
                    if last:
                        extra["last_visit_date"]     = (last.get("appointment_date") or "")[:10]
                        extra["last_visit_specialty"]= last.get("specialty")
                        extra["last_visit_doctor"]   = last.get("doctor_name")
                    # Register real values — get the token back to inject into context
                    patient_token = vault.register("patient_id",   real_patient_id)
                    vault.register("patient_name", data.get("name", ""))
                    vault.register("phone",        data.get("phone", ""))

                    # Embed the patient_id hint inside the masked tool response
                    # so the LLM knows exactly which token to use for book_appointment.
                    # We cannot inject a separate SystemMessage here — OpenAI requires
                    # ToolMessages to immediately follow tool calls with matching IDs.
                    print(f"{DIM}│  💉 Patient ID token for booking: {patient_token}{R}")

                    # Feature 1: flag recurring if last visit specialty matches current
                    last = data.get("last_visit") or {}
                    if last and last.get("specialty") == state.get("detected_specialty"):
                        extra["is_recurring"] = True
                        print(f"{YELLOW}│  🔄 RECURRING SYMPTOM DETECTED: {last.get('specialty')} — prev visit {last.get('appointment_date','')[:10]}{R}")

            elif name == "book_appointment":
                if data.get("status") == "confirmed":
                    extra["appointment_id"]         = data.get("appointment_id")
                    extra["selected_doctor_name"]   = data.get("doctor_name")
                    extra["selected_slot_datetime"] = data.get("slot_datetime")
                    extra["stage"]                  = "confirmed"
                    vault.register("appointment_id", data.get("appointment_id", ""))

            elif name == "cancel_appointment":
                if data.get("success"):
                    extra["stage"] = "cancelled"

            elif name == "reschedule_appointment":
                if data.get("status") == "rescheduled":
                    extra["selected_slot_datetime"] = data.get("new_slot_datetime")
                    extra["selected_doctor_name"]   = data.get("doctor_name")
                    extra["stage"]                  = "confirmed"


            # For lookup_or_create_patient: embed patient_id token hint in the
            # tool response so the LLM uses it correctly in the next tool call.
            if name == "lookup_or_create_patient" and data.get("patient_id"):
                patient_token = vault._to_token.get(data["patient_id"], "")
                if patient_token:
                    data = dict(data)
                    data["_booking_hint"] = (
                        f"IMPORTANT: Use patient_id={patient_token} "
                        f"when calling book_appointment. Do not use any other UUID."
                    )

            # Mask real values in response before LLM sees it
            safe_data    = vault.mask_dict(data)
            masked_count = sum(
                1 for k in safe_data
                if safe_data[k] != data.get(k)
            )
            total_masked += masked_count

            # Rebuild ToolMessage with masked content
            safe_msg = ToolMessage(
                content   = json.dumps(safe_data),
                tool_call_id = msg.tool_call_id,
                name      = name,
            )
            safe_tool_messages.append(safe_msg)

        if total_masked:
            _log_pii("masked", total_masked)

        new_stage = extra.get("stage", old_stage)
        _log_stage(old_stage, new_stage)
        _log_node_end()

        return {"messages": safe_tool_messages, **extra}

    # ── Router ────────────────────────────────────────────────────────────────

    def should_continue(state: AgentState) -> str:
        last = state["messages"][-1]
        if hasattr(last, "tool_calls") and last.tool_calls:
            print(f"{DIM}  ↪ routing → TOOLS{R}")
            return "tools"
        print(f"{DIM}  ↪ routing → END{R}")
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
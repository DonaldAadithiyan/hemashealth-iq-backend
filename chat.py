#!/usr/bin/env python3
"""
chat.py — HemasHealth IQ interactive terminal chat.
Run: python chat.py
"""

import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

if not os.getenv("OPENAI_API_KEY"):
    print("\n❌  OPENAI_API_KEY not found in .env file.\n")
    exit(1)

from app.agents.patient_agent import run_agent
from app.models.schemas import ChatMessage, BookingState

# ── Colours ───────────────────────────────────────────────────────────────────
R       = "\033[0m"
BOLD    = "\033[1m"
DIM     = "\033[2m"
CYAN    = "\033[96m"
GREEN   = "\033[92m"
YELLOW  = "\033[93m"
RED     = "\033[91m"
BLUE    = "\033[94m"
MAGENTA = "\033[95m"
WHITE   = "\033[97m"

STAGE_COLOURS = {
    "intake":     CYAN,
    "routing":    BLUE,
    "emergency":  RED,
    "slots_shown":YELLOW,
    "collecting": MAGENTA,
    "confirmed":  GREEN,
    "cancelled":  RED,
}

STAGE_LABELS = {
    "intake":     "💬 Intake",
    "routing":    "🔍 Routing",
    "emergency":  "🚨 Emergency",
    "slots_shown":"📅 Slots Shown",
    "collecting": "👤 Patient Lookup",
    "confirmed":  "✅ Confirmed",
    "cancelled":  "🚫 Cancelled",
}


def banner():
    print(f"\n{BOLD}{CYAN}{'═'*60}{R}")
    print(f"{BOLD}{CYAN}   🏥  HemasHealth IQ — Terminal Chat{R}")
    print(f"{BOLD}{CYAN}{'═'*60}{R}")
    print(f"{DIM}  Commands anytime:{R}")
    print(f"{DIM}  • {WHITE}state{DIM}  → show current booking state{R}")
    print(f"{DIM}  • {WHITE}reset{DIM}  → start a new conversation{R}")
    print(f"{DIM}  • {WHITE}quit{DIM}   → exit{R}")
    print(f"{BOLD}{CYAN}{'─'*60}{R}\n")


def print_agent_reply(text: str, stage: str):
    c = STAGE_COLOURS.get(stage, CYAN)
    label = STAGE_LABELS.get(stage, stage)
    print(f"\n{c}{BOLD}HemasHealth IQ  {DIM}[{label}]{R}")
    print(f"{c}{'─'*50}{R}")
    for line in text.split("\n"):
        print(f"  {line}")
    print(f"{c}{'─'*50}{R}\n")


def print_state(state: BookingState):
    print(f"\n{BOLD}{YELLOW}{'─'*50}{R}")
    print(f"{BOLD}{YELLOW}  📊 Current Booking State{R}")
    print(f"{BOLD}{YELLOW}{'─'*50}{R}")
    data = state.model_dump()
    for k, v in data.items():
        if v is None or v is False:
            print(f"  {DIM}{k}: {v}{R}")
        elif k == "stage":
            c = STAGE_COLOURS.get(str(v), CYAN)
            label = STAGE_LABELS.get(str(v), str(v))
            print(f"  {BOLD}{k}: {c}{label}{R}")
        elif k == "is_emergency" and v:
            print(f"  {BOLD}{k}: {RED}⚠️  TRUE{R}")
        else:
            print(f"  {BOLD}{k}: {GREEN}{v}{R}")
    print(f"{BOLD}{YELLOW}{'─'*50}{R}\n")


def print_stage_change(old: str, new: str):
    if old == new:
        return
    old_label = STAGE_LABELS.get(old, old)
    new_label = STAGE_LABELS.get(new, new)
    old_c = STAGE_COLOURS.get(old, CYAN)
    new_c = STAGE_COLOURS.get(new, CYAN)
    print(f"\n  {DIM}Stage: {old_c}{old_label}{R}{DIM} ──▶ {new_c}{BOLD}{new_label}{R}")

    if new == "emergency":
        print(f"\n  {RED}{BOLD}{'!'*50}{R}")
        print(f"  {RED}{BOLD}  🚨 EMERGENCY DETECTED — Show 1990 hotline UI{R}")
        print(f"  {RED}{BOLD}{'!'*50}{R}\n")
    elif new == "confirmed":
        print(f"\n  {GREEN}{BOLD}{'─'*50}{R}")
        print(f"  {GREEN}{BOLD}  ✅ BOOKING CONFIRMED — Trigger payment UI{R}")
        print(f"  {GREEN}{BOLD}{'─'*50}{R}\n")
    elif new == "cancelled":
        print(f"\n  {YELLOW}{BOLD}  🚫 APPOINTMENT CANCELLED{R}\n")


def print_separator():
    print(f"{DIM}{'·'*60}{R}")


async def main():
    banner()

    history: list[ChatMessage] = []
    booking_state = BookingState()

    # Opening greeting
    print(f"{DIM}  Connecting to HemasHealth IQ...{R}")
    result = await run_agent(
        new_message="Hello",
        history=[],
        patient_id=booking_state.patient_id,
        preferred_location=booking_state.preferred_location,
        current_stage=booking_state.stage,
    )
    booking_state = BookingState(**result["state"])
    print_agent_reply(result["reply"], booking_state.stage)
    history.append(ChatMessage(role="user",      content="Hello"))
    history.append(ChatMessage(role="assistant", content=result["reply"]))

    while True:
        print_separator()
        try:
            user_input = input(f"{BOLD}{WHITE}You: {R}").strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n{DIM}  Goodbye. Stay healthy! 👋{R}\n")
            break

        if not user_input:
            continue

        cmd = user_input.lower()

        if cmd in ("quit", "exit"):
            print(f"\n{DIM}  Goodbye. Stay healthy! 👋{R}\n")
            break

        if cmd == "state":
            print_state(booking_state)
            continue

        if cmd == "reset":
            history = []
            booking_state = BookingState()
            print(f"\n{YELLOW}{BOLD}  ↺  Conversation reset — starting fresh{R}\n")
            result = await run_agent(new_message="Hello", history=[], current_stage="intake")
            booking_state = BookingState(**result["state"])
            print_agent_reply(result["reply"], booking_state.stage)
            history.append(ChatMessage(role="user",      content="Hello"))
            history.append(ChatMessage(role="assistant", content=result["reply"]))
            continue

        # ── Send to agent ─────────────────────────────────────────────────────
        print(f"\n{DIM}{'─'*60}{R}")
        print(f"{DIM}  ⚡ Sending to agent...{R}")
        print(f"{DIM}{'─'*60}{R}")

        try:
            result = await run_agent(
                new_message=user_input,
                history=history,
                patient_id=booking_state.patient_id,
                preferred_location=booking_state.preferred_location,
                current_stage=booking_state.stage,
                detected_specialty=booking_state.detected_specialty,
                selected_slot_id=booking_state.selected_slot_id,
                selected_slot_datetime=booking_state.selected_slot_datetime,
                selected_doctor_id=booking_state.selected_doctor_id,
                selected_doctor_name=booking_state.selected_doctor_name,
                appointment_id=booking_state.appointment_id,
                is_emergency=booking_state.is_emergency,
            )
        except Exception as e:
            print(f"\n{RED}{BOLD}  ❌ Error: {e}{R}\n")
            continue

        new_state   = BookingState(**result["state"])
        reply       = result["reply"]
        old_stage   = booking_state.stage

        # Update history
        history.append(ChatMessage(role="user",      content=user_input))
        history.append(ChatMessage(role="assistant", content=reply))

        # Show stage change
        print_stage_change(old_stage, new_state.stage)

        # Show reply
        print_agent_reply(reply, new_state.stage)

        booking_state = new_state


if __name__ == "__main__":
    asyncio.run(main())
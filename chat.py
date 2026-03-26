#!/usr/bin/env python3
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

if not os.getenv("OPENAI_API_KEY"):
    print("\n❌  OPENAI_API_KEY not found.")
    print("    Add OPENAI_API_KEY=sk-... to your .env file\n")
    exit(1)

from app.agents.patient_agent import run_agent
from app.models.schemas import ChatMessage, BookingState

RESET  = "\033[0m"
BOLD   = "\033[1m"
CYAN   = "\033[96m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
DIM    = "\033[2m"

def print_agent(text):
    print(f"\n{CYAN}{BOLD}HemasHealth IQ:{RESET}")
    for line in text.split("\n"):
        print(f"  {line}")
    print()

def print_state(state):
    print(f"\n{DIM}── Booking State ──────────────────{RESET}")
    for k, v in state.model_dump().items():
        print(f"{DIM}  {k}: {YELLOW}{v}{RESET}")
    print(f"{DIM}────────────────────────────────────{RESET}\n")

def print_banner():
    print(f"\n{BOLD}{CYAN}╔══════════════════════════════════════════╗{RESET}")
    print(f"{BOLD}{CYAN}║       HemasHealth IQ — Terminal Chat     ║{RESET}")
    print(f"{BOLD}{CYAN}╚══════════════════════════════════════════╝{RESET}")
    print(f"{DIM}  'quit' to exit | 'reset' to restart | 'state' to inspect{RESET}\n")

async def main():
    print_banner()

    history = []
    booking_state = BookingState()

    result = await run_agent(
        new_message="Hello",
        history=[],
        patient_id=booking_state.patient_id,
        preferred_location=booking_state.preferred_location,
        current_stage=booking_state.stage,
    )
    print_agent(result["reply"])
    history.append(ChatMessage(role="user", content="Hello"))
    history.append(ChatMessage(role="assistant", content=result["reply"]))
    booking_state = BookingState(**result["state"])

    while True:
        try:
            user_input = input(f"{BOLD}You:{RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n{DIM}Goodbye.{RESET}\n")
            break

        if not user_input:
            continue

        if user_input.lower() in ("quit", "exit"):
            print(f"\n{DIM}Goodbye.{RESET}\n")
            break

        if user_input.lower() == "reset":
            history = []
            booking_state = BookingState()
            print(f"\n{YELLOW}── Conversation reset ──{RESET}\n")
            result = await run_agent(new_message="Hello", history=[], current_stage="intake")
            print_agent(result["reply"])
            history.append(ChatMessage(role="user", content="Hello"))
            history.append(ChatMessage(role="assistant", content=result["reply"]))
            booking_state = BookingState(**result["state"])
            continue

        if user_input.lower() == "state":
            print_state(booking_state)
            continue

        print(f"{DIM}  (thinking...){RESET}", end="\r")

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
            print(f"\n{RED}Error: {e}{RESET}\n")
            continue

        new_state = BookingState(**result["state"])
        reply = result["reply"]

        history.append(ChatMessage(role="user", content=user_input))
        history.append(ChatMessage(role="assistant", content=reply))

        print_agent(reply)

        if new_state.stage != booking_state.stage:
            if new_state.stage == "emergency":
                print(f"  {RED}⚠️  EMERGENCY STAGE{RESET}\n")
            elif new_state.stage == "confirmed":
                print(f"  {GREEN}✅  CONFIRMED — Appointment ID: {new_state.appointment_id}{RESET}\n")
            elif new_state.stage == "cancelled":
                print(f"  {YELLOW}🚫  CANCELLED{RESET}\n")

        booking_state = new_state

if __name__ == "__main__":
    asyncio.run(main())
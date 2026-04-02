"""
rewind.py — Navigation rewind tool.

Called by the agent when the patient wants to go back to a previous step.
The graph handles the actual state restoration from the navigation stack.
"""
from langchain_core.tools import tool


@tool
def rewind_booking(target: str) -> dict:
    """
    Rewind the booking flow to a previous step.
    Call this when the patient expresses intent to go back or change something.

    Args:
        target: Which step to go back to:
            "specialty" — go back to choosing location (re-show location picker)
            "location"  — go back to choosing a different location
            "slot"      — go back to viewing the slot list (same location)
            "doctor"    — same as "slot" — see different doctors/times
            "start"     — full reset, start from scratch

    Returns:
        rewound:    bool — True if rewind was successful
        target:     str  — the target that was requested
        message:    str  — what to tell the patient
    """
    messages = {
        "specialty": "No problem! Let me find you a different location.",
        "location":  "Sure! Which hospital location would you prefer?",
        "slot":      "Of course! Here are the available slots again — please choose below.",
        "doctor":    "Sure! Let me show you the available slots again.",
        "start":     "No problem! Let's start fresh. What health concern can I help you with today?",
    }
    return {
        "rewound": True,
        "target":  target,
        "message": messages.get(target, "Let me take you back to the previous step."),
    }
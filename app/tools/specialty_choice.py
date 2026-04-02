"""
specialty_choice.py — Tool for the agent to signal a specialty choice to the frontend.

When the agent narrows down from gp_first to a likely specialist, it calls this tool
to store the choice options in state. The router then builds SHOW_SPECIALTY_CHOICE
with two buttons: specialist vs GP.
"""

from langchain_core.tools import tool


@tool
def signal_specialty_choice(
    suggested_specialty: str,
    reason: str,
) -> dict:
    """
    Signal to the frontend that the patient should choose between a specialist and GP.
    Call this when you've identified a likely specialist from follow-up questions.

    Args:
        suggested_specialty: The specialist you are recommending e.g. "Neurology"
        reason:              One sentence explaining why e.g. "Your symptoms suggest a migraine."

    Returns:
        choice_pending: bool — always True (confirms signal was received)
        specialist:     str  — the suggested specialty
        reason:         str  — the reason
    """
    return {
        "choice_pending":  True,
        "specialist":      suggested_specialty,
        "reason":          reason,
    }
"""
summarizer.py — Conversation summarizer for HemasHealth IQ.

Uses gpt-4o-mini to compress old conversation turns into a single summary.
This keeps the context window small without losing important information.

How it works:
  - Triggered when history grows beyond SUMMARIZE_AFTER_TURNS turns
  - Keeps the last KEEP_VERBATIM_TURNS turns as raw messages
  - Everything older gets compressed into one summary string
  - Summary is stored in BookingState.conversation_summary
  - On subsequent turns, existing summary + new old turns get re-summarized together
  - The graph receives: [system prompt] + [summary message] + [last N verbatim] + [new message]

Cost: gpt-4o-mini is ~50x cheaper than gpt-4o. A summary call costs less than $0.001.
"""

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langchain_openai import ChatOpenAI
from app.config import get_settings

# ── Config ────────────────────────────────────────────────────────────────────

SUMMARIZE_AFTER_TURNS = 6   # summarize when conversation exceeds this many turns
KEEP_VERBATIM_TURNS   = 4   # always keep this many recent turns as raw messages

# ── Summarizer prompt ─────────────────────────────────────────────────────────

SUMMARIZER_PROMPT = """You are summarizing a conversation between a patient and HemasHealth IQ, 
a hospital booking assistant for Hemas Hospitals in Sri Lanka.

Extract and preserve ALL of the following if mentioned:
- Patient's name and phone number
- Symptoms or reason for visit described
- Specialist they were routed to
- Hospital location chosen (Wattala or Thalawathugoda)
- Doctor(s) shown and any slot times discussed
- Any slot_id values mentioned (copy them exactly)
- Whether the patient was identified as new or returning
- Any appointment ID mentioned
- Any decisions or confirmations made

Write a concise factual summary in 3-5 sentences.
Do not include greetings or pleasantries.
Do not invent or infer anything not explicitly stated.
"""

# ─────────────────────────────────────────────────────────────────────────────

def _messages_to_text(messages: list[BaseMessage]) -> str:
    """Convert a list of LangChain messages to a readable transcript."""
    lines = []
    for msg in messages:
        if isinstance(msg, HumanMessage):
            lines.append(f"Patient: {msg.content}")
        elif isinstance(msg, AIMessage):
            # Skip tool call messages (no visible content)
            if msg.content:
                lines.append(f"Agent: {msg.content}")
        # ToolMessages are skipped — they're internal plumbing, not conversation
    return "\n".join(lines)


async def summarize_messages(messages: list[BaseMessage], existing_summary: str | None = None) -> str:
    """
    Call gpt-4o-mini to summarize a list of messages.
    If there's an existing summary, prepend it so context accumulates correctly.
    """
    settings = get_settings()

    llm = ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0,
        api_key=settings.openai_api_key,
    )

    transcript = _messages_to_text(messages)

    if existing_summary:
        user_content = (
            f"Previous summary:\n{existing_summary}\n\n"
            f"New conversation to add:\n{transcript}\n\n"
            f"Write an updated summary combining both."
        )
    else:
        user_content = f"Conversation to summarize:\n{transcript}"

    response = await llm.ainvoke([
        SystemMessage(content=SUMMARIZER_PROMPT),
        HumanMessage(content=user_content),
    ])

    return response.content.strip()


def should_summarize(history_message_count: int) -> bool:
    """
    Returns True if we should trigger summarization this turn.
    history_message_count = total messages in history (each turn = 2 messages: user + assistant)
    """
    total_turns = history_message_count // 2
    return total_turns > SUMMARIZE_AFTER_TURNS


def split_history(messages: list[BaseMessage]) -> tuple[list[BaseMessage], list[BaseMessage]]:
    """
    Split messages into:
      - to_summarize: everything except the last KEEP_VERBATIM_TURNS turns
      - to_keep:      the last KEEP_VERBATIM_TURNS turns verbatim

    Each turn = 2 messages (HumanMessage + AIMessage).
    Tool messages are counted as part of the turn they belong to.
    """
    # Find turn boundaries by counting HumanMessages
    turn_indices = [i for i, m in enumerate(messages) if isinstance(m, HumanMessage)]

    if len(turn_indices) <= KEEP_VERBATIM_TURNS:
        # Not enough turns to split — keep everything verbatim
        return [], messages

    # The split point: keep last KEEP_VERBATIM_TURNS human turns and everything after
    split_turn_index = turn_indices[-KEEP_VERBATIM_TURNS]
    to_summarize = messages[:split_turn_index]
    to_keep      = messages[split_turn_index:]

    return to_summarize, to_keep
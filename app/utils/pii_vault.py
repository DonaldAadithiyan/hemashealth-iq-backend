"""
pii_vault.py — PII token substitution vault for HemasHealth IQ.

Implements the deterministic token-substitution pattern from Joel Sathiyendra's
FHIR + AI privacy approach:
  Real values  →  tokens  (before LLM sees anything)
  Tokens       →  real values  (at tool-call time, never in LLM prompts)

One vault per session. Stored server-side in memory.
The LLM only ever sees tokens like :::patient_id::: — never real UUIDs,
phone numbers, or names.

TOKEN FORMAT:  :::key_N:::
  e.g.  :::patient_id_1:::   :::phone_1:::   :::appointment_id_1:::

HOW IT WORKS:
  1. Before building LLM context, call vault.mask(text) on any string
     containing real values — or vault.register(label, real_value) to
     get a token for a known field.
  2. The LLM reasons with tokens only.
  3. When the LLM emits a tool call with tokens in args, call
     vault.unmask_dict(args) to swap tokens back to real values.
  4. Tool responses contain real values — call vault.mask_dict(response)
     before feeding back to LLM so history stays clean.
"""

import re
import threading
from typing import Any


class PIIVault:
    """
    Thread-safe per-session PII token vault.

    Usage:
        vault = PIIVault(session_id="abc-123")

        # Register a known value → get a token
        token = vault.register("patient_id", "real-uuid-here")
        # token = ":::patient_id_1:::"

        # Unmask tokens in a dict (for tool call args)
        real_args = vault.unmask_dict({"patient_id": ":::patient_id_1:::"})
        # → {"patient_id": "real-uuid-here"}

        # Mask real values in a dict (for tool responses)
        safe_response = vault.mask_dict({"patient_id": "real-uuid-here", "name": "Aadithiyan"})
        # → {"patient_id": ":::patient_id_1:::", "name": ":::patient_name_1:::"}

        # Mask real values in free text
        safe_text = vault.mask_text("Patient real-uuid-here has been booked")
        # → "Patient :::patient_id_1::: has been booked"
    """

    # Fields we always mask — maps field name → token label prefix
    SENSITIVE_FIELDS = {
        # Exact key matches in dicts
        "patient_id":       "patient_id",
        "user_id":          "user_id",
        "doctor_id":        "doctor_id",
        "appointment_id":   "appointment_id",
        "slot_id":          "slot_id",
        "phone":            "phone",
        "name":             "patient_name",
        "email":            "email",
        "reason_for_visit": "reason",
        "symptoms_summary": "reason",
    }

    def __init__(self, session_id: str):
        self.session_id  = session_id
        self._lock       = threading.Lock()
        self._to_token:  dict[str, str] = {}   # real_value  → token
        self._to_real:   dict[str, str] = {}   # token       → real_value
        self._counters:  dict[str, int] = {}   # label       → counter

    # ── Core registration ──────────────────────────────────────────────────

    def register(self, label: str, real_value: str) -> str:
        """
        Register a real value and return its token.
        If already registered, returns the existing token.
        Idempotent — same value always gets same token.
        """
        if not real_value or not isinstance(real_value, str):
            return real_value

        with self._lock:
            if real_value in self._to_token:
                return self._to_token[real_value]

            count = self._counters.get(label, 0) + 1
            self._counters[label] = count
            token = f":::{label}_{count}:::"

            self._to_token[real_value] = token
            self._to_real[token]       = real_value
            return token

    def resolve(self, token: str) -> str:
        """Resolve a token back to its real value. Returns token unchanged if not found."""
        return self._to_real.get(token, token)

    # ── Dict operations ────────────────────────────────────────────────────

    def mask_dict(self, data: dict) -> dict:
        """
        Replace real values in a dict with tokens for sensitive fields.
        Used before feeding tool responses back to the LLM.
        """
        result = {}
        for key, value in data.items():
            if value is None:
                result[key] = value
                continue
            label = self.SENSITIVE_FIELDS.get(key)
            if label and isinstance(value, str) and value:
                result[key] = self.register(label, value)
            elif isinstance(value, dict):
                result[key] = self.mask_dict(value)
            elif isinstance(value, list):
                result[key] = [
                    self.mask_dict(v) if isinstance(v, dict) else v
                    for v in value
                ]
            else:
                result[key] = value
        return result

    def unmask_dict(self, data: dict) -> dict:
        """
        Swap tokens back to real values in a dict.
        Used on tool call args before hitting the database.
        """
        result = {}
        for key, value in data.items():
            if isinstance(value, str):
                result[key] = self.resolve(value)
            elif isinstance(value, dict):
                result[key] = self.unmask_dict(value)
            elif isinstance(value, list):
                result[key] = [
                    self.unmask_dict(v) if isinstance(v, dict)
                    else self.resolve(v) if isinstance(v, str)
                    else v
                    for v in value
                ]
            else:
                result[key] = value
        return result

    def mask_text(self, text: str) -> str:
        """
        Replace all known real values in a free-text string with their tokens.
        Used to sanitise AI replies before storing in history.
        """
        if not text:
            return text
        with self._lock:
            # Sort by length descending so longer values are replaced first
            # (avoids partial replacements)
            for real_value, token in sorted(
                self._to_token.items(), key=lambda x: len(x[0]), reverse=True
            ):
                if real_value in text:
                    text = text.replace(real_value, token)
        return text

    def unmask_text(self, text: str) -> str:
        """
        Replace tokens in text with real values.
        Used when sending a final response to the patient (they should see real info).
        """
        if not text:
            return text
        # Find all tokens in the text
        token_pattern = re.compile(r':::[\w_]+:::')
        def replace_token(match):
            token = match.group(0)
            return self._to_real.get(token, token)
        return token_pattern.sub(replace_token, text)

    def mask_booking_state(self, state_dict: dict) -> dict:
        """
        Mask all sensitive fields in a BookingState dict.
        Returns a safe version to inject into LLM context.
        """
        sensitive_state_keys = {
            "patient_id":             "patient_id",
            "appointment_id":         "appointment_id",
            "selected_doctor_id":     "doctor_id",
            "selected_slot_id":       "slot_id",
            "selected_doctor_name":   "patient_name",
            "selected_slot_datetime": "slot_datetime",
        }
        result = dict(state_dict)
        for key, label in sensitive_state_keys.items():
            val = result.get(key)
            if val and isinstance(val, str):
                result[key] = self.register(label, val)
        return result

    def debug_summary(self) -> dict:
        """Return a summary of registered mappings — for terminal debug display only."""
        with self._lock:
            return {
                "session_id":   self.session_id,
                "total_tokens": len(self._to_token),
                "tokens":       {token: f"{real[:8]}..." if len(real) > 8 else real
                                 for real, token in self._to_token.items()},
            }


# ── Session vault registry ────────────────────────────────────────────────────
# One vault per session_id, kept in memory for the server's lifetime.
# In production you'd back this with Redis with a TTL.

_registry_lock = threading.Lock()
_vaults: dict[str, PIIVault] = {}


def get_vault(session_id: str) -> PIIVault:
    """Get or create the PII vault for a session."""
    with _registry_lock:
        if session_id not in _vaults:
            _vaults[session_id] = PIIVault(session_id)
        return _vaults[session_id]


def clear_vault(session_id: str):
    """Clear vault when session ends (e.g. after booking confirmed)."""
    with _registry_lock:
        _vaults.pop(session_id, None)
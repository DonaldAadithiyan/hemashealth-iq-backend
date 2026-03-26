"""
Basic tests for the HemasHealth IQ backend.

Run with:  pytest tests/ -v

These tests use httpx's AsyncClient against the FastAPI app directly
(no live Supabase or OpenAI calls — mock those in CI).
"""

import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch, MagicMock
from app.main import app


# ── Helpers ───────────────────────────────────────────────────────────────────

@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


# ── Health ────────────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# ── Routing tool unit tests (no network) ──────────────────────────────────────

def test_route_to_specialist_cardiology():
    from app.tools.routing import route_to_specialist
    result = route_to_specialist.invoke({"symptoms": "I have chest pain and palpitations"})
    assert result["specialty"] == "Cardiology"
    assert result["is_emergency"] is False


def test_route_to_specialist_emergency():
    from app.tools.routing import route_to_specialist
    result = route_to_specialist.invoke({"symptoms": "I cannot breathe and feel dizzy"})
    assert result["is_emergency"] is True
    assert result["specialty"] is None


def test_route_to_specialist_general_fallback():
    from app.tools.routing import route_to_specialist
    result = route_to_specialist.invoke({"symptoms": "I feel a bit off generally"})
    assert result["specialty"] == "General Medicine"
    assert result["confidence"] == "low"


def test_route_to_specialist_neurology():
    from app.tools.routing import route_to_specialist
    result = route_to_specialist.invoke({"symptoms": "Severe migraine for 3 days"})
    assert result["specialty"] == "Neurology"


# ── Chat endpoint — mocked agent ──────────────────────────────────────────────

@pytest.mark.anyio
async def test_chat_returns_reply(client):
    mock_result = {
        "reply": "Hello! I'm HemasHealth IQ. What brings you in today?",
        "state": {
            "stage": "intake",
            "detected_specialty": None,
            "selected_doctor_name": None,
            "selected_slot_datetime": None,
            "patient_id": None,
            "appointment_id": None,
            "preferred_location": None,
            "is_emergency": False,
        },
    }

    with patch("app.routers.chat.run_agent", new=AsyncMock(return_value=mock_result)):
        resp = await client.post(
            "/chat",
            json={
                "session_id": "test-session-001",
                "message": "Hello",
                "history": [],
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == "test-session-001"
    assert "reply" in data
    assert data["state"]["stage"] == "intake"


@pytest.mark.anyio
async def test_chat_emergency_state(client):
    mock_result = {
        "reply": "This sounds like a medical emergency. Please call 1990 immediately.",
        "state": {
            "stage": "emergency",
            "detected_specialty": None,
            "selected_doctor_name": None,
            "selected_slot_datetime": None,
            "patient_id": None,
            "appointment_id": None,
            "preferred_location": None,
            "is_emergency": True,
        },
    }

    with patch("app.routers.chat.run_agent", new=AsyncMock(return_value=mock_result)):
        resp = await client.post(
            "/chat",
            json={
                "session_id": "test-session-002",
                "message": "I have severe chest pain and cannot breathe",
                "history": [],
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["state"]["is_emergency"] is True
    assert data["state"]["stage"] == "emergency"


@pytest.mark.anyio
async def test_chat_confirmed_state(client):
    mock_result = {
        "reply": "Your appointment with Dr. Perera is confirmed for tomorrow at 10:00 AM.",
        "state": {
            "stage": "confirmed",
            "detected_specialty": "Cardiology",
            "selected_doctor_name": "Dr. Perera",
            "selected_slot_datetime": "2026-03-27T10:00:00+05:30",
            "patient_id": "patient-uuid-123",
            "appointment_id": "appt-uuid-456",
            "preferred_location": "wattala",
            "is_emergency": False,
        },
    }

    with patch("app.routers.chat.run_agent", new=AsyncMock(return_value=mock_result)):
        resp = await client.post(
            "/chat",
            json={
                "session_id": "test-session-003",
                "message": "Yes, confirm that slot",
                "history": [
                    {"role": "user", "content": "I have chest pains"},
                    {"role": "assistant", "content": "I'll route you to Cardiology. Wattala or Thalawathugoda?"},
                    {"role": "user", "content": "Wattala please"},
                    {"role": "assistant", "content": "Dr. Perera has a slot tomorrow 10 AM. Shall I book it?"},
                ],
                "patient_id": "patient-uuid-123",
                "preferred_location": "wattala",
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["state"]["stage"] == "confirmed"
    assert data["state"]["appointment_id"] == "appt-uuid-456"
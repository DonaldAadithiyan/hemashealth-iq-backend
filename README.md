# HemasHealth IQ — AI Backend

FastAPI + LangGraph backend powering the HemasHealth IQ conversational patient engagement platform for Hemas Hospitals, Sri Lanka.

---

## What this backend does

This is the **AI brain only**. It handles:

- Conversational patient intake via a LangGraph agent (GPT-4o)
- Symptom analysis and specialist routing
- Real-time doctor availability checking
- Appointment booking, cancellation, and rescheduling
- Returning patient detection by phone number
- Emergency detection with immediate escalation
- Dashboard data endpoints for Admin, Doctor, and Patient views

What it does **not** do (handled by Next.js):
- Auth (Supabase Auth)
- Payment
- Notifications (coming later)
- All UI

---

## Project Structure

```
hemashealth-iq-backend/
│
├── chat.py                          ← Interactive terminal chat for local testing
│
├── app/
│   ├── main.py                      ← FastAPI app entry point + CORS
│   ├── config.py                    ← Environment settings (pydantic-settings)
│   │
│   ├── agents/
│   │   └── patient_agent.py         ← Runs one conversation turn through the graph
│   │
│   ├── graphs/
│   │   └── booking_graph.py         ← LangGraph state machine (the AI brain)
│   │
│   ├── tools/
│   │   ├── routing.py               ← Symptom → specialist routing + emergency detection
│   │   ├── availability.py          ← Check doctor slots by specialty + location
│   │   ├── patient.py               ← Lookup or register patient by phone
│   │   └── booking.py               ← Book / cancel appointments with slot locking
│   │
│   ├── routers/
│   │   ├── chat.py                  ← POST /chat (main AI endpoint)
│   │   └── appointments.py          ← GET/DELETE /appointments/* (dashboard endpoints)
│   │
│   ├── models/
│   │   └── schemas.py               ← All Pydantic models including UIAction enum
│   │
│   ├── db/
│   │   ├── mock_db.py               ← ✅ ACTIVE — in-memory data (15 doctors, slots, patients)
│   │   └── supabase.py              ← Ready to activate when real DB is set up
│   │
│   └── prompts/
│       └── system_prompt.py         ← Master LLM system prompt (8-step booking flow)
│
├── tests/
│   └── test_chat.py
│
├── supabase_schema.sql              ← Run in Supabase SQL editor when DB is ready
├── render.yaml                      ← One-click deploy to Render
├── requirements.txt
└── .env.example
```

---

## Setup

**1. Clone and enter the project**
```bash
cd hemashealth-iq-backend
```

**2. Create virtual environment**
```bash
python -m venv venv
source venv/bin/activate        # Mac/Linux
# venv\Scripts\activate         # Windows
```

**3. Install dependencies**
```bash
pip install -r requirements.txt
```

**4. Set up environment variables**
```bash
cp .env.example .env
```
Open `.env` and add your OpenAI API key. That is the only required field to run locally.
```
OPENAI_API_KEY=sk-...
```

---

## Running Locally

### Terminal chat (test the AI directly, no server needed)
```bash
python chat.py
```
Commands while chatting:
- `state` — print the current booking state
- `reset` — start a fresh conversation
- `quit` — exit

### API server
```bash
uvicorn app.main:app --reload
```
Open **http://localhost:8000/docs** for the interactive Swagger UI.

---

## API Endpoints

### `POST /chat`
Main patient-facing AI endpoint. Every patient message goes here.

**Request:**
```json
{
  "session_id": "uuid-generated-by-frontend",
  "message": "I have been having bad headaches",
  "history": [
    { "role": "user", "content": "Hello" },
    { "role": "assistant", "content": "Hello! How can I help you today?" }
  ],
  "booking_state": {
    "stage": "intake",
    "is_emergency": false,
    "detected_specialty": null,
    "preferred_location": null,
    "selected_slot_id": null,
    "selected_slot_datetime": null,
    "selected_doctor_id": null,
    "selected_doctor_name": null,
    "patient_id": null,
    "appointment_id": null
  }
}
```

**Response:**
```json
{
  "session_id": "uuid-generated-by-frontend",
  "reply": "Based on what you've described, I'll find you a Neurologist...",
  "ui_action": "SHOW_CHAT",
  "state": {
    "stage": "routing",
    "detected_specialty": "Neurology",
    "is_emergency": false,
    "preferred_location": null,
    "selected_slot_id": null,
    "selected_slot_datetime": null,
    "selected_doctor_id": null,
    "selected_doctor_name": null,
    "patient_id": null,
    "appointment_id": null
  }
}
```

### Dashboard Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/appointments/{id}` | Single appointment |
| GET | `/appointments/patient/{patient_id}` | All appointments for a patient |
| GET | `/appointments/doctor/{doctor_id}?date=YYYY-MM-DD` | Doctor's appointments for a day |
| GET | `/appointments/admin/all?location=wattala&status=confirmed` | All appointments (admin) |
| DELETE | `/appointments/{id}` | Cancel an appointment |

### `GET /health`
```json
{ "status": "ok", "service": "hemashealth-iq-backend" }
```

---

## How the Chat Works

### Context sent to LLM each turn

Every request sends the full conversation to GPT-4o:

```
SystemMessage  ← master system prompt (booking rules, clinical boundary)
HumanMessage   ← "Hello"
AIMessage      ← "Hello! How can I help?"
HumanMessage   ← "I have a tummy ache"
AIMessage      ← tool call to route_to_specialist
ToolMessage    ← { specialty: "Gastroenterology" }
AIMessage      ← "I'll find you a Gastroenterologist. Which location?"
HumanMessage   ← "Wattala"        ← new message this turn
```

The backend is **completely stateless**. The frontend must send full `history[]` and `booking_state` on every request.

### Conversation flow

```
Patient message
      ↓
POST /chat
      ↓
LangGraph agent (GPT-4o)
      ↓
  ┌── calls tools as needed ──────────────────────────────┐
  │  route_to_specialist   → symptom → specialty          │
  │  check_availability    → doctors + free slots         │
  │  lookup_or_create_patient → find or register patient  │
  │  book_appointment      → lock slot + create record    │
  │  cancel_appointment    → free slot + update record    │
  └───────────────────────────────────────────────────────┘
      ↓
reply + ui_action + state
      ↓
Next.js renders response
```

### Booking flow (8 steps)

1. Patient describes symptoms
2. Agent announces specialist
3. Agent asks which hospital (Wattala or Thalawathugoda)
4. Agent shows available doctor slots
5. Patient picks a slot
6. Agent checks if returning patient by phone number
7. Agent books the appointment
8. Confirmation message with appointment ID

---

## UIAction — How the Frontend Knows What to Render

Every `/chat` response includes a `ui_action` field. The frontend switches on this to decide what component to show alongside the chat bubble.

| `ui_action` | When | What to render |
|-------------|------|----------------|
| `SHOW_CHAT` | Normal conversation | Just the chat bubble |
| `SHOW_EMERGENCY` | Red-flag symptoms detected | Red banner + 1990 call button |
| `SHOW_SLOTS` | Doctor slots presented | Chat bubble + optional slot picker cards |
| `SHOW_PATIENT_FORM` | Collecting patient details | Chat bubble + name/phone input form |
| `SHOW_PAYMENT` | Appointment confirmed | Booking confirmation card + payment trigger |
| `SHOW_CANCELLED` | Appointment cancelled | Cancellation confirmation card |

`reply` is always displayed as the assistant chat bubble regardless of `ui_action`.

---

## Data Layer

Currently using **in-memory mock data** (`app/db/mock_db.py`):
- 15 doctors across both locations and all specialties
- Hourly slots 9am–4pm for the next 7 days for every doctor
- 2 seed patients (Kamal Jayawardena +94771234567, Nimali Perera +94779876543)

### Switching to Supabase (when DB is ready)

1. Run `supabase_schema.sql` in your Supabase SQL editor
2. Add `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` to `.env`
3. In each of the 4 tool files, change:
   ```python
   from app.db.mock_db import get_db      # remove this
   from app.db.supabase import get_supabase  # add this
   ```
   Then rewrite the `db.*` calls as Supabase queries. Return shapes are identical.

---

## Supabase Schema (for when DB is ready)

### `doctors`
| Column | Type |
|--------|------|
| id | uuid |
| name | text |
| specialty | text |
| location | text (`wattala` / `thalawathugoda`) |
| is_active | bool |

### `doctor_slots`
| Column | Type |
|--------|------|
| id | uuid |
| doctor_id | uuid FK |
| slot_datetime | timestamptz |
| is_booked | bool |

### `patients`
| Column | Type |
|--------|------|
| id | uuid |
| name | text |
| phone | text (unique) |
| email | text |
| created_at | timestamptz |

### `appointments`
| Column | Type |
|--------|------|
| id | uuid |
| patient_id | uuid FK |
| doctor_id | uuid FK |
| slot_id | uuid FK |
| status | text (`confirmed` / `cancelled` / `completed`) |
| symptoms_summary | text |
| created_at | timestamptz |

---

## Deployment (Render)

```bash
# render.yaml is already configured
# Just connect your repo to Render and set environment variables:
# OPENAI_API_KEY
# SUPABASE_URL
# SUPABASE_SERVICE_KEY
# ALLOWED_ORIGINS (your Vercel URL)
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| API Framework | FastAPI |
| AI Orchestration | LangGraph |
| LLM | GPT-4o (OpenAI) |
| Database (prod) | Supabase (PostgreSQL) |
| Database (dev) | In-memory mock |
| Hosting | Render |
| Frontend | Next.js (separate repo) |
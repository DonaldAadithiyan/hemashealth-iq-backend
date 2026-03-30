# HemasHealth IQ — AI Backend

FastAPI + LangGraph backend powering the HemasHealth IQ conversational patient engagement platform for Hemas Hospitals, Sri Lanka.

---

## What this backend does

This is the **AI brain only**. It handles:

- Conversational patient intake via a LangGraph agent (GPT-4o)
- Symptom and disease name → specialist routing (170+ keywords)
- Real-time doctor availability computed from `doctor_availability_rules`
- Automatic fallback to related specialties when a doctor isn't available
- Appointment booking, cancellation, and rescheduling
- Returning patient detection by phone number
- PII token substitution — real patient IDs/names never reach the LLM
- Conversation summarisation after 6 turns (gpt-4o-mini) to keep context lean
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
├── chat.py                              ← Interactive terminal chat for local testing
├── seed_data.sql                        ← Sample data — run in Supabase SQL editor
│
├── app/
│   ├── main.py                          ← FastAPI app entry point + CORS
│   ├── config.py                        ← Environment settings (pydantic-settings)
│   │
│   ├── agents/
│   │   └── patient_agent.py             ← Runs one turn: masks PII, invokes graph, unmasks reply
│   │
│   ├── graphs/
│   │   └── booking_graph.py             ← LangGraph state machine + PII vault interception
│   │
│   ├── tools/
│   │   ├── routing.py                   ← Symptom/disease → specialist + emergency detection
│   │   ├── availability.py              ← Doctor slots with 4-level fallback chain
│   │   ├── patient.py                   ← Lookup or register patient by phone
│   │   └── booking.py                   ← Book / cancel / reschedule appointments
│   │
│   ├── routers/
│   │   ├── chat.py                      ← POST /chat (main AI endpoint)
│   │   └── appointments.py              ← GET/PATCH/DELETE /appointments/* (dashboards)
│   │
│   ├── models/
│   │   └── schemas.py                   ← All Pydantic models + UIAction enum
│   │
│   ├── db/
│   │   ├── mock_db.py                   ← In-memory data for local dev (no Supabase needed)
│   │   └── supabase.py                  ← Real Supabase queries against your schema
│   │
│   ├── prompts/
│   │   └── system_prompt.py             ← Master LLM system prompt (8-step booking flow)
│   │
│   └── utils/
│       ├── pii_vault.py                 ← PII token substitution vault (per session)
│       └── summarizer.py               ← Conversation summariser (gpt-4o-mini)
│
├── tests/
│   └── test_all.py                      ← 80 tests, no OpenAI or Supabase needed
│
├── render.yaml                          ← One-click deploy to Render
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

Minimum required to run locally with mock data:
```
OPENAI_API_KEY=sk-...
```

Add these when connecting to Supabase:
```
SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_SERVICE_KEY=eyJ...   # service_role key from Supabase → Settings → API
```

---

## Running Locally

### Terminal chat (test the AI, no server needed)
```bash
python chat.py
```

**Terminal commands:**
| Command | What it does |
|---------|-------------|
| `state` | Show booking state + PII vault contents |
| `reset` | Start a fresh conversation (vault cleared) |
| `quit`  | Exit |

### API server
```bash
uvicorn app.main:app --reload
```
Open **http://localhost:8000/docs** for the Swagger UI.

### Run tests
```bash
python tests/test_all.py
```
80 tests, no OpenAI or Supabase needed. Runs in under 2 seconds.

---

## Seeding your Supabase DB

Run `seed_data.sql` in your Supabase SQL editor. It inserts:
- 15 doctors across both locations and all specialties
- Availability rules (Mon–Fri, 9am–5pm) for all doctors
- 3 sample patients for testing the returning patient flow

**Test phone numbers (returning patient flow):**
- `+94771234567` — Kamal Jayawardena
- `+94779876543` — Nimali Perera
- `+94761122334` — Suresh Silva

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
    { "role": "user",      "content": "Hello" },
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
    "appointment_id": null,
    "conversation_summary": null
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
    "appointment_id": null,
    "conversation_summary": null
  }
}
```

### Dashboard Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET    | `/appointments/{id}` | Single appointment |
| GET    | `/appointments/patient/{patient_id}` | Patient's appointments |
| GET    | `/appointments/doctor/{doctor_id}?date=YYYY-MM-DD` | Doctor's appointments for a day |
| GET    | `/appointments/admin/all?location=wattala&status=confirmed` | All appointments |
| PATCH  | `/appointments/{id}/reschedule` | Reschedule an appointment |
| DELETE | `/appointments/{id}` | Cancel an appointment |

### `GET /health`
```json
{ "status": "ok", "service": "hemashealth-iq-backend" }
```

---

## UIAction — What the Frontend Should Render

Every `/chat` response includes a `ui_action` field. Switch on this to decide which component to show alongside the chat bubble.

| `ui_action` | When it fires | What to render |
|-------------|--------------|----------------|
| `SHOW_CHAT` | Normal conversation | Just the chat bubble |
| `SHOW_EMERGENCY` | Red-flag symptoms detected | Red banner + 1990 call button |
| `SHOW_SLOTS` | Doctor slots presented | Chat bubble + optional slot picker cards |
| `SHOW_PATIENT_FORM` | Collecting patient details | Chat bubble + name/phone input form |
| `SHOW_PAYMENT` | Appointment confirmed | Booking confirmation card + payment trigger |
| `SHOW_CANCELLED` | Appointment cancelled | Cancellation confirmation card |
| `SHOW_RESCHEDULED` | Appointment rescheduled | Reschedule confirmation card |

`reply` is always displayed as the assistant chat bubble regardless of `ui_action`.

---

## How the Chat Works

### Context sent to LLM each turn

```
SystemMessage   ← master system prompt (booking rules, clinical guardrails)
SystemMessage   ← conversation summary (if > 6 turns, replaces old messages)
HumanMessage    ← "Hello"            ← recent history verbatim
AIMessage       ← "How can I help?"
HumanMessage    ← "I have migraines"
AIMessage       ← "I'll find a Neurologist..."
HumanMessage    ← "Wattala"          ← new message this turn (PII-masked)
```

The backend is **completely stateless**. Frontend sends full `history[]` and `booking_state` on every request.

### Booking flow (8 steps)

1. Patient describes symptoms or names a condition/disease
2. Agent calls `route_to_specialist` → announces specialty
3. Agent asks which hospital (Wattala or Thalawathugoda)
4. Agent calls `check_availability` → shows doctor slots (with fallback if needed)
5. Patient picks a slot
6. Agent checks if returning patient by phone number
7. Agent books the appointment
8. Confirmation message with appointment ID

### Specialist availability fallback (4 levels)

When a specialty is unavailable, `check_availability` automatically tries:

| Level | What is tried |
|-------|--------------|
| 1 | Exact match — requested specialty + requested location |
| 2 | Related specialty — same location |
| 3 | Same specialty — other location |
| 4 | Related specialty — other location |

The response includes `fallback_used` and `fallback_reason` so the agent can explain the recommendation to the patient warmly.

---

## PII Safety

Implements the deterministic token-substitution pattern:

```
Real value              → What the LLM sees
────────────────────────────────────────────
patient-uuid-abc-123    → :::patient_id_1:::
+94773609683            → :::phone_1:::
appt-uuid-xyz-456       → :::appointment_id_1:::
```

- One `PIIVault` per session, stored server-side
- Real values swapped to tokens before building LLM context
- Tokens swapped back to real values at tool-call time (in-memory only, never logged)
- Final reply unmasked before returning to patient
- History on the frontend only ever contains tokens
- Vault cleared when booking is confirmed

---

## Conversation Optimisation

History is compressed after 6 turns using `gpt-4o-mini`:

| History length | What the LLM receives |
|---------------|----------------------|
| ≤ 6 turns | Full history verbatim |
| 7+ turns | Summary of old turns + last 4 turns verbatim |

Summary accumulates across turns and is stored in `booking_state.conversation_summary`. Frontend stores and sends it back as-is — it never needs to read or understand it.

---

## Data Layer

**Development (default):** `app/db/mock_db.py` — in-memory, no Supabase needed
- 15 doctors, 840 slots, 2 seed patients
- Only `OPENAI_API_KEY` required to run

**Production:** `app/db/supabase.py` — queries your real Supabase schema
- Availability computed from `doctor_availability_rules` + `doctor_availability_exceptions`
- No pre-generated slots table needed
- Slot IDs are synthetic: `"doctor-uuid::2026-03-27T10:00"`

### Switching to Supabase
Add to `.env`:
```
SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_SERVICE_KEY=eyJ...
```

The tools already point to `app/db/supabase.py`. No code changes needed — just add the credentials.

---

## Supabase Schema (your real tables)

| Table | Purpose |
|-------|---------|
| `users` | All users — doctors, patients, admins (phone/name/email live here) |
| `doctors` | Doctor profiles — specialization, location, consultation_fee |
| `doctor_availability_rules` | Recurring weekly schedules (days_of_week as smallint[]) |
| `doctor_availability_exceptions` | One-off unavailable dates |
| `patients` | Patient medical records (linked to users via user_id) |
| `appointments` | Bookings — appointment_date, status, reason_for_visit |
| `notifications` | Push/email notifications (not yet integrated) |

**Status values for `appointments.status`:**
`reserved` → `confirmed` → `paid` → `completed` / `cancelled` / `not_attended`

---

## Routing Coverage

The symptom router covers 170+ keywords across all specialties plus:
- Disease names: AIDS, HIV, tuberculosis, dengue, hepatitis, cancer, etc.
- Medical abbreviations: IBS, UTI, COPD, PCOS, OCD, PTSD
- Conditions: epilepsy, Parkinson's, arthritis, psoriasis, PCOS, glaucoma, lupus
- Natural language: "my child has a fever" → Pediatrics, "I have depression" → General Medicine
- Emergency detection: cannot breathe, heart attack, choking, overdose, anaphylactic shock

---

## Deployment (Render)

`render.yaml` is already configured. Connect your repo to Render and set:
```
OPENAI_API_KEY
SUPABASE_URL
SUPABASE_SERVICE_KEY
ALLOWED_ORIGINS   # your Vercel URL
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| API Framework | FastAPI |
| AI Orchestration | LangGraph |
| LLM (main) | GPT-4o (OpenAI) |
| LLM (summariser) | GPT-4o-mini |
| Database (prod) | Supabase (PostgreSQL) |
| Database (dev) | In-memory mock |
| PII Safety | Custom PIIVault (token substitution) |
| Hosting | Render |
| Frontend | Next.js (separate repo) |
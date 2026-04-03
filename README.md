# HemasHealth IQ — AI Backend

FastAPI + LangGraph backend powering the HemasHealth IQ conversational patient engagement platform for Hemas Hospitals, Sri Lanka.

---

## What this backend does

This is the **AI brain only**. The Next.js frontend handles all UI, auth, and payment gateway integration.

**The backend handles:**
- Conversational patient intake via a LangGraph agent (GPT-4o)
- Three-tier symptom routing: direct specialist / GP-first / clarify
- Smart follow-up questions before routing vague symptoms
- Specialist vs GP choice buttons when specialty is identified
- Real-time doctor availability computed from `doctor_availability_rules`
- 4-level fallback chain when a specialty/location has no availability
- Appointment booking, cancellation, and rescheduling
- Returning patient detection + symptom progression tracking
- Drug interaction warning when patient mentions current medications
- Payment confirmation — agent updates Supabase status to `paid` via chat
- Navigation rewind — patient can go back to any previous step conversationally
- PII token substitution — real patient data never reaches the LLM
- Conversation summarisation after 6 turns (gpt-4o-mini)

---

## Project Structure

```
hemashealth-iq-backend/
│
├── chat.py                              ← Interactive terminal chat for local testing
├── seed_data.sql                        ← Sample data — run in Supabase SQL editor
├── render.yaml                          ← One-click deploy to Render
├── requirements.txt
├── .env.example
│
├── app/
│   ├── main.py                          ← FastAPI entry point + CORS
│   ├── config.py                        ← Environment settings (pydantic-settings)
│   │
│   ├── agents/
│   │   └── patient_agent.py             ← Runs one turn: masks PII → graph → unmasks reply
│   │
│   ├── graphs/
│   │   └── booking_graph.py             ← LangGraph state machine + PII vault + navigation stack
│   │
│   ├── tools/
│   │   ├── routing.py                   ← 3-tier symptom router (direct / gp_first / clarify)
│   │   ├── availability.py              ← Doctor slots with 4-level fallback chain
│   │   ├── patient.py                   ← Lookup or register patient + last visit fetch
│   │   ├── booking.py                   ← Book / cancel / reschedule appointments
│   │   ├── specialty_choice.py          ← Signal specialist vs GP choice to frontend
│   │   ├── payment.py                   ← Confirm payment and update appointment to 'paid'
│   │   ├── rewind.py                    ← Navigate back to previous booking steps
│   │   └── intake.py                    ← Pre-appointment notes (available, not active)
│   │
│   ├── routers/
│   │   ├── chat.py                      ← POST /chat (main AI endpoint)
│   │   └── appointments.py              ← GET/PATCH/DELETE /appointments/* (dashboards)
│   │
│   ├── models/
│   │   └── schemas.py                   ← All Pydantic models + UIAction enum + payloads
│   │
│   ├── db/
│   │   ├── mock_db.py                   ← In-memory dev (no Supabase needed)
│   │   └── supabase.py                  ← Real Supabase queries
│   │
│   ├── prompts/
│   │   └── system_prompt.py             ← Master LLM system prompt (9-step booking flow)
│   │
│   └── utils/
│       ├── pii_vault.py                 ← PII token substitution vault (per session)
│       ├── summarizer.py               ← Conversation summariser (gpt-4o-mini)
│       └── classifier.py               ← ML symptom classifier utility (unused, available)
│
└── tests/
    └── test_all.py                      ← Tests, no OpenAI or Supabase needed
```

---

## Setup & Running Locally

### Mac

```bash
cd hemashealth-iq-backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # add OPENAI_API_KEY at minimum
uvicorn app.main:app --reload  # → http://127.0.0.1:8000
python chat.py                 # terminal chat
```

### Windows

```cmd
cd hemashealth-iq-backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload
python chat.py
```

### Run tests
```bash
python tests/test_all.py
```

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | ✅ Always | Your OpenAI API key |
| `SUPABASE_URL` | Production | Your Supabase project URL |
| `SUPABASE_SERVICE_KEY` | Production | Service role key (starts with `eyJ`) |
| `ALLOWED_ORIGINS` | Production | Comma-separated frontend URLs for CORS |
| `APP_ENV` | Optional | `development` or `production` |

Local dev only needs `OPENAI_API_KEY` — uses in-memory mock data by default.

---

## Supabase DB Setup

### Run seed data
Open **Supabase → SQL Editor** and run `seed_data.sql`. Inserts 15 doctors, availability rules, and 3 test patients.

### Required schema additions
Run these once in Supabase SQL Editor:

```sql
-- Add payment reference column
ALTER TABLE public.appointments
ADD COLUMN IF NOT EXISTS payment_ref text;

-- Ensure all status values are in the CHECK constraint
ALTER TABLE public.appointments
DROP CONSTRAINT IF EXISTS appointments_status_check;

ALTER TABLE public.appointments
ADD CONSTRAINT appointments_status_check
CHECK (status IN (
  'reserved', 'confirmed', 'paid',
  'cancelled', 'not_attended', 'completed'
));
```

### Test phone numbers
| Phone | Name |
|-------|------|
| `+94771234567` or `0771234567` | Kamal Jayawardena |
| `+94779876543` or `0779876543` | Nimali Perera |
| `+94761122334` or `0761122334` | Suresh Silva |

---

## Terminal Chat Commands

| Command | What it does |
|---------|-------------|
| `state` | Show booking state + PII vault |
| `debug` | Test Supabase connection directly |
| `reset` | Start fresh conversation |
| `quit`  | Exit |

---

## API Reference

### `POST /chat`
Main AI endpoint. Every patient message goes here.

**Request:**
```json
{
  "session_id":    "uuid — generate once per conversation",
  "message":       "patient's message",
  "user_phone":    "+94773609683",
  "history":       [{ "role": "user", "content": "..." }, ...],
  "booking_state": { ... }
}
```

**Response:**
```json
{
  "session_id": "...",
  "reply":      "assistant's reply — always show as chat bubble",
  "ui_action":  "SHOW_SLOTS",
  "ui_payload": { ... },
  "state":      { ... }
}
```

**`user_phone`** — send on every request from Supabase Auth. When present, the backend shows phone choice buttons (SHOW_PHONE_CHOICE) instead of asking the patient to type their number.

### ui_action Reference

| `ui_action` | When | `ui_payload` shape |
|-------------|------|--------------------|
| `SHOW_CHAT` | Normal conversation | null |
| `SHOW_EMERGENCY` | Red-flag symptom | `{ hotline, message, allow_booking_after }` |
| `SHOW_LOCATION_PICKER` | After specialty confirmed | `{ buttons: [{ value, label, address }] }` |
| `SHOW_SPECIALTY_CHOICE` | Agent narrows to specialist | `{ buttons, suggested_specialty, reason }` |
| `SHOW_SLOTS` | Doctor slots available | `{ doctors: [{ doctor_name, slots: [{ slot_id, label }] }], fallback_used, fallback_reason }` |
| `SHOW_PATIENT_FORM` | Phone lookup result | `{ is_returning, patient_name, last_visit, is_recurring }` |
| `SHOW_PHONE_CHOICE` | Logged-in user at phone step | `{ logged_in_phone, logged_in_label, other_label }` |
| `SHOW_PAYMENT` | Appointment confirmed | `{ appointment_id, doctor_name, datetime_label, location, specialty, mentions_medication, is_recurring }` |
| `SHOW_PAID` | Payment confirmed via chat | `{ appointment_id, doctor_name, datetime_label, location, specialty }` |
| `SHOW_CANCELLED` | Appointment cancelled | `{ appointment_id }` |
| `SHOW_RESCHEDULED` | Appointment rescheduled | `{ appointment_id, doctor_name, new_datetime_label, location }` |

**Key rule:** `ui_action` is driven by what the agent said, not just the stage. Always switch on `ui_action`.

### Dashboard Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET    | `/appointments/{id}` | Single appointment |
| GET    | `/appointments/patient/{patient_id}?status=confirmed` | Patient's appointments |
| GET    | `/appointments/doctor/{doctor_id}?date=YYYY-MM-DD` | Doctor's schedule |
| GET    | `/appointments/admin/all?location=wattala&status=confirmed` | All appointments |
| PATCH  | `/appointments/{id}/reschedule` | Reschedule |
| DELETE | `/appointments/{id}` | Cancel |
| GET    | `/health` | Health check |

---

## Booking Flow (9 steps)

1. Patient describes symptoms → `route_to_specialist` called
2. **Three-tier routing:**
   - `direct` → named condition or explicit specialist request → go straight to step 3
   - `clarify` → too vague → agent asks ONE follow-up question
   - `gp_first` → symptoms present but undiagnosed → agent asks 1-2 follow-up questions, then may offer `SHOW_SPECIALTY_CHOICE`
3. Agent asks location → `SHOW_LOCATION_PICKER` (two hospital buttons)
4. `check_availability` → `SHOW_SLOTS` (slot cards with labels)
5. Patient taps slot → agent asks for phone
6. **Phone step:** if `user_phone` in request → `SHOW_PHONE_CHOICE`; otherwise agent asks freely
7. `lookup_or_create_patient` → `SHOW_PATIENT_FORM` (returning/new patient card)
8. `book_appointment` → `SHOW_PAYMENT` (booking confirmation + payment buttons)
9. Patient pays → sends "payment successful" to `/chat` → `confirm_payment` → `SHOW_PAID` (receipt)

---

## Payment Flow

The payment gateway is handled entirely by the frontend. The backend only needs a chat message.

```
Patient taps "Pay Now"
  → frontend triggers Stripe / PayHere
  → payment gateway success
  → frontend sends message "payment successful" to POST /chat
  → backend agent calls confirm_payment tool
  → Supabase appointments.status updated to "paid"
  → response: ui_action = "SHOW_PAID" with receipt data
```

**"Pay at Hospital":** no chat message needed. Appointment stays `reserved` until front desk marks it.

---

## Navigation Rewind

Patient can say anything like "go back", "I want a different slot", "change the location", "start over" at any point before booking is confirmed. The agent calls `rewind_booking` internally and the state is restored to the appropriate checkpoint. No special frontend handling needed — just handle whatever `ui_action` comes back.

---

## Key Features

### Three-tier routing
| Tier | Trigger | Behaviour |
|------|---------|-----------|
| `direct` | Named condition ("I have diabetes") or specialist request ("I need a cardiologist") | Routes straight to specialist |
| `gp_first` | Vague symptoms ("I have a headache") | Asks 1-2 follow-up questions, may offer specialist vs GP choice |
| `clarify` | Too vague ("I don't feel well") | Asks one clarifying question |

### Specialist fallback (4 levels)
1. Exact specialty + requested location
2. Related specialty + same location
3. Same specialty + other location
4. Related specialty + other location

### PII Safety
Real patient IDs, phone numbers, and names are replaced with tokens (`:::patient_id_1:::`) before the LLM sees anything. Tokens are unmasked back to real values only at tool-call time. The vault is cleared after booking is confirmed.

### Context Optimisation
After 6 conversation turns, older messages are compressed using `gpt-4o-mini`. The summary is stored in `booking_state.conversation_summary` — the frontend stores and returns it unchanged.

---

## Deployment (Render)

`render.yaml` is pre-configured.

1. Push to GitHub
2. Render → New Web Service → connect repo
3. Add env vars: `OPENAI_API_KEY`, `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `ALLOWED_ORIGINS`
4. Deploy → `https://hemashealth-iq-backend.onrender.com`

> **Free tier:** spins down after 15 min inactivity. Open `/health` before a demo.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| API | FastAPI |
| AI Orchestration | LangGraph |
| LLM (main) | GPT-4o |
| LLM (summariser) | GPT-4o-mini |
| Database (prod) | Supabase (PostgreSQL) |
| Database (dev) | In-memory mock |
| PII Safety | Custom PIIVault (token substitution) |
| Hosting | Render (Singapore) |
| Frontend | Next.js (separate repo) |
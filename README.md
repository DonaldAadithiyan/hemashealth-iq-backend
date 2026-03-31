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
- Returning patient detection by phone number + symptom progression tracking
- Drug interaction warning when patient mentions current medications
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
├── supabase_schema.sql                  ← Full DB schema reference
├── render.yaml                          ← One-click deploy to Render
├── requirements.txt
├── .env.example
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
│   │   ├── routing.py                   ← Symptom/disease → specialist + emergency + medication detection
│   │   ├── availability.py              ← Doctor slots with 4-level fallback chain
│   │   ├── patient.py                   ← Lookup or register patient by phone + last visit fetch
│   │   ├── booking.py                   ← Book / cancel / reschedule appointments
│   │   └── intake.py                    ← Pre-appointment intake note (unused, available for later)
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
│       ├── pii_vault.py                 ← PII token substitution vault (per session, in-memory)
│       └── summarizer.py               ← Conversation summariser (gpt-4o-mini)
│
└── tests/
    ├── test_all.py                      ← 80 tests, no OpenAI or Supabase needed
    └── test_chat.py                     ← Chat endpoint tests
```

---

## Setup & Running Locally

### Mac

**1. Clone and enter the project**
```bash
cd hemashealth-iq-backend
```

**2. Create virtual environment**
```bash
python3 -m venv venv
source venv/bin/activate
```

**3. Install dependencies**
```bash
pip install -r requirements.txt
```

**4. Set up environment variables**
```bash
cp .env.example .env
```
Open `.env` and fill in your values. Minimum required:
```
OPENAI_API_KEY=sk-...
```
Add these when connecting to Supabase:
```
SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_SERVICE_KEY=eyJ...
```

**5. Run the API server**
```bash
uvicorn app.main:app --reload
```
Server starts at **http://127.0.0.1:8000**
Open **http://127.0.0.1:8000/docs** for the Swagger UI.

**6. Run the terminal chat (optional)**
```bash
python chat.py
```

---

### Windows

**1. Open Command Prompt or PowerShell and navigate to the project**
```cmd
cd hemashealth-iq-backend
```

**2. Create virtual environment**
```cmd
python -m venv venv
venv\Scripts\activate
```

**3. Install dependencies**
```cmd
pip install -r requirements.txt
```

**4. Set up environment variables**

Copy the example file:
```cmd
copy .env.example .env
```
Open `.env` in Notepad or VS Code and fill in your values:
```
OPENAI_API_KEY=sk-...
SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_SERVICE_KEY=eyJ...
```

**5. Run the API server**
```cmd
uvicorn app.main:app --reload
```
Server starts at **http://127.0.0.1:8000**
Open **http://127.0.0.1:8000/docs** for the Swagger UI.

**6. Run the terminal chat (optional)**
```cmd
python chat.py
```

---

### Run Tests
```bash
# Mac/Linux
python tests/test_all.py

# Windows
python tests\test_all.py
```
80 tests, no OpenAI or Supabase needed. Runs in under 2 seconds.

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | ✅ Always | Your OpenAI API key |
| `SUPABASE_URL` | Production only | Your Supabase project URL |
| `SUPABASE_SERVICE_KEY` | Production only | Service role key (starts with `eyJ`) |
| `ALLOWED_ORIGINS` | Production only | Comma-separated frontend URLs for CORS |
| `APP_ENV` | Optional | `development` or `production` |

> **Local dev:** Only `OPENAI_API_KEY` is needed. The app uses in-memory mock data by default.

---

## Seeding your Supabase DB

Run `seed_data.sql` in your Supabase SQL editor (Dashboard → SQL Editor → paste and run).

It inserts:
- 15 doctors across both locations and all specialties
- Availability rules (Mon–Fri, 9am–5pm, Asia/Colombo) for all doctors
- 3 sample patients for testing the returning patient flow

**Test phone numbers (returning patient flow):**
| Phone | Name |
|-------|------|
| `+94771234567` or `0771234567` | Kamal Jayawardena |
| `+94779876543` or `0779876543` | Nimali Perera |
| `+94761122334` or `0761122334` | Suresh Silva |

---

## Terminal Chat Commands

| Command | What it does |
|---------|-------------|
| `state` | Show current booking state + PII vault contents |
| `debug` | Test Supabase connection directly (shows doctors + slots) |
| `reset` | Start a fresh conversation (vault cleared) |
| `quit`  | Exit |

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
    { "role": "assistant", "content": "Hello! How can I help?" }
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
    "mentions_medication": false,
    "is_recurring": false,
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
  "state": { "stage": "routing", "detected_specialty": "Neurology", ... }
}
```

### Dashboard Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET    | `/appointments/{id}` | Single appointment |
| GET    | `/appointments/patient/{patient_id}?status=confirmed` | Patient's appointments |
| GET    | `/appointments/doctor/{doctor_id}?date=YYYY-MM-DD` | Doctor's day schedule |
| GET    | `/appointments/admin/all?location=wattala&status=confirmed` | All appointments |
| PATCH  | `/appointments/{id}/reschedule` | Reschedule an appointment |
| DELETE | `/appointments/{id}` | Cancel an appointment |
| GET    | `/health` | Health check |

---

## UIAction Reference

| `ui_action` | When | What the frontend renders |
|-------------|------|--------------------------|
| `SHOW_CHAT` | Normal conversation | Just the chat bubble |
| `SHOW_EMERGENCY` | Red-flag symptoms | Red banner + 1990 call button |
| `SHOW_SLOTS` | Doctor slots presented | Chat bubble + optional slot cards |
| `SHOW_PATIENT_FORM` | Collecting patient details | Chat bubble + name/phone form |
| `SHOW_PAYMENT` | Appointment confirmed | Confirmation card + payment trigger |
| `SHOW_CANCELLED` | Appointment cancelled | Cancellation confirmation |
| `SHOW_RESCHEDULED` | Appointment rescheduled | Reschedule confirmation |

---

## How Sessions Work

- Each conversation has a `session_id` generated by the frontend (UUID)
- The backend is **fully stateless** — it stores nothing between requests
- The frontend must send `history[]` and `booking_state` on every request
- The PII vault is stored in **server memory** keyed by `session_id`
- If the server restarts (e.g. Render free tier spins down), the vault is cleared — patient may need to re-enter their phone number for an in-progress booking
- For production: back the vault with Redis to survive restarts

---

## How the Chat Works

### Booking flow (8 steps)
1. Patient describes symptoms or names a condition/disease
2. Agent calls `route_to_specialist` → announces specialty
3. Agent asks which hospital (Wattala or Thalawathugoda)
4. Agent calls `check_availability` → shows doctor slots
5. Patient picks a slot
6. Agent checks if returning patient by phone number
7. Agent books the appointment
8. Confirmation message with appointment ID

### New features
- **Symptom progression tracking** — if the returning patient's current specialty matches their last visit, the agent flags it as recurring (`is_recurring: true` in state)
- **Drug interaction warning** — if patient mentions current medications, `mentions_medication: true` is set and a reminder is added to the confirmation message
- **Specialist fallback** — if no doctor is available for the requested specialty/location, the agent tries related specialties and the other location automatically

### PII Safety
Real patient IDs, phone numbers, and names are replaced with tokens (`:::patient_id_1:::`) before reaching the LLM. Real values are only resolved at tool-call time in memory and never appear in logs or conversation history.

### Context Optimisation
After 6 conversation turns, older messages are summarised using `gpt-4o-mini` and stored in `booking_state.conversation_summary`. Last 4 turns always kept verbatim.

---

## Data Layer

| Mode | When | How to activate |
|------|------|----------------|
| Mock DB | Local dev | Default — just set `OPENAI_API_KEY` |
| Supabase | Production | Add `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` to `.env` |

---

## Deployment (Render)

`render.yaml` is already configured. Steps:

1. Push code to GitHub
2. Go to render.com → New Web Service → connect repo
3. Add environment variables in Render dashboard
4. Deploy — your URL will be `https://hemashealth-iq-backend.onrender.com`

> **Free tier note:** Render free tier spins down after 15 minutes of inactivity. First request after sleep takes ~30 seconds. Open `/health` before a demo to wake it up.

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
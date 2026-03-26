# HemasHealth IQ — Backend (AI Brain)

FastAPI + LangGraph backend powering the HemasHealth IQ conversational patient engagement platform.

## What this backend does

- Runs a LangGraph-orchestrated conversational AI agent for patient interaction
- Routes patients to the correct specialist based on symptom intake
- Checks real-time doctor availability from Supabase
- Books, reschedules, and cancels appointments
- Exposes clean REST endpoints consumed by the Next.js frontend

## What this backend does NOT do (handled by Next.js)
- Auth (Supabase Auth)
- Dashboard UI & data fetching
- Doctor / Admin profile management
- Notifications (coming later)

---

## Project Structure

```
hemashealth-iq-backend/
├── app/
│   ├── main.py               # FastAPI app entry point
│   ├── config.py             # Settings / env vars
│   ├── agents/
│   │   └── patient_agent.py  # LangGraph agent definition
│   ├── graphs/
│   │   └── booking_graph.py  # LangGraph state graph (nodes + edges)
│   ├── tools/
│   │   ├── availability.py   # Check doctor availability (Supabase)
│   │   ├── booking.py        # Create / cancel / reschedule appointments
│   │   ├── routing.py        # Symptom → specialist routing
│   │   └── patient.py        # Patient lookup / creation
│   ├── routers/
│   │   ├── chat.py           # POST /chat — main agent endpoint
│   │   └── appointments.py   # GET /appointments/:id — read appointments
│   ├── models/
│   │   └── schemas.py        # Pydantic request/response models
│   ├── db/
│   │   └── supabase.py       # Supabase client singleton
│   └── prompts/
│       └── system_prompt.py  # Master system prompt for the LLM
├── tests/
│   └── test_chat.py
├── .env.example
├── requirements.txt
└── README.md
```

---

## Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Fill in OPENAI_API_KEY, SUPABASE_URL, SUPABASE_SERVICE_KEY
```

## Run

```bash
uvicorn app.main:app --reload
```

## Key Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/chat` | Send a message to the patient agent, get a response + state |
| GET | `/appointments/{appointment_id}` | Fetch a single appointment |
| GET | `/appointments/patient/{patient_id}` | All appointments for a patient |
| DELETE | `/appointments/{appointment_id}` | Cancel an appointment |

---

## Supabase Schema (expected tables)

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
| doctor_id | uuid (FK) |
| slot_datetime | timestamptz |
| is_booked | bool |

### `patients`
| Column | Type |
|--------|------|
| id | uuid |
| name | text |
| phone | text |
| email | text |
| created_at | timestamptz |

### `appointments`
| Column | Type |
|--------|------|
| id | uuid |
| patient_id | uuid (FK) |
| doctor_id | uuid (FK) |
| slot_id | uuid (FK) |
| status | text (`confirmed` / `cancelled` / `completed`) |
| symptoms_summary | text |
| created_at | timestamptz |
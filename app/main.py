from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import get_settings
from app.routers import chat, appointments

settings = get_settings()

app = FastAPI(
    title="HemasHealth IQ — AI Backend",
    description=(
        "LangGraph-powered conversational AI backend for Hemas Hospitals. "
        "Handles patient symptom intake, specialist routing, doctor availability, "
        "and appointment booking. All UI is served by the Next.js frontend."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(chat.router)
app.include_router(appointments.router)


# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok", "service": "hemashealth-iq-backend"}
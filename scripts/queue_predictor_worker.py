#!/usr/bin/env python3
"""
Queue Predictor Worker
======================
Subscribes to INSERT / UPDATE events on `public.queue` via Supabase Realtime.
On every change, recalculates predicted_service_start_time and
recommended_arrival_time for all waiting patients of the affected doctor,
then upserts the results into `appointment_ml_features`.

Run:  python -m scripts.queue_predictor_worker        (from repo root)
      python scripts/queue_predictor_worker.py         (standalone)

Requires SUPABASE_URL and SUPABASE_SERVICE_KEY in .env (same file the
FastAPI backend already uses).
"""
from __future__ import annotations

import asyncio
import logging
import math
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Ensure repo root is importable when run as a script
_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from dotenv import load_dotenv

load_dotenv(_REPO / ".env")

from supabase import acreate_client, AClient
from realtime import RealtimeSubscribeStates

from app.ml.duration_predictor import predict_duration

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("queue_worker")

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_KEY"]
SAFETY_BUFFER_MINS = 10

_processing_lock = asyncio.Lock()
_sb: AClient | None = None


async def get_supabase() -> AClient:
    global _sb
    if _sb is None:
        _sb = await acreate_client(SUPABASE_URL, SUPABASE_KEY)
    return _sb


async def recalculate_queue(doctor_id: str) -> None:
    """Fetch the queue for one doctor, predict wait times, upsert results."""
    async with _processing_lock:
        sb = await get_supabase()
        now = datetime.now(timezone.utc)
        today = now.strftime("%Y-%m-%d")

        logger.info("[recalc] doctor=%s date=%s", doctor_id, today)

        # Fetch doctor specialty for duration heuristic
        doc_resp = await sb.table("doctors").select(
            "specialization"
        ).eq("id", doctor_id).limit(1).execute()
        specialty = None
        if doc_resp.data:
            specialty = doc_resp.data[0].get("specialization")

        # Fetch today's queue for this doctor, ordered by position
        q_resp = await sb.table("queue").select(
            "id, appointment_id, position, status, consultation_started_at"
        ).eq("doctor_id", doctor_id).eq(
            "queue_date", today
        ).order("position").execute()

        rows = q_resp.data or []
        if not rows:
            logger.info("[recalc] empty queue, nothing to do")
            return

        # Separate in-consultation vs waiting
        in_consult = [r for r in rows if r["status"] == "in-consultation"]
        waiting = [r for r in rows if r["status"] == "waiting"]

        if not waiting:
            logger.info("[recalc] no waiting patients")
            return

        est = predict_duration(specialty=specialty)
        mean_mins = est.mean_mins
        std_mins = est.std_mins

        # Remaining time of the in-consultation patient
        remaining_mins = 0.0
        if in_consult:
            started_str = in_consult[0].get("consultation_started_at")
            if started_str:
                started = datetime.fromisoformat(started_str)
                if started.tzinfo is None:
                    started = started.replace(tzinfo=timezone.utc)
                elapsed = (now - started).total_seconds() / 60.0
                remaining_mins = max(mean_mins - elapsed, 0.0)
            else:
                remaining_mins = mean_mins

        upserts: list[dict] = []

        for idx, patient in enumerate(waiting):
            patients_ahead = idx + (1 if in_consult else 0)
            cumulative_wait = remaining_mins + (idx * mean_mins)
            variance_ahead = (patients_ahead) * (std_mins ** 2)
            uncertainty_mins = math.sqrt(variance_ahead) if variance_ahead > 0 else 0.0

            predicted_start = now + timedelta(minutes=cumulative_wait)
            recommended_arrival = predicted_start - timedelta(
                minutes=uncertainty_mins + SAFETY_BUFFER_MINS
            )

            # Don't recommend arriving in the past
            if recommended_arrival < now:
                recommended_arrival = now

            upserts.append({
                "appointment_id": patient["appointment_id"],
                "visit_type": specialty or "General",
                "predicted_service_start_time": predicted_start.isoformat(),
                "recommended_arrival_time": recommended_arrival.isoformat(),
                "historical_avg_duration_mins": round(mean_mins, 2),
                "historical_std_dev_mins": round(std_mins, 2),
            })

        if upserts:
            resp = await sb.table("appointment_ml_features").upsert(
                upserts, on_conflict="appointment_id"
            ).execute()
            logger.info(
                "[recalc] upserted %d predictions for doctor %s",
                len(resp.data or []), doctor_id,
            )

        for u in upserts:
            logger.info(
                "  appt=%s start=%s arrive=%s (avg=%.0fmin std=%.0fmin)",
                u["appointment_id"][:8],
                u["predicted_service_start_time"][11:16],
                u["recommended_arrival_time"][11:16],
                u["historical_avg_duration_mins"],
                u["historical_std_dev_mins"],
            )


async def on_queue_change(payload: dict) -> None:
    """Called by Supabase Realtime on INSERT / UPDATE to `queue`."""
    record = payload.get("data", {}).get("record") or payload.get("record", {})
    doctor_id = record.get("doctor_id")
    event = payload.get("data", {}).get("type") or payload.get("event", "?")
    logger.info("[event] %s on queue — doctor=%s", event, doctor_id)

    if not doctor_id:
        logger.warning("[event] no doctor_id in payload, skipping")
        return

    try:
        await recalculate_queue(doctor_id)
    except Exception:
        logger.exception("[event] recalculate_queue failed for doctor %s", doctor_id)


async def main() -> None:
    logger.info("Starting queue predictor worker...")
    logger.info("SUPABASE_URL=%s", SUPABASE_URL[:40] + "...")

    sb = await get_supabase()

    await sb.realtime.connect()
    logger.info("Realtime connected")

    channel = sb.realtime.channel("queue-predictions")

    channel.on_postgres_changes(
        "*",
        schema="public",
        table="queue",
        callback=lambda payload: asyncio.ensure_future(on_queue_change(payload)),
    )

    def on_subscribe(status: RealtimeSubscribeStates, err):
        if status == RealtimeSubscribeStates.SUBSCRIBED:
            logger.info("Subscribed to queue changes")
        elif err:
            logger.error("Subscribe error: %s", err)

    await channel.subscribe(on_subscribe)

    logger.info("Listening for queue changes... (Ctrl+C to stop)")

    # Keep the event loop alive; the realtime client runs its own
    # _listen and _heartbeat tasks in the background.
    try:
        while True:
            await asyncio.sleep(60)
    except asyncio.CancelledError:
        pass
    finally:
        await sb.realtime.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Worker stopped.")

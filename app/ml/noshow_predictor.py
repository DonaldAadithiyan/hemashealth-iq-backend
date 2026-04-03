"""
No-show prediction service.

Loads the trained LightGBM model once at import time and exposes
`predict_no_show()` which is called right after an appointment row is inserted.
The result is written to `appointment_no_show_predictions`.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

_MODEL_PATH = Path(__file__).resolve().parent / "noshow_model.pkl"
_THRESHOLD = 0.5
_MODEL_VERSION = "lgbm_v1"


@lru_cache(maxsize=1)
def _load_artifact() -> dict:
    artifact = joblib.load(_MODEL_PATH)
    logger.info(
        "Loaded no-show model (%s) — features: %s",
        artifact["model_type"],
        artifact["feature_names"],
    )
    return artifact


def _compute_features(
    patient_age_years: float | None,
    sms_reminder_received: int,
    appointment_date: datetime,
    booking_time: datetime,
    feature_names: list[str],
) -> pd.DataFrame:
    """Build a single-row DataFrame with named columns matching training order."""
    age = patient_age_years if patient_age_years is not None else 30.0

    lead_days = max((appointment_date.date() - booking_time.date()).days, 0)
    scheduled_hour = booking_time.hour
    scheduled_dow = booking_time.weekday()     # Mon=0 … Sun=6
    appointment_dow = appointment_date.weekday()

    values = {
        "patient_age_years": [age],
        "sms_reminder_received": [sms_reminder_received],
        "booking_lead_days": [lead_days],
        "scheduled_time_hour": [scheduled_hour],
        "scheduled_weekday": [scheduled_dow],
        "appointment_weekday": [appointment_dow],
    }

    logger.info(
        "No-show feature values: age=%.1f sms=%d lead_days=%d "
        "sched_hour=%d sched_dow=%d appt_dow=%d",
        age, sms_reminder_received, lead_days,
        scheduled_hour, scheduled_dow, appointment_dow,
    )

    return pd.DataFrame(values, columns=feature_names)


def predict_no_show(
    appointment_id: str,
    patient_age_years: float | None,
    sms_reminder_received: int,
    appointment_date: datetime,
    booking_time: datetime | None = None,
) -> dict:
    """
    Run inference and persist the prediction.

    Returns dict with keys: no_show_probability, no_show_predicted, model_version
    """
    from app.db.supabase import get_supabase

    if booking_time is None:
        booking_time = datetime.now(timezone.utc)

    logger.info(
        "[noshow] predict called — appt=%s patient_age=%s sms=%d appt_date=%s booking=%s",
        appointment_id, patient_age_years, sms_reminder_received,
        appointment_date.isoformat(), booking_time.isoformat(),
    )

    art = _load_artifact()
    model = art["model"]
    feature_names = art["feature_names"]

    features = _compute_features(
        patient_age_years=patient_age_years,
        sms_reminder_received=sms_reminder_received,
        appointment_date=appointment_date,
        booking_time=booking_time,
        feature_names=feature_names,
    )

    proba = float(model.predict_proba(features)[0, 1])
    predicted = proba >= _THRESHOLD

    logger.info(
        "[noshow] result — appt=%s probability=%.6f predicted=%s",
        appointment_id, proba, predicted,
    )

    row = {
        "appointment_id": appointment_id,
        "no_show_probability": round(proba, 6),
        "no_show_predicted": predicted,
        "model_version": _MODEL_VERSION,
    }

    try:
        sb = get_supabase()
        resp = sb.table("appointment_no_show_predictions").upsert(row).execute()
        logger.info(
            "[noshow] DB upsert OK — appt=%s rows=%d",
            appointment_id, len(resp.data or []),
        )
    except Exception:
        logger.exception("[noshow] DB upsert FAILED for %s", appointment_id)

    return row

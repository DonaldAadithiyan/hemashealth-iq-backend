"""
Consultation duration predictor.

Phase 1 (now):  Heuristic defaults per specialty.
Phase 2 (later): Drop-in replacement with a trained regression model
                 once consultation_started_at / consultation_ended_at
                 data has accumulated (~200+ rows).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

_MODEL_PATH = Path(__file__).resolve().parent / "duration_model.pkl"

SPECIALTY_DEFAULTS: dict[str, tuple[float, float]] = {
    "Cardiology":       (20.0, 6.0),
    "Dermatology":      (12.0, 4.0),
    "ENT":              (10.0, 3.5),
    "General Practice": (15.0, 5.0),
    "Gynecology":       (18.0, 5.5),
    "Neurology":        (20.0, 6.0),
    "Ophthalmology":    (12.0, 4.0),
    "Orthopedics":      (15.0, 5.0),
    "Pediatrics":       (12.0, 4.0),
    "Psychiatry":       (25.0, 7.0),
}
_DEFAULT_MEAN = 15.0
_DEFAULT_STD = 5.0


@dataclass
class DurationEstimate:
    mean_mins: float
    std_mins: float


def predict_duration(
    specialty: str | None = None,
    **_kwargs,
) -> DurationEstimate:
    """
    Return expected consultation duration (mean) and uncertainty (std).

    When a trained model exists at _MODEL_PATH, this function will load it
    and use patient/doctor features for inference. Until then, it uses
    specialty-based heuristic defaults.
    """
    if _MODEL_PATH.exists():
        try:
            import joblib
            model = joblib.load(_MODEL_PATH)
            logger.info("Loaded duration model from %s", _MODEL_PATH)
            # Future: model.predict([[features...]]) → (mean, std)
            # For now fall through to heuristic
        except Exception:
            logger.warning("Failed to load duration model, using heuristic", exc_info=True)

    mean, std = SPECIALTY_DEFAULTS.get(specialty or "", (_DEFAULT_MEAN, _DEFAULT_STD))
    return DurationEstimate(mean_mins=mean, std_mins=std)

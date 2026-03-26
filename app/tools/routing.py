"""
Symptom → Specialist routing tool.

This is intentionally a lightweight rule-based + LLM-assisted router.
The routing table is the source of truth; the LLM is used only as a fallback
classifier when no keyword matches.
"""

from langchain_core.tools import tool

# ---------------------------------------------------------------------------
# Routing table — manually curated clinical routing logic
# Extend this as needed. Keys are lowercase symptom keywords.
# ---------------------------------------------------------------------------
ROUTING_TABLE: dict[str, str] = {
    # Cardiology
    "chest pain": "Cardiology",
    "palpitations": "Cardiology",
    "heart": "Cardiology",
    "shortness of breath": "Cardiology",
    "high blood pressure": "Cardiology",
    "hypertension": "Cardiology",

    # Gastroenterology
    "stomach": "Gastroenterology",
    "abdominal pain": "Gastroenterology",
    "nausea": "Gastroenterology",
    "vomiting": "Gastroenterology",
    "diarrhea": "Gastroenterology",
    "constipation": "Gastroenterology",
    "acid reflux": "Gastroenterology",
    "bloating": "Gastroenterology",

    # Neurology
    "headache": "Neurology",
    "migraine": "Neurology",
    "dizziness": "Neurology",
    "seizure": "Neurology",
    "numbness": "Neurology",
    "memory loss": "Neurology",
    "stroke": "Neurology",

    # Orthopedics
    "back pain": "Orthopedics",
    "joint pain": "Orthopedics",
    "knee pain": "Orthopedics",
    "fracture": "Orthopedics",
    "bone": "Orthopedics",
    "shoulder pain": "Orthopedics",
    "spine": "Orthopedics",

    # Dermatology
    "skin": "Dermatology",
    "rash": "Dermatology",
    "acne": "Dermatology",
    "eczema": "Dermatology",
    "itching": "Dermatology",
    "hair loss": "Dermatology",

    # ENT
    "ear": "ENT",
    "nose": "ENT",
    "throat": "ENT",
    "sore throat": "ENT",
    "hearing loss": "ENT",
    "sinusitis": "ENT",
    "tonsil": "ENT",

    # Ophthalmology
    "eye": "Ophthalmology",
    "vision": "Ophthalmology",
    "blurred vision": "Ophthalmology",
    "eye pain": "Ophthalmology",

    # Endocrinology
    "diabetes": "Endocrinology",
    "thyroid": "Endocrinology",
    "weight gain": "Endocrinology",
    "hormonal": "Endocrinology",

    # Urology
    "urinary": "Urology",
    "kidney": "Urology",
    "bladder": "Urology",
    "prostate": "Urology",

    # Gynecology / Obstetrics
    "pregnancy": "Obstetrics & Gynecology",
    "menstrual": "Obstetrics & Gynecology",
    "ovarian": "Obstetrics & Gynecology",
    "pelvic pain": "Obstetrics & Gynecology",
    "gynecology": "Obstetrics & Gynecology",

    # Pediatrics
    "child": "Pediatrics",
    "infant": "Pediatrics",
    "baby": "Pediatrics",
    "pediatric": "Pediatrics",

    # General / Internal Medicine (catch-all)
    "fever": "General Medicine",
    "flu": "General Medicine",
    "cold": "General Medicine",
    "fatigue": "General Medicine",
    "general checkup": "General Medicine",
    "checkup": "General Medicine",
}

# Emergency keywords — agent checks these BEFORE routing
EMERGENCY_KEYWORDS = [
    "can't breathe",
    "cannot breathe",
    "difficulty breathing",
    "unconscious",
    "heavy bleeding",
    "heart attack",
    "severe head injury",
    "loss of consciousness",
    "not breathing",
    "stroke symptoms",
]


def is_emergency(symptoms: str) -> bool:
    lower = symptoms.lower()
    return any(kw in lower for kw in EMERGENCY_KEYWORDS)


@tool
def route_to_specialist(symptoms: str) -> dict:
    """
    Given a free-text description of a patient's symptoms or reason for visit,
    returns the most appropriate medical specialty to route them to.

    Returns a dict with:
      - specialty: str  (e.g. "Cardiology")
      - is_emergency: bool
      - confidence: "high" | "low"
    """
    if is_emergency(symptoms):
        return {
            "specialty": None,
            "is_emergency": True,
            "confidence": "high",
        }

    lower = symptoms.lower()
    for keyword, specialty in ROUTING_TABLE.items():
        if keyword in lower:
            return {
                "specialty": specialty,
                "is_emergency": False,
                "confidence": "high",
            }

    # Fallback — return General Medicine with low confidence
    # The LLM agent can decide to ask the patient for more detail
    return {
        "specialty": "General Medicine",
        "is_emergency": False,
        "confidence": "low",
    }
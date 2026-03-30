"""
Symptom → Specialist routing tool.

Rule-based keyword router. The LLM is used as fallback only when no keyword matches.
Covers symptoms, disease names, conditions, and medical terms.
"""

from langchain_core.tools import tool

ROUTING_TABLE: dict[str, str] = {

    # ── Cardiology ─────────────────────────────────────────────────────────
    "chest pain":           "Cardiology",
    "palpitations":         "Cardiology",
    "heart":                "Cardiology",
    "shortness of breath":  "Cardiology",
    "high blood pressure":  "Cardiology",
    "hypertension":         "Cardiology",
    "arrhythmia":           "Cardiology",
    "atrial fibrillation":  "Cardiology",
    "angina":               "Cardiology",
    "heart failure":        "Cardiology",
    "coronary":             "Cardiology",
    "cardiac":              "Cardiology",
    "tachycardia":          "Cardiology",
    "bradycardia":          "Cardiology",
    "murmur":               "Cardiology",
    "cholesterol":          "Cardiology",

    # ── Gastroenterology ───────────────────────────────────────────────────
    "stomach":              "Gastroenterology",
    "abdominal pain":       "Gastroenterology",
    "nausea":               "Gastroenterology",
    "vomiting":             "Gastroenterology",
    "diarrhea":             "Gastroenterology",
    "constipation":         "Gastroenterology",
    "acid reflux":          "Gastroenterology",
    "bloating":             "Gastroenterology",
    "ibs":                  "Gastroenterology",
    "irritable bowel":      "Gastroenterology",
    "crohn":                "Gastroenterology",
    "colitis":              "Gastroenterology",
    "gastritis":            "Gastroenterology",
    "ulcer":                "Gastroenterology",
    "hepatitis":            "Gastroenterology",
    "liver":                "Gastroenterology",
    "gallstone":            "Gastroenterology",
    "jaundice":             "Gastroenterology",
    "indigestion":          "Gastroenterology",
    "bowel":                "Gastroenterology",
    "rectal":               "Gastroenterology",
    "hemorrhoid":           "Gastroenterology",
    "celiac":               "Gastroenterology",
    "pancreatitis":         "Gastroenterology",

    # ── Neurology ──────────────────────────────────────────────────────────
    "headache":             "Neurology",
    "migraine":             "Neurology",
    "dizziness":            "Neurology",
    "seizure":              "Neurology",
    "epilepsy":             "Neurology",
    "numbness":             "Neurology",
    "memory loss":          "Neurology",
    "stroke":               "Neurology",
    "tremor":               "Neurology",
    "parkinson":            "Neurology",
    "alzheimer":            "Neurology",
    "multiple sclerosis":   "Neurology",
    "ms ":                  "Neurology",
    "neuropathy":           "Neurology",
    "vertigo":              "Neurology",
    "concussion":           "Neurology",
    "brain":                "Neurology",
    "nerve":                "Neurology",
    "paralysis":            "Neurology",
    "facial droop":         "Neurology",

    # ── Orthopedics ────────────────────────────────────────────────────────
    "back pain":            "Orthopedics",
    "joint pain":           "Orthopedics",
    "knee pain":            "Orthopedics",
    "fracture":             "Orthopedics",
    "bone":                 "Orthopedics",
    "shoulder pain":        "Orthopedics",
    "spine":                "Orthopedics",
    "arthritis":            "Orthopedics",
    "osteoporosis":         "Orthopedics",
    "ligament":             "Orthopedics",
    "tendon":               "Orthopedics",
    "hip pain":             "Orthopedics",
    "neck pain":            "Orthopedics",
    "scoliosis":            "Orthopedics",
    "slipped disc":         "Orthopedics",
    "sports injury":        "Orthopedics",
    "muscle pain":          "Orthopedics",
    "rheumatoid":           "Orthopedics",
    "gout":                 "Orthopedics",
    "wrist pain":           "Orthopedics",

    # ── Dermatology ────────────────────────────────────────────────────────
    "skin":                 "Dermatology",
    "rash":                 "Dermatology",
    "acne":                 "Dermatology",
    "eczema":               "Dermatology",
    "itching":              "Dermatology",
    "hair loss":            "Dermatology",
    "psoriasis":            "Dermatology",
    "fungal infection":     "Dermatology",
    "ringworm":             "Dermatology",
    "hives":                "Dermatology",
    "urticaria":            "Dermatology",
    "mole":                 "Dermatology",
    "wart":                 "Dermatology",
    "dandruff":             "Dermatology",
    "vitiligo":             "Dermatology",
    "nail":                 "Dermatology",
    "wound":                "Dermatology",
    "burn":                 "Dermatology",
    "pigmentation":         "Dermatology",

    # ── ENT ────────────────────────────────────────────────────────────────
    "ear":                  "ENT",
    "nose":                 "ENT",
    "throat":               "ENT",
    "sore throat":          "ENT",
    "hearing loss":         "ENT",
    "sinusitis":            "ENT",
    "tonsil":               "ENT",
    "snoring":              "ENT",
    "sleep apnea":          "ENT",
    "nasal":                "ENT",
    "tinnitus":             "ENT",
    "laryngitis":           "ENT",
    "voice":                "ENT",
    "adenoid":              "ENT",
    "nosebleed":            "ENT",
    "swallowing":           "ENT",

    # ── Ophthalmology ──────────────────────────────────────────────────────
    "eye":                  "Ophthalmology",
    "vision":               "Ophthalmology",
    "blurred vision":       "Ophthalmology",
    "eye pain":             "Ophthalmology",
    "cataract":             "Ophthalmology",
    "glaucoma":             "Ophthalmology",
    "dry eye":              "Ophthalmology",
    "conjunctivitis":       "Ophthalmology",
    "pink eye":             "Ophthalmology",
    "retina":               "Ophthalmology",
    "short sighted":        "Ophthalmology",
    "long sighted":         "Ophthalmology",
    "colour blind":         "Ophthalmology",
    "double vision":        "Ophthalmology",

    # ── Endocrinology ──────────────────────────────────────────────────────
    "diabetes":             "Endocrinology",
    "thyroid":              "Endocrinology",
    "weight gain":          "Endocrinology",
    "hormonal":             "Endocrinology",
    "blood sugar":          "Endocrinology",
    "insulin":              "Endocrinology",
    "hyperthyroid":         "Endocrinology",
    "hypothyroid":          "Endocrinology",
    "goiter":               "Endocrinology",
    "adrenal":              "Endocrinology",
    "pituitary":            "Endocrinology",
    "obesity":              "Endocrinology",
    "metabolic":            "Endocrinology",
    "polycystic":           "Endocrinology",
    "pcos":                 "Endocrinology",
    "cushing":              "Endocrinology",

    # ── Urology ────────────────────────────────────────────────────────────
    "urinary":              "Urology",
    "kidney":               "Urology",
    "bladder":              "Urology",
    "prostate":             "Urology",
    "kidney stone":         "Urology",
    "uti":                  "Urology",
    "urinary infection":    "Urology",
    "incontinence":         "Urology",
    "erectile":             "Urology",
    "testicular":           "Urology",
    "renal":                "Urology",
    "blood in urine":       "Urology",
    "frequent urination":   "Urology",

    # ── Obstetrics & Gynecology ────────────────────────────────────────────
    "pregnancy":            "Obstetrics & Gynecology",
    "menstrual":            "Obstetrics & Gynecology",
    "ovarian":              "Obstetrics & Gynecology",
    "pelvic pain":          "Obstetrics & Gynecology",
    "gynecology":           "Obstetrics & Gynecology",
    "period":               "Obstetrics & Gynecology",
    "irregular period":     "Obstetrics & Gynecology",
    "vaginal":              "Obstetrics & Gynecology",
    "uterus":               "Obstetrics & Gynecology",
    "fibroid":              "Obstetrics & Gynecology",
    "endometriosis":        "Obstetrics & Gynecology",
    "menopause":            "Obstetrics & Gynecology",
    "fertility":            "Obstetrics & Gynecology",
    "antenatal":            "Obstetrics & Gynecology",
    "prenatal":             "Obstetrics & Gynecology",
    "cervical":             "Obstetrics & Gynecology",
    "breast lump":          "Obstetrics & Gynecology",
    "breast pain":          "Obstetrics & Gynecology",

    # ── Pediatrics ─────────────────────────────────────────────────────────
    "child":                "Pediatrics",
    "infant":               "Pediatrics",
    "baby":                 "Pediatrics",
    "pediatric":            "Pediatrics",
    "toddler":              "Pediatrics",
    "vaccination":          "Pediatrics",
    "growth":               "Pediatrics",
    "developmental":        "Pediatrics",
    "my son":               "Pediatrics",
    "my daughter":          "Pediatrics",
    "my kid":               "Pediatrics",
    "my child":             "Pediatrics",

    # ── Infectious Disease / General Medicine ──────────────────────────────
    "aids":                 "General Medicine",
    "hiv":                  "General Medicine",
    "tuberculosis":         "General Medicine",
    "tb ":                  "General Medicine",
    "malaria":              "General Medicine",
    "dengue":               "General Medicine",
    "typhoid":              "General Medicine",
    "covid":                "General Medicine",
    "coronavirus":          "General Medicine",
    "infection":            "General Medicine",
    "viral":                "General Medicine",
    "bacterial":            "General Medicine",
    "fever":                "General Medicine",
    "flu":                  "General Medicine",
    "cold":                 "General Medicine",
    "fatigue":              "General Medicine",
    "general checkup":      "General Medicine",
    "checkup":              "General Medicine",
    "weakness":             "General Medicine",
    "weight loss":          "General Medicine",
    "loss of appetite":     "General Medicine",
    "night sweats":         "General Medicine",
    "swollen glands":       "General Medicine",
    "lymph node":           "General Medicine",
    "anaemia":              "General Medicine",
    "anemia":               "General Medicine",
    "sickle cell":          "General Medicine",
    "leptospirosis":        "General Medicine",
    "chikungunya":          "General Medicine",

    # ── Psychiatry / Mental Health ─────────────────────────────────────────
    "depression":           "General Medicine",
    "anxiety":              "General Medicine",
    "stress":               "General Medicine",
    "mental health":        "General Medicine",
    "panic attack":         "General Medicine",
    "insomnia":             "General Medicine",
    "sleep":                "General Medicine",
    "bipolar":              "General Medicine",
    "schizophrenia":        "General Medicine",
    "ocd":                  "General Medicine",
    "ptsd":                 "General Medicine",

    # ── Pulmonology / Respiratory ──────────────────────────────────────────
    "asthma":               "General Medicine",
    "cough":                "General Medicine",
    "breathing":            "General Medicine",
    "lung":                 "General Medicine",
    "pneumonia":            "General Medicine",
    "bronchitis":           "General Medicine",
    "copd":                 "General Medicine",
    "wheezing":             "General Medicine",
    "chest tightness":      "General Medicine",
    "phlegm":               "General Medicine",
    "sputum":               "General Medicine",

    # ── Oncology / Cancer (route to General Medicine for referral) ─────────
    "cancer":               "General Medicine",
    "tumour":               "General Medicine",
    "tumor":                "General Medicine",
    "lump":                 "General Medicine",
    "chemotherapy":         "General Medicine",
    "radiation":            "General Medicine",
    "biopsy":               "General Medicine",
    "lymphoma":             "General Medicine",
    "leukemia":             "General Medicine",

    # ── Allergy & Immunology ───────────────────────────────────────────────
    "allergy":              "General Medicine",
    "allergic":             "General Medicine",
    "anaphylaxis":          "General Medicine",
    "autoimmune":           "General Medicine",
    "lupus":                "General Medicine",
}

# Emergency keywords — checked before any routing
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
    "choking",
    "overdose",
    "suicide",
    "poisoning",
    "severe allergic",
    "anaphylactic shock",
]


def is_emergency(symptoms: str) -> bool:
    lower = symptoms.lower()
    return any(kw in lower for kw in EMERGENCY_KEYWORDS)


@tool
def route_to_specialist(symptoms: str) -> dict:
    """
    Given a patient's description of symptoms, conditions, or reason for visit,
    returns the most appropriate medical specialty to route them to.

    Covers symptoms, disease names, medical conditions, and common terms.

    Returns:
        specialty:   str   — e.g. "Cardiology", "General Medicine"
        is_emergency: bool — True if red-flag symptoms detected
        confidence:  str   — "high" | "low"
    """
    if is_emergency(symptoms):
        return {"specialty": None, "is_emergency": True, "confidence": "high"}

    lower = symptoms.lower()
    for keyword, specialty in ROUTING_TABLE.items():
        if keyword in lower:
            return {"specialty": specialty, "is_emergency": False, "confidence": "high"}

    return {"specialty": "General Medicine", "is_emergency": False, "confidence": "low"}
"""
routing.py — Three-tier symptom → specialist routing tool.

Tier 1 — DIRECT specialist
  Patient names a known condition, a known disease, or explicitly requests
  a specialist. Route straight to that specialist.
  Examples: "I have diabetes", "I need a cardiologist", "I have epilepsy"

Tier 2 — GP FIRST
  Patient describes vague or acute symptoms without a known diagnosis.
  Route to General Medicine. GP decides on referral.
  Examples: "I have a headache", "stomach ache", "I feel tired"

Tier 3 — CLARIFY
  Too vague to route at all. Agent asks one targeted follow-up question.
  Examples: "I feel sick", "something is wrong", "I'm not well"
"""

from langchain_core.tools import tool

# ── Tier 1: DIRECT specialist ─────────────────────────────────────────────────
# Patient explicitly names a condition/disease, already has a diagnosis,
# or explicitly requests a specific specialist.

DIRECT_SPECIALIST: dict[str, str] = {

    # Explicit specialist requests
    "i need a cardiologist":     "Cardiology",
    "i want a cardiologist":     "Cardiology",
    "see a cardiologist":        "Cardiology",
    "i need a neurologist":      "Neurology",
    "i want a neurologist":      "Neurology",
    "see a neurologist":         "Neurology",
    "i need an orthopaedic":     "Orthopedics",
    "i need orthopedic":         "Orthopedics",
    "i need a gastro":           "Gastroenterology",
    "i need a dermatologist":    "Dermatology",
    "see a dermatologist":       "Dermatology",
    "i need an ent":             "ENT",
    "ent doctor":                "ENT",
    "ent specialist":            "ENT",
    "ent":                       "ENT",
    "book me an ent":            "ENT",
    "see an ent":                "ENT",
    "ear nose throat doctor":    "ENT",
    "ear nose throat specialist":"ENT",
    "i need an eye doctor":      "Ophthalmology",
    "i need an ophthalmologist": "Ophthalmology",
    "i need an endocrinologist": "Endocrinology",
    "i need a urologist":        "Urology",
    "i need a gynaecologist":    "Obstetrics & Gynecology",
    "i need a gynecologist":     "Obstetrics & Gynecology",
    "i need a paediatrician":    "Pediatrics",
    "i need a pediatrician":     "Pediatrics",
    "referred to":               "General Medicine",
    "my doctor referred":        "General Medicine",
    "gp referred":               "General Medicine",
    "referred by":               "General Medicine",
    "specialist referral":       "General Medicine",

    # Named cardiovascular conditions
    "hypertension":              "Cardiology",
    "high blood pressure":       "Cardiology",
    "atrial fibrillation":       "Cardiology",
    "heart failure":             "Cardiology",
    "coronary artery":           "Cardiology",
    "arrhythmia":                "Cardiology",
    "angina":                    "Cardiology",
    "tachycardia":               "Cardiology",
    "bradycardia":               "Cardiology",
    "heart murmur":              "Cardiology",
    "aortic":                    "Cardiology",
    "myocardial":                "Cardiology",

    # Named neurological conditions
    "epilepsy":                  "Neurology",
    "parkinson":                 "Neurology",
    "alzheimer":                 "Neurology",
    "multiple sclerosis":        "Neurology",
    "neuropathy":                "Neurology",
    "dementia":                  "Neurology",
    "migraine":                  "Neurology",
    "trigeminal neuralgia":      "Neurology",
    "bell's palsy":              "Neurology",
    "meningitis":                "Neurology",

    # Named GI conditions
    "crohn":                     "Gastroenterology",
    "colitis":                   "Gastroenterology",
    "ibs":                       "Gastroenterology",
    "irritable bowel":           "Gastroenterology",
    "celiac":                    "Gastroenterology",
    "hepatitis":                 "Gastroenterology",
    "cirrhosis":                 "Gastroenterology",
    "pancreatitis":              "Gastroenterology",
    "gastritis":                 "Gastroenterology",
    "peptic ulcer":              "Gastroenterology",
    "acid reflux":               "Gastroenterology",
    "gerd":                      "Gastroenterology",

    # Named orthopaedic conditions
    "arthritis":                 "Orthopedics",
    "osteoporosis":              "Orthopedics",
    "scoliosis":                 "Orthopedics",
    "osteoarthritis":            "Orthopedics",
    "rheumatoid":                "Orthopedics",
    "gout":                      "Orthopedics",
    "slipped disc":              "Orthopedics",
    "herniated disc":            "Orthopedics",
    "fracture":                  "Orthopedics",
    "torn ligament":             "Orthopedics",
    "rotator cuff":              "Orthopedics",

    # Named skin conditions
    "eczema":                    "Dermatology",
    "psoriasis":                 "Dermatology",
    "vitiligo":                  "Dermatology",
    "rosacea":                   "Dermatology",
    "melanoma":                  "Dermatology",
    "ringworm":                  "Dermatology",
    "urticaria":                 "Dermatology",
    "alopecia":                  "Dermatology",

    # Named ENT conditions
    "sinusitis":                 "ENT",
    "tonsillitis":               "ENT",
    "otitis":                    "ENT",
    "sleep apnea":               "ENT",
    "tinnitus":                  "ENT",
    "vertigo":                   "ENT",
    "meniere":                   "ENT",
    "deviated septum":           "ENT",

    # Named eye conditions
    "glaucoma":                  "Ophthalmology",
    "cataract":                  "Ophthalmology",
    "macular degeneration":      "Ophthalmology",
    "conjunctivitis":            "Ophthalmology",
    "retinal":                   "Ophthalmology",
    "diabetic retinopathy":      "Ophthalmology",
    "strabismus":                "Ophthalmology",

    # Named endocrine/metabolic conditions
    "diabetes":                  "Endocrinology",
    "hypothyroid":               "Endocrinology",
    "hyperthyroid":              "Endocrinology",
    "thyroid":                   "Endocrinology",
    "goiter":                    "Endocrinology",
    "pcos":                      "Endocrinology",
    "polycystic ovary":          "Endocrinology",
    "cushing":                   "Endocrinology",
    "addison":                   "Endocrinology",
    "hypoglycemia":              "Endocrinology",

    # Named urological conditions
    "kidney stone":              "Urology",
    "renal stone":               "Urology",
    "prostate":                  "Urology",
    "bladder cancer":            "Urology",
    "urinary tract infection":   "Urology",
    "uti":                       "Urology",
    "incontinence":              "Urology",
    "hydronephrosis":            "Urology",

    # Named OB/GYN conditions
    "endometriosis":             "Obstetrics & Gynecology",
    "fibroid":                   "Obstetrics & Gynecology",
    "ovarian cyst":              "Obstetrics & Gynecology",
    "pregnancy":                 "Obstetrics & Gynecology",
    "antenatal":                 "Obstetrics & Gynecology",
    "prenatal":                  "Obstetrics & Gynecology",
    "menopause":                 "Obstetrics & Gynecology",
    "cervical":                  "Obstetrics & Gynecology",

    # Named paediatric
    "my baby":                   "Pediatrics",
    "my infant":                 "Pediatrics",
    "my toddler":                "Pediatrics",
    "my child":                  "Pediatrics",
    "my son":                    "Pediatrics",
    "my daughter":               "Pediatrics",
    "my kid":                    "Pediatrics",
    "vaccination":               "Pediatrics",
    "immunisation":              "Pediatrics",

    # Named infectious diseases
    "hiv":                       "General Medicine",
    "aids":                      "General Medicine",
    "tuberculosis":              "General Medicine",
    "dengue":                    "General Medicine",
    "malaria":                   "General Medicine",
    "typhoid":                   "General Medicine",
    "leptospirosis":             "General Medicine",
    "chikungunya":               "General Medicine",
    "covid":                     "General Medicine",

    # Named mental health
    "bipolar":                   "General Medicine",
    "schizophrenia":             "General Medicine",
    "ocd":                       "General Medicine",
    "ptsd":                      "General Medicine",
    "eating disorder":           "General Medicine",
    "anorexia":                  "General Medicine",

    # Named respiratory
    "asthma":                    "General Medicine",
    "copd":                      "General Medicine",
    "pneumonia":                 "General Medicine",
    "bronchitis":                "General Medicine",
    "emphysema":                 "General Medicine",

    # Named cancer/oncology
    "cancer":                    "General Medicine",
    "tumour":                    "General Medicine",
    "tumor":                     "General Medicine",
    "lymphoma":                  "General Medicine",
    "leukemia":                  "General Medicine",
    "chemotherapy":              "General Medicine",

    # Named blood/haematology
    "anaemia":                   "General Medicine",
    "anemia":                    "General Medicine",
    "sickle cell":               "General Medicine",
    "thalassemia":               "General Medicine",

    # Named autoimmune
    "lupus":                     "General Medicine",
    "autoimmune":                "General Medicine",
}


# ── Tier 2: GP FIRST ──────────────────────────────────────────────────────────
# Vague or acute symptom — patient describes how they feel, not what they have.
# Send to General Medicine. GP decides if specialist referral is needed.
# suggested_specialty hints at which specialist the GP may refer to.

GP_FIRST: dict[str, str] = {

    # Cardiovascular symptoms
    "chest pain":                "Cardiology",
    "heart racing":              "Cardiology",
    "heart pounding":            "Cardiology",
    "palpitations":              "Cardiology",
    "shortness of breath":       "Cardiology",
    "out of breath":             "Cardiology",
    "cholesterol":               "Cardiology",

    # Neurological symptoms
    "headache":                  "Neurology",
    "head pain":                 "Neurology",
    "dizziness":                 "Neurology",
    "feeling dizzy":             "Neurology",
    "numbness":                  "Neurology",
    "tingling":                  "Neurology",
    "memory loss":               "Neurology",
    "forgetfulness":             "Neurology",
    "tremor":                    "Neurology",
    "shaking":                   "Neurology",
    "seizure":                   "Neurology",
    "fits":                      "Neurology",
    "fainting":                  "Neurology",
    "blackout":                  "Neurology",
    "confusion":                 "Neurology",
    "brain fog":                 "Neurology",
    "stroke":                    "Neurology",

    # GI symptoms
    "stomach ache":              "Gastroenterology",
    "stomach pain":              "Gastroenterology",
    "abdominal pain":            "Gastroenterology",
    "belly pain":                "Gastroenterology",
    "nausea":                    "Gastroenterology",
    "vomiting":                  "Gastroenterology",
    "diarrhea":                  "Gastroenterology",
    "constipation":              "Gastroenterology",
    "bloating":                  "Gastroenterology",
    "indigestion":               "Gastroenterology",
    "heartburn":                 "Gastroenterology",
    "blood in stool":            "Gastroenterology",
    "jaundice":                  "Gastroenterology",
    "yellow skin":               "Gastroenterology",
    "liver":                     "Gastroenterology",
    "stomach":                   "Gastroenterology",

    # Orthopaedic symptoms
    "back pain":                 "Orthopedics",
    "lower back":                "Orthopedics",
    "knee pain":                 "Orthopedics",
    "joint pain":                "Orthopedics",
    "shoulder pain":             "Orthopedics",
    "hip pain":                  "Orthopedics",
    "neck pain":                 "Orthopedics",
    "wrist pain":                "Orthopedics",
    "ankle pain":                "Orthopedics",
    "muscle pain":               "Orthopedics",
    "bone pain":                 "Orthopedics",
    "sports injury":             "Orthopedics",
    "swollen joint":             "Orthopedics",
    "stiff joints":              "Orthopedics",
    "spine":                     "Orthopedics",

    # Skin symptoms
    "rash":                      "Dermatology",
    "skin rash":                 "Dermatology",
    "itching":                   "Dermatology",
    "itchy skin":                "Dermatology",
    "acne":                      "Dermatology",
    "hair loss":                 "Dermatology",
    "dry skin":                  "Dermatology",
    "skin lesion":               "Dermatology",
    "mole":                      "Dermatology",
    "wart":                      "Dermatology",
    "nail problem":              "Dermatology",
    "dandruff":                  "Dermatology",
    "skin":                      "Dermatology",
    "fungal":                    "Dermatology",

    # ENT symptoms
    "sore throat":               "ENT",
    "ear pain":                  "ENT",
    "earache":                   "ENT",
    "hearing loss":              "ENT",
    "hard of hearing":           "ENT",
    "blocked nose":              "ENT",
    "runny nose":                "ENT",
    "nasal congestion":          "ENT",
    "nosebleed":                 "ENT",
    "snoring":                   "ENT",
    "hoarse voice":              "ENT",
    "loss of voice":             "ENT",
    "difficulty swallowing":     "ENT",
    "ear":                       "ENT",
    "nose":                      "ENT",
    "throat":                    "ENT",

    # Eye symptoms
    "eye pain":                  "Ophthalmology",
    "blurred vision":            "Ophthalmology",
    "double vision":             "Ophthalmology",
    "red eye":                   "Ophthalmology",
    "itchy eyes":                "Ophthalmology",
    "watery eyes":               "Ophthalmology",
    "vision problem":            "Ophthalmology",
    "eye":                       "Ophthalmology",

    # Endocrine symptoms
    "weight gain":               "Endocrinology",
    "weight loss":               "Endocrinology",
    "always thirsty":            "Endocrinology",
    "frequent urination":        "Endocrinology",
    "blood sugar":               "Endocrinology",
    "hair thinning":             "Endocrinology",
    "neck swelling":             "Endocrinology",

    # Urological symptoms
    "burning urination":         "Urology",
    "pain urinating":            "Urology",
    "blood in urine":            "Urology",
    "kidney pain":               "Urology",
    "difficulty urinating":      "Urology",
    "urinary":                   "Urology",
    "kidney":                    "Urology",
    "bladder":                   "Urology",

    # OB/GYN symptoms
    "irregular periods":         "Obstetrics & Gynecology",
    "missed period":             "Obstetrics & Gynecology",
    "pelvic pain":               "Obstetrics & Gynecology",
    "vaginal discharge":         "Obstetrics & Gynecology",
    "breast pain":               "Obstetrics & Gynecology",
    "breast lump":               "Obstetrics & Gynecology",
    "period pain":               "Obstetrics & Gynecology",
    "heavy periods":             "Obstetrics & Gynecology",

    # General / multi-system
    "fever":                     "General Medicine",
    "high fever":                "General Medicine",
    "flu":                       "General Medicine",
    "cold":                      "General Medicine",
    "cough":                     "General Medicine",
    "fatigue":                   "General Medicine",
    "tired":                     "General Medicine",
    "exhausted":                 "General Medicine",
    "weakness":                  "General Medicine",
    "loss of appetite":          "General Medicine",
    "night sweats":              "General Medicine",
    "swollen glands":            "General Medicine",
    "lymph node":                "General Medicine",
    "body ache":                 "General Medicine",
    "body pain":                 "General Medicine",
    "depression":                "General Medicine",
    "anxiety":                   "General Medicine",
    "stress":                    "General Medicine",
    "panic attack":              "General Medicine",
    "insomnia":                  "General Medicine",
    "sleep problem":             "General Medicine",
    "wheezing":                  "General Medicine",
    "breathing problem":         "General Medicine",
    "chest tightness":           "General Medicine",
    "phlegm":                    "General Medicine",
    "checkup":                   "General Medicine",
    "lump":                      "General Medicine",
    "swelling":                  "General Medicine",
    "infection":                 "General Medicine",
}

# ── Tier 3: CLARIFY triggers ──────────────────────────────────────────────────

CLARIFY_TRIGGERS = {
    "not well", "unwell", "sick", "ill", "feeling bad",
    "not feeling good", "not feeling well", "something is wrong",
    "feeling off", "not myself", "feel terrible", "feel awful",
    "i feel bad", "i feel sick", "feel sick", "under the weather",
    "i don't feel good", "i dont feel good",
}

# ── Emergency keywords ────────────────────────────────────────────────────────

EMERGENCY_KEYWORDS = [
    "can't breathe", "cannot breathe", "difficulty breathing",
    "unconscious", "heavy bleeding", "heart attack",
    "severe head injury", "loss of consciousness", "not breathing",
    "stroke symptoms", "choking", "overdose", "suicide",
    "poisoning", "severe allergic", "anaphylactic shock",
    "severe chest pain", "crushing chest",
]

# ── Medication keywords ───────────────────────────────────────────────────────

MEDICATION_KEYWORDS = [
    "taking", "on medication", "prescribed", "currently using",
    "i take", "i am on", "i'm on", "my medication", "my medicine",
    "my tablets", "my pills", "my drugs",
    "metformin", "insulin", "aspirin", "paracetamol", "ibuprofen",
    "amoxicillin", "warfarin", "lisinopril", "atorvastatin", "omeprazole",
    "blood thinner", "steroids", "antidepressant", "antibiotic",
    "blood pressure medication", "diabetes medication",
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _match_table(text: str, table: dict) -> str | None:
    for keyword, specialty in table.items():
        if keyword in text:
            return specialty
    return None

def _is_clarify(text: str) -> bool:
    if any(phrase in text for phrase in CLARIFY_TRIGGERS):
        return True
    words = text.split()
    if len(words) <= 3 and not _match_table(text, DIRECT_SPECIALIST) and not _match_table(text, GP_FIRST):
        return True
    return False


# ── Tool ──────────────────────────────────────────────────────────────────────

@tool
def route_to_specialist(symptoms: str) -> dict:
    """
    Routes a patient's message to the most appropriate medical specialty
    using a three-tier system that mirrors real clinical practice.

    Tier 1 DIRECT: patient has a known diagnosis or requests a specialist → direct booking
    Tier 2 GP_FIRST: patient describes symptoms without a diagnosis → General Medicine first
    Tier 3 CLARIFY: too vague → agent asks one follow-up question before routing

    Args:
        symptoms: Patient's full message describing their health concern

    Returns:
        specialty:           str | None  — specialty to book (None if clarify needed)
        routing_tier:        str         — "direct" | "gp_first" | "clarify" | "emergency"
        suggested_specialty: str | None  — for gp_first: specialist GP may refer to (show to patient)
        is_emergency:        bool
        mentions_medication: bool
        clarify_question:    str | None  — question to ask if routing_tier == "clarify"
    """
    text = symptoms.lower().strip()
    med  = any(kw in text for kw in MEDICATION_KEYWORDS)

    # Emergency — always first
    if any(kw in text for kw in EMERGENCY_KEYWORDS):
        return {
            "specialty":           None,
            "routing_tier":        "emergency",
            "suggested_specialty": None,
            "is_emergency":        True,
            "mentions_medication": med,
            "clarify_question":    None,
        }

    # Tier 1 — direct specialist
    direct = _match_table(text, DIRECT_SPECIALIST)
    if direct:
        return {
            "specialty":           direct,
            "routing_tier":        "direct",
            "suggested_specialty": None,
            "is_emergency":        False,
            "mentions_medication": med,
            "clarify_question":    None,
        }

    # Tier 2 — GP first
    gp_suggestion = _match_table(text, GP_FIRST)
    if gp_suggestion:
        return {
            "specialty":           "General Medicine",
            "routing_tier":        "gp_first",
            "suggested_specialty": gp_suggestion if gp_suggestion != "General Medicine" else None,
            "is_emergency":        False,
            "mentions_medication": med,
            "clarify_question":    None,
        }

    # Tier 3 — clarify
    if _is_clarify(text):
        return {
            "specialty":           None,
            "routing_tier":        "clarify",
            "suggested_specialty": None,
            "is_emergency":        False,
            "mentions_medication": med,
            "clarify_question":    (
                "Could you tell me a bit more about what you're experiencing — "
                "is it pain, fatigue, digestive issues, or something else?"
            ),
        }

    # Fallback
    return {
        "specialty":           "General Medicine",
        "routing_tier":        "gp_first",
        "suggested_specialty": None,
        "is_emergency":        False,
        "mentions_medication": med,
        "clarify_question":    None,
    }
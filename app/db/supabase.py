"""
supabase.py — Supabase client + all DB operations against the real schema.

All tools import from here when running against the real database.
The methods mirror what mock_db.py provides so the tools don't change their call signatures.
"""

from datetime import datetime, timedelta, timezone, date as dt_date
from functools import lru_cache
from supabase import create_client, Client
from app.config import get_settings


@lru_cache()
def get_supabase() -> Client:
    settings = get_settings()
    return create_client(settings.supabase_url, settings.supabase_service_key)


# ── Doctors ───────────────────────────────────────────────────────────────────

def get_doctors(
    specialty: str | None = None,
    location:  str | None = None,
    active_only: bool = True,
) -> list[dict]:
    """
    Fetch doctors filtered by specialization and/or location.
    Returns normalised dicts with keys: id, name, specialty, location, is_active
    """
    sb = get_supabase()
    q  = sb.table("doctors").select("id, doctor_name, specialization, location, is_available")

    if specialty:
        q = q.eq("specialization", specialty)
    if location:
        q = q.eq("location", location.lower().strip())
    if active_only:
        q = q.eq("is_available", True)

    rows = q.execute().data or []

    return [
        {
            "id":        r["id"],
            "name":      r["doctor_name"],
            "specialty": r["specialization"],
            "location":  r["location"],
            "is_active": r["is_available"],
        }
        for r in rows
    ]


def get_doctor(doctor_id: str) -> dict | None:
    sb  = get_supabase()
    row = (
        sb.table("doctors")
        .select("id, doctor_name, specialization, location, is_available, consultation_fee")
        .eq("id", doctor_id)
        .maybe_single()
        .execute()
        .data
    )
    if not row:
        return None
    return {
        "id":               row["id"],
        "name":             row["doctor_name"],
        "specialty":        row["specialization"],
        "location":         row["location"],
        "is_active":        row["is_available"],
        "consultation_fee": row.get("consultation_fee"),
    }


# ── Availability (computed from rules) ───────────────────────────────────────

def _weekday_name(d: datetime) -> str:
    return d.strftime("%A").lower()   # "monday", "tuesday", ...


def get_available_slots(
    doctor_ids: list[str],
    after:  str | None = None,
    before: str | None = None,
) -> list[dict]:
    """
    Compute available slots for a list of doctors by:
      1. Reading doctor_availability_rules (recurring weekly schedule)
      2. Removing any doctor_availability_exceptions (days off / overrides)
      3. Removing datetimes that already have a confirmed/reserved/paid appointment

    Returns list of dicts: { doctor_id, slot_datetime, slot_id (synthetic) }
    slot_id is a deterministic string "doctor_id::YYYY-MM-DDTHH:MM" so the agent
    can refer to it and the booking tool can parse it back.
    """
    sb = get_supabase()

    now        = datetime.now(timezone.utc)
    start_dt   = datetime.fromisoformat(after)  if after  else now
    end_dt     = datetime.fromisoformat(before) if before else now + timedelta(days=7)

    # Ensure timezone-aware
    if start_dt.tzinfo is None:
        start_dt = start_dt.replace(tzinfo=timezone.utc)
    if end_dt.tzinfo is None:
        end_dt = end_dt.replace(tzinfo=timezone.utc)

    all_slots: list[dict] = []

    for doctor_id in doctor_ids:
        # 1. Get availability rules for this doctor
        rules_resp = (
            sb.table("doctor_availability_rules")
            .select("days_of_week, start_time, end_time, effective_from, effective_to, is_active, repeat_interval_weeks")
            .eq("doctor_id", doctor_id)
            .eq("is_active", True)
            .execute()
        )
        rules = rules_resp.data or []
        if not rules:
            continue

        # 2. Get exceptions (unavailable dates) in range
        exceptions_resp = (
            sb.table("doctor_availability_exceptions")
            .select("exception_date, start_time, end_time, is_unavailable")
            .eq("doctor_id", doctor_id)
            .gte("exception_date", start_dt.date().isoformat())
            .lte("exception_date", end_dt.date().isoformat())
            .eq("is_unavailable", True)
            .execute()
        )
        exception_dates = {e["exception_date"] for e in (exceptions_resp.data or [])}

        # 3. Get existing booked appointments in range
        booked_resp = (
            sb.table("appointments")
            .select("appointment_date")
            .eq("doctor_id", doctor_id)
            .in_("status", ["reserved", "confirmed", "paid"])
            .gte("appointment_date", start_dt.isoformat())
            .lte("appointment_date", end_dt.isoformat())
            .execute()
        )
        booked_datetimes = set()
        for b in (booked_resp.data or []):
            # Normalise to "YYYY-MM-DDTHH:MM" for comparison
            dt = b["appointment_date"][:16]
            booked_datetimes.add(dt)

        # 4. Walk each day in range, check rules
        current = start_dt.replace(minute=0, second=0, microsecond=0)
        # Round up to next hour
        if current < now:
            current = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)

        while current <= end_dt:
            day_str  = current.date().isoformat()    # "2026-03-27"
            weekday  = _weekday_name(current)        # "monday"

            if day_str not in exception_dates:
                for rule in rules:
                    days = [d.lower() for d in rule["days_of_week"]]
                    if weekday not in days:
                        continue

                    # Check rule effective range
                    eff_from = rule.get("effective_from")
                    eff_to   = rule.get("effective_to")
                    if eff_from and day_str < eff_from:
                        continue
                    if eff_to and day_str > eff_to:
                        continue

                    # Generate hourly slots within rule start/end times
                    rule_start_h = int(rule["start_time"][:2])
                    rule_end_h   = int(rule["end_time"][:2])
                    slot_h       = current.hour

                    if rule_start_h <= slot_h < rule_end_h:
                        slot_key = current.strftime("%Y-%m-%dT%H:%M")
                        if slot_key not in booked_datetimes:
                            # Synthetic slot_id: "doctor_id::datetime"
                            synthetic_id = f"{doctor_id}::{slot_key}"
                            all_slots.append({
                                "doctor_id":    doctor_id,
                                "slot_id":      synthetic_id,
                                "slot_datetime": current.isoformat(),
                            })

            current += timedelta(hours=1)

    return sorted(all_slots, key=lambda s: s["slot_datetime"])


def parse_synthetic_slot_id(slot_id: str) -> tuple[str, str]:
    """
    Parse a synthetic slot_id back into (doctor_id, datetime_str).
    slot_id format: "doctor-uuid::YYYY-MM-DDTHH:MM"
    """
    parts = slot_id.split("::")
    if len(parts) != 2:
        raise ValueError(f"Invalid slot_id format: {slot_id}")
    return parts[0], parts[1]


# ── Patients ──────────────────────────────────────────────────────────────────

def find_patient_by_phone(phone: str) -> dict | None:
    """
    Look up a patient by phone number.
    Phone lives in the users table; patient record is in patients.
    Returns a normalised dict with: id (patient.id), name, phone, email, user_id
    """
    sb    = get_supabase()
    phone = phone.strip().replace(" ", "")

    # Find user by phone
    user_resp = (
        sb.table("users")
        .select("id, full_name, email, phone")
        .eq("phone", phone)
        .eq("role", "patient")
        .eq("is_active", True)
        .maybe_single()
        .execute()
    )
    user = user_resp.data
    if not user:
        return None

    # Find patient record linked to this user
    patient_resp = (
        sb.table("patients")
        .select("id, user_id")
        .eq("user_id", user["id"])
        .maybe_single()
        .execute()
    )
    patient = patient_resp.data
    if not patient:
        return None

    return {
        "id":      patient["id"],
        "user_id": user["id"],
        "name":    user["full_name"],
        "phone":   user["phone"],
        "email":   user["email"],
    }


def create_patient(name: str, phone: str, email: str | None) -> dict:
    """
    Create a new user (role=patient) + patient record.
    Returns normalised dict with: id (patient.id), name, phone, email, user_id
    """
    sb    = get_supabase()
    phone = phone.strip().replace(" ", "")

    # 1. Insert into users
    user_resp = (
        sb.table("users")
        .insert({
            "full_name": name,
            "phone":     phone,
            "email":     email or f"{phone}@hemashealth.placeholder",
            "role":      "patient",
            "is_active": True,
        })
        .execute()
    )
    user = user_resp.data[0]

    # 2. Insert into patients
    patient_resp = (
        sb.table("patients")
        .insert({"user_id": user["id"]})
        .execute()
    )
    patient = patient_resp.data[0]

    return {
        "id":      patient["id"],
        "user_id": user["id"],
        "name":    user["full_name"],
        "phone":   user["phone"],
        "email":   user["email"],
    }


# ── Appointments ──────────────────────────────────────────────────────────────

def create_appointment(
    patient_id:       str,
    doctor_id:        str,
    appointment_date: str,      # ISO datetime string
    reason_for_visit: str,
) -> dict:
    sb = get_supabase()

    # Double-check no appointment already exists at this datetime for this doctor
    clash = (
        sb.table("appointments")
        .select("id")
        .eq("doctor_id", doctor_id)
        .eq("appointment_date", appointment_date)
        .in_("status", ["reserved", "confirmed", "paid"])
        .execute()
        .data
    )
    if clash:
        return None  # Caller handles this as a booking conflict

    resp = (
        sb.table("appointments")
        .insert({
            "patient_id":       patient_id,
            "doctor_id":        doctor_id,
            "appointment_date": appointment_date,
            "status":           "reserved",
            "reason_for_visit": reason_for_visit,
        })
        .execute()
    )
    return resp.data[0] if resp.data else None


def get_appointment(appointment_id: str) -> dict | None:
    sb  = get_supabase()
    row = (
        sb.table("appointments")
        .select("*")
        .eq("id", appointment_id)
        .maybe_single()
        .execute()
        .data
    )
    return row


def get_appointments_for_patient(patient_id: str, status: str | None = None) -> list[dict]:
    sb = get_supabase()
    q  = (
        sb.table("appointments")
        .select("*")
        .eq("patient_id", patient_id)
        .order("appointment_date", desc=True)
    )
    if status:
        q = q.eq("status", status)
    return q.execute().data or []


def get_appointments_for_doctor_on_date(doctor_id: str, date: str) -> list[dict]:
    sb = get_supabase()
    return (
        sb.table("appointments")
        .select("*")
        .eq("doctor_id", doctor_id)
        .gte("appointment_date", f"{date}T00:00:00")
        .lte("appointment_date", f"{date}T23:59:59")
        .neq("status", "cancelled")
        .order("appointment_date", desc=False)
        .execute()
        .data or []
    )


def get_all_appointments(
    location: str | None = None,
    status:   str | None = None,
    limit:    int = 50,
) -> list[dict]:
    sb = get_supabase()

    if location:
        doctor_ids = [
            d["id"] for d in get_doctors(location=location)
        ]
        if not doctor_ids:
            return []
        q = sb.table("appointments").select("*").in_("doctor_id", doctor_ids)
    else:
        q = sb.table("appointments").select("*")

    if status:
        q = q.eq("status", status)

    return (
        q.order("appointment_date", desc=True)
        .limit(limit)
        .execute()
        .data or []
    )


def update_appointment_status(appointment_id: str, status: str) -> bool:
    sb = get_supabase()
    sb.table("appointments").update({"status": status}).eq("id", appointment_id).execute()
    return True


def reschedule_appointment_db(
    appointment_id:   str,
    new_appointment_date: str,
    new_doctor_id:    str,
) -> bool:
    sb = get_supabase()
    sb.table("appointments").update({
        "appointment_date": new_appointment_date,
        "doctor_id":        new_doctor_id,
        "status":           "reserved",
    }).eq("id", appointment_id).execute()
    return True
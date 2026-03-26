-- HemasHealth IQ — Supabase Schema
-- Run this in the Supabase SQL editor to set up all required tables.

-- ── Extensions ────────────────────────────────────────────────────────────────
create extension if not exists "uuid-ossp";

-- ── Doctors ───────────────────────────────────────────────────────────────────
create table if not exists doctors (
  id          uuid primary key default uuid_generate_v4(),
  name        text not null,
  specialty   text not null,
  location    text not null check (location in ('wattala', 'thalawathugoda')),
  is_active   boolean not null default true,
  created_at  timestamptz not null default now()
);

-- ── Doctor Slots ──────────────────────────────────────────────────────────────
create table if not exists doctor_slots (
  id             uuid primary key default uuid_generate_v4(),
  doctor_id      uuid not null references doctors(id) on delete cascade,
  slot_datetime  timestamptz not null,
  is_booked      boolean not null default false,
  created_at     timestamptz not null default now(),

  unique (doctor_id, slot_datetime)  -- prevent duplicate slots
);

create index if not exists idx_doctor_slots_doctor_id on doctor_slots(doctor_id);
create index if not exists idx_doctor_slots_datetime  on doctor_slots(slot_datetime);
create index if not exists idx_doctor_slots_is_booked on doctor_slots(is_booked);

-- ── Patients ──────────────────────────────────────────────────────────────────
create table if not exists patients (
  id          uuid primary key default uuid_generate_v4(),
  name        text not null,
  phone       text not null unique,
  email       text,
  created_at  timestamptz not null default now()
);

create index if not exists idx_patients_phone on patients(phone);

-- ── Appointments ──────────────────────────────────────────────────────────────
create table if not exists appointments (
  id                uuid primary key default uuid_generate_v4(),
  patient_id        uuid not null references patients(id) on delete cascade,
  doctor_id         uuid not null references doctors(id) on delete cascade,
  slot_id           uuid not null references doctor_slots(id) on delete cascade,
  status            text not null default 'confirmed'
                      check (status in ('confirmed', 'cancelled', 'completed')),
  symptoms_summary  text,
  created_at        timestamptz not null default now()
);

create index if not exists idx_appointments_patient_id on appointments(patient_id);
create index if not exists idx_appointments_doctor_id  on appointments(doctor_id);
create index if not exists idx_appointments_slot_id    on appointments(slot_id);
create index if not exists idx_appointments_status     on appointments(status);

-- ── Seed: Sample Doctors ──────────────────────────────────────────────────────
-- Remove or expand before production use.
insert into doctors (name, specialty, location) values
  ('Dr. Nimal Perera',     'Cardiology',                'wattala'),
  ('Dr. Shalini Fernando', 'Cardiology',                'thalawathugoda'),
  ('Dr. Ruwan Jayasinghe', 'Neurology',                 'wattala'),
  ('Dr. Amara Silva',      'Neurology',                 'thalawathugoda'),
  ('Dr. Priyanka Gunasekara', 'General Medicine',       'wattala'),
  ('Dr. Tharaka Bandara',  'General Medicine',          'thalawathugoda'),
  ('Dr. Dilini Wickramasinghe', 'Orthopedics',          'wattala'),
  ('Dr. Kasun Rajapaksa',  'Gastroenterology',          'wattala'),
  ('Dr. Nadeesha Herath',  'Obstetrics & Gynecology',   'thalawathugoda'),
  ('Dr. Roshan Mendis',    'Dermatology',               'wattala')
on conflict do nothing;

-- ── Seed: Sample Slots (next 7 days, 9am–5pm, hourly) ────────────────────────
-- This is a convenience seed. In production, doctors/admins manage slots
-- via the Doctor Dashboard in Next.js (writing directly to doctor_slots).
do $$
declare
  doc record;
  d   int;
  h   int;
begin
  for doc in select id from doctors loop
    for d in 1..7 loop
      for h in 9..16 loop
        insert into doctor_slots (doctor_id, slot_datetime)
        values (
          doc.id,
          (current_date + d + (h || ' hours')::interval)::timestamptz
        )
        on conflict do nothing;
      end loop;
    end loop;
  end loop;
end $$;
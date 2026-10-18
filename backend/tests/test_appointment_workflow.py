from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time, timedelta, timezone
from threading import Barrier
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.providers import (
    Appointment,
    AppointmentEvent,
    AppointmentSlotLock,
    Doctor,
    DoctorSchedule,
    Hospital,
)
from app.models.user import User
from tests.auth_utils import make_session_token

IST = ZoneInfo("Asia/Kolkata")


def _next_day_with_schedule(offset_days: int = 2) -> date:
    return (datetime.now(IST) + timedelta(days=offset_days)).date()


def _appointment_app(database_url="sqlite://"):
    engine = create_engine(
        database_url,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool if database_url == "sqlite://" else None,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)

    def override_database():
        with session_factory() as db:
            yield db

    service_day = _next_day_with_schedule()
    with session_factory() as db:
        hospital = Hospital(
            name="Transactional Hospital",
            city="Raipur",
            state="Chhattisgarh",
            verified=True,
            verification_status="verified",
        )
        db.add(hospital)
        db.flush()
        doctor = Doctor(
            hospital_id=hospital.id,
            full_name="Dr. Appointment Test",
            specialty="General Medicine",
            languages="Hindi, English",
            language_list=["Hindi", "English"],
            consultation_mode="in_person",
            consultation_types=["in_person", "online"],
            verified=True,
            verification_status="verified",
            is_active=True,
        )
        patient = User(full_name="Appointment Patient", email=f"patient-{uuid4()}@example.test", password_hash="unused", role="patient")
        other_patient = User(full_name="Other Patient", email=f"other-{uuid4()}@example.test", password_hash="unused", role="patient")
        doctor_user = User(
            full_name="Doctor User",
            email=f"doctor-{uuid4()}@example.test",
            password_hash="unused",
            role="doctor",
            hospital_id=hospital.id,
        )
        db.add_all([doctor, patient, other_patient, doctor_user])
        db.flush()
        doctor_user.doctor_id = doctor.id
        for weekday in range(7):
            doctor.schedules.append(
                DoctorSchedule(
                    day_of_week=weekday,
                    starts_at=time(9, 0),
                    ends_at=time(12, 0),
                    timezone="Asia/Kolkata",
                    consultation_type="in_person",
                    is_active=True,
                )
            )
        db.commit()
        tokens = {
            "patient": make_session_token(db, patient),
            "other_patient": make_session_token(db, other_patient),
            "doctor": make_session_token(db, doctor_user),
        }
        ids = {"doctor": doctor.id, "hospital": hospital.id}

    app.dependency_overrides[get_db] = override_database
    return engine, session_factory, tokens, ids, service_day


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _time_at(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(day, time(hour, minute), tzinfo=IST)


def _book(client, token, doctor_id, when, key=None):
    return client.post(
        "/api/v1/providers/appointments",
        headers={**_auth(token), "Idempotency-Key": key or str(uuid4())},
        json={
            "doctor_id": doctor_id,
            "scheduled_for": when.isoformat(),
            "consultation_type": "in_person",
            "notes": "Follow-up",
        },
    )


def test_available_slots_booking_idempotency_and_conflicts():
    engine, _, tokens, ids, day = _appointment_app()
    try:
        with TestClient(app) as client:
            slot_url = f"/api/v1/providers/doctors/{ids['doctor']}/available-slots?day={day.isoformat()}&consultation_type=in_person"
            slots = client.get(slot_url, headers=_auth(tokens["patient"]))
            assert slots.status_code == 200
            assert [row["local_time"][:5] for row in slots.json()] == ["09:00", "09:30", "10:00", "10:30", "11:00", "11:30"]
            assert slots.json()[0]["timezone"] == "Asia/Kolkata"
            first_start = slots.json()[0]["scheduled_for"]

            key = str(uuid4())
            booked = _book(client, tokens["patient"], ids["doctor"], datetime.fromisoformat(first_start), key)
            assert booked.status_code == 201
            assert booked.json()["status"] == "scheduled"

            duplicate = _book(client, tokens["patient"], ids["doctor"], datetime.fromisoformat(first_start), key)
            assert duplicate.status_code == 200
            assert duplicate.json()["id"] == booked.json()["id"]

            duplicate_slot = _book(client, tokens["other_patient"], ids["doctor"], datetime.fromisoformat(first_start))
            assert duplicate_slot.status_code == 409

            slots_after_booking = client.get(slot_url, headers=_auth(tokens["patient"]))
            assert slots_after_booking.status_code == 200
            assert first_start not in [row["scheduled_for"] for row in slots_after_booking.json()]

            mismatch = _book(client, tokens["patient"], ids["doctor"], _time_at(day, 9, 30), key)
            assert mismatch.status_code == 409

            with Session(engine) as db:
                assert db.scalar(select(func.count()).select_from(Appointment)) == 1
                assert db.scalar(select(func.count()).select_from(AppointmentSlotLock)) == 1
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_available_slots_use_ist_calendar_days_for_non_ist_schedules():
    engine, session_factory, tokens, ids, day = _appointment_app()
    try:
        schedule_day = day - timedelta(days=1)
        with session_factory() as db:
            doctor = db.get(Doctor, ids["doctor"])
            doctor.schedules.append(
                DoctorSchedule(
                    day_of_week=schedule_day.weekday(),
                    starts_at=time(20, 0),
                    ends_at=time(21, 0),
                    timezone="UTC",
                    consultation_type="in_person",
                    is_active=True,
                )
            )
            db.commit()

        with TestClient(app) as client:
            response = client.get(
                f"/api/v1/providers/doctors/{ids['doctor']}/available-slots?day={day.isoformat()}",
                headers=_auth(tokens["patient"]),
            )
            assert response.status_code == 200
            expected_start = datetime.combine(schedule_day, time(20), tzinfo=timezone.utc)
            cross_midnight_slot = next(
                slot for slot in response.json()
                if datetime.fromisoformat(slot["scheduled_for"]) == expected_start
            )
            assert cross_midnight_slot["local_date"] == day.isoformat()
            assert cross_midnight_slot["local_time"].startswith("01:30")
            assert cross_midnight_slot["timezone"] == "Asia/Kolkata"
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_cancel_releases_slot_and_records_audit_history_with_access_control():
    engine, _, tokens, ids, day = _appointment_app()
    try:
        with TestClient(app) as client:
            booked = _book(client, tokens["patient"], ids["doctor"], _time_at(day, 9))
            assert booked.status_code == 201
            appointment_id = booked.json()["id"]

            denied = client.patch(
                f"/api/v1/providers/appointments/{appointment_id}/cancel",
                headers=_auth(tokens["other_patient"]),
                json={"reason": "not mine"},
            )
            assert denied.status_code == 403

            anonymous = client.patch(
                f"/api/v1/providers/appointments/{appointment_id}/cancel",
                json={"reason": "anonymous"},
            )
            assert anonymous.status_code == 401

            cancelled = client.patch(
                f"/api/v1/providers/appointments/{appointment_id}/cancel",
                headers=_auth(tokens["patient"]),
                json={"reason": "Patient requested cancellation"},
            )
            assert cancelled.status_code == 200
            assert cancelled.json()["status"] == "cancelled"

            repeated = client.patch(
                f"/api/v1/providers/appointments/{appointment_id}/cancel",
                headers=_auth(tokens["patient"]),
                json={},
            )
            assert repeated.status_code == 409

            available = client.get(
                f"/api/v1/providers/doctors/{ids['doctor']}/available-slots?day={day.isoformat()}",
                headers=_auth(tokens["patient"]),
            )
            assert available.status_code == 200
            assert available.json()[0]["local_time"].startswith("09:00")

            history = client.get(
                f"/api/v1/providers/appointments/{appointment_id}/history",
                headers=_auth(tokens["patient"]),
            )
            assert history.status_code == 200
            assert [event["event_type"] for event in history.json()] == ["booked", "cancelled"]
            assert history.json()[-1]["reason"] == "Patient requested cancellation"

            fetch_appointment = client.get(
                f"/api/v1/providers/appointments/{appointment_id}",
                headers=_auth(tokens["patient"]),
            )
            assert fetch_appointment.status_code == 200
            assert fetch_appointment.json()["id"] == appointment_id
            assert fetch_appointment.json()["status"] == "cancelled"

            denied_fetch = client.get(
                f"/api/v1/providers/appointments/{appointment_id}",
                headers=_auth(tokens["other_patient"]),
            )
            assert denied_fetch.status_code == 403

            missing_fetch = client.get(
                "/api/v1/providers/appointments/999999",
                headers=_auth(tokens["patient"]),
            )
            assert missing_fetch.status_code == 404

            denied_history = client.get(
                f"/api/v1/providers/appointments/{appointment_id}/history",
                headers=_auth(tokens["other_patient"]),
            )
            assert denied_history.status_code == 403
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_confirmation_rescheduling_idempotency_and_state_transitions():
    engine, _, tokens, ids, day = _appointment_app()
    try:
        with TestClient(app) as client:
            booked = _book(client, tokens["patient"], ids["doctor"], _time_at(day, 9))
            appointment_id = booked.json()["id"]

            confirmed = client.post(
                f"/api/v1/providers/appointments/{appointment_id}/confirm",
                headers=_auth(tokens["doctor"]),
            )
            assert confirmed.status_code == 200
            assert confirmed.json()["status"] == "confirmed"

            confirm_again = client.post(
                f"/api/v1/providers/appointments/{appointment_id}/confirm",
                headers=_auth(tokens["doctor"]),
            )
            assert confirm_again.status_code == 409

            new_time = _time_at(day, 10)
            key = str(uuid4())
            reschedule = client.patch(
                f"/api/v1/providers/appointments/{appointment_id}/reschedule",
                headers={**_auth(tokens["patient"]), "Idempotency-Key": key},
                json={"scheduled_for": new_time.isoformat(), "consultation_type": "in_person", "reason": "Change requested"},
            )
            assert reschedule.status_code == 200
            assert reschedule.json()["status"] == "scheduled"
            assert datetime.fromisoformat(reschedule.json()["scheduled_for"]) == new_time.astimezone(timezone.utc)

            replay = client.patch(
                f"/api/v1/providers/appointments/{appointment_id}/reschedule",
                headers={**_auth(tokens["patient"]), "Idempotency-Key": key},
                json={"scheduled_for": new_time.isoformat(), "consultation_type": "in_person", "reason": "Change requested"},
            )
            assert replay.status_code == 200
            assert replay.json()["id"] == appointment_id

            used_for_different_request = client.patch(
                f"/api/v1/providers/appointments/{appointment_id}/reschedule",
                headers={**_auth(tokens["patient"]), "Idempotency-Key": key},
                json={"scheduled_for": _time_at(day, 10, 30).isoformat(), "consultation_type": "in_person"},
            )
            assert used_for_different_request.status_code == 409

            old_slots = client.get(
                f"/api/v1/providers/doctors/{ids['doctor']}/available-slots?day={day.isoformat()}",
                headers=_auth(tokens["patient"]),
            ).json()
            assert any(item["local_time"].startswith("09:00") for item in old_slots)
            assert not any(item["local_time"].startswith("10:00") for item in old_slots)

            history = client.get(
                f"/api/v1/providers/appointments/{appointment_id}/history",
                headers=_auth(tokens["patient"]),
            )
            assert history.status_code == 200
            assert [event["event_type"] for event in history.json()] == ["booked", "confirmed", "rescheduled"]
            assert history.json()[-1]["previous_scheduled_for"] is not None

            cancel = client.patch(
                f"/api/v1/providers/appointments/{appointment_id}/cancel",
                headers=_auth(tokens["patient"]),
                json={},
            )
            assert cancel.status_code == 200
            assert cancel.json()["status"] == "cancelled"
            no_reschedule = client.patch(
                f"/api/v1/providers/appointments/{appointment_id}/reschedule",
                headers={**_auth(tokens["patient"]), "Idempotency-Key": str(uuid4())},
                json={"scheduled_for": _time_at(day, 11).isoformat()},
            )
            assert no_reschedule.status_code == 409
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_slot_lock_database_constraint_rejects_parallel_double_booking(tmp_path):
    database_url = f"sqlite:///{tmp_path}/appointments-concurrency.db"
    engine, session_factory, _, ids, day = _appointment_app(database_url)
    try:
        with session_factory() as db:
            doctor = db.get(Doctor, ids["doctor"])
            patients = [
                User(full_name=f"Concurrent Patient {index}", email=f"parallel-{uuid4()}@example.test", password_hash="unused", role="patient")
                for index in range(2)
            ]
            db.add_all(patients)
            db.flush()
            appointments = [
                Appointment(
                    patient_user_id=patient.id,
                    doctor_id=doctor.id,
                    hospital_id=doctor.hospital_id,
                    scheduled_for=_time_at(day, 9).astimezone(timezone.utc),
                    duration_minutes=30,
                    consultation_type="in_person",
                    status="scheduled",
                )
                for patient in patients
            ]
            db.add_all(appointments)
            db.commit()
            appointment_ids = [appointment.id for appointment in appointments]

        barrier = Barrier(2)

        def claim_slot(appointment_id):
            with session_factory() as db:
                barrier.wait(timeout=5)
                db.add(
                    AppointmentSlotLock(
                        appointment_id=appointment_id,
                        doctor_id=ids["doctor"],
                        slot_start=_time_at(day, 9).astimezone(timezone.utc),
                    )
                )
                try:
                    db.commit()
                    return "claimed"
                except (IntegrityError, OperationalError):
                    db.rollback()
                    return "conflict"

        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(claim_slot, appointment_ids))
        assert sorted(outcomes) == ["claimed", "conflict"]
        with session_factory() as db:
            assert db.scalar(select(func.count()).select_from(AppointmentSlotLock)) == 1
    finally:
        engine.dispose()

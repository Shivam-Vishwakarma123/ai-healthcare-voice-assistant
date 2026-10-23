from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth.security import hash_password, verify_password
from app.core.config import settings
from app.core.database import Base
from app.models.billing import Invoice, Payment
from app.models.patient import Patient
from app.models.providers import (
    Appointment,
    AppointmentEvent,
    AppointmentSlotLock,
    Doctor,
    DoctorSchedule,
    Hospital,
)
from app.models.user import User
from app.seed_demo import DEMO_PASSWORD, SEED_MARKER, clean_demo_data, main, seed_demo_data


def _seeded_database():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
    return engine, sessions


def test_demo_seed_is_repeatable_and_relationships_are_consistent():
    engine, sessions = _seeded_database()
    try:
        with sessions.begin() as db:
            existing_admin = User(
                full_name="Existing Platform Administrator",
                email="existing-platform-admin@example.test",
                password_hash=hash_password("existing-admin-password"),
                role="platform_admin",
            )
            db.add(existing_admin)
            first_run = seed_demo_data(db)
        with sessions.begin() as db:
            second_run = seed_demo_data(db)

        assert first_run == {
            "hospitals_created": 3,
            "doctors_created": 10,
            "patients_created": 20,
            "patient_accounts_created": 20,
            "hospital_admins_created": 3,
            "doctor_accounts_created": 10,
            "appointments_created": 30,
            "invoices_created": 20,
            "payments_created": 20,
            "conversations_created": 6,
            "allergies_created": 2,
            "ai_reports_created": 5,
            "prescriptions_created": 6,
            "notes_created": 7,
            "documents_created": 6,
        }
        assert all(value == 0 for value in second_run.values())

        with sessions() as db:
            demo_hospitals = db.scalars(
                select(Hospital).where(Hospital.name.like("DEMO - %"))
            ).all()
            demo_doctors = db.scalars(
                select(Doctor).where(Doctor.bio.like(f"{SEED_MARKER}: fictional clinician %"))
            ).all()
            demo_users = db.scalars(
                select(User).where(User.email.like("%@demo.carevoice.test"))
            ).all()
            demo_patients = db.scalars(
                select(Patient).where(Patient.email.like("%@demo.carevoice.test"))
            ).all()
            demo_appointments = db.scalars(
                select(Appointment).where(Appointment.notes.like(f"{SEED_MARKER}:appointment:%"))
            ).all()
            demo_invoices = db.scalars(
                select(Invoice).where(Invoice.invoice_number.like("DEMO-SEED-V1-%"))
            ).all()
            demo_payments = db.scalars(
                select(Payment).where(Payment.provider_order_id.like("demo_seed_v1_%"))
            ).all()

            assert len(demo_hospitals) == 3
            assert len(demo_doctors) == 10
            assert len(demo_users) == 33
            assert len(demo_patients) == 20
            assert len(demo_appointments) == 30
            assert db.scalar(
                select(func.count())
                .select_from(AppointmentEvent)
                .where(AppointmentEvent.appointment_id.in_({appointment.id for appointment in demo_appointments}))
            ) == 65
            assert len(demo_invoices) == 20
            assert len(demo_payments) == 20
            assert all(hospital.verification_status == "verified" for hospital in demo_hospitals)
            assert all(doctor.hospital_id in {hospital.id for hospital in demo_hospitals} for doctor in demo_doctors)
            assert all(len(doctor.schedules) == 5 for doctor in demo_doctors)
            assert all(user.is_active for user in demo_users)

            states = {
                status: count
                for status, count in db.execute(
                    select(Appointment.status, func.count())
                    .where(Appointment.notes.like(f"{SEED_MARKER}:appointment:%"))
                    .group_by(Appointment.status)
                )
            }
            assert states == {
                "cancelled": 10,
                "completed": 10,
                "confirmed": 5,
                "scheduled": 5,
            }

            for appointment in demo_appointments:
                doctor = db.get(Doctor, appointment.doctor_id)
                patient = db.get(User, appointment.patient_user_id)
                assert doctor is not None and doctor.hospital_id == appointment.hospital_id
                assert patient is not None and patient.role == "patient"
            active_ids = {
                appointment.id
                for appointment in demo_appointments
                if appointment.status in {"scheduled", "confirmed"}
            }
            lock_ids = set(
                db.scalars(
                    select(AppointmentSlotLock.appointment_id).where(
                        AppointmentSlotLock.appointment_id.in_(active_ids)
                    )
                ).all()
            )
            assert lock_ids == active_ids

            for invoice in demo_invoices:
                appointment = db.get(Appointment, invoice.appointment_id)
                doctor = db.get(Doctor, appointment.doctor_id)
                assert appointment.patient_user_id == invoice.owner_user_id
                assert appointment.hospital_id == invoice.hospital_id
                assert invoice.amount_minor == doctor.fee_minor
            assert all(
                payment.provider_order_id.startswith("demo_seed_v1_")
                for payment in demo_payments
            )

            patient = db.scalar(select(User).where(User.email == "patient01@demo.carevoice.test"))
            doctor_user = db.scalar(select(User).where(User.email == "doctor01@demo.carevoice.test"))
            hospital_admin = db.scalar(
                select(User).where(User.email == "hospital-admin01@demo.carevoice.test")
            )
            assert patient and verify_password(DEMO_PASSWORD, patient.password_hash)
            assert doctor_user and doctor_user.role == "doctor"
            assert hospital_admin and hospital_admin.role == "hospital_admin"
            existing_admin = db.scalar(
                select(User).where(User.email == "existing-platform-admin@example.test")
            )
            assert existing_admin
            assert existing_admin.full_name == "Existing Platform Administrator"
            assert verify_password("existing-admin-password", existing_admin.password_hash)
            assert db.scalar(select(DoctorSchedule.id).limit(1)) is not None
    finally:
        engine.dispose()


def test_seed_stops_on_identity_conflict_without_committing_partial_records():
    engine, sessions = _seeded_database()
    try:
        with sessions.begin() as db:
            db.add(
                User(
                    full_name="Conflicting account",
                    email="patient01@demo.carevoice.test",
                    password_hash="existing-hash",
                    role="doctor",
                )
            )
        with pytest.raises(ValueError, match="identity conflicts"):
            with sessions.begin() as db:
                seed_demo_data(db)
        with sessions() as db:
            assert db.scalar(select(func.count()).select_from(Hospital)) == 0
            assert db.scalar(select(func.count()).select_from(Doctor)) == 0
    finally:
        engine.dispose()


def test_cli_refuses_to_seed_outside_development_and_test(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "production")
    with pytest.raises(SystemExit, match="APP_ENV"):
        main()
    engine, sessions = _seeded_database()
    try:
        with pytest.raises(RuntimeError, match="APP_ENV"):
            with sessions.begin() as db:
                seed_demo_data(db)
        with sessions() as db:
            assert db.scalar(select(func.count()).select_from(Hospital)) == 0
    finally:
        engine.dispose()


def test_cli_does_not_print_seed_password(monkeypatch, capsys):
    monkeypatch.setattr(settings, "app_env", "test")
    engine, sessions = _seeded_database()
    monkeypatch.setattr("app.seed_demo.SessionLocal", sessions)
    try:
        main()
        assert DEMO_PASSWORD not in capsys.readouterr().out
    finally:
        engine.dispose()


def test_demo_seed_uses_slots_in_the_past_and_future():
    engine, sessions = _seeded_database()
    try:
        with sessions.begin() as db:
            seed_demo_data(db)
        with sessions() as db:
            past = db.scalar(
                select(func.count())
                .select_from(Appointment)
                .where(
                    Appointment.notes.like(f"{SEED_MARKER}:appointment:%"),
                    Appointment.status.in_(("completed", "cancelled")),
                    Appointment.scheduled_for < datetime.now(timezone.utc),
                )
            )
            upcoming = db.scalar(
                select(func.count())
                .select_from(Appointment)
                .where(
                    Appointment.notes.like(f"{SEED_MARKER}:appointment:%"),
                    Appointment.status.in_(("scheduled", "confirmed")),
                    Appointment.scheduled_for > datetime.now(timezone.utc),
                )
            )
            assert past == 20
            assert upcoming == 10
    finally:
        engine.dispose()


def test_clean_demo_data_safely_removes_demo_data_and_preserves_user_records():
    engine, sessions = _seeded_database()
    try:
        with sessions.begin() as db:
            real_user = User(
                full_name="Real Patient Sneha",
                email="sneha@gmail.com",
                password_hash=hash_password("RealSecret123!"),
                role="patient",
            )
            db.add(real_user)
            db.flush()
            real_invoice = Invoice(
                owner_user_id=real_user.id,
                invoice_number="INV-REAL-2026-001",
                currency="inr",
                amount_minor=150000,
                status="paid",
                description="Real consultation fee",
            )
            db.add(real_invoice)
            seed_demo_data(db)

        # Verify demo data exists alongside real user
        with sessions() as db:
            assert db.scalar(select(func.count()).select_from(User)) > 2
            assert db.scalar(select(User).where(User.email == "sneha@gmail.com")) is not None
            assert db.scalar(select(User).where(User.email == "patient01@demo.carevoice.test")) is not None

        # Clean demo data
        with sessions.begin() as db:
            clean_counts = clean_demo_data(db)

        # Verify demo records are removed while real user records persist
        with sessions() as db:
            assert clean_counts["users_removed"] > 0
            assert db.scalar(select(User).where(User.email == "patient01@demo.carevoice.test")) is None
            persisting_user = db.scalar(select(User).where(User.email == "sneha@gmail.com"))
            assert persisting_user is not None
            assert persisting_user.full_name == "Real Patient Sneha"
            persisting_invoice = db.scalar(
                select(Invoice).where(Invoice.owner_user_id == persisting_user.id)
            )
            assert persisting_invoice is not None
            assert persisting_invoice.invoice_number == "INV-REAL-2026-001"
    finally:
        engine.dispose()


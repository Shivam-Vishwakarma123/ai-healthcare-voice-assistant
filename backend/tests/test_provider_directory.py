from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.providers import Doctor, DoctorSchedule, Hospital
from app.models.user import User
from tests.auth_utils import make_session_token


def test_appointment_booking_cors_preflight_allows_idempotency_header():
    with TestClient(app) as client:
        response = client.options(
            "/api/v1/providers/appointments",
            headers={
                "Origin": "http://127.0.0.1:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,content-type,idempotency-key",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:3000"
    assert "idempotency-key" in response.headers["access-control-allow-headers"].lower()


def test_provider_directory_and_appointment_booking():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)

    def override_database():
        with session_factory() as db:
            yield db

    with session_factory() as db:
        patient = User(full_name="Patient One", email="patient-one@example.com", password_hash="unused", role="patient")
        other = User(full_name="Other User", email="patient-two@example.com", password_hash="unused", role="patient")
        hospital = Hospital(name="Sanjeevani Multispeciality", city="Raipur", state="Chhattisgarh", departments="Cardiology, General Medicine", description="Demo hospital", verified=True, verification_status="verified")
        doctor = Doctor(
            hospital_id=None,
            full_name="Dr. Ananya Singh",
            specialty="Cardiology",
            specialties=["Cardiology"],
            languages="English, Hindi",
            language_list=["English", "Hindi"],
            consultation_types=["in_person"],
            fee_minor=120000,
            verified=True,
            verification_status="verified",
            is_active=True,
            experience_years=12,
            consultation_mode="in_person",
        )
        db.add_all([patient, other, hospital, doctor])
        db.commit()
        hospital.id = 1
        doctor.hospital_id = hospital.id
        scheduled_for = datetime.now(timezone.utc).replace(hour=4, minute=0, second=0, microsecond=0) + timedelta(days=3)
        local_time = scheduled_for.astimezone(ZoneInfo("Asia/Kolkata"))
        doctor.schedules.append(
            DoctorSchedule(
                day_of_week=local_time.weekday(),
                starts_at=datetime.strptime("09:00", "%H:%M").time(),
                ends_at=datetime.strptime("12:00", "%H:%M").time(),
                timezone="Asia/Kolkata",
                consultation_type="in_person",
            )
        )
        db.commit()
        db.refresh(patient)
        db.refresh(doctor)
        patient_token = make_session_token(db, patient)
        other_token = make_session_token(db, other)

    app.dependency_overrides[get_db] = override_database
    try:
        with TestClient(app) as client:
            hospitals = client.get("/api/v1/providers/hospitals", headers={"Authorization": f"Bearer {patient_token}"})
            assert hospitals.status_code == 200
            assert hospitals.json()["items"][0]["city"] == "Raipur"

            recommendations = client.post(
                "/api/v1/providers/recommendations",
                headers={"Authorization": f"Bearer {patient_token}"},
                json={"symptoms": "chest pain and breathlessness"},
            )
            assert recommendations.status_code == 200
            assert recommendations.json()[0]["doctor_name"] == "Dr. Ananya Singh"
            assert recommendations.json()[0]["available_slots"] == []

            booking = client.post(
                "/api/v1/providers/appointments",
                headers={
                    "Authorization": f"Bearer {patient_token}",
                    "Idempotency-Key": "provider-directory-booking-001",
                },
                json={"doctor_id": doctor.id, "scheduled_for": scheduled_for.isoformat(), "notes": "Need follow-up"},
            )
            assert booking.status_code == 201
            assert booking.json()["status"] == "scheduled"

            mine = client.get("/api/v1/providers/appointments", headers={"Authorization": f"Bearer {patient_token}"})
            assert mine.status_code == 200
            assert len(mine.json()) == 1

            other_view = client.get("/api/v1/providers/appointments", headers={"Authorization": f"Bearer {other_token}"})
            assert other_view.status_code == 200
            assert other_view.json() == []
    finally:
        app.dependency_overrides.clear()
        engine.dispose()

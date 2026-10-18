from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.providers import Doctor, Hospital
from app.models.user import User
from tests.auth_utils import make_session_token


def _profile_app():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)

    def override_database():
        with session_factory() as db:
            yield db

    with session_factory() as db:
        verified_hospital = Hospital(
            name="Raipur Care",
            city="Raipur",
            state="Chhattisgarh",
            departments="Cardiology",
            verified=True,
            verification_status="verified",
        )
        other_hospital = Hospital(
            name="Bilaspur Health",
            city="Bilaspur",
            state="Chhattisgarh",
            verified=True,
            verification_status="verified",
        )
        unverified_hospital = Hospital(
            name="Unverified Clinic",
            city="Raipur",
            state="Chhattisgarh",
        )
        db.add_all([verified_hospital, other_hospital, unverified_hospital])
        db.flush()
        doctor = Doctor(
            hospital_id=verified_hospital.id,
            full_name="Dr. Asha Rao",
            specialty="Cardiology",
            specialties=["Cardiology"],
            languages="Hindi, English",
            language_list=["Hindi", "English"],
            consultation_mode="online",
            consultation_types=["online"],
            fee_minor=80000,
            verified=True,
            verification_status="verified",
            is_active=True,
            experience_years=8,
        )
        second_doctor = Doctor(
            hospital_id=verified_hospital.id,
            full_name="Dr. Kiran Das",
            specialty="General Medicine",
            specialties=["General Medicine"],
            languages="English",
            language_list=["English"],
            consultation_mode="in_person",
            consultation_types=["in_person"],
            verified=True,
            verification_status="verified",
            is_active=True,
        )
        other_tenant_doctor = Doctor(
            hospital_id=other_hospital.id,
            full_name="Dr. Other Tenant",
            specialty="Neurology",
            verified=True,
            verification_status="verified",
            is_active=True,
        )
        unverified_doctor = Doctor(
            hospital_id=unverified_hospital.id,
            full_name="Unverified Provider",
            specialty="Cardiology",
            verified=True,
            verification_status="verified",
            is_active=True,
        )
        db.add_all([doctor, second_doctor, other_tenant_doctor, unverified_doctor])
        db.flush()
        hospital_admin = User(
            full_name="Hospital Admin",
            email="hospital-admin@example.test",
            password_hash="unused",
            role="hospital_admin",
            hospital_id=verified_hospital.id,
        )
        other_admin = User(
            full_name="Other Admin",
            email="other-admin@example.test",
            password_hash="unused",
            role="hospital_admin",
            hospital_id=other_hospital.id,
        )
        hospital_staff = User(
            full_name="Hospital Staff",
            email="hospital-staff@example.test",
            password_hash="unused",
            role="hospital_staff",
            hospital_id=verified_hospital.id,
        )
        doctor_user = User(
            full_name="Doctor Account",
            email="doctor@example.test",
            password_hash="unused",
            role="doctor",
            hospital_id=verified_hospital.id,
            doctor_id=doctor.id,
        )
        platform_admin = User(
            full_name="Platform Admin",
            email="platform-admin@example.test",
            password_hash="unused",
            role="platform_admin",
        )
        db.add_all([hospital_admin, other_admin, hospital_staff, doctor_user, platform_admin])
        db.commit()
        tokens = {
            "hospital_admin": make_session_token(db, hospital_admin),
            "other_admin": make_session_token(db, other_admin),
            "hospital_staff": make_session_token(db, hospital_staff),
            "doctor": make_session_token(db, doctor_user),
            "platform_admin": make_session_token(db, platform_admin),
        }
        ids = {
            "hospital": verified_hospital.id,
            "other_hospital": other_hospital.id,
            "doctor": doctor.id,
            "other_doctor": second_doctor.id,
            "other_tenant_doctor": other_tenant_doctor.id,
            "unverified_doctor": unverified_doctor.id,
        }

    app.dependency_overrides[get_db] = override_database
    return engine, tokens, ids


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def test_provider_directory_is_verified_searchable_and_paginated():
    engine, tokens, ids = _profile_app()
    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/v1/providers/doctors?city=Raipur&limit=1&offset=0",
                headers=_headers(tokens["hospital_admin"]),
            )
            assert response.status_code == 200
            assert response.json()["total"] == 2
            assert response.json()["limit"] == 1
            assert len(response.json()["items"]) == 1

            second_page = client.get(
                "/api/v1/providers/doctors?city=Raipur&limit=1&offset=1",
                headers=_headers(tokens["hospital_admin"]),
            )
            assert second_page.status_code == 200
            assert second_page.json()["items"][0]["id"] != response.json()["items"][0]["id"]

            filtered = client.get(
                "/api/v1/providers/doctors?specialty=Cardiology&language=Hindi",
                headers=_headers(tokens["hospital_admin"]),
            )
            assert filtered.status_code == 200
            assert [item["full_name"] for item in filtered.json()["items"]] == ["Dr. Asha Rao"]
            assert all(item["verification_status"] == "verified" for item in filtered.json()["items"])

            hidden_profile = client.get(
                f"/api/v1/providers/doctors/{ids['unverified_doctor']}",
                headers=_headers(tokens["hospital_admin"]),
            )
            assert hidden_profile.status_code == 404
            hospitals = client.get("/api/v1/providers/hospitals?limit=1", headers=_headers(tokens["doctor"]))
            assert hospitals.status_code == 200
            assert hospitals.json()["total"] == 2
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_hospital_admin_and_staff_are_scoped_and_role_limited():
    engine, tokens, ids = _profile_app()
    try:
        with TestClient(app) as client:
            own_hospital_update = client.patch(
                f"/api/v1/providers/hospitals/{ids['hospital']}",
                headers=_headers(tokens["hospital_admin"]),
                json={"description": "Updated hospital information"},
            )
            assert own_hospital_update.status_code == 200
            assert own_hospital_update.json()["verification_status"] == "pending"
            hospital_verified = client.patch(
                f"/api/v1/providers/hospitals/{ids['hospital']}/verification",
                headers=_headers(tokens["platform_admin"]),
                json={"verification_status": "verified"},
            )
            assert hospital_verified.status_code == 200
            assert hospital_verified.json()["verified"] is True

            forbidden_hospital = client.patch(
                f"/api/v1/providers/hospitals/{ids['other_hospital']}",
                headers=_headers(tokens["hospital_admin"]),
                json={"description": "cross-tenant change"},
            )
            assert forbidden_hospital.status_code == 403

            forbidden_create = client.post(
                f"/api/v1/providers/hospitals/{ids['other_hospital']}/doctors",
                headers=_headers(tokens["hospital_admin"]),
                json={"full_name": "Dr. New Provider", "specialty": "Neurology"},
            )
            assert forbidden_create.status_code == 403

            forbidden_doctor = client.patch(
                f"/api/v1/providers/doctors/{ids['other_tenant_doctor']}",
                headers=_headers(tokens["hospital_admin"]),
                json={"bio": "unauthorized"},
            )
            assert forbidden_doctor.status_code == 403

            staff_edit = client.patch(
                f"/api/v1/providers/hospitals/{ids['hospital']}",
                headers=_headers(tokens["hospital_staff"]),
                json={"description": "unauthorized"},
            )
            assert staff_edit.status_code == 403

            dashboard = client.get("/api/v1/providers/dashboard", headers=_headers(tokens["hospital_admin"]))
            assert dashboard.status_code == 200
            assert dashboard.json()["doctor_count"] == 2
            assert dashboard.json()["hospital"]["id"] == ids["hospital"]

            created = client.post(
                f"/api/v1/providers/hospitals/{ids['hospital']}/doctors",
                headers=_headers(tokens["hospital_admin"]),
                json={"full_name": "Dr. New Provider", "specialty": "Neurology"},
            )
            assert created.status_code == 201
            assert created.json()["verification_status"] == "pending"
            assert created.json()["verified"] is False
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_doctor_profile_schedule_and_explainable_recommendations():
    engine, tokens, ids = _profile_app()
    try:
        with TestClient(app) as client:
            profile = client.patch(
                f"/api/v1/providers/doctors/{ids['doctor']}",
                headers=_headers(tokens["doctor"]),
                json={
                    "bio": "Cardiology consultation",
                    "languages": ["Hindi", "English"],
                    "specialties": ["Cardiology", "Internal Medicine"],
                    "consultation_types": ["online"],
                    "qualifications": [
                        {"degree": "MD", "institution": "Example Medical College", "completion_year": 2018}
                    ],
                },
            )
            assert profile.status_code == 200
            assert profile.json()["verification_status"] == "pending"
            assert profile.json()["qualifications"][0]["verification_status"] == "pending"
            profile_verified = client.patch(
                f"/api/v1/providers/doctors/{ids['doctor']}/verification",
                headers=_headers(tokens["platform_admin"]),
                json={"verification_status": "verified"},
            )
            assert profile_verified.status_code == 200

            schedule_payload = [
                {
                    "day_of_week": 2,
                    "starts_at": "09:00:00",
                    "ends_at": "12:00:00",
                    "timezone": "Asia/Kolkata",
                    "consultation_type": "online",
                }
            ]
            schedules = client.put(
                f"/api/v1/providers/doctors/{ids['doctor']}/schedules",
                headers=_headers(tokens["doctor"]),
                json=schedule_payload,
            )
            assert schedules.status_code == 200
            assert schedules.json()[0]["day_of_week"] == 2

            overlapping = client.put(
                f"/api/v1/providers/doctors/{ids['doctor']}/schedules",
                headers=_headers(tokens["doctor"]),
                json=schedule_payload + [
                    {
                        "day_of_week": 2,
                        "starts_at": "11:00:00",
                        "ends_at": "13:00:00",
                        "timezone": "Asia/Kolkata",
                        "consultation_type": "online",
                    }
                ],
            )
            assert overlapping.status_code == 422

            recommendation = client.post(
                "/api/v1/providers/recommendations",
                headers=_headers(tokens["doctor"]),
                json={
                    "symptoms": "chest pain",
                    "city": "Raipur",
                    "language": "Hindi",
                    "consultation_type": "online",
                },
            )
            assert recommendation.status_code == 200
            assert recommendation.json()[0]["doctor_id"] == ids["doctor"]
            assert recommendation.json()[0]["score"] > recommendation.json()[1]["score"]
            assert len(recommendation.json()[0]["match_reasons"]) == 4
            assert recommendation.json()[0]["available_slots"] == []
            assert recommendation.json()[0]["schedules"][0]["day_of_week"] == 2
            assert "not real-time" in recommendation.json()[0]["availability_note"]

            profile_detail = client.get(
                f"/api/v1/providers/doctors/{ids['doctor']}",
                headers=_headers(tokens["doctor"]),
            )
            assert profile_detail.status_code == 200
            assert len(profile_detail.json()["schedules"]) == 1

            unauthorized_verification = client.patch(
                f"/api/v1/providers/doctors/{ids['doctor']}/verification",
                headers=_headers(tokens["doctor"]),
                json={"verification_status": "verified"},
            )
            assert unauthorized_verification.status_code == 403
            verified = client.patch(
                f"/api/v1/providers/doctors/{ids['doctor']}/verification",
                headers=_headers(tokens["platform_admin"]),
                json={"verification_status": "verified"},
            )
            assert verified.status_code == 200
            assert verified.json()["verified"] is True

            queue = client.get("/api/v1/providers/review-queue", headers=_headers(tokens["platform_admin"]))
            assert queue.status_code == 200
            qualification_id = queue.json()["qualifications"][0]["id"]
            qualification_status = client.patch(
                f"/api/v1/providers/qualifications/{qualification_id}/verification",
                headers=_headers(tokens["platform_admin"]),
                json={"verification_status": "verified"},
            )
            assert qualification_status.status_code == 200
            assert qualification_status.json()["verification_status"] == "verified"
    finally:
        app.dependency_overrides.clear()
        engine.dispose()

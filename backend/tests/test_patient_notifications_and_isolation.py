from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.providers import Appointment, Doctor, Hospital
from app.models.security import NotificationDelivery
from app.models.user import User
from tests.auth_utils import make_session_token


def _isolation_fixture():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)

    def override_database():
        with factory() as db:
            yield db

    with factory() as db:
        # Create two distinct hospitals
        hospital_a = Hospital(name="Hospital Alpha", city="Delhi", state="DL", verification_status="verified", verified=True)
        hospital_b = Hospital(name="Hospital Beta", city="Mumbai", state="MH", verification_status="verified", verified=True)
        db.add_all([hospital_a, hospital_b])
        db.flush()

        # Create two doctors
        doctor_a = Doctor(
            hospital_id=hospital_a.id,
            full_name="Dr. Alpha Specialist",
            specialty="Cardiology",
            verification_status="verified",
            verified=True,
            fee_minor=50000,
        )
        doctor_b = Doctor(
            hospital_id=hospital_b.id,
            full_name="Dr. Beta Specialist",
            specialty="Neurology",
            verification_status="verified",
            verified=True,
            fee_minor=60000,
        )
        db.add_all([doctor_a, doctor_b])
        db.flush()

        # Create user accounts
        patient_a = User(
            full_name="Patient Alpha",
            email=f"patient_a_{uuid4()}@example.test",
            password_hash="unused",
            role="patient",
        )
        patient_b = User(
            full_name="Patient Beta",
            email=f"patient_b_{uuid4()}@example.test",
            password_hash="unused",
            role="patient",
        )
        admin_a = User(
            full_name="Admin Hospital A",
            email=f"admin_a_{uuid4()}@example.test",
            password_hash="unused",
            role="hospital_admin",
            hospital_id=hospital_a.id,
        )
        admin_b = User(
            full_name="Admin Hospital B",
            email=f"admin_b_{uuid4()}@example.test",
            password_hash="unused",
            role="hospital_admin",
            hospital_id=hospital_b.id,
        )
        doc_user_a = User(
            full_name="Doctor User A",
            email=f"doc_a_{uuid4()}@example.test",
            password_hash="unused",
            role="doctor",
            hospital_id=hospital_a.id,
            doctor_id=doctor_a.id,
        )
        doc_user_b = User(
            full_name="Doctor User B",
            email=f"doc_b_{uuid4()}@example.test",
            password_hash="unused",
            role="doctor",
            hospital_id=hospital_b.id,
            doctor_id=doctor_b.id,
        )
        db.add_all([patient_a, patient_b, admin_a, admin_b, doc_user_a, doc_user_b])
        db.flush()

        # Create appointment for Patient B with Doctor B
        appointment_b = Appointment(
            patient_user_id=patient_b.id,
            doctor_id=doctor_b.id,
            hospital_id=hospital_b.id,
            scheduled_for=datetime.now(timezone.utc) + timedelta(days=3),
            status="scheduled",
        )
        db.add(appointment_b)
        db.flush()

        # Add notification for Patient A
        delivery_a = NotificationDelivery(
            user_id=patient_a.id,
            hospital_id=hospital_a.id,
            channel="email",
            event_type="appointment.scheduled",
            status="sent",
        )
        db.add(delivery_a)
        db.commit()

        tokens = {
            "patient_a": make_session_token(db, patient_a),
            "patient_b": make_session_token(db, patient_b),
            "admin_a": make_session_token(db, admin_a),
            "admin_b": make_session_token(db, admin_b),
            "doctor_a": make_session_token(db, doc_user_a),
            "doctor_b": make_session_token(db, doc_user_b),
        }
        ids = {
            "hospital_a_id": hospital_a.id,
            "hospital_b_id": hospital_b.id,
            "doctor_a_id": doctor_a.id,
            "doctor_b_id": doctor_b.id,
            "patient_a_id": patient_a.id,
            "patient_b_id": patient_b.id,
            "appointment_b_id": appointment_b.id,
        }

    return override_database, tokens, ids


def test_patient_notifications_isolation():
    override_db, tokens, ids = _isolation_fixture()
    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            # Patient A should see their notification
            res_a = client.get(
                "/api/v1/patients/notifications",
                headers={"Authorization": f"Bearer {tokens['patient_a']}"},
            )
            assert res_a.status_code == 200, res_a.text
            data_a = res_a.json()
            assert data_a["total"] == 1
            assert len(data_a["items"]) == 1
            assert data_a["items"][0]["event_type"] == "appointment.scheduled"
            assert data_a["items"][0]["title"] == "Appointment Scheduled"
            assert "अपॉइंटमेंट तय हुआ" in data_a["items"][0]["title_hi"]

            # Patient B should NOT see Patient A's notification
            res_b = client.get(
                "/api/v1/patients/notifications",
                headers={"Authorization": f"Bearer {tokens['patient_b']}"},
            )
            assert res_b.status_code == 200, res_b.text
            data_b = res_b.json()
            assert data_b["total"] == 0
            assert len(data_b["items"]) == 0
    finally:
        app.dependency_overrides.clear()


def test_cross_hospital_isolation():
    override_db, tokens, ids = _isolation_fixture()
    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            # Hospital Admin A attempts to modify Hospital B's details -> Must be Forbidden
            res = client.patch(
                f"/api/v1/providers/hospitals/{ids['hospital_b_id']}",
                json={"description": "Hacked description"},
                headers={"Authorization": f"Bearer {tokens['admin_a']}"},
            )
            assert res.status_code in {403, 404}, f"Expected 403/404, got {res.status_code}"

            # Hospital Admin A attempts to modify Doctor B (belonging to Hospital B) -> Must be Forbidden
            res = client.patch(
                f"/api/v1/providers/doctors/{ids['doctor_b_id']}",
                json={"bio": "Unauthorized bio change"},
                headers={"Authorization": f"Bearer {tokens['admin_a']}"},
            )
            assert res.status_code in {403, 404}, f"Expected 403/404, got {res.status_code}"

            # Doctor A attempts to confirm Doctor B's appointment -> Must be Forbidden
            res = client.post(
                f"/api/v1/providers/appointments/{ids['appointment_b_id']}/confirm",
                headers={"Authorization": f"Bearer {tokens['doctor_a']}"},
            )
            assert res.status_code == 403, f"Expected 403, got {res.status_code}"

            # Patient A attempts to view Patient B's appointment history -> Must be Forbidden
            res = client.get(
                f"/api/v1/providers/appointments/{ids['appointment_b_id']}/history",
                headers={"Authorization": f"Bearer {tokens['patient_a']}"},
            )
            assert res.status_code == 403, f"Expected 403, got {res.status_code}"

            # Patient A attempts to generate invoice for Patient B's appointment -> Must be Forbidden or Not Found (IDOR defense)
            res = client.post(
                f"/api/v1/billing/appointments/{ids['appointment_b_id']}/invoice",
                headers={"Authorization": f"Bearer {tokens['patient_a']}"},
            )
            assert res.status_code in {403, 404}, f"Expected 403 or 404, got {res.status_code}"

    finally:
        app.dependency_overrides.clear()

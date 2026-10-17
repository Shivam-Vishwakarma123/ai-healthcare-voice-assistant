from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth.security import get_current_user, verify_password
from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app
from app.models.billing import Invoice, Payment
from app.models.providers import Appointment, Doctor, Hospital
from app.models.security import AdminBootstrapState
from app.models.user import User
from app.services import payment_service
from tests.auth_utils import make_session_token


@pytest.fixture
def db_sessions():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    test_sessions = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)

    def override_database():
        with test_sessions() as db:
            yield db

    app.dependency_overrides[get_db] = override_database
    yield test_sessions
    app.dependency_overrides.clear()
    engine.dispose()


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_first_admin_bootstrap_requires_token_and_is_one_time(db_sessions, monkeypatch):
    monkeypatch.setattr(settings, "admin_bootstrap_token", "setup-token-" + ("x" * 40))
    with db_sessions() as db:
        db.add(AdminBootstrapState(id=1, completed=False))
        db.commit()

    with TestClient(app) as client:
        assert client.get("/api/v1/auth/bootstrap/status").json() == {
            "setup_available": True,
            "reason": "available",
        }
        payload = {
            "full_name": "First Administrator",
            "email": "platform@example.test",
            "password": "SecureAdmin123!",
            "password_confirmation": "SecureAdmin123!",
            "bootstrap_token": "wrong-token-" + ("y" * 40),
        }
        assert client.post("/api/v1/auth/bootstrap/platform-admin", json=payload).status_code == 403

        payload["bootstrap_token"] = "setup-token-" + ("x" * 40)
        created = client.post("/api/v1/auth/bootstrap/platform-admin", json=payload)
        assert created.status_code == 201
        assert created.json()["user"]["role"] == "platform_admin"
        assert client.get("/api/v1/auth/bootstrap/status").json() == {
            "setup_available": False,
            "reason": "complete",
        }
        assert client.post("/api/v1/auth/bootstrap/platform-admin", json=payload).status_code == 409

        registered = client.post(
            "/api/v1/auth/register",
            json={
                "full_name": "Public Patient",
                "email": "patient@example.test",
                "password": "patient-password",
                "role": "platform_admin",
            },
        )
        assert registered.status_code == 201
        assert registered.json()["user"]["role"] == "patient"

    with db_sessions() as db:
        admin = db.scalar(select(User).where(User.email == "platform@example.test"))
        state = db.get(AdminBootstrapState, 1)
        assert admin is not None and verify_password("SecureAdmin123!", admin.password_hash)
        assert state is not None and state.completed


def test_bootstrap_status_explains_missing_setup_token(db_sessions, monkeypatch):
    monkeypatch.setattr(settings, "admin_bootstrap_token", "")
    with db_sessions() as db:
        db.add(AdminBootstrapState(id=1, completed=False))
        db.commit()

    with TestClient(app) as client:
        assert client.get("/api/v1/auth/bootstrap/status").json() == {
            "setup_available": False,
            "reason": "token_not_configured",
        }


def test_admin_account_creation_is_scoped_and_audited(db_sessions):
    with db_sessions() as db:
        hospital_one = Hospital(name="North Clinic", city="Raipur", state="CG")
        hospital_two = Hospital(name="South Clinic", city="Pune", state="MH")
        db.add_all([hospital_one, hospital_two])
        db.flush()
        platform = User(full_name="Platform", email="platform@test", password_hash="unused", role="platform_admin")
        hospital_admin = User(
            full_name="Hospital Admin",
            email="admin@test",
            password_hash="unused",
            role="hospital_admin",
            hospital_id=hospital_one.id,
        )
        patient = User(full_name="Patient", email="patient@test", password_hash="unused", role="patient")
        db.add_all([platform, hospital_admin, patient])
        doctor_one = Doctor(hospital_id=hospital_one.id, full_name="Dr One", specialty="Medicine")
        doctor_two = Doctor(hospital_id=hospital_two.id, full_name="Dr Two", specialty="Medicine")
        db.add_all([doctor_one, doctor_two])
        db.commit()
        ids = (hospital_one.id, hospital_two.id, doctor_one.id, doctor_two.id)
        tokens = {
            "platform": make_session_token(db, platform),
            "hospital_admin": make_session_token(db, hospital_admin),
            "patient": make_session_token(db, patient),
        }

    with TestClient(app) as client:
        hospital_account = client.post(
            "/api/v1/admin/accounts",
            headers=_headers(tokens["platform"]),
            json={
                "full_name": "Clinic Manager",
                "email": "manager@example.test",
                "role": "hospital_admin",
                "hospital_id": ids[0],
                "password": "SecureAdmin123!",
                "password_confirmation": "SecureAdmin123!",
            },
        )
        assert hospital_account.status_code == 201
        assert hospital_account.json()["hospital_id"] == ids[0]

        doctor_account = {
            "full_name": "Dr One",
            "email": "doctor@example.test",
            "role": "doctor",
            "hospital_id": ids[0],
            "doctor_id": ids[2],
            "password": "SecureDoctor123!",
            "password_confirmation": "SecureDoctor123!",
        }
        assert client.post(
            "/api/v1/admin/accounts",
            headers=_headers(tokens["hospital_admin"]),
            json={**doctor_account, "hospital_id": ids[1], "doctor_id": ids[3]},
        ).status_code == 404
        doctor_created = client.post(
            "/api/v1/admin/accounts",
            headers=_headers(tokens["hospital_admin"]),
            json=doctor_account,
        )
        assert doctor_created.status_code == 201
        assert doctor_created.json()["doctor_id"] == ids[2]

        assert client.post(
            "/api/v1/admin/accounts",
            headers=_headers(tokens["patient"]),
            json={**doctor_account, "email": "patient-escalation@example.test"},
        ).status_code == 403
        assert [row["id"] for row in client.get("/api/v1/admin/hospitals", headers=_headers(tokens["hospital_admin"])).json()] == [ids[0]]


def test_demo_payment_modes_use_only_valid_attempts_and_settle_once(db_sessions, monkeypatch):
    monkeypatch.setattr(settings, "payment_mode", "demo")
    monkeypatch.setattr(settings, "razorpay_key_id", "")
    monkeypatch.setattr(settings, "razorpay_key_secret", "")
    provider_calls = []
    monkeypatch.setattr(payment_service.httpx, "AsyncClient", lambda **_: provider_calls.append("called"))

    with db_sessions() as db:
        hospital = Hospital(name="Demo Clinic", city="Raipur", state="CG")
        db.add(hospital)
        db.flush()
        patient = User(full_name="Demo Patient", email="demo-patient@test", password_hash="unused", role="patient")
        other_patient = User(full_name="Other Patient", email="other-patient@test", password_hash="unused", role="patient")
        staff = User(
            full_name="Clinic Staff",
            email="demo-staff@test",
            password_hash="unused",
            role="hospital_staff",
            hospital_id=hospital.id,
        )
        db.add_all([patient, other_patient, staff])
        db.flush()
        doctor = Doctor(hospital_id=hospital.id, full_name="Dr Demo", specialty="Medicine", fee_minor=12500)
        db.add(doctor)
        db.flush()
        appointment = Appointment(
            patient_user_id=patient.id,
            doctor_id=doctor.id,
            hospital_id=hospital.id,
            scheduled_for=datetime.now(timezone.utc) + timedelta(days=1),
        )
        failed_appointment = Appointment(
            patient_user_id=patient.id,
            doctor_id=doctor.id,
            hospital_id=hospital.id,
            scheduled_for=datetime.now(timezone.utc) + timedelta(days=2),
        )
        cancelled_appointment = Appointment(
            patient_user_id=patient.id,
            doctor_id=doctor.id,
            hospital_id=hospital.id,
            scheduled_for=datetime.now(timezone.utc) + timedelta(days=3),
        )
        db.add_all([appointment, failed_appointment, cancelled_appointment])
        db.commit()
        ids = (patient.id, other_patient.id, staff.id, appointment.id, failed_appointment.id, cancelled_appointment.id)
        tokens = {
            "patient": make_session_token(db, patient),
            "other": make_session_token(db, other_patient),
            "staff": make_session_token(db, staff),
        }

    with TestClient(app) as client:
        assert client.get("/api/v1/billing/config", headers=_headers(tokens["patient"])).json() == {
            "payment_mode": "demo",
            "online_payment_enabled": True,
            "demo_payment_enabled": True,
        }
        assert client.post(
            "/api/v1/billing/checkout",
            headers=_headers(tokens["patient"]),
            json={"invoice_id": 999999},
        ).status_code == 404
        mismatch = client.post(
            "/api/v1/billing/invoices",
            headers=_headers(tokens["staff"]),
            json={
                "patient_user_id": ids[0],
                "appointment_id": ids[3],
                "description": "Consultation",
                "amount_minor": 10,
            },
        )
        assert mismatch.status_code == 422

        invoice = client.post(
            "/api/v1/billing/invoices",
            headers=_headers(tokens["staff"]),
            json={
                "patient_user_id": ids[0],
                "appointment_id": ids[3],
                "description": "Consultation",
                "amount_minor": 12500,
            },
        )
        assert invoice.status_code == 201
        assert invoice.json()["amount_minor"] == 12500
        assert invoice.json()["appointment_id"] == ids[3]
        assert client.post(
            "/api/v1/billing/invoices",
            headers=_headers(tokens["staff"]),
            json={
                "patient_user_id": ids[0],
                "appointment_id": ids[3],
                "description": "Duplicate consultation",
                "amount_minor": 12500,
            },
        ).status_code == 409

        checkout = client.post(
            "/api/v1/billing/checkout",
            headers=_headers(tokens["patient"]),
            json={"invoice_id": invoice.json()["id"]},
        )
        assert checkout.status_code == 200
        assert checkout.json()["mode"] == "demo"
        assert checkout.json()["key_id"] is None
        assert client.post(
            "/api/v1/billing/demo/complete",
            headers=_headers(tokens["other"]),
            json={"order_id": checkout.json()["order_id"], "outcome": "success"},
        ).status_code == 404
        success = client.post(
            "/api/v1/billing/demo/complete",
            headers=_headers(tokens["patient"]),
            json={"order_id": checkout.json()["order_id"], "outcome": "success"},
        )
        assert success.status_code == 200
        assert success.json()["invoice_status"] == "paid"
        replay = client.post(
            "/api/v1/billing/demo/complete",
            headers=_headers(tokens["patient"]),
            json={"order_id": checkout.json()["order_id"], "outcome": "success"},
        )
        assert replay.status_code == 200
        assert replay.json()["transaction_id"] == success.json()["transaction_id"]

        created_invoices = []
        for appointment_id in ids[4:]:
            created = client.post(
                "/api/v1/billing/invoices",
                headers=_headers(tokens["staff"]),
                json={
                    "patient_user_id": ids[0],
                    "appointment_id": appointment_id,
                    "description": "Consultation",
                    "amount_minor": 12500,
                },
            )
            assert created.status_code == 201
            created_invoices.append(created.json())
        for invoice_row, outcome, expected_status in zip(created_invoices, ("failed", "cancelled"), ("failed", "cancelled")):
            pending = client.post(
                "/api/v1/billing/checkout",
                headers=_headers(tokens["patient"]),
                json={"invoice_id": invoice_row["id"]},
            )
            result = client.post(
                "/api/v1/billing/demo/complete",
                headers=_headers(tokens["patient"]),
                json={"order_id": pending.json()["order_id"], "outcome": outcome},
            )
            assert result.status_code == 200
            assert result.json()["payment_status"] == expected_status
            assert result.json()["invoice_status"] == "unpaid"

        history = client.get("/api/v1/billing/payments", headers=_headers(tokens["patient"]))
        assert history.status_code == 200
        assert len(history.json()) == 3
        assert all(row["is_demo"] for row in history.json())
        assert provider_calls == []

    with db_sessions() as db:
        assert db.scalar(select(Invoice.status).where(Invoice.id == invoice.json()["id"])) == "paid"
        assert db.scalar(select(Payment).where(Payment.status == "paid")) is not None

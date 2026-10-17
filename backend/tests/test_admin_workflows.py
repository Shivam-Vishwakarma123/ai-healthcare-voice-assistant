from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
import smtplib
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy import create_engine

from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app
from app.models.billing import Invoice, Payment
from app.models.providers import Appointment, Doctor, Hospital
from app.models.security import AuditLog, AuthSession, NotificationDelivery
from app.models.user import User
from app.services import notification_service
from tests.auth_utils import make_session_token


def _admin_app():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)

    def override_database():
        with factory() as db:
            yield db

    with factory() as db:
        hospital_one = Hospital(name="Admin Hospital One", city="Raipur", state="CG", verification_status="pending")
        hospital_two = Hospital(name="Admin Hospital Two", city="Pune", state="MH", verification_status="verified", verified=True)
        db.add_all([hospital_one, hospital_two])
        db.flush()
        doctor_one = Doctor(
            hospital_id=hospital_one.id,
            full_name="Dr. Admin One",
            specialty="General Medicine",
            verification_status="pending",
            verified=False,
        )
        doctor_two = Doctor(
            hospital_id=hospital_two.id,
            full_name="Dr. Admin Two",
            specialty="Cardiology",
            verification_status="verified",
            verified=True,
        )
        patient = User(
            full_name="Admin Test Patient",
            email=f"patient-{uuid4()}@example.test",
            password_hash="unused",
            role="patient",
        )
        hospital_admin = User(
            full_name="Hospital One Admin",
            email=f"admin1-{uuid4()}@example.test",
            password_hash="unused",
            role="hospital_admin",
            hospital_id=hospital_one.id,
            phone_number="+919876543211",
        )
        other_admin = User(
            full_name="Hospital Two Admin",
            email=f"admin2-{uuid4()}@example.test",
            password_hash="unused",
            role="hospital_admin",
            hospital_id=hospital_two.id,
        )
        staff_one = User(
            full_name="Hospital One Staff",
            email=f"staff1-{uuid4()}@example.test",
            password_hash="unused",
            role="hospital_staff",
            hospital_id=hospital_one.id,
            phone_number="+919876543210",
        )
        staff_two = User(
            full_name="Hospital Two Staff",
            email=f"staff2-{uuid4()}@example.test",
            password_hash="unused",
            role="hospital_staff",
            hospital_id=hospital_two.id,
        )
        platform_admin = User(
            full_name="Platform Admin",
            email=f"platform-{uuid4()}@example.test",
            password_hash="unused",
            role="platform_admin",
        )
        db.add_all([doctor_one, doctor_two, patient, hospital_admin, other_admin, staff_one, staff_two, platform_admin])
        db.flush()
        doctor_account = User(
            full_name="Doctor Account",
            email=f"doctor-{uuid4()}@example.test",
            password_hash="unused",
            role="doctor",
            hospital_id=hospital_one.id,
            doctor_id=doctor_one.id,
        )
        db.add(doctor_account)
        db.flush()
        appointment = Appointment(
            patient_user_id=patient.id,
            doctor_id=doctor_one.id,
            hospital_id=hospital_one.id,
            scheduled_for=datetime.now(timezone.utc) + timedelta(days=2),
            status="scheduled",
        )
        invoice = Invoice(
            owner_user_id=patient.id,
            hospital_id=hospital_one.id,
            invoice_number=f"TEST-{uuid4().hex[:10]}",
            description="Synthetic consultation",
            amount_minor=2500,
            status="unpaid",
        )
        db.add_all([appointment, invoice])
        db.flush()
        payment = Payment(invoice_id=invoice.id, provider_order_id=f"order_{uuid4().hex}", status="failed", failure_code="DECLINED")
        db.add_all([
            payment,
            AuditLog(actor_user_id=staff_one.id, hospital_id=hospital_one.id, action="test.local", resource_type="test"),
            AuditLog(actor_user_id=staff_two.id, hospital_id=hospital_two.id, action="test.other", resource_type="test"),
        ])
        db.commit()
        tokens = {
            "patient": make_session_token(db, patient),
            "hospital_admin": make_session_token(db, hospital_admin),
            "other_admin": make_session_token(db, other_admin),
            "staff": make_session_token(db, staff_one),
            "staff_two": make_session_token(db, staff_two),
            "platform_admin": make_session_token(db, platform_admin),
        }
        ids = {
            "hospital_one": hospital_one.id,
            "hospital_two": hospital_two.id,
            "doctor_one": doctor_one.id,
            "doctor_two": doctor_two.id,
            "patient": patient.id,
            "staff_one": staff_one.id,
            "staff_two": staff_two.id,
            "hospital_admin": hospital_admin.id,
            "platform_admin": platform_admin.id,
            "appointment": appointment.id,
        }
    app.dependency_overrides[get_db] = override_database
    return engine, factory, tokens, ids


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def test_admin_access_tenant_isolation_and_database_aggregates():
    engine, _, tokens, ids = _admin_app()
    try:
        with TestClient(app) as client:
            assert client.get("/api/v1/admin/overview", headers=_headers(tokens["patient"])).status_code == 403
            assert client.get("/api/v1/admin/audit-logs", headers=_headers(tokens["staff"])).status_code == 403

            scoped = client.get("/api/v1/admin/audit-logs", headers=_headers(tokens["hospital_admin"]))
            assert scoped.status_code == 200
            assert all(row["hospital_id"] == ids["hospital_one"] for row in scoped.json()["items"])
            assert "ip_address" not in scoped.text
            assert "user_agent" not in scoped.text

            overview = client.get("/api/v1/admin/overview", headers=_headers(tokens["hospital_admin"]))
            assert overview.status_code == 200
            assert overview.json()["data_source"] == "database"
            assert overview.json()["demo_records"] is False
            assert overview.json()["appointments_by_status"]["scheduled"]["count"] is None
            assert overview.json()["appointments_by_status"]["scheduled"]["suppressed"] is True
            assert overview.json()["payments_by_status"]["failed"]["count"] is None

            global_logs = client.get("/api/v1/admin/audit-logs", headers=_headers(tokens["platform_admin"]))
            assert global_logs.status_code == 200
            assert any(row["hospital_id"] == 2 for row in global_logs.json()["items"])
            appointments = client.get("/api/v1/admin/appointments", headers=_headers(tokens["hospital_admin"]))
            assert appointments.status_code == 200
            assert appointments.json()["total"] == 1
            assert "patient" not in appointments.text.lower()
            payments = client.get("/api/v1/admin/payments", headers=_headers(tokens["hospital_admin"]))
            assert payments.json()["items"][0]["payment_status"] == "failed"
            assert "provider_order_id" not in payments.text
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_platform_admin_account_scope_and_hospital_scoped_activation(monkeypatch):
    engine, factory, tokens, ids = _admin_app()
    monkeypatch.setattr(notification_service.settings, "smtp_host", "")
    monkeypatch.setattr(notification_service.settings, "smtp_from_email", "")
    monkeypatch.setattr(notification_service.settings, "sms_api_url", "")
    monkeypatch.setattr(notification_service.settings, "sms_api_token", "")
    try:
        with TestClient(app) as client:
            platform_users = client.get(
                "/api/v1/admin/users",
                headers=_headers(tokens["platform_admin"]),
            )
            assert platform_users.status_code == 200
            self_account = next(
                item for item in platform_users.json()["items"]
                if item["id"] == ids["platform_admin"]
            )
            assert self_account["role"] == "platform_admin"

            own_role_change = client.patch(
                f"/api/v1/admin/users/{ids['platform_admin']}",
                headers=_headers(tokens["platform_admin"]),
                json={"role": "hospital_staff", "hospital_id": ids["hospital_one"]},
            )
            assert own_role_change.status_code == 409

            invalid_role = client.patch(
                f"/api/v1/admin/users/{ids['staff_one']}",
                headers=_headers(tokens["platform_admin"]),
                json={"role": "invalid_role"},
            )
            assert invalid_role.status_code == 422

            cross_tenant = client.patch(
                f"/api/v1/admin/users/{ids['staff_two']}",
                headers=_headers(tokens["hospital_admin"]),
                json={"is_active": False},
            )
            assert cross_tenant.status_code == 404

            role_escalation = client.patch(
                f"/api/v1/admin/users/{ids['staff_one']}",
                headers=_headers(tokens["hospital_admin"]),
                json={"role": "hospital_admin"},
            )
            assert role_escalation.status_code == 403
            platform_escalation = client.patch(
                f"/api/v1/admin/users/{ids['staff_one']}",
                headers=_headers(tokens["hospital_admin"]),
                json={"role": "platform_admin"},
            )
            assert platform_escalation.status_code == 403

            unauthorized_staff_change = client.patch(
                f"/api/v1/admin/users/{ids['staff_one']}",
                headers=_headers(tokens["staff"]),
                json={"role": "patient"},
            )
            assert unauthorized_staff_change.status_code == 403
            unauthorized_patient_change = client.patch(
                f"/api/v1/admin/users/{ids['patient']}",
                headers=_headers(tokens["patient"]),
                json={"role": "doctor"},
            )
            assert unauthorized_patient_change.status_code == 403

            deactivated = client.patch(
                f"/api/v1/admin/users/{ids['staff_one']}",
                headers=_headers(tokens["hospital_admin"]),
                json={"is_active": False},
            )
            assert deactivated.status_code == 200
            assert deactivated.json()["is_active"] is False

            managed_admin = client.patch(
                f"/api/v1/admin/users/{ids['hospital_admin']}",
                headers=_headers(tokens["platform_admin"]),
                json={"is_active": False},
            )
            assert managed_admin.status_code == 200
            assert managed_admin.json()["role"] == "hospital_admin"
            assert managed_admin.json()["is_active"] is False

            forbidden_provisioning = client.post(
                "/api/v1/admin/accounts",
                headers=_headers(tokens["platform_admin"]),
                json={
                    "full_name": "Unauthorized Staff Account",
                    "email": f"unauthorized-{uuid4()}@example.test",
                    "role": "doctor",
                    "hospital_id": ids["hospital_one"],
                    "doctor_id": ids["doctor_one"],
                    "password": "ValidPassword@2026!",
                    "password_confirmation": "ValidPassword@2026!",
                },
            )
            assert forbidden_provisioning.status_code == 403

            provisioned = client.post(
                "/api/v1/admin/accounts",
                headers=_headers(tokens["platform_admin"]),
                json={
                    "full_name": "New Hospital Admin",
                    "email": f"new-admin-{uuid4()}@example.test",
                    "role": "hospital_admin",
                    "hospital_id": ids["hospital_one"],
                    "password": "ValidPassword@2026!",
                    "password_confirmation": "ValidPassword@2026!",
                },
            )
            assert provisioned.status_code == 201
            assert provisioned.json()["role"] == "hospital_admin"
            assert provisioned.json()["hospital_id"] == ids["hospital_one"]

            with factory() as db:
                account = db.get(User, ids["hospital_admin"])
                assert account.role == "hospital_admin"
                assert db.get(User, ids["platform_admin"]).role == "platform_admin"
                assert db.scalar(select(func.count()).select_from(AuthSession).where(
                    AuthSession.user_id == account.id,
                    AuthSession.revoked_at.is_not(None),
                )) > 0
                delivery_outcomes = {
                    item.channel: item.status
                    for item in db.scalars(
                        select(NotificationDelivery).where(NotificationDelivery.user_id == account.id)
                    ).all()
                }
                assert delivery_outcomes == {"email": "unconfigured", "sms": "unconfigured"}
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_platform_admin_assigns_all_roles_and_revokes_sessions(monkeypatch):
    engine, factory, tokens, ids = _admin_app()
    monkeypatch.setattr(notification_service.settings, "smtp_host", "")
    monkeypatch.setattr(notification_service.settings, "smtp_from_email", "")
    monkeypatch.setattr(notification_service.settings, "sms_api_url", "")
    monkeypatch.setattr(notification_service.settings, "sms_api_token", "")
    try:
        with TestClient(app) as client:
            role_updates = [
                ("patient", {}),
                ("hospital_staff", {"hospital_id": ids["hospital_one"]}),
                ("hospital_admin", {"hospital_id": ids["hospital_one"]}),
                ("doctor", {"hospital_id": ids["hospital_two"], "doctor_id": ids["doctor_two"]}),
                ("platform_admin", {}),
            ]
            for role, scope in role_updates:
                with factory() as db:
                    target = db.get(User, ids["staff_one"])
                    target_session_token = make_session_token(db, target)

                response = client.patch(
                    f"/api/v1/admin/users/{ids['staff_one']}",
                    headers=_headers(tokens["platform_admin"]),
                    json={"role": role, **scope},
                )
                assert response.status_code == 200, response.text
                assert response.json()["role"] == role
                with factory() as db:
                    persisted = db.get(User, ids["staff_one"])
                    assert persisted.role == role
                    if role == "doctor":
                        assert persisted.hospital_id == ids["hospital_two"]
                        assert persisted.doctor_id == ids["doctor_two"]
                assert client.get(
                    "/api/v1/auth/me",
                    headers=_headers(target_session_token),
                ).status_code == 401

            duplicate_doctor = client.patch(
                f"/api/v1/admin/users/{ids['staff_two']}",
                headers=_headers(tokens["platform_admin"]),
                json={
                    "role": "doctor",
                    "hospital_id": ids["hospital_one"],
                    "doctor_id": ids["doctor_one"],
                },
            )
            assert duplicate_doctor.status_code == 409

            with factory() as db:
                own_account = db.get(User, ids["platform_admin"])
                own_session_token = make_session_token(db, own_account)
            own_role_change = client.patch(
                f"/api/v1/admin/users/{ids['platform_admin']}",
                headers=_headers(tokens["platform_admin"]),
                json={"role": "hospital_staff", "hospital_id": ids["hospital_one"]},
            )
            assert own_role_change.status_code == 200
            assert own_role_change.json()["role"] == "hospital_staff"
            with factory() as db:
                assert db.get(User, ids["platform_admin"]).role == "hospital_staff"
                assert db.scalar(
                    select(func.count()).select_from(User).where(
                        User.role == "platform_admin",
                        User.is_active.is_(True),
                    )
                ) >= 1
            # The self-demotion revoked this token; it cannot be reused for privileged actions.
            assert client.get(
                "/api/v1/admin/users",
                headers=_headers(own_session_token),
            ).status_code == 401
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_verification_workflow_is_platform_admin_only_and_audited():
    engine, factory, tokens, ids = _admin_app()
    try:
        with TestClient(app) as client:
            denied = client.patch(
                f"/api/v1/providers/doctors/{ids['doctor_one']}/verification",
                headers=_headers(tokens["hospital_admin"]),
                json={"verification_status": "verified"},
            )
            assert denied.status_code == 403
            verified = client.patch(
                f"/api/v1/providers/doctors/{ids['doctor_one']}/verification",
                headers=_headers(tokens["platform_admin"]),
                json={"verification_status": "verified"},
            )
            assert verified.status_code == 200
            assert verified.json()["verified"] is True
            with factory() as db:
                doctor = db.get(Doctor, ids["doctor_one"])
                assert doctor.verification_status == "verified"
                assert db.scalar(select(func.count()).select_from(AuditLog).where(
                    AuditLog.action == "doctor.verification.update",
                    AuditLog.resource_id == str(ids["doctor_one"]),
                )) == 1
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_notification_provider_failures_are_persisted_without_reverting_admin_action(monkeypatch):
    engine, factory, tokens, ids = _admin_app()
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.test")
    monkeypatch.setattr(settings, "smtp_from_email", "no-reply@example.test")
    monkeypatch.setattr(settings, "sms_api_url", "https://sms.example.test/send")
    monkeypatch.setattr(settings, "sms_api_token", "test-token")

    class FailingSMTP:
        def __init__(self, *_args, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def ehlo(self):
            return None

        def starttls(self):
            return None

        def send_message(self, message):
            assert message["Subject"] == "CareVoice notification"
            assert message.get_content().strip() == "You have a new CareVoice notification. Sign in to your account for details."
            raise smtplib.SMTPException("email gateway unavailable")

    monkeypatch.setattr(notification_service.smtplib, "SMTP", FailingSMTP)
    def unavailable_sms_provider(url, *, json, **_kwargs):
        assert url == "https://sms.example.test/send"
        assert json["message"] == "You have a new CareVoice notification. Sign in to your account for details."
        return httpx.Response(503, request=httpx.Request("POST", url))

    monkeypatch.setattr(notification_service.httpx, "post", unavailable_sms_provider)
    try:
        with TestClient(app) as client:
            response = client.patch(
                f"/api/v1/admin/users/{ids['hospital_admin']}",
                headers=_headers(tokens["platform_admin"]),
                json={"is_active": False},
            )
            assert response.status_code == 200
            assert response.json()["is_active"] is False
            with factory() as db:
                assert db.get(User, ids["hospital_admin"]).is_active is False
                outcomes = db.scalars(
                    select(NotificationDelivery).where(NotificationDelivery.user_id == ids["hospital_admin"])
                ).all()
                assert {item.channel: item.status for item in outcomes} == {"email": "failed", "sms": "failed"}
                assert all(item.failure_code == "failed" for item in outcomes)
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_notification_tracking_failure_does_not_fail_committed_admin_action(monkeypatch):
    engine, factory, tokens, ids = _admin_app()
    monkeypatch.setattr(settings, "smtp_host", "")
    monkeypatch.setattr(settings, "smtp_from_email", "")
    monkeypatch.setattr(settings, "sms_api_url", "")
    monkeypatch.setattr(settings, "sms_api_token", "")

    def fail_notification_commit(session):
        if any(isinstance(item, NotificationDelivery) for item in session.new):
            raise SQLAlchemyError("simulated persistence failure")

    event.listen(Session, "before_commit", fail_notification_commit)
    try:
        with TestClient(app) as client:
            response = client.patch(
                f"/api/v1/admin/users/{ids['staff_one']}",
                headers=_headers(tokens["hospital_admin"]),
                json={"is_active": False},
            )
            assert response.status_code == 200
            assert response.json()["is_active"] is False
            with factory() as db:
                assert db.get(User, ids["staff_one"]).is_active is False
                assert db.scalar(
                    select(func.count()).select_from(NotificationDelivery).where(
                        NotificationDelivery.user_id == ids["staff_one"]
                    )
                ) == 0
    finally:
        event.remove(Session, "before_commit", fail_notification_commit)
        app.dependency_overrides.clear()
        engine.dispose()

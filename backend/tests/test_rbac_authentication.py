from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth.rate_limit import reset_auth_rate_limits
from app.auth.security import ALGORITHM, create_access_token, verify_password
from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app
from app.models.providers import Hospital
from app.models.security import AuthSession
from app.models.user import User
from app.seed_rbac_test_accounts import ACCOUNT_ROLES, seed_rbac_test_accounts

TEST_PASSWORDS = {
    "platform.admin": "PlatformTest@2026!",
    "hospital.admin": "HospitalAdmin@2026!",
    "hospital.staff": "HospitalStaff@2026!",
    "doctor": "DoctorTest@2026!",
    "patient": "PatientTest@2026!",
}


@pytest.fixture
def rbac_client(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
    monkeypatch.setattr(settings, "app_env", "test")
    monkeypatch.setattr(settings, "auth_rate_limit_attempts", 100)

    def override_database():
        with sessions() as db:
            yield db

    app.dependency_overrides[get_db] = override_database
    with sessions.begin() as db:
        assert seed_rbac_test_accounts(db, TEST_PASSWORDS) == {"created": 5, "unchanged": 0}
    reset_auth_rate_limits()
    with TestClient(app) as client:
        yield client, sessions
    app.dependency_overrides.clear()
    engine.dispose()


def test_all_five_roles_login_with_username_and_receive_role_scoped_access(rbac_client):
    client, _ = rbac_client
    for username, (_, role) in ACCOUNT_ROLES.items():
        response = client.post(
            "/api/v1/auth/login",
            json={"username": username, "password": TEST_PASSWORDS[username]},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["user"]["role"] == role
        assert body["user"]["username"] == username
        assert body["access_token"]

        headers = {"Authorization": f"Bearer {body['access_token']}"}
        identity = client.get("/api/v1/auth/me", headers=headers)
        assert identity.status_code == 200
        assert identity.json()["role"] == role

        admin_overview = client.get("/api/v1/admin/overview", headers=headers)
        assert admin_overview.status_code == (
            200 if role in {"platform_admin", "hospital_admin"} else 403
        )

    assert client.get("/api/v1/auth/me").status_code == 401


def test_username_and_email_login_are_supported_and_test_seed_is_idempotent(rbac_client):
    client, sessions = rbac_client
    email_login = client.post(
        "/api/v1/auth/login",
        json={"email": "patient@rbac-test.example.test", "password": TEST_PASSWORDS["patient"]},
    )
    assert email_login.status_code == 200
    assert email_login.json()["user"]["username"] == "patient"

    with sessions.begin() as db:
        assert seed_rbac_test_accounts(
            db,
            {username: "ReplacementPassword@2026!" for username in ACCOUNT_ROLES},
        ) == {"created": 0, "unchanged": 5}
        assert db.scalar(select(func.count()).select_from(User)) == 5
        assert db.scalar(select(func.count()).select_from(Hospital)) == 1
        patient = db.scalar(select(User).where(User.username == "patient"))
        assert patient is not None and patient.is_test_account
        assert patient.password_hash != TEST_PASSWORDS["patient"]
        assert verify_password(TEST_PASSWORDS["patient"], patient.password_hash)
        assert not verify_password("ReplacementPassword@2026!", patient.password_hash)


def test_invalid_and_unknown_username_credentials_have_identical_responses(rbac_client):
    client, _ = rbac_client
    unknown = client.post(
        "/api/v1/auth/login",
        json={"username": "not.a.user", "password": "IncorrectPassword@2026!"},
    )
    assert unknown.status_code == 401
    for username in ACCOUNT_ROLES:
        incorrect = client.post(
            "/api/v1/auth/login",
            json={"username": username, "password": "IncorrectPassword@2026!"},
        )
        assert incorrect.status_code == 401
        assert incorrect.json() == unknown.json()


def test_invalid_expired_and_role_tampered_tokens_are_rejected(rbac_client):
    client, sessions = rbac_client
    user = client.post(
        "/api/v1/auth/login",
        json={"username": "patient", "password": TEST_PASSWORDS["patient"]},
    ).json()["user"]
    with sessions() as db:
        session = db.scalar(select(AuthSession).where(AuthSession.user_id == user["id"]))
        assert session is not None
        session_id = session.id
        user_id = user["id"]

    forged_role = create_access_token(user_id, "platform_admin", session_id)
    expired = jwt.encode(
        {
            "sub": str(user_id),
            "role": "patient",
            "jti": session_id,
            "iat": datetime.now(timezone.utc) - timedelta(minutes=10),
            "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
            "type": "access",
        },
        settings.jwt_secret_key,
        algorithm=ALGORITHM,
    )
    for token in ("malformed.token.value", forged_role, expired):
        response = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 401


def test_register_ignores_client_supplied_role_and_test_account_flags(rbac_client):
    client, sessions = rbac_client
    response = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Role Spoof Attempt",
            "email": "role-spoof@example.test",
            "password": "ValidRegistration@2026!",
            "role": "platform_admin",
            "is_test_account": True,
        },
    )
    assert response.status_code == 201
    assert response.json()["user"]["role"] == "patient"
    assert "is_test_account" not in response.json()["user"]
    with sessions.begin() as db:
        account = db.scalar(select(User).where(User.email == "role-spoof@example.test"))
        assert account is not None
        assert account.role == "patient"
        assert not account.is_test_account


def test_test_account_seeding_refuses_production(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "production")
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db, pytest.raises(RuntimeError, match="development or test"):
            seed_rbac_test_accounts(db, TEST_PASSWORDS)
        with Session(engine) as db:
            assert db.scalar(select(func.count()).select_from(User)) == 0
    finally:
        engine.dispose()

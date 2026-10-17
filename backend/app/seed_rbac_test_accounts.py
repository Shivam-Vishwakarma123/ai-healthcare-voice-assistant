"""Create development-only accounts for exercising all application roles."""

import os
from urllib.parse import urlsplit

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.auth.security import hash_password
from app.core.config import settings
from app.core.database import SessionLocal
from app.models.providers import Doctor, Hospital
from app.models.user import User

HOSPITAL_NAME = "DEVELOPMENT TEST - CareVoice RBAC Hospital"
HOSPITAL_MARKER = "RBAC-TEST-V1: development test data only."
DOCTOR_MARKER = "RBAC-TEST-V1: development test clinician only."
ACCOUNT_ROLES = {
    "platform.admin": ("Platform Admin Test", "platform_admin"),
    "hospital.admin": ("Hospital Admin Test", "hospital_admin"),
    "hospital.staff": ("Hospital Staff Test", "hospital_staff"),
    "doctor": ("Doctor Test", "doctor"),
    "patient": ("Patient Test", "patient"),
}
PASSWORD_ENVIRONMENT_KEYS = {
    username: f"RBAC_TEST_{username.replace('.', '_').upper()}_PASSWORD"
    for username in ACCOUNT_ROLES
}


def _require_development_environment() -> None:
    if settings.app_env.strip().lower() not in {"development", "test"}:
        raise RuntimeError("RBAC test-account seeding is allowed only in development or test.")


def _validate_password(password: str) -> None:
    if (
        len(password) < 12
        or not any(char.islower() for char in password)
        or not any(char.isupper() for char in password)
        or not any(char.isdigit() for char in password)
        or not any(not char.isalnum() for char in password)
    ):
        raise ValueError("Each test-account password must be at least 12 characters and include mixed case, a digit, and a symbol.")


def _get_or_create_test_hospital(db: Session) -> Hospital:
    hospital = db.scalar(select(Hospital).where(Hospital.name == HOSPITAL_NAME))
    if hospital is None:
        hospital = Hospital(
            name=HOSPITAL_NAME,
            city="Development",
            state="Development",
            departments="General Medicine",
            description=HOSPITAL_MARKER,
            verified=True,
            verification_status="verified",
        )
        db.add(hospital)
        db.flush()
    elif hospital.description != HOSPITAL_MARKER:
        raise ValueError("The development RBAC hospital name conflicts with an existing record.")
    return hospital


def _get_or_create_test_doctor(db: Session, hospital: Hospital) -> Doctor:
    doctor = db.scalar(select(Doctor).where(Doctor.bio == DOCTOR_MARKER))
    if doctor is None:
        doctor = Doctor(
            hospital_id=hospital.id,
            full_name="Doctor Test",
            specialty="General Medicine",
            bio=DOCTOR_MARKER,
            specialties=["General Medicine"],
            language_list=["English"],
            consultation_types=["in_person"],
            verified=True,
            is_active=True,
            verification_status="verified",
        )
        db.add(doctor)
        db.flush()
    elif doctor.hospital_id != hospital.id:
        raise ValueError("The development RBAC clinician is assigned to a different hospital.")
    return doctor


def seed_rbac_test_accounts(db: Session, passwords: dict[str, str]) -> dict[str, int]:
    """Add missing role accounts without changing existing account credentials."""
    _require_development_environment()
    if set(passwords) != set(ACCOUNT_ROLES):
        raise ValueError("A password must be provided for each of the five test accounts.")
    for password in passwords.values():
        _validate_password(password)

    hospital = _get_or_create_test_hospital(db)
    doctor = _get_or_create_test_doctor(db, hospital)
    created = 0
    unchanged = 0

    for username, (full_name, role) in ACCOUNT_ROLES.items():
        email = f"{username}@rbac-test.example.test"
        matches = db.scalars(
            select(User).where(or_(User.username == username, User.email == email))
        ).all()
        if matches:
            if len(matches) != 1:
                raise ValueError(f"Development RBAC identity conflicts for username {username}.")
            user = matches[0]
            expected_doctor_id = doctor.id if role == "doctor" else None
            expected_hospital_id = hospital.id if role in {"hospital_admin", "hospital_staff", "doctor"} else None
            if (
                user.username != username
                or user.email != email
                or user.role != role
                or user.hospital_id != expected_hospital_id
                or user.doctor_id != expected_doctor_id
                or not user.is_test_account
            ):
                raise ValueError(f"Development RBAC identity conflicts for username {username}.")
            unchanged += 1
            continue

        db.add(
            User(
                full_name=full_name,
                email=email,
                username=username,
                password_hash=hash_password(passwords[username]),
                role=role,
                hospital_id=hospital.id if role in {"hospital_admin", "hospital_staff", "doctor"} else None,
                doctor_id=doctor.id if role == "doctor" else None,
                is_test_account=True,
            )
        )
        created += 1

    db.flush()
    return {"created": created, "unchanged": unchanged}


def _read_passwords_from_environment() -> dict[str, str]:
    passwords = {
        username: os.environ.get(environment_key, "")
        for username, environment_key in PASSWORD_ENVIRONMENT_KEYS.items()
    }
    if any(not password for password in passwords.values()):
        raise RuntimeError(
            "Set all RBAC_TEST_*_PASSWORD environment variables before seeding; values are never logged."
        )
    return passwords


def _require_local_postgresql() -> None:
    database_url = urlsplit(settings.database_url)
    if (
        database_url.scheme not in {"postgresql", "postgresql+psycopg"}
        or database_url.hostname not in {"localhost", "127.0.0.1", "::1", "db"}
    ):
        raise RuntimeError("RBAC test-account seeding requires a local PostgreSQL database.")


def main() -> None:
    _require_development_environment()
    _require_local_postgresql()
    passwords = _read_passwords_from_environment()
    with SessionLocal.begin() as db:
        counts = seed_rbac_test_accounts(db, passwords)
    print(
        "Development RBAC test-account seed completed: "
        f"{counts['created']} created, {counts['unchanged']} already present."
    )


if __name__ == "__main__":
    main()

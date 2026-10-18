from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.providers import Doctor
from app.models.security import AuthSession
from app.models.user import User

ALGORITHM = "HS256"
ROLE_NAMES = {"patient", "doctor", "hospital_staff", "hospital_admin", "platform_admin"}
password_hash = PasswordHash.recommended()
dummy_password_hash = password_hash.hash("not-a-real-user-password")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return password_hash.verify(password, hashed)
    except (ValueError, TypeError):
        return False


def create_access_token(user_id: int, role: str, session_id: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "role": role,
        "jti": session_id,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_minutes),
        "type": "access",
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=ALGORITHM)


def issue_access_token(db: Session, user: User) -> str:
    now = datetime.now(timezone.utc)
    session = AuthSession(
        id=str(uuid4()),
        user_id=user.id,
        expires_at=now + timedelta(minutes=settings.access_token_minutes),
    )
    db.add(session)
    db.flush()
    return create_access_token(user.id, user.role, session.id)


def revoke_user_sessions(db: Session, user_id: int, now: datetime | None = None) -> None:
    revoked_at = now or datetime.now(timezone.utc)
    sessions = db.scalars(
        select(AuthSession).where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
    ).all()
    for session in sessions:
        session.revoked_at = revoked_at


def get_current_user(
    request: Request,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired access token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[ALGORITHM])
        user_id = int(payload.get("sub", ""))
        session_id = str(payload.get("jti", ""))
        if payload.get("type") != "access" or not session_id:
            raise unauthorized
    except (JWTError, ValueError, TypeError):
        raise unauthorized

    auth_session = db.get(AuthSession, session_id)
    now = datetime.now(timezone.utc)
    if (
        auth_session is None
        or auth_session.user_id != user_id
        or auth_session.revoked_at is not None
        or _as_utc(auth_session.expires_at) <= now
    ):
        raise unauthorized

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise unauthorized
    if payload.get("role") != user.role:
        raise unauthorized
    if user.role not in ROLE_NAMES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This account has no valid application role.")
    if user.role in {"doctor", "hospital_staff", "hospital_admin"} and user.hospital_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This account is not assigned to a hospital.")
    if user.role == "doctor":
        doctor = db.get(Doctor, user.doctor_id) if user.doctor_id is not None else None
        if doctor is None or doctor.hospital_id != user.hospital_id or not doctor.is_active:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "This doctor account is not linked to a clinician profile.")

    request.state.auth_session_id = session_id
    return user


def require_roles(*roles: str):
    invalid = set(roles) - ROLE_NAMES
    if invalid:
        raise ValueError(f"Unknown role(s): {', '.join(sorted(invalid))}")

    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Your account is not permitted to perform this action.")
        return user

    return dependency


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


_as_utc = as_utc

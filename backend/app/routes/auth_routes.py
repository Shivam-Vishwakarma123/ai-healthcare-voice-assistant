import hashlib
import logging
import secrets
import smtplib
import hmac
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.email_validation import normalize_email
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.rate_limit import enforce_auth_rate_limit
from app.auth.security import (
    dummy_password_hash,
    get_current_user,
    hash_password,
    issue_access_token,
    revoke_user_sessions,
    verify_password,
)
from app.core.config import settings
from app.core.database import get_db
from app.models.providers import Doctor
from app.models.security import AdminBootstrapState, AuthSession, PasswordResetToken
from app.models.user import User
from app.services.audit_service import record_audit

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Authentication"])


class RegisterIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    email: str
    password: str = Field(min_length=10, max_length=128)

    @field_validator("full_name")
    @classmethod
    def strip_full_name(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise ValueError("Full name must contain at least 2 non-space characters.")
        return value

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return normalize_email(value)


class BootstrapAdminIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    email: str
    password: str = Field(min_length=12, max_length=128)
    password_confirmation: str = Field(min_length=12, max_length=128)
    bootstrap_token: str = Field(min_length=32, max_length=256)

    @field_validator("full_name")
    @classmethod
    def strip_full_name(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise ValueError("Full name must contain at least 2 non-space characters.")
        return value

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return normalize_email(value)

    @field_validator("password")
    @classmethod
    def validate_strong_password(cls, value: str) -> str:
        if (
            not any(char.islower() for char in value)
            or not any(char.isupper() for char in value)
            or not any(char.isdigit() for char in value)
            or not any(not char.isalnum() for char in value)
        ):
            raise ValueError("Password must include lowercase, uppercase, numeric, and special characters.")
        return value

    @field_validator("password_confirmation")
    @classmethod
    def validate_confirmation(cls, value: str, info) -> str:
        password = info.data.get("password")
        if password is not None and value != password:
            raise ValueError("Password confirmation does not match.")
        return value


class LoginIn(BaseModel):
    email: str | None = None
    username: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
    )
    password: str = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def normalize_login_identifier(self):
        if (self.email is None) == (self.username is None):
            raise ValueError("Provide exactly one email address or username.")
        if self.email is not None:
            self.email = normalize_email(self.email)
        else:
            self.username = self.username.strip().lower()
            if not self.username:
                raise ValueError("Username must not be empty.")
        return self

    @property
    def login_identifier(self) -> str:
        if self.email is not None:
            return self.email
        assert self.username is not None
        return self.username


class PasswordResetRequest(BaseModel):
    email: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return normalize_email(value)


class PasswordResetConfirm(BaseModel):
    token: str = Field(min_length=32, max_length=256)
    new_password: str = Field(min_length=10, max_length=128)


class UserOut(BaseModel):
    id: int
    full_name: str
    email: str
    username: str | None = None
    role: str
    phone_number: str | None = None


class UserContactUpdate(BaseModel):
    phone_number: str | None = Field(default=None, pattern=r"^\+[1-9]\d{7,14}$")


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


class ResetRequestOut(BaseModel):
    message: str


@router.get("/bootstrap/status")
def admin_bootstrap_status(db: Session = Depends(get_db)):
    state = db.get(AdminBootstrapState, 1)
    admin_exists = db.scalar(select(User.id).where(User.role == "platform_admin").limit(1)) is not None
    if state is None:
        reason = "state_unavailable"
    elif state.completed or admin_exists:
        reason = "complete"
    elif len(settings.admin_bootstrap_token) < 32:
        reason = "token_not_configured"
    else:
        reason = "available"
    return {"setup_available": reason == "available", "reason": reason}


@router.post("/bootstrap/platform-admin", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
def bootstrap_platform_admin(
    payload: BootstrapAdminIn,
    request: Request,
    db: Session = Depends(get_db),
):
    normalized_email = str(payload.email).lower()
    enforce_auth_rate_limit(request, normalized_email)
    configured_token = settings.admin_bootstrap_token
    if len(configured_token) < 32 or not hmac.compare_digest(payload.bootstrap_token, configured_token):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Initial administrator setup is not authorized.")

    state = db.scalar(select(AdminBootstrapState).where(AdminBootstrapState.id == 1).with_for_update())
    if state is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Administrator setup state is unavailable.")
    if state.completed or db.scalar(select(User.id).where(User.role == "platform_admin").limit(1)) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Initial administrator setup has already been completed.")

    user = User(
        full_name=payload.full_name,
        email=normalized_email,
        password_hash=hash_password(payload.password),
        role="platform_admin",
    )
    db.add(user)
    state.completed = True
    state.completed_at = datetime.now(timezone.utc)
    try:
        db.flush()
        access_token = issue_access_token(db, user)
        record_audit(db, request, "auth.bootstrap_platform_admin", actor=user, resource_type="user", resource_id=user.id)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with that email already exists.") from exc
    db.refresh(user)
    return _token_response(user, access_token)


@router.post("/register", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterIn, request: Request, db: Session = Depends(get_db)):
    email = str(payload.email).lower()
    enforce_auth_rate_limit(request, email)
    user = User(
        full_name=payload.full_name,
        email=email,
        password_hash=hash_password(payload.password),
        role="patient",
    )
    db.add(user)
    try:
        db.flush()
        access_token = issue_access_token(db, user)
        record_audit(db, request, "auth.register", actor=user, resource_type="user", resource_id=user.id)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered.") from exc
    db.refresh(user)
    return _token_response(user, access_token)


@router.post("/login", response_model=TokenOut)
def login(payload: LoginIn, request: Request, db: Session = Depends(get_db)):
    identifier = payload.login_identifier
    enforce_auth_rate_limit(request, identifier)
    user = db.scalar(
        select(User).where(or_(User.email == identifier, User.username == identifier))
    )
    stored_hash = user.password_hash if user else dummy_password_hash
    password_valid = verify_password(payload.password, stored_hash)
    if not user or not password_valid or not user.is_active:
        record_audit(db, request, "auth.login_failed", actor=user, details={"reason": "invalid_credentials"})
        db.commit()
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    doctor = db.get(Doctor, user.doctor_id) if user.role == "doctor" and user.doctor_id is not None else None
    if user.role not in {"patient", "platform_admin"} and (
        user.hospital_id is None
        or (
            user.role == "doctor"
            and (doctor is None or doctor.hospital_id != user.hospital_id or not doctor.is_active)
        )
    ):
        record_audit(db, request, "auth.login_denied", actor=user, details={"reason": "role_not_provisioned"})
        db.commit()
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This account has not been assigned to its organization.")

    access_token = issue_access_token(db, user)
    record_audit(db, request, "auth.login", actor=user, resource_type="session")
    db.commit()
    return _token_response(user, access_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session_id = getattr(request.state, "auth_session_id", None)
    auth_session = db.get(AuthSession, session_id) if session_id else None
    if auth_session and auth_session.user_id == user.id and auth_session.revoked_at is None:
        auth_session.revoked_at = datetime.now(timezone.utc)
    record_audit(db, request, "auth.logout", actor=user, resource_type="session", resource_id=session_id)
    db.commit()
    return None


@router.post("/password-reset/request", response_model=ResetRequestOut, status_code=status.HTTP_202_ACCEPTED)
def request_password_reset(
    payload: PasswordResetRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    normalized_email = str(payload.email).lower()
    enforce_auth_rate_limit(request, normalized_email)
    if not settings.smtp_host or not settings.smtp_from_email:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Password reset email is not configured. Contact the platform administrator.",
        )

    user = db.scalar(select(User).where(User.email == normalized_email, User.is_active.is_(True)))
    record_audit(
        db,
        request,
        "auth.password_reset_requested",
        actor=user,
        details={"account_found": bool(user)},
    )
    if user is None:
        db.commit()
        return ResetRequestOut(message=_reset_request_message())

    now = datetime.now(timezone.utc)
    for previous in db.scalars(
        select(PasswordResetToken).where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used_at.is_(None),
        )
    ).all():
        previous.used_at = now

    raw_token = secrets.token_urlsafe(48)
    reset_token = PasswordResetToken(
        user_id=user.id,
        token_hash=_token_digest(raw_token),
        expires_at=now + timedelta(minutes=settings.password_reset_minutes),
    )
    db.add(reset_token)
    db.commit()
    try:
        _send_password_reset_email(user.email, raw_token)
    except (OSError, smtplib.SMTPException):
        logger.exception("Password-reset email delivery failed")
        reset_token.used_at = datetime.now(timezone.utc)
        record_audit(
            db,
            request,
            "auth.password_reset_delivery_failed",
            actor=user,
            details={"reason": "smtp_delivery_failed"},
        )
        db.commit()
        return ResetRequestOut(message=_reset_request_message())
    return ResetRequestOut(message=_reset_request_message())


@router.post("/password-reset/confirm", response_model=ResetRequestOut)
def confirm_password_reset(payload: PasswordResetConfirm, request: Request, db: Session = Depends(get_db)):
    enforce_auth_rate_limit(request, "reset-confirm")
    now = datetime.now(timezone.utc)
    reset_token = db.scalar(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == _token_digest(payload.token))
    )
    if (
        reset_token is None
        or reset_token.used_at is not None
        or _as_utc(reset_token.expires_at) <= now
    ):
        record_audit(db, request, "auth.password_reset_failed", details={"reason": "invalid_or_expired_token"})
        db.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Password reset link is invalid or expired.")

    user = db.get(User, reset_token.user_id)
    if user is None or not user.is_active:
        reset_token.used_at = now
        record_audit(db, request, "auth.password_reset_failed", details={"reason": "account_unavailable"})
        db.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Password reset link is invalid or expired.")

    user.password_hash = hash_password(payload.new_password)
    reset_token.used_at = now
    revoke_user_sessions(db, user.id, now)
    for other_token in db.scalars(
        select(PasswordResetToken).where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.id != reset_token.id,
            PasswordResetToken.used_at.is_(None),
        )
    ).all():
        other_token.used_at = now
    record_audit(db, request, "auth.password_reset_completed", actor=user, resource_type="user", resource_id=user.id)
    db.commit()
    return ResetRequestOut(message="Password changed. Sign in with your new password.")


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.patch("/me", response_model=UserOut)
def update_my_contact(
    payload: UserContactUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    user.phone_number = payload.phone_number
    record_audit(
        db,
        request,
        "auth.contact.update",
        actor=user,
        resource_type="user",
        resource_id=user.id,
        details={"phone_number_configured": bool(payload.phone_number)},
    )
    db.commit()
    db.refresh(user)
    return user


def _token_response(user: User, access_token: str) -> dict:
    return {
        "access_token": access_token,
        "expires_in": settings.access_token_minutes * 60,
        "user": user,
    }


def _token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _reset_request_message() -> str:
    return "If an active account matches that address, reset instructions will be sent if email delivery succeeds. If they do not arrive, contact support."


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _send_password_reset_email(email: str, token: str) -> None:
    reset_url = f"{settings.app_public_url.rstrip('/')}/reset-password?{urlencode({'token': token})}"
    message = EmailMessage()
    message["Subject"] = "Reset your CareVoice password"
    message["From"] = settings.smtp_from_email
    message["To"] = email
    message.set_content(
        "A password reset was requested for your CareVoice account.\n\n"
        f"Use this one-time link within {settings.password_reset_minutes} minutes:\n{reset_url}\n\n"
        "If you did not request this, you can ignore this email."
    )
    if settings.smtp_port == 465:
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=10) as server:
            if settings.smtp_username:
                server.login(settings.smtp_username, settings.smtp_password)
            server.send_message(message)
        return
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as server:
        server.ehlo()
        if settings.smtp_starttls:
            server.starttls()
            server.ehlo()
        if settings.smtp_username:
            server.login(settings.smtp_username, settings.smtp_password)
        server.send_message(message)

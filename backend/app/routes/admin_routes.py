from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.email_validation import normalize_email
from app.core.validators import (
    strip_full_name as normalize_full_name,
    validate_password_confirmation,
    validate_strong_password as check_strong_password,
)
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.security import ROLE_NAMES, get_current_user, hash_password, revoke_user_sessions
from app.core.database import get_db
from app.models.billing import Invoice, Payment
from app.models.providers import Appointment, Doctor, Hospital
from app.models.security import AuditLog, NotificationDelivery
from app.models.user import User
from app.services.audit_service import record_audit
from app.services.notification_service import notify_user

router = APIRouter(prefix="/admin", tags=["Administration"])
ADMIN_ROLES = {"platform_admin", "hospital_admin"}


# Validates administrative account modification payloads for role, affiliation, or active state changes.
class UserAdminUpdate(BaseModel):
    role: str | None = None
    hospital_id: int | None = Field(default=None, gt=0)
    doctor_id: int | None = Field(default=None, gt=0)
    is_active: bool | None = None

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str | None) -> str | None:
        if value is not None and value not in ROLE_NAMES:
            raise ValueError("Unsupported account role.")
        return value

    @model_validator(mode="after")
    def require_update(self):
        if not any(getattr(self, field) is not None for field in ("role", "hospital_id", "doctor_id", "is_active")):
            raise ValueError("At least one non-null account update is required.")
        return self


# Validates credential parameters and organization linkages for newly provisioned staff or clinician accounts.
class AccountCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    email: str
    role: str = Field(pattern="^(doctor|hospital_admin)$")
    hospital_id: int = Field(gt=0)
    doctor_id: int | None = Field(default=None, gt=0)
    password: str = Field(min_length=12, max_length=128)
    password_confirmation: str = Field(min_length=12, max_length=128)

    @field_validator("full_name")
    @classmethod
    def strip_full_name(cls, value: str) -> str:
        return normalize_full_name(value)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return normalize_email(value)

    @field_validator("password")
    @classmethod
    def validate_strong_password(cls, value: str) -> str:
        return check_strong_password(value)

    @field_validator("password_confirmation")
    @classmethod
    def validate_confirmation(cls, value: str, info) -> str:
        return validate_password_confirmation(info.data.get("password"), value)

    @model_validator(mode="after")
    def validate_doctor_link(self):
        if (self.role == "doctor") != (self.doctor_id is not None):
            raise ValueError("Doctor accounts must link a doctor profile; hospital administrator accounts must not.")
        return self


# Resolves the caller's hospital tenancy constraint or permits platform-wide visibility for platform admins.
def _admin_hospital(user: User) -> int | None:
    if user.role not in ADMIN_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Administration access is required.")
    return user.hospital_id if user.role == "hospital_admin" else None


# Lists hospitals accessible within the calling administrator's operational jurisdiction.
@router.get("/hospitals")
def list_account_hospitals(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    hospital_id = _admin_hospital(user)
    query = select(Hospital).order_by(Hospital.name.asc(), Hospital.id.asc())
    if hospital_id is not None:
        query = query.where(Hospital.id == hospital_id)
    return [
        {"id": item.id, "name": item.name, "city": item.city, "verification_status": item.verification_status}
        for item in db.scalars(query).all()
    ]


# Lists doctors affiliated with the administrator's authorized hospital or across all facilities.
@router.get("/doctors")
def list_account_doctors(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    hospital_id = _admin_hospital(user)
    query = select(Doctor).order_by(Doctor.full_name.asc(), Doctor.id.asc())
    if hospital_id is not None:
        query = query.where(Doctor.hospital_id == hospital_id)
    return [
        {
            "id": item.id,
            "hospital_id": item.hospital_id,
            "full_name": item.full_name,
            "specialty": item.specialty,
            "is_active": item.is_active,
        }
        for item in db.scalars(query).all()
    ]


# Provisions new doctor or hospital administrator accounts with tenancy boundaries and audit trail recording.
@router.post("/accounts", status_code=status.HTTP_201_CREATED)
def create_managed_account(
    payload: AccountCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    hospital_id = _admin_hospital(user)
    if user.role == "platform_admin" and payload.role != "hospital_admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Platform administrators may only provision hospital administrator accounts.")
    if user.role == "hospital_admin" and payload.role != "doctor":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Hospital administrators may only create doctor accounts.")
    hospital = db.get(Hospital, payload.hospital_id)
    if hospital is None or (hospital_id is not None and hospital.id != hospital_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Hospital not found in your administrative scope.")
    doctor = None
    if payload.role == "doctor":
        doctor = db.get(Doctor, payload.doctor_id)
        if (
            doctor is None
            or doctor.hospital_id != hospital.id
            or not doctor.is_active
        ):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Active clinician profile not found at this hospital.")
    normalized_email = str(payload.email).lower()
    if db.scalar(select(User.id).where(User.email == normalized_email)) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with that email already exists.")
    account = User(
        full_name=payload.full_name,
        email=normalized_email,
        password_hash=hash_password(payload.password),
        role=payload.role,
        hospital_id=hospital.id,
        doctor_id=doctor.id if doctor is not None else None,
    )
    db.add(account)
    try:
        db.flush()
        record_audit(
            db,
            request,
            "account.provisioned",
            actor=user,
            hospital_id=hospital.id,
            resource_type="user",
            resource_id=account.id,
            details={"role": account.role},
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "The account could not be created because it conflicts with an existing account.") from exc
    db.refresh(account)
    return {
        "id": account.id,
        "full_name": account.full_name,
        "email": account.email,
        "role": account.role,
        "hospital_id": account.hospital_id,
        "doctor_id": account.doctor_id,
        "is_active": account.is_active,
        "created_at": account.created_at,
    }


# Suppresses low cell counts (<5) in administrative aggregate statistics to protect patient privacy.
def _visible_count(value: int) -> dict[str, int | bool | None]:
    return {"count": None if 0 < value < 5 else value, "suppressed": 0 < value < 5}


# Aggregates model status counts scoped to a specific facility or the entire platform with privacy masking.
def _status_counts(db: Session, model, column, hospital_id: int | None) -> dict[str, dict[str, int | bool | None]]:
    query = select(column, func.count()).select_from(model)
    if hospital_id is not None:
        if model is Payment:
            query = query.join(Invoice, Invoice.id == Payment.invoice_id).where(Invoice.hospital_id == hospital_id)
        elif model is Hospital:
            query = query.where(Hospital.id == hospital_id)
        else:
            query = query.where(model.hospital_id == hospital_id)
    return {str(key or "unknown"): _visible_count(count) for key, count in db.execute(query.group_by(column))}


# Returns high-level operational statistics including user roles, appointments, payments, and verifications.
@router.get("/overview")
def admin_overview(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    hospital_id = _admin_hospital(user)
    role_query = select(User.role, func.count()).where(User.is_active.is_(True))
    if hospital_id is not None:
        role_query = role_query.where(User.hospital_id == hospital_id)
    user_counts = {
        role: _visible_count(count)
        for role, count in db.execute(role_query.group_by(User.role))
    }
    return {
        "data_source": "database",
        "demo_records": False,
        "users_by_role": user_counts,
        "appointments_by_status": _status_counts(db, Appointment, Appointment.status, hospital_id),
        "payments_by_status": _status_counts(db, Payment, Payment.status, hospital_id),
        "invoices_by_status": _status_counts(db, Invoice, Invoice.status, hospital_id),
        "doctors_by_verification": _status_counts(db, Doctor, Doctor.verification_status, hospital_id),
        "hospitals_by_verification": _status_counts(db, Hospital, Hospital.verification_status, hospital_id),
    }


# Queries managed user accounts with role filtering within the administrator's authorized facility scope.
@router.get("/users")
def list_admin_users(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    role: str | None = Query(default=None, pattern="^(patient|doctor|hospital_staff|hospital_admin|platform_admin)$"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    hospital_id = _admin_hospital(user)
    query = select(User)
    if hospital_id is not None:
        query = query.where(
            User.hospital_id == hospital_id,
            User.role.in_(("doctor", "hospital_staff")),
        )
    if role:
        query = query.where(User.role == role)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    users = db.scalars(query.order_by(User.id.asc()).limit(limit).offset(offset)).all()
    return {
        "items": [
            {
                "id": item.id,
                "full_name": item.full_name,
                "email": item.email,
                "role": item.role,
                "hospital_id": item.hospital_id,
                "doctor_id": item.doctor_id,
                "is_active": item.is_active,
                "created_at": item.created_at,
            }
            for item in users
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


# Updates user roles, facility associations, or active states with last-admin protection and session invalidation.
@router.patch("/users/{user_id}")
def update_admin_user(
    user_id: int,
    payload: UserAdminUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if user.role not in ADMIN_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Administration access is required.")
    if not payload.model_fields_set:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Provide an account role or active-state update.")
    if user.role == "platform_admin":
        locked_platform_admin_ids = db.scalars(
            select(User.id)
            .where(User.role == "platform_admin", User.is_active.is_(True))
            .order_by(User.id.asc())
            .with_for_update()
        ).all()
    else:
        locked_platform_admin_ids = []
    target = db.scalar(select(User).where(User.id == user_id).with_for_update())
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Managed account not found.")
    previous_role = target.role
    previous_hospital_id = target.hospital_id
    previous_doctor_id = target.doctor_id

    if user.role == "hospital_admin":
        if target.hospital_id != user.hospital_id or target.role not in {"doctor", "hospital_staff"}:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Managed account not found in this hospital.")
        if payload.role is not None and payload.role not in {"doctor", "hospital_staff"}:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Hospital administrators may assign only doctor or hospital staff roles.")
        if payload.hospital_id is not None and payload.hospital_id != user.hospital_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Hospital administrators cannot assign accounts to another hospital.")
    else:
        if payload.role is not None and payload.role not in ROLE_NAMES:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Unsupported account role.")

    next_role = payload.role or target.role
    next_hospital_id = payload.hospital_id
    next_doctor_id = payload.doctor_id
    role_changed = payload.role is not None and payload.role != target.role

    if next_role == "doctor":
        if next_doctor_id is None and not role_changed:
            next_doctor_id = target.doctor_id
        doctor = db.scalar(
            select(Doctor).where(Doctor.id == next_doctor_id).with_for_update()
        ) if next_doctor_id is not None else None
        if doctor is None or not doctor.is_active:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Doctor accounts must be linked to an active clinician profile.")
        assigned_doctor = db.scalar(
            select(User.id).where(
                User.doctor_id == doctor.id,
                User.id != target.id,
            )
        )
        if assigned_doctor is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, "This clinician profile is already linked to another account.")
        if next_hospital_id is None:
            next_hospital_id = doctor.hospital_id
        if doctor.hospital_id != next_hospital_id:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Doctor profile and account must belong to the same hospital.")
    elif next_role in {"hospital_admin", "hospital_staff"}:
        if next_hospital_id is None:
            next_hospital_id = target.hospital_id
        if next_hospital_id is None or db.get(Hospital, next_hospital_id) is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Hospital accounts must be assigned to an existing hospital.")
        next_doctor_id = None
    else:
        if payload.hospital_id is not None or payload.doctor_id is not None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Patient and platform administrator accounts cannot be assigned to a hospital or clinician.")
        next_hospital_id = None
        next_doctor_id = None

    if user.role == "hospital_admin" and (
        next_hospital_id != user.hospital_id
        or next_role not in {"doctor", "hospital_staff"}
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Hospital administrators may manage only doctor and staff accounts in their hospital.")

    removes_platform_admin = target.role == "platform_admin" and (
        next_role != "platform_admin" or payload.is_active is False
    )
    if removes_platform_admin and target.is_active:
        if len(locked_platform_admin_ids) <= 1:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "The last active platform administrator cannot be removed or downgraded.",
            )

    target.role = next_role
    target.hospital_id = next_hospital_id
    target.doctor_id = next_doctor_id
    if payload.is_active is not None:
        target.is_active = payload.is_active

    scope_changed = (
        previous_hospital_id != target.hospital_id
        or previous_doctor_id != target.doctor_id
    )
    if role_changed or scope_changed or payload.is_active is not None:
        revoke_user_sessions(db, target.id)
    record_audit(
        db,
        request,
        "admin.user.update",
        actor=user,
        hospital_id=target.hospital_id,
        resource_type="user",
        resource_id=target.id,
        details={
            "previous_role": previous_role,
            "role": target.role,
            "is_active": target.is_active,
        },
    )
    db.commit()
    db.refresh(target)
    notify_user(
        db,
        target,
        "admin.account.updated",
        hospital_id=target.hospital_id,
    )
    return {
        "id": target.id,
        "role": target.role,
        "hospital_id": target.hospital_id,
        "doctor_id": target.doctor_id,
        "is_active": target.is_active,
    }


# Lists consultation appointments across the administrative scope with doctor info and status filters.
@router.get("/appointments")
def list_admin_appointments(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    appointment_status: str | None = Query(default=None, alias="status", max_length=20),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    hospital_id = _admin_hospital(user)
    query = select(Appointment, Doctor).join(Doctor, Doctor.id == Appointment.doctor_id)
    if hospital_id is not None:
        query = query.where(Appointment.hospital_id == hospital_id)
    if appointment_status:
        query = query.where(Appointment.status == appointment_status)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.execute(
        query.order_by(Appointment.scheduled_for.desc(), Appointment.id.desc()).limit(limit).offset(offset)
    ).all()
    return {
        "items": [
            {
                "id": appointment.id,
                "doctor_id": appointment.doctor_id,
                "doctor_name": doctor.full_name,
                "hospital_id": appointment.hospital_id,
                "scheduled_for": appointment.scheduled_for,
                "duration_minutes": appointment.duration_minutes,
                "consultation_type": appointment.consultation_type,
                "status": appointment.status,
            }
            for appointment, doctor in rows
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


# Lists billing payments and associated invoices for financial auditing within the administrative scope.
@router.get("/payments")
def list_admin_payments(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    hospital_id = _admin_hospital(user)
    query = select(Payment, Invoice).join(Invoice, Invoice.id == Payment.invoice_id)
    if hospital_id is not None:
        query = query.where(Invoice.hospital_id == hospital_id)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.execute(
        query.order_by(Payment.created_at.desc(), Payment.id.desc()).limit(limit).offset(offset)
    ).all()
    return {
        "items": [
            {
                "id": payment.id,
                "invoice_id": invoice.id,
                "invoice_number": invoice.invoice_number,
                "amount_minor": invoice.amount_minor,
                "currency": invoice.currency,
                "invoice_status": invoice.status,
                "payment_status": payment.status,
                "failure_code": payment.failure_code,
                "created_at": payment.created_at,
                "updated_at": payment.updated_at,
            }
            for payment, invoice in rows
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


# Queries immutable system audit trail records filtered by action, date range, or facility tenancy.
@router.get("/audit-logs")
def list_admin_audit_logs(
    request: Request,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    action: str | None = Query(default=None, max_length=80),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    hospital_id = _admin_hospital(user)
    query = select(AuditLog)
    if hospital_id is not None:
        query = query.where(AuditLog.hospital_id == hospital_id)
    if action:
        query = query.where(AuditLog.action == action)
    if since:
        query = query.where(AuditLog.created_at >= since)
    if until:
        query = query.where(AuditLog.created_at <= until)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    entries = db.scalars(
        query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(limit).offset(offset)
    ).all()
    record_audit(
        db,
        request,
        "admin.audit_logs.read",
        actor=user,
        hospital_id=hospital_id,
        details={"count": len(entries)},
    )
    db.commit()
    return {
        "items": [
            {
                "id": entry.id,
                "actor_user_id": entry.actor_user_id,
                "hospital_id": entry.hospital_id,
                "action": entry.action,
                "resource_type": entry.resource_type,
                "resource_id": entry.resource_id,
                "created_at": entry.created_at,
            }
            for entry in entries
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


# Lists SMS and email notification dispatch logs with delivery status and failure reasons.
@router.get("/notifications")
def list_admin_notification_deliveries(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    hospital_id = _admin_hospital(user)
    query = select(NotificationDelivery)
    if hospital_id is not None:
        query = query.where(NotificationDelivery.hospital_id == hospital_id)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    deliveries = db.scalars(
        query.order_by(NotificationDelivery.created_at.desc(), NotificationDelivery.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return {
        "items": [
            {
                "id": item.id,
                "user_id": item.user_id,
                "channel": item.channel,
                "event_type": item.event_type,
                "status": item.status,
                "failure_code": item.failure_code,
                "created_at": item.created_at,
            }
            for item in deliveries
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }

import hashlib
import json
import logging
from datetime import date, datetime, timedelta, timezone
from itertools import combinations
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, Request, Response, status
from sqlalchemy import String, and_, delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.auth.security import get_current_user, require_roles
from app.core.config import settings
from app.core.database import get_db
from app.models.providers import (
    Appointment,
    AppointmentCommand,
    AppointmentEvent,
    AppointmentSlotLock,
    Doctor,
    DoctorQualification,
    DoctorSchedule,
    Hospital,
)
from app.models.user import User
from app.schemas.providers import (
    AppointmentCreate,
    AppointmentCancel,
    AppointmentEventRead,
    AppointmentRead,
    AppointmentReschedule,
    AppointmentSlotRead,
    DoctorRead,
    DoctorRecommendation,
    DoctorCreate,
    DoctorPage,
    DoctorProfileUpdate,
    HospitalCreate,
    HospitalPage,
    HospitalProfileUpdate,
    HospitalRead,
    QualificationRead,
    RecommendationRequest,
    ScheduleInput,
    ScheduleRead,
    VerificationUpdate,
)
from app.services.audit_service import record_audit
from app.services.notification_service import notify_user

router = APIRouter(prefix="/providers", tags=["Providers"])
patient_user = require_roles("patient")
logger = logging.getLogger(__name__)

_SPECIALTY_KEYWORDS = {
    "general medicine": ["fever", "cold", "cough", "fatigue", "body pain"],
    "cardiology": ["chest pain", "palpitations", "breathlessness", "pressure"],
    "neurology": ["headache", "dizziness", "weakness", "numbness", "seizure"],
    "gynaecology": ["pregnancy", "period", "bleeding", "pelvic pain"],
    "orthopedics": ["joint", "knee", "back pain", "leg pain", "ankle"],
    "dermatology": ["rash", "skin", "itching", "hair loss"],
    "pediatrics": ["child", "infant", "fever", "vomiting"],
    "psychiatry": ["anxiety", "stress", "panic", "sleep", "depression"],
}

_CONSULTATION_TYPES = {"in_person", "online", "phone"}
_IST = ZoneInfo("Asia/Kolkata")


def _safe_lower(value: str | None) -> str:
    return (value or "").strip().lower()


def _doctor_read(doctor: Doctor, hospital: Hospital | None = None) -> DoctorRead:
    legacy_languages = [item.strip() for item in (doctor.languages or "").split(",") if item.strip()]
    return DoctorRead(
        id=doctor.id,
        hospital_id=doctor.hospital_id,
        full_name=doctor.full_name,
        specialty=doctor.specialty,
        specialties=doctor.specialties or [doctor.specialty],
        languages=doctor.language_list or legacy_languages,
        consultation_types=doctor.consultation_types or [doctor.consultation_mode],
        qualifications=doctor.qualifications,
        schedules=doctor.schedules,
        bio=doctor.bio,
        fee_minor=doctor.fee_minor,
        verified=doctor.verified,
        verification_status=doctor.verification_status,
        is_active=doctor.is_active,
        experience_years=doctor.experience_years,
        consultation_mode=doctor.consultation_mode,
        hospital_name=hospital.name if hospital else None,
    )


def _hospital_read(hospital: Hospital) -> HospitalRead:
    return HospitalRead.model_validate(hospital)


def _hospital_access(user: User, hospital_id: int, db: Session, *, manage: bool = False) -> Hospital:
    hospital = db.get(Hospital, hospital_id)
    if hospital is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Hospital not found.")
    if user.role == "platform_admin":
        return hospital
    if user.role not in ({"hospital_admin"} if manage else {"hospital_admin", "hospital_staff"}) or user.hospital_id != hospital_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Your account cannot access this hospital.")
    return hospital


def _doctor_access(user: User, doctor_id: int, db: Session, *, manage: bool = False) -> Doctor:
    doctor = db.get(Doctor, doctor_id)
    if doctor is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Doctor not found.")
    allowed = (
        user.role == "platform_admin"
        or (user.role == "doctor" and user.doctor_id == doctor_id)
        or (user.role == "hospital_admin" and user.hospital_id == doctor.hospital_id)
    )
    if not allowed:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Your account cannot manage this clinician profile.")
    if manage and user.role == "hospital_staff":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Hospital staff cannot modify clinician profiles.")
    return doctor


def _schedule_conflicts(schedules: list[ScheduleInput]) -> bool:
    for left, right in combinations(schedules, 2):
        if (
            left.day_of_week == right.day_of_week
            and left.is_active
            and right.is_active
            and left.starts_at < right.ends_at
            and right.starts_at < left.ends_at
        ):
            return True
    return False


def _score_for_request(payload: RecommendationRequest, doctor: Doctor, hospital: Hospital | None) -> tuple[float, list[str]]:
    text = _safe_lower(payload.symptoms)
    wanted_specialties = {_safe_lower(payload.specialty)} if payload.specialty else set()
    for specialty, keywords in _SPECIALTY_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            wanted_specialties.add(specialty)
    specialties = {_safe_lower(item) for item in (doctor.specialties or [doctor.specialty])}
    specialties.add(_safe_lower(doctor.specialty))
    reasons: list[str] = []
    weighted_score = 0.0
    total_weight = 0.0
    if wanted_specialties:
        total_weight += settings.provider_match_specialty_weight
        if any(any(item in actual or actual in item for actual in specialties) for item in wanted_specialties):
            weighted_score += settings.provider_match_specialty_weight
            reasons.append(f"Specialty matches: {doctor.specialty}")
        else:
            reasons.append("Specialty does not match the requested criteria")
    if payload.city:
        total_weight += settings.provider_match_city_weight
        if hospital and _safe_lower(payload.city) in _safe_lower(hospital.city):
            weighted_score += settings.provider_match_city_weight
            reasons.append(f"Located in {hospital.city}")
        else:
            reasons.append(f"No matching hospital location for {payload.city}")
    if payload.language:
        total_weight += settings.provider_match_language_weight
        languages = doctor.language_list or [item.strip() for item in (doctor.languages or "").split(",")]
        if any(_safe_lower(payload.language) == _safe_lower(item) for item in languages):
            weighted_score += settings.provider_match_language_weight
            reasons.append(f"Supports {payload.language}")
        else:
            reasons.append(f"{payload.language} is not listed as a supported language")
    if payload.consultation_type:
        total_weight += settings.provider_match_consultation_weight
        modes = doctor.consultation_types or [doctor.consultation_mode]
        if payload.consultation_type in modes:
            weighted_score += settings.provider_match_consultation_weight
            reasons.append(f"Offers {payload.consultation_type.replace('_', ' ')} consultations")
        else:
            reasons.append(f"{payload.consultation_type.replace('_', ' ')} consultation is not listed")
    return (round(weighted_score / total_weight, 2) if total_weight else 0.0), reasons


@router.get("/hospitals", response_model=HospitalPage)
def list_hospitals(
    search: str | None = Query(default=None, max_length=120),
    city: str | None = Query(default=None, max_length=80),
    state: str | None = Query(default=None, max_length=80),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    del user
    query = select(Hospital).where(Hospital.verification_status == "verified")
    if search:
        term = f"%{search.strip()}%"
        query = query.where(
            or_(
                Hospital.name.ilike(term),
                Hospital.departments.ilike(term),
                Hospital.city.ilike(term),
                Hospital.state.ilike(term),
                Hospital.description.ilike(term),
                Hospital.address.ilike(term),
            )
        )
    if city:
        query = query.where(Hospital.city.ilike(f"%{city.strip()}%"))
    if state:
        query = query.where(Hospital.state.ilike(f"%{state.strip()}%"))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(query.order_by(Hospital.name.asc()).offset(offset).limit(limit)).all()
    return HospitalPage(items=[_hospital_read(hospital) for hospital in rows], total=total, limit=limit, offset=offset)


@router.get("/hospitals/{hospital_id}", response_model=HospitalRead)
def get_hospital(hospital_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    del user
    hospital = db.scalar(
        select(Hospital).where(Hospital.id == hospital_id, Hospital.verification_status == "verified")
    )
    if hospital is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Verified hospital not found.")
    return _hospital_read(hospital)


@router.get("/doctors", response_model=DoctorPage)
def list_doctors(
    search: str | None = Query(default=None, max_length=120),
    specialty: str | None = Query(default=None, max_length=120),
    city: str | None = Query(default=None, max_length=80),
    language: str | None = Query(default=None, max_length=80),
    consultation_type: str | None = Query(default=None, pattern="^(in_person|online|phone)$"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    del user
    query = (
        select(Doctor, Hospital)
        .join(Hospital, Hospital.id == Doctor.hospital_id, isouter=True)
        .options(selectinload(Doctor.qualifications), selectinload(Doctor.schedules))
        .where(
            Doctor.is_active.is_(True),
            Doctor.verification_status == "verified",
            or_(Doctor.hospital_id.is_(None), Hospital.verification_status == "verified"),
        )
    )
    if specialty:
        query = query.where(or_(Doctor.specialty.ilike(f"%{specialty.strip()}%"), Doctor.specialties.cast(String).ilike(f"%{specialty.strip()}%")))
    if city:
        query = query.where(Hospital.city.ilike(f"%{city.strip()}%"))
    if language:
        query = query.where(or_(Doctor.languages.ilike(f"%{language.strip()}%"), Doctor.language_list.cast(String).ilike(f"%{language.strip()}%")))
    if consultation_type:
        query = query.where(or_(Doctor.consultation_mode == consultation_type, Doctor.consultation_types.cast(String).ilike(f"%{consultation_type}%")))
    if search:
        term = f"%{search.strip()}%"
        query = query.where(
            or_(
                Doctor.full_name.ilike(term),
                Doctor.specialty.ilike(term),
                Doctor.languages.ilike(term),
                Doctor.specialties.cast(String).ilike(term),
                Doctor.language_list.cast(String).ilike(term),
                Doctor.consultation_types.cast(String).ilike(term),
                Doctor.bio.ilike(term),
                Hospital.name.ilike(term),
                Hospital.city.ilike(term),
                Hospital.state.ilike(term),
            )
        )
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.execute(query.order_by(Doctor.specialty.asc(), Doctor.full_name.asc()).offset(offset).limit(limit)).all()
    return DoctorPage(items=[_doctor_read(doctor, hospital) for doctor, hospital in rows], total=total, limit=limit, offset=offset)


@router.get("/doctors/{doctor_id}", response_model=DoctorRead)
def get_doctor(doctor_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    del user
    row = db.execute(
        select(Doctor, Hospital)
        .join(Hospital, Hospital.id == Doctor.hospital_id, isouter=True)
        .options(selectinload(Doctor.qualifications), selectinload(Doctor.schedules))
        .where(
            Doctor.id == doctor_id,
            Doctor.is_active.is_(True),
            Doctor.verification_status == "verified",
            or_(Doctor.hospital_id.is_(None), Hospital.verification_status == "verified"),
        )
    ).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Verified doctor not found.")
    return _doctor_read(*row)


@router.post("/recommendations", response_model=list[DoctorRecommendation])
def doctor_recommendations(
    payload: RecommendationRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    del user
    query = (
        select(Doctor, Hospital)
        .join(Hospital, Hospital.id == Doctor.hospital_id, isouter=True)
        .options(selectinload(Doctor.schedules))
        .where(
            Doctor.is_active.is_(True),
            Doctor.verification_status == "verified",
            or_(Doctor.hospital_id.is_(None), Hospital.verification_status == "verified"),
        )
    )
    rows = db.execute(query).all()
    candidates: list[DoctorRecommendation] = []
    for doctor, hospital in rows:
        score, reasons = _score_for_request(payload, doctor, hospital)
        if score <= 0:
            continue
        candidates.append(
            DoctorRecommendation(
                doctor_id=doctor.id,
                doctor_name=doctor.full_name,
                specialty=doctor.specialty,
                hospital_name=hospital.name if hospital else None,
                score=score,
                match_reasons=reasons,
                fee_minor=doctor.fee_minor,
                available_slots=[],
                schedules=[schedule for schedule in doctor.schedules if schedule.is_active],
            )
        )
    candidates.sort(key=lambda item: (-item.score, item.doctor_name))
    return candidates[:6]


@router.get("/dashboard")
def provider_dashboard(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if user.role == "doctor":
        doctor = db.scalar(
            select(Doctor)
            .options(selectinload(Doctor.qualifications), selectinload(Doctor.schedules))
            .where(Doctor.id == user.doctor_id)
        )
        if doctor is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Linked doctor profile not found.")
        return {"role": "doctor", "doctor": _doctor_read(doctor, db.get(Hospital, doctor.hospital_id))}
    if user.role in {"hospital_staff", "hospital_admin"}:
        hospital = _hospital_access(user, user.hospital_id, db)
        doctors = db.scalars(
            select(Doctor)
            .options(selectinload(Doctor.qualifications), selectinload(Doctor.schedules))
            .where(Doctor.hospital_id == hospital.id)
            .order_by(Doctor.full_name.asc())
        ).all()
        return {
            "role": user.role,
            "hospital": _hospital_read(hospital),
            "doctors": [_doctor_read(doctor, hospital) for doctor in doctors],
            "doctor_count": len(doctors),
            "appointment_count": db.scalar(select(func.count()).select_from(Appointment).where(Appointment.hospital_id == hospital.id)) or 0,
        }
    if user.role == "platform_admin":
        return {
            "role": user.role,
            "hospital_count": db.scalar(select(func.count()).select_from(Hospital)) or 0,
            "doctor_count": db.scalar(select(func.count()).select_from(Doctor)) or 0,
            "pending_hospitals": db.scalar(select(func.count()).select_from(Hospital).where(Hospital.verification_status == "pending")) or 0,
            "pending_doctors": db.scalar(select(func.count()).select_from(Doctor).where(Doctor.verification_status == "pending")) or 0,
        }
    raise HTTPException(status.HTTP_403_FORBIDDEN, "This workspace is only available to care providers.")


@router.post("/hospitals", response_model=HospitalRead, status_code=status.HTTP_201_CREATED)
def create_hospital(
    payload: HospitalCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("platform_admin")),
):
    hospital = Hospital(**payload.model_dump(), verified=False, verification_status="pending")
    db.add(hospital)
    db.flush()
    record_audit(db, request, "hospital.create", actor=user, resource_type="hospital", resource_id=hospital.id)
    db.commit()
    db.refresh(hospital)
    return _hospital_read(hospital)


@router.patch("/hospitals/{hospital_id}", response_model=HospitalRead)
def update_hospital(
    hospital_id: int,
    payload: HospitalProfileUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("hospital_admin", "platform_admin")),
):
    hospital = _hospital_access(user, hospital_id, db, manage=True)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(hospital, field, value)
    if user.role != "platform_admin" and payload.model_dump(exclude_unset=True):
        hospital.verification_status = "pending"
        hospital.verified = False
    record_audit(db, request, "hospital.update", actor=user, hospital_id=hospital.id, resource_type="hospital", resource_id=hospital.id)
    db.commit()
    db.refresh(hospital)
    return _hospital_read(hospital)


@router.post("/hospitals/{hospital_id}/doctors", response_model=DoctorRead, status_code=status.HTTP_201_CREATED)
def create_doctor(
    hospital_id: int,
    payload: DoctorCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("hospital_admin", "platform_admin")),
):
    _hospital_access(user, hospital_id, db, manage=True)
    doctor = Doctor(
        hospital_id=hospital_id,
        full_name=payload.full_name.strip(),
        specialty=payload.specialty.strip(),
        specialties=[payload.specialty.strip()],
        languages="",
        fee_minor=payload.fee_minor,
        experience_years=payload.experience_years,
        bio=payload.bio.strip(),
        verified=False,
        verification_status="pending",
        is_active=True,
    )
    db.add(doctor)
    db.flush()
    record_audit(db, request, "doctor.create", actor=user, hospital_id=hospital_id, resource_type="doctor", resource_id=doctor.id)
    db.commit()
    db.refresh(doctor)
    return _doctor_read(doctor, db.get(Hospital, hospital_id))


@router.patch("/doctors/{doctor_id}", response_model=DoctorRead)
def update_doctor(
    doctor_id: int,
    payload: DoctorProfileUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("doctor", "hospital_admin", "platform_admin")),
):
    doctor = _doctor_access(user, doctor_id, db, manage=True)
    values = payload.model_dump(exclude_unset=True)
    changed_profile = bool(values)
    qualifications = values.pop("qualifications", None)
    languages = values.pop("languages", None)
    specialties = values.get("specialties")
    consultation_types = values.get("consultation_types")
    if "specialty" in values and not values["specialty"].strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Specialty must not be empty.")
    if consultation_types is not None and (not consultation_types or set(consultation_types) - _CONSULTATION_TYPES):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Select one or more supported consultation types.")
    if languages is not None and any(not language.strip() for language in languages):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Languages must not be empty.")
    if specialties is not None and (not specialties or any(not specialty.strip() for specialty in specialties)):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Provide at least one non-empty specialty.")
    if specialties is not None:
        values["specialties"] = [specialty.strip() for specialty in specialties]
        values["specialty"] = values["specialties"][0]
    elif "specialty" in values:
        values["specialty"] = values["specialty"].strip()
        values["specialties"] = [values["specialty"]]
    for field, value in values.items():
        setattr(doctor, field, value)
    if consultation_types:
        doctor.consultation_mode = consultation_types[0]
    if languages is not None:
        doctor.language_list = [language.strip() for language in languages]
        doctor.languages = ", ".join(doctor.language_list)
    if qualifications is not None:
        doctor.qualifications.clear()
        doctor.qualifications.extend(
            DoctorQualification(**qualification, verification_status="pending")
            for qualification in qualifications
        )
    if user.role != "platform_admin" and changed_profile:
        doctor.verification_status = "pending"
        doctor.verified = False
    record_audit(db, request, "doctor.profile.update", actor=user, hospital_id=doctor.hospital_id, resource_type="doctor", resource_id=doctor.id)
    db.commit()
    db.refresh(doctor)
    return _doctor_read(doctor, db.get(Hospital, doctor.hospital_id))


@router.put("/doctors/{doctor_id}/schedules", response_model=list[ScheduleRead])
def replace_doctor_schedules(
    doctor_id: int,
    schedules: list[ScheduleInput],
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("doctor", "hospital_admin", "platform_admin")),
):
    doctor = _doctor_access(user, doctor_id, db, manage=True)
    if len(schedules) > 50:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "At most 50 recurring schedule entries are allowed.")
    if _schedule_conflicts(schedules):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Recurring schedule entries overlap.")
    doctor.schedules.clear()
    doctor.schedules.extend(DoctorSchedule(**entry.model_dump()) for entry in schedules)
    record_audit(db, request, "doctor.schedule.update", actor=user, hospital_id=doctor.hospital_id, resource_type="doctor", resource_id=doctor.id)
    db.commit()
    db.refresh(doctor)
    return doctor.schedules


@router.patch("/doctors/{doctor_id}/verification", response_model=DoctorRead)
def update_doctor_verification(
    doctor_id: int,
    payload: VerificationUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("platform_admin")),
):
    doctor = db.get(Doctor, doctor_id)
    if doctor is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Doctor not found.")
    doctor.verification_status = payload.verification_status
    doctor.verified = payload.verification_status == "verified"
    record_audit(db, request, "doctor.verification.update", actor=user, hospital_id=doctor.hospital_id, resource_type="doctor", resource_id=doctor.id, details={"verification_status": payload.verification_status})
    db.commit()
    db.refresh(doctor)
    doctor_user = db.scalar(select(User).where(User.doctor_id == doctor.id))
    if doctor_user is not None:
        notify_user(
            db,
            doctor_user,
            "provider.verification.updated",
            hospital_id=doctor.hospital_id,
        )
    return _doctor_read(doctor, db.get(Hospital, doctor.hospital_id))


@router.patch("/hospitals/{hospital_id}/verification", response_model=HospitalRead)
def update_hospital_verification(
    hospital_id: int,
    payload: VerificationUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("platform_admin")),
):
    hospital = db.get(Hospital, hospital_id)
    if hospital is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Hospital not found.")
    hospital.verification_status = payload.verification_status
    hospital.verified = payload.verification_status == "verified"
    record_audit(db, request, "hospital.verification.update", actor=user, hospital_id=hospital.id, resource_type="hospital", resource_id=hospital.id, details={"verification_status": payload.verification_status})
    db.commit()
    db.refresh(hospital)
    hospital_admins = db.scalars(
        select(User).where(User.hospital_id == hospital.id, User.role == "hospital_admin", User.is_active.is_(True))
    ).all()
    for hospital_admin in hospital_admins:
        notify_user(
            db,
            hospital_admin,
            "hospital.verification.updated",
            hospital_id=hospital.id,
        )
    return _hospital_read(hospital)


@router.patch("/qualifications/{qualification_id}/verification", response_model=QualificationRead)
def update_qualification_verification(
    qualification_id: int,
    payload: VerificationUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("platform_admin")),
):
    qualification = db.get(DoctorQualification, qualification_id)
    if qualification is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Qualification not found.")
    qualification.verification_status = payload.verification_status
    record_audit(
        db,
        request,
        "doctor.qualification.verification.update",
        actor=user,
        resource_type="doctor_qualification",
        resource_id=qualification.id,
        details={"verification_status": payload.verification_status},
    )
    db.commit()
    db.refresh(qualification)
    return qualification


@router.get("/review-queue")
def provider_review_queue(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("platform_admin")),
):
    del user
    hospitals = db.scalars(
        select(Hospital).where(Hospital.verification_status == "pending").order_by(Hospital.name.asc())
    ).all()
    doctors = db.execute(
        select(Doctor, Hospital)
        .join(Hospital, Hospital.id == Doctor.hospital_id, isouter=True)
        .options(selectinload(Doctor.qualifications), selectinload(Doctor.schedules))
        .where(Doctor.verification_status == "pending")
        .order_by(Doctor.full_name.asc())
    ).all()
    qualifications = db.execute(
        select(DoctorQualification.id, DoctorQualification.doctor_id, DoctorQualification.degree, DoctorQualification.institution)
        .where(DoctorQualification.verification_status == "pending")
        .order_by(DoctorQualification.id.asc())
    ).all()
    return {
        "hospitals": [_hospital_read(hospital).model_dump() for hospital in hospitals],
        "doctors": [_doctor_read(doctor, hospital).model_dump() for doctor, hospital in doctors],
        "qualifications": [
            {"id": item.id, "doctor_id": item.doctor_id, "degree": item.degree, "institution": item.institution}
            for item in qualifications
        ],
    }


APPOINTMENT_MINUTES = 30
SLOT_BUCKET_SECONDS = APPOINTMENT_MINUTES * 60


def _request_fingerprint(operation: str, values: dict) -> str:
    data = json.dumps({"operation": operation, **values}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _notify_appointment_patient(db: Session, appointment: Appointment, event_type: str) -> None:
    patient = db.get(User, appointment.patient_user_id)
    if patient is None:
        return
    notify_user(
        db,
        patient,
        event_type,
        hospital_id=appointment.hospital_id,
    )


def _same_command(db: Session, actor: User, key: str, operation: str, fingerprint: str) -> Appointment | None:
    command = db.scalar(
        select(AppointmentCommand).where(
            AppointmentCommand.actor_user_id == actor.id,
            AppointmentCommand.idempotency_key == key,
        )
    )
    if command is None:
        return None
    if command.operation != operation or command.request_fingerprint != fingerprint:
        raise HTTPException(status.HTTP_409_CONFLICT, "This idempotency key was already used for a different request.")
    appointment = db.get(Appointment, command.appointment_id)
    if appointment is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "The appointment for this idempotency key no longer exists.")
    return appointment


def _validate_booking_target(db: Session, doctor_id: int, scheduled_for: datetime, consultation_type: str) -> Doctor:
    doctor = db.scalar(
        select(Doctor)
        .options(selectinload(Doctor.schedules))
        .where(
            Doctor.id == doctor_id,
            Doctor.is_active.is_(True),
            Doctor.verification_status == "verified",
        )
    )
    if doctor is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Verified active doctor not found.")
    if doctor.hospital_id:
        hospital = db.get(Hospital, doctor.hospital_id)
        if hospital is None or hospital.verification_status != "verified":
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Verified hospital not found.")
    start = scheduled_for.astimezone(timezone.utc)
    if start <= datetime.now(timezone.utc):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Appointment time must be in the future.")
    supported_types = doctor.consultation_types or [doctor.consultation_mode]
    if consultation_type not in supported_types:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "This consultation type is not offered by the doctor.")
    if not _fits_published_schedule(start, doctor, consultation_type):
        raise HTTPException(status.HTTP_409_CONFLICT, "This time is outside the doctor's published schedule.")
    return doctor


def _fits_published_schedule(start: datetime, doctor: Doctor, consultation_type: str) -> bool:
    for schedule in doctor.schedules:
        if not schedule.is_active or schedule.consultation_type != consultation_type:
            continue
        local_start = start.astimezone(ZoneInfo(schedule.timezone))
        local_end = local_start + timedelta(minutes=APPOINTMENT_MINUTES)
        slot_offset = (
            local_start.hour * 60 + local_start.minute
            - (schedule.starts_at.hour * 60 + schedule.starts_at.minute)
        )
        if (
            local_start.date() == local_end.date()
            and local_start.weekday() == schedule.day_of_week
            and slot_offset >= 0
            and slot_offset % APPOINTMENT_MINUTES == 0
            and local_start.second == 0
            and local_start.microsecond == 0
            and schedule.starts_at <= local_start.time().replace(tzinfo=None)
            and local_end.time().replace(tzinfo=None) <= schedule.ends_at
        ):
            return True
    return False


def _appointment_read(db: Session, appointment: Appointment) -> AppointmentRead:
    doctor = db.get(Doctor, appointment.doctor_id)
    hospital = db.get(Hospital, appointment.hospital_id) if appointment.hospital_id else None
    return AppointmentRead(
        id=appointment.id,
        patient_user_id=appointment.patient_user_id,
        doctor_id=appointment.doctor_id,
        hospital_id=appointment.hospital_id,
        scheduled_for=_as_utc(appointment.scheduled_for),
        duration_minutes=appointment.duration_minutes,
        consultation_type=appointment.consultation_type,
        status=appointment.status,
        notes=appointment.notes,
        created_at=_as_utc(appointment.created_at),
        doctor_name=doctor.full_name if doctor else None,
        hospital_name=hospital.name if hospital else None,
        specialty=doctor.specialty if doctor else None,
    )


def _appointment_access(db: Session, appointment_id: int, user: User, *, lock: bool = False) -> Appointment:
    query = select(Appointment).where(Appointment.id == appointment_id)
    if lock:
        query = query.with_for_update()
    appointment = db.scalar(query)
    if appointment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Appointment not found.")
    allowed = (
        (user.role == "patient" and appointment.patient_user_id == user.id)
        or (user.role == "doctor" and appointment.doctor_id == user.doctor_id)
        or (user.role in {"hospital_staff", "hospital_admin"} and appointment.hospital_id == user.hospital_id)
        or user.role == "platform_admin"
    )
    if not allowed:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Your account cannot access this appointment.")
    return appointment


def _release_appointment_slots(db: Session, appointment: Appointment) -> None:
    db.execute(delete(AppointmentSlotLock).where(AppointmentSlotLock.appointment_id == appointment.id))


def _claim_appointment_slot(db: Session, appointment: Appointment, start: datetime) -> None:
    epoch_start = int(start.timestamp())
    epoch_end = epoch_start + appointment.duration_minutes * 60
    bucket_start = epoch_start // SLOT_BUCKET_SECONDS * SLOT_BUCKET_SECONDS
    while bucket_start < epoch_end:
        db.add(
            AppointmentSlotLock(
                appointment_id=appointment.id,
                doctor_id=appointment.doctor_id,
                slot_start=datetime.fromtimestamp(bucket_start, timezone.utc),
            )
        )
        bucket_start += SLOT_BUCKET_SECONDS


@router.get("/doctors/{doctor_id}/available-slots", response_model=list[AppointmentSlotRead])
def list_available_slots(
    doctor_id: int,
    day: date = Query(...),
    consultation_type: str = Query(default="in_person", pattern="^(in_person|online|phone)$"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    del user
    doctor = db.scalar(
        select(Doctor)
        .options(selectinload(Doctor.schedules))
        .where(
            Doctor.id == doctor_id,
            Doctor.is_active.is_(True),
            Doctor.verification_status == "verified",
        )
    )
    if doctor is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Verified active doctor not found.")
    if doctor.hospital_id:
        hospital = db.get(Hospital, doctor.hospital_id)
        if hospital is None or hospital.verification_status != "verified":
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Verified hospital not found.")
    starts: set[datetime] = set()
    for schedule in doctor.schedules:
        if not schedule.is_active or schedule.consultation_type != consultation_type:
            continue
        zone = ZoneInfo(schedule.timezone)
        for local_day in (day - timedelta(days=1), day, day + timedelta(days=1)):
            if local_day.weekday() != schedule.day_of_week:
                continue
            local_start = datetime.combine(local_day, schedule.starts_at, tzinfo=zone)
            local_end = datetime.combine(local_day, schedule.ends_at, tzinfo=zone)
            cursor = local_start
            while cursor + timedelta(minutes=APPOINTMENT_MINUTES) <= local_end:
                utc_start = cursor.astimezone(timezone.utc)
                if utc_start.astimezone(_IST).date() == day and utc_start > datetime.now(timezone.utc):
                    starts.add(utc_start)
                cursor += timedelta(minutes=APPOINTMENT_MINUTES)
    if not starts:
        return []
    candidate_buckets = {
        datetime.fromtimestamp(int(start.timestamp()) // SLOT_BUCKET_SECONDS * SLOT_BUCKET_SECONDS, timezone.utc)
        for start in starts
    }
    occupied = {
        slot.replace(tzinfo=timezone.utc) if slot.tzinfo is None else slot.astimezone(timezone.utc)
        for slot in db.scalars(
            select(AppointmentSlotLock.slot_start).where(
                AppointmentSlotLock.doctor_id == doctor_id,
                AppointmentSlotLock.slot_start.in_(list(candidate_buckets)),
            )
        ).all()
    }
    return [
        AppointmentSlotRead(
            scheduled_for=start,
            local_date=start.astimezone(_IST).date(),
            local_time=start.astimezone(_IST).time().replace(tzinfo=None),
            timezone="Asia/Kolkata",
            consultation_type=consultation_type,
        )
        for start in sorted(starts)
        if datetime.fromtimestamp(int(start.timestamp()) // SLOT_BUCKET_SECONDS * SLOT_BUCKET_SECONDS, timezone.utc) not in occupied
    ]


@router.get("/appointments", response_model=list[AppointmentRead])
def list_appointments(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = select(Appointment, Doctor, Hospital).join(Doctor, Doctor.id == Appointment.doctor_id).join(Hospital, Hospital.id == Appointment.hospital_id, isouter=True)
    if user.role == "patient":
        query = query.where(Appointment.patient_user_id == user.id)
    elif user.role == "doctor":
        query = query.where(Appointment.doctor_id == user.doctor_id)
    elif user.role in {"hospital_staff", "hospital_admin"}:
        query = query.where(Appointment.hospital_id == user.hospital_id)
    elif user.role != "platform_admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Your account cannot access appointments.")
    rows = db.execute(query.order_by(Appointment.scheduled_for.desc())).all()
    record_audit(db, request, "appointment.list", actor=user, details={"count": len(rows)})
    db.commit()
    return [
        AppointmentRead(
            id=appointment.id,
            patient_user_id=appointment.patient_user_id,
            doctor_id=appointment.doctor_id,
            hospital_id=appointment.hospital_id,
            scheduled_for=_as_utc(appointment.scheduled_for),
            duration_minutes=appointment.duration_minutes,
            consultation_type=appointment.consultation_type,
            status=appointment.status,
            notes=appointment.notes,
            created_at=_as_utc(appointment.created_at),
            doctor_name=doctor.full_name,
            hospital_name=hospital.name if hospital else None,
            specialty=doctor.specialty,
        )
        for appointment, doctor, hospital in rows
    ]


@router.post("/appointments", response_model=AppointmentRead, status_code=status.HTTP_201_CREATED)
def create_appointment(
    payload: AppointmentCreate,
    request: Request,
    response: Response,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=16, max_length=128, pattern="^[A-Za-z0-9._:-]+$"),
    db: Session = Depends(get_db),
    user: User = Depends(patient_user),
):
    start = payload.scheduled_for.astimezone(timezone.utc)
    fingerprint = _request_fingerprint(
        "book",
        {
            "doctor_id": payload.doctor_id,
            "scheduled_for": start.isoformat(),
            "consultation_type": payload.consultation_type,
            "notes": payload.notes.strip() if payload.notes else None,
        },
    )
    replay = _same_command(db, user, idempotency_key, "book", fingerprint)
    if replay:
        response.status_code = status.HTTP_200_OK
        return _appointment_read(db, replay)

    doctor = _validate_booking_target(db, payload.doctor_id, start, payload.consultation_type)
    appointment = Appointment(
        patient_user_id=user.id,
        doctor_id=doctor.id,
        hospital_id=doctor.hospital_id,
        scheduled_for=start,
        duration_minutes=APPOINTMENT_MINUTES,
        consultation_type=payload.consultation_type,
        notes=payload.notes.strip() if payload.notes else None,
        status="scheduled",
    )
    db.add(appointment)
    try:
        db.flush()
        _claim_appointment_slot(db, appointment, start)
        db.add(
            AppointmentCommand(
                actor_user_id=user.id,
                idempotency_key=idempotency_key,
                operation="book",
                request_fingerprint=fingerprint,
                appointment_id=appointment.id,
            )
        )
        db.add(
            AppointmentEvent(
                appointment_id=appointment.id,
                actor_user_id=user.id,
                event_type="booked",
                to_status="scheduled",
                scheduled_for=start,
            )
        )
        record_audit(db, request, "appointment.create", actor=user, hospital_id=appointment.hospital_id, resource_type="appointment", resource_id=appointment.id)
        db.commit()
        db.refresh(appointment)
        logger.info("Appointment booking completed.")
        _notify_appointment_patient(db, appointment, "appointment.booked")
    except IntegrityError as exc:
        db.rollback()
        logger.warning("Appointment booking conflicted with an existing command or slot.")
        replay = _same_command(db, user, idempotency_key, "book", fingerprint)
        if replay:
            response.status_code = status.HTTP_200_OK
            return _appointment_read(db, replay)
        raise HTTPException(status.HTTP_409_CONFLICT, "That appointment time was just booked. Choose another available slot.") from exc
    return _appointment_read(db, appointment)


@router.post("/appointments/{appointment_id}/confirm", response_model=AppointmentRead)
def confirm_appointment(
    appointment_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("doctor", "hospital_staff", "hospital_admin", "platform_admin")),
):
    appointment = _appointment_access(db, appointment_id, user, lock=True)
    if appointment.status != "scheduled":
        raise HTTPException(status.HTTP_409_CONFLICT, f"Cannot confirm an appointment in the '{appointment.status}' state.")
    if _as_utc(appointment.scheduled_for) <= datetime.now(timezone.utc):
        raise HTTPException(status.HTTP_409_CONFLICT, "Past appointments cannot be confirmed.")
    appointment.status = "confirmed"
    db.add(
        AppointmentEvent(
            appointment_id=appointment.id,
            actor_user_id=user.id,
            event_type="confirmed",
            from_status="scheduled",
            to_status="confirmed",
            scheduled_for=_as_utc(appointment.scheduled_for),
        )
    )
    record_audit(db, request, "appointment.confirm", actor=user, hospital_id=appointment.hospital_id, resource_type="appointment", resource_id=appointment.id)
    db.commit()
    db.refresh(appointment)
    logger.info("Appointment confirmation completed.")
    _notify_appointment_patient(db, appointment, "appointment.confirmed")
    return _appointment_read(db, appointment)


@router.patch("/appointments/{appointment_id}/cancel", response_model=AppointmentRead)
def cancel_appointment(
    appointment_id: int,
    request: Request,
    payload: AppointmentCancel = Body(default=AppointmentCancel()),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    appointment = _appointment_access(db, appointment_id, user, lock=True)
    if appointment.status not in {"scheduled", "confirmed"}:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Cannot cancel an appointment in the '{appointment.status}' state.")
    if _as_utc(appointment.scheduled_for) <= datetime.now(timezone.utc):
        raise HTTPException(status.HTTP_409_CONFLICT, "Past appointments cannot be cancelled.")
    previous_status = appointment.status
    appointment.status = "cancelled"
    _release_appointment_slots(db, appointment)
    db.add(
        AppointmentEvent(
            appointment_id=appointment.id,
            actor_user_id=user.id,
            event_type="cancelled",
            from_status=previous_status,
            to_status="cancelled",
            scheduled_for=_as_utc(appointment.scheduled_for),
            reason=payload.reason,
        )
    )
    record_audit(db, request, "appointment.cancel", actor=user, hospital_id=appointment.hospital_id, resource_type="appointment", resource_id=appointment.id)
    db.commit()
    db.refresh(appointment)
    _notify_appointment_patient(db, appointment, "appointment.cancelled")
    return _appointment_read(db, appointment)


@router.patch("/appointments/{appointment_id}/reschedule", response_model=AppointmentRead)
def reschedule_appointment(
    appointment_id: int,
    payload: AppointmentReschedule,
    request: Request,
    response: Response,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=16, max_length=128, pattern="^[A-Za-z0-9._:-]+$"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    new_start = payload.scheduled_for.astimezone(timezone.utc)
    fingerprint = _request_fingerprint(
        "reschedule",
        {
            "appointment_id": appointment_id,
            "scheduled_for": new_start.isoformat(),
            "consultation_type": payload.consultation_type,
            "reason": payload.reason,
        },
    )
    appointment = _appointment_access(db, appointment_id, user, lock=True)
    replay = _same_command(db, user, idempotency_key, "reschedule", fingerprint)
    if replay:
        response.status_code = status.HTTP_200_OK
        return _appointment_read(db, replay)
    if appointment.status not in {"scheduled", "confirmed"}:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Cannot reschedule an appointment in the '{appointment.status}' state.")
    if _as_utc(appointment.scheduled_for) <= datetime.now(timezone.utc):
        raise HTTPException(status.HTTP_409_CONFLICT, "Past appointments cannot be rescheduled.")
    if new_start == _as_utc(appointment.scheduled_for):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Choose a different appointment time.")
    doctor = _validate_booking_target(db, appointment.doctor_id, new_start, payload.consultation_type)
    previous_start = _as_utc(appointment.scheduled_for)
    previous_status = appointment.status
    appointment.scheduled_for = new_start
    appointment.consultation_type = payload.consultation_type
    appointment.status = "scheduled"
    _release_appointment_slots(db, appointment)
    try:
        _claim_appointment_slot(db, appointment, new_start)
        db.add(
            AppointmentCommand(
                actor_user_id=user.id,
                idempotency_key=idempotency_key,
                operation="reschedule",
                request_fingerprint=fingerprint,
                appointment_id=appointment.id,
            )
        )
        db.add(
            AppointmentEvent(
                appointment_id=appointment.id,
                actor_user_id=user.id,
                event_type="rescheduled",
                from_status=previous_status,
                to_status="scheduled",
                previous_scheduled_for=previous_start,
                scheduled_for=new_start,
                reason=payload.reason,
            )
        )
        record_audit(db, request, "appointment.reschedule", actor=user, hospital_id=appointment.hospital_id, resource_type="appointment", resource_id=appointment.id)
        db.commit()
        db.refresh(appointment)
        _notify_appointment_patient(db, appointment, "appointment.rescheduled")
    except IntegrityError as exc:
        db.rollback()
        replay = _same_command(db, user, idempotency_key, "reschedule", fingerprint)
        if replay:
            response.status_code = status.HTTP_200_OK
            return _appointment_read(db, replay)
        raise HTTPException(status.HTTP_409_CONFLICT, "That appointment time was just booked. Choose another available slot.") from exc
    return _appointment_read(db, appointment)


@router.get("/appointments/{appointment_id}/history", response_model=list[AppointmentEventRead])
def appointment_history(
    appointment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    appointment = _appointment_access(db, appointment_id, user)
    events = db.scalars(
        select(AppointmentEvent)
        .where(AppointmentEvent.appointment_id == appointment.id)
        .order_by(AppointmentEvent.created_at.asc(), AppointmentEvent.id.asc())
    ).all()
    return [
        AppointmentEventRead(
            id=event.id,
            appointment_id=event.appointment_id,
            actor_user_id=event.actor_user_id,
            event_type=event.event_type,
            from_status=event.from_status,
            to_status=event.to_status,
            previous_scheduled_for=_as_utc(event.previous_scheduled_for) if event.previous_scheduled_for else None,
            scheduled_for=_as_utc(event.scheduled_for) if event.scheduled_for else None,
            reason=event.reason,
            created_at=_as_utc(event.created_at),
        )
        for event in events
    ]

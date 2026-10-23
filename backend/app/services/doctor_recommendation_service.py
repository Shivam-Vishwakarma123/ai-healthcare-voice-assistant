from __future__ import annotations

import logging
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.models.providers import Doctor, Hospital
from app.schemas.providers import DoctorRecommendation, RecommendationRequest, ScheduleRead

logger = logging.getLogger(__name__)

_SPECIALTY_KEYWORDS = {
    "general medicine": ["fever", "cold", "cough", "fatigue", "body pain", "weakness"],
    "cardiology": ["chest pain", "palpitations", "breathlessness", "pressure in chest", "cardiac", "heart"],
    "pulmonology": ["cough", "asthma", "wheezing", "shortness of breath", "breathing difficulty", "lungs"],
    "neurology": ["headache", "dizziness", "weakness", "numbness", "seizure", "stroke", "paralysis"],
    "gynaecology": ["pregnancy", "period", "bleeding", "pelvic pain", "menstrual", "pregnant"],
    "orthopedics": ["joint", "knee", "back pain", "leg pain", "ankle", "bone", "fracture", "sprain"],
    "dermatology": ["rash", "skin", "itching", "hair loss", "allergy", "hives"],
    "pediatrics": ["child", "infant", "baby", "newborn", "toddler"],
    "psychiatry": ["anxiety", "stress", "panic", "sleep", "depression", "mental health", "distress"],
    "ent": ["ear", "nose", "throat", "sinus", "hearing", "nasal"],
}


# Normalizes input strings by stripping whitespace and converting to lowercase.
def _safe_lower(value: str | None) -> str:
    return (value or "").strip().lower()


# Computes a weighted match score and explanation list comparing a doctor to patient requirements.
def score_doctor_for_request(
    symptoms: str,
    specialty: str | None,
    city: str | None,
    language: str | None,
    consultation_type: str | None,
    doctor: Doctor,
    hospital: Hospital | None,
) -> tuple[float, list[str]]:
    text = _safe_lower(symptoms)
    wanted_specialties = {_safe_lower(specialty)} if specialty else set()
    for spec, keywords in _SPECIALTY_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            wanted_specialties.add(spec)

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

    if city:
        total_weight += settings.provider_match_city_weight
        if hospital and _safe_lower(city) in _safe_lower(hospital.city):
            weighted_score += settings.provider_match_city_weight
            reasons.append(f"Located in {hospital.city}")
        else:
            reasons.append(f"No matching hospital location for {city}")

    if language:
        total_weight += settings.provider_match_language_weight
        languages = doctor.language_list or [item.strip() for item in (doctor.languages or "").split(",") if item.strip()]
        if any(_safe_lower(language) == _safe_lower(item) for item in languages):
            weighted_score += settings.provider_match_language_weight
            reasons.append(f"Supports {language}")
        else:
            reasons.append(f"{language} is not listed as a supported language")

    if consultation_type:
        total_weight += settings.provider_match_consultation_weight
        modes = doctor.consultation_types or [doctor.consultation_mode]
        if consultation_type in modes:
            weighted_score += settings.provider_match_consultation_weight
            reasons.append(f"Offers {consultation_type.replace('_', ' ')} consultations")
        else:
            reasons.append(f"{consultation_type.replace('_', ' ')} consultation is not listed")

    score = round(weighted_score / total_weight, 2) if total_weight else 0.0
    return score, reasons


# Queries verified active doctors and returns top-ranked clinical recommendations.
def get_verified_doctor_recommendations(
    db: Session,
    *,
    symptoms: str,
    specialty: str | None = None,
    city: str | None = None,
    language: str | None = None,
    consultation_type: str | None = None,
    limit: int = 4,
) -> list[DoctorRecommendation]:
    """Retrieve actual verified, active doctor records with explainable criteria."""
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
        score, reasons = score_doctor_for_request(
            symptoms=symptoms,
            specialty=specialty,
            city=city,
            language=language,
            consultation_type=consultation_type,
            doctor=doctor,
            hospital=hospital,
        )
        if score <= 0 and (specialty or city):
            continue
        # Baseline score for verified active doctors if no strict filter failed
        final_score = max(score, 0.5 if not (specialty or city) else score)
        if not reasons:
            reasons = [f"Verified {doctor.specialty} specialist", f"Experience: {doctor.experience_years} years"]

        schedules_read = [
            ScheduleRead(
                id=sched.id,
                day_of_week=sched.day_of_week,
                starts_at=sched.starts_at,
                ends_at=sched.ends_at,
                is_active=sched.is_active,
            )
            for sched in (doctor.schedules or [])
            if sched.is_active
        ]

        candidates.append(
            DoctorRecommendation(
                doctor_id=doctor.id,
                doctor_name=doctor.full_name,
                specialty=doctor.specialty,
                hospital_name=hospital.name if hospital else None,
                score=final_score,
                match_reasons=reasons,
                fee_minor=doctor.fee_minor,
                available_slots=[],
                schedules=schedules_read,
                availability_note="Verified clinician in CareVoice directory. Select to book in-person or online appointment.",
            )
        )

    candidates.sort(key=lambda item: (-item.score, item.doctor_name))
    return candidates[:limit]

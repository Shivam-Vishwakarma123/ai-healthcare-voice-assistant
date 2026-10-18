from datetime import date, datetime, time
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator


def _valid_http_url(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    parsed = urlsplit(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Website must be an absolute HTTP or HTTPS URL.")
    return value.strip()


class HospitalRead(BaseModel):
    id: int
    name: str
    city: str
    state: str
    departments: str
    description: str
    address: str | None = None
    phone: str | None = None
    website: str | None = None
    verified: bool
    verification_status: str
    model_config = ConfigDict(from_attributes=True)


class QualificationRead(BaseModel):
    id: int
    degree: str
    institution: str
    completion_year: int | None
    verification_status: str

    model_config = ConfigDict(from_attributes=True)


class QualificationInput(BaseModel):
    degree: str = Field(min_length=1, max_length=120)
    institution: str = Field(min_length=1, max_length=180)
    completion_year: int | None = Field(default=None, ge=1950, le=2100)


class ScheduleInput(BaseModel):
    day_of_week: int = Field(ge=0, le=6)
    starts_at: time
    ends_at: time
    timezone: str = Field(default="Asia/Kolkata", min_length=1, max_length=64)
    consultation_type: str = Field(default="in_person", pattern="^(in_person|online|phone)$")
    is_active: bool = True

    @model_validator(mode="after")
    def validate_time_range(self):
        if self.starts_at.tzinfo is not None or self.ends_at.tzinfo is not None:
            raise ValueError("Schedule times are local wall-clock times; provide timezone separately.")
        if self.starts_at.second or self.starts_at.microsecond or self.ends_at.second or self.ends_at.microsecond:
            raise ValueError("Schedule boundaries must use whole minutes.")
        if self.starts_at >= self.ends_at:
            raise ValueError("Schedule start time must be before its end time.")
        try:
            ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("Schedule timezone must be a valid IANA timezone.") from exc
        return self


class ScheduleRead(ScheduleInput):
    id: int

    model_config = ConfigDict(from_attributes=True)


class DoctorProfileUpdate(BaseModel):
    bio: str | None = Field(default=None, max_length=2000)
    specialty: str | None = Field(default=None, min_length=2, max_length=120)
    specialties: list[str] | None = Field(default=None, max_length=10)
    languages: list[str] | None = Field(default=None, max_length=12)
    consultation_types: list[str] | None = Field(default=None, max_length=3)
    qualifications: list[QualificationInput] | None = Field(default=None, max_length=20)


class HospitalProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=180)
    city: str | None = Field(default=None, min_length=1, max_length=80)
    state: str | None = Field(default=None, min_length=1, max_length=80)
    departments: str | None = Field(default=None, max_length=1000)
    description: str | None = Field(default=None, max_length=2000)
    address: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=32)
    website: str | None = Field(default=None, max_length=255)

    @field_validator("website")
    @classmethod
    def validate_website(cls, value: str | None) -> str | None:
        return _valid_http_url(value)


class VerificationUpdate(BaseModel):
    verification_status: str = Field(pattern="^(pending|verified|rejected)$")


class DoctorRead(BaseModel):
    id: int
    hospital_id: int | None
    full_name: str
    specialty: str
    languages: list[str]
    specialties: list[str]
    consultation_types: list[str]
    qualifications: list[QualificationRead]
    schedules: list[ScheduleRead]
    bio: str
    fee_minor: int
    verified: bool
    verification_status: str
    is_active: bool
    experience_years: int
    consultation_mode: str
    hospital_name: str | None = None
    model_config = ConfigDict(from_attributes=True)


class DoctorRecommendation(BaseModel):
    doctor_id: int
    doctor_name: str
    specialty: str
    hospital_name: str | None = None
    score: float
    match_reasons: list[str]
    fee_minor: int
    available_slots: list[str] = Field(default_factory=list)
    schedules: list[ScheduleRead] = Field(default_factory=list)
    availability_note: str = "Published recurring hours are not real-time appointment availability."


class DoctorPage(BaseModel):
    items: list[DoctorRead]
    total: int
    limit: int
    offset: int


class HospitalPage(BaseModel):
    items: list[HospitalRead]
    total: int
    limit: int
    offset: int


class RecommendationRequest(BaseModel):
    symptoms: str = Field(default="", max_length=1000)
    specialty: str | None = Field(default=None, max_length=120)
    city: str | None = Field(default=None, max_length=80)
    language: str | None = Field(default=None, max_length=80)
    consultation_type: str | None = Field(default=None, pattern="^(in_person|online|phone)$")


class HospitalCreate(BaseModel):
    name: str = Field(min_length=2, max_length=180)
    city: str = Field(min_length=1, max_length=80)
    state: str = Field(min_length=1, max_length=80)
    departments: str = Field(default="General Medicine", max_length=1000)
    description: str = Field(default="", max_length=2000)
    address: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=32)
    website: str | None = Field(default=None, max_length=255)

    @field_validator("website")
    @classmethod
    def validate_website(cls, value: str | None) -> str | None:
        return _valid_http_url(value)


class DoctorCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    specialty: str = Field(min_length=2, max_length=120)
    fee_minor: int = Field(default=0, ge=0, le=10_000_000)
    experience_years: int = Field(default=0, ge=0, le=80)
    bio: str = Field(default="", max_length=2000)


class AppointmentCreate(BaseModel):
    doctor_id: int = Field(gt=0)
    scheduled_for: datetime
    notes: str | None = Field(default=None, max_length=500)
    consultation_type: str = Field(default="in_person", pattern="^(in_person|online|phone)$")

    @model_validator(mode="after")
    def require_timezone(self):
        if self.scheduled_for.tzinfo is None or self.scheduled_for.utcoffset() is None:
            raise ValueError("Appointment time must include a timezone.")
        return self


class AppointmentReschedule(BaseModel):
    scheduled_for: datetime
    consultation_type: str = Field(default="in_person", pattern="^(in_person|online|phone)$")
    reason: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def require_timezone(self):
        if self.scheduled_for.tzinfo is None or self.scheduled_for.utcoffset() is None:
            raise ValueError("Appointment time must include a timezone.")
        return self


class AppointmentCancel(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class AppointmentSlotRead(BaseModel):
    scheduled_for: datetime
    local_date: date
    local_time: time
    timezone: str
    consultation_type: str


class AppointmentEventRead(BaseModel):
    id: int
    appointment_id: int
    actor_user_id: int | None
    event_type: str
    from_status: str | None
    to_status: str
    previous_scheduled_for: datetime | None
    scheduled_for: datetime | None
    reason: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AppointmentRead(BaseModel):
    id: int
    patient_user_id: int
    doctor_id: int
    hospital_id: int | None
    scheduled_for: datetime
    duration_minutes: int
    consultation_type: str = "in_person"
    status: str
    notes: str | None
    created_at: datetime
    doctor_name: str | None = None
    hospital_name: str | None = None
    specialty: str | None = None
    fee_minor: int = 0
    invoice_id: int | None = None
    invoice_status: str | None = None
    payment_status: str | None = None
    payment_transaction_id: str | None = None
    payment_is_demo: bool = False
    can_start_payment: bool = False
    payment_block_reason: str | None = None
    model_config = ConfigDict(from_attributes=True)

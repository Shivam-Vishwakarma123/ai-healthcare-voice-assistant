from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.email_validation import normalize_email
from app.core.validators import strip_full_name as normalize_full_name

Gender = Literal["female", "male", "other", "prefer_not_to_say"]

class PatientCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    email: str
    age: int = Field(ge=0, le=120)
    gender: Gender

    @field_validator("full_name")
    @classmethod
    def strip_full_name(cls, value: str) -> str:
        return normalize_full_name(value)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return normalize_email(value)

class PatientUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    email: str | None = None
    age: int | None = Field(default=None, ge=0, le=120)
    gender: Gender | None = None

    @field_validator("full_name")
    @classmethod
    def strip_full_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return normalize_full_name(value)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return normalize_email(value)

class PatientRead(BaseModel):
    id: int
    full_name: str
    email: str
    age: int
    gender: Gender
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class PatientNotificationRead(BaseModel):
    id: int
    event_type: str
    channel: str
    status: str
    created_at: datetime
    title: str
    title_hi: str
    message: str
    message_hi: str
    model_config = ConfigDict(from_attributes=True)


class PatientNotificationPage(BaseModel):
    items: list[PatientNotificationRead]
    total: int
    limit: int
    offset: int


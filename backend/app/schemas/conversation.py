from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field


class ConversationMessageRead(BaseModel):
    id: int
    conversation_id: int
    role: Literal["user", "assistant", "system"]
    content: str
    created_at: datetime
    structured_data: dict[str, Any] | None = None

    model_config = ConfigDict(from_attributes=True)


class ConversationRead(BaseModel):
    id: int
    conversation_id: str
    user_id: int
    patient_id: int | None = None
    title: str
    urgency_level: str = "routine"
    category: str = "general"
    summary: str | None = None
    consent_given: bool = True
    created_at: datetime
    updated_at: datetime
    messages: list[ConversationMessageRead] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class ConversationSummary(BaseModel):
    id: int
    conversation_id: str
    user_id: int
    patient_id: int | None = None
    title: str
    urgency_level: str = "routine"
    category: str = "general"
    consent_given: bool = True
    created_at: datetime
    updated_at: datetime
    message_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class ConversationCreate(BaseModel):
    title: str = Field(default="Health consultation", min_length=1, max_length=200)
    consent_given: bool = Field(default=True)

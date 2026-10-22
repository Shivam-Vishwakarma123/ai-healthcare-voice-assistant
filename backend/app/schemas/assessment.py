from __future__ import annotations

from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field


class AssessmentEvidenceSource(BaseModel):
    title: str
    source_url: str
    citation: str
    licence: str = "open"
    allowed_use: str = "public health guidance"
    provenance: str = ""
    publication_date: str | None = None
    updated_at: str | None = None
    retrieval_date: str = ""
    version: str = "1.0"


class AssessmentResponse(BaseModel):
    assessment_id: str
    language: str = "en"
    symptom_summary: str
    follow_up_questions: list[str] = Field(default_factory=list)
    red_flags: list[str] = Field(default_factory=list)
    triage_level: str = "routine"
    recommended_next_steps: list[str] = Field(default_factory=list)
    care_urgency: str = "routine"
    possible_explanations: list[str] = Field(default_factory=list)
    evidence_sources: list[AssessmentEvidenceSource] = Field(default_factory=list)
    uncertainty_notes: str | None = None
    disclaimer: str = (
        "CareVoice provides health education and navigation assistance only. "
        "It does not provide a definitive medical diagnosis or replace consultation with a qualified clinician."
    )
    model_metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None


class AssessmentSummary(BaseModel):
    assessment_id: str
    id: int
    title: str
    urgency_level: str
    category: str
    created_at: datetime
    updated_at: datetime
    message_count: int = 0

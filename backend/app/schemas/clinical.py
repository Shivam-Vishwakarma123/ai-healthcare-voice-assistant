from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field


# ============================================================================
# Clinical Notes
# ============================================================================

class ClinicalNoteBase(BaseModel):
    note_type: str = Field(default="consultation_note", description="consultation_note, soap_note, progress_note")
    chief_complaint: str | None = None
    history_of_present_illness: str | None = None
    examination_findings: str | None = None
    assessment: str | None = None
    plan: str | None = None
    follow_up_instructions: str | None = None


class ClinicalNoteCreate(ClinicalNoteBase):
    patient_user_id: int
    appointment_id: int | None = None
    is_ai_draft: bool = False


class ClinicalNoteUpdate(BaseModel):
    chief_complaint: str | None = None
    history_of_present_illness: str | None = None
    examination_findings: str | None = None
    assessment: str | None = None
    plan: str | None = None
    follow_up_instructions: str | None = None


class ClinicalNoteRead(ClinicalNoteBase):
    id: int
    patient_user_id: int
    doctor_id: int
    doctor_name: str | None = None
    hospital_name: str | None = None
    appointment_id: int | None = None
    is_ai_draft: bool
    status: str
    version: int
    finalized_at: datetime | None = None
    finalized_by_user_id: int | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ClinicalNoteAIDraftRequest(BaseModel):
    patient_user_id: int
    appointment_id: int | None = None
    conversation_id: int | None = None
    symptoms_context: str | None = None


# ============================================================================
# Prescriptions
# ============================================================================

class PrescriptionItemBase(BaseModel):
    medication_name: str
    strength: str | None = None
    dosage_form: str = "tablet"
    route: str = "oral"
    frequency: str = "1-0-1 (Twice daily after meals)"
    duration: str = "5 days"
    quantity: str | None = "10 tablets"
    instructions: str | None = "Take after food with plenty of water"


class PrescriptionItemCreate(PrescriptionItemBase):
    pass


class PrescriptionItemRead(PrescriptionItemBase):
    id: int
    prescription_id: int

    model_config = ConfigDict(from_attributes=True)


class PrescriptionCreate(BaseModel):
    patient_user_id: int
    appointment_id: int | None = None
    diagnosis: str | None = None
    notes: str | None = None
    allergy_warnings: list[str] = Field(default_factory=list)
    is_ai_draft: bool = False
    items: list[PrescriptionItemCreate] = Field(default_factory=list)


class PrescriptionRead(BaseModel):
    id: int
    prescription_number: str
    patient_user_id: int
    patient_name: str | None = None
    doctor_id: int
    doctor_name: str | None = None
    hospital_name: str | None = None
    appointment_id: int | None = None
    diagnosis: str | None = None
    notes: str | None = None
    allergy_warnings: list[str] = Field(default_factory=list)
    is_ai_draft: bool
    status: str
    finalized_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    items: list[PrescriptionItemRead] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class PrescriptionAIDraftRequest(BaseModel):
    patient_user_id: int
    appointment_id: int | None = None
    diagnosis_hint: str
    symptoms_context: str | None = None


# ============================================================================
# Medical Reports & AI Summaries
# ============================================================================

class MedicalReportCreate(BaseModel):
    patient_user_id: int
    appointment_id: int | None = None
    conversation_id: int | None = None
    report_type: str = "symptom_assessment"
    title: str
    summary: str
    urgency_level: str = "routine"
    red_flags: list[str] = Field(default_factory=list)
    findings: list[dict[str, Any]] = Field(default_factory=list)
    recommended_next_steps: list[str] = Field(default_factory=list)
    evidence_sources: list[dict[str, Any]] = Field(default_factory=list)
    uncertainty_notes: str | None = None
    disclaimer: str | None = None
    model_metadata: dict[str, Any] = Field(default_factory=dict)


class MedicalReportRead(BaseModel):
    id: int
    report_id: str
    patient_user_id: int
    doctor_id: int | None = None
    doctor_name: str | None = None
    appointment_id: int | None = None
    conversation_id: int | None = None
    report_type: str
    title: str
    summary: str
    urgency_level: str
    red_flags: list[str] = Field(default_factory=list)
    findings: list[dict[str, Any]] = Field(default_factory=list)
    recommended_next_steps: list[str] = Field(default_factory=list)
    evidence_sources: list[dict[str, Any]] = Field(default_factory=list)
    uncertainty_notes: str | None = None
    disclaimer: str
    model_metadata: dict[str, Any] = Field(default_factory=dict)
    status: str
    reviewed_by_doctor_id: int | None = None
    reviewed_by_doctor_name: str | None = None
    reviewed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MedicalReportGenerateRequest(BaseModel):
    patient_user_id: int | None = None
    conversation_id: int | None = None
    appointment_id: int | None = None
    report_type: Literal[
        "symptom_assessment",
        "conversation_summary",
        "health_timeline",
        "pre_appointment_summary",
        "visit_summary",
        "follow_up_summary",
    ] = "symptom_assessment"


# ============================================================================
# Allergies & Conditions
# ============================================================================

class PatientAllergyCreate(BaseModel):
    allergen_or_condition: str
    category: Literal["allergy", "chronic_condition", "medication_reaction"] = "allergy"
    severity: Literal["mild", "moderate", "severe", "life_threatening"] = "mild"
    reaction: str | None = None


class PatientAllergyRead(BaseModel):
    id: int
    patient_user_id: int
    allergen_or_condition: str
    category: str
    severity: str
    reaction: str | None = None
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# Medical Documents
# ============================================================================

class MedicalDocumentRead(BaseModel):
    id: int
    patient_user_id: int
    uploaded_by_user_id: int | None = None
    title: str
    document_type: str
    file_size: int
    mime_type: str
    notes: str | None = None
    extracted_data: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# Timeline & Patient Overview
# ============================================================================

class PatientTimelineEvent(BaseModel):
    id: str
    event_type: str  # assessment, conversation, appointment, note, prescription, report, document, allergy
    category: str  # ai, clinician, patient, operational
    title: str
    description: str
    timestamp: datetime
    actor_name: str | None = None
    actor_role: str | None = None
    urgency_level: str | None = None
    status: str | None = None
    resource_id: int | str
    details: dict[str, Any] = Field(default_factory=dict)


class PatientTimelineResponse(BaseModel):
    patient_user_id: int
    patient_name: str
    events: list[PatientTimelineEvent]
    total_count: int


class PatientOverviewResponse(BaseModel):
    patient_user_id: int
    full_name: str
    email: str
    age: int | None = None
    gender: str | None = None
    allergies: list[PatientAllergyRead] = Field(default_factory=list)
    recent_assessments: list[dict[str, Any]] = Field(default_factory=list)
    recent_reports: list[MedicalReportRead] = Field(default_factory=list)
    recent_prescriptions: list[PrescriptionRead] = Field(default_factory=list)
    recent_notes: list[ClinicalNoteRead] = Field(default_factory=list)
    upcoming_appointments: list[dict[str, Any]] = Field(default_factory=list)
    past_appointments: list[dict[str, Any]] = Field(default_factory=list)


# ============================================================================
# Doctor Workspace Overview
# ============================================================================

class AssignedPatientSummary(BaseModel):
    patient_user_id: int
    patient_name: str
    email: str
    last_appointment: datetime | None = None
    next_appointment: datetime | None = None
    active_allergies_count: int = 0
    pending_ai_assessments_count: int = 0
    total_prescriptions_count: int = 0


class DoctorWorkspaceResponse(BaseModel):
    doctor_id: int
    doctor_name: str
    specialty: str
    hospital_name: str | None = None
    assigned_patients: list[AssignedPatientSummary]
    today_appointments: list[dict[str, Any]]
    recent_ai_assessments: list[dict[str, Any]]

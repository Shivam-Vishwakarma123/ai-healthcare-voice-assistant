from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def _generate_report_id() -> str:
    return str(uuid.uuid4())


def _generate_prescription_number() -> str:
    return f"RX-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"


class ClinicalNote(Base):
    __tablename__ = "clinical_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patient_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    doctor_id: Mapped[int] = mapped_column(
        ForeignKey("doctors.id", ondelete="CASCADE"), nullable=False, index=True
    )
    appointment_id: Mapped[int | None] = mapped_column(
        ForeignKey("appointments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    note_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="consultation_note"
    )  # consultation_note, soap_note, progress_note
    chief_complaint: Mapped[str | None] = mapped_column(Text, nullable=True)
    history_of_present_illness: Mapped[str | None] = mapped_column(Text, nullable=True)
    examination_findings: Mapped[str | None] = mapped_column(Text, nullable=True)
    assessment: Mapped[str | None] = mapped_column(Text, nullable=True)
    plan: Mapped[str | None] = mapped_column(Text, nullable=True)
    follow_up_instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_ai_draft: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="draft"
    )  # draft, finalized, amended
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finalized_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    patient_user = relationship("User", foreign_keys=[patient_user_id])
    doctor = relationship("Doctor", foreign_keys=[doctor_id])
    appointment = relationship("Appointment", foreign_keys=[appointment_id])
    finalized_by = relationship("User", foreign_keys=[finalized_by_user_id])


class Prescription(Base):
    __tablename__ = "prescriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    prescription_number: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, default=_generate_prescription_number, nullable=False
    )
    patient_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    doctor_id: Mapped[int] = mapped_column(
        ForeignKey("doctors.id", ondelete="CASCADE"), nullable=False, index=True
    )
    appointment_id: Mapped[int | None] = mapped_column(
        ForeignKey("appointments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    diagnosis: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    allergy_warnings: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    is_ai_draft: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="draft"
    )  # draft, finalized, cancelled, amended
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finalized_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    patient_user = relationship("User", foreign_keys=[patient_user_id])
    doctor = relationship("Doctor", foreign_keys=[doctor_id])
    appointment = relationship("Appointment", foreign_keys=[appointment_id])
    finalized_by = relationship("User", foreign_keys=[finalized_by_user_id])
    items: Mapped[list[PrescriptionItem]] = relationship(
        back_populates="prescription", cascade="all, delete-orphan", order_by="PrescriptionItem.id.asc()"
    )


class PrescriptionItem(Base):
    __tablename__ = "prescription_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    prescription_id: Mapped[int] = mapped_column(
        ForeignKey("prescriptions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    medication_name: Mapped[str] = mapped_column(String(180), nullable=False)
    strength: Mapped[str | None] = mapped_column(String(60), nullable=True)
    dosage_form: Mapped[str] = mapped_column(String(60), default="tablet", nullable=False)
    route: Mapped[str] = mapped_column(String(40), default="oral", nullable=False)
    frequency: Mapped[str] = mapped_column(String(80), nullable=False)
    duration: Mapped[str] = mapped_column(String(80), nullable=False)
    quantity: Mapped[str | None] = mapped_column(String(40), nullable=True)
    instructions: Mapped[str | None] = mapped_column(Text, nullable=True)

    prescription: Mapped[Prescription] = relationship(back_populates="items")


class MedicalReport(Base):
    __tablename__ = "medical_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_id: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, default=_generate_report_id, nullable=False
    )
    patient_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    doctor_id: Mapped[int | None] = mapped_column(
        ForeignKey("doctors.id", ondelete="SET NULL"), nullable=True, index=True
    )
    appointment_id: Mapped[int | None] = mapped_column(
        ForeignKey("appointments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    conversation_id: Mapped[int | None] = mapped_column(
        ForeignKey("assistant_conversations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    report_type: Mapped[str] = mapped_column(
        String(60), default="symptom_assessment", nullable=False
    )  # symptom_assessment, conversation_summary, health_timeline, pre_appointment_summary, visit_summary, follow_up_summary
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    urgency_level: Mapped[str] = mapped_column(String(40), default="routine", nullable=False)
    red_flags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    findings: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    recommended_next_steps: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    evidence_sources: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    uncertainty_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    disclaimer: Mapped[str] = mapped_column(
        Text,
        default=(
            "CareVoice AI reports provide structured educational assessment and clinical synthesis only. "
            "They do not constitute a definitive medical diagnosis or replacement for licensed clinician evaluation."
        ),
        nullable=False,
    )
    model_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="generated", nullable=False
    )  # draft, generated, pending_review, reviewed, finalized, amended, failed
    reviewed_by_doctor_id: Mapped[int | None] = mapped_column(
        ForeignKey("doctors.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    patient_user = relationship("User", foreign_keys=[patient_user_id])
    doctor = relationship("Doctor", foreign_keys=[doctor_id])
    appointment = relationship("Appointment", foreign_keys=[appointment_id])
    conversation = relationship("AssistantConversation", foreign_keys=[conversation_id])
    reviewed_by_doctor = relationship("Doctor", foreign_keys=[reviewed_by_doctor_id])


class PatientAllergy(Base):
    __tablename__ = "patient_allergies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patient_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    allergen_or_condition: Mapped[str] = mapped_column(String(180), nullable=False)
    category: Mapped[str] = mapped_column(
        String(40), default="allergy", nullable=False
    )  # allergy, chronic_condition, medication_reaction
    severity: Mapped[str] = mapped_column(
        String(30), default="mild", nullable=False
    )  # mild, moderate, severe, life_threatening
    reaction: Mapped[str | None] = mapped_column(Text, nullable=True)
    recorded_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    patient_user = relationship("User", foreign_keys=[patient_user_id])
    recorded_by = relationship("User", foreign_keys=[recorded_by_user_id])


class MedicalDocument(Base):
    __tablename__ = "medical_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patient_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    uploaded_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    document_type: Mapped[str] = mapped_column(
        String(60), default="other", nullable=False
    )  # lab_report, imaging, discharge_summary, prescription, other
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), default="application/pdf", nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    patient_user = relationship("User", foreign_keys=[patient_user_id])
    uploaded_by = relationship("User", foreign_keys=[uploaded_by_user_id])


class PatientVital(Base):
    __tablename__ = "patient_vitals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patient_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    bp_systolic: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bp_diastolic: Mapped[int | None] = mapped_column(Integer, nullable=True)
    heart_rate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    spo2: Mapped[int | None] = mapped_column(Integer, nullable=True)
    temperature_f: Mapped[float | None] = mapped_column(Float, nullable=True)
    respiratory_rate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    blood_glucose: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="normal", nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(40), default="clinical_encounter", nullable=False)
    encounter_id: Mapped[int | None] = mapped_column(
        ForeignKey("appointments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    patient_user = relationship("User", foreign_keys=[patient_user_id])
    encounter = relationship("Appointment", foreign_keys=[encounter_id])


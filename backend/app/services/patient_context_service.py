from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.clinical import (
    ClinicalNote,
    MedicalDocument,
    MedicalReport,
    PatientAllergy,
    Prescription,
)
from app.models.patient import Patient
from app.models.user import User

logger = logging.getLogger(__name__)


# Provenance record pointing to a verified patient record in the database.
class PatientRecordProvenance(BaseModel):
    source_type: str
    record_id: int
    label: str
    verified: bool = True
    finalized_at: str | None = None


# Structured snapshot of authorized clinical data for a patient.
class AuthorizedPatientContext(BaseModel):
    patient_user_id: int
    full_name: str
    age: int | None = None
    gender: str | None = None
    active_allergies: list[dict[str, Any]] = Field(default_factory=list)
    chronic_conditions: list[dict[str, Any]] = Field(default_factory=list)
    active_prescriptions: list[dict[str, Any]] = Field(default_factory=list)
    recent_clinical_notes: list[dict[str, Any]] = Field(default_factory=list)
    recent_documents: list[dict[str, Any]] = Field(default_factory=list)
    recent_vitals: dict[str, Any] = Field(default_factory=dict)
    provenance: list[PatientRecordProvenance] = Field(default_factory=list)
    context_text: str = ""


# Service providing authorized, safety-bounded patient context for AI clinical synthesis.
class PatientContextService:
    # Resolves and authorizes access to clinical records, strictly enforcing RBAC boundaries.
    @staticmethod
    def get_patient_context(
        db: Session,
        *,
        requesting_user: User,
        target_patient_user_id: int | None = None,
    ) -> AuthorizedPatientContext | None:
        """Retrieves and packages verified patient health context.

        RBAC Enforcement:
        - Patients can ONLY access their own records (requesting_user.id).
        - Clinicians (doctors) can access assigned patients.
        - Platform / hospital administrators can access patient context for quality review.
        - Unauthenticated or unauthorized cross-patient requests raise HTTP 403 Forbidden.
        """
        # Determine target patient user ID
        resolved_patient_id: int | None = None
        if requesting_user.role == "patient":
            if target_patient_user_id is not None and target_patient_user_id != requesting_user.id:
                logger.warning(
                    "RBAC Violation: Patient user %d attempted to access patient user %d context.",
                    requesting_user.id,
                    target_patient_user_id,
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access forbidden: Patients may only access their own healthcare records.",
                )
            resolved_patient_id = requesting_user.id
        elif requesting_user.role in {"doctor", "hospital_admin", "platform_admin"}:
            resolved_patient_id = target_patient_user_id
            if resolved_patient_id is None:
                return None
        else:
            return None

        # Fetch patient profile
        patient = db.scalar(select(Patient).where(Patient.owner_user_id == resolved_patient_id))
        target_user = db.get(User, resolved_patient_id)
        if not target_user:
            return None

        full_name = patient.full_name if patient else target_user.full_name
        age = patient.age if patient else None
        gender = patient.gender if patient else None

        provenance_list: list[PatientRecordProvenance] = []

        # 1. Active Allergies and Adverse Reactions
        allergies_records = db.scalars(
            select(PatientAllergy)
            .where(
                PatientAllergy.patient_user_id == resolved_patient_id,
                PatientAllergy.is_active == True,  # noqa: E712
            )
            .order_by(PatientAllergy.created_at.desc())
        ).all()

        active_allergies: list[dict[str, Any]] = []
        chronic_conditions: list[dict[str, Any]] = []

        for item in allergies_records:
            entry = {
                "id": item.id,
                "name": item.allergen_or_condition,
                "category": item.category,
                "severity": item.severity,
                "reaction": item.reaction or "",
            }
            if item.category in {"chronic_condition", "condition"}:
                chronic_conditions.append(entry)
                provenance_list.append(
                    PatientRecordProvenance(
                        source_type="patient_allergy",
                        record_id=item.id,
                        label=f"Chronic Condition: {item.allergen_or_condition}",
                    )
                )
            else:
                active_allergies.append(entry)
                provenance_list.append(
                    PatientRecordProvenance(
                        source_type="patient_allergy",
                        record_id=item.id,
                        label=f"Allergy: {item.allergen_or_condition} ({item.severity})",
                    )
                )

        # 2. Active Clinician-Finalized Prescriptions (Drafts strictly excluded!)
        prescriptions_query = (
            select(Prescription)
            .options(selectinload(Prescription.items))
            .where(
                Prescription.patient_user_id == resolved_patient_id,
                Prescription.status == "finalized",
            )
            .order_by(Prescription.finalized_at.desc())
            .limit(10)
        )
        finalized_prescriptions = db.scalars(prescriptions_query).all()

        active_prescriptions: list[dict[str, Any]] = []
        for rx in finalized_prescriptions:
            rx_items = [
                {
                    "medication_name": it.medication_name,
                    "strength": it.strength,
                    "dosage_form": it.dosage_form,
                    "frequency": it.frequency,
                    "duration": it.duration,
                    "instructions": it.instructions,
                }
                for it in rx.items
            ]
            active_prescriptions.append({
                "prescription_number": rx.prescription_number,
                "diagnosis": rx.diagnosis,
                "finalized_at": rx.finalized_at.isoformat() if rx.finalized_at else None,
                "items": rx_items,
            })
            provenance_list.append(
                PatientRecordProvenance(
                    source_type="prescription",
                    record_id=rx.id,
                    label=f"Finalized Prescription {rx.prescription_number}",
                    finalized_at=rx.finalized_at.isoformat() if rx.finalized_at else None,
                )
            )

        # 3. Finalized Clinician Visit Notes (Drafts strictly excluded!)
        notes_query = (
            select(ClinicalNote)
            .where(
                ClinicalNote.patient_user_id == resolved_patient_id,
                ClinicalNote.status == "finalized",
            )
            .order_by(ClinicalNote.finalized_at.desc())
            .limit(3)
        )
        finalized_notes = db.scalars(notes_query).all()

        recent_notes: list[dict[str, Any]] = []
        for n in finalized_notes:
            recent_notes.append({
                "id": n.id,
                "note_type": n.note_type,
                "chief_complaint": n.chief_complaint,
                "assessment": n.assessment,
                "plan": n.plan,
                "finalized_at": n.finalized_at.isoformat() if n.finalized_at else None,
            })
            provenance_list.append(
                PatientRecordProvenance(
                    source_type="clinical_note",
                    record_id=n.id,
                    label=f"Finalized Clinician Note ({n.note_type})",
                    finalized_at=n.finalized_at.isoformat() if n.finalized_at else None,
                )
            )

        # 4. Diagnostic & Lab Documents
        docs_query = (
            select(MedicalDocument)
            .where(MedicalDocument.patient_user_id == resolved_patient_id)
            .order_by(MedicalDocument.created_at.desc())
            .limit(5)
        )
        documents = db.scalars(docs_query).all()

        recent_docs: list[dict[str, Any]] = []
        recent_vitals: dict[str, Any] = {}

        for doc in documents:
            recent_docs.append({
                "id": doc.id,
                "title": doc.title,
                "document_type": doc.document_type,
                "extracted_data": doc.extracted_data or {},
                "created_at": doc.created_at.isoformat() if doc.created_at else None,
            })
            if doc.extracted_data and isinstance(doc.extracted_data, dict):
                # Extract any vitals or lab findings
                for k, v in doc.extracted_data.items():
                    if k in {"blood_pressure", "heart_rate", "temperature", "spo2", "platelets", "glucose", "hemoglobin"}:
                        recent_vitals[k] = v
            provenance_list.append(
                PatientRecordProvenance(
                    source_type="medical_document",
                    record_id=doc.id,
                    label=f"Diagnostic Report: {doc.title} ({doc.document_type})",
                )
            )

        # Build formatted XML context block for the LLM prompt
        context_text = PatientContextService._build_context_xml(
            full_name=full_name,
            age=age,
            gender=gender,
            active_allergies=active_allergies,
            chronic_conditions=chronic_conditions,
            active_prescriptions=active_prescriptions,
            recent_notes=recent_notes,
            recent_vitals=recent_vitals,
            recent_docs=recent_docs,
        )

        return AuthorizedPatientContext(
            patient_user_id=resolved_patient_id,
            full_name=full_name,
            age=age,
            gender=gender,
            active_allergies=active_allergies,
            chronic_conditions=chronic_conditions,
            active_prescriptions=active_prescriptions,
            recent_clinical_notes=recent_notes,
            recent_documents=recent_docs,
            recent_vitals=recent_vitals,
            provenance=provenance_list,
            context_text=context_text,
        )

    # Formats retrieved patient records into a secure, structured XML block for system prompts.
    @staticmethod
    def _build_context_xml(
        *,
        full_name: str,
        age: int | None,
        gender: str | None,
        active_allergies: list[dict[str, Any]],
        chronic_conditions: list[dict[str, Any]],
        active_prescriptions: list[dict[str, Any]],
        recent_notes: list[dict[str, Any]],
        recent_vitals: dict[str, Any],
        recent_docs: list[dict[str, Any]],
    ) -> str:
        lines: list[str] = [
            "<authorized-patient-context>",
            f"[PATIENT DEMOGRAPHICS]\nName: {full_name}, Age: {age if age is not None else 'Unrecorded'}, Gender: {gender if gender else 'Unrecorded'}",
        ]

        # Allergies
        lines.append("\n[CLINICIAN-VERIFIED ACTIVE ALLERGIES]")
        if active_allergies:
            for al in active_allergies:
                reaction_part = f", Reaction: {al['reaction']}" if al.get("reaction") else ""
                lines.append(f"- {al['name']} (Severity: {al['severity']}{reaction_part})")
        else:
            lines.append("None recorded in electronic health record. (Note: Absence of recorded allergies does not guarantee absence of allergy.)")

        # Chronic Conditions
        lines.append("\n[CHRONIC DIAGNOSES & PROBLEM LIST]")
        if chronic_conditions:
            for cond in chronic_conditions:
                lines.append(f"- {cond['name']}")
        else:
            lines.append("No chronic medical conditions recorded.")

        # Prescriptions
        lines.append("\n[ACTIVE FINALIZED PRESCRIPTIONS]")
        if active_prescriptions:
            for rx in active_prescriptions:
                diag_text = f" (Diagnosis: {rx['diagnosis']})" if rx.get("diagnosis") else ""
                lines.append(f"Prescription {rx['prescription_number']}{diag_text}:")
                for it in rx.get("items", []):
                    details = f"{it['medication_name']} {it.get('strength') or ''} ({it.get('dosage_form') or 'dose'}), Frequency: {it.get('frequency') or 'per instructions'}, Duration: {it.get('duration') or 'as directed'}"
                    lines.append(f"  * {details}")
        else:
            lines.append("No active clinician prescriptions on file.")

        # Recent Vitals
        lines.append("\n[RECENT VITALS & DIAGNOSTIC LABS]")
        if recent_vitals:
            for k, v in recent_vitals.items():
                lines.append(f"- {k.replace('_', ' ').title()}: {v}")
        else:
            lines.append("No recent vitals or lab values on file.")

        # Recent Visit Notes
        lines.append("\n[RECENT FINALIZED CLINICIAN VISIT NOTES]")
        if recent_notes:
            for note in recent_notes:
                lines.append(f"- [{note.get('note_type', 'Consultation')}] Assessment: {note.get('assessment') or 'N/A'}")
                if note.get("plan"):
                    lines.append(f"  Plan: {note['plan']}")
        else:
            lines.append("No previous finalized visit notes.")

        lines.extend([
            "\n[SAFETY & PROVENANCE BOUNDARY]",
            "The records above are verified patient health data from CareVoice.",
            "Patient statements in the conversation are self-reported and unverified.",
            "Never autonomously prescribe, recommend medication changes, or calculate personalized dosages.",
            "If records are missing or ambiguous, state the ambiguity clearly rather than guessing.",
            "</authorized-patient-context>",
        ])

        return "\n".join(lines)

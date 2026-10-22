from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.auth.security import get_current_user, require_roles
from app.core.database import get_db
from app.models.clinical import (
    ClinicalNote,
    MedicalDocument,
    MedicalReport,
    PatientAllergy,
    Prescription,
    PrescriptionItem,
)
from app.models.conversation import AssistantConversation, AssistantMessage
from app.models.patient import Patient
from app.models.providers import Appointment, Doctor, Hospital
from app.models.user import User
from app.schemas.clinical import (
    AssignedPatientSummary,
    ClinicalNoteAIDraftRequest,
    ClinicalNoteCreate,
    ClinicalNoteRead,
    ClinicalNoteUpdate,
    DoctorWorkspaceResponse,
    MedicalDocumentRead,
    MedicalReportCreate,
    MedicalReportGenerateRequest,
    MedicalReportRead,
    PatientAllergyCreate,
    PatientAllergyRead,
    PatientOverviewResponse,
    PatientTimelineEvent,
    PatientTimelineResponse,
    PrescriptionAIDraftRequest,
    PrescriptionCreate,
    PrescriptionItemCreate,
    PrescriptionItemRead,
    PrescriptionRead,
)
from app.services.audit_service import record_audit
from app.services.clinical_service import (
    check_medication_allergy_conflicts,
    draft_clinical_note_with_ai,
    draft_prescription_with_ai,
    generate_fhir_r4_bundle,
)
from app.services.pdf_report_service import (
    generate_medical_report_pdf,
    generate_prescription_pdf,
)

router = APIRouter(prefix="/records", tags=["Clinical Records & Doctor Workspace"])

DOCUMENTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "medical_documents")
os.makedirs(DOCUMENTS_DIR, exist_ok=True)


def _normalize_dt(dt: datetime | None) -> datetime:
    if not dt:
        return datetime.now(timezone.utc)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _check_doctor_or_patient_access(
    db: Session,
    user: User,
    target_patient_user_id: int,
    *,
    require_doctor_write: bool = False,
) -> Doctor | None:
    """Verifies that the current user has authorized access to target_patient_user_id.

    - A patient can only access their own records (read/upload/request).
    - A doctor can only access patients with whom they have an active or past appointment/encounter.
    - A platform admin has administrative audit-logged read access.
    """
    if user.role == "patient":
        if user.id != target_patient_user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: You can only access your own clinical records.",
            )
        if require_doctor_write:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Clinician privileges required for this clinical action.",
            )
        return None

    if user.role == "doctor":
        if not user.doctor_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Doctor profile not linked to user account.",
            )
        doctor = db.get(Doctor, user.doctor_id)
        if not doctor:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Doctor profile not found.",
            )

        # Verify relationship via appointment
        has_relationship = db.scalar(
            select(func.count(Appointment.id)).where(
                Appointment.doctor_id == doctor.id,
                Appointment.patient_user_id == target_patient_user_id,
            )
        )
        if not has_relationship:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: You are not assigned to this patient encounter.",
            )
        return doctor

    if user.role == "platform_admin":
        if require_doctor_write:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Platform admins cannot sign clinical notes or prescriptions.",
            )
        return None

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Insufficient clinical privileges to access patient records.",
    )


# ============================================================================
# 1. Timeline, Overview & FHIR Export
# ============================================================================

@router.get("/timeline", response_model=PatientTimelineResponse)
def get_patient_timeline(
    request: Request,
    patient_user_id: int | None = Query(None, description="Patient user ID (defaults to current user)"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    target_id = patient_user_id or user.id
    _check_doctor_or_patient_access(db, user, target_id)

    target_patient = db.get(User, target_id)
    if not target_patient:
        raise HTTPException(status_code=404, detail="Patient user not found.")

    events: list[PatientTimelineEvent] = []

    # 1. AI Conversations / Assessments
    conversations = db.scalars(
        select(AssistantConversation).where(
            AssistantConversation.user_id == target_id,
            AssistantConversation.is_active == True,  # noqa: E712
        )
    ).all()
    for conv in conversations:
        events.append(
            PatientTimelineEvent(
                id=f"conv-{conv.id}",
                event_type="assessment",
                category="ai",
                title=f"AI Health Assessment: {conv.title}",
                description=conv.summary or "Patient symptom triage and educational consultation.",
                timestamp=conv.created_at,
                urgency_level=conv.urgency_level,
                status="completed",
                resource_id=conv.conversation_id,
                details={"category": conv.category},
            )
        )

    # 2. Appointments
    appts = db.scalars(
        select(Appointment).where(Appointment.patient_user_id == target_id)
    ).all()
    for appt in appts:
        doc = db.get(Doctor, appt.doctor_id)
        doc_name = doc.full_name if doc else "Doctor"
        events.append(
            PatientTimelineEvent(
                id=f"appt-{appt.id}",
                event_type="appointment",
                category="operational",
                title=f"Doctor Appointment: {doc_name}",
                description=f"Consultation scheduled for {appt.consultation_type.replace('_', ' ')}.",
                timestamp=appt.scheduled_for,
                actor_name=doc_name,
                actor_role="doctor",
                status=appt.status,
                resource_id=appt.id,
                details={"duration_minutes": appt.duration_minutes},
            )
        )

    # 3. Clinical Notes (Patient only sees finalized; doctor sees draft & finalized)
    notes_query = select(ClinicalNote).where(ClinicalNote.patient_user_id == target_id)
    if user.role == "patient":
        notes_query = notes_query.where(ClinicalNote.status == "finalized")
    notes = db.scalars(notes_query).all()
    for note in notes:
        doc = db.get(Doctor, note.doctor_id)
        doc_name = doc.full_name if doc else "Clinician"
        events.append(
            PatientTimelineEvent(
                id=f"note-{note.id}",
                event_type="note",
                category="clinician",
                title=f"Doctor Clinical Note ({note.note_type.replace('_', ' ').title()})",
                description=note.assessment or note.chief_complaint or "Clinical documentation.",
                timestamp=note.finalized_at or note.created_at,
                actor_name=doc_name,
                actor_role="doctor",
                status=note.status,
                resource_id=note.id,
                details={"is_ai_draft": note.is_ai_draft, "version": note.version},
            )
        )

    # 4. Prescriptions
    presc_query = select(Prescription).where(Prescription.patient_user_id == target_id)
    if user.role == "patient":
        presc_query = presc_query.where(Prescription.status == "finalized")
    prescriptions = db.scalars(presc_query).all()
    for rx in prescriptions:
        doc = db.get(Doctor, rx.doctor_id)
        doc_name = doc.full_name if doc else "Doctor"
        med_summary = ", ".join([it.medication_name for it in rx.items]) if rx.items else "Medications"
        events.append(
            PatientTimelineEvent(
                id=f"rx-{rx.id}",
                event_type="prescription",
                category="clinician",
                title=f"Prescription {rx.prescription_number}",
                description=f"Prescribed: {med_summary}. Diagnosis: {rx.diagnosis or 'Clinical evaluation'}.",
                timestamp=rx.finalized_at or rx.created_at,
                actor_name=doc_name,
                actor_role="doctor",
                status=rx.status,
                resource_id=rx.id,
                details={"item_count": len(rx.items), "is_ai_draft": rx.is_ai_draft},
            )
        )

    # 5. Medical Reports
    reports = db.scalars(
        select(MedicalReport).where(MedicalReport.patient_user_id == target_id)
    ).all()
    for rep in reports:
        events.append(
            PatientTimelineEvent(
                id=f"report-{rep.id}",
                event_type="report",
                category="ai",
                title=f"Medical Report: {rep.title}",
                description=rep.summary,
                timestamp=rep.created_at,
                urgency_level=rep.urgency_level,
                status=rep.status,
                resource_id=rep.report_id,
                details={"report_type": rep.report_type},
            )
        )

    # 6. Uploaded Documents
    docs = db.scalars(
        select(MedicalDocument).where(MedicalDocument.patient_user_id == target_id)
    ).all()
    for d in docs:
        events.append(
            PatientTimelineEvent(
                id=f"doc-{d.id}",
                event_type="document",
                category="patient",
                title=f"Uploaded Document: {d.title}",
                description=f"Type: {d.document_type.replace('_', ' ').title()} (MIME: {d.mime_type}).",
                timestamp=d.created_at,
                status="available",
                resource_id=d.id,
                details={"file_size": d.file_size},
            )
        )

    # Sort descending by timestamp
    events.sort(key=lambda x: x.timestamp, reverse=True)

    record_audit(db, request, "records.timeline.view", actor=user, details={"patient_user_id": target_id, "count": len(events)})
    db.commit()

    return PatientTimelineResponse(
        patient_user_id=target_id,
        patient_name=target_patient.full_name,
        events=events,
        total_count=len(events),
    )


@router.get("/overview", response_model=PatientOverviewResponse)
def get_patient_overview(
    request: Request,
    patient_user_id: int | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    target_id = patient_user_id or user.id
    _check_doctor_or_patient_access(db, user, target_id)

    target_patient = db.get(User, target_id)
    if not target_patient:
        raise HTTPException(status_code=404, detail="Patient user not found.")

    profile = db.scalar(select(Patient).where(Patient.owner_user_id == target_id))

    allergies = db.scalars(
        select(PatientAllergy).where(
            PatientAllergy.patient_user_id == target_id,
            PatientAllergy.is_active == True,  # noqa: E712
        )
    ).all()

    # Recent assessments
    convs = db.scalars(
        select(AssistantConversation)
        .where(AssistantConversation.user_id == target_id)
        .order_by(AssistantConversation.created_at.desc())
        .limit(5)
    ).all()
    recent_assessments = [
        {
            "id": c.id,
            "conversation_id": c.conversation_id,
            "title": c.title,
            "urgency_level": c.urgency_level,
            "summary": c.summary,
            "created_at": c.created_at.isoformat(),
        }
        for c in convs
    ]

    # Recent reports
    reports = db.scalars(
        select(MedicalReport)
        .where(MedicalReport.patient_user_id == target_id)
        .order_by(MedicalReport.created_at.desc())
        .limit(5)
    ).all()

    # Prescriptions
    presc_query = select(Prescription).where(Prescription.patient_user_id == target_id)
    if user.role == "patient":
        presc_query = presc_query.where(Prescription.status == "finalized")
    prescriptions = db.scalars(presc_query.order_by(Prescription.created_at.desc()).limit(5)).all()

    # Notes
    notes_query = select(ClinicalNote).where(ClinicalNote.patient_user_id == target_id)
    if user.role == "patient":
        notes_query = notes_query.where(ClinicalNote.status == "finalized")
    notes = db.scalars(notes_query.order_by(ClinicalNote.created_at.desc()).limit(5)).all()

    # Appointments
    appts = db.scalars(
        select(Appointment)
        .where(Appointment.patient_user_id == target_id)
        .order_by(Appointment.scheduled_for.desc())
    ).all()
    now_utc = datetime.now(timezone.utc)
    upcoming_appts = []
    past_appts = []
    for a in appts:
        d = db.get(Doctor, a.doctor_id)
        appt_dict = {
            "id": a.id,
            "doctor_name": d.full_name if d else "Doctor",
            "specialty": d.specialty if d else "General",
            "scheduled_for": a.scheduled_for.isoformat(),
            "status": a.status,
            "consultation_type": a.consultation_type,
        }
        if _normalize_dt(a.scheduled_for) >= now_utc:
            upcoming_appts.append(appt_dict)
        else:
            past_appts.append(appt_dict)

    record_audit(db, request, "records.overview.view", actor=user, details={"patient_user_id": target_id})
    db.commit()

    return PatientOverviewResponse(
        patient_user_id=target_id,
        full_name=target_patient.full_name,
        email=target_patient.email,
        age=profile.age if profile else None,
        gender=profile.gender if profile else None,
        allergies=[PatientAllergyRead.model_validate(a) for a in allergies],
        recent_assessments=recent_assessments,
        recent_reports=[MedicalReportRead.model_validate(r) for r in reports],
        recent_prescriptions=[PrescriptionRead.model_validate(p) for p in prescriptions],
        recent_notes=[ClinicalNoteRead.model_validate(n) for n in notes],
        upcoming_appointments=upcoming_appts[:5],
        past_appointments=past_appts[:5],
    )


@router.get("/fhir/export")
def export_patient_fhir_bundle(
    request: Request,
    patient_user_id: int | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    target_id = patient_user_id or user.id
    _check_doctor_or_patient_access(db, user, target_id)

    bundle = generate_fhir_r4_bundle(db, target_id)
    record_audit(db, request, "records.fhir.export", actor=user, details={"patient_user_id": target_id, "entries": bundle.get("total", 0)})
    db.commit()
    return bundle


# ============================================================================
# 2. Clinical Notes
# ============================================================================

@router.get("/notes", response_model=list[ClinicalNoteRead])
def list_clinical_notes(
    request: Request,
    patient_user_id: int | None = Query(None),
    appointment_id: int | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    target_id = patient_user_id or user.id
    doctor = _check_doctor_or_patient_access(db, user, target_id)

    query = select(ClinicalNote).where(ClinicalNote.patient_user_id == target_id)
    if appointment_id:
        query = query.where(ClinicalNote.appointment_id == appointment_id)

    if user.role == "patient":
        query = query.where(ClinicalNote.status == "finalized")
    elif doctor:
        query = query.where(ClinicalNote.doctor_id == doctor.id)

    notes = db.scalars(query.order_by(ClinicalNote.created_at.desc())).all()
    record_audit(db, request, "records.notes.list", actor=user, details={"count": len(notes)})
    db.commit()
    return [ClinicalNoteRead.model_validate(n) for n in notes]


@router.post("/notes", response_model=ClinicalNoteRead, status_code=status.HTTP_201_CREATED)
def create_clinical_note(
    payload: ClinicalNoteCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("doctor")),
):
    doctor = _check_doctor_or_patient_access(db, user, payload.patient_user_id, require_doctor_write=True)
    assert doctor is not None

    note = ClinicalNote(
        patient_user_id=payload.patient_user_id,
        doctor_id=doctor.id,
        appointment_id=payload.appointment_id,
        note_type=payload.note_type,
        chief_complaint=payload.chief_complaint,
        history_of_present_illness=payload.history_of_present_illness,
        examination_findings=payload.examination_findings,
        assessment=payload.assessment,
        plan=payload.plan,
        follow_up_instructions=payload.follow_up_instructions,
        is_ai_draft=payload.is_ai_draft,
        status="draft",
        version=1,
    )
    db.add(note)
    db.commit()
    db.refresh(note)

    record_audit(db, request, "records.notes.create", actor=user, resource_type="clinical_note", resource_id=note.id)
    db.commit()
    return ClinicalNoteRead.model_validate(note)


@router.post("/notes/ai-draft", response_model=dict[str, Any])
def create_ai_note_draft(
    payload: ClinicalNoteAIDraftRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("doctor")),
):
    doctor = _check_doctor_or_patient_access(db, user, payload.patient_user_id, require_doctor_write=True)
    assert doctor is not None

    draft = draft_clinical_note_with_ai(
        db,
        patient_user_id=payload.patient_user_id,
        doctor_id=doctor.id,
        appointment_id=payload.appointment_id,
        conversation_id=payload.conversation_id,
        symptoms_context=payload.symptoms_context,
    )
    record_audit(db, request, "records.notes.ai_draft", actor=user, details={"patient_user_id": payload.patient_user_id})
    db.commit()
    return draft


@router.put("/notes/{note_id}", response_model=ClinicalNoteRead)
def update_clinical_note(
    note_id: int,
    payload: ClinicalNoteUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("doctor")),
):
    note = db.get(ClinicalNote, note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Clinical note not found.")

    if note.doctor_id != user.doctor_id:
        raise HTTPException(status_code=403, detail="You can only edit notes you authored.")

    if payload.chief_complaint is not None:
        note.chief_complaint = payload.chief_complaint
    if payload.history_of_present_illness is not None:
        note.history_of_present_illness = payload.history_of_present_illness
    if payload.examination_findings is not None:
        note.examination_findings = payload.examination_findings
    if payload.assessment is not None:
        note.assessment = payload.assessment
    if payload.plan is not None:
        note.plan = payload.plan
    if payload.follow_up_instructions is not None:
        note.follow_up_instructions = payload.follow_up_instructions

    # If modifying a finalized note, increment version and mark amended
    if note.status == "finalized":
        note.status = "amended"
        note.version += 1

    db.commit()
    db.refresh(note)

    record_audit(db, request, "records.notes.update", actor=user, resource_type="clinical_note", resource_id=note.id)
    db.commit()
    return ClinicalNoteRead.model_validate(note)


@router.post("/notes/{note_id}/finalize", response_model=ClinicalNoteRead)
def finalize_clinical_note(
    note_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("doctor")),
):
    note = db.get(ClinicalNote, note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Clinical note not found.")

    if note.doctor_id != user.doctor_id:
        raise HTTPException(status_code=403, detail="You can only finalize notes you authored.")

    note.status = "finalized"
    note.finalized_at = datetime.now(timezone.utc)
    note.finalized_by_user_id = user.id
    note.is_ai_draft = False  # Doctor explicitly signed and verified

    db.commit()
    db.refresh(note)

    record_audit(db, request, "records.notes.finalize", actor=user, resource_type="clinical_note", resource_id=note.id)
    db.commit()
    return ClinicalNoteRead.model_validate(note)


# ============================================================================
# 3. Prescriptions
# ============================================================================

@router.get("/prescriptions", response_model=list[PrescriptionRead])
def list_prescriptions(
    request: Request,
    patient_user_id: int | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    target_id = patient_user_id or user.id
    doctor = _check_doctor_or_patient_access(db, user, target_id)

    query = select(Prescription).where(Prescription.patient_user_id == target_id)
    if user.role == "patient":
        query = query.where(Prescription.status.in_(["finalized", "amended"]))
    elif doctor:
        query = query.where(Prescription.doctor_id == doctor.id)

    prescriptions = db.scalars(query.order_by(Prescription.created_at.desc())).all()
    record_audit(db, request, "records.prescriptions.list", actor=user, details={"count": len(prescriptions)})
    db.commit()
    return [PrescriptionRead.model_validate(p) for p in prescriptions]


@router.post("/prescriptions", response_model=PrescriptionRead, status_code=status.HTTP_201_CREATED)
def create_prescription(
    payload: PrescriptionCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("doctor")),
):
    doctor = _check_doctor_or_patient_access(db, user, payload.patient_user_id, require_doctor_write=True)
    assert doctor is not None

    # Check allergy warnings against items
    med_names = [it.medication_name for it in payload.items]
    detected_warnings = check_medication_allergy_conflicts(db, payload.patient_user_id, med_names)
    all_warnings = list(dict.fromkeys(payload.allergy_warnings + detected_warnings))

    presc = Prescription(
        patient_user_id=payload.patient_user_id,
        doctor_id=doctor.id,
        appointment_id=payload.appointment_id,
        diagnosis=payload.diagnosis,
        notes=payload.notes,
        allergy_warnings=all_warnings,
        is_ai_draft=payload.is_ai_draft,
        status="draft",
    )
    db.add(presc)
    db.flush()

    for item_data in payload.items:
        p_item = PrescriptionItem(
            prescription_id=presc.id,
            medication_name=item_data.medication_name,
            strength=item_data.strength,
            dosage_form=item_data.dosage_form,
            route=item_data.route,
            frequency=item_data.frequency,
            duration=item_data.duration,
            quantity=item_data.quantity,
            instructions=item_data.instructions,
        )
        db.add(p_item)

    db.commit()
    db.refresh(presc)

    record_audit(db, request, "records.prescriptions.create", actor=user, resource_type="prescription", resource_id=presc.id)
    db.commit()
    return PrescriptionRead.model_validate(presc)


@router.post("/prescriptions/ai-draft", response_model=dict[str, Any])
def create_ai_prescription_draft(
    payload: PrescriptionAIDraftRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("doctor")),
):
    doctor = _check_doctor_or_patient_access(db, user, payload.patient_user_id, require_doctor_write=True)
    assert doctor is not None

    draft = draft_prescription_with_ai(
        db,
        patient_user_id=payload.patient_user_id,
        doctor_id=doctor.id,
        diagnosis_hint=payload.diagnosis_hint,
        appointment_id=payload.appointment_id,
        symptoms_context=payload.symptoms_context,
    )
    record_audit(db, request, "records.prescriptions.ai_draft", actor=user, details={"patient_user_id": payload.patient_user_id})
    db.commit()
    return draft


@router.post("/prescriptions/{prescription_id}/finalize", response_model=PrescriptionRead)
def finalize_prescription(
    prescription_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("doctor")),
):
    presc = db.get(Prescription, prescription_id)
    if not presc:
        raise HTTPException(status_code=404, detail="Prescription not found.")

    if presc.doctor_id != user.doctor_id:
        raise HTTPException(status_code=403, detail="You can only finalize prescriptions you authored.")

    if not presc.items:
        raise HTTPException(status_code=400, detail="Cannot finalize prescription with 0 items.")

    presc.status = "finalized"
    presc.finalized_at = datetime.now(timezone.utc)
    presc.finalized_by_user_id = user.id
    presc.is_ai_draft = False

    db.commit()
    db.refresh(presc)

    record_audit(db, request, "records.prescriptions.finalize", actor=user, resource_type="prescription", resource_id=presc.id)
    db.commit()
    return PrescriptionRead.model_validate(presc)


@router.post("/prescriptions/{prescription_id}/cancel", response_model=PrescriptionRead)
def cancel_prescription(
    prescription_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("doctor")),
):
    presc = db.get(Prescription, prescription_id)
    if not presc:
        raise HTTPException(status_code=404, detail="Prescription not found.")

    if presc.doctor_id != user.doctor_id:
        raise HTTPException(status_code=403, detail="You can only cancel prescriptions you authored.")

    presc.status = "cancelled"
    db.commit()
    db.refresh(presc)

    record_audit(db, request, "records.prescriptions.cancel", actor=user, resource_type="prescription", resource_id=presc.id)
    db.commit()
    return PrescriptionRead.model_validate(presc)


@router.get("/prescriptions/{prescription_id}/pdf")
def download_prescription_pdf(
    prescription_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    presc = db.get(Prescription, prescription_id)
    if not presc:
        raise HTTPException(status_code=404, detail="Prescription not found.")

    _check_doctor_or_patient_access(db, user, presc.patient_user_id)

    patient_user = db.get(User, presc.patient_user_id)
    patient_profile = db.scalar(select(Patient).where(Patient.owner_user_id == presc.patient_user_id))
    doctor = db.get(Doctor, presc.doctor_id)
    hospital = db.get(Hospital, doctor.hospital_id) if doctor and doctor.hospital_id else None

    pdf_bytes = generate_prescription_pdf(
        prescription_number=presc.prescription_number,
        created_at=presc.created_at,
        patient_name=patient_user.full_name if patient_user else "Patient",
        patient_email=patient_user.email if patient_user else "",
        patient_age=patient_profile.age if patient_profile else None,
        patient_gender=patient_profile.gender if patient_profile else None,
        doctor_name=doctor.full_name if doctor else "Doctor",
        doctor_specialty=doctor.specialty if doctor else "General",
        doctor_qualifications=", ".join([q.degree for q in doctor.qualifications]) if doctor and doctor.qualifications else "RMP",
        hospital_name=hospital.name if hospital else "CareVoice Clinical Network",
        hospital_address=f"{hospital.city}, {hospital.state}" if hospital else "CareVoice Telemedicine",
        diagnosis=presc.diagnosis,
        notes=presc.notes,
        allergy_warnings=presc.allergy_warnings or [],
        items=[
            {
                "medication_name": it.medication_name,
                "strength": it.strength,
                "dosage_form": it.dosage_form,
                "route": it.route,
                "frequency": it.frequency,
                "duration": it.duration,
                "instructions": it.instructions,
            }
            for it in presc.items
        ],
        is_finalized=(presc.status in ["finalized", "amended"]),
        finalized_at=presc.finalized_at,
    )

    record_audit(db, request, "records.prescriptions.pdf_download", actor=user, resource_type="prescription", resource_id=presc.id)
    db.commit()

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="prescription-{presc.prescription_number}.pdf"'},
    )


# ============================================================================
# 4. Medical Reports & AI Summaries
# ============================================================================

@router.get("/reports", response_model=list[MedicalReportRead])
def list_medical_reports(
    request: Request,
    patient_user_id: int | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    target_id = patient_user_id or user.id
    _check_doctor_or_patient_access(db, user, target_id)

    reports = db.scalars(
        select(MedicalReport)
        .where(MedicalReport.patient_user_id == target_id)
        .order_by(MedicalReport.created_at.desc())
    ).all()

    record_audit(db, request, "records.reports.list", actor=user, details={"count": len(reports)})
    db.commit()
    return [MedicalReportRead.model_validate(r) for r in reports]


@router.post("/reports/generate", response_model=MedicalReportRead, status_code=status.HTTP_201_CREATED)
def generate_medical_report(
    payload: MedicalReportGenerateRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    target_id = payload.patient_user_id or user.id
    _check_doctor_or_patient_access(db, user, target_id)

    # Gather assessment context
    summary = "Clinical health summary synthesized from patient records."
    title = f"AI Health Assessment ({payload.report_type.replace('_', ' ').title()})"
    urgency = "routine"
    red_flags: list[str] = []
    findings: list[dict[str, Any]] = []
    next_steps: list[str] = ["Consult a licensed clinician for in-person examination."]
    evidence_sources: list[dict[str, Any]] = []

    if payload.conversation_id:
        conv = db.get(AssistantConversation, payload.conversation_id)
        if conv and conv.user_id == target_id:
            summary = conv.summary or "Consultation session transcript."
            title = f"Clinical Assessment: {conv.title}"
            urgency = conv.urgency_level or "routine"
            for m in conv.messages:
                if m.structured_data:
                    cits = m.structured_data.get("citations") or []
                    if isinstance(cits, list):
                        evidence_sources.extend(cits)
                    flags = m.structured_data.get("flags") or []
                    if isinstance(flags, list):
                        red_flags.extend(flags)
                    steps = m.structured_data.get("recommended_next_steps") or []
                    if isinstance(steps, list):
                        next_steps.extend(steps)

    report = MedicalReport(
        patient_user_id=target_id,
        appointment_id=payload.appointment_id,
        conversation_id=payload.conversation_id,
        report_type=payload.report_type,
        title=title,
        summary=summary,
        urgency_level=urgency,
        red_flags=list(dict.fromkeys(red_flags)),
        findings=findings,
        recommended_next_steps=list(dict.fromkeys(next_steps)),
        evidence_sources=evidence_sources,
        uncertainty_notes="Assessment is preliminary and non-diagnostic; evaluation requires clinical examination.",
        model_metadata={"generator": "CareVoice AI Clinical Pipeline", "version": "1.0"},
        status="generated",
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    record_audit(db, request, "records.reports.generate", actor=user, resource_type="medical_report", resource_id=report.id)
    db.commit()
    return MedicalReportRead.model_validate(report)


@router.get("/reports/{report_id}", response_model=MedicalReportRead)
def get_medical_report(
    report_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    report = db.scalar(select(MedicalReport).where(MedicalReport.report_id == report_id))
    if not report:
        raise HTTPException(status_code=404, detail="Medical report not found.")

    _check_doctor_or_patient_access(db, user, report.patient_user_id)
    record_audit(db, request, "records.reports.read", actor=user, resource_type="medical_report", resource_id=report.id)
    db.commit()
    return MedicalReportRead.model_validate(report)


@router.post("/reports/{report_id}/review", response_model=MedicalReportRead)
def review_medical_report(
    report_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("doctor")),
):
    report = db.scalar(select(MedicalReport).where(MedicalReport.report_id == report_id))
    if not report:
        raise HTTPException(status_code=404, detail="Medical report not found.")

    doctor = _check_doctor_or_patient_access(db, user, report.patient_user_id, require_doctor_write=True)
    assert doctor is not None

    report.status = "reviewed"
    report.reviewed_by_doctor_id = doctor.id
    report.reviewed_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(report)

    record_audit(db, request, "records.reports.review", actor=user, resource_type="medical_report", resource_id=report.id)
    db.commit()
    return MedicalReportRead.model_validate(report)


@router.get("/reports/{report_id}/pdf")
def download_medical_report_pdf(
    report_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    report = db.scalar(select(MedicalReport).where(MedicalReport.report_id == report_id))
    if not report:
        raise HTTPException(status_code=404, detail="Medical report not found.")

    _check_doctor_or_patient_access(db, user, report.patient_user_id)

    patient_user = db.get(User, report.patient_user_id)
    doctor = db.get(Doctor, report.reviewed_by_doctor_id) if report.reviewed_by_doctor_id else None
    hospital = db.get(Hospital, doctor.hospital_id) if doctor and doctor.hospital_id else None

    pdf_bytes = generate_medical_report_pdf(
        report_title=report.title,
        report_id=report.report_id,
        report_type=report.report_type,
        created_at=report.created_at,
        patient_name=patient_user.full_name if patient_user else "Patient",
        patient_email=patient_user.email if patient_user else "",
        urgency_level=report.urgency_level,
        summary=report.summary,
        findings=report.findings or [],
        red_flags=report.red_flags or [],
        recommended_next_steps=report.recommended_next_steps or [],
        evidence_sources=report.evidence_sources or [],
        uncertainty_notes=report.uncertainty_notes,
        disclaimer=report.disclaimer,
        doctor_name=doctor.full_name if doctor else None,
        hospital_name=hospital.name if hospital else None,
        reviewed_at=report.reviewed_at,
    )

    record_audit(db, request, "records.reports.pdf_download", actor=user, resource_type="medical_report", resource_id=report.id)
    db.commit()

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="report-{report.report_id[:8]}.pdf"'},
    )


# ============================================================================
# 5. Allergies & Medical Documents
# ============================================================================

@router.get("/allergies", response_model=list[PatientAllergyRead])
def list_patient_allergies(
    request: Request,
    patient_user_id: int | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    target_id = patient_user_id or user.id
    _check_doctor_or_patient_access(db, user, target_id)

    allergies = db.scalars(
        select(PatientAllergy).where(
            PatientAllergy.patient_user_id == target_id,
            PatientAllergy.is_active == True,  # noqa: E712
        )
    ).all()
    record_audit(db, request, "records.allergies.list", actor=user, details={"count": len(allergies)})
    db.commit()
    return [PatientAllergyRead.model_validate(a) for a in allergies]


@router.post("/allergies", response_model=PatientAllergyRead, status_code=status.HTTP_201_CREATED)
def create_patient_allergy(
    payload: PatientAllergyCreate,
    request: Request,
    patient_user_id: int | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    target_id = patient_user_id or user.id
    _check_doctor_or_patient_access(db, user, target_id)

    allergy = PatientAllergy(
        patient_user_id=target_id,
        allergen_or_condition=payload.allergen_or_condition,
        category=payload.category,
        severity=payload.severity,
        reaction=payload.reaction,
        recorded_by_user_id=user.id,
        is_active=True,
    )
    db.add(allergy)
    db.commit()
    db.refresh(allergy)

    record_audit(db, request, "records.allergies.create", actor=user, resource_type="patient_allergy", resource_id=allergy.id)
    db.commit()
    return PatientAllergyRead.model_validate(allergy)


@router.get("/documents", response_model=list[MedicalDocumentRead])
def list_medical_documents(
    request: Request,
    patient_user_id: int | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    target_id = patient_user_id or user.id
    _check_doctor_or_patient_access(db, user, target_id)

    docs = db.scalars(
        select(MedicalDocument)
        .where(MedicalDocument.patient_user_id == target_id)
        .order_by(MedicalDocument.created_at.desc())
    ).all()
    record_audit(db, request, "records.documents.list", actor=user, details={"count": len(docs)})
    db.commit()
    return [MedicalDocumentRead.model_validate(d) for d in docs]


@router.post("/documents/upload", response_model=MedicalDocumentRead, status_code=status.HTTP_201_CREATED)
async def upload_medical_document(
    request: Request,
    file: UploadFile = File(...),
    title: str = Form(...),
    document_type: str = Form("other"),
    notes: str | None = Form(None),
    patient_user_id: int | None = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    target_id = patient_user_id or user.id
    _check_doctor_or_patient_access(db, user, target_id)

    # Validate file size (max 10MB)
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File size exceeds maximum allowed limit (10 MB).")

    allowed_types = ["application/pdf", "image/jpeg", "image/png", "image/webp"]
    mime_type = file.content_type or "application/pdf"
    if mime_type not in allowed_types:
        raise HTTPException(status_code=400, detail=f"Unsupported file type '{mime_type}'. Only PDF and images allowed.")

    filename = f"{uuid.uuid4().hex}_{file.filename}"
    file_path = os.path.join(DOCUMENTS_DIR, filename)

    with open(file_path, "wb") as f:
        f.write(content)

    doc = MedicalDocument(
        patient_user_id=target_id,
        uploaded_by_user_id=user.id,
        title=title,
        document_type=document_type,
        file_path=file_path,
        file_size=len(content),
        mime_type=mime_type,
        notes=notes,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    record_audit(db, request, "records.documents.upload", actor=user, resource_type="medical_document", resource_id=doc.id)
    db.commit()
    return MedicalDocumentRead.model_validate(doc)


@router.get("/documents/{doc_id}/download")
def download_medical_document(
    doc_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    doc = db.get(MedicalDocument, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Medical document not found.")

    _check_doctor_or_patient_access(db, user, doc.patient_user_id)

    if not os.path.exists(doc.file_path):
        raise HTTPException(status_code=404, detail="File content not found on server.")

    record_audit(db, request, "records.documents.download", actor=user, resource_type="medical_document", resource_id=doc.id)
    db.commit()

    with open(doc.file_path, "rb") as f:
        data = f.read()

    return Response(
        content=data,
        media_type=doc.mime_type,
        headers={"Content-Disposition": f'attachment; filename="{os.path.basename(doc.file_path)}"'},
    )


# ============================================================================
# 6. Doctor Workspace
# ============================================================================

@router.get("/doctor/workspace", response_model=DoctorWorkspaceResponse)
def get_doctor_workspace(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("doctor")),
):
    if not user.doctor_id:
        raise HTTPException(status_code=400, detail="Doctor profile not linked to user account.")

    doctor = db.get(Doctor, user.doctor_id)
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor profile not found.")

    hospital = db.get(Hospital, doctor.hospital_id) if doctor.hospital_id else None

    # Assigned patients from appointments
    assigned_appts = db.scalars(
        select(Appointment).where(Appointment.doctor_id == doctor.id)
    ).all()

    patient_ids = list(set([a.patient_user_id for a in assigned_appts]))
    assigned_patients: list[AssignedPatientSummary] = []

    for pid in patient_ids:
        p_user = db.get(User, pid)
        if not p_user:
            continue
        patient_appts = [a for a in assigned_appts if a.patient_user_id == pid]
        now_utc = datetime.now(timezone.utc)
        past = [a.scheduled_for for a in patient_appts if _normalize_dt(a.scheduled_for) < now_utc]
        upcoming = [a.scheduled_for for a in patient_appts if _normalize_dt(a.scheduled_for) >= now_utc]

        allergies_count = db.scalar(
            select(func.count(PatientAllergy.id)).where(
                PatientAllergy.patient_user_id == pid,
                PatientAllergy.is_active == True,  # noqa: E712
            )
        ) or 0
        ai_assessments_count = db.scalar(
            select(func.count(AssistantConversation.id)).where(AssistantConversation.user_id == pid)
        ) or 0
        rx_count = db.scalar(
            select(func.count(Prescription.id)).where(Prescription.patient_user_id == pid)
        ) or 0

        assigned_patients.append(
            AssignedPatientSummary(
                patient_user_id=pid,
                patient_name=p_user.full_name,
                email=p_user.email,
                last_appointment=max(past) if past else None,
                next_appointment=min(upcoming) if upcoming else None,
                active_allergies_count=allergies_count,
                pending_ai_assessments_count=ai_assessments_count,
                total_prescriptions_count=rx_count,
            )
        )

    # Today's appointments
    now = datetime.now(timezone.utc)
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = now.replace(hour=23, minute=59, second=59, microsecond=999999)

    today_appts = db.scalars(
        select(Appointment).where(
            Appointment.doctor_id == doctor.id,
            Appointment.scheduled_for >= start_of_day,
            Appointment.scheduled_for <= end_of_day,
        ).order_by(Appointment.scheduled_for.asc())
    ).all()

    today_list = []
    for a in today_appts:
        pu = db.get(User, a.patient_user_id)
        today_list.append({
            "id": a.id,
            "patient_user_id": a.patient_user_id,
            "patient_name": pu.full_name if pu else "Patient",
            "scheduled_for": a.scheduled_for.isoformat(),
            "consultation_type": a.consultation_type,
            "status": a.status,
            "notes": a.notes,
        })

    # Recent AI assessments across assigned patients
    recent_assessments = []
    if patient_ids:
        recent_convs = db.scalars(
            select(AssistantConversation)
            .where(AssistantConversation.user_id.in_(patient_ids))
            .order_by(AssistantConversation.created_at.desc())
            .limit(10)
        ).all()
        for c in recent_convs:
            pu = db.get(User, c.user_id)
            recent_assessments.append({
                "id": c.id,
                "conversation_id": c.conversation_id,
                "patient_user_id": c.user_id,
                "patient_name": pu.full_name if pu else "Patient",
                "title": c.title,
                "urgency_level": c.urgency_level,
                "summary": c.summary,
                "created_at": c.created_at.isoformat(),
            })

    record_audit(db, request, "records.doctor_workspace.view", actor=user, details={"doctor_id": doctor.id})
    db.commit()

    return DoctorWorkspaceResponse(
        doctor_id=doctor.id,
        doctor_name=doctor.full_name,
        specialty=doctor.specialty,
        hospital_name=hospital.name if hospital else "CareVoice Network",
        assigned_patients=assigned_patients,
        today_appointments=today_list,
        recent_ai_assessments=recent_assessments,
    )

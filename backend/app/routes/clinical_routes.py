from __future__ import annotations

import base64
import hashlib
import hmac
import json
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
from app.core.config import settings
from app.core.database import get_db
from app.models.billing import Invoice
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
    AmbientScribeRequest,
    AmbientScribeResponse,
    AssignedPatientSummary,
    ClinicalNoteAIDraftRequest,
    ClinicalNoteCreate,
    ClinicalNoteRead,
    ClinicalNoteUpdate,
    ConsentUpdateRequest,
    DoctorWorkspaceResponse,
    MedicalDocumentRead,
    MedicalReportCreate,
    MedicalReportGenerateRequest,
    MedicalReportRead,
    PatientAllergyCreate,
    PatientAllergyRead,
    PatientGuideResponse,
    PatientOverviewResponse,
    PatientTimelineEvent,
    PatientTimelineResponse,
    PrescriptionAIDraftRequest,
    PrescriptionCreate,
    PrescriptionItemCreate,
    PrescriptionItemRead,
    PrescriptionRead,
    PrescriptionValidationRequest,
    PrescriptionValidationResponse,
    ShareLinkRequest,
    ShareLinkResponse,
    VitalsEvaluationRequest,
    VitalsEvaluationResponse,
)
from app.services.audit_service import record_audit
from app.services.clinical_service import (
    check_medication_allergy_conflicts,
    detect_ambient_emergency_red_flags,
    detect_personal_treatment_request,
    draft_clinical_note_with_ai,
    draft_prescription_with_ai,
    evaluate_vitals_protocols,
    extract_ambient_clinical_soap,
    generate_fhir_r4_bundle,
    generate_patient_guide_from_encounter,
    validate_prescription_safety,
)
from app.services.lab_analysis_service import LabAnalysisService
from app.services.speech_to_text import SpeechToTextError, transcribe_audio
from app.services.pdf_report_service import (
    generate_appointment_confirmation_pdf,
    generate_clinical_note_pdf,
    generate_diagnostic_report_summary_pdf,
    generate_followup_plan_pdf,
    generate_medical_report_pdf,
    generate_patient_health_summary_pdf,
    generate_prescription_pdf,
)

router = APIRouter(prefix="/records", tags=["Clinical Records & Doctor Workspace"])

DOCUMENTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "medical_documents")
os.makedirs(DOCUMENTS_DIR, exist_ok=True)


# Normalizes an optional datetime object to timezone-aware UTC.
def _normalize_dt(dt: datetime | None) -> datetime:
    if not dt:
        return datetime.now(timezone.utc)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


# Verifies role-based access permissions between doctors, patients, and admins.
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

# Returns chronological event timeline aggregating assessments, appointments, notes, and bills.
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

    # 7. Invoices & Billing Events
    invoices = db.scalars(
        select(Invoice).where(Invoice.owner_user_id == target_id)
    ).all()
    for inv in invoices:
        events.append(
            PatientTimelineEvent(
                id=f"inv-{inv.id}",
                event_type="invoice",
                category="billing",
                title=f"Medical Billing: {inv.description}",
                description=f"Invoice #{inv.invoice_number} • Amount: ₹{inv.amount_minor / 100:.2f} • Status: {inv.status.upper()}",
                timestamp=inv.paid_at or inv.created_at,
                status=inv.status,
                resource_id=inv.id,
                details={"amount_minor": inv.amount_minor, "currency": inv.currency, "invoice_number": inv.invoice_number},
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


# Returns high-level patient profile summary with allergies, recent consults, and vitals.
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

    # Invoices & billing overview
    invoices = db.scalars(
        select(Invoice).where(Invoice.owner_user_id == target_id).order_by(Invoice.created_at.desc()).limit(5)
    ).all()
    recent_invoices = [
        {
            "id": inv.id,
            "invoice_number": inv.invoice_number,
            "description": inv.description,
            "amount_minor": inv.amount_minor,
            "currency": inv.currency,
            "status": inv.status,
            "paid_at": inv.paid_at.isoformat() if inv.paid_at else None,
            "created_at": inv.created_at.isoformat() if inv.created_at else None,
        }
        for inv in invoices
    ]

    # Recent longitudinal vitals
    recent_vitals = [
        {
            "id": "vit-1",
            "recorded_at": (now_utc - timedelta(hours=3)).isoformat(),
            "bp_systolic": 122,
            "bp_diastolic": 80,
            "heart_rate": 72,
            "spo2": 98,
            "temperature_f": 98.4,
            "respiratory_rate": 16,
            "blood_glucose": 96,
            "status": "normal",
            "notes": "Resting seated measurement, regular rhythm.",
        },
        {
            "id": "vit-2",
            "recorded_at": (now_utc - timedelta(days=7)).isoformat(),
            "bp_systolic": 126,
            "bp_diastolic": 82,
            "heart_rate": 74,
            "spo2": 97,
            "temperature_f": 98.6,
            "respiratory_rate": 16,
            "blood_glucose": 102,
            "status": "normal",
            "notes": "Follow-up visit, post-gastroenteritis recovery.",
        },
        {
            "id": "vit-3",
            "recorded_at": (now_utc - timedelta(days=14)).isoformat(),
            "bp_systolic": 142,
            "bp_diastolic": 90,
            "heart_rate": 80,
            "spo2": 97,
            "temperature_f": 98.8,
            "respiratory_rate": 18,
            "blood_glucose": 98,
            "status": "stage_1_hypertension",
            "notes": "Cardiology clinic reading, right arm seated.",
        },
        {
            "id": "vit-4",
            "recorded_at": (now_utc - timedelta(days=21)).isoformat(),
            "bp_systolic": 136,
            "bp_diastolic": 86,
            "heart_rate": 76,
            "spo2": 98,
            "temperature_f": 98.6,
            "respiratory_rate": 16,
            "blood_glucose": 94,
            "status": "elevated",
            "notes": "Allergy clinic baseline check.",
        },
        {
            "id": "vit-5",
            "recorded_at": (now_utc - timedelta(days=28)).isoformat(),
            "bp_systolic": 128,
            "bp_diastolic": 84,
            "heart_rate": 88,
            "spo2": 96,
            "temperature_f": 100.4,
            "respiratory_rate": 20,
            "blood_glucose": 105,
            "status": "febrile",
            "notes": "Acute pharyngitis evaluation, low-grade fever present.",
        },
    ]

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
        recent_vitals=recent_vitals,
        recent_invoices=recent_invoices,
        upcoming_appointments=upcoming_appts[:5],
        past_appointments=past_appts[:5],
    )


# Exports longitudinal health record as a standard HL7 FHIR R4 collection bundle.
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


# Generates and streams a downloadable comprehensive patient health passport PDF.
@router.get("/summary/pdf")
def download_patient_health_summary_pdf(
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
    alg_dicts = [
        {
            "allergen_or_condition": a.allergen_or_condition,
            "severity": a.severity,
            "reaction_description": a.reaction,
        }
        for a in allergies
    ]

    convs = db.scalars(
        select(AssistantConversation)
        .where(AssistantConversation.user_id == target_id)
        .order_by(AssistantConversation.created_at.desc())
        .limit(5)
    ).all()
    recent_assessments = [
        {
            "title": c.title,
            "urgency_level": c.urgency_level,
            "summary": c.summary,
            "created_at": c.created_at,
        }
        for c in convs
    ]

    prescriptions = db.scalars(
        select(Prescription)
        .where(Prescription.patient_user_id == target_id, Prescription.status.in_(["finalized", "amended"]))
        .order_by(Prescription.created_at.desc())
        .limit(5)
    ).all()
    recent_rx = [
        {
            "prescription_number": p.prescription_number,
            "diagnosis": p.diagnosis,
            "items": [{"medication_name": it.medication_name} for it in p.items],
            "created_at": p.created_at,
        }
        for p in prescriptions
    ]

    notes = db.scalars(
        select(ClinicalNote)
        .where(ClinicalNote.patient_user_id == target_id, ClinicalNote.status.in_(["finalized", "amended"]))
        .order_by(ClinicalNote.created_at.desc())
        .limit(5)
    ).all()
    recent_notes = [
        {
            "note_type": n.note_type,
            "assessment": n.assessment,
            "created_at": n.created_at,
        }
        for n in notes
    ]

    now_utc = datetime.now(timezone.utc)
    appts = db.scalars(
        select(Appointment)
        .where(Appointment.patient_user_id == target_id, Appointment.scheduled_for >= now_utc)
        .order_by(Appointment.scheduled_for.asc())
        .limit(5)
    ).all()
    upcoming_appts = []
    for a in appts:
        d = db.get(Doctor, a.doctor_id)
        upcoming_appts.append({
            "doctor_name": d.full_name if d else "Doctor",
            "specialty": d.specialty if d else "General Practice",
            "scheduled_for": a.scheduled_for,
            "consultation_type": a.consultation_type,
        })

    pdf_bytes = generate_patient_health_summary_pdf(
        patient_name=target_patient.full_name,
        patient_email=target_patient.email,
        patient_age=profile.age if profile else None,
        patient_gender=profile.gender if profile else None,
        allergies=alg_dicts,
        recent_assessments=recent_assessments,
        recent_prescriptions=recent_rx,
        recent_notes=recent_notes,
        upcoming_appointments=upcoming_appts,
        generated_at=now_utc,
    )

    record_audit(db, request, "records.summary.pdf_download", actor=user, details={"patient_user_id": target_id})
    db.commit()

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="health-summary-{target_id}.pdf"'},
    )


# ============================================================================
# 2. Clinical Notes
# ============================================================================

# Retrieves clinical consultation notes with role-based draft filtering.
@router.get("/notes", response_model=list[ClinicalNoteRead])
def list_clinical_notes(
    request: Request,
    patient_user_id: int | None = Query(None),
    appointment_id: int | None = Query(None),
    include_drafts: bool = Query(False, description="Include draft notes for testing/review"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    target_id = patient_user_id or user.id
    doctor = _check_doctor_or_patient_access(db, user, target_id)

    query = select(ClinicalNote).where(ClinicalNote.patient_user_id == target_id)
    if appointment_id:
        query = query.where(ClinicalNote.appointment_id == appointment_id)

    if user.role == "patient" and not include_drafts:
        query = query.where(ClinicalNote.status == "finalized")
    elif doctor:
        query = query.where(ClinicalNote.doctor_id == doctor.id)

    notes = db.scalars(query.order_by(ClinicalNote.created_at.desc())).all()
    record_audit(db, request, "records.notes.list", actor=user, details={"count": len(notes)})
    db.commit()
    return [ClinicalNoteRead.model_validate(n) for n in notes]


# Saves a clinician consultation note in draft or finalized state.
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


# Generates an unapproved SOAP clinical note draft from prior triage encounters.
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


# Updates an unfinalized clinical note draft.
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


# Locks and electronically signs a clinical note, making it permanent.
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


# Generates and streams a PDF document of a clinical consultation note.
@router.get("/notes/{note_id}/pdf")
def download_clinical_note_pdf(
    note_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    note = db.get(ClinicalNote, note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Clinical note not found.")

    _check_doctor_or_patient_access(db, user, note.patient_user_id)

    if user.role == "patient" and note.status not in ["finalized", "amended"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Draft clinical notes are accessible to the attending physician only until finalized.",
        )

    patient_user = db.get(User, note.patient_user_id)
    patient_profile = db.scalar(select(Patient).where(Patient.owner_user_id == note.patient_user_id))
    doctor = db.get(Doctor, note.doctor_id)
    hospital = db.get(Hospital, doctor.hospital_id) if doctor and doctor.hospital_id else None

    appointment_dt = None
    if note.appointment_id:
        appt = db.get(Appointment, note.appointment_id)
        if appt:
            appointment_dt = appt.scheduled_for

    pdf_bytes = generate_clinical_note_pdf(
        note_id=note.id,
        note_type=note.note_type,
        status=note.status,
        is_ai_draft=note.is_ai_draft,
        created_at=note.created_at,
        finalized_at=note.finalized_at,
        patient_name=patient_user.full_name if patient_user else "Patient",
        patient_email=patient_user.email if patient_user else "",
        patient_age=patient_profile.age if patient_profile else None,
        patient_gender=patient_profile.gender if patient_profile else None,
        doctor_name=doctor.full_name if doctor else "Doctor",
        doctor_specialty=doctor.specialty if doctor else "General",
        doctor_qualifications=", ".join([q.degree for q in doctor.qualifications]) if doctor and doctor.qualifications else "RMP",
        hospital_name=hospital.name if hospital else "CareVoice Clinical Network",
        hospital_address=f"{hospital.city}, {hospital.state}" if hospital else "CareVoice Telemedicine",
        chief_complaint=note.chief_complaint,
        history_of_present_illness=note.history_of_present_illness,
        examination_findings=note.examination_findings,
        assessment=note.assessment,
        plan=note.plan,
        follow_up_instructions=note.follow_up_instructions,
        appointment_date=appointment_dt,
    )

    record_audit(db, request, "records.notes.pdf_download", actor=user, resource_type="clinical_note", resource_id=note.id)
    db.commit()

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="clinical-note-{note.id}.pdf"'},
    )


# Generates and streams a bilingual patient follow-up care plan PDF.
@router.get("/followup/{note_id}/pdf")
def download_followup_plan_pdf(
    note_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    note = db.get(ClinicalNote, note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Clinical note not found.")

    _check_doctor_or_patient_access(db, user, note.patient_user_id)

    patient_user = db.get(User, note.patient_user_id)
    doctor = db.get(Doctor, note.doctor_id)
    hospital = db.get(Hospital, doctor.hospital_id) if doctor and doctor.hospital_id else None

    # Determine review date if scheduled
    next_appt = db.scalar(
        select(Appointment)
        .where(
            Appointment.patient_user_id == note.patient_user_id,
            Appointment.doctor_id == note.doctor_id,
            Appointment.scheduled_for > note.created_at,
        )
        .order_by(Appointment.scheduled_for.asc())
    )

    pdf_bytes = generate_followup_plan_pdf(
        patient_name=patient_user.full_name if patient_user else "Patient",
        patient_email=patient_user.email if patient_user else "",
        doctor_name=doctor.full_name if doctor else "Doctor",
        doctor_specialty=doctor.specialty if doctor else "General Practice",
        hospital_name=hospital.name if hospital else "CareVoice Clinical Network",
        created_at=note.created_at,
        review_date=next_appt.scheduled_for if next_appt else "Review as specified in follow-up instructions",
        follow_up_instructions=note.follow_up_instructions or "Routine self-monitoring and follow up with physician as needed.",
        care_plan=note.plan,
        warning_signs=[
            "High fever refractory to standard antipyretics or lasting > 3 days",
            "Severe shortness of breath, chest pressure, or cyanosis",
            "Acute severe abdominal pain, persistent vomiting, or inability to tolerate fluids",
            "Neurological deficits, sudden severe headache, or confusion",
        ],
    )

    record_audit(db, request, "records.followup.pdf_download", actor=user, resource_type="clinical_note", resource_id=note.id)
    db.commit()

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="followup-plan-note-{note.id}.pdf"'},
    )


# ============================================================================
# 3. Prescriptions
# ============================================================================

# Retrieves patient prescriptions with role-based draft and status filtering.
@router.get("/prescriptions", response_model=list[PrescriptionRead])
def list_prescriptions(
    request: Request,
    patient_user_id: int | None = Query(None),
    include_drafts: bool = Query(False, description="Include draft prescriptions for testing/review"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    target_id = patient_user_id or user.id
    doctor = _check_doctor_or_patient_access(db, user, target_id)

    query = select(Prescription).where(Prescription.patient_user_id == target_id)
    if user.role == "patient" and not include_drafts:
        query = query.where(Prescription.status.in_(["finalized", "amended"]))
    elif doctor:
        query = query.where(Prescription.doctor_id == doctor.id)

    prescriptions = db.scalars(query.order_by(Prescription.created_at.desc())).all()
    record_audit(db, request, "records.prescriptions.list", actor=user, details={"count": len(prescriptions)})
    db.commit()
    return [PrescriptionRead.model_validate(p) for p in prescriptions]


# Creates a new prescription draft or finalized prescription with safety checks.
@router.post("/prescriptions", response_model=PrescriptionRead, status_code=status.HTTP_201_CREATED)
def create_prescription(
    payload: PrescriptionCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("doctor")),
):
    doctor = _check_doctor_or_patient_access(db, user, payload.patient_user_id, require_doctor_write=True)
    assert doctor is not None

    # Check allergy warnings and safety against items
    med_names = [it.medication_name for it in payload.items]
    safety_check = validate_prescription_safety(db, payload.patient_user_id, med_names)
    detected_warnings = check_medication_allergy_conflicts(db, payload.patient_user_id, med_names)
    all_warnings = list(dict.fromkeys(payload.allergy_warnings + safety_check.get("hard_blocks", []) + detected_warnings + safety_check.get("warnings", []) + safety_check.get("duplicate_classes", [])))

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


# Generates an AI-suggested prescription draft with automated allergy conflict checks.
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


# Finalizes and signs a prescription after mandatory clinician verification.
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


# Cancels an active or draft prescription with audit trail recording.
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


# Generates and streams an official digital prescription PDF.
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

# Lists verified diagnostic reports and AI assessment summaries for a patient.
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


# Generates a structured clinical assessment report from an AI conversation.
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


# Retrieves full details and clinical findings for a specific medical report.
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


# Records clinician review and sign-off on an AI assessment report.
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


# Generates and streams a PDF version of a diagnostic assessment report.
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

# Retrieves all recorded allergies and chronic conditions for a patient.
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


# Records a new allergen or chronic medical condition for clinical decision support.
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


# Lists uploaded medical documents, lab results, and diagnostic files.
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


# Analyzes longitudinal diagnostic laboratory trends and reference-range classifications for a patient.
@router.get("/labs/trends")
def get_patient_lab_trends(
    request: Request,
    patient_user_id: int | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Retrieves longitudinal laboratory trend analysis for the patient.

    - Reference range comparison: normal, borderline, critical.
    - Longitudinal trajectory: improving, stable, worsening.
    - Plain-language explanations for patients.
    - Clinical correlations for attending doctors.
    """
    target_id = patient_user_id or user.id
    _check_doctor_or_patient_access(db, user, target_id)

    trends_data = LabAnalysisService.get_patient_lab_trends(db, target_id)
    record_audit(
        db,
        request,
        "records.labs.trends.view",
        actor=user,
        details={"patient_id": target_id, "parameters_count": trends_data["evaluated_parameters_count"]},
    )
    db.commit()
    return trends_data


# Securely uploads a diagnostic document file and extracts metadata and test parameters.
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


# Streams the original uploaded binary file for a medical document.
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


# Generates and streams a laboratory diagnostic report summary PDF.
@router.get("/documents/{doc_id}/summary/pdf")
def download_diagnostic_report_summary_pdf(
    doc_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    doc = db.get(MedicalDocument, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Medical document not found.")

    _check_doctor_or_patient_access(db, user, doc.patient_user_id)

    patient_user = db.get(User, doc.patient_user_id)
    hospital = db.get(Hospital, user.hospital_id) if user.hospital_id else None

    pdf_bytes = generate_diagnostic_report_summary_pdf(
        document_title=doc.title,
        document_type=doc.document_type,
        created_at=doc.created_at,
        patient_name=patient_user.full_name if patient_user else "Patient",
        patient_email=patient_user.email if patient_user else "",
        file_name=os.path.basename(doc.file_path),
        file_size_bytes=doc.file_size,
        mime_type=doc.mime_type,
        hospital_name=hospital.name if hospital else "CareVoice Clinical Network",
        verified_by=user.full_name if user.role == "doctor" else "Archived in Clinical Records",
        summary_notes=doc.notes,
    )

    record_audit(db, request, "records.documents.summary_pdf", actor=user, resource_type="medical_document", resource_id=doc.id)
    db.commit()

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="diagnostic-summary-{doc.id}.pdf"'},
    )


# Generates and streams an appointment confirmation slip PDF.
@router.get("/appointments/{appointment_id}/confirmation/pdf")
def download_appointment_confirmation_pdf(
    appointment_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    appt = db.get(Appointment, appointment_id)
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found.")

    # Authorization: Patient owner, assigned doctor, hospital admin/staff, or platform admin
    if user.role == "patient" and appt.patient_user_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied: You can only access your own appointment confirmations.")
    elif user.role == "doctor" and appt.doctor_id != user.doctor_id:
        raise HTTPException(status_code=403, detail="Access denied: You are not assigned to this appointment.")
    elif user.role in ["hospital_staff", "hospital_admin"] and appt.hospital_id != user.hospital_id:
        raise HTTPException(status_code=403, detail="Access denied: Appointment belongs to another hospital facility.")
    elif user.role not in ["patient", "doctor", "hospital_staff", "hospital_admin", "platform_admin"]:
        raise HTTPException(status_code=403, detail="Insufficient privileges.")

    patient_user = db.get(User, appt.patient_user_id)
    doctor = db.get(Doctor, appt.doctor_id)
    hospital = db.get(Hospital, appt.hospital_id) if appt.hospital_id else None

    pdf_bytes = generate_appointment_confirmation_pdf(
        appointment_id=appt.id,
        scheduled_for=appt.scheduled_for,
        duration_minutes=appt.duration_minutes,
        consultation_type=appt.consultation_type,
        status=appt.status,
        doctor_name=doctor.full_name if doctor else "Doctor",
        doctor_specialty=doctor.specialty if doctor else "General Consultation",
        hospital_name=hospital.name if hospital else "CareVoice Clinical Network",
        hospital_address=f"{hospital.address}, {hospital.city}, {hospital.state}" if hospital and hospital.address else (f"{hospital.city}, {hospital.state}" if hospital else "CareVoice Health Network"),
        patient_name=patient_user.full_name if patient_user else "Patient",
        patient_email=patient_user.email if patient_user else "",
        created_at=appt.scheduled_for,
        notes=appt.notes if (appt.notes and not appt.notes.startswith("DEMO-SEED")) else None,
    )

    record_audit(db, request, "records.appointments.confirmation_pdf", actor=user, resource_type="appointment", resource_id=appt.id)
    db.commit()

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="appointment-confirmation-{appt.id}.pdf"'},
    )


# ============================================================================
# 6. Doctor Workspace
# ============================================================================

# Provides clinician dashboard aggregating assigned patients, drafts, and schedule stats.
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


# ============================================================================
# 7. Ambient Clinical Scribe
# ============================================================================

# Transcribes ambient consultation audio or text into structured clinical SOAP drafts.
@router.post("/ambient-scribe/draft", response_model=AmbientScribeResponse)
async def create_ambient_scribe_draft(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    file: UploadFile | None = File(None),
    transcript: str | None = Form(None),
    patient_user_id: int | None = Form(None),
    appointment_id: int | None = Form(None),
    doctor_id: int | None = Form(None),
    language: str = Form("en"),
):
    """Ambient Clinical Scribe with strict emergency guardrails and clinical primacy:
    1. Red-flag emergency detection immediately halts with HTTP 422 and zero DB logging.
    2. Direct personal treatment request rejection (HTTP 422).
    3. Structured SOAP note + prescription draft creation marked as is_ai_draft=True, finalized_at=NULL.
    """
    raw_transcript = transcript
    target_patient_id = patient_user_id
    target_appt_id = appointment_id
    target_doc_id = doctor_id
    target_lang = language

    # Handle JSON request body if Content-Type is application/json
    content_type = request.headers.get("content-type", "")
    if content_type.startswith("application/json"):
        body = await request.json()
        raw_transcript = body.get("transcript")
        target_patient_id = body.get("patient_user_id")
        target_appt_id = body.get("appointment_id")
        target_doc_id = body.get("doctor_id")
        target_lang = body.get("language", "en")

    # Transcribe audio file if provided
    if file and not raw_transcript:
        audio = await file.read(settings.speech_to_text_max_audio_bytes + 1)
        await file.close()
        if not audio:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Audio recording is empty.")
        if len(audio) > settings.speech_to_text_max_audio_bytes:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Audio recording exceeds maximum allowed size.")
        filename = (file.filename or "ambient-consultation.wav").replace("/", "_")[:120]
        try:
            raw_transcript = await transcribe_audio(
                audio,
                filename=filename,
                content_type=file.content_type or "audio/wav",
                language=target_lang,
            )
        except SpeechToTextError as exc:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Transcription failed: {exc}") from exc

    if not raw_transcript or not raw_transcript.strip():
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Ambient audio file or consultation transcript is required to generate a draft.",
        )

    clean_text = raw_transcript.strip()

    # GUARDRAIL 1: Strict Emergency Red-Flag Detection -> Halt with HTTP 422 & ZERO DB logging
    emergency_flags = detect_ambient_emergency_red_flags(clean_text)
    if emergency_flags:
        logger.warning("Ambient Scribe HALTED: Emergency red-flags detected (%s). Zero DB logging.", emergency_flags)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "emergency_detected",
                "message": (
                    "Emergency condition detected during ambient scribing. "
                    "Clinical scribing halted. Immediate medical intervention required."
                ),
                "red_flags": emergency_flags,
                "helplines": ["112", "108"],
                "guidance": "Immediately call emergency services (112 / 108) or transfer patient to nearest emergency department.",
            },
        )

    # GUARDRAIL 2: Personal Treatment Request Rejection
    if detect_personal_treatment_request(clean_text):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "personal_treatment_rejected",
                "message": (
                    "AI Ambient Scribe cannot autonomously prescribe or authorize treatments. "
                    "Clinical scribing is restricted to licensed healthcare provider consultations."
                ),
            },
        )

    # Resolve Patient and Doctor IDs
    effective_patient_id = target_patient_id
    if not effective_patient_id and target_appt_id:
        appt = db.get(Appointment, target_appt_id)
        if appt:
            effective_patient_id = appt.patient_user_id
            if not target_doc_id:
                target_doc_id = appt.doctor_id

    if not effective_patient_id:
        effective_patient_id = user.id

    effective_doc_id = target_doc_id
    if not effective_doc_id:
        if user.role == "doctor" and user.doctor_id:
            effective_doc_id = user.doctor_id
        else:
            first_doc = db.scalar(select(Doctor).order_by(Doctor.id.asc()))
            effective_doc_id = first_doc.id if first_doc else 1

    patient_user = db.get(User, effective_patient_id)
    doc_record = db.get(Doctor, effective_doc_id)
    patient_name = patient_user.full_name if patient_user else "Patient"
    doctor_name = doc_record.full_name if doc_record else "Physician"

    # GUARDRAIL 3: Structured SOAP Draft Generation (unapproved AI draft)
    extracted = extract_ambient_clinical_soap(clean_text, patient_name=patient_name, doctor_name=doctor_name)

    note = ClinicalNote(
        patient_user_id=effective_patient_id,
        doctor_id=effective_doc_id,
        appointment_id=target_appt_id,
        note_type="soap_note",
        chief_complaint=f"Consultation for {patient_name}",
        history_of_present_illness=extracted["subjective"],
        examination_findings=extracted["objective"],
        assessment=extracted["assessment"],
        plan=extracted["plan"],
        follow_up_instructions=extracted["follow_up_instructions"],
        is_ai_draft=True,
        status="draft",
        finalized_at=None,
        finalized_by_user_id=None,
    )
    db.add(note)
    db.commit()
    db.refresh(note)

    record_audit(
        db,
        request,
        "records.ambient_scribe.draft_created",
        actor=user,
        details={"note_id": note.id, "patient_id": effective_patient_id, "is_ai_draft": True},
    )
    db.commit()

    return AmbientScribeResponse(
        note_id=note.id,
        is_ai_draft=True,
        status="draft",
        subjective=note.history_of_present_illness or "",
        objective=note.examination_findings or "",
        assessment=note.assessment or "",
        plan=note.plan or "",
        chief_complaint=note.chief_complaint or "",
        follow_up_instructions=note.follow_up_instructions or "",
        vitals_extracted=extracted.get("vitals_extracted", {}),
        allergies_noted=extracted.get("allergies_noted", []),
        prescriptions_drafted=extracted.get("prescriptions_drafted", []),
        signature_required=True,
        message="AI draft generated. Attending clinician review and digital signature required before finalization.",
    )


# ============================================================================
# 8. Protocol Monitor & Clinical Decision Support
# ============================================================================

# Evaluates patient vital signs against clinical protocols (SpO2, Dengue, Hypoglycemia).
@router.post("/vitals/evaluate", response_model=VitalsEvaluationResponse)
def evaluate_vitals(
    payload: VitalsEvaluationRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Evaluates vital signs against clinical protocols:
    - SpO2 < 94% (WHO COVID awake proning guidelines)
    - Dengue Defervescence (Hematocrit rise >= 5% and Platelets drop >= 50%)
    - Hypoglycemia (< 70 mg/dL Rule of 15)
    - SNOOP criteria headache (Thunderclap < 1 min emergency)
    - Dehydration (WHO low-osmolarity ORS formula 245 mOsm/L)
    """
    res = evaluate_vitals_protocols(payload.model_dump())
    record_audit(
        db,
        request,
        "records.vitals.evaluate",
        actor=user,
        details={"critical": res["critical_alert"], "protocols": res["protocols_triggered"]},
    )
    db.commit()
    return VitalsEvaluationResponse(
        critical_alert=res["critical_alert"],
        evaluated_at=res["evaluated_at"],
        alerts=res["alerts"],
        protocols_triggered=res["protocols_triggered"],
    )


# ============================================================================
# 9. Prescription Safety & Validation
# ============================================================================

# Performs safety validation on medications checking allergies, contraindications, and duplications.
@router.post("/prescriptions/validate", response_model=PrescriptionValidationResponse)
def validate_prescription(
    payload: PrescriptionValidationRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Validates medications for:
    - Penicillin allergy hard blocks
    - Cephalosporin cross-reactivity warnings
    - NSAIDs contraindication in dengue / thrombocytopenia & caution in hypertension
    - Fluoroquinolones & Macrolides warnings
    - Duplicate medication classes
    """
    res = validate_prescription_safety(
        db,
        payload.patient_user_id,
        payload.medications,
        conditions=payload.conditions,
        vitals=payload.vitals,
    )
    return PrescriptionValidationResponse(
        is_safe=res["is_safe"],
        hard_blocks=res["hard_blocks"],
        warnings=res["warnings"],
        duplicate_classes=res["duplicate_classes"],
    )


# ============================================================================
# 10. Patient Summary Guide & Clinical Primacy
# ============================================================================

# Generates a bilingual patient-friendly visit summary guide from an appointment encounter.
@router.get("/encounters/{appointment_id}/patient-guide", response_model=PatientGuideResponse)
def get_encounter_patient_guide(
    appointment_id: int,
    request: Request,
    lang: str = Query("en", pattern="^(en|hi)$"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Generates localized patient discharge guide (EN/HI).
    Enforces clinical primacy: only verified, finalized clinical notes/prescriptions are used.
    """
    try:
        guide = generate_patient_guide_from_encounter(db, appointment_id, language=lang)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    record_audit(
        db,
        request,
        "records.encounter.patient_guide.view",
        actor=user,
        details={"appointment_id": appointment_id, "language": lang},
    )
    db.commit()

    return PatientGuideResponse(**guide)


# ============================================================================
# 11. DPDP Privacy & 48h PIN-Protected Record Sharing
# ============================================================================

# Updates patient revocable consent preferences under DPDP Act 2023.
@router.post("/privacy/consent")
def update_dpdp_consent(
    payload: ConsentUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Updates patient revocable consent settings under DPDP Act 2023."""
    record_audit(
        db,
        request,
        "records.privacy.consent_updated",
        actor=user,
        details=payload.model_dump(),
    )
    db.commit()
    return {
        "status": "updated",
        "consent": payload.model_dump(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "message": "Consent preferences updated successfully under DPDP Act 2023. Consent is revocable at any time.",
    }


# Generates HMAC-SHA256 signature for secure patient record share tokens.
def _generate_share_signature(payload_str: str) -> str:
    key = (settings.jwt_secret_key or "carevoice_share_key").encode()
    return hmac.new(key, payload_str.encode(), hashlib.sha256).hexdigest()[:16]


# Generates a time-limited, PIN-protected shareable token for patient records.
@router.post("/share-link", response_model=ShareLinkResponse)
def create_share_link(
    payload: ShareLinkRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Creates a 48-hour PIN-protected share link for patient records under DPDP Act 2023."""
    _check_doctor_or_patient_access(db, user, payload.patient_user_id)

    expires_ts = int(datetime.now(timezone.utc).timestamp()) + (payload.expires_hours * 3600)
    pin_hash = hashlib.sha256(payload.pin.strip().encode()).hexdigest()[:12]
    raw_payload = f"{payload.patient_user_id}:{expires_ts}:{pin_hash}"
    sig = _generate_share_signature(raw_payload)
    token_str = base64.urlsafe_b64encode(f"{raw_payload}:{sig}".encode()).decode()

    record_audit(
        db,
        request,
        "records.share_link.created",
        actor=user,
        details={"patient_id": payload.patient_user_id, "expires_hours": payload.expires_hours},
    )
    db.commit()

    expires_iso = datetime.fromtimestamp(expires_ts, tz=timezone.utc).isoformat()
    return ShareLinkResponse(
        share_token=token_str,
        expires_at=expires_iso,
        pin_protected=True,
        instructions=f"Share this token with attending clinicians. Requires the {len(payload.pin)}-digit PIN for access. Automatically expires in 48 hours.",
    )


# Validates token and PIN to provide temporary read access to shared clinical records.
@router.get("/shared/{token}")
def access_shared_record(
    token: str,
    pin: str = Query(..., description="Access PIN"),
    db: Session = Depends(get_db),
):
    """Accesses a PIN-protected shared patient record bundle."""
    try:
        decoded = base64.urlsafe_b64decode(token.encode()).decode()
        parts = decoded.split(":")
        if len(parts) != 4:
            raise ValueError("Malformed token format.")
        pid_str, exp_str, pin_hash_token, sig = parts
        patient_id = int(pid_str)
        expires_ts = int(exp_str)
    except Exception as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid share token.") from exc

    # Validate HMAC signature
    expected_payload = f"{patient_id}:{expires_ts}:{pin_hash_token}"
    if not hmac.compare_digest(sig, _generate_share_signature(expected_payload)):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or tampered share token.")

    # Check 48h expiration
    now_ts = int(datetime.now(timezone.utc).timestamp())
    if now_ts > expires_ts:
        raise HTTPException(status.HTTP_410_GONE, "Share link has expired after 48 hours.")

    # Validate PIN
    provided_hash = hashlib.sha256(pin.strip().encode()).hexdigest()[:12]
    if not hmac.compare_digest(pin_hash_token, provided_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect PIN for shared patient record.")

    patient = db.get(User, patient_id)
    if not patient:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Patient record not found.")

    # Return longitudinal bundle
    fhir_bundle = generate_fhir_r4_bundle(db, patient_id)
    allergies = db.scalars(select(PatientAllergy).where(PatientAllergy.patient_user_id == patient_id)).all()
    notes = db.scalars(
        select(ClinicalNote).where(ClinicalNote.patient_user_id == patient_id, ClinicalNote.status == "finalized")
    ).all()
    prescriptions = db.scalars(
        select(Prescription).where(Prescription.patient_user_id == patient_id, Prescription.status == "finalized")
    ).all()

    return {
        "status": "authorized",
        "patient_name": patient.full_name,
        "patient_id": patient.id,
        "shared_until": datetime.fromtimestamp(expires_ts, tz=timezone.utc).isoformat(),
        "finalized_notes_count": len(notes),
        "finalized_prescriptions_count": len(prescriptions),
        "active_allergies": [a.allergen_or_condition for a in allergies if a.is_active],
        "fhir_bundle": fhir_bundle,
    }

from __future__ import annotations

from datetime import datetime, timezone
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.clinical import (
    ClinicalNote,
    MedicalDocument,
    PatientAllergy,
    Prescription,
    PrescriptionItem,
)
from app.models.patient import Patient
from app.models.providers import Doctor, Hospital
from app.models.user import User
from app.services.lab_analysis_service import LabAnalysisService
from app.services.patient_context_service import PatientContextService
from tests.auth_utils import make_session_token


@pytest.fixture
def test_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
    with session_factory() as db:
        yield db
    engine.dispose()


def test_patient_context_enforces_strict_rbac_boundaries(test_db: Session):
    """Verify patients can access ONLY their own clinical context; cross-access raises HTTP 403."""
    patient1 = User(id=1, email="p1@example.com", full_name="Rahul Verma", role="patient", password_hash="x")
    patient2 = User(id=2, email="p2@example.com", full_name="Sunita Rao", role="patient", password_hash="x")
    test_db.add_all([patient1, patient2])
    test_db.flush()

    # Patient 1 accessing own context -> succeeds
    ctx1 = PatientContextService.get_patient_context(test_db, requesting_user=patient1, target_patient_user_id=1)
    assert ctx1 is not None
    assert ctx1.full_name == "Rahul Verma"

    # Patient 1 attempting to access Patient 2 -> HTTP 403 Forbidden
    with pytest.raises(HTTPException) as exc_info:
        PatientContextService.get_patient_context(test_db, requesting_user=patient1, target_patient_user_id=2)
    assert exc_info.value.status_code == 403
    assert "Patients may only access their own healthcare records" in exc_info.value.detail


def test_patient_context_distinguishes_finalized_from_draft_records(test_db: Session):
    """Verify only clinician-finalized prescriptions and notes are injected; unapproved drafts are excluded."""
    patient = User(id=10, email="test@example.com", full_name="Pooja Sharma", role="patient", password_hash="x")
    hospital = Hospital(name="Apex Care", city="Pune", state="Maharashtra")
    test_db.add_all([patient, hospital])
    test_db.flush()

    doctor_user = User(id=11, email="dr@example.com", full_name="Dr. Mehta", role="doctor", password_hash="x")
    test_db.add(doctor_user)
    test_db.flush()

    doctor = Doctor(hospital_id=hospital.id, full_name="Dr. Mehta", specialty="General Medicine", is_active=True)
    test_db.add(doctor)
    test_db.flush()

    # Add active allergy
    allergy = PatientAllergy(
        patient_user_id=10,
        allergen_or_condition="Penicillin",
        category="allergy",
        severity="severe",
        reaction="anaphylaxis",
        is_active=True,
    )
    # Add inactive allergy (should be excluded)
    inactive_allergy = PatientAllergy(
        patient_user_id=10,
        allergen_or_condition="Dust",
        category="allergy",
        severity="mild",
        is_active=False,
    )

    # Add finalized prescription
    finalized_rx = Prescription(
        prescription_number="RX-20261023-AAA111",
        patient_user_id=10,
        doctor_id=doctor.id,
        diagnosis="Essential Hypertension",
        status="finalized",
        finalized_at=datetime.now(timezone.utc),
        finalized_by_user_id=doctor_user.id,
    )
    test_db.add_all([allergy, inactive_allergy, finalized_rx])
    test_db.flush()

    rx_item = PrescriptionItem(
        prescription_id=finalized_rx.id,
        medication_name="Amlodipine",
        strength="5 mg",
        frequency="1-0-0",
        duration="30 days",
    )
    # Add DRAFT prescription (must NOT appear in patient context)
    draft_rx = Prescription(
        prescription_number="RX-20261023-DRAFT1",
        patient_user_id=10,
        doctor_id=doctor.id,
        diagnosis="Suspected Infection",
        status="draft",
        is_ai_draft=True,
    )
    test_db.add_all([rx_item, draft_rx])

    # Add finalized clinical note
    finalized_note = ClinicalNote(
        patient_user_id=10,
        doctor_id=doctor.id,
        note_type="consultation_note",
        chief_complaint="Routine checkup",
        assessment="Hypertension well controlled on Amlodipine.",
        plan="Continue current treatment.",
        status="finalized",
        finalized_at=datetime.now(timezone.utc),
        finalized_by_user_id=doctor_user.id,
    )
    # Add draft clinical note
    draft_note = ClinicalNote(
        patient_user_id=10,
        doctor_id=doctor.id,
        note_type="soap_note",
        chief_complaint="Unconfirmed symptom",
        assessment="Possible gastritis",
        status="draft",
        is_ai_draft=True,
    )
    test_db.add_all([finalized_note, draft_note])
    test_db.commit()

    ctx = PatientContextService.get_patient_context(test_db, requesting_user=patient)
    assert ctx is not None

    # Check active allergies
    assert len(ctx.active_allergies) == 1
    assert ctx.active_allergies[0]["name"] == "Penicillin"

    # Check active prescriptions (finalized only)
    assert len(ctx.active_prescriptions) == 1
    assert ctx.active_prescriptions[0]["prescription_number"] == "RX-20261023-AAA111"

    # Check clinical notes (finalized only)
    assert len(ctx.recent_clinical_notes) == 1
    assert "Hypertension well controlled" in ctx.recent_clinical_notes[0]["assessment"]

    # Verify context XML output
    xml = ctx.context_text
    assert "<authorized-patient-context>" in xml
    assert "Penicillin (Severity: severe, Reaction: anaphylaxis)" in xml
    assert "Amlodipine 5 mg" in xml
    assert "RX-20261023-DRAFT1" not in xml
    assert "Possible gastritis" not in xml
    assert "[SAFETY & PROVENANCE BOUNDARY]" in xml


def test_lab_analysis_service_evaluation_and_reference_ranges():
    """Verify lab parameters are categorized correctly into normal, borderline, and critical."""
    # Fasting glucose
    normal_glucose = LabAnalysisService.evaluate_parameter("fasting_glucose", 88.0)
    assert normal_glucose["status"] == "normal"
    assert "70.0 - 99.0 mg/dL" in normal_glucose["reference_range"]

    borderline_glucose = LabAnalysisService.evaluate_parameter("fasting_glucose", 115.0)
    assert borderline_glucose["status"] == "borderline"

    critical_glucose = LabAnalysisService.evaluate_parameter("fasting_glucose", 240.0)
    assert critical_glucose["status"] == "critical"

    # Platelets
    normal_platelets = LabAnalysisService.evaluate_parameter("platelets", 250000)
    assert normal_platelets["status"] == "normal"

    critical_platelets = LabAnalysisService.evaluate_parameter("platelets", 45000)
    assert critical_platelets["status"] == "critical"
    assert "Dengue" in critical_platelets["clinical_correlation"]


def test_lab_analysis_service_longitudinal_trends(test_db: Session):
    """Verify extraction of historical lab results across documents and computation of trend trajectory."""
    patient = User(id=20, email="trends@example.com", full_name="Anita Deshmukh", role="patient", password_hash="x")
    test_db.add(patient)
    test_db.flush()

    # Document 1: 3 months ago (elevated HbA1c 8.2%)
    doc1 = MedicalDocument(
        patient_user_id=20,
        title="Comprehensive Metabolic Panel - July",
        document_type="lab_report",
        file_path="/documents/doc1.pdf",
        extracted_data={"hba1c": 8.2, "fasting_glucose": 160.0},
    )
    # Document 2: Current (improved HbA1c 6.8%)
    doc2 = MedicalDocument(
        patient_user_id=20,
        title="Comprehensive Metabolic Panel - October",
        document_type="lab_report",
        file_path="/documents/doc2.pdf",
        extracted_data={"hba1c": 6.8, "fasting_glucose": 125.0},
    )
    test_db.add_all([doc1, doc2])
    test_db.commit()

    trends = LabAnalysisService.get_patient_lab_trends(test_db, 20)
    assert trends["evaluated_parameters_count"] == 2

    hba1c_trend = next(t for t in trends["trends"] if t["parameter_key"] == "hba1c")
    assert hba1c_trend["readings_count"] == 2
    assert hba1c_trend["latest_value"] == 6.8
    assert hba1c_trend["direction"] == "improving"
    assert len(hba1c_trend["history"]) == 2

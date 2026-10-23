from __future__ import annotations

import io
from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth.security import get_current_user
from app.core.database import Base, get_db
from app.main import app
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


def _setup_test_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)

    def override_database():
        with session_factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_database
    return engine, session_factory, TestClient(app)


def _seed_clinical_environment(sessions):
    with sessions() as db:
        # 1. Hospital
        hosp = Hospital(
            id=1,
            name="CareVoice Central Hospital",
            city="Bengaluru",
            state="Karnataka",
            departments="Cardiology, General Medicine",
            verified=True,
            verification_status="verified",
        )
        db.add(hosp)
        db.flush()

        # 2. Doctor
        doc = Doctor(
            id=10,
            hospital_id=hosp.id,
            full_name="Dr. Sameer Verma",
            specialty="General Medicine",
            fee_minor=50000,
            verified=True,
            verification_status="verified",
        )
        db.add(doc)
        db.flush()

        # 3. Users: Patient Alice, Patient Bob, Doctor User, Unassigned Doctor User
        user_alice = User(id=1, full_name="Alice Patient", email="alice@test.com", password_hash="h", role="patient")
        user_bob = User(id=2, full_name="Bob Patient", email="bob@test.com", password_hash="h", role="patient")
        user_doc = User(id=3, full_name="Dr. Sameer Verma", email="doc@test.com", password_hash="h", role="doctor", doctor_id=doc.id)

        # Unassigned Doctor
        doc_unassigned = Doctor(
            id=20,
            hospital_id=hosp.id,
            full_name="Dr. Unassigned",
            specialty="Dermatology",
            verified=True,
            verification_status="verified",
        )
        db.add(doc_unassigned)
        db.flush()
        user_unassigned_doc = User(id=4, full_name="Dr. Unassigned", email="unassigned@test.com", password_hash="h", role="doctor", doctor_id=doc_unassigned.id)

        db.add_all([user_alice, user_bob, user_doc, user_unassigned_doc])
        db.flush()

        # 4. Patient profile for Alice
        pat_alice = Patient(id=1, owner_user_id=user_alice.id, full_name="Alice Patient", email="alice@test.com", age=29, gender="female")
        db.add(pat_alice)

        # 5. Appointment establishing care relationship between Doctor Sameer and Alice
        appt = Appointment(
            id=100,
            patient_user_id=user_alice.id,
            doctor_id=doc.id,
            hospital_id=hosp.id,
            scheduled_for=datetime.now(timezone.utc),
            status="scheduled",
            consultation_type="in_person",
        )
        db.add(appt)

        # 6. Allergy for Alice
        allergy = PatientAllergy(
            id=1,
            patient_user_id=user_alice.id,
            allergen_or_condition="Penicillin",
            category="medication_reaction",
            severity="severe",
            reaction="Hives and facial swelling",
            is_active=True,
        )
        db.add(allergy)

        # 7. Assistant Conversation for Alice
        conv = AssistantConversation(
            id=50,
            user_id=user_alice.id,
            title="Throat Pain and Mild Fever",
            urgency_level="routine",
            summary="Patient reports sore throat and fever for 2 days.",
            consent_given=True,
        )
        db.add(conv)
        db.flush()

        msg = AssistantMessage(
            conversation_id=conv.id,
            role="assistant",
            content="Based on your symptoms, rest and hydration are recommended.",
            structured_data={
                "citations": [{"title": "WHO Pharyngitis", "source_url": "https://who.int/guidance"}],
                "flags": [],
                "recommended_next_steps": ["Maintain oral fluids", "Consult a doctor if fever worsens"],
            },
        )
        db.add(msg)
        db.commit()


def test_patient_records_timeline_and_ownership():
    """Verify patient can view own timeline but cannot view another patient's timeline."""
    engine, sessions, client = _setup_test_db()
    _seed_clinical_environment(sessions)

    try:
        # 1. Alice viewing her own timeline
        alice_user = sessions().get(User, 1)
        app.dependency_overrides[get_current_user] = lambda: alice_user

        resp = client.get("/api/v1/records/timeline")
        assert resp.status_code == 200
        data = resp.json()
        assert data["patient_user_id"] == 1
        assert data["patient_name"] == "Alice Patient"
        assert len(data["events"]) >= 2  # Conversation and Appointment

        # 2. Alice attempting to view Bob's timeline -> 403 Forbidden
        resp_bob = client.get("/api/v1/records/timeline?patient_user_id=2")
        assert resp_bob.status_code == 403
        assert "Access denied" in resp_bob.json()["detail"]

        # 3. Assigned Doctor viewing Alice's timeline -> 200 OK
        doc_user = sessions().get(User, 3)
        app.dependency_overrides[get_current_user] = lambda: doc_user

        resp_doc = client.get("/api/v1/records/timeline?patient_user_id=1")
        assert resp_doc.status_code == 200
        assert resp_doc.json()["patient_user_id"] == 1

        # 4. Unassigned Doctor attempting to view Alice's timeline -> 403 Forbidden
        unassigned_doc_user = sessions().get(User, 4)
        app.dependency_overrides[get_current_user] = lambda: unassigned_doc_user

        resp_unassigned = client.get("/api/v1/records/timeline?patient_user_id=1")
        assert resp_unassigned.status_code == 403
        assert "not assigned" in resp_unassigned.json()["detail"]
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_clinical_notes_workflow_and_finalization():
    """Verify doctor can draft, update, and finalize clinical notes; patients only see finalized notes."""
    engine, sessions, client = _setup_test_db()
    _seed_clinical_environment(sessions)

    try:
        doc_user = sessions().get(User, 3)
        app.dependency_overrides[get_current_user] = lambda: doc_user

        # 1. Doctor requests AI draft note
        draft_resp = client.post(
            "/api/v1/records/notes/ai-draft",
            json={
                "patient_user_id": 1,
                "appointment_id": 100,
                "conversation_id": 50,
                "symptoms_context": "Sore throat with fever",
            },
        )
        assert draft_resp.status_code == 200
        draft_data = draft_resp.json()
        assert draft_data["is_ai_draft"] is True
        assert draft_data["status"] == "draft"

        # 2. Doctor creates clinical note
        create_resp = client.post(
            "/api/v1/records/notes",
            json={
                "patient_user_id": 1,
                "appointment_id": 100,
                "note_type": "consultation_note",
                "chief_complaint": "Sore throat and mild fever",
                "history_of_present_illness": "Patient reports onset 2 days ago.",
                "examination_findings": "Erythematous pharynx, no exudates.",
                "assessment": "Viral pharyngitis.",
                "plan": "Warm saline gargles, hydration, paracetamol if fever > 100°F.",
                "follow_up_instructions": "Follow up if symptoms persist after 48 hours.",
                "is_ai_draft": True,
            },
        )
        assert create_resp.status_code == 201
        note_id = create_resp.json()["id"]
        assert create_resp.json()["status"] == "draft"

        # 3. Patient viewing notes should NOT see draft note
        alice_user = sessions().get(User, 1)
        app.dependency_overrides[get_current_user] = lambda: alice_user
        patient_notes_resp = client.get("/api/v1/records/notes")
        assert patient_notes_resp.status_code == 200
        assert len(patient_notes_resp.json()) == 0  # Drafts hidden from patient

        # 4. Doctor finalizes note
        app.dependency_overrides[get_current_user] = lambda: doc_user
        fin_resp = client.post(f"/api/v1/records/notes/{note_id}/finalize")
        assert fin_resp.status_code == 200
        assert fin_resp.json()["status"] == "finalized"
        assert fin_resp.json()["finalized_at"] is not None
        assert fin_resp.json()["is_ai_draft"] is False  # Doctor signature verified

        # 5. Patient can now view finalized note
        app.dependency_overrides[get_current_user] = lambda: alice_user
        patient_view_resp = client.get("/api/v1/records/notes")
        assert patient_view_resp.status_code == 200
        assert len(patient_view_resp.json()) == 1
        assert patient_view_resp.json()[0]["status"] == "finalized"
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_prescription_allergy_checks_and_pdf_download():
    """Verify prescription drafting detects patient allergies and PDF download enforces authorization."""
    engine, sessions, client = _setup_test_db()
    _seed_clinical_environment(sessions)

    try:
        doc_user = sessions().get(User, 3)
        app.dependency_overrides[get_current_user] = lambda: doc_user

        # 1. AI prescription draft for Alice (who is allergic to Penicillin)
        ai_draft_resp = client.post(
            "/api/v1/records/prescriptions/ai-draft",
            json={
                "patient_user_id": 1,
                "appointment_id": 100,
                "diagnosis_hint": "Bacterial pharyngitis",
            },
        )
        assert ai_draft_resp.status_code == 200
        draft_json = ai_draft_resp.json()
        assert draft_json["status"] == "draft"
        assert draft_json["is_ai_draft"] is True

        # 2. Prescribing Amoxicillin (penicillin class) should trigger allergy warning
        create_resp = client.post(
            "/api/v1/records/prescriptions",
            json={
                "patient_user_id": 1,
                "appointment_id": 100,
                "diagnosis": "Acute Pharyngitis",
                "notes": "Ensure plenty of warm fluids.",
                "items": [
                    {
                        "medication_name": "Amoxicillin",
                        "strength": "500 mg",
                        "dosage_form": "capsule",
                        "route": "oral",
                        "frequency": "1-1-1",
                        "duration": "5 days",
                        "instructions": "Take after meals",
                    }
                ],
            },
        )
        assert create_resp.status_code == 201
        rx_data = create_resp.json()
        rx_id = rx_data["id"]
        # Must flag allergy conflict with Alice's recorded Penicillin allergy!
        assert len(rx_data["allergy_warnings"]) > 0
        assert any("Penicillin" in w or "ALLERGY" in w for w in rx_data["allergy_warnings"])

        # 3. Doctor finalizes prescription
        fin_resp = client.post(f"/api/v1/records/prescriptions/{rx_id}/finalize")
        assert fin_resp.status_code == 200
        assert fin_resp.json()["status"] == "finalized"

        # 4. Alice downloads finalized prescription PDF
        alice_user = sessions().get(User, 1)
        app.dependency_overrides[get_current_user] = lambda: alice_user

        pdf_resp = client.get(f"/api/v1/records/prescriptions/{rx_id}/pdf")
        assert pdf_resp.status_code == 200
        assert pdf_resp.headers["content-type"] == "application/pdf"
        assert len(pdf_resp.content) > 1000

        # 5. Bob (unauthorized patient) cannot download Alice's prescription
        bob_user = sessions().get(User, 2)
        app.dependency_overrides[get_current_user] = lambda: bob_user

        pdf_denied = client.get(f"/api/v1/records/prescriptions/{rx_id}/pdf")
        assert pdf_denied.status_code == 403
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_medical_report_generation_and_fhir_export():
    """Verify AI medical report generation and standard HL7 FHIR R4 export."""
    engine, sessions, client = _setup_test_db()
    _seed_clinical_environment(sessions)

    try:
        alice_user = sessions().get(User, 1)
        app.dependency_overrides[get_current_user] = lambda: alice_user

        # 1. Generate AI medical report from conversation 50
        rep_resp = client.post(
            "/api/v1/records/reports/generate",
            json={
                "patient_user_id": 1,
                "conversation_id": 50,
                "report_type": "symptom_assessment",
            },
        )
        assert rep_resp.status_code == 201
        rep_data = rep_resp.json()
        report_uuid = rep_data["report_id"]
        assert rep_data["summary"] == "Patient reports sore throat and fever for 2 days."
        assert len(rep_data["evidence_sources"]) >= 1

        # 2. Download report PDF
        pdf_resp = client.get(f"/api/v1/records/reports/{report_uuid}/pdf")
        assert pdf_resp.status_code == 200
        assert pdf_resp.headers["content-type"] == "application/pdf"
        assert len(pdf_resp.content) > 1000

        # 3. Export FHIR R4 Bundle
        fhir_resp = client.get("/api/v1/records/fhir/export")
        assert fhir_resp.status_code == 200
        bundle = fhir_resp.json()
        assert bundle["resourceType"] == "Bundle"
        assert bundle["type"] == "collection"
        assert bundle["total"] >= 3  # Patient, AllergyIntolerance, Encounter, DiagnosticReport

        # Verify Patient resource in bundle
        resources = [e["resource"] for e in bundle["entry"]]
        resource_types = [r["resourceType"] for r in resources]
        assert "Patient" in resource_types
        assert "AllergyIntolerance" in resource_types
        assert "Encounter" in resource_types
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_doctor_workspace_overview():
    """Verify doctor workspace aggregates assigned patients, today's appointments, and AI assessments."""
    engine, sessions, client = _setup_test_db()
    _seed_clinical_environment(sessions)

    try:
        doc_user = sessions().get(User, 3)
        app.dependency_overrides[get_current_user] = lambda: doc_user

        resp = client.get("/api/v1/records/doctor/workspace")
        assert resp.status_code == 200
        data = resp.json()
        assert data["doctor_id"] == 10
        assert data["doctor_name"] == "Dr. Sameer Verma"
        assert len(data["assigned_patients"]) == 1
        assert data["assigned_patients"][0]["patient_name"] == "Alice Patient"
        assert data["assigned_patients"][0]["active_allergies_count"] == 1
        assert len(data["today_appointments"]) == 1
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_all_clinical_and_billing_pdf_endpoints():
    """Verify all newly added ReportLab PDF endpoints generate valid PDFs and enforce authorization."""
    from app.models.billing import Invoice, Payment

    engine, sessions, client = _setup_test_db()
    _seed_clinical_environment(sessions)

    try:
        # Seed additional required records:
        with sessions() as db:
            # 1. Finalized Clinical Note
            note = ClinicalNote(
                id=1,
                patient_user_id=1,
                doctor_id=10,
                appointment_id=100,
                note_type="consultation_note",
                chief_complaint="Throat pain and difficulty swallowing",
                history_of_present_illness="Sore throat for 3 days, worsening on swallowing.",
                examination_findings="Erythematous tonsils without membrane. Cervical lymph nodes palpable.",
                assessment="Acute streptococcal pharyngotonsillitis.",
                plan="Course of oral antibiotics, hydration, paracetamol SOS for temperature.",
                follow_up_instructions="Review in clinic after 5 days or sooner if high fever persists.",
                status="finalized",
                finalized_at=datetime.now(timezone.utc),
                is_ai_draft=False,
            )
            db.add(note)

            # 2. Medical Document / Lab Report
            doc_file = MedicalDocument(
                id=1,
                patient_user_id=1,
                uploaded_by_user_id=1,
                title="CBC and Throat Swab Report",
                document_type="lab_report",
                file_path="/tmp/fake_cbc_throat_swab.pdf",
                file_size=245000,
                mime_type="application/pdf",
                notes="Elevated leukocyte count and positive rapid Strep A antigen consistent with acute bacterial tonsillitis.",
                extracted_data={
                    "clinical_summary": "Elevated leukocyte count and positive rapid Strep A antigen consistent with acute bacterial tonsillitis.",
                    "abnormal_flags": ["WBC > 11,000", "Strep A Antigen Positive", "Elevated CRP"],
                    "extracted_text": "WBC Count: 12,400 /uL (Elevated). Rapid Strep A Antigen: POSITIVE. CRP: 24 mg/L.",
                },
            )
            db.add(doc_file)

            # 3. Unpaid Invoice
            unpaid_inv = Invoice(
                id=1,
                invoice_number="INV-2026-TEST-0001",
                owner_user_id=1,
                hospital_id=1,
                appointment_id=100,
                amount_minor=50000,
                currency="INR",
                status="unpaid",
                description="Consultation fee - Dr. Sameer Verma",
            )
            # 4. Paid Invoice
            paid_inv = Invoice(
                id=2,
                invoice_number="INV-2026-TEST-0002",
                owner_user_id=1,
                hospital_id=1,
                appointment_id=None,
                amount_minor=65000,
                currency="INR",
                status="paid",
                paid_at=datetime.now(timezone.utc),
                description="Comprehensive ENT Examination & Swab",
            )
            db.add_all([unpaid_inv, paid_inv])
            db.flush()

            # 5. Payment for Paid Invoice
            payment = Payment(
                id=1,
                invoice_id=paid_inv.id,
                status="captured",
                provider_payment_id="pay_test_pdf_12345",
                provider_order_id="order_test_pdf_67890",
            )
            db.add(payment)
            db.commit()

        alice_user = sessions().get(User, 1)
        bob_user = sessions().get(User, 2)
        doc_user = sessions().get(User, 3)

        # A. Alice: Clinical Note PDF
        app.dependency_overrides[get_current_user] = lambda: alice_user
        note_pdf_resp = client.get("/api/v1/records/notes/1/pdf")
        assert note_pdf_resp.status_code == 200
        assert note_pdf_resp.headers["content-type"] == "application/pdf"
        assert len(note_pdf_resp.content) > 1000

        # B. Alice: Follow-up Plan PDF
        followup_pdf_resp = client.get("/api/v1/records/followup/1/pdf")
        assert followup_pdf_resp.status_code == 200
        assert followup_pdf_resp.headers["content-type"] == "application/pdf"
        assert len(followup_pdf_resp.content) > 1000

        # C. Alice: Longitudinal Health Summary PDF
        summary_pdf_resp = client.get("/api/v1/records/summary/pdf")
        assert summary_pdf_resp.status_code == 200
        assert summary_pdf_resp.headers["content-type"] == "application/pdf"
        assert len(summary_pdf_resp.content) > 1000

        # D. Alice: Diagnostic Document Summary PDF
        doc_pdf_resp = client.get("/api/v1/records/documents/1/summary/pdf")
        assert doc_pdf_resp.status_code == 200
        assert doc_pdf_resp.headers["content-type"] == "application/pdf"
        assert len(doc_pdf_resp.content) > 1000

        # E. Alice: Appointment Confirmation Slip PDF
        appt_pdf_resp = client.get("/api/v1/records/appointments/100/confirmation/pdf")
        assert appt_pdf_resp.status_code == 200
        assert appt_pdf_resp.headers["content-type"] == "application/pdf"
        assert len(appt_pdf_resp.content) > 1000

        # F. Alice: Tax Invoice PDF (for unpaid and paid)
        inv_pdf_resp = client.get("/api/v1/billing/invoices/1/pdf")
        assert inv_pdf_resp.status_code == 200
        assert inv_pdf_resp.headers["content-type"] == "application/pdf"
        assert len(inv_pdf_resp.content) > 1000

        # G. Alice: Receipt for unpaid invoice should be rejected (400)
        unpaid_receipt_resp = client.get("/api/v1/billing/receipts/1/pdf")
        assert unpaid_receipt_resp.status_code == 400
        assert "paid" in unpaid_receipt_resp.json()["detail"]

        # H. Alice: Receipt for paid invoice succeeds (200)
        paid_receipt_resp = client.get("/api/v1/billing/receipts/2/pdf")
        assert paid_receipt_resp.status_code == 200
        assert paid_receipt_resp.headers["content-type"] == "application/pdf"
        assert len(paid_receipt_resp.content) > 1000

        # I. Security / BOLA checks: Bob cannot access Alice's documents
        app.dependency_overrides[get_current_user] = lambda: bob_user
        assert client.get("/api/v1/records/notes/1/pdf").status_code == 403
        assert client.get("/api/v1/records/followup/1/pdf").status_code == 403
        assert client.get("/api/v1/records/documents/1/summary/pdf").status_code == 403
        assert client.get("/api/v1/records/appointments/100/confirmation/pdf").status_code == 403
        assert client.get("/api/v1/billing/invoices/1/pdf").status_code == 403
        assert client.get("/api/v1/billing/receipts/2/pdf").status_code == 403

        # J. Doctor can access assigned patient's clinical note PDF and summary PDF
        app.dependency_overrides[get_current_user] = lambda: doc_user
        doc_note_resp = client.get("/api/v1/records/notes/1/pdf")
        assert doc_note_resp.status_code == 200
        doc_summary_resp = client.get("/api/v1/records/summary/pdf?patient_user_id=1")
        assert doc_summary_resp.status_code == 200
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


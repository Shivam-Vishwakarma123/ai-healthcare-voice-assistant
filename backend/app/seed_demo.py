"""Idempotent development-only CareVoice demo-data seeder."""

import argparse
import os
import sys
import uuid
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.auth.security import hash_password
from app.core.config import settings
from app.core.database import SessionLocal
from app.models.billing import Invoice, Payment
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
from app.models.providers import (
    Appointment,
    AppointmentEvent,
    AppointmentSlotLock,
    Doctor,
    DoctorQualification,
    DoctorSchedule,
    Hospital,
)
from app.models.user import User

DEMO_PASSWORD = "CareVoiceDemo2026!"
SEED_MARKER = "DEMO-SEED-V1"
LOCAL_TZ = ZoneInfo("Asia/Kolkata")
DOCUMENTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "medical_documents"
)
os.makedirs(DOCUMENTS_DIR, exist_ok=True)

HOSPITALS = (
    {
        "name": "DEMO - Cedar Valley Care Hospital",
        "city": "Jaipur",
        "state": "Rajasthan",
        "address": "101 Fictional Garden Road",
        "phone": "+1-202-555-0101",
        "website": "https://cedar-valley.example.test",
        "departments": "General Medicine, Cardiology, Pediatrics",
    },
    {
        "name": "DEMO - Bluebird Community Clinic",
        "city": "Bhopal",
        "state": "Madhya Pradesh",
        "address": "202 Sample Lake Avenue",
        "phone": "+1-202-555-0102",
        "website": "https://bluebird.example.test",
        "departments": "General Medicine, Dermatology, Orthopedics",
    },
    {
        "name": "DEMO - Maple Grove Health Centre",
        "city": "Kochi",
        "state": "Kerala",
        "address": "303 Imaginary Harbor Street",
        "phone": "+1-202-555-0103",
        "website": "https://maple-grove.example.test",
        "departments": "General Medicine, Neurology, Women's Health",
    },
)

DOCTORS = (
    ("Asha Demo", "General Medicine", 45000, 12),
    ("Kabir Sample", "Cardiology", 80000, 16),
    ("Mira Fiction", "Pediatrics", 55000, 9),
    ("Dev Sample", "Dermatology", 60000, 11),
    ("Tara Demo", "Orthopedics", 70000, 14),
    ("Neel Fiction", "General Medicine", 40000, 7),
    ("Riya Sample", "Neurology", 90000, 18),
    ("Arjun Demo", "Women's Health", 65000, 10),
    ("Leela Fiction", "Pediatrics", 50000, 8),
    ("Ishaan Sample", "Cardiology", 85000, 15),
)

PATIENT_NAMES = (
    "Aarav Demo", "Diya Sample", "Ira Fiction", "Vivaan Demo", "Anaya Sample",
    "Reyansh Fiction", "Saanvi Demo", "Advik Sample", "Myra Fiction", "Kabir Demo",
    "Aadhya Sample", "Arnav Fiction", "Kiara Demo", "Dhruv Sample", "Tara Fiction",
    "Rohan Demo", "Meera Sample", "Neil Fiction", "Ishita Demo", "Veer Sample",
)


def _get_or_create_user(
    db: Session,
    *,
    email: str,
    full_name: str,
    role: str,
    hospital_id: int | None = None,
    doctor_id: int | None = None,
    phone_number: str | None = None,
) -> tuple[User, bool]:
    user = db.scalar(select(User).where(User.email == email))
    if user is not None:
        if (
            user.role != role
            or user.hospital_id != hospital_id
            or user.doctor_id != doctor_id
        ):
            raise ValueError(f"Demo account identity conflicts with an existing account: {email}")
        return user, False
    user = User(
        full_name=full_name,
        email=email,
        password_hash=hash_password(DEMO_PASSWORD),
        role=role,
        hospital_id=hospital_id,
        doctor_id=doctor_id,
        phone_number=phone_number,
        is_active=True,
    )
    db.add(user)
    db.flush()
    return user, True


def _get_or_create_hospitals(db: Session) -> tuple[list[Hospital], int]:
    hospitals: list[Hospital] = []
    created = 0
    for index, details in enumerate(HOSPITALS, start=1):
        marker = f"{SEED_MARKER}: fictional hospital {index}; demo data only."
        hospital = db.scalar(select(Hospital).where(Hospital.name == details["name"]))
        if hospital is None:
            hospital = Hospital(
                **details,
                description=marker,
                verified=True,
                verification_status="verified",
            )
            db.add(hospital)
            db.flush()
            created += 1
        elif hospital.description != marker:
            raise ValueError(f"Demo hospital name conflicts with an existing record: {details['name']}")
        hospitals.append(hospital)
    return hospitals, created


def _get_or_create_doctors(db: Session, hospitals: list[Hospital]) -> tuple[list[Doctor], int]:
    doctors: list[Doctor] = []
    created = 0
    for index, (name, specialty, fee_minor, experience_years) in enumerate(DOCTORS, start=1):
        hospital = hospitals[(index - 1) % len(hospitals)]
        marker = f"{SEED_MARKER}: fictional clinician {index}; demo data only."
        doctor = db.scalar(select(Doctor).where(Doctor.bio == marker))
        if doctor is None:
            doctor = Doctor(
                hospital_id=hospital.id,
                full_name=f"Dr. {name}",
                specialty=specialty,
                languages="English, Hindi",
                fee_minor=fee_minor,
                verified=True,
                is_active=True,
                experience_years=experience_years,
                consultation_mode="in_person",
                bio=marker,
                specialties=[specialty],
                language_list=["English", "Hindi"],
                consultation_types=["in_person", "online"],
                verification_status="verified",
            )
            db.add(doctor)
            db.flush()
            created += 1
        elif doctor.hospital_id != hospital.id or doctor.specialty != specialty:
            raise ValueError(f"Demo clinician marker conflicts with an existing profile: {marker}")
        doctors.append(doctor)

        qualification = db.scalar(
            select(DoctorQualification).where(
                DoctorQualification.doctor_id == doctor.id,
                DoctorQualification.degree == "Fictional demo qualification",
                DoctorQualification.institution == "CareVoice synthetic seed data",
            )
        )
        if qualification is None:
            db.add(
                DoctorQualification(
                    doctor_id=doctor.id,
                    degree="Fictional demo qualification",
                    institution="CareVoice synthetic seed data",
                    completion_year=2020,
                    verification_status="pending",
                )
            )

        for weekday in range(5):
            schedule = db.scalar(
                select(DoctorSchedule).where(
                    DoctorSchedule.doctor_id == doctor.id,
                    DoctorSchedule.day_of_week == weekday,
                    DoctorSchedule.starts_at == time(9, 0),
                    DoctorSchedule.ends_at == time(17, 0),
                    DoctorSchedule.timezone == "Asia/Kolkata",
                    DoctorSchedule.consultation_type == "in_person",
                    DoctorSchedule.is_active.is_(True),
                )
            )
            if schedule is None:
                overlapping = db.scalar(
                    select(DoctorSchedule.id).where(
                        DoctorSchedule.doctor_id == doctor.id,
                        DoctorSchedule.day_of_week == weekday,
                        DoctorSchedule.is_active.is_(True),
                        DoctorSchedule.starts_at < time(17, 0),
                        DoctorSchedule.ends_at > time(9, 0),
                    ).limit(1)
                )
                if overlapping is not None:
                    raise ValueError(f"Existing schedule overlaps the demo schedule for clinician {doctor.id}.")
                db.add(
                    DoctorSchedule(
                        doctor_id=doctor.id,
                        day_of_week=weekday,
                        starts_at=time(9, 0),
                        ends_at=time(17, 0),
                        timezone="Asia/Kolkata",
                        consultation_type="in_person",
                        is_active=True,
                    )
                )
    db.flush()
    return doctors, created


def _get_or_create_patients(db: Session) -> tuple[list[User], int, int]:
    patients: list[User] = []
    users_created = 0
    profiles_created = 0
    genders = ("female", "male", "other", "prefer_not_to_say")
    for index, full_name in enumerate(PATIENT_NAMES, start=1):
        email = f"patient{index:02d}@demo.carevoice.test"
        phone = f"+120255501{index + 9:02d}"
        user, created = _get_or_create_user(
            db,
            email=email,
            full_name=full_name,
            role="patient",
            phone_number=phone,
        )
        users_created += int(created)
        profile = db.scalar(select(Patient).where(Patient.owner_user_id == user.id))
        if profile is None:
            conflicting_profile = db.scalar(select(Patient.id).where(Patient.email == email))
            if conflicting_profile is not None:
                raise ValueError(f"Demo patient profile email conflicts with an existing profile: {email}")
            db.add(
                Patient(
                    owner_user_id=user.id,
                    full_name=full_name,
                    email=email,
                    age=24 + (index * 3) % 47,
                    gender=genders[(index - 1) % len(genders)],
                )
            )
            profiles_created += 1
        elif profile.email != email:
            raise ValueError(f"Existing patient profile does not match its demo account: {email}")
        patients.append(user)
    db.flush()
    return patients, users_created, profiles_created


def _local_appointment(day: date, hour: int) -> datetime:
    return datetime.combine(day, time(hour, 0), tzinfo=LOCAL_TZ).astimezone(timezone.utc)


def _matching_weekday(anchor: date, weekday: int, *, forward: bool) -> date:
    delta = (weekday - anchor.weekday()) % 7 if forward else (anchor.weekday() - weekday) % 7
    return anchor + timedelta(days=delta if forward else -delta)


def _ensure_hospital_admins(db: Session, hospitals: list[Hospital]) -> int:
    created = 0
    for index, hospital in enumerate(hospitals, start=1):
        _, was_created = _get_or_create_user(
            db,
            email=f"hospital-admin{index:02d}@demo.carevoice.test",
            full_name=f"Demo Hospital Administrator {index:02d}",
            role="hospital_admin",
            hospital_id=hospital.id,
            phone_number=f"+120255501{index + 39:02d}",
        )
        created += int(was_created)
    return created


def _ensure_doctor_accounts(db: Session, doctors: list[Doctor], hospitals: list[Hospital]) -> int:
    created = 0
    for index, doctor in enumerate(doctors, start=1):
        _, was_created = _get_or_create_user(
            db,
            email=f"doctor{index:02d}@demo.carevoice.test",
            full_name=doctor.full_name,
            role="doctor",
            hospital_id=hospitals[(index - 1) % len(hospitals)].id,
            doctor_id=doctor.id,
            phone_number=f"+120255501{index + 59:02d}",
        )
        created += int(was_created)
    return created


def _ensure_appointments(
    db: Session,
    doctors: list[Doctor],
    patients: list[User],
    hospitals: list[Hospital],
) -> int:
    today = datetime.now(LOCAL_TZ).date()
    created = 0
    for index, doctor in enumerate(doctors):
        weekday = index % 5
        cases = (
            (
                "completed",
                _local_appointment(_matching_weekday(today - timedelta(days=28), weekday, forward=False), 9),
            ),
            (
                "cancelled",
                _local_appointment(_matching_weekday(today - timedelta(days=14), weekday, forward=False), 10),
            ),
            (
                "confirmed" if index % 2 == 0 else "scheduled",
                _local_appointment(_matching_weekday(today + timedelta(days=14), weekday, forward=True), 11),
            ),
        )
        hospital_id = hospitals[index % len(hospitals)].id
        for case_index, (final_status, scheduled_for) in enumerate(cases, start=1):
            marker = f"{SEED_MARKER}:appointment:{index + 1:02d}:{case_index}"
            if index == 1 and case_index == 1:
                patient = patients[0]  # Ensure Dr. Kabir (doctor index 1) has completed encounter with Aarav (patient index 0)
            elif index == 6 and case_index == 3:
                patient = patients[3]  # Swap with patient 3 so all patients have appointments
            else:
                patient = patients[(index * 3 + case_index - 1) % len(patients)]
            appointment = db.scalar(select(Appointment).where(Appointment.notes == marker))
            if appointment is None:
                appointment = Appointment(
                    patient_user_id=patient.id,
                    doctor_id=doctor.id,
                    hospital_id=hospital_id,
                    scheduled_for=scheduled_for,
                    duration_minutes=30,
                    consultation_type="in_person",
                    status=final_status,
                    notes=marker,
                )
                db.add(appointment)
                db.flush()
                created += 1
                db.add(
                    AppointmentEvent(
                        appointment_id=appointment.id,
                        actor_user_id=None,
                        event_type="booked",
                        to_status="scheduled",
                        scheduled_for=scheduled_for,
                    )
                )
                if final_status in {"confirmed", "completed"}:
                    db.add(
                        AppointmentEvent(
                            appointment_id=appointment.id,
                            actor_user_id=None,
                            event_type="confirmed",
                            from_status="scheduled",
                            to_status="confirmed",
                            scheduled_for=scheduled_for,
                        )
                    )
                if final_status in {"cancelled", "completed"}:
                    db.add(
                        AppointmentEvent(
                            appointment_id=appointment.id,
                            actor_user_id=None,
                            event_type=final_status,
                            from_status="confirmed" if final_status == "completed" else "scheduled",
                            to_status=final_status,
                            scheduled_for=scheduled_for,
                            reason="Fictional demo appointment history.",
                        )
                    )
                if final_status in {"scheduled", "confirmed"}:
                    epoch_start = int(scheduled_for.timestamp())
                    db.add(
                        AppointmentSlotLock(
                            appointment_id=appointment.id,
                            doctor_id=doctor.id,
                            slot_start=datetime.fromtimestamp(
                                epoch_start // 1800 * 1800,
                                timezone.utc,
                            ),
                        )
                    )
            elif (
                appointment.doctor_id != doctor.id
                or appointment.hospital_id != hospital_id
                or appointment.patient_user_id != patient.id
            ):
                # Sync demo appointment fields if the seed specification evolved
                appointment.doctor_id = doctor.id
                appointment.hospital_id = hospital_id
                appointment.patient_user_id = patient.id
    db.flush()
    return created


def _ensure_invoices_and_payments(db: Session) -> tuple[int, int]:
    appointments = db.scalars(
        select(Appointment)
        .where(Appointment.notes.like(f"{SEED_MARKER}:appointment:%"))
        .order_by(Appointment.id.asc())
    ).all()
    invoice_created = 0
    payment_created = 0
    for appointment in appointments:
        if appointment.status not in {"completed", "scheduled", "confirmed"}:
            continue
        doctor = db.get(Doctor, appointment.doctor_id)
        if doctor is None:
            raise ValueError(f"Demo appointment {appointment.id} references a missing clinician.")
        invoice_number = f"DEMO-SEED-V1-{appointment.id:08d}"
        invoice = db.scalar(select(Invoice).where(Invoice.invoice_number == invoice_number))
        if invoice is None:
            invoice = db.scalar(select(Invoice).where(Invoice.appointment_id == appointment.id))
            if invoice is None:
                invoice = Invoice(
                    owner_user_id=appointment.patient_user_id,
                    hospital_id=appointment.hospital_id,
                    appointment_id=appointment.id,
                    invoice_number=invoice_number,
                    description=f"DEMO consultation - {doctor.specialty}",
                    amount_minor=doctor.fee_minor,
                    currency="INR",
                    status="unpaid",
                )
                db.add(invoice)
                db.flush()
                invoice_created += 1
            elif (
                invoice.owner_user_id != appointment.patient_user_id
                or invoice.hospital_id != appointment.hospital_id
                or invoice.amount_minor != doctor.fee_minor
            ):
                invoice.owner_user_id = appointment.patient_user_id
                invoice.hospital_id = appointment.hospital_id
                invoice.amount_minor = doctor.fee_minor
        elif (
            invoice.appointment_id != appointment.id
            or invoice.owner_user_id != appointment.patient_user_id
            or invoice.amount_minor != doctor.fee_minor
        ):
            if invoice.invoice_number.startswith(SEED_MARKER):
                invoice.appointment_id = appointment.id
                invoice.owner_user_id = appointment.patient_user_id
                invoice.amount_minor = doctor.fee_minor
            else:
                raise ValueError(f"Demo invoice number conflicts with an existing invoice: {invoice_number}")

        payment_order_id = f"demo_seed_v1_{invoice.id}"
        payment = db.scalar(select(Payment).where(Payment.provider_order_id == payment_order_id))
        if payment is None:
            paid = appointment.status == "completed" and appointment.id % 4 != 0
            if paid:
                payment_status = "paid"
                invoice.status = "paid"
                invoice.paid_at = appointment.scheduled_for + timedelta(hours=1)
            elif appointment.status == "completed" and appointment.id % 4 == 0:
                payment_status = "failed"
            else:
                payment_status = "created"
            payment = Payment(
                invoice_id=invoice.id,
                provider_order_id=payment_order_id,
                provider_payment_id=f"demo_tx_seed_v1_{invoice.id}" if payment_status == "paid" else None,
                status=payment_status,
                failure_code="demo_seed_failure" if payment_status == "failed" else None,
                failure_description="Fictional demo payment failure." if payment_status == "failed" else None,
            )
            db.add(payment)
            payment_created += 1
        elif payment.invoice_id != invoice.id:
            raise ValueError(f"Demo payment order conflicts with an existing invoice: {payment_order_id}")
    db.flush()
    return invoice_created, payment_created


def _create_sample_diagnostic_pdf(
    filepath: str,
    hospital_name: str,
    patient_name: str,
    patient_age_gender: str,
    test_title: str,
    test_category: str,
    collection_date: str,
    parameters: list[tuple[str, str, str, str]],
    interpretation: str,
    signing_doctor: str,
) -> int:
    """Generate a high-fidelity clinical diagnostic PDF using ReportLab."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    doc = SimpleDocTemplate(
        filepath,
        pagesize=letter,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40,
    )
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=15,
        leading=18,
        textColor=colors.HexColor("#0f766e"),
        spaceAfter=3,
    )
    subtitle_style = ParagraphStyle(
        "DocSub",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#475569"),
        spaceAfter=10,
    )
    section_style = ParagraphStyle(
        "SectionHeader",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=15,
        textColor=colors.HexColor("#0f172a"),
        spaceBefore=8,
        spaceAfter=5,
    )
    body_style = ParagraphStyle(
        "Body",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#1e293b"),
    )
    banner_style = ParagraphStyle(
        "DemoBanner",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#b45309"),
        alignment=1,
    )

    story = [
        Paragraph("DEMO DATA — SYNTHETIC RECORD FOR CAREVOICE DEMONSTRATION PURPOSES ONLY", banner_style),
        Spacer(1, 6),
        Paragraph(hospital_name, title_style),
        Paragraph(f"Department of {test_category} • Accredited Diagnostic Facility", subtitle_style),
        HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#0f766e"), spaceAfter=10),
    ]

    patient_info = [
        [
            Paragraph(f"<b>Patient Name:</b> {patient_name}", body_style),
            Paragraph(f"<b>Age / Gender:</b> {patient_age_gender}", body_style),
        ],
        [
            Paragraph(f"<b>Investigation:</b> {test_title}", body_style),
            Paragraph(f"<b>Reported:</b> {collection_date}", body_style),
        ],
        [
            Paragraph("<b>Specimen:</b> Venous Blood / Routine", body_style),
            Paragraph("<b>Result Status:</b> FINAL / VERIFIED", body_style),
        ],
    ]
    info_table = Table(patient_info, colWidths=[266, 266])
    info_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
                ("PADDING", (0, 0), (-1, -1), 5),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ]
        )
    )
    story.append(info_table)
    story.append(Spacer(1, 10))

    story.append(Paragraph("<b>Test Results & Biological Reference Intervals:</b>", section_style))
    table_data = [["Test Parameter", "Observed Result", "Reference Interval", "Flag"]]
    for row in parameters:
        table_data.append(
            [
                Paragraph(row[0], body_style),
                Paragraph(f"<b>{row[1]}</b>", body_style),
                Paragraph(row[2], body_style),
                Paragraph(f"<b>{row[3]}</b>" if row[3] != "NORMAL" else row[3], body_style),
            ]
        )

    results_table = Table(table_data, colWidths=[190, 110, 162, 70])
    results_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f766e")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 9),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f5f9")]),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("PADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(results_table)
    story.append(Spacer(1, 10))

    story.append(Paragraph("<b>Clinical Impression & Medical Notes:</b>", section_style))
    story.append(Paragraph(interpretation, body_style))
    story.append(Spacer(1, 12))

    sig_data = [
        [
            Paragraph("<i>Electronically authenticated via secure laboratory information system.</i>", body_style),
            Paragraph(f"<b>Authorized Signatory:</b><br/>{signing_doctor}<br/><i>Consultant Pathologist / Radiologist</i>", body_style),
        ]
    ]
    sig_table = Table(sig_data, colWidths=[312, 220])
    sig_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
            ]
        )
    )
    story.append(sig_table)

    doc.build(story)
    return os.path.getsize(filepath)


def _ensure_demo_conversations(
    db: Session,
    patients: list[User],
) -> int:
    """Seed multi-turn consultation conversations and assistant messages."""
    if not patients:
        return 0
    aarav = patients[0]
    diya = patients[1] if len(patients) > 1 else None
    now = datetime.now(timezone.utc)
    created = 0

    demo_conversations = [
        {
            "user": aarav,
            "conversation_id": f"{SEED_MARKER}-CONV-01",
            "title": "Acute Pharyngitis & Upper Respiratory Consultation",
            "category": "ent",
            "urgency_level": "routine",
            "summary": "Patient reports 3-day history of scratchy sore throat, difficulty swallowing, and low-grade fever (100.4°F). Documented Penicillin allergy avoided. Warm saline gargles and paracetamol advised.",
            "days_ago": 28,
            "messages": [
                {
                    "role": "user",
                    "content": "Hello CareVoice, I have had a severe scratchy sore throat for 3 days and painful swallowing. My temperature reached 100.4°F this morning. What should I do?",
                    "structured_data": None,
                },
                {
                    "role": "assistant",
                    "content": "Hello Aarav. Based on your symptoms of acute sore throat, painful swallowing, and low-grade fever (100.4°F), this presentation is most consistent with viral pharyngitis. Centor criteria calculation indicates low likelihood (Score 2) of streptococcal pharyngitis.\n\n⚠️ ALLERGY NOTICE: You have a documented severe allergy to Penicillins (urticaria/rash). Beta-lactam antibiotics must not be prescribed.\n\nRecommended home care:\n1. Warm saline gargles (1/2 teaspoon salt in 1 cup warm water) 3-4 times daily.\n2. Hydration maintenance with warm broths and water.\n3. Paracetamol 650mg SOS after meals for fever/pain (avoid NSAIDs due to your recorded sensitivity).\n4. Schedule an in-person clinical check if fever >101°F persists >48 hours.",
                    "structured_data": {
                        "triage_urgency": "routine",
                        "citations": [
                            {"title": "WHO Guidelines on Pharyngitis and Sore Throat Home Management", "source_url": "https://who.int/guidelines/pharyngitis"},
                            {"title": "NIH MedQuAD Pharyngitis Clinical Care Guide", "source_url": "https://medlineplus.gov/sorethroat.html"},
                        ],
                        "red_flags": [],
                    },
                },
                {
                    "role": "user",
                    "content": "Thank you. What warning signs should I watch for that would mean I need immediate emergency help?",
                    "structured_data": None,
                },
                {
                    "role": "assistant",
                    "content": "Please seek immediate emergency medical care (call 112) if you experience:\n• Stridor, wheezing, or difficulty breathing\n• Inability to swallow saliva or fluids (drooling)\n• Inability to fully open your mouth (trismus)\n• Neck stiffness or high fever above 102°F\n\nDr. Asha Demo has been notified and an encounter note has been prepared for your record.",
                    "structured_data": {
                        "emergency_helpline": "112",
                        "citations": [],
                    },
                },
            ],
        },
        {
            "user": aarav,
            "conversation_id": f"{SEED_MARKER}-CONV-02",
            "title": "Stage 1 Hypertension & Lifestyle Evaluation",
            "category": "cardiology",
            "urgency_level": "routine",
            "summary": "Longitudinal evaluation of home blood pressure readings (mean 140/90 mmHg). Patient remains asymptomatic. DASH dietary sodium restriction and cardiology consultation arranged.",
            "days_ago": 14,
            "messages": [
                {
                    "role": "user",
                    "content": "My home blood pressure monitor has been averaging 140/90 mmHg over the past two weeks. I feel completely fine, but should I be worried?",
                    "structured_data": None,
                },
                {
                    "role": "assistant",
                    "content": "A resting blood pressure of 140/90 mmHg falls into the Stage 1 Essential Hypertension category under ACC/AHA clinical guidelines. Because you are currently asymptomatic with no chest tightness or shortness of breath, this is not an acute hypertensive emergency, but it does require proactive clinical management.\n\nRecommended next steps:\n1. Maintain a daily blood pressure log (measure twice daily: morning before breakfast and evening before dinner).\n2. Adopt the Dietary Approaches to Stop Hypertension (DASH) protocol: restrict sodium to <2,000 mg/day.\n3. Engage in 150 minutes of moderate aerobic activity weekly.\n4. Consult attending cardiologist Dr. Kabir Sample for baseline ECG and lipid evaluation.",
                    "structured_data": {
                        "triage_urgency": "routine",
                        "citations": [
                            {"title": "NIH NHLBI Guidelines on High Blood Pressure in Adults", "source_url": "https://nih.gov/health-topics/high-blood-pressure"}
                        ],
                    },
                },
            ],
        },
        {
            "user": aarav,
            "conversation_id": f"{SEED_MARKER}-CONV-03",
            "title": "Seasonal Allergic Rhinitis & Sinus Congestion",
            "category": "allergy",
            "urgency_level": "routine",
            "summary": "Patient presented with bouts of morning sneezing, ocular pruritus, and clear rhinorrhea. Moderate-to-severe allergic rhinitis confirmed. Antihistamine and nasal corticosteroid plan initiated.",
            "days_ago": 21,
            "messages": [
                {
                    "role": "user",
                    "content": "Every morning I have bouts of 10 to 15 sneezes, my eyes are red and itchy, and my nose runs constantly. Dust seems to trigger it.",
                    "structured_data": None,
                },
                {
                    "role": "assistant",
                    "content": "Your symptoms are classic indicators of Seasonal Allergic Rhinitis with allergic rhinoconjunctivitis. Allergen exposure triggers mast cell degranulation, releasing histamines that cause mucosal edema and secretions.\n\nClinical plan:\n1. Second-generation non-sedating H1-antihistamine (Levocetirizine 5mg).\n2. Intranasal corticosteroid spray (Fluticasone Propionate) — use consistently as peak efficacy occurs after 3-5 days.\n3. Environmental mitigations: Keep windows closed during early morning pollen peaks and use a HEPA air purifier.\n4. Avoid oral NSAIDs for associated sinus aches due to your recorded sensitivity.",
                    "structured_data": {
                        "triage_urgency": "routine",
                        "citations": [
                            {"title": "MedlinePlus Allergic Rhinitis Clinical Reference", "source_url": "https://medlineplus.gov/allergicrhinitis.html"}
                        ],
                    },
                },
            ],
        },
        {
            "user": aarav,
            "conversation_id": f"{SEED_MARKER}-CONV-04",
            "title": "Acute Gastroenteritis & Oral Rehydration Guidance",
            "category": "gastroenterology",
            "urgency_level": "routine",
            "summary": "Sudden onset watery diarrhea and nausea. WHO-standard ORS fluid replacement therapy and 14-day zinc mucosal restoration protocol established.",
            "days_ago": 7,
            "messages": [
                {
                    "role": "user",
                    "content": "I came down with sudden nausea and 5 loose watery stools since yesterday after eating at a party. No fever or blood, but I feel weak.",
                    "structured_data": None,
                },
                {
                    "role": "assistant",
                    "content": "This presentation is typical for acute viral gastroenteritis. Preventing dehydration is the primary clinical goal.\n\nHome rehydration protocol:\n1. WHO-standard Oral Rehydration Salts (ORS): Dissolve 1 sachet in exactly 1 Liter of clean boiled water. Drink 200-400 mL after each loose stool.\n2. Zinc supplementation (20mg daily for 14 days) to accelerate intestinal mucosal healing.\n3. BRAT diet: Bananas, Rice, Applesauce, Toast. Avoid dairy, high-fat foods, and caffeine.\n4. Alert triggers: Seek urgent care if vomiting prevents fluid retention, high fever develops, or stool contains blood.",
                    "structured_data": {
                        "triage_urgency": "routine",
                        "citations": [
                            {"title": "WHO Clinical Management of Acute Diarrhea & ORS Formulation", "source_url": "https://who.int/publications/diarrhoea-treatment"}
                        ],
                    },
                },
            ],
        },
        {
            "user": aarav,
            "conversation_id": f"{SEED_MARKER}-CONV-05",
            "title": "Nocturnal Wheezing & Asthma Action Plan",
            "category": "pulmonology",
            "urgency_level": "urgent",
            "summary": "Nocturnal dry cough and wheezing following cold exposure. Peak flow monitoring showed 475 L/min (82% personal best, Yellow Zone). Inhaled bronchodilator protocol reviewed.",
            "days_ago": 2,
            "messages": [
                {
                    "role": "user",
                    "content": "I woke up at 2 AM with a tight chest and audible wheezing. My home peak flow meter reads 475 L/min; my normal best is 580.",
                    "structured_data": None,
                },
                {
                    "role": "assistant",
                    "content": "Your peak expiratory flow is at 82% of your baseline, placing you in the Yellow Caution Zone under Global Initiative for Asthma (GINA) guidelines.\n\nImmediate instructions:\n1. Sit upright; do not lie flat. Stay in a warm, dust-free environment.\n2. Administer your prescribed bronchodilator rescue inhaler (2 puffs with a spacer).\n3. Re-check peak flow after 20-30 minutes.\n4. 🚨 EMERGENCY WARNING: If you experience difficulty speaking in full sentences, chest retractions, cyanosis, or if peak flow falls below 50% (< 290 L/min), call 112 immediately or proceed to the nearest emergency room.",
                    "structured_data": {
                        "triage_urgency": "urgent",
                        "red_flags": [
                            "Notify immediately if unable to speak full sentences, central cyanosis develops, or PEF falls below 50% (Red Zone)"
                        ],
                        "citations": [
                            {"title": "Global Initiative for Asthma (GINA) Management Strategy", "source_url": "https://ginasthma.org/reports"}
                        ],
                    },
                },
            ],
        },
    ]

    if diya:
        demo_conversations.append({
            "user": diya,
            "conversation_id": f"{SEED_MARKER}-CONV-06",
            "title": "Episodic Migraine Headache with Visual Aura",
            "category": "neurology",
            "urgency_level": "routine",
            "summary": "Patient reports recurring unilateral throbbing headaches preceded by scintillating scotoma and photophobia. SNOOP criteria screened negative.",
            "days_ago": 10,
            "messages": [
                {
                    "role": "user",
                    "content": "I get severe throbbing headaches on the right side of my head, usually preceded by flashing zigzag lights in my vision for 20 minutes.",
                    "structured_data": None,
                },
                {
                    "role": "assistant",
                    "content": "The visual disturbance you describe is a scintillating scotoma, a classic migraine aura. The subsequent unilateral throbbing headache meets the International Headache Society diagnostic criteria for Migraine with Aura.\n\nGuidance:\n1. Rest in a dark, quiet room with cold compress at symptom onset.\n2. Maintain consistent sleep schedule and hydration; keep a headache trigger diary.\n3. Screen for SNOOP red flags (sudden thunderclap onset, systemic symptoms, neurological deficit) — all negative in your report.\n4. Neurological consultation with Dr. Asha arranged.",
                    "structured_data": {
                        "triage_urgency": "routine",
                        "citations": [],
                    },
                },
            ],
        })

    sneha = db.scalar(select(User).where(User.email == "sneha@gmail.com"))
    if sneha:
        demo_conversations.extend([
            {
                "user": sneha,
                "conversation_id": f"{SEED_MARKER}-SNEHA-CONV-01",
                "title": "Seasonal Allergies & Respiratory Health Consultation",
                "category": "allergy",
                "urgency_level": "routine",
                "summary": "Voice triage session regarding seasonal allergic rhinitis, ocular pruritus, and morning nasal congestion. Allergen avoidance and antihistamine protocol synthesized.",
                "days_ago": 12,
                "messages": [
                    {
                        "role": "user",
                        "content": "I have been sneezing frequently in the mornings with watery eyes and a stuffy nose for the past week.",
                        "structured_data": None,
                    },
                    {
                        "role": "assistant",
                        "content": "Your symptoms are typical of allergic rhinitis triggered by airborne allergens.\n\nRecommended steps:\n1. Non-sedating antihistamine (Cetirizine or Levocetirizine).\n2. Saline nasal rinse to clear allergens.\n3. Keep bedroom windows closed during high pollen hours.\n4. Consult your clinician if symptoms persist beyond two weeks.",
                        "structured_data": {
                            "triage_urgency": "routine",
                            "citations": [
                                {"title": "WHO Guidelines on Allergic Rhinitis Management", "source_url": "https://who.int/publications/allergic-rhinitis"}
                            ],
                        },
                    },
                ],
            },
            {
                "user": sneha,
                "conversation_id": f"{SEED_MARKER}-SNEHA-CONV-02",
                "title": "Tension Headache & Digital Eye Strain Assessment",
                "category": "neurology",
                "urgency_level": "routine",
                "summary": "AI triage evaluation for mild bilateral frontal headache after prolonged screen time. SNOOP criteria screened negative for emergency flags.",
                "days_ago": 4,
                "messages": [
                    {
                        "role": "user",
                        "content": "I have a dull ache across my forehead and around my eyes after working on my laptop all day.",
                        "structured_data": None,
                    },
                    {
                        "role": "assistant",
                        "content": "This presentation is characteristic of tension-type headache associated with digital eye strain (asthenopia).\n\nGuidance:\n1. Follow the 20-20-20 rule: every 20 minutes, look at an object 20 feet away for 20 seconds.\n2. Ensure adequate hydration and ergonomic screen positioning.\n3. Take regular short screen breaks.\n4. Emergency red flags: Thunderclap onset, visual loss, or neurological weakness require immediate emergency evaluation (Call 112).",
                        "structured_data": {
                            "triage_urgency": "routine",
                            "citations": [
                                {"title": "NIH Clinical Guide: Headaches and Digital Eye Strain", "source_url": "https://medlineplus.gov/headache.html"}
                            ],
                        },
                    },
                ],
            },
        ])

    for c_data in demo_conversations:
        existing_conv = db.scalar(
            select(AssistantConversation).where(
                AssistantConversation.conversation_id == c_data["conversation_id"]
            )
        )
        if existing_conv is None:
            conv_date = now - timedelta(days=c_data["days_ago"])
            conv = AssistantConversation(
                conversation_id=c_data["conversation_id"],
                user_id=c_data["user"].id,
                title=c_data["title"],
                category=c_data["category"],
                urgency_level=c_data["urgency_level"],
                summary=c_data["summary"],
                consent_given=True,
                is_active=True,
                created_at=conv_date,
            )
            db.add(conv)
            db.flush()

            for msg_idx, m_data in enumerate(c_data["messages"]):
                msg_time = conv_date + timedelta(minutes=msg_idx * 2)
                msg = AssistantMessage(
                    conversation_id=conv.id,
                    role=m_data["role"],
                    content=m_data["content"],
                    structured_data=m_data.get("structured_data"),
                    created_at=msg_time,
                )
                db.add(msg)
            created += 1

    db.flush()
    return created


def _ensure_demo_clinical_records(
    db: Session,
    patients: list[User],
    doctors: list[Doctor],
    hospitals: list[Hospital],
) -> dict[str, int]:
    """Seed comprehensive longitudinal clinical records for Aarav Demo (patient01@demo.carevoice.test)."""
    if not patients or not doctors or not hospitals:
        return {}

    aarav = patients[0]
    dr_asha = doctors[0]
    dr_asha_user = db.scalar(select(User).where(User.email == "doctor01@demo.carevoice.test"))
    dr_kabir = doctors[1]
    dr_kabir_user = db.scalar(select(User).where(User.email == "doctor02@demo.carevoice.test"))

    hospital_primary = hospitals[0]
    hospital_name = hospital_primary.name

    now = datetime.now(timezone.utc)
    counts = {
        "allergies_created": 0,
        "ai_reports_created": 0,
        "prescriptions_created": 0,
        "notes_created": 0,
        "documents_created": 0,
    }

    # 1. Patient Allergies
    demo_allergies = [
        (
            "Penicillins (Amoxicillin, Ampicillin)",
            "allergy",
            "moderate",
            "Urticaria, pruritic rash, and mild periorbital edema",
        ),
        (
            "NSAIDs (Aspirin, Ibuprofen)",
            "medication_reaction",
            "mild",
            "Bronchospasm, mild dyspnea, and gastric irritation",
        ),
    ]
    for allergen, cat, sev, reaction in demo_allergies:
        existing_allergy = db.scalar(
            select(PatientAllergy).where(
                PatientAllergy.patient_user_id == aarav.id,
                PatientAllergy.allergen_or_condition == allergen,
            )
        )
        if existing_allergy is None:
            allergy = PatientAllergy(
                patient_user_id=aarav.id,
                allergen_or_condition=allergen,
                category=cat,
                severity=sev,
                reaction=reaction,
                recorded_by_user_id=dr_asha_user.id if dr_asha_user else aarav.id,
                is_active=True,
            )
            db.add(allergy)
            counts["allergies_created"] += 1

    # 2. AI Reports (5 comprehensive assessments)
    demo_reports = [
        {
            "title": "Acute Pharyngitis & Upper Respiratory Symptoms Assessment",
            "report_type": "symptom_assessment",
            "urgency_level": "routine",
            "days_ago": 28,
            "doctor": dr_asha,
            "summary": "Patient reported acute sore throat (3 days), painful swallowing, low-grade fever (100.4°F), and mild rhinorrhea. Centor criteria calculation indicates low likelihood (Score 2) of streptococcal pharyngitis, most consistent with self-limiting viral upper respiratory infection.",
            "findings": [
                {"finding": "Pharyngeal erythema with tonsillar injection", "significance": "Consistent with viral pharyngitis"},
                {"finding": "Absence of tonsillar exudates", "significance": "Low risk for Group A Streptococcus"},
                {"finding": "Bilateral tender anterior cervical lymphadenopathy", "significance": "Reactive inflammatory response"},
            ],
            "red_flags": [],
            "next_steps": [
                "Warm saline gargles 3-4 times daily",
                "Hydration maintenance with warm liquids",
                "Acetaminophen/Paracetamol 650mg for symptom relief (avoid NSAIDs due to recorded allergy)",
                "Schedule in-person clinic follow-up if fever >101°F persists >48h or breathing difficulty occurs",
            ],
            "evidence": [
                {"title": "WHO Guidelines on Pharyngitis and Sore Throat Home Management", "provenance": "WHO SEARO", "url": "https://who.int/guidelines/pharyngitis"},
                {"title": "NIH MedQuAD Pharyngitis Clinical Care Guide", "provenance": "NIH MedQuAD", "url": "https://medlineplus.gov/sorethroat.html"},
            ],
        },
        {
            "title": "Stage 1 Hypertension Follow-up & Lifestyle Evaluation",
            "report_type": "visit_summary",
            "urgency_level": "routine",
            "days_ago": 14,
            "doctor": dr_kabir,
            "summary": "Longitudinal review of 4-week home blood pressure readings (mean 140/90 mmHg). Patient remains asymptomatic. Re-assessed 10-year ASCVD risk and dietary sodium intake under AHA/ACC guidelines.",
            "findings": [
                {"finding": "Mean systolic blood pressure 140 mmHg", "significance": "Stage 1 Essential Hypertension"},
                {"finding": "Absence of target organ damage", "significance": "Normal renal function and baseline ECG"},
            ],
            "red_flags": [],
            "next_steps": [
                "Continue antihypertensive medication as prescribed",
                "Maintain dietary sodium under 2000mg per day (DASH diet protocol)",
                "150 minutes of moderate aerobic exercise weekly",
                "Weekly home BP logging in morning seated position",
            ],
            "evidence": [
                {"title": "NIH NHLBI Guidelines on High Blood Pressure in Adults", "provenance": "NIH NHLBI", "url": "https://nih.gov/health-topics/high-blood-pressure"},
            ],
        },
        {
            "title": "Seasonal Allergic Rhinitis & Sinus Congestion Evaluation",
            "report_type": "symptom_assessment",
            "urgency_level": "routine",
            "days_ago": 21,
            "doctor": dr_asha,
            "summary": "Evaluation of seasonal paroxysmal sneezing, clear rhinorrhea, and ocular pruritus triggered by seasonal pollen and dust. Assessment confirms moderate-to-severe intermittent allergic rhinitis.",
            "findings": [
                {"finding": "Bilateral nasal mucosal edema with pale turbinates", "significance": "Classic allergic rhinitis hallmark"},
                {"finding": "Conjunctival hyperemia without purulent discharge", "significance": "Allergic conjunctivitis component"},
            ],
            "red_flags": [],
            "next_steps": [
                "Initiate intranasal corticosteroid spray (Fluticasone Propionate)",
                "Non-sedating second-generation H1-antihistamine therapy",
                "Environmental allergen avoidance: keep windows closed during high-pollen hours",
                "Saline nasal irrigation twice daily",
            ],
            "evidence": [
                {"title": "MedlinePlus Allergic Rhinitis Clinical Reference", "provenance": "MedlinePlus", "url": "https://medlineplus.gov/allergicrhinitis.html"},
            ],
        },
        {
            "title": "Acute Gastroenteritis & Rehydration Guidance",
            "report_type": "symptom_assessment",
            "urgency_level": "routine",
            "days_ago": 7,
            "doctor": dr_asha,
            "summary": "Assessment of sudden onset nausea and acute watery diarrhea without gross blood or high fever. Rehydration plan established using WHO-formula Oral Rehydration Salts (ORS) and clinical warning thresholds.",
            "findings": [
                {"finding": "Acute onset watery diarrhea (4-5 episodes/day)", "significance": "Probable viral gastroenteritis"},
                {"finding": "Mild dehydration without hemodynamic instability", "significance": "Candidate for home oral rehydration"},
            ],
            "red_flags": [],
            "next_steps": [
                "Active oral rehydration therapy with WHO-standard ORS (200-400 mL after each loose stool)",
                "Zinc supplementation (20mg daily for 14 days) to support mucosal repair",
                "Gradual dietary transition: BRAT diet (bananas, rice, applesauce, toast)",
                "Emergency re-evaluation if signs of severe dehydration or persistent vomiting occur",
            ],
            "evidence": [
                {"title": "WHO Clinical Management of Acute Diarrhea & ORS Formulation", "provenance": "WHO SEARO", "url": "https://who.int/publications/diarrhoea-treatment"},
            ],
        },
        {
            "title": "Adult Asthma Flare-up & Respiratory Monitoring Assessment",
            "report_type": "symptom_assessment",
            "urgency_level": "urgent",
            "days_ago": 2,
            "doctor": dr_asha,
            "summary": "Patient reported mild nocturnal wheezing and dry cough following cold exposure. Peak flow monitoring showed 82% of personal best (Yellow Zone). Emergency red flags screened negative. Action plan reviewed.",
            "findings": [
                {"finding": "Peak Expiratory Flow (PEF) 475 L/min (82% of baseline)", "significance": "Mild-to-moderate airway hyperreactivity"},
                {"finding": "Room air SpO2 97%", "significance": "Adequate peripheral arterial oxygen saturation"},
            ],
            "red_flags": [
                "Notify immediately if unable to speak full sentences, central cyanosis develops, or PEF falls below 50% (Red Zone)"
            ],
            "next_steps": [
                "Inhaled bronchodilator therapy as per personal action plan",
                "Avoid cold air exposure and outdoor irritants",
                "Repeat peak flow measurement every 4 hours",
                "If peak flow does not improve to >90% within 24 hours, contact attending physician",
            ],
            "evidence": [
                {"title": "Global Initiative for Asthma (GINA) Management Strategy", "provenance": "GINA", "url": "https://ginasthma.org/reports"},
            ],
        },
    ]

    for rep in demo_reports:
        existing_report = db.scalar(
            select(MedicalReport).where(
                MedicalReport.patient_user_id == aarav.id,
                MedicalReport.title == rep["title"],
            )
        )
        if existing_report is None:
            rep_date = now - timedelta(days=rep["days_ago"])
            report = MedicalReport(
                patient_user_id=aarav.id,
                doctor_id=rep["doctor"].id,
                report_type=rep["report_type"],
                title=rep["title"],
                summary=rep["summary"],
                urgency_level=rep["urgency_level"],
                red_flags=rep["red_flags"],
                findings=rep["findings"],
                recommended_next_steps=rep["next_steps"],
                evidence_sources=rep["evidence"],
                disclaimer="DEMO DATA — NOT A REAL PATIENT ASSESSMENT. CareVoice AI reports provide structured educational assessment and clinical synthesis only.",
                status="reviewed",
                reviewed_by_doctor_id=rep["doctor"].id,
                reviewed_at=rep_date + timedelta(hours=2),
                created_at=rep_date,
            )
            db.add(report)
            counts["ai_reports_created"] += 1

    # 3. Prescriptions (4 finalized prescriptions with complete items)
    demo_prescriptions = [
        {
            "prescription_number": "RX-20260924-DEMO01",
            "days_ago": 28,
            "doctor": dr_asha,
            "finalized_by": dr_asha_user,
            "diagnosis": "Acute Pharyngitis & Upper Respiratory Infection",
            "notes": "Patient has documented penicillin allergy (urticaria). Prescribed Macrolide (Azithromycin) instead of beta-lactams. Maintain hydration and complete full antibiotic course.",
            "warnings": [
                "Cross-reactivity screened: Patient allergic to Penicillins. Beta-lactams avoided; Azithromycin safely selected.",
                "NSAIDs avoided due to recorded adverse reaction.",
            ],
            "items": [
                ("Azithromycin", "500 mg", "tablet", "oral", "1-0-0 (Once daily)", "3 days", "3 tablets", "Take 1 hour before food or 2 hours after meals"),
                ("Paracetamol", "650 mg", "tablet", "oral", "1-0-1 (SOS / As needed)", "5 days", "10 tablets", "Take after food for fever or throat discomfort"),
                ("Cetirizine Hydrochloride", "10 mg", "tablet", "oral", "0-0-1 (Night)", "5 days", "5 tablets", "Take at bedtime for rhinorrhea and sneezing"),
            ],
        },
        {
            "prescription_number": "RX-20261008-DEMO02",
            "days_ago": 14,
            "doctor": dr_kabir,
            "finalized_by": dr_kabir_user,
            "diagnosis": "Essential (Primary) Hypertension, Stage 1",
            "notes": "Target BP: <130/80 mmHg. Emphasized low-sodium diet (<2g/day) and daily 30-min brisk walk. Log BP in the morning before medication.",
            "warnings": [
                "Allergy profile verified: Penicillin and NSAID allergies present. No conflict with ARB / CCB classes.",
            ],
            "items": [
                ("Telmisartan", "40 mg", "tablet", "oral", "1-0-0 (Morning)", "30 days", "30 tablets", "Take every morning after breakfast with water"),
                ("Amlodipine Besylate", "5 mg", "tablet", "oral", "0-0-1 (Evening)", "30 days", "30 tablets", "Take each evening. Report peripheral edema if noticed"),
            ],
        },
        {
            "prescription_number": "RX-20261001-DEMO03",
            "days_ago": 21,
            "doctor": dr_asha,
            "finalized_by": dr_asha_user,
            "diagnosis": "Moderate-to-Severe Intermittent Allergic Rhinitis",
            "notes": "Use nasal spray regularly for full therapeutic effect (onset 2-4 days). Keep windows closed during morning pollen peaks.",
            "warnings": [
                "Patient allergy screen passed. No contraindications detected.",
            ],
            "items": [
                ("Levocetirizine + Montelukast", "5 mg / 10 mg", "tablet", "oral", "0-0-1 (Night)", "14 days", "14 tablets", "Take one tablet every night before sleep"),
                ("Fluticasone Propionate Nasal Spray", "50 mcg/actuation", "nasal spray", "nasal", "2 sprays each nostril OD", "30 days", "1 bottle (120 doses)", "Prime bottle before first use; spray away from nasal septum"),
            ],
        },
        {
            "prescription_number": "RX-20261015-DEMO04",
            "days_ago": 7,
            "doctor": dr_asha,
            "finalized_by": dr_asha_user,
            "diagnosis": "Acute Gastroenteritis (Resolved, Recovery Phase)",
            "notes": "Continue oral hydration. Zinc supplementation is critical to restore intestinal mucosal barrier integrity.",
            "warnings": [
                "Patient allergy screen passed.",
            ],
            "items": [
                ("Oral Rehydration Salts (WHO Formula)", "20.5 g sachet", "powder for solution", "oral", "As needed (200-400 mL/stool)", "3 days", "6 sachets", "Dissolve 1 sachet in exactly 1 Liter of clean boiled water. Sip throughout day"),
                ("Ondansetron", "4 mg", "orally disintegrating tablet", "oral", "1-0-1 (SOS)", "3 days", "6 tablets", "Place on tongue to dissolve 30 minutes before meal if nausea occurs"),
                ("Zinc Sulfate Monohydrate", "20 mg elemental zinc", "tablet", "oral", "1-0-0 (Morning)", "14 days", "14 tablets", "Take once daily with breakfast for 14 continuous days"),
            ],
        },
        {
            "prescription_number": "RX-20261022-DRAFT01",
            "days_ago": 1,
            "doctor": dr_asha,
            "finalized_by": None,
            "is_ai_draft": True,
            "status": "draft",
            "diagnosis": "AI Draft: Acute Rhino-sinusitis & Bronchospasm",
            "notes": "AI Generated Draft: Awaiting attending physician review and digital signature. Penicillin allergy confirmed and beta-lactams avoided.",
            "warnings": [
                "AI Screening: Documented Penicillin allergy present. Beta-lactams prohibited.",
                "NSAID warning: Avoid Aspirin and Ibuprofen due to sensitivity reaction.",
            ],
            "items": [
                ("Azithromycin", "500 mg", "tablet", "oral", "1-0-0 (Once daily)", "3 days", "3 tablets", "Take 1 hour before or 2 hours after meals"),
                ("Levocetirizine", "5 mg", "tablet", "oral", "0-0-1 (Night)", "7 days", "7 tablets", "Take at bedtime with water"),
            ],
        },
        {
            "prescription_number": "RX-20261023-DRAFT02",
            "days_ago": 0,
            "doctor": dr_kabir,
            "finalized_by": None,
            "is_ai_draft": True,
            "status": "draft",
            "diagnosis": "AI Draft: Essential Hypertension Regimen Review",
            "notes": "AI Generated Draft: Awaiting serum electrolytes and physician sign-off.",
            "warnings": [
                "Allergy profile verified. No contraindications detected.",
            ],
            "items": [
                ("Telmisartan", "40 mg", "tablet", "oral", "1-0-0 (Morning)", "30 days", "30 tablets", "Take in morning after breakfast"),
                ("Hydrochlorothiazide", "12.5 mg", "tablet", "oral", "1-0-0 (Morning)", "30 days", "30 tablets", "Pending clinician review and baseline serum potassium check"),
            ],
        },
    ]

    for rx_data in demo_prescriptions:
        existing_rx = db.scalar(
            select(Prescription).where(
                Prescription.patient_user_id == aarav.id,
                Prescription.prescription_number == rx_data["prescription_number"],
            )
        )
        if existing_rx is None:
            rx_date = now - timedelta(days=rx_data["days_ago"])
            is_draft = rx_data.get("is_ai_draft", False) or rx_data.get("status") == "draft"
            rx = Prescription(
                prescription_number=rx_data["prescription_number"],
                patient_user_id=aarav.id,
                doctor_id=rx_data["doctor"].id,
                diagnosis=rx_data["diagnosis"],
                notes=rx_data["notes"],
                allergy_warnings=rx_data["warnings"],
                is_ai_draft=is_draft,
                status="draft" if is_draft else rx_data.get("status", "finalized"),
                finalized_at=None if is_draft else rx_date,
                finalized_by_user_id=None if is_draft else (rx_data["finalized_by"].id if rx_data.get("finalized_by") else aarav.id),
                created_at=rx_date,
            )
            for it in rx_data["items"]:
                item = PrescriptionItem(
                    medication_name=it[0],
                    strength=it[1],
                    dosage_form=it[2],
                    route=it[3],
                    frequency=it[4],
                    duration=it[5],
                    quantity=it[6],
                    instructions=it[7],
                )
                rx.items.append(item)
            db.add(rx)
            counts["prescriptions_created"] += 1

    # 4. Doctor Notes (5 clinical consultation notes)
    demo_notes = [
        {
            "chief_complaint": "Severe throat pain, odynophagia, and fever for 3 days",
            "days_ago": 28,
            "doctor": dr_asha,
            "finalized_by": dr_asha_user,
            "note_type": "consultation_note",
            "hpi": "32-year-old male presents with 3-day history of scratchy sore throat, difficulty swallowing solids, and mild fever up to 100.4°F. Associated with clear nasal discharge and dry cough. Denies dyspnea, stridor, neck stiffness, or rash.",
            "exam": "Vitals: BP 124/80 mmHg, HR 78 bpm regular, Temp 100.2°F, SpO2 99% on ambient air. Pharynx: Marked erythema of posterior pharyngeal wall and tonsillar pillars. No exudates, membranes, or uvular deviation. Neck: Tender submandibular and anterior cervical lymphadenopathy bilaterally (1 cm, mobile). Lungs: Vesicular breath sounds bilaterally, no crackles or rhonchi.",
            "assessment": "Acute viral pharyngitis with mild upper respiratory involvement. Centor Score = 2 (low probability of bacterial GAS infection). Penicillin allergy noted.",
            "plan": "Prescribed Azithromycin 500mg (as non-penicillin antimicrobial coverage due to clinical suspicion of secondary bacterial overlay), Paracetamol 650mg SOS for pyrexia, and Cetirizine 10mg. Warm saline gargles recommended.",
            "follow_up": "Return to clinic immediately if temperature exceeds 102°F, inability to swallow liquids occurs, or shortness of breath develops.",
        },
        {
            "chief_complaint": "Cardiology consult: Evaluation of stage 1 hypertension detected on workplace physical",
            "days_ago": 14,
            "doctor": dr_kabir,
            "finalized_by": dr_kabir_user,
            "note_type": "progress_note",
            "hpi": "Patient was advised to obtain formal cardiology evaluation after routine corporate health screen showed BP 144/92 mmHg. Over the past 4 weeks, patient logged home BP readings ranging 136-146 / 88-94 mmHg. Asymptomatic: denies exertional chest tightness, dyspnea, orthopnea, palpitations, syncope, or visual disturbances. Non-smoker, occasional alcohol.",
            "exam": "Vitals: Seated Right Arm BP 142/90 mmHg (repeat left arm 140/88 mmHg), Pulse 72 bpm regular, BMI 24.6 kg/m². CV: S1 and S2 physiologically normal. No murmurs, clicks, rubs, or gallops. JVP not elevated. Abdomen: No renal artery bruits. Extremities: Warm and well-perfused, zero pedal edema.",
            "assessment": "Stage 1 Essential Hypertension (ICD-10 I10). Low 10-year atherosclerotic cardiovascular disease risk (<5%). Good candidate for first-line ARB therapy.",
            "plan": "1. Start Telmisartan 40mg once daily in morning. 2. Low-dose Amlodipine 5mg evening. 3. DASH dietary sodium restriction (<2,000 mg/day). 4. Prescribed lipid panel and renal function panel. 5. Maintain daily home BP log.",
            "follow_up": "Follow-up in 4 weeks with home BP record and laboratory results.",
        },
        {
            "chief_complaint": "Paroxysmal sneezing, itchy watery eyes, and clear nasal discharge",
            "days_ago": 21,
            "doctor": dr_asha,
            "finalized_by": dr_asha_user,
            "note_type": "soap_note",
            "hpi": "Patient reports persistent sneezing bouts (10-15 consecutively) especially in early morning and during dust exposure for the past 2 weeks. Associated with itchy soft palate and red, tearing eyes. Impairing sleep and work productivity.",
            "exam": "Eyes: Bilateral mild conjunctival injection without crusting or discharge. Nose: Nasal mucosa boggy, pale-bluish with copious thin watery secretions. Ears: Bilateral tympanic membranes pearly gray, intact with normal light reflex.",
            "assessment": "Moderate-Severe Intermittent Allergic Rhinitis (ARIA criteria) with associated allergic rhinoconjunctivitis.",
            "plan": "1. Fluticasone Propionate nasal spray (2 sprays per nostril OD). 2. Levocetirizine 5mg + Montelukast 10mg nightly for 14 days. 3. Advised on environmental allergen mitigation (HEPA air purifier, mattress covers, morning window closure).",
            "follow_up": "Review in 2 weeks or SOS if unmanaged.",
        },
        {
            "chief_complaint": "Follow-up: Recovery from acute gastroenteritis and diet re-introduction",
            "days_ago": 7,
            "doctor": dr_asha,
            "finalized_by": dr_asha_user,
            "note_type": "progress_note",
            "hpi": "Patient presented 5 days ago with acute watery diarrhea (5-6 loose stools) and nausea after dining at a public banquet. Managed successfully at home with WHO-ORS fluid therapy. Diarrhea resolved 48 hours ago; now passing soft formed stool. Denies lingering fever or abdominal cramps.",
            "exam": "Vitals: BP 120/78 mmHg, HR 74 bpm, Temp 98.4°F, SpO2 99%. Oral cavity: Moist mucous membranes, normal skin turgor. Abdomen: Soft, non-tender, non-distended, active normoactive bowel sounds. No organomegaly.",
            "assessment": "Resolved acute gastroenteritis (probable viral etiology). Successful home oral rehydration without complication or electrolyte imbalance.",
            "plan": "1. Discontinue Ondansetron. 2. Continue Zinc 20mg daily to complete the full 14-day mucosal restitution regimen. 3. Liberalize diet progressively from bland soft foods to regular balanced diet; avoid heavy fried foods and unpasteurized dairy for 3 days.",
            "follow_up": "Routine follow-up as needed.",
        },
        {
            "chief_complaint": "Annual preventive health checkup and comprehensive lab review",
            "days_ago": 2,
            "doctor": dr_asha,
            "finalized_by": dr_asha_user,
            "note_type": "consultation_note",
            "hpi": "32-year-old male presents for routine annual preventative clinical evaluation. No active clinical complaints. Compliant with antihypertensive medication. Exercise routine: 30-minute jog 4 times weekly. Sleep 7 hours nightly.",
            "exam": "Vitals: BP 126/82 mmHg (well-controlled), HR 70 bpm, BMI 24.2 kg/m² (normal range), Waist circumference 33 inches. General: Healthy, alert, athletic build. Systemic examination: Heart, lungs, abdomen, and neurological checks all within normal limits.",
            "assessment": "Healthy adult male with well-controlled Stage 1 Essential Hypertension on low-dose medical therapy and lifestyle management. Normal routine hematological and metabolic panels.",
            "plan": "1. Continue current lifestyle regimen and medication. 2. Routine age-appropriate screening: baseline dental prophylaxis and annual ophthalmological fundus check. 3. Repeat fasting lipid panel and renal parameters in 12 months.",
            "follow_up": "Next annual preventive wellness assessment in 12 months.",
        },
        {
            "chief_complaint": "AI Draft: Acute Sinus Congestion and Cough",
            "days_ago": 1,
            "doctor": dr_asha,
            "finalized_by": None,
            "note_type": "consultation_note",
            "is_ai_draft": True,
            "status": "draft",
            "hpi": "Patient completed AI symptom assessment for acute sinus pressure, facial fullness, and morning dry cough.",
            "exam": "Pending in-person physical examination and physician encounter.",
            "assessment": "AI Draft: Acute viral rhino-sinusitis. Differential includes allergic flare-up.",
            "plan": "Warm saline steam inhalation, hydration, avoidance of environmental allergens. In-person review recommended.",
            "follow_up": "Awaiting attending physician review and electronic signature.",
        },
        {
            "chief_complaint": "AI Draft: Follow-up on Blood Pressure Readings",
            "days_ago": 0,
            "doctor": dr_kabir,
            "finalized_by": None,
            "note_type": "progress_note",
            "is_ai_draft": True,
            "status": "draft",
            "hpi": "Patient recorded home blood pressure log averaging 138-142 / 88-92 mmHg over past 7 days.",
            "exam": "To be verified at upcoming clinical encounter.",
            "assessment": "AI Draft: Stage 1 Essential Hypertension responding to initial lifestyle modification.",
            "plan": "Review daily sodium intake log and consider combination therapy if SBP > 140 persists.",
            "follow_up": "Awaiting clinician electronic review and sign-off.",
        },
    ]

    for n_data in demo_notes:
        existing_note = db.scalar(
            select(ClinicalNote).where(
                ClinicalNote.patient_user_id == aarav.id,
                ClinicalNote.chief_complaint == n_data["chief_complaint"],
            )
        )
        if existing_note is None:
            note_date = now - timedelta(days=n_data["days_ago"])
            is_draft = n_data.get("is_ai_draft", False) or n_data.get("status") == "draft"
            note = ClinicalNote(
                patient_user_id=aarav.id,
                doctor_id=n_data["doctor"].id,
                note_type=n_data["note_type"],
                chief_complaint=n_data["chief_complaint"],
                history_of_present_illness=n_data["hpi"],
                examination_findings=n_data["exam"],
                assessment=n_data["assessment"],
                plan=n_data["plan"],
                follow_up_instructions=n_data["follow_up"],
                is_ai_draft=is_draft,
                status="draft" if is_draft else n_data.get("status", "finalized"),
                finalized_at=None if is_draft else note_date,
                finalized_by_user_id=None if is_draft else (n_data["finalized_by"].id if n_data.get("finalized_by") else aarav.id),
                created_at=note_date,
            )
            db.add(note)
            counts["notes_created"] += 1

    # 5. Medical Documents & Diagnostic Reports (6 physical PDFs generated on disk)
    demo_documents = [
        {
            "filename": "DEMO_CBC_Panel_Aarav_Demo.pdf",
            "title": "Complete Blood Count (CBC) Panel with Differential",
            "document_type": "lab_report",
            "days_ago": 28,
            "category": "Clinical Pathology",
            "parameters": [
                ("Hemoglobin (Hb)", "14.8 g/dL", "13.0 - 17.0 g/dL", "NORMAL"),
                ("Total RBC Count", "5.1 mil/uL", "4.5 - 5.9 mil/uL", "NORMAL"),
                ("Total Leucocyte Count (WBC)", "7,400 /uL", "4,000 - 11,000 /uL", "NORMAL"),
                ("Platelet Count", "265,000 /uL", "150,000 - 450,000 /uL", "NORMAL"),
                ("Neutrophils", "62 %", "40 - 75 %", "NORMAL"),
                ("Lymphocytes", "29 %", "20 - 45 %", "NORMAL"),
                ("Monocytes", "6 %", "2 - 10 %", "NORMAL"),
                ("Eosinophils", "2 %", "1 - 6 %", "NORMAL"),
                ("Erythrocyte Sedimentation Rate (ESR)", "8 mm/hr", "0 - 15 mm/hr", "NORMAL"),
            ],
            "interpretation": "Normocytic, normochromic RBC morphology. Normal total and differential WBC count. Platelets adequate on smear. No atypical cells seen.",
            "doctor": "Dr. S. K. Sharma, MD (Pathology)",
        },
        {
            "filename": "DEMO_CMP_Lipid_Profile_Aarav_Demo.pdf",
            "title": "Comprehensive Metabolic Panel (CMP) & Lipid Profile",
            "document_type": "lab_report",
            "days_ago": 14,
            "category": "Clinical Biochemistry",
            "parameters": [
                ("Fasting Blood Sugar (Glucose)", "94 mg/dL", "70 - 99 mg/dL", "NORMAL"),
                ("Glycated Hemoglobin (HbA1c)", "5.4 %", "< 5.7 % (Normal)", "NORMAL"),
                ("Serum Creatinine", "0.95 mg/dL", "0.70 - 1.30 mg/dL", "NORMAL"),
                ("Estimated GFR (eGFR)", "> 90 mL/min/1.73m²", "> 60 mL/min/1.73m²", "NORMAL"),
                ("Blood Urea Nitrogen (BUN)", "14 mg/dL", "7 - 20 mg/dL", "NORMAL"),
                ("Total Serum Cholesterol", "188 mg/dL", "< 200 mg/dL (Desirable)", "NORMAL"),
                ("LDL Cholesterol", "112 mg/dL", "< 100 mg/dL (Optimal)", "BORDERLINE HIGH"),
                ("HDL Cholesterol", "48 mg/dL", "> 40 mg/dL (Normal)", "NORMAL"),
                ("Serum Triglycerides", "140 mg/dL", "< 150 mg/dL (Normal)", "NORMAL"),
            ],
            "interpretation": "Fasting glucose and HbA1c indicate normal glucose homeostasis. Renal function panel is intact. Mild borderline elevation of LDL cholesterol, manageable with dietary adjustments.",
            "doctor": "Dr. Neha Verma, MD (Biochemistry)",
        },
        {
            "filename": "DEMO_12_Lead_ECG_Report_Aarav_Demo.pdf",
            "title": "12-Lead Electrocardiogram (ECG) Diagnostic Report",
            "document_type": "imaging",
            "days_ago": 14,
            "category": "Cardiovascular Diagnostics",
            "parameters": [
                ("Ventricular Heart Rate", "72 bpm", "60 - 100 bpm", "NORMAL"),
                ("PR Interval", "156 ms", "120 - 200 ms", "NORMAL"),
                ("QRS Duration", "88 ms", "60 - 100 ms", "NORMAL"),
                ("QT / QTc Interval", "380 / 412 ms", "< 440 ms (Male)", "NORMAL"),
                ("Mean Frontal P-QRS-T Axes", "+52° / +45° / +40°", "Normal Axis (-30° to +90°)", "NORMAL"),
                ("ST Segment & T Wave Morphology", "Isoelectric / Normal", "No ST elevation or depression", "NORMAL"),
            ],
            "interpretation": "Normal Sinus Rhythm at 72 bpm. Normal intervals and axis. No pathological Q waves, ST deviations, or T wave inversions. No evidence of chamber enlargement or active ischemia.",
            "doctor": "Dr. Kabir Sample, MD, DM (Cardiology)",
        },
        {
            "filename": "DEMO_Chest_XRay_Radiology_Aarav_Demo.pdf",
            "title": "Chest X-Ray (PA View) Radiology Report",
            "document_type": "imaging",
            "days_ago": 14,
            "category": "Diagnostic Radiology",
            "parameters": [
                ("Projection & Technique", "Posteroanterior (PA) View", "Adequate inspiratory effort", "NORMAL"),
                ("Pulmonary Parenchyma", "Clear lung fields bilaterally", "No focal consolidation or effusion", "NORMAL"),
                ("Cardiothoracic Ratio (CTR)", "0.44", "< 0.50 (Normal cardiac size)", "NORMAL"),
                ("Mediastinum & Hilar Contours", "Normal configuration", "No lymphadenopathy or mass", "NORMAL"),
                ("Costophrenic & Cardiophrenic Sulci", "Sharp bilaterally", "No pleural thickening or blunting", "NORMAL"),
                ("Thoracic Cage & Soft Tissues", "Intact osseous structures", "No acute fracture or lytic lesion", "NORMAL"),
            ],
            "interpretation": "Unremarkable chest radiograph. No active pulmonary parenchymal consolidation, pleural effusion, pneumothorax, or cardiomegaly.",
            "doctor": "Dr. Rajesh Gupta, MD (Radiodiagnosis)",
        },
        {
            "filename": "DEMO_Urinalysis_Routine_Aarav_Demo.pdf",
            "title": "Urine Routine & Microscopic Examination (Urinalysis)",
            "document_type": "lab_report",
            "days_ago": 7,
            "category": "Clinical Pathology",
            "parameters": [
                ("Physical Appearance & Color", "Pale Yellow, Clear", "Straw / Yellow, Clear", "NORMAL"),
                ("Specific Gravity", "1.018", "1.005 - 1.030", "NORMAL"),
                ("pH Reaction", "6.2", "4.5 - 8.0", "NORMAL"),
                ("Urinary Protein / Albumin", "Negative", "Negative (< 15 mg/dL)", "NORMAL"),
                ("Urinary Glucose", "Negative", "Negative", "NORMAL"),
                ("Ketones & Bilirubin", "Negative", "Negative", "NORMAL"),
                ("Microscopic Red Blood Cells (RBC)", "0 - 1 / HPF", "0 - 2 / HPF", "NORMAL"),
                ("Microscopic Pus Cells (WBC)", "1 - 2 / HPF", "0 - 5 / HPF", "NORMAL"),
            ],
            "interpretation": "Normal routine and microscopic urinalysis. Negative for proteinuria, glycosuria, hematuria, or bacteriuria.",
            "doctor": "Dr. S. K. Sharma, MD (Pathology)",
        },
        {
            "filename": "DEMO_Pulmonary_Function_Spirometry_Aarav_Demo.pdf",
            "title": "Pulmonary Function Test (Spirometry) Report",
            "document_type": "other",
            "days_ago": 2,
            "category": "Pulmonary Function Laboratory",
            "parameters": [
                ("Forced Vital Capacity (FVC)", "4.62 L (98 % pred)", ">= 80 % predicted", "NORMAL"),
                ("Forced Expiratory Volume in 1s (FEV1)", "3.88 L (96 % pred)", ">= 80 % predicted", "NORMAL"),
                ("FEV1 / FVC Ratio", "84.0 %", ">= 70.0 % (Normal limit)", "NORMAL"),
                ("Forced Expiratory Flow (FEF 25-75%)", "4.10 L/s (92 % pred)", ">= 65 % predicted", "NORMAL"),
                ("Peak Expiratory Flow Rate (PEFR)", "580 L/min", ">= 80 % predicted", "NORMAL"),
            ],
            "interpretation": "Spirometry demonstrates normal baseline ventilatory volumes and flow rates. No obstructive or restrictive ventilatory impairment observed.",
            "doctor": "Dr. Asha Demo, MD (General Medicine)",
        },
    ]

    for doc_data in demo_documents:
        filepath = os.path.join(DOCUMENTS_DIR, doc_data["filename"])
        file_size = 0
        if not os.path.exists(filepath):
            file_size = _create_sample_diagnostic_pdf(
                filepath=filepath,
                hospital_name=hospital_name,
                patient_name="Aarav Demo",
                patient_age_gender="32Y / Male",
                test_title=doc_data["title"],
                test_category=doc_data["category"],
                collection_date=(now - timedelta(days=doc_data["days_ago"])).strftime("%d %b %Y"),
                parameters=doc_data["parameters"],
                interpretation=doc_data["interpretation"],
                signing_doctor=doc_data["doctor"],
            )
        else:
            file_size = os.path.getsize(filepath)

        existing_doc = db.scalar(
            select(MedicalDocument).where(
                MedicalDocument.patient_user_id == aarav.id,
                MedicalDocument.title == doc_data["title"],
            )
        )
        structured_extracted_data = {
            "category": doc_data["category"],
            "status": "VERIFIED",
            "parameters": [
                {"name": p[0], "value": p[1], "reference_range": p[2], "status": p[3]}
                for p in doc_data["parameters"]
            ],
            "interpretation": doc_data["interpretation"],
            "signing_doctor": doc_data["doctor"],
        }
        if existing_doc is None:
            doc_date = now - timedelta(days=doc_data["days_ago"])
            doc = MedicalDocument(
                patient_user_id=aarav.id,
                uploaded_by_user_id=dr_asha_user.id if dr_asha_user else aarav.id,
                title=doc_data["title"],
                document_type=doc_data["document_type"],
                file_path=filepath,
                file_size=file_size,
                mime_type="application/pdf",
                notes=f"Synthetic diagnostic record for {doc_data['title']}.",
                extracted_data=structured_extracted_data,
                created_at=doc_date,
            )
            db.add(doc)
            counts["documents_created"] += 1
        elif not (existing_doc.extracted_data or {}).get("parameters"):
            existing_doc.extracted_data = structured_extracted_data

    # 6. Comprehensive Clinical Records for Sneha Vishwakarma (sneha@gmail.com) if present
    sneha = db.scalar(select(User).where(User.email == "sneha@gmail.com"))
    if sneha:
        # Sneha Allergies
        sneha_allergies = [
            (
                "Sulfa Drugs (Sulfamethoxazole, Trimethoprim)",
                "allergy",
                "moderate",
                f"Erythematous macular rash, pruritus, and facial swelling ({SEED_MARKER})",
            ),
            (
                "NSAIDs (Aspirin, Mefenamic Acid)",
                "medication_reaction",
                "mild",
                f"Dyspepsia, epigastric burning, and nausea ({SEED_MARKER})",
            ),
        ]
        for allergen, cat, sev, reaction in sneha_allergies:
            existing_alg = db.scalar(
                select(PatientAllergy).where(
                    PatientAllergy.patient_user_id == sneha.id,
                    PatientAllergy.allergen_or_condition == allergen,
                )
            )
            if existing_alg is None:
                db.add(
                    PatientAllergy(
                        patient_user_id=sneha.id,
                        allergen_or_condition=allergen,
                        category=cat,
                        severity=sev,
                        reaction=reaction,
                        recorded_by_user_id=dr_asha_user.id if dr_asha_user else sneha.id,
                        is_active=True,
                    )
                )
                counts["allergies_created"] += 1

        # Sneha AI Reports (5 comprehensive assessments)
        sneha_reports = [
            {
                "title": "Comprehensive Acute Pharyngitis & Upper Respiratory Assessment",
                "report_type": "symptom_assessment",
                "urgency_level": "routine",
                "days_ago": 18,
                "doctor": dr_asha,
                "summary": "Clinical synthesis of 3-day acute pharyngeal irritation, low-grade fever, and nasal congestion. Centor criteria calculation (Score 1) indicates viral etiology with low streptococcal likelihood.",
                "findings": [
                    {"finding": "Pharyngeal mucosal erythema without exudates", "significance": "Consistent with viral pharyngitis"},
                    {"finding": "Bilateral clear nasal discharge", "significance": "Upper respiratory viral presentation"},
                    {"finding": "SpO2 98% on room air", "significance": "Normal pulmonary gas exchange"},
                ],
                "red_flags": [],
                "next_steps": [
                    "Warm saline gargles 3-4 times daily",
                    "Hydration maintenance with warm liquids",
                    "Paracetamol 650mg SOS for throat discomfort (Avoid NSAIDs due to recorded adverse reaction)",
                    "In-person evaluation if fever >101°F persists >48 hours",
                ],
                "evidence": [
                    {"title": "WHO Guidelines on Pharyngitis Clinical Synthesis", "provenance": "WHO SEARO", "url": "https://who.int/guidelines/pharyngitis"},
                    {"title": "NIH MedQuAD Pharyngitis Care Guide", "provenance": "NIH MedQuAD", "url": "https://medlineplus.gov/sorethroat.html"},
                ],
            },
            {
                "title": "Annual Preventive Wellness & Routine Metabolic Screening",
                "report_type": "visit_summary",
                "urgency_level": "routine",
                "days_ago": 12,
                "doctor": dr_kabir,
                "summary": "Longitudinal preventive health evaluation and metabolic screening review. Blood pressure 118/76 mmHg, BMI 22.4 kg/m². Fasting blood glucose and lipid panel within optimal biological reference intervals.",
                "findings": [
                    {"finding": "Normotensive sitting blood pressure (118/76 mmHg)", "significance": "Optimal cardiovascular profile"},
                    {"finding": "Fasting blood sugar 88 mg/dL and HbA1c 5.1%", "significance": "Optimal glycemic control"},
                    {"finding": "Mild 25-OH Vitamin D insufficiency (19.4 ng/mL)", "significance": "Reversible nutritional insufficiency"},
                ],
                "red_flags": [],
                "next_steps": [
                    "Vitamin D3 60,000 IU weekly supplementation for 4 weeks",
                    "Maintain 150 minutes weekly moderate aerobic physical activity",
                    "Balanced diet rich in leafy greens and adequate dietary calcium",
                    "Routine follow-up laboratory evaluation in 6 months",
                ],
                "evidence": [
                    {"title": "WHO Global Health Action Plan on Noncommunicable Disease Prevention", "provenance": "WHO", "url": "https://who.int/publications/ncd-prevention"},
                ],
            },
            {
                "title": "Seasonal Allergic Rhinitis & Sinus Congestion Management Assessment",
                "report_type": "symptom_assessment",
                "urgency_level": "routine",
                "days_ago": 7,
                "doctor": dr_asha,
                "summary": "Evaluation of episodic morning sneezing, ocular pruritus, and nasal congestion triggered by seasonal pollen changes. Screened negative for acute bacterial rhinosinusitis.",
                "findings": [
                    {"finding": "Pale, boggy nasal turbinates on rhinoscopy", "significance": "Classic allergic mucosal edema"},
                    {"finding": "Absence of facial pain or purulent discharge", "significance": "Excludes acute bacterial sinusitis"},
                ],
                "red_flags": [],
                "next_steps": [
                    "Daily Cetirizine 10mg at bedtime",
                    "Normal saline nasal spray twice daily",
                    "Keep bedroom windows closed during peak morning pollen hours",
                ],
                "evidence": [
                    {"title": "Allergic Rhinitis and its Impact on Asthma (ARIA) Guidelines", "provenance": "ARIA", "url": "https://aria.org/guidelines"},
                ],
            },
            {
                "title": "Post-Consultation Recovery & Treatment Monitoring",
                "report_type": "follow_up",
                "urgency_level": "routine",
                "days_ago": 3,
                "doctor": dr_kabir,
                "summary": "Patient reports complete resolution of upper respiratory symptoms and good tolerance of prescribed nutritional supplementation. No adverse drug events or hypersensitivity reactions.",
                "findings": [
                    {"finding": "Complete symptom resolution reported", "significance": "Uncomplicated recovery"},
                    {"finding": "Medication compliance verified", "significance": "Optimal therapeutic adherence"},
                ],
                "red_flags": [],
                "next_steps": [
                    "Complete scheduled vitamin D supplementation course",
                    "Continue regular health maintenance and physical fitness",
                ],
                "evidence": [
                    {"title": "CareVoice Clinical Synthesis Protocol", "provenance": "CareVoice Clinical Hub", "url": "https://carevoice.test/clinical/guidelines"},
                ],
            },
            {
                "title": "Hydration, Electrolyte & Dietary Wellness Assessment",
                "report_type": "symptom_assessment",
                "urgency_level": "routine",
                "days_ago": 1,
                "doctor": dr_asha,
                "summary": "Assessment of mild afternoon fatigue and work-related headache after prolonged computer screen time. Hydration, ergonomic posture, and 20-20-20 visual rest protocol reviewed.",
                "findings": [
                    {"finding": "Absence of neurological focal deficits", "significance": "Benign tension-type headache etiology"},
                    {"finding": "Adequate baseline vitals (BP 116/74 mmHg, Pulse 72 bpm)", "significance": "Physiologically stable"},
                ],
                "red_flags": [],
                "next_steps": [
                    "Target 2.0 - 2.5 Liters daily oral fluid intake",
                    "Implement 20-20-20 screen break rule during work hours",
                    "Screen ergonomics adjustment: monitor at eye level",
                ],
                "evidence": [
                    {"title": "NIH Clinical Guide: Headaches and Digital Eye Strain", "provenance": "NIH MedQuAD", "url": "https://medlineplus.gov/headache.html"},
                ],
            },
        ]
        for rep in sneha_reports:
            existing_rep = db.scalar(
                select(MedicalReport).where(
                    MedicalReport.patient_user_id == sneha.id,
                    MedicalReport.title == rep["title"],
                )
            )
            if existing_rep is None:
                rep_date = now - timedelta(days=rep["days_ago"])
                db.add(
                    MedicalReport(
                        patient_user_id=sneha.id,
                        doctor_id=rep["doctor"].id,
                        report_type=rep["report_type"],
                        title=rep["title"],
                        summary=rep["summary"],
                        urgency_level=rep["urgency_level"],
                        red_flags=rep["red_flags"],
                        findings=rep["findings"],
                        recommended_next_steps=rep["next_steps"],
                        evidence_sources=rep["evidence"],
                        disclaimer=f"DEMO DATA — NOT A REAL PATIENT ASSESSMENT ({SEED_MARKER}). CareVoice AI reports provide structured educational assessment and clinical synthesis only.",
                        status="reviewed",
                        reviewed_by_doctor_id=rep["doctor"].id,
                        reviewed_at=rep_date + timedelta(hours=2),
                        created_at=rep_date,
                    )
                )
                counts["ai_reports_created"] += 1

        # Sneha Prescriptions (4 prescriptions: 3 finalized, 1 AI draft)
        sneha_prescriptions = [
            {
                "prescription_number": "RX-20261005-SNEHA01",
                "days_ago": 18,
                "doctor": dr_asha,
                "finalized_by": dr_asha_user,
                "diagnosis": "Acute Pharyngitis & Upper Respiratory Tract Infection",
                "notes": f"Sulfa allergy documented. Prescribed Amoxicillin-Clavulanate. Maintain hydration. ({SEED_MARKER})",
                "warnings": [
                    "Allergy verified: Sulfa drugs avoided.",
                    "NSAID sensitivity: Aspirin avoided, Paracetamol safely prescribed.",
                ],
                "items": [
                    ("Amoxicillin-Clavulanate", "625 mg", "tablet", "oral", "1-0-1 (Twice daily)", "5 days", "10 tablets", "Take with or right after food"),
                    ("Paracetamol", "650 mg", "tablet", "oral", "1-0-1 (SOS / As needed)", "3 days", "6 tablets", "Take after food for fever or discomfort"),
                    ("Cetirizine", "10 mg", "tablet", "oral", "0-0-1 (Night)", "5 days", "5 tablets", "Take at bedtime with water"),
                ],
            },
            {
                "prescription_number": "RX-20261011-SNEHA02",
                "days_ago": 12,
                "doctor": dr_kabir,
                "finalized_by": dr_kabir_user,
                "diagnosis": "Mild Functional Dyspepsia & Airway Hyperreactivity",
                "notes": f"Proton pump inhibitor and leukotriene receptor antagonist. ({SEED_MARKER})",
                "warnings": [
                    "Allergy profile verified. No contraindications detected.",
                ],
                "items": [
                    ("Pantoprazole", "40 mg", "tablet", "oral", "1-0-0 (Morning)", "14 days", "14 tablets", "Take on empty stomach 30 minutes before breakfast"),
                    ("Montelukast", "10 mg", "tablet", "oral", "0-0-1 (Night)", "10 days", "10 tablets", "Take at bedtime with water"),
                ],
            },
            {
                "prescription_number": "RX-20261016-SNEHA03",
                "days_ago": 7,
                "doctor": dr_asha,
                "finalized_by": dr_asha_user,
                "diagnosis": "Nutritional Vitamin D3 Insufficiency & Health Maintenance",
                "notes": f"High-dose weekly vitamin D3 protocol. ({SEED_MARKER})",
                "warnings": [
                    "Allergy profile verified. No contraindications detected.",
                ],
                "items": [
                    ("Vitamin D3 (Cholecalciferol)", "60,000 IU", "capsule", "oral", "1-0-0 (Once weekly)", "4 weeks", "4 capsules", "Take once weekly with milk or after a meal"),
                    ("Calcium Citrate", "500 mg", "tablet", "oral", "0-1-0 (After lunch)", "30 days", "30 tablets", "Take with water after meals"),
                ],
            },
            {
                "prescription_number": "RX-20261022-SNEHA04",
                "days_ago": 1,
                "doctor": dr_asha,
                "finalized_by": None,
                "is_ai_draft": True,
                "status": "draft",
                "diagnosis": "AI Draft: Seasonal Environmental Allergic Rhinitis",
                "notes": f"AI Generated Draft: Awaiting attending physician validation and digital signature. ({SEED_MARKER})",
                "warnings": [
                    "AI Screening: Sulfa allergy confirmed on record.",
                    "NSAID sensitivity noted: Paracetamol recommended if needed.",
                ],
                "items": [
                    ("Azithromycin", "500 mg", "tablet", "oral", "1-0-0 (Once daily)", "3 days", "3 tablets", "Take 1 hour before or 2 hours after meals"),
                    ("Levocetirizine", "5 mg", "tablet", "oral", "0-0-1 (Night)", "7 days", "7 tablets", "Take at bedtime with water"),
                ],
            },
        ]
        for rx_data in sneha_prescriptions:
            existing_rx = db.scalar(
                select(Prescription).where(
                    Prescription.patient_user_id == sneha.id,
                    Prescription.prescription_number == rx_data["prescription_number"],
                )
            )
            if existing_rx is None:
                rx_date = now - timedelta(days=rx_data["days_ago"])
                is_draft = rx_data.get("is_ai_draft", False) or rx_data.get("status") == "draft"
                rx = Prescription(
                    prescription_number=rx_data["prescription_number"],
                    patient_user_id=sneha.id,
                    doctor_id=rx_data["doctor"].id,
                    diagnosis=rx_data["diagnosis"],
                    notes=rx_data["notes"],
                    allergy_warnings=rx_data["warnings"],
                    is_ai_draft=is_draft,
                    status="draft" if is_draft else rx_data.get("status", "finalized"),
                    finalized_at=None if is_draft else rx_date,
                    finalized_by_user_id=None if is_draft else (rx_data["finalized_by"].id if rx_data.get("finalized_by") else sneha.id),
                    created_at=rx_date,
                )
                for it in rx_data["items"]:
                    rx.items.append(
                        PrescriptionItem(
                            medication_name=it[0],
                            strength=it[1],
                            dosage_form=it[2],
                            route=it[3],
                            frequency=it[4],
                            duration=it[5],
                            quantity=it[6],
                            instructions=it[7],
                        )
                    )
                db.add(rx)
                counts["prescriptions_created"] += 1

        # Sneha Clinical Notes (4 notes: 3 finalized, 1 AI draft)
        sneha_notes = [
            {
                "note_type": "outpatient_consultation",
                "days_ago": 18,
                "doctor": dr_asha,
                "finalized_by": dr_asha_user,
                "chief_complaint": "Sore throat, nasal congestion, and low-grade fever for 3 days.",
                "hpi": f"29-year-old female presenting with 3-day history of scratchy throat, nasal congestion, rhinorrhea, and mild dry cough. No dyspnea or chest pain. Negative for acute red flags. ({SEED_MARKER})",
                "exam": "Throat: mild erythema, no tonsillar exudates. Chest: clear bilaterally. SpO2 98%, HR 76 bpm, BP 118/76 mmHg, Temp 99.2°F.",
                "assessment": "Acute Viral Pharyngitis & Upper Respiratory Infection. Sulfa drug allergy documented.",
                "plan": f"Supportive symptomatic therapy, warm saline gargles, adequate hydration. Amoxicillin-Clavulanate prescribed. ({SEED_MARKER})",
                "follow_up": "Return to clinic if fever exceeds 101°F or difficulty swallowing develops.",
            },
            {
                "note_type": "follow_up",
                "days_ago": 12,
                "doctor": dr_kabir,
                "finalized_by": dr_kabir_user,
                "chief_complaint": "Follow-up for seasonal allergic rhinitis and mild dyspepsia.",
                "hpi": f"Patient reports substantial improvement in pharyngitis symptoms. Occasional mild morning nasal congestion and occasional acid reflux after spicy meals. ({SEED_MARKER})",
                "exam": "Abdomen: soft, non-tender, no organomegaly. BP 120/78 mmHg, HR 74 bpm regular. Heart sounds normal.",
                "assessment": "Resolving Upper Respiratory Episode; Mild Functional Dyspepsia.",
                "plan": f"Pantoprazole 40mg before meals; Montelukast 10mg at night for 10 days. Dietary counseling provided. ({SEED_MARKER})",
                "follow_up": "Review in 2 weeks or SOS.",
            },
            {
                "note_type": "wellness_examination",
                "days_ago": 7,
                "doctor": dr_asha,
                "finalized_by": dr_asha_user,
                "chief_complaint": "Annual preventive health assessment and routine blood work review.",
                "hpi": f"Comprehensive health maintenance review. Patient reports good energy levels, regular exercise 3-4 days/week. No cardiovascular or pulmonary complaints. ({SEED_MARKER})",
                "exam": "General: alert, well-nourished. Vital signs: BP 116/74 mmHg, HR 72 bpm, BMI 22.4 kg/m² (normal range). Systemic examination within normal limits.",
                "assessment": "Healthy adult female, optimal cardiovascular profile, mild Vitamin D insufficiency noted on lab work.",
                "plan": f"Vitamin D3 60,000 IU weekly supplementation for 4 weeks. Continue balanced diet and physical activity. ({SEED_MARKER})",
                "follow_up": "Repeat 25-OH Vitamin D level in 3 months; routine annual review in 1 year.",
            },
            {
                "note_type": "outpatient_consultation",
                "days_ago": 1,
                "doctor": dr_asha,
                "finalized_by": None,
                "is_ai_draft": True,
                "status": "draft",
                "chief_complaint": "AI Ambient Scribe Intake: Mild seasonal cough and environmental allergy symptoms.",
                "hpi": f"AI Scribe ambient recording transcript synthesized: Patient described mild dry cough triggered by recent dust exposure and seasonal weather change. No fever, hemoptysis, or nocturnal dyspnea. ({SEED_MARKER})",
                "exam": "Automated vitals sync: SpO2 98%, Heart Rate 75 bpm, BP 118/76 mmHg. Respiratory rate 16/min.",
                "assessment": "AI Draft: Seasonal Environmental Allergic Rhinitis with Mild Reactive Cough.",
                "plan": f"AI Draft recommendation: Second-generation antihistamine (Levocetirizine), saline nasal sprays. Awaiting physician validation and digital signature. ({SEED_MARKER})",
                "follow_up": "Doctor review pending.",
            },
        ]
        for n_data in sneha_notes:
            existing_note = db.scalar(
                select(ClinicalNote).where(
                    ClinicalNote.patient_user_id == sneha.id,
                    ClinicalNote.chief_complaint == n_data["chief_complaint"],
                )
            )
            if existing_note is None:
                note_date = now - timedelta(days=n_data["days_ago"])
                is_draft = n_data.get("is_ai_draft", False) or n_data.get("status") == "draft"
                db.add(
                    ClinicalNote(
                        patient_user_id=sneha.id,
                        doctor_id=n_data["doctor"].id,
                        note_type=n_data["note_type"],
                        chief_complaint=n_data["chief_complaint"],
                        history_of_present_illness=n_data["hpi"],
                        examination_findings=n_data["exam"],
                        assessment=n_data["assessment"],
                        plan=n_data["plan"],
                        follow_up_instructions=n_data["follow_up"],
                        is_ai_draft=is_draft,
                        status="draft" if is_draft else n_data.get("status", "finalized"),
                        finalized_at=None if is_draft else note_date,
                        finalized_by_user_id=None if is_draft else (n_data["finalized_by"].id if n_data.get("finalized_by") else sneha.id),
                        created_at=note_date,
                    )
                )
                counts["notes_created"] += 1

        # Sneha Medical Documents (5 physical PDFs generated on disk)
        sneha_documents = [
            {
                "filename": "DEMO_CBC_Panel_Sneha_Vishwakarma.pdf",
                "title": "Complete Blood Count (CBC) Panel with Differential",
                "document_type": "lab_report",
                "days_ago": 20,
                "category": "Clinical Pathology",
                "parameters": [
                    ("Hemoglobin (Hb)", "13.6 g/dL", "12.0 - 15.5 g/dL", "NORMAL"),
                    ("Total RBC Count", "4.65 mil/uL", "4.0 - 5.2 mil/uL", "NORMAL"),
                    ("Total Leucocyte Count (WBC)", "6,800 /uL", "4,000 - 11,000 /uL", "NORMAL"),
                    ("Platelet Count", "275,000 /uL", "150,000 - 450,000 /uL", "NORMAL"),
                    ("Neutrophils", "60 %", "40 - 75 %", "NORMAL"),
                    ("Lymphocytes", "32 %", "20 - 45 %", "NORMAL"),
                    ("Monocytes", "5 %", "2 - 10 %", "NORMAL"),
                    ("Eosinophils", "3 %", "1 - 6 %", "NORMAL"),
                    ("ESR", "10 mm/hr", "0 - 20 mm/hr", "NORMAL"),
                ],
                "interpretation": "Normocytic normochromic red cells. Normal total and differential leukocyte count. Platelet count adequate.",
                "doctor": "Dr. S. K. Sharma, MD (Pathology)",
            },
            {
                "filename": "DEMO_CMP_Lipid_Profile_Sneha_Vishwakarma.pdf",
                "title": "Comprehensive Metabolic Panel (CMP) & Lipid Profile",
                "document_type": "lab_report",
                "days_ago": 12,
                "category": "Clinical Biochemistry",
                "parameters": [
                    ("Fasting Blood Sugar (Glucose)", "88 mg/dL", "70 - 99 mg/dL", "NORMAL"),
                    ("Glycated Hemoglobin (HbA1c)", "5.1 %", "< 5.7 %", "NORMAL"),
                    ("Serum Creatinine", "0.82 mg/dL", "0.55 - 1.02 mg/dL", "NORMAL"),
                    ("eGFR", "> 90 mL/min/1.73m²", "> 60 mL/min/1.73m²", "NORMAL"),
                    ("Total Serum Cholesterol", "172 mg/dL", "< 200 mg/dL", "NORMAL"),
                    ("LDL Cholesterol", "96 mg/dL", "< 100 mg/dL", "NORMAL"),
                    ("HDL Cholesterol", "56 mg/dL", "> 50 mg/dL", "NORMAL"),
                    ("Serum Triglycerides", "110 mg/dL", "< 150 mg/dL", "NORMAL"),
                ],
                "interpretation": "Normal fasting glucose and HbA1c confirming euglycemia. Renal function intact. Desirable lipid profile.",
                "doctor": "Dr. Neha Verma, MD (Biochemistry)",
            },
            {
                "filename": "DEMO_Thyroid_Profile_Sneha_Vishwakarma.pdf",
                "title": "Complete Thyroid Function Profile (TSH, Free T3, Free T4)",
                "document_type": "lab_report",
                "days_ago": 12,
                "category": "Endocrinology Laboratory",
                "parameters": [
                    ("Thyroid Stimulating Hormone (TSH)", "2.18 uIU/mL", "0.45 - 4.50 uIU/mL", "NORMAL"),
                    ("Free Triiodothyronine (FT3)", "3.1 pg/mL", "2.0 - 4.4 pg/mL", "NORMAL"),
                    ("Free Thyroxine (FT4)", "1.24 ng/dL", "0.82 - 1.77 ng/dL", "NORMAL"),
                    ("25-OH Vitamin D Total", "19.4 ng/mL", "30.0 - 100.0 ng/mL", "BORDERLINE LOW"),
                ],
                "interpretation": "Euthyroid state confirmed. Baseline 25-OH Vitamin D level shows mild insufficiency amenable to oral supplementation.",
                "doctor": "Dr. Neha Verma, MD (Biochemistry)",
            },
            {
                "filename": "DEMO_Urinalysis_Sneha_Vishwakarma.pdf",
                "title": "Urine Routine & Microscopic Examination (Urinalysis)",
                "document_type": "lab_report",
                "days_ago": 7,
                "category": "Clinical Pathology",
                "parameters": [
                    ("Physical Appearance", "Pale Yellow, Clear", "Straw / Yellow, Clear", "NORMAL"),
                    ("Specific Gravity", "1.016", "1.005 - 1.030", "NORMAL"),
                    ("pH Reaction", "6.5", "4.5 - 8.0", "NORMAL"),
                    ("Urinary Protein", "Negative", "Negative", "NORMAL"),
                    ("Urinary Glucose", "Negative", "Negative", "NORMAL"),
                    ("Ketones", "Negative", "Negative", "NORMAL"),
                    ("Microscopic RBC", "0 - 1 / HPF", "0 - 2 / HPF", "NORMAL"),
                    ("Microscopic Pus Cells", "1 - 2 / HPF", "0 - 5 / HPF", "NORMAL"),
                ],
                "interpretation": "Normal urinalysis findings. Negative for proteinuria, hematuria, or active sediment.",
                "doctor": "Dr. S. K. Sharma, MD (Pathology)",
            },
            {
                "filename": "DEMO_Chest_XRay_Sneha_Vishwakarma.pdf",
                "title": "Chest X-Ray (PA View) Diagnostic Radiology Report",
                "document_type": "imaging",
                "days_ago": 12,
                "category": "Diagnostic Radiology",
                "parameters": [
                    ("Pulmonary Parenchyma", "Clear lung fields bilaterally", "No focal consolidation or effusion", "NORMAL"),
                    ("Cardiothoracic Ratio (CTR)", "0.42", "< 0.50 (Normal cardiac size)", "NORMAL"),
                    ("Mediastinal Contours", "Normal configuration", "No mass or adenopathy", "NORMAL"),
                    ("Costophrenic Angles", "Sharp bilaterally", "No blunting", "NORMAL"),
                    ("Thoracic Skeleton", "Normal osseous structures", "Intact", "NORMAL"),
                ],
                "interpretation": "Normal chest radiograph. No evidence of active pulmonary disease, infiltration, or cardiomegaly.",
                "doctor": "Dr. Rajesh Gupta, MD (Radiodiagnosis)",
            },
        ]
        for doc_data in sneha_documents:
            filepath = os.path.join(DOCUMENTS_DIR, doc_data["filename"])
            file_size = 0
            if not os.path.exists(filepath):
                file_size = _create_sample_diagnostic_pdf(
                    filepath=filepath,
                    hospital_name=hospital_name,
                    patient_name="Sneha Vishwakarma",
                    patient_age_gender="29Y / Female",
                    test_title=doc_data["title"],
                    test_category=doc_data["category"],
                    collection_date=(now - timedelta(days=doc_data["days_ago"])).strftime("%d %b %Y"),
                    parameters=doc_data["parameters"],
                    interpretation=doc_data["interpretation"],
                    signing_doctor=doc_data["doctor"],
                )
            else:
                file_size = os.path.getsize(filepath)

            existing_doc = db.scalar(
                select(MedicalDocument).where(
                    MedicalDocument.patient_user_id == sneha.id,
                    MedicalDocument.title == doc_data["title"],
                )
            )
            structured_extracted_data = {
                "category": doc_data["category"],
                "status": "VERIFIED",
                "parameters": [
                    {"name": p[0], "value": p[1], "reference_range": p[2], "status": p[3]}
                    for p in doc_data["parameters"]
                ],
                "interpretation": doc_data["interpretation"],
                "signing_doctor": doc_data["doctor"],
            }
            if existing_doc is None:
                doc_date = now - timedelta(days=doc_data["days_ago"])
                db.add(
                    MedicalDocument(
                        patient_user_id=sneha.id,
                        uploaded_by_user_id=dr_asha_user.id if dr_asha_user else sneha.id,
                        title=doc_data["title"],
                        document_type=doc_data["document_type"],
                        file_path=filepath,
                        file_size=file_size,
                        mime_type="application/pdf",
                        notes=f"Diagnostic report for {doc_data['title']} ({SEED_MARKER}).",
                        extracted_data=structured_extracted_data,
                        created_at=doc_date,
                    )
                )
                counts["documents_created"] += 1
            elif not (existing_doc.extracted_data or {}).get("parameters"):
                existing_doc.extracted_data = structured_extracted_data

    db.flush()
    return counts


def seed_demo_data(db: Session) -> dict[str, int]:
    """Add missing synthetic records without changing existing application data."""
    if settings.app_env.strip().lower() not in {"development", "test"}:
        raise RuntimeError("Demo seeding is disabled unless APP_ENV is development or test.")
    hospitals, hospitals_created = _get_or_create_hospitals(db)
    doctors, doctors_created = _get_or_create_doctors(db, hospitals)
    patients, patient_users_created, patient_profiles_created = _get_or_create_patients(db)
    hospital_admins_created = _ensure_hospital_admins(db, hospitals)
    doctor_accounts_created = _ensure_doctor_accounts(db, doctors, hospitals)
    appointments_created = _ensure_appointments(db, doctors, patients, hospitals)
    invoices_created, payments_created = _ensure_invoices_and_payments(db)
    conversations_created = _ensure_demo_conversations(db, patients)
    clinical_counts = _ensure_demo_clinical_records(db, patients, doctors, hospitals)
    return {
        "hospitals_created": hospitals_created,
        "doctors_created": doctors_created,
        "patients_created": patient_profiles_created,
        "patient_accounts_created": patient_users_created,
        "hospital_admins_created": hospital_admins_created,
        "doctor_accounts_created": doctor_accounts_created,
        "appointments_created": appointments_created,
        "invoices_created": invoices_created,
        "payments_created": payments_created,
        "conversations_created": conversations_created,
        **clinical_counts,
    }


def clean_demo_data(db: Session) -> dict[str, int]:
    """Safely remove synthetic demo records without affecting real user data."""
    if settings.app_env.strip().lower() not in {"development", "test"}:
        raise RuntimeError("Demo cleaning is disabled unless APP_ENV is development or test.")

    cleaned_counts: dict[str, int] = {
        "prescription_items_removed": 0,
        "prescriptions_removed": 0,
        "clinical_notes_removed": 0,
        "medical_reports_removed": 0,
        "medical_documents_removed": 0,
        "allergies_removed": 0,
        "messages_removed": 0,
        "conversations_removed": 0,
        "payments_removed": 0,
        "invoices_removed": 0,
        "appointment_events_removed": 0,
        "appointments_removed": 0,
        "doctor_schedules_removed": 0,
        "doctor_qualifications_removed": 0,
        "doctors_removed": 0,
        "patients_removed": 0,
        "users_removed": 0,
        "hospitals_removed": 0,
    }

    demo_emails = [
        "patient01@demo.carevoice.test",
        "patient02@demo.carevoice.test",
        "doctor01@demo.carevoice.test",
        "doctor02@demo.carevoice.test",
        "admin01@demo.carevoice.test",
        "admin02@demo.carevoice.test",
    ]
    demo_users = db.scalars(
        select(User).where(
            User.email.in_(demo_emails) | User.email.like("%@demo.carevoice.test")
        )
    ).all()
    demo_user_ids = [u.id for u in demo_users]

    demo_doctors = (
        db.scalars(
            select(Doctor).where(
                Doctor.id.in_([u.doctor_id for u in demo_users if u.doctor_id is not None])
                | Doctor.bio.like(f"{SEED_MARKER}: fictional clinician %")
            )
        ).all()
        if demo_users
        else []
    )
    demo_doctor_ids = [d.id for d in demo_doctors]

    # 1. Prescription items & Prescriptions
    demo_prescriptions = (
        db.scalars(
            select(Prescription).where(
                (Prescription.patient_user_id.in_(demo_user_ids))
                | (Prescription.prescription_number.like("RX-DEMO-%"))
                | (Prescription.prescription_number.like("RX-202610%"))
                | (Prescription.notes.like(f"%{SEED_MARKER}%"))
            )
        ).all()
        if demo_user_ids
        else []
    )
    demo_rx_ids = [rx.id for rx in demo_prescriptions]
    if demo_rx_ids:
        deleted_items = db.execute(
            delete(PrescriptionItem).where(PrescriptionItem.prescription_id.in_(demo_rx_ids))
        ).rowcount
        cleaned_counts["prescription_items_removed"] = deleted_items
        deleted_rxs = db.execute(
            delete(Prescription).where(Prescription.id.in_(demo_rx_ids))
        ).rowcount
        cleaned_counts["prescriptions_removed"] = deleted_rxs

    # 2. Clinical Notes
    if demo_user_ids or demo_doctor_ids:
        deleted_notes = db.execute(
            delete(ClinicalNote).where(
                ClinicalNote.patient_user_id.in_(demo_user_ids)
                | ClinicalNote.doctor_id.in_(demo_doctor_ids)
                | ClinicalNote.history_of_present_illness.like(f"%{SEED_MARKER}%")
                | ClinicalNote.plan.like(f"%{SEED_MARKER}%")
            )
        ).rowcount
        cleaned_counts["clinical_notes_removed"] = deleted_notes

    # 3. Medical Reports
    if demo_user_ids:
        deleted_reports = db.execute(
            delete(MedicalReport).where(
                MedicalReport.patient_user_id.in_(demo_user_ids)
                | MedicalReport.report_id.like("REP-DEMO-%")
                | MedicalReport.disclaimer.like(f"%{SEED_MARKER}%")
            )
        ).rowcount
        cleaned_counts["medical_reports_removed"] = deleted_reports

    # 4. Medical Documents
    if demo_user_ids:
        demo_docs = db.scalars(
            select(MedicalDocument).where(
                MedicalDocument.patient_user_id.in_(demo_user_ids)
                | MedicalDocument.notes.like(f"%{SEED_MARKER}%")
            )
        ).all()
        for d in demo_docs:
            if d.file_path and os.path.exists(d.file_path) and ("sample_" in os.path.basename(d.file_path) or "DEMO_" in os.path.basename(d.file_path)):
                try:
                    os.remove(d.file_path)
                except OSError:
                    pass
        deleted_docs = db.execute(
            delete(MedicalDocument).where(
                MedicalDocument.patient_user_id.in_(demo_user_ids)
                | MedicalDocument.notes.like(f"%{SEED_MARKER}%")
            )
        ).rowcount
        cleaned_counts["medical_documents_removed"] = deleted_docs

    # 5. Patient Allergies
    if demo_user_ids:
        deleted_allergies = db.execute(
            delete(PatientAllergy).where(
                PatientAllergy.patient_user_id.in_(demo_user_ids)
                | PatientAllergy.reaction.like(f"%{SEED_MARKER}%")
            )
        ).rowcount
        cleaned_counts["allergies_removed"] = deleted_allergies

    # 6. Assistant Messages & Conversations
    demo_conversations = (
        db.scalars(
            select(AssistantConversation).where(
                (AssistantConversation.user_id.in_(demo_user_ids))
                | (AssistantConversation.conversation_id.like("conv-aarav-demo-%"))
                | (AssistantConversation.conversation_id.like("conv-diya-demo-%"))
                | (AssistantConversation.conversation_id.like(f"{SEED_MARKER}%"))
            )
        ).all()
        if demo_user_ids
        else []
    )
    demo_conv_ids = [c.id for c in demo_conversations]
    if demo_conv_ids:
        deleted_msgs = db.execute(
            delete(AssistantMessage).where(AssistantMessage.conversation_id.in_(demo_conv_ids))
        ).rowcount
        cleaned_counts["messages_removed"] = deleted_msgs
        deleted_convs = db.execute(
            delete(AssistantConversation).where(AssistantConversation.id.in_(demo_conv_ids))
        ).rowcount
        cleaned_counts["conversations_removed"] = deleted_convs

    # 7. Payments & Invoices
    demo_invoices = (
        db.scalars(
            select(Invoice).where(
                (Invoice.owner_user_id.in_(demo_user_ids))
                | (Invoice.invoice_number.like("INV-DEMO-%"))
            )
        ).all()
        if demo_user_ids
        else []
    )
    demo_inv_ids = [inv.id for inv in demo_invoices]
    if demo_inv_ids:
        deleted_payments = db.execute(
            delete(Payment).where(Payment.invoice_id.in_(demo_inv_ids))
        ).rowcount
        cleaned_counts["payments_removed"] = deleted_payments
        deleted_invoices = db.execute(
            delete(Invoice).where(Invoice.id.in_(demo_inv_ids))
        ).rowcount
        cleaned_counts["invoices_removed"] = deleted_invoices

    # 8. Appointments & Events
    demo_appointments = (
        db.scalars(
            select(Appointment).where(
                (Appointment.patient_user_id.in_(demo_user_ids))
                | (Appointment.doctor_id.in_(demo_doctor_ids))
            )
        ).all()
        if demo_user_ids
        else []
    )
    demo_appt_ids = [a.id for a in demo_appointments]
    if demo_appt_ids:
        deleted_locks = db.execute(
            delete(AppointmentSlotLock).where(
                AppointmentSlotLock.appointment_id.in_(demo_appt_ids)
                | AppointmentSlotLock.doctor_id.in_(demo_doctor_ids)
            )
        ).rowcount
        deleted_events = db.execute(
            delete(AppointmentEvent).where(AppointmentEvent.appointment_id.in_(demo_appt_ids))
        ).rowcount
        cleaned_counts["appointment_events_removed"] = deleted_events
        deleted_appts = db.execute(
            delete(Appointment).where(Appointment.id.in_(demo_appt_ids))
        ).rowcount
        cleaned_counts["appointments_removed"] = deleted_appts

    # 9. Doctor Schedules, Qualifications & Doctors
    if demo_doctor_ids:
        deleted_schedules = db.execute(
            delete(DoctorSchedule).where(DoctorSchedule.doctor_id.in_(demo_doctor_ids))
        ).rowcount
        cleaned_counts["doctor_schedules_removed"] = deleted_schedules
        deleted_quals = db.execute(
            delete(DoctorQualification).where(DoctorQualification.doctor_id.in_(demo_doctor_ids))
        ).rowcount
        cleaned_counts["doctor_qualifications_removed"] = deleted_quals
        deleted_docs = db.execute(
            delete(Doctor).where(Doctor.id.in_(demo_doctor_ids))
        ).rowcount
        cleaned_counts["doctors_removed"] = deleted_docs

    # 10. Patients
    if demo_user_ids:
        deleted_patients = db.execute(
            delete(Patient).where(Patient.owner_user_id.in_(demo_user_ids))
        ).rowcount
        cleaned_counts["patients_removed"] = deleted_patients

    # 11. Demo Users
    if demo_user_ids:
        deleted_users = db.execute(
            delete(User).where(User.id.in_(demo_user_ids))
        ).rowcount
        cleaned_counts["users_removed"] = deleted_users

    # 12. Demo Hospitals (only if no remaining doctors)
    demo_hospital_names = [
        "CareVoice Model Hospital - Indiranagar",
        "CareVoice Health Center - Koramangala",
    ]
    demo_hospitals = db.scalars(
        select(Hospital).where(Hospital.name.in_(demo_hospital_names))
    ).all()
    for hosp in demo_hospitals:
        remaining_doctors = db.scalar(
            select(Doctor).where(Doctor.hospital_id == hosp.id)
        )
        if not remaining_doctors:
            db.delete(hosp)
            cleaned_counts["hospitals_removed"] += 1

    db.flush()
    return cleaned_counts


def main(argv: list[str] | None = None) -> None:
    if settings.app_env.strip().lower() not in {"development", "test"}:
        raise SystemExit("Demo operations are disabled unless APP_ENV is development or test.")

    parser = argparse.ArgumentParser(description="CareVoice Demo Data Seeder and Cleaner")
    parser.add_argument(
        "--clean",
        "--remove",
        action="store_true",
        help="Safely remove all synthetic demo records without affecting real user data.",
    )
    args, _ = parser.parse_known_args(argv)

    with SessionLocal.begin() as db:
        if args.clean:
            counts = clean_demo_data(db)
            print(f"CareVoice synthetic demo data safely cleaned: {counts}")
        else:
            counts = seed_demo_data(db)
            print(f"CareVoice fictional demo data seeded: {counts}")


if __name__ == "__main__":
    main()

"""Idempotent development-only CareVoice demo-data seeder."""

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.security import hash_password
from app.core.config import settings
from app.core.database import SessionLocal
from app.models.billing import Invoice, Payment
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
                raise ValueError(f"Demo appointment marker conflicts with appointment {appointment.id}.")
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
                raise ValueError(f"Invoice already exists with inconsistent details for demo appointment {appointment.id}.")
        elif (
            invoice.appointment_id != appointment.id
            or invoice.owner_user_id != appointment.patient_user_id
            or invoice.amount_minor != doctor.fee_minor
        ):
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
    }


def main() -> None:
    if settings.app_env.strip().lower() not in {"development", "test"}:
        raise SystemExit("Demo seeding is disabled unless APP_ENV is development or test.")
    with SessionLocal.begin() as db:
        counts = seed_demo_data(db)
    print(f"CareVoice fictional demo data seeded: {counts}")


if __name__ == "__main__":
    main()

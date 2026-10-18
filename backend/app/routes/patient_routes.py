from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.controllers.patient_controller import patient_controller
from app.auth.security import get_current_user, require_roles
from app.core.database import get_db
from app.models.security import NotificationDelivery
from app.schemas.patient import (
    PatientCreate,
    PatientNotificationPage,
    PatientNotificationRead,
    PatientRead,
    PatientUpdate,
)
from app.models.user import User
from app.services.audit_service import record_audit

router = APIRouter(prefix="/patients", tags=["Patients"])
patient_user = require_roles("patient")

_EVENT_DETAILS = {
    "appointment.scheduled": {
        "title": "Appointment Scheduled",
        "title_hi": "अपॉइंटमेंट तय हुआ",
        "message": "Your healthcare appointment has been successfully scheduled.",
        "message_hi": "आपका स्वास्थ्य अपॉइंटमेंट सफलतापूर्वक तय हो गया है।",
    },
    "appointment.rescheduled": {
        "title": "Appointment Rescheduled",
        "title_hi": "अपॉइंटमेंट का समय बदला",
        "message": "Your appointment time has been updated.",
        "message_hi": "आपके अपॉइंटमेंट का समय बदल दिया गया है।",
    },
    "appointment.cancelled": {
        "title": "Appointment Cancelled",
        "title_hi": "अपॉइंटमेंट रद्द हुआ",
        "message": "Your appointment has been cancelled.",
        "message_hi": "आपका अपॉइंटमेंट रद्द कर दिया गया है।",
    },
    "billing.invoice.issued": {
        "title": "Invoice Issued",
        "title_hi": "चालान जारी हुआ",
        "message": "A new healthcare service invoice has been issued for your visit.",
        "message_hi": "आपकी मुलाक़ात के लिए एक नया सेवा चालान जारी किया गया है।",
    },
    "billing.payment.captured": {
        "title": "Payment Confirmed",
        "title_hi": "भुगतान की पुष्टि",
        "message": "Your payment has been received and verified.",
        "message_hi": "आपका भुगतान प्राप्त और सत्यापित हो गया है।",
    },
    "billing.refund.requested": {
        "title": "Refund Requested",
        "title_hi": "धनवापसी अनुरोध",
        "message": "A refund request has been submitted for review.",
        "message_hi": "समीक्षा के लिए धनवापसी का अनुरोध दर्ज किया गया है।",
    },
    "billing.refund.processed": {
        "title": "Refund Processed",
        "title_hi": "धनवापसी पूरी हुई",
        "message": "Your refund has been processed successfully.",
        "message_hi": "आपकी धनवापसी सफलतापूर्वक पूरी हो गई है।",
    },
    "account.updated": {
        "title": "Account Updated",
        "title_hi": "खाता अपडेट हुआ",
        "message": "Your account details or permissions have been updated.",
        "message_hi": "आपके खाते का विवरण या अनुमतियाँ अपडेट की गई हैं।",
    },
}


@router.get("/notifications", response_model=PatientNotificationPage)
def list_patient_notifications(
    request: Request,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = select(NotificationDelivery).where(NotificationDelivery.user_id == user.id)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    deliveries = db.scalars(
        query.order_by(NotificationDelivery.created_at.desc(), NotificationDelivery.id.desc())
        .offset(skip)
        .limit(limit)
    ).all()

    items = []
    for item in deliveries:
        meta = _EVENT_DETAILS.get(
            item.event_type,
            {
                "title": item.event_type.replace(".", " ").replace("_", " ").title(),
                "title_hi": item.event_type.replace(".", " ").replace("_", " ").title(),
                "message": f"Update regarding {item.event_type}.",
                "message_hi": f"{item.event_type} के संबंध में सूचना।",
            },
        )
        items.append(
            PatientNotificationRead(
                id=item.id,
                event_type=item.event_type,
                channel=item.channel,
                status=item.status,
                created_at=item.created_at,
                title=meta["title"],
                title_hi=meta["title_hi"],
                message=meta["message"],
                message_hi=meta["message_hi"],
            )
        )

    record_audit(db, request, "patient.notifications.list", actor=user, details={"count": len(items)})
    db.commit()
    return PatientNotificationPage(items=items, total=total, limit=limit, offset=skip)


@router.post("/", response_model=PatientRead, status_code=status.HTTP_201_CREATED)
def create_patient(payload: PatientCreate, request: Request, db: Session = Depends(get_db), user: User = Depends(patient_user)):
    patient = patient_controller.create(db, payload, user.id)
    record_audit(db, request, "patient.create", actor=user, resource_type="patient", resource_id=patient.id)
    db.commit()
    return patient

@router.get("/", response_model=list[PatientRead])
def list_patients(request: Request, skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100), db: Session = Depends(get_db), user: User = Depends(patient_user)):
    patients = patient_controller.list(db, skip, limit, user.id)
    record_audit(db, request, "patient.list", actor=user, details={"count": len(patients)})
    db.commit()
    return patients

@router.get("/{patient_id}", response_model=PatientRead)
def get_patient(patient_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(patient_user)):
    patient = patient_controller.get(db, patient_id, user.id)
    record_audit(db, request, "patient.read", actor=user, resource_type="patient", resource_id=patient_id)
    db.commit()
    return patient

@router.patch("/{patient_id}", response_model=PatientRead)
def update_patient(patient_id: int, payload: PatientUpdate, request: Request, db: Session = Depends(get_db), user: User = Depends(patient_user)):
    patient = patient_controller.update(db, patient_id, payload, user.id)
    record_audit(db, request, "patient.update", actor=user, resource_type="patient", resource_id=patient_id)
    db.commit()
    return patient

@router.delete("/{patient_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_patient(patient_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(patient_user)):
    patient_controller.delete(db, patient_id, user.id)
    record_audit(db, request, "patient.delete", actor=user, resource_type="patient", resource_id=patient_id)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

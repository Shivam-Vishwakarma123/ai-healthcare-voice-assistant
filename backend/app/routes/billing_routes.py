import hashlib
import hmac
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.security import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.models.billing import Invoice, Payment, PaymentWebhookEvent
from app.models.providers import Appointment, Doctor, Hospital
from app.models.user import User
from app.services.audit_service import record_audit
from app.services.notification_service import notify_user
from app.services.payment_service import PaymentProviderError, PaymentService, RazorpayPaymentService

router = APIRouter(prefix="/billing", tags=["Billing"])


def _payment_service() -> PaymentService:
    return RazorpayPaymentService(
        settings.razorpay_key_id,
        settings.razorpay_key_secret,
        settings.razorpay_api_base_url,
    )


class InvoiceCreate(BaseModel):
    patient_user_id: int = Field(gt=0)
    hospital_id: int | None = Field(default=None, gt=0)
    appointment_id: int | None = Field(default=None, gt=0)
    description: str = Field(min_length=2, max_length=240)
    amount_minor: int | None = Field(default=None, gt=0, le=100_000_000)

    @field_validator("description")
    @classmethod
    def strip_description(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise ValueError("Description must contain at least 2 non-space characters.")
        return value

    @model_validator(mode="after")
    def require_amount_for_service(self):
        if self.appointment_id is None and self.amount_minor is None:
            raise ValueError("A service invoice must specify an amount.")
        return self


class InvoiceRead(BaseModel):
    id: int
    invoice_number: str
    description: str
    amount_minor: int
    currency: str
    status: str
    appointment_id: int | None
    created_at: datetime
    paid_at: datetime | None

    model_config = {"from_attributes": True}


class CheckoutCreate(BaseModel):
    invoice_id: int = Field(gt=0)


class CheckoutOrder(BaseModel):
    order_id: str
    key_id: str | None = None
    amount_minor: int
    currency: str
    invoice_number: str
    description: str
    mode: str


class CheckoutVerify(BaseModel):
    invoice_id: int = Field(gt=0)
    razorpay_order_id: str = Field(min_length=1, max_length=80)
    razorpay_payment_id: str = Field(min_length=1, max_length=80)
    razorpay_signature: str = Field(min_length=1, max_length=256)


class DemoCheckoutComplete(BaseModel):
    order_id: str = Field(min_length=1, max_length=80)
    outcome: Literal["success", "failed", "cancelled"]


class DemoPaymentResult(BaseModel):
    invoice_id: int
    invoice_number: str
    invoice_status: str
    payment_id: int
    transaction_id: str
    payment_status: str
    amount_minor: int
    currency: str
    demo: Literal[True] = True


def _checkout_order(invoice: Invoice, payment: Payment) -> CheckoutOrder:
    return CheckoutOrder(
        order_id=payment.provider_order_id,
        key_id=settings.razorpay_key_id if settings.payment_mode == "live" else None,
        amount_minor=invoice.amount_minor,
        currency=invoice.currency,
        invoice_number=invoice.invoice_number,
        description=invoice.description,
        mode=settings.payment_mode,
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _require_staff(user: User) -> None:
    if user.role not in {"hospital_staff", "hospital_admin", "platform_admin"}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Clinic staff access is required.")


@router.get("/config")
def billing_config(_: User = Depends(get_current_user)):
    enabled = settings.payment_mode == "demo" or bool(settings.razorpay_key_id and settings.razorpay_key_secret)
    return {
        "payment_mode": settings.payment_mode,
        "online_payment_enabled": enabled,
        "demo_payment_enabled": settings.payment_mode == "demo",
    }


@router.get("/invoices", response_model=list[InvoiceRead])
def list_invoices(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    query = select(Invoice).order_by(Invoice.created_at.desc(), Invoice.id.desc())
    if user.role == "patient":
        query = query.where(Invoice.owner_user_id == user.id)
    elif user.role in {"hospital_staff", "hospital_admin"}:
        query = query.where(Invoice.hospital_id == user.hospital_id)
    elif user.role != "platform_admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Your account cannot access invoices.")
    invoices = list(db.scalars(query).all())
    record_audit(db, request, "billing.invoice_list", actor=user, details={"count": len(invoices)})
    db.commit()
    return invoices


@router.get("/payments")
def list_payments(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    query = select(Payment, Invoice).join(Invoice, Invoice.id == Payment.invoice_id)
    if user.role == "patient":
        query = query.where(Invoice.owner_user_id == user.id)
    elif user.role in {"hospital_staff", "hospital_admin"}:
        query = query.where(Invoice.hospital_id == user.hospital_id)
    elif user.role != "platform_admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Your account cannot access payment history.")
    return [
        {
            "id": payment.id,
            "invoice_id": invoice.id,
            "invoice_number": invoice.invoice_number,
            "transaction_id": payment.provider_payment_id or payment.provider_order_id,
            "status": payment.status,
            "amount_minor": invoice.amount_minor,
            "currency": invoice.currency,
            "is_demo": payment.provider_order_id.startswith("demo_"),
            "created_at": payment.created_at,
            "updated_at": payment.updated_at,
        }
        for payment, invoice in db.execute(query.order_by(Payment.created_at.desc(), Payment.id.desc())).all()
    ]


@router.get("/billable-appointments")
def list_billable_appointments(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _require_staff(user)
    query = (
        select(Appointment, Doctor)
        .join(Doctor, Doctor.id == Appointment.doctor_id)
        .outerjoin(Invoice, Invoice.appointment_id == Appointment.id)
        .where(Invoice.id.is_(None), Appointment.status != "cancelled")
        .order_by(Appointment.scheduled_for.desc(), Appointment.id.desc())
        .limit(100)
    )
    if user.role in {"hospital_staff", "hospital_admin"}:
        query = query.where(Appointment.hospital_id == user.hospital_id)
    return [
        {
            "appointment_id": appointment.id,
            "patient_user_id": appointment.patient_user_id,
            "hospital_id": appointment.hospital_id,
            "doctor_id": doctor.id,
            "doctor_name": doctor.full_name,
            "scheduled_for": appointment.scheduled_for,
            "fee_minor": doctor.fee_minor,
        }
        for appointment, doctor in db.execute(query).all()
    ]


@router.post("/invoices", response_model=InvoiceRead, status_code=status.HTTP_201_CREATED)
def create_invoice(payload: InvoiceCreate, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _require_staff(user)
    patient = db.get(User, payload.patient_user_id)
    if patient is None or not patient.is_active or patient.role != "patient":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Patient account not found.")
    hospital_id = user.hospital_id if user.role != "platform_admin" else payload.hospital_id
    appointment = db.get(Appointment, payload.appointment_id) if payload.appointment_id is not None else None
    amount_minor = payload.amount_minor
    if payload.appointment_id is not None:
        if (
            appointment is None
            or appointment.patient_user_id != patient.id
            or appointment.status == "cancelled"
            or (user.role in {"hospital_staff", "hospital_admin"} and appointment.hospital_id != user.hospital_id)
            or (payload.hospital_id is not None and appointment.hospital_id != payload.hospital_id)
        ):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Eligible appointment not found.")
        doctor = db.get(Doctor, appointment.doctor_id)
        if doctor is None or doctor.fee_minor <= 0:
            raise HTTPException(status.HTTP_409_CONFLICT, "The clinician has no billable consultation fee.")
        if amount_minor is not None and amount_minor != doctor.fee_minor:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invoice amount must match the clinician's recorded fee.")
        amount_minor = doctor.fee_minor
        hospital_id = appointment.hospital_id
    if user.role in {"hospital_staff", "hospital_admin"}:
        if payload.hospital_id is not None and payload.hospital_id != user.hospital_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only create invoices for your hospital.")
        linked_appointment = db.scalar(
            select(Appointment.id).where(
                Appointment.patient_user_id == patient.id,
                Appointment.hospital_id == user.hospital_id,
            ).limit(1)
        )
        if linked_appointment is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Patient has no care relationship with this hospital.")
    elif hospital_id is not None and db.get(Hospital, hospital_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Hospital not found.")
    invoice = Invoice(
        owner_user_id=payload.patient_user_id,
        hospital_id=hospital_id,
        appointment_id=appointment.id if appointment is not None else None,
        invoice_number=f"CV-{datetime.now(timezone.utc):%Y%m%d}-{uuid.uuid4().hex[:8].upper()}",
        description=payload.description.strip(),
        amount_minor=amount_minor,
        currency="INR",
        status="unpaid",
    )
    db.add(invoice)
    try:
        db.flush()
        record_audit(db, request, "billing.invoice_create", actor=user, hospital_id=hospital_id, resource_type="invoice", resource_id=invoice.id)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "This appointment already has an invoice.") from exc
    db.refresh(invoice)
    notify_user(
        db,
        patient,
        "billing.invoice.created",
        hospital_id=invoice.hospital_id,
    )
    return invoice


@router.post("/checkout", response_model=CheckoutOrder)
async def create_checkout(payload: CheckoutCreate, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if user.role != "patient":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the invoice owner can start checkout.")
    invoice = db.scalar(
        select(Invoice)
        .where(Invoice.id == payload.invoice_id, Invoice.owner_user_id == user.id)
        .with_for_update()
    )
    if invoice is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found.")
    if invoice.status != "unpaid":
        raise HTTPException(status.HTTP_409_CONFLICT, "This invoice is already paid.")
    if settings.payment_mode != "demo" and (not settings.razorpay_key_id or not settings.razorpay_key_secret):
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Online payments are not configured. Set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET in .env.",
        )
    existing_order = db.scalar(
        select(Payment)
        .where(Payment.invoice_id == invoice.id, Payment.status == "created")
        .order_by(Payment.created_at.desc(), Payment.id.desc())
        .limit(1)
    )
    if existing_order is not None:
        existing_is_demo = existing_order.provider_order_id.startswith("demo_")
        if settings.payment_mode == "demo" and existing_is_demo:
            if datetime.now(timezone.utc) - _as_utc(existing_order.created_at) <= timedelta(minutes=15):
                return _checkout_order(invoice, existing_order)
            existing_order.status = "expired"
        elif settings.payment_mode == "live" and not existing_is_demo:
            return _checkout_order(invoice, existing_order)
        else:
            existing_order.status = "cancelled"

    if settings.payment_mode == "demo":
        payment = Payment(
            invoice_id=invoice.id,
            provider_order_id=f"demo_{uuid.uuid4().hex}",
            status="created",
        )
        db.add(payment)
        db.flush()
        record_audit(
            db,
            request,
            "billing.demo_checkout_create",
            actor=user,
            hospital_id=invoice.hospital_id,
            resource_type="invoice",
            resource_id=invoice.id,
        )
        db.commit()
        db.refresh(payment)
        return _checkout_order(invoice, payment)

    try:
        order_id = await _payment_service().create_order(
            invoice_id=invoice.id,
            invoice_number=invoice.invoice_number,
            amount_minor=invoice.amount_minor,
            currency=invoice.currency,
        )
    except PaymentProviderError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc

    payment = Payment(invoice_id=invoice.id, provider_order_id=order_id, status="created")
    db.add(payment)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        existing_order = db.scalar(
            select(Payment)
            .where(Payment.invoice_id == invoice.id, Payment.status == "created")
            .order_by(Payment.created_at.desc(), Payment.id.desc())
            .limit(1)
        )
        if existing_order is not None:
            return _checkout_order(invoice, existing_order)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "The checkout order could not be saved safely.") from exc
    record_audit(db, request, "billing.checkout_create", actor=user, hospital_id=invoice.hospital_id, resource_type="invoice", resource_id=invoice.id)
    db.commit()
    return _checkout_order(invoice, payment)


@router.post("/demo/complete", response_model=DemoPaymentResult)
def complete_demo_checkout(
    payload: DemoCheckoutComplete,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if settings.payment_mode != "demo":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Demo checkout is not enabled.")
    if user.role != "patient":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the invoice owner can complete checkout.")
    attempt = db.scalar(select(Payment).where(Payment.provider_order_id == payload.order_id))
    if attempt is None or not attempt.provider_order_id.startswith("demo_"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Demo checkout attempt not found.")
    invoice = db.scalar(
        select(Invoice)
        .where(Invoice.id == attempt.invoice_id, Invoice.owner_user_id == user.id)
        .with_for_update()
    )
    payment = db.scalar(select(Payment).where(Payment.id == attempt.id).with_for_update())
    if invoice is None or payment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Demo checkout attempt not found.")

    settled_status = {"success": "paid", "failed": "failed", "cancelled": "cancelled"}[payload.outcome]
    if payment.status in {"paid", "failed", "cancelled"}:
        if payment.status != settled_status:
            raise HTTPException(status.HTTP_409_CONFLICT, "This demo attempt was already completed with a different result.")
        return DemoPaymentResult(
            invoice_id=invoice.id,
            invoice_number=invoice.invoice_number,
            invoice_status=invoice.status,
            payment_id=payment.id,
            transaction_id=payment.provider_payment_id or payment.provider_order_id,
            payment_status=payment.status,
            amount_minor=invoice.amount_minor,
            currency=invoice.currency,
        )
    if payment.status != "created":
        raise HTTPException(status.HTTP_409_CONFLICT, "This demo checkout attempt is no longer pending.")
    if datetime.now(timezone.utc) - _as_utc(payment.created_at) > timedelta(minutes=15):
        payment.status = "expired"
        record_audit(
            db,
            request,
            "billing.demo_payment_expired",
            actor=user,
            hospital_id=invoice.hospital_id,
            resource_type="payment",
            resource_id=payment.id,
        )
        db.commit()
        raise HTTPException(status.HTTP_410_GONE, "This demo checkout attempt has expired. Start a new checkout.")
    if invoice.status != "unpaid":
        raise HTTPException(status.HTTP_409_CONFLICT, "This invoice has already been settled.")

    payment.status = settled_status
    payment.provider_payment_id = f"demo_tx_{uuid.uuid4().hex}"
    if payload.outcome == "failed":
        payment.failure_code = "demo_failure"
        payment.failure_description = "The user selected the simulated failure outcome."
    else:
        payment.failure_code = None
        payment.failure_description = None
    if payload.outcome == "success":
        invoice.status = "paid"
        invoice.paid_at = datetime.now(timezone.utc)
    record_audit(
        db,
        request,
        f"billing.demo_payment_{payload.outcome}",
        actor=user,
        hospital_id=invoice.hospital_id,
        resource_type="payment",
        resource_id=payment.id,
        details={"demo": True, "invoice_id": invoice.id},
    )
    db.commit()
    db.refresh(payment)
    db.refresh(invoice)
    if payload.outcome == "success":
        notify_user(db, user, "billing.payment.captured", hospital_id=invoice.hospital_id)
    return DemoPaymentResult(
        invoice_id=invoice.id,
        invoice_number=invoice.invoice_number,
        invoice_status=invoice.status,
        payment_id=payment.id,
        transaction_id=payment.provider_payment_id,
        payment_status=payment.status,
        amount_minor=invoice.amount_minor,
        currency=invoice.currency,
    )


@router.post("/verify", response_model=InvoiceRead)
async def verify_checkout(payload: CheckoutVerify, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if user.role != "patient":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the invoice owner can verify checkout.")
    invoice = db.scalar(
        select(Invoice)
        .where(Invoice.id == payload.invoice_id, Invoice.owner_user_id == user.id)
        .with_for_update()
    )
    payment = db.scalar(
        select(Payment)
        .where(Payment.invoice_id == payload.invoice_id, Payment.provider_order_id == payload.razorpay_order_id)
        .with_for_update()
    )
    if invoice is None or payment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Checkout order not found.")
    if payment.provider_order_id.startswith("demo_"):
        raise HTTPException(status.HTTP_409_CONFLICT, "Demo attempts must use the demo completion endpoint.")
    if payment.status == "paid":
        if payment.provider_payment_id == payload.razorpay_payment_id:
            return invoice
        raise HTTPException(status.HTTP_409_CONFLICT, "This order was already verified with another payment.")
    if not settings.razorpay_key_id or not settings.razorpay_key_secret:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Razorpay verification is not configured.")
    expected = hmac.new(
        settings.razorpay_key_secret.encode(),
        f"{payload.razorpay_order_id}|{payload.razorpay_payment_id}".encode(),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected, payload.razorpay_signature):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Payment signature is invalid.")

    try:
        captured_payment = await _payment_service().fetch_payment(payload.razorpay_payment_id)
    except PaymentProviderError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    if (
        captured_payment.get("order_id") != payload.razorpay_order_id
        or type(captured_payment.get("amount")) is not int
        or captured_payment.get("amount") != invoice.amount_minor
        or captured_payment.get("currency") != invoice.currency
    ):
        raise HTTPException(status.HTTP_409_CONFLICT, "Payment details do not match this invoice.")
    if captured_payment.get("status") != "captured":
        raise HTTPException(status.HTTP_409_CONFLICT, "Payment has not been captured yet.")
    if invoice.status == "paid":
        raise HTTPException(status.HTTP_409_CONFLICT, "This invoice has already been paid by another checkout.")
    payment.status = "paid"
    payment.provider_payment_id = payload.razorpay_payment_id
    payment.failure_code = None
    payment.failure_description = None
    invoice.status = "paid"
    invoice.paid_at = datetime.now(timezone.utc)
    record_audit(db, request, "billing.payment_verified", actor=user, hospital_id=invoice.hospital_id, resource_type="invoice", resource_id=invoice.id)
    db.commit()
    db.refresh(invoice)
    notify_user(
        db,
        user,
        "billing.payment.captured",
        hospital_id=invoice.hospital_id,
    )
    return invoice


@router.post("/webhooks/razorpay", status_code=status.HTTP_204_NO_CONTENT)
async def razorpay_webhook(
    request: Request,
    db: Session = Depends(get_db),
    signature: str | None = Header(default=None, alias="X-Razorpay-Signature"),
    event_id: str | None = Header(default=None, alias="X-Razorpay-Event-Id"),
):
    if settings.payment_mode != "live":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Razorpay webhooks are disabled in demo mode.")
    if not settings.razorpay_webhook_secret:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Razorpay webhook verification is not configured.")
    body = await request.body()
    if len(body) > 1_000_000:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Webhook payload is too large.")
    expected = hmac.new(settings.razorpay_webhook_secret.encode(), body, hashlib.sha256).hexdigest()
    if not signature or not hmac.compare_digest(expected, signature):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Webhook signature is invalid.")
    if not event_id or len(event_id) > 100:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A valid Razorpay event ID is required.")

    payload_hash = hashlib.sha256(body).hexdigest()
    try:
        event = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid Razorpay webhook payload.") from exc
    if not isinstance(event, dict) or not isinstance(event.get("event"), str):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid Razorpay webhook payload.")

    existing_event = db.scalar(
        select(PaymentWebhookEvent).where(PaymentWebhookEvent.provider_event_id == event_id)
    )
    if existing_event is not None:
        if not hmac.compare_digest(existing_event.payload_sha256, payload_hash):
            raise HTTPException(status.HTTP_409_CONFLICT, "Razorpay event ID was reused with a different payload.")
        return None

    event_type = event["event"]
    payment = None
    invoice = None
    result = "ignored"
    if event_type in {"payment.captured", "payment.failed"}:
        try:
            payment_data = event["payload"]["payment"]["entity"]
            order_id = payment_data["order_id"]
            payment_id = payment_data["id"]
            amount_minor = payment_data["amount"]
            currency = payment_data["currency"]
        except (KeyError, TypeError) as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid Razorpay payment event payload.") from exc
        if (
            not isinstance(order_id, str)
            or not order_id
            or not isinstance(payment_id, str)
            or not payment_id
            or len(payment_id) > 80
            or type(amount_minor) is not int
            or not isinstance(currency, str)
        ):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid Razorpay payment event fields.")

        payment = db.scalar(
            select(Payment).where(Payment.provider_order_id == order_id).with_for_update()
        )
        if payment is None:
            result = "unmatched"
        else:
            invoice = db.scalar(select(Invoice).where(Invoice.id == payment.invoice_id).with_for_update())
            if invoice is None:
                payment = None
                result = "unmatched"
            elif amount_minor != invoice.amount_minor or currency != invoice.currency:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "Payment event does not match its invoice amount and currency.")
            elif event_type == "payment.failed":
                if payment.status != "paid":
                    payment.status = "failed"
                    payment.provider_payment_id = payment_id
                    payment.failure_code = str(payment_data.get("error_code") or "")[:80] or None
                    payment.failure_description = str(payment_data.get("error_description") or "")[:2000] or None
                    result = "failed"
                else:
                    result = "already_paid"
            elif payment.status == "paid":
                if payment.provider_payment_id != payment_id:
                    raise HTTPException(status.HTTP_409_CONFLICT, "Order was already captured with another payment.")
                result = "already_applied"
            else:
                payment.status = "paid"
                payment.provider_payment_id = payment_id
                payment.failure_code = None
                payment.failure_description = None
                if invoice.status != "paid":
                    invoice.status = "paid"
                    invoice.paid_at = datetime.now(timezone.utc)
                    result = "captured"
                    record_audit(
                        db,
                        request,
                        "billing.webhook_payment_captured",
                        hospital_id=invoice.hospital_id,
                        resource_type="invoice",
                        resource_id=invoice.id,
                    )
                else:
                    result = "review"
                    record_audit(
                        db,
                        request,
                        "billing.webhook_duplicate_invoice_capture",
                        hospital_id=invoice.hospital_id,
                        resource_type="invoice",
                        resource_id=invoice.id,
                    )

    db.add(
        PaymentWebhookEvent(
            provider_event_id=event_id,
            event_type=event_type[:80],
            payload_sha256=payload_hash,
            payment_id=payment.id if payment else None,
            result=result,
        )
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        duplicate = db.scalar(
            select(PaymentWebhookEvent).where(PaymentWebhookEvent.provider_event_id == event_id)
        )
        if duplicate is not None and hmac.compare_digest(duplicate.payload_sha256, payload_hash):
            return None
        raise HTTPException(status.HTTP_409_CONFLICT, "Razorpay webhook could not be applied safely.") from exc
    if result == "captured" and invoice is not None:
        invoice_owner = db.get(User, invoice.owner_user_id)
        if invoice_owner is not None:
            notify_user(
                db,
                invoice_owner,
                "billing.payment.captured",
                hospital_id=invoice.hospital_id,
            )
    return None

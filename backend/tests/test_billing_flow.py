import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app
from app.models.providers import Appointment, Doctor, Hospital
from app.models.billing import Invoice, Payment, PaymentWebhookEvent, Refund
from app.models.user import User
from app.services import payment_service
from tests.auth_utils import make_session_token


def test_staff_invoice_owner_checkout_and_captured_payment(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    test_sessions = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)

    def override_database():
        with test_sessions() as db:
            yield db

    with test_sessions() as db:
        patient = User(full_name="Patient One", email="billing-owner@example.com", password_hash="unused", role="patient")
        other_patient = User(full_name="Patient Two", email="billing-other@example.com", password_hash="unused", role="patient")
        staff = User(full_name="Clinic Staff", email="billing-staff@example.com", password_hash="unused", role="hospital_staff")
        hospital_admin = User(full_name="Clinic Admin", email="billing-admin@example.com", password_hash="unused", role="hospital_admin")
        other_hospital_admin = User(
            full_name="Other Hospital Admin",
            email="billing-other-admin@example.com",
            password_hash="unused",
            role="hospital_admin",
        )
        hospital = Hospital(name="Billing Hospital", city="Raipur", state="CG")
        other_hospital = Hospital(name="Other Hospital", city="Pune", state="MH")
        db.add_all([patient, other_patient, staff, hospital_admin, other_hospital_admin, hospital, other_hospital])
        db.commit()
        staff.hospital_id = hospital.id
        hospital_admin.hospital_id = hospital.id
        other_hospital_admin.hospital_id = other_hospital.id
        doctor = Doctor(hospital_id=hospital.id, full_name="Dr. One", specialty="General Medicine")
        db.add(doctor)
        db.commit()
        db.add(
            Appointment(
                patient_user_id=patient.id,
                doctor_id=doctor.id,
                hospital_id=hospital.id,
                scheduled_for=datetime.now(timezone.utc) + timedelta(days=1),
            )
        )
        db.commit()
        patient_id = patient.id
        patient_token = make_session_token(db, patient)
        other_token = make_session_token(db, other_patient)
        staff_token = make_session_token(db, staff)
        hospital_admin_token = make_session_token(db, hospital_admin)
        other_hospital_token = make_session_token(db, other_hospital_admin)

    # This test exercises the provider-backed flow; Docker's development environment
    # may set PAYMENT_MODE=demo, so make the intended mode explicit.
    monkeypatch.setattr(settings, "payment_mode", "live")
    monkeypatch.setattr(settings, "razorpay_key_id", "rzp_test_key")
    monkeypatch.setattr(settings, "razorpay_key_secret", "test-secret")
    monkeypatch.setattr(settings, "razorpay_webhook_secret", "webhook-secret")
    monkeypatch.setattr(settings, "razorpay_api_base_url", "https://razorpay.test/v1")
    invoice_amount = 12500
    created_orders = {}
    provider_behavior = {"fail_order": False, "fail_payment_lookup": False, "wrong_amount": False}

    def provider_response(request):
        if request.method == "POST" and request.url.path == "/v1/orders":
            if provider_behavior["fail_order"]:
                return httpx.Response(503, json={"error": "provider unavailable"})
            order = json.loads(request.content)
            assert order["amount"] == invoice_amount
            order_id = f"order_test_{order['notes']['invoice_id']}"
            created_orders[order_id] = invoice_amount
            return httpx.Response(200, json={"id": order_id, "amount": invoice_amount, "currency": "INR"})
        if request.method == "GET" and request.url.path.startswith("/v1/payments/"):
            if provider_behavior["fail_payment_lookup"]:
                return httpx.Response(503, json={"error": "provider unavailable"})
            payment_id = request.url.path.rsplit("/", 1)[-1]
            return httpx.Response(
                200,
                json={
                    "id": payment_id,
                    "order_id": f"order_test_{payment_id.rsplit('_', 1)[-1]}",
                    "amount": invoice_amount - 1 if provider_behavior["wrong_amount"] else invoice_amount,
                    "currency": "INR",
                    "status": "captured",
                },
            )
        if request.method == "POST" and request.url.path == "/v1/payments/pay_test_1/refund":
            refund = json.loads(request.content)
            return httpx.Response(200, json={
                "id": "rfnd_test_1", "payment_id": "pay_test_1", "amount": refund["amount"], "status": "pending"
            })
        return httpx.Response(404, json={"error": "not found"})

    original_async_client = httpx.AsyncClient
    transport = httpx.MockTransport(provider_response)
    monkeypatch.setattr(
        payment_service.httpx,
        "AsyncClient",
        lambda **kwargs: original_async_client(transport=transport, **kwargs),
    )
    app.dependency_overrides[get_db] = override_database
    try:
        with TestClient(app) as client:
            billing_config = client.get(
                "/api/v1/billing/config",
                headers={"Authorization": f"Bearer {patient_token}"},
            )
            assert billing_config.status_code == 200
            assert billing_config.json() == {
                "payment_mode": "live",
                "online_payment_enabled": True,
                "provider_checkout_enabled": True,
                "provider_test_mode": True,
                "demo_payment_enabled": False,
                "checkout_enabled": True,
            }

            denied = client.post(
                "/api/v1/billing/invoices",
                headers={"Authorization": f"Bearer {patient_token}"},
                json={"patient_user_id": patient_id, "description": "Consultation", "amount_minor": invoice_amount},
            )
            assert denied.status_code == 403

            issued = client.post(
                "/api/v1/billing/invoices",
                headers={"Authorization": f"Bearer {staff_token}"},
                json={"patient_user_id": patient_id, "description": "Consultation", "amount_minor": invoice_amount},
            )
            assert issued.status_code == 201
            invoice_id = issued.json()["id"]

            hospital_invoices = client.get(
                "/api/v1/billing/invoices",
                headers={"Authorization": f"Bearer {staff_token}"},
            )
            other_hospital_invoices = client.get(
                "/api/v1/billing/invoices",
                headers={"Authorization": f"Bearer {other_hospital_token}"},
            )
            assert len(hospital_invoices.json()) == 1
            assert other_hospital_invoices.json() == []

            other_invoices = client.get(
                "/api/v1/billing/invoices",
                headers={"Authorization": f"Bearer {other_token}"},
            )
            assert other_invoices.status_code == 200
            assert other_invoices.json() == []

            order = client.post(
                "/api/v1/billing/checkout",
                headers={"Authorization": f"Bearer {patient_token}"},
                json={"invoice_id": invoice_id},
            )
            assert order.status_code == 200
            assert order.json()["amount_minor"] == invoice_amount
            replayed_order = client.post(
                "/api/v1/billing/checkout",
                headers={"Authorization": f"Bearer {patient_token}"},
                json={"invoice_id": invoice_id},
            )
            assert replayed_order.status_code == 200
            assert replayed_order.json()["order_id"] == order.json()["order_id"]
            assert len(created_orders) == 1

            signature = hmac.new(
                b"test-secret",
                f"{order.json()['order_id']}|pay_test_1".encode(),
                hashlib.sha256,
            ).hexdigest()
            invalid_verify_signature = client.post(
                "/api/v1/billing/verify",
                headers={"Authorization": f"Bearer {patient_token}"},
                json={
                    "invoice_id": invoice_id,
                    "razorpay_order_id": order.json()["order_id"],
                    "razorpay_payment_id": "pay_test_1",
                    "razorpay_signature": "invalid",
                },
            )
            assert invalid_verify_signature.status_code == 400

            provider_behavior["wrong_amount"] = True
            mismatch_verify_signature = client.post(
                "/api/v1/billing/verify",
                headers={"Authorization": f"Bearer {patient_token}"},
                json={
                    "invoice_id": invoice_id,
                    "razorpay_order_id": order.json()["order_id"],
                    "razorpay_payment_id": "pay_test_1",
                    "razorpay_signature": signature,
                },
            )
            assert mismatch_verify_signature.status_code == 409
            provider_behavior["wrong_amount"] = False

            provider_behavior["fail_payment_lookup"] = True
            failed_lookup = client.post(
                "/api/v1/billing/verify",
                headers={"Authorization": f"Bearer {patient_token}"},
                json={
                    "invoice_id": invoice_id,
                    "razorpay_order_id": order.json()["order_id"],
                    "razorpay_payment_id": "pay_test_1",
                    "razorpay_signature": signature,
                },
            )
            assert failed_lookup.status_code == 502
            provider_behavior["fail_payment_lookup"] = False

            verified = client.post(
                "/api/v1/billing/verify",
                headers={"Authorization": f"Bearer {patient_token}"},
                json={
                    "invoice_id": invoice_id,
                    "razorpay_order_id": order.json()["order_id"],
                    "razorpay_payment_id": "pay_test_1",
                    "razorpay_signature": signature,
                },
            )
            assert verified.status_code == 200
            assert verified.json()["status"] == "paid"
            assert verified.json()["paid_at"] is not None
            patient_payments = client.get(
                "/api/v1/billing/payments",
                headers={"Authorization": f"Bearer {patient_token}"},
            )
            assert patient_payments.status_code == 200
            assert patient_payments.json()[0]["paid_at"] is not None
            assert patient_payments.json()[0]["appointment_id"] is None

            def post_webhook(event_id, event, *, valid_signature=True):
                body = json.dumps(event, separators=(",", ":")).encode()
                webhook_signature = hmac.new(b"webhook-secret", body, hashlib.sha256).hexdigest()
                if not valid_signature:
                    webhook_signature = "invalid"
                return client.post(
                    "/api/v1/billing/webhooks/razorpay",
                    headers={
                        "X-Razorpay-Signature": webhook_signature,
                        "X-Razorpay-Event-Id": event_id,
                        "Content-Type": "application/json",
                    },
                    content=body,
                ), body

            denied_refund = client.post(
                "/api/v1/billing/refunds",
                headers={"Authorization": f"Bearer {staff_token}", "Idempotency-Key": "refund-denied-key-0001"},
                json={"payment_id": 1, "amount_minor": invoice_amount, "reason": "Approved cancellation"},
            )
            assert denied_refund.status_code == 403
            refund_headers = {"Authorization": f"Bearer {hospital_admin_token}", "Idempotency-Key": "refund-approved-key-0001"}
            refund_request = {"payment_id": 1, "amount_minor": invoice_amount, "reason": "Approved cancellation"}
            refund = client.post("/api/v1/billing/refunds", headers=refund_headers, json=refund_request)
            assert refund.status_code == 202
            assert refund.json()["status"] == "pending"
            replayed_refund = client.post("/api/v1/billing/refunds", headers=refund_headers, json=refund_request)
            assert replayed_refund.status_code == 202
            assert replayed_refund.json()["id"] == refund.json()["id"]
            refund_event = {
                "event": "refund.processed",
                "payload": {"refund": {"entity": {
                    "id": "rfnd_test_1", "payment_id": "pay_test_1", "amount": invoice_amount, "status": "processed"
                }}},
            }
            processed, _ = post_webhook("evt_refund_processed_1", refund_event)
            assert processed.status_code == 204
            with test_sessions() as db:
                payment = db.scalar(select(Payment).where(Payment.provider_payment_id == "pay_test_1"))
                refund_record = db.scalar(select(Refund).where(Refund.provider_refund_id == "rfnd_test_1"))
                refunded_invoice = db.get(Invoice, invoice_id)
                assert payment.status == "refunded"
                assert refunded_invoice.status == "refunded"
                assert refund_record.status == "processed"

            mismatch_event = {
                "event": "payment.captured",
                "payload": {"payment": {"entity": {
                    "id": "pay_mismatch",
                    "order_id": order.json()["order_id"],
                    "amount": invoice_amount + 1,
                    "currency": "INR",
                }}},
            }
            mismatch, _ = post_webhook("evt_amount_mismatch", mismatch_event)
            assert mismatch.status_code == 400

            invalid_signature, _ = post_webhook("evt_bad_signature", mismatch_event, valid_signature=False)
            assert invalid_signature.status_code == 400

            valid_capture_event = {
                "event": "payment.captured",
                "payload": {"payment": {"entity": {
                    "id": "pay_test_1",
                    "order_id": order.json()["order_id"],
                    "amount": invoice_amount,
                    "currency": "INR",
                }}},
            }
            captured, _ = post_webhook("evt_capture_duplicate", valid_capture_event)
            assert captured.status_code == 204
            duplicate_capture, _ = post_webhook("evt_capture_duplicate", valid_capture_event)
            assert duplicate_capture.status_code == 204
            changed_payload = {**valid_capture_event, "event": "payment.failed"}
            reused_id, _ = post_webhook("evt_capture_duplicate", changed_payload)
            assert reused_id.status_code == 409

            second_invoice = client.post(
                "/api/v1/billing/invoices",
                headers={"Authorization": f"Bearer {staff_token}"},
                json={"patient_user_id": patient_id, "description": "Follow-up", "amount_minor": invoice_amount},
            )
            assert second_invoice.status_code == 201
            second_invoice_id = second_invoice.json()["id"]
            provider_behavior["fail_order"] = True
            failed_order = client.post(
                "/api/v1/billing/checkout",
                headers={"Authorization": f"Bearer {patient_token}"},
                json={"invoice_id": second_invoice_id},
            )
            assert failed_order.status_code == 502
            with test_sessions() as db:
                assert db.scalar(
                    select(func.count()).select_from(Payment).where(Payment.invoice_id == second_invoice_id)
                ) == 0
            provider_behavior["fail_order"] = False
            second_order = client.post(
                "/api/v1/billing/checkout",
                headers={"Authorization": f"Bearer {patient_token}"},
                json={"invoice_id": second_invoice_id},
            )
            assert second_order.status_code == 200
            failed_event = {
                "event": "payment.failed",
                "payload": {"payment": {"entity": {
                    "id": "pay_failed_1",
                    "order_id": second_order.json()["order_id"],
                    "amount": invoice_amount,
                    "currency": "INR",
                    "error_code": "BAD_REQUEST_ERROR",
                    "error_description": "Payment was declined",
                }}},
            }
            failed, _ = post_webhook("evt_payment_failed", failed_event)
            assert failed.status_code == 204
            failed_duplicate, _ = post_webhook("evt_payment_failed", failed_event)
            assert failed_duplicate.status_code == 204

            with test_sessions() as db:
                payment = db.scalar(select(Payment).where(Payment.provider_order_id == second_order.json()["order_id"]))
                invoice = db.get(Invoice, second_invoice_id)
                assert payment.status == "failed"
                assert payment.failure_code == "BAD_REQUEST_ERROR"
                assert payment.failure_description == "Payment was declined"
                assert invoice.status == "unpaid"
                assert db.scalar(
                    select(func.count()).select_from(PaymentWebhookEvent).where(
                        PaymentWebhookEvent.provider_event_id == "evt_payment_failed"
                    )
                ) == 1
                assert db.scalar(
                    select(func.count()).select_from(PaymentWebhookEvent).where(
                        PaymentWebhookEvent.provider_event_id == "evt_capture_duplicate"
                    )
                ) == 1
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_patient_can_request_one_server_priced_invoice_for_own_upcoming_appointment():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    test_sessions = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)

    def override_database():
        with test_sessions() as db:
            yield db

    with test_sessions() as db:
        patient = User(full_name="Invoice Patient", email="invoice-patient@example.com", password_hash="unused", role="patient")
        other_patient = User(full_name="Other Patient", email="other-invoice-patient@example.com", password_hash="unused", role="patient")
        hospital = Hospital(name="Fee Hospital", city="Raipur", state="CG")
        db.add_all([patient, other_patient, hospital])
        db.flush()
        doctor = Doctor(hospital_id=hospital.id, full_name="Dr. Fee", specialty="General Medicine", fee_minor=55000)
        db.add(doctor)
        db.flush()
        appointment = Appointment(
            patient_user_id=patient.id,
            doctor_id=doctor.id,
            hospital_id=hospital.id,
            scheduled_for=datetime.now(timezone.utc) + timedelta(days=2),
            status="confirmed",
        )
        db.add(appointment)
        stale_appointment = Appointment(
            patient_user_id=patient.id,
            doctor_id=doctor.id,
            hospital_id=hospital.id,
            scheduled_for=datetime.now(timezone.utc) - timedelta(hours=1),
            status="scheduled",
        )
        cancelled_appointment = Appointment(
            patient_user_id=patient.id,
            doctor_id=doctor.id,
            hospital_id=hospital.id,
            scheduled_for=datetime.now(timezone.utc) + timedelta(days=3),
            status="cancelled",
        )
        db.add_all([stale_appointment, cancelled_appointment])
        db.commit()
        appointment_id = appointment.id
        stale_appointment_id = stale_appointment.id
        cancelled_appointment_id = cancelled_appointment.id
        patient_token = make_session_token(db, patient)
        other_token = make_session_token(db, other_patient)

    app.dependency_overrides[get_db] = override_database
    try:
        with TestClient(app) as client:
            path = f"/api/v1/billing/appointments/{appointment_id}/invoice"
            headers = {"Authorization": f"Bearer {patient_token}"}
            first = client.post(path, headers=headers)
            replay = client.post(path, headers=headers)
            denied = client.post(path, headers={"Authorization": f"Bearer {other_token}"})
            assert first.status_code == 200
            assert first.json()["amount_minor"] == 55000
            assert first.json()["status"] == "unpaid"
            assert replay.json()["id"] == first.json()["id"]
            assert denied.status_code == 404
            assert client.get("/api/v1/billing/payments", headers=headers).json() == []
            appointments = client.get("/api/v1/providers/appointments", headers=headers)
            assert appointments.status_code == 200
            appointment_flags = {row["id"]: row for row in appointments.json()}
            assert appointment_flags[appointment_id]["can_start_payment"] is True
            assert appointment_flags[stale_appointment_id]["can_start_payment"] is False
            assert appointment_flags[stale_appointment_id]["payment_block_reason"] == "past"
            assert appointment_flags[cancelled_appointment_id]["can_start_payment"] is False
            assert appointment_flags[cancelled_appointment_id]["payment_block_reason"] == "cancelled"
            assert client.post(
                f"/api/v1/billing/appointments/{stale_appointment_id}/invoice", headers=headers
            ).status_code == 409
            assert client.post(
                f"/api/v1/billing/appointments/{cancelled_appointment_id}/invoice", headers=headers
            ).status_code == 409
            with test_sessions() as db:
                patient_id = db.scalar(select(User.id).where(User.email == "invoice-patient@example.com"))
                invoice = db.get(Invoice, first.json()["id"])
                assert invoice.owner_user_id == patient_id
                assert invoice.appointment_id == appointment_id
                assert db.scalar(select(func.count()).select_from(Invoice).where(Invoice.appointment_id == appointment_id)) == 1
                stale_invoice = Invoice(
                    owner_user_id=patient_id,
                    hospital_id=invoice.hospital_id,
                    appointment_id=stale_appointment_id,
                    invoice_number="STALE-APPOINTMENT-TEST",
                    description="Stale consultation test",
                    amount_minor=55000,
                    currency="INR",
                    status="unpaid",
                )
                db.add(stale_invoice)
                db.commit()
                stale_invoice_id = stale_invoice.id
            stale_checkout = client.post(
                "/api/v1/billing/checkout",
                headers=headers,
                json={"invoice_id": stale_invoice_id},
            )
            assert stale_checkout.status_code == 409
            assert stale_checkout.json()["detail"] == "Past appointments cannot start a new consultation payment."
    finally:
        app.dependency_overrides.clear()
        engine.dispose()

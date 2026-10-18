import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app
from app.models.billing import Invoice, Payment, PaymentWebhookEvent
from app.models.providers import Appointment, Doctor, Hospital
from app.models.user import User


TEST_WEBHOOK_SECRET = "test_webhook_secret_for_hmac_sha256_verification_123"


@pytest.fixture
def test_db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)

    def override_get_db():
        with session_factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield session_factory
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


@pytest.fixture
def seeded_checkout(test_db_session):
    with test_db_session() as db:
        patient = User(
            full_name="Webhook Patient",
            email="webhook.patient@example.com",
            password_hash="dummy_hash",
            role="patient",
        )
        hospital = Hospital(name="Apex Webhook Hospital", city="Raipur", state="CG", verified=True)
        db.add_all([patient, hospital])
        db.flush()

        doctor = Doctor(hospital_id=hospital.id, full_name="Dr. Raman", specialty="Cardiology", fee_minor=75000)
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
        db.flush()

        invoice = Invoice(
            owner_user_id=patient.id,
            hospital_id=hospital.id,
            appointment_id=appointment.id,
            invoice_number="INV-WEBHOOK-TEST-001",
            description="Consultation fee",
            amount_minor=75000,
            currency="INR",
            status="unpaid",
        )
        db.add(invoice)
        db.flush()

        payment = Payment(
            invoice_id=invoice.id,
            provider_order_id="order_webhook_test_12345",
            status="created",
        )
        db.add(payment)
        db.commit()

        return {
            "patient_id": patient.id,
            "invoice_id": invoice.id,
            "payment_id": payment.id,
            "order_id": payment.provider_order_id,
            "amount_minor": invoice.amount_minor,
            "currency": invoice.currency,
        }


def make_webhook_request(
    client: TestClient,
    event: dict,
    *,
    event_id: str | None = "evt_test_event_001",
    signature: str | None = None,
    secret: str = TEST_WEBHOOK_SECRET,
    custom_headers: dict | None = None,
):
    body = json.dumps(event, separators=(",", ":")).encode("utf-8")
    if signature is None:
        signature = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()

    headers = {"Content-Type": "application/json"}
    if signature != "OMIT":
        headers["X-Razorpay-Signature"] = signature
    if event_id is not None:
        headers["X-Razorpay-Event-Id"] = event_id
    if custom_headers:
        headers.update(custom_headers)

    return client.post("/api/v1/billing/webhooks/razorpay", headers=headers, content=body)


def test_webhook_valid_signature_payment_captured(test_db_session, seeded_checkout, monkeypatch):
    monkeypatch.setattr(settings, "payment_mode", "live")
    monkeypatch.setattr(settings, "razorpay_webhook_secret", TEST_WEBHOOK_SECRET)

    order_id = seeded_checkout["order_id"]
    event_payload = {
        "entity": "event",
        "account_id": "acc_test_merchant",
        "event": "payment.captured",
        "contains": ["payment"],
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_test_capture_9999",
                    "order_id": order_id,
                    "amount": 75000,
                    "currency": "INR",
                    "status": "captured",
                }
            }
        },
    }

    with TestClient(app) as client:
        response = make_webhook_request(client, event_payload, event_id="evt_valid_capture_001")
        assert response.status_code == 204

    with test_db_session() as db:
        invoice = db.get(Invoice, seeded_checkout["invoice_id"])
        payment = db.get(Payment, seeded_checkout["payment_id"])
        webhook_event = db.scalar(
            select(PaymentWebhookEvent).where(PaymentWebhookEvent.provider_event_id == "evt_valid_capture_001")
        )

        assert invoice.status == "paid"
        assert invoice.paid_at is not None
        assert payment.status == "paid"
        assert payment.provider_payment_id == "pay_test_capture_9999"
        assert webhook_event is not None
        assert webhook_event.result == "captured"
        assert webhook_event.payment_id == payment.id


def test_webhook_invalid_signature_rejected(test_db_session, seeded_checkout, monkeypatch):
    monkeypatch.setattr(settings, "payment_mode", "live")
    monkeypatch.setattr(settings, "razorpay_webhook_secret", TEST_WEBHOOK_SECRET)

    event_payload = {
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_tampered",
                    "order_id": seeded_checkout["order_id"],
                    "amount": 75000,
                    "currency": "INR",
                }
            }
        },
    }

    with TestClient(app) as client:
        response = make_webhook_request(
            client,
            event_payload,
            event_id="evt_tampered_001",
            signature="invalid_signature_hex_digest_tampered",
        )
        assert response.status_code == 400
        assert "signature is invalid" in response.json()["detail"].lower()

    with test_db_session() as db:
        invoice = db.get(Invoice, seeded_checkout["invoice_id"])
        payment = db.get(Payment, seeded_checkout["payment_id"])
        assert invoice.status == "unpaid"
        assert payment.status == "created"


def test_webhook_missing_signature_rejected(test_db_session, seeded_checkout, monkeypatch):
    monkeypatch.setattr(settings, "payment_mode", "live")
    monkeypatch.setattr(settings, "razorpay_webhook_secret", TEST_WEBHOOK_SECRET)

    event_payload = {"event": "payment.captured", "payload": {}}

    with TestClient(app) as client:
        response = make_webhook_request(client, event_payload, signature="OMIT")
        assert response.status_code == 400
        assert "signature is invalid" in response.json()["detail"].lower()


def test_webhook_disabled_in_demo_mode(test_db_session, seeded_checkout, monkeypatch):
    monkeypatch.setattr(settings, "payment_mode", "demo")
    monkeypatch.setattr(settings, "razorpay_webhook_secret", TEST_WEBHOOK_SECRET)

    event_payload = {"event": "payment.captured"}
    with TestClient(app) as client:
        response = make_webhook_request(client, event_payload)
        assert response.status_code == 404
        assert "disabled in demo mode" in response.json()["detail"]


def test_webhook_unconfigured_secret_returns_503(test_db_session, seeded_checkout, monkeypatch):
    monkeypatch.setattr(settings, "payment_mode", "live")
    monkeypatch.setattr(settings, "razorpay_webhook_secret", "")

    event_payload = {"event": "payment.captured"}
    with TestClient(app) as client:
        response = make_webhook_request(client, event_payload)
        assert response.status_code == 503
        assert "not configured" in response.json()["detail"].lower()


def test_webhook_duplicate_event_idempotency(test_db_session, seeded_checkout, monkeypatch):
    monkeypatch.setattr(settings, "payment_mode", "live")
    monkeypatch.setattr(settings, "razorpay_webhook_secret", TEST_WEBHOOK_SECRET)

    event_payload = {
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_dup_001",
                    "order_id": seeded_checkout["order_id"],
                    "amount": 75000,
                    "currency": "INR",
                }
            }
        },
    }

    with TestClient(app) as client:
        res1 = make_webhook_request(client, event_payload, event_id="evt_duplicate_test_001")
        assert res1.status_code == 204

        res2 = make_webhook_request(client, event_payload, event_id="evt_duplicate_test_001")
        assert res2.status_code == 204

    with test_db_session() as db:
        events = list(
            db.scalars(
                select(PaymentWebhookEvent).where(PaymentWebhookEvent.provider_event_id == "evt_duplicate_test_001")
            ).all()
        )
        assert len(events) == 1
        assert events[0].result == "captured"


def test_webhook_duplicate_event_reused_with_different_payload_rejected(test_db_session, seeded_checkout, monkeypatch):
    monkeypatch.setattr(settings, "payment_mode", "live")
    monkeypatch.setattr(settings, "razorpay_webhook_secret", TEST_WEBHOOK_SECRET)

    payload_a = {
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_reused_001",
                    "order_id": seeded_checkout["order_id"],
                    "amount": 75000,
                    "currency": "INR",
                }
            }
        },
    }
    payload_b = {
        "event": "payment.failed",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_reused_002",
                    "order_id": seeded_checkout["order_id"],
                    "amount": 75000,
                    "currency": "INR",
                }
            }
        },
    }

    with TestClient(app) as client:
        res1 = make_webhook_request(client, payload_a, event_id="evt_reused_id_001")
        assert res1.status_code == 204

        res2 = make_webhook_request(client, payload_b, event_id="evt_reused_id_001")
        assert res2.status_code == 409
        assert "different payload" in res2.json()["detail"]


def test_webhook_supported_payment_failed_event(test_db_session, seeded_checkout, monkeypatch):
    monkeypatch.setattr(settings, "payment_mode", "live")
    monkeypatch.setattr(settings, "razorpay_webhook_secret", TEST_WEBHOOK_SECRET)

    failed_payload = {
        "event": "payment.failed",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_failed_attempt_001",
                    "order_id": seeded_checkout["order_id"],
                    "amount": 75000,
                    "currency": "INR",
                    "error_code": "BAD_REQUEST_ERROR",
                    "error_description": "Card was declined by issuing bank",
                }
            }
        },
    }

    with TestClient(app) as client:
        res = make_webhook_request(client, failed_payload, event_id="evt_failed_001")
        assert res.status_code == 204

    with test_db_session() as db:
        invoice = db.get(Invoice, seeded_checkout["invoice_id"])
        payment = db.get(Payment, seeded_checkout["payment_id"])
        assert payment.status == "failed"
        assert payment.provider_payment_id == "pay_failed_attempt_001"
        assert payment.failure_code == "BAD_REQUEST_ERROR"
        assert payment.failure_description == "Card was declined by issuing bank"
        assert invoice.status == "unpaid"


def test_webhook_payment_failed_after_captured_does_not_override_paid(test_db_session, seeded_checkout, monkeypatch):
    monkeypatch.setattr(settings, "payment_mode", "live")
    monkeypatch.setattr(settings, "razorpay_webhook_secret", TEST_WEBHOOK_SECRET)

    # First mark payment captured
    with test_db_session() as db:
        payment = db.get(Payment, seeded_checkout["payment_id"])
        payment.status = "paid"
        payment.provider_payment_id = "pay_already_captured_001"
        invoice = db.get(Invoice, seeded_checkout["invoice_id"])
        invoice.status = "paid"
        invoice.paid_at = datetime.now(timezone.utc)
        db.commit()

    # Now a late payment.failed arrives for another attempt on that order
    failed_payload = {
        "event": "payment.failed",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_late_failed_002",
                    "order_id": seeded_checkout["order_id"],
                    "amount": 75000,
                    "currency": "INR",
                    "error_code": "GATEWAY_ERROR",
                    "error_description": "Network timeout",
                }
            }
        },
    }

    with TestClient(app) as client:
        res = make_webhook_request(client, failed_payload, event_id="evt_late_failed_001")
        assert res.status_code == 204

    with test_db_session() as db:
        payment = db.get(Payment, seeded_checkout["payment_id"])
        invoice = db.get(Invoice, seeded_checkout["invoice_id"])
        webhook_event = db.scalar(
            select(PaymentWebhookEvent).where(PaymentWebhookEvent.provider_event_id == "evt_late_failed_001")
        )

        assert payment.status == "paid"
        assert invoice.status == "paid"
        assert webhook_event.result == "already_paid"


def test_webhook_supported_order_paid_event(test_db_session, seeded_checkout, monkeypatch):
    monkeypatch.setattr(settings, "payment_mode", "live")
    monkeypatch.setattr(settings, "razorpay_webhook_secret", TEST_WEBHOOK_SECRET)

    order_paid_payload = {
        "entity": "event",
        "account_id": "acc_test_merchant",
        "event": "order.paid",
        "contains": ["order", "payment"],
        "payload": {
            "order": {
                "entity": {
                    "id": seeded_checkout["order_id"],
                    "amount": 75000,
                    "currency": "INR",
                    "status": "paid",
                }
            },
            "payment": {
                "entity": {
                    "id": "pay_from_order_paid_001",
                    "order_id": seeded_checkout["order_id"],
                    "amount": 75000,
                    "currency": "INR",
                    "status": "captured",
                }
            },
        },
    }

    with TestClient(app) as client:
        res = make_webhook_request(client, order_paid_payload, event_id="evt_order_paid_001")
        assert res.status_code == 204

    with test_db_session() as db:
        invoice = db.get(Invoice, seeded_checkout["invoice_id"])
        payment = db.get(Payment, seeded_checkout["payment_id"])
        assert invoice.status == "paid"
        assert payment.status == "paid"
        assert payment.provider_payment_id == "pay_from_order_paid_001"


def test_webhook_amount_or_currency_mismatch_rejected(test_db_session, seeded_checkout, monkeypatch):
    monkeypatch.setattr(settings, "payment_mode", "live")
    monkeypatch.setattr(settings, "razorpay_webhook_secret", TEST_WEBHOOK_SECRET)

    mismatched_payload = {
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_mismatch_001",
                    "order_id": seeded_checkout["order_id"],
                    "amount": 99999,  # does not match invoice (75000)
                    "currency": "INR",
                }
            }
        },
    }

    with TestClient(app) as client:
        res = make_webhook_request(client, mismatched_payload, event_id="evt_mismatch_001")
        assert res.status_code == 400
        assert "does not match its invoice amount" in res.json()["detail"]


def test_webhook_unmatched_order_safely_acknowledged(test_db_session, monkeypatch):
    monkeypatch.setattr(settings, "payment_mode", "live")
    monkeypatch.setattr(settings, "razorpay_webhook_secret", TEST_WEBHOOK_SECRET)

    unmatched_payload = {
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_unknown_order",
                    "order_id": "order_not_in_our_system_9999",
                    "amount": 50000,
                    "currency": "INR",
                }
            }
        },
    }

    with TestClient(app) as client:
        res = make_webhook_request(client, unmatched_payload, event_id="evt_unmatched_001")
        assert res.status_code == 204

    with test_db_session() as db:
        webhook_event = db.scalar(
            select(PaymentWebhookEvent).where(PaymentWebhookEvent.provider_event_id == "evt_unmatched_001")
        )
        assert webhook_event is not None
        assert webhook_event.result == "unmatched"
        assert webhook_event.payment_id is None


def test_webhook_event_id_from_body_payload_fallback(test_db_session, seeded_checkout, monkeypatch):
    monkeypatch.setattr(settings, "payment_mode", "live")
    monkeypatch.setattr(settings, "razorpay_webhook_secret", TEST_WEBHOOK_SECRET)

    payload_with_id = {
        "id": "evt_body_id_001",
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_body_id_001",
                    "order_id": seeded_checkout["order_id"],
                    "amount": 75000,
                    "currency": "INR",
                }
            }
        },
    }

    # Pass event_id=None so header is omitted
    with TestClient(app) as client:
        res = make_webhook_request(client, payload_with_id, event_id=None)
        assert res.status_code == 204

    with test_db_session() as db:
        event = db.scalar(
            select(PaymentWebhookEvent).where(PaymentWebhookEvent.provider_event_id == "evt_body_id_001")
        )
        assert event is not None
        assert event.result == "captured"


def test_webhook_database_integrity_error_concurrent_deduplication(test_db_session, seeded_checkout, monkeypatch):
    monkeypatch.setattr(settings, "payment_mode", "live")
    monkeypatch.setattr(settings, "razorpay_webhook_secret", TEST_WEBHOOK_SECRET)

    payload = {
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_race_001",
                    "order_id": seeded_checkout["order_id"],
                    "amount": 75000,
                    "currency": "INR",
                }
            }
        },
    }

    # First insert the event record as if a concurrent thread committed it
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    payload_hash = hashlib.sha256(payload_bytes).hexdigest()

    with test_db_session() as db:
        db.add(
            PaymentWebhookEvent(
                provider_event_id="evt_race_001",
                event_type="payment.captured",
                payload_sha256=payload_hash,
                result="captured",
            )
        )
        db.commit()

    # Now make the request: during commit, an IntegrityError would occur if duplicate is inserted.
    # The handler catches it, finds the matching duplicate, and returns 204.
    with TestClient(app) as client:
        res = make_webhook_request(client, payload, event_id="evt_race_001")
        assert res.status_code == 204


def test_webhook_database_failure_rollback(test_db_session, seeded_checkout, monkeypatch):
    monkeypatch.setattr(settings, "payment_mode", "live")
    monkeypatch.setattr(settings, "razorpay_webhook_secret", TEST_WEBHOOK_SECRET)

    payload = {
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_fail_db_001",
                    "order_id": seeded_checkout["order_id"],
                    "amount": 75000,
                    "currency": "INR",
                }
            }
        },
    }

    with patch.object(Session, "commit", side_effect=SQLAlchemyError("Simulated DB connection lost")):
        with TestClient(app) as client:
            res = make_webhook_request(client, payload, event_id="evt_db_fail_001")
            assert res.status_code == 500
            assert "Failed to persist webhook event" in res.json()["detail"]


def test_webhook_oversized_payload_rejected(test_db_session, monkeypatch):
    monkeypatch.setattr(settings, "payment_mode", "live")
    monkeypatch.setattr(settings, "razorpay_webhook_secret", TEST_WEBHOOK_SECRET)

    large_body = b"X" * 1_000_001
    signature = hmac.new(TEST_WEBHOOK_SECRET.encode(), large_body, hashlib.sha256).hexdigest()

    with TestClient(app) as client:
        res = client.post(
            "/api/v1/billing/webhooks/razorpay",
            headers={
                "X-Razorpay-Signature": signature,
                "X-Razorpay-Event-Id": "evt_large_001",
                "Content-Type": "application/json",
            },
            content=large_body,
        )
        assert res.status_code == 413
        assert "too large" in res.json()["detail"].lower()

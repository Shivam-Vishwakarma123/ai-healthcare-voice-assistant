import hashlib
import hmac
import json
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app
from app.models.billing import Invoice, Payment
from app.models.providers import Appointment, Doctor, Hospital
from app.models.user import User
from app.services.payment_service import RazorpayPaymentService
from tests.auth_utils import make_session_token

SYNTHETIC_TEST_CARDS = {
    "domestic": [
        {"network": "Visa", "number": "4100 2800 0000 1007", "type": "Debit, consumer"},
        {"network": "Mastercard", "number": "5555 5100 0008 1006", "type": "Credit, business"},
        {"network": "Mastercard", "number": "5180 2872 0009 1001", "type": "Prepaid, consumer"},
        {"network": "RuPay", "number": "6527 6589 0000 1005", "type": "Credit, consumer"},
        {"network": "Diners", "number": "3608 280009 1007", "type": "Credit, consumer"},
        {"network": "Amex", "number": "3402 560004 01007", "type": "Credit, consumer"},
    ],
    "international": [
        {"network": "Mastercard", "number": "5555 5555 5555 4444"},
        {"network": "Mastercard", "number": "5105 1051 0510 5100"},
        {"network": "Mastercard", "number": "5104 0600 0000 0008"},
        {"network": "Visa", "number": "4012 8888 8888 1881"},
    ],
    "emi": [
        {"network": "Mastercard", "number": "5241 8100 0000 0000"},
    ],
}


def test_razorpay_test_mode_credentials_and_config():
    """Verify that Test Mode credentials are configured with expected prefix."""
    assert settings.payment_mode == "live", "payment_mode must be 'live' to select Razorpay provider"
    assert settings.razorpay_key_id.startswith("rzp_test_"), "RAZORPAY_KEY_ID must use Razorpay test mode key in development"
    assert len(settings.razorpay_key_secret) > 10, "RAZORPAY_KEY_SECRET must be configured"


def test_test_card_catalog_structure():
    """Verify synthetic test-card numbers conform to Razorpay documentation."""
    for card in SYNTHETIC_TEST_CARDS["domestic"]:
        clean_num = card["number"].replace(" ", "")
        assert clean_num.isdigit()
        assert 14 <= len(clean_num) <= 16
    for card in SYNTHETIC_TEST_CARDS["international"]:
        clean_num = card["number"].replace(" ", "")
        assert clean_num.isdigit()
        assert len(clean_num) == 16


def test_complete_razorpay_test_mode_flow(monkeypatch):
    """Test full workflow: invoice creation, order creation, signature verification, and idempotency."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    test_sessions = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)

    def override_database():
        with test_sessions() as db:
            yield db

    with test_sessions() as db:
        patient_a = User(full_name="Patient Alpha", email="alpha@test.carevoice", password_hash="dummy", role="patient")
        patient_b = User(full_name="Patient Beta", email="beta@test.carevoice", password_hash="dummy", role="patient")
        hospital = Hospital(name="Apex Hospital", city="Raipur", state="CG", verified=True)
        db.add_all([patient_a, patient_b, hospital])
        db.flush()

        doctor = Doctor(hospital_id=hospital.id, full_name="Dr. Raman", specialty="Cardiology", fee_minor=75000)
        db.add(doctor)
        db.flush()

        appointment = Appointment(
            patient_user_id=patient_a.id,
            doctor_id=doctor.id,
            hospital_id=hospital.id,
            scheduled_for=datetime.now(timezone.utc) + timedelta(days=2),
            status="confirmed",
        )
        db.add(appointment)
        db.commit()

        token_a = make_session_token(db, patient_a)
        token_b = make_session_token(db, patient_b)
        apt_id = appointment.id

    test_secret = "test_key_secret_for_hmac_verification"
    monkeypatch.setattr(settings, "payment_mode", "live")
    monkeypatch.setattr(settings, "razorpay_key_id", "rzp_test_mock_key")
    monkeypatch.setattr(settings, "razorpay_key_secret", test_secret)
    monkeypatch.setattr(settings, "razorpay_checkout_config_id", "config_test_upi_123")

    # Mock Razorpay HTTP responses
    mock_order_id = "order_rzp_mock_12345"
    mock_payment_id = "pay_rzp_mock_67890"

    def mock_provider_response(request: httpx.Request):
        if request.method == "POST" and request.url.path.endswith("/orders"):
            body = json.loads(request.content)
            assert body["amount"] == 75000
            assert body["currency"] == "INR"
            assert body["receipt"].startswith("cv_")
            assert len(body["receipt"]) <= 40
            assert "payment_capture" not in body
            assert body.get("checkout_config_id") == "config_test_upi_123"
            return httpx.Response(200, json={
                "id": mock_order_id,
                "amount": 75000,
                "currency": "INR",
                "status": "created",
            })
        if request.method == "GET" and request.url.path.endswith(f"/payments/{mock_payment_id}"):
            return httpx.Response(200, json={
                "id": mock_payment_id,
                "order_id": mock_order_id,
                "amount": 75000,
                "currency": "INR",
                "status": "captured",
            })
        if request.method == "POST" and "/capture" in request.url.path:
            return httpx.Response(200, json={
                "id": mock_payment_id,
                "order_id": mock_order_id,
                "amount": 75000,
                "currency": "INR",
                "status": "captured",
            })
        return httpx.Response(404, json={"error": "not found"})

    original_async_client = httpx.AsyncClient
    transport = httpx.MockTransport(mock_provider_response)
    from app.services import payment_service
    monkeypatch.setattr(
        payment_service.httpx,
        "AsyncClient",
        lambda **kwargs: original_async_client(transport=transport, **kwargs),
    )

    app.dependency_overrides[get_db] = override_database
    try:
        with TestClient(app) as client:
            # 1. Patient A requests invoice for their appointment
            inv_res = client.post(
                f"/api/v1/billing/appointments/{apt_id}/invoice",
                headers={"Authorization": f"Bearer {token_a}"},
            )
            assert inv_res.status_code == 200
            inv = inv_res.json()
            assert inv["amount_minor"] == 75000
            assert inv["status"] == "unpaid"
            inv_id = inv["id"]

            # 2. Patient B cannot pay or start checkout for Patient A's invoice
            unauthorized_checkout = client.post(
                "/api/v1/billing/checkout",
                headers={"Authorization": f"Bearer {token_b}"},
                json={"invoice_id": inv_id},
            )
            assert unauthorized_checkout.status_code == 404

            # 3. Patient A starts checkout
            checkout_res = client.post(
                "/api/v1/billing/checkout",
                headers={"Authorization": f"Bearer {token_a}"},
                json={"invoice_id": inv_id},
            )
            assert checkout_res.status_code == 200
            order_data = checkout_res.json()
            assert order_data["order_id"] == mock_order_id
            assert order_data["key_id"] == "rzp_test_mock_key"
            assert order_data["amount_minor"] == 75000
            assert order_data["mode"] == "live"

            # 4. Attempt verification with invalid signature -> 400
            bad_sig_res = client.post(
                "/api/v1/billing/verify",
                headers={"Authorization": f"Bearer {token_a}"},
                json={
                    "invoice_id": inv_id,
                    "razorpay_order_id": mock_order_id,
                    "razorpay_payment_id": mock_payment_id,
                    "razorpay_signature": "invalid_tampered_signature_12345",
                },
            )
            assert bad_sig_res.status_code == 400
            assert "signature is invalid" in bad_sig_res.json()["detail"].lower()

            # 5. Generate correct HMAC-SHA256 signature
            valid_sig = hmac.new(
                test_secret.encode(),
                f"{mock_order_id}|{mock_payment_id}".encode(),
                hashlib.sha256,
            ).hexdigest()

            # 6. Verify with valid signature -> 200 Paid
            verify_res = client.post(
                "/api/v1/billing/verify",
                headers={"Authorization": f"Bearer {token_a}"},
                json={
                    "invoice_id": inv_id,
                    "razorpay_order_id": mock_order_id,
                    "razorpay_payment_id": mock_payment_id,
                    "razorpay_signature": valid_sig,
                },
            )
            assert verify_res.status_code == 200
            verified_invoice = verify_res.json()
            assert verified_invoice["status"] == "paid"
            assert verified_invoice["paid_at"] is not None

            # 7. Duplicate verify request is idempotent
            dup_verify = client.post(
                "/api/v1/billing/verify",
                headers={"Authorization": f"Bearer {token_a}"},
                json={
                    "invoice_id": inv_id,
                    "razorpay_order_id": mock_order_id,
                    "razorpay_payment_id": mock_payment_id,
                    "razorpay_signature": valid_sig,
                },
            )
            assert dup_verify.status_code == 200
            assert dup_verify.json()["status"] == "paid"

            # 8. Check that appointment list now reflects paid invoice status
            apt_list = client.get(
                "/api/v1/providers/appointments",
                headers={"Authorization": f"Bearer {token_a}"},
            )
            assert apt_list.status_code == 200
            patient_apts = apt_list.json()
            assert len(patient_apts) == 1
            assert patient_apts[0]["invoice_status"] == "paid"
            assert patient_apts[0]["payment_status"] == "paid"

            # 9. Database state inspection
            with test_sessions() as db:
                db_invoice = db.get(Invoice, inv_id)
                db_payment = db.scalar(select(Payment).where(Payment.invoice_id == inv_id))
                assert db_invoice.status == "paid"
                assert db_payment.status == "paid"
                assert db_payment.provider_payment_id == mock_payment_id
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


@pytest.mark.anyio
async def test_live_razorpay_api_order_creation_if_connected():
    """Verify live order creation against Razorpay Test Mode API using configured credentials."""
    if not settings.razorpay_key_id.startswith("rzp_test_") or not settings.razorpay_key_secret:
        pytest.skip("Razorpay Test Mode credentials not configured")

    svc = RazorpayPaymentService(
        key_id=settings.razorpay_key_id,
        key_secret=settings.razorpay_key_secret,
        api_base_url=settings.razorpay_api_base_url,
    )
    order_id = await svc.create_order(
        invoice_id=88888,
        receipt=f"test_{uuid.uuid4().hex}",
        amount_minor=60000,
        currency="INR",
    )
    assert order_id.startswith("order_")
    assert len(order_id) > 10


@pytest.mark.anyio
async def test_razorpay_order_rejects_amount_below_minimum():
    svc = RazorpayPaymentService(
        key_id="rzp_test_mock_key",
        key_secret="test_secret",
        api_base_url="https://razorpay.test/v1",
    )
    with pytest.raises(ValueError, match="at least 100 paise"):
        await svc.create_order(
            invoice_id=1,
            receipt="cv_test_minimum",
            amount_minor=99,
            currency="INR",
        )

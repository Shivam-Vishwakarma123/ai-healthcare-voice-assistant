# Razorpay Payment Integration Setup Guide

## Executive Summary

The CareVoice application has **complete Razorpay integration code** already implemented, including:

✅ Backend order creation, signature verification, and webhook handling  
✅ Frontend Razorpay Checkout SDK integration  
✅ Appointment payment eligibility logic  
✅ Database models for invoices, payments, refunds  
✅ Comprehensive automated tests (all passing)

**Current Status:** The code is production-ready but **requires Razorpay Test Mode credentials** to enable the actual checkout flow.

---

## Architecture Overview

### Payment Mode Configuration

The application uses `PAYMENT_MODE` to select the payment provider:

- **`PAYMENT_MODE=demo`** — Local simulation without Razorpay (no card form, simulated outcomes only)
- **`PAYMENT_MODE=live`** — Real Razorpay integration (uses Test Mode keys in development)

⚠️ **Important:** "live" mode means "use the real Razorpay gateway" — it does NOT mean production. During development, `PAYMENT_MODE=live` with `rzp_test_*` keys uses Razorpay's Test Mode sandbox.

### Complete Payment Flow

```
Patient clicks "Pay Now"
    ↓
Frontend: POST /api/v1/billing/appointments/{id}/invoice
    → Backend creates/retrieves invoice using doctor's fee
    ↓
Frontend: POST /api/v1/billing/checkout {invoice_id}
    ↓
Backend checks:
    - User owns invoice
    - Invoice is unpaid
    - Appointment is eligible (upcoming, not cancelled, not past)
    - Razorpay credentials are configured
    ↓
Backend creates Razorpay order via API
    → Returns: order_id, key_id, amount, currency
    ↓
Frontend loads Razorpay Checkout SDK
    ↓
Frontend opens Razorpay-hosted checkout modal
    → Patient enters card details on Razorpay's secure page
    → Razorpay handles 3DS/OTP authentication
    ↓
Razorpay calls success handler with:
    - razorpay_order_id
    - razorpay_payment_id
    - razorpay_signature
    ↓
Frontend: POST /api/v1/billing/verify
    ↓
Backend verifies:
    1. HMAC signature (order_id|payment_id with secret)
    2. Fetches payment from Razorpay API
    3. Confirms status="captured", correct amount/currency
    4. Updates invoice.status="paid", payment.status="paid"
    ↓
Patient sees "Payment verified" success message
```

---

## Prerequisites

1. **Razorpay Account** — Sign up at https://dashboard.razorpay.com/signup
2. **Test Mode Access** — Available immediately after signup (no business verification needed)
3. **Docker Compose** — Services must be running

---

## Step-by-Step Setup Instructions

### Step 1: Get Razorpay Test Mode Credentials

1. Go to https://dashboard.razorpay.com/ and sign in
2. **Switch to Test Mode** using the toggle in the top-left corner (it should show "Test Mode" with a yellow/orange indicator)
3. Navigate to **Settings → API Keys** (or directly: https://dashboard.razorpay.com/app/keys)
4. Click **Generate Test Key** if you don't have one
5. Copy:
   - **Key ID** (starts with `rzp_test_`)
   - **Key Secret** (click "Show" and copy the secret)

⚠️ **Never use Live Mode keys during development.** The backend validates that development environments use `rzp_test_*` keys.

### Step 2: Configure Environment Variables

Edit the **`.env`** file in the project root (NOT `.env.example`):

```bash
# Payment configuration
PAYMENT_MODE=live

# Razorpay Test Mode credentials (keep secrets server-side)
RAZORPAY_KEY_ID=rzp_test_YourActualKeyID
RAZORPAY_KEY_SECRET=YourActualKeySecret
RAZORPAY_WEBHOOK_SECRET=
```

⚠️ **Security Notes:**
- `.env` is in `.gitignore` — never commit actual credentials
- Only `RAZORPAY_KEY_ID` is sent to the frontend (it's public)
- `RAZORPAY_KEY_SECRET` stays server-side only
- `RAZORPAY_WEBHOOK_SECRET` is optional (only needed if you configure webhooks)

### Step 3: Enable Cards in Razorpay Checkout Settings

1. Go to **Settings → Checkout → Payment Methods** (https://dashboard.razorpay.com/app/checkout)
2. Ensure **Cards** is enabled under **Test Mode** payment methods
3. If disabled, toggle it on and save

This is why the card option might not appear even with valid credentials.

### Step 4: Restart Backend Service

```bash
# From project root
docker compose restart backend

# Verify backend started successfully
docker compose logs backend | tail -20
```

The backend validates configuration on startup. If credentials are invalid, you'll see an error in the logs.

### Step 5: Restart Frontend (Optional)

The frontend doesn't need Razorpay keys at build time, but restart to ensure it fetches the latest `/billing/config`:

```bash
docker compose restart frontend
```

### Step 6: Verify Configuration

Open your browser and check the API:

```bash
# Get billing configuration (requires authentication)
curl http://localhost:8000/api/v1/billing/config \
  -H "Authorization: Bearer YOUR_TOKEN"
```

Expected response with valid credentials:

```json
{
  "payment_mode": "live",
  "online_payment_enabled": true,
  "provider_checkout_enabled": true,
  "provider_test_mode": true,
  "demo_payment_enabled": false,
  "checkout_enabled": true
}
```

If `provider_checkout_enabled` is `false`, credentials are missing or invalid.

---

## Testing the Payment Flow

### Option A: Use Existing Seeded Data

If you've run the demo seed script:

```bash
docker compose exec backend python -m app.seed_demo
```

You can sign in as:
- **Patient:** `patient01@demo.carevoice.test` / `CareVoiceDemo2026!`
- **Doctor:** `doctor01@demo.carevoice.test` / `CareVoiceDemo2026!`

### Option B: Manual Setup

1. **Create accounts:**
   - Sign up as a patient at http://localhost:3000
   - Create platform admin (first-time setup at `/setup/administrator`)
   - Create hospital, doctor, and hospital admin via Provider Dashboard

2. **Book an appointment:**
   - Sign in as patient
   - Navigate to **Find Care**
   - Select a verified doctor
   - Book an upcoming appointment

3. **Pay for appointment:**
   - Go to **Appointments**
   - Click **Pay Now** on an upcoming appointment
   - Razorpay Checkout should open

### Test Card Details (Razorpay Test Mode)

Use these official test cards in Razorpay Test Mode:

| Card Number | CVV | Expiry | Result |
|-------------|-----|--------|--------|
| `4111 1111 1111 1111` | Any 3 digits | Any future date | Success |
| `4100 2800 0000 1007` | Any 3 digits | Any future date | Success (recommended by Razorpay docs) |
| `4000 0000 0000 0002` | Any 3 digits | Any future date | Card declined |

**Important:** Test cards only work with `rzp_test_*` keys in Test Mode.

### Expected Checkout Experience

1. Click **Pay Now** → Razorpay Checkout modal opens
2. See payment details: doctor name, appointment date, amount
3. **Payment methods available:** Cards, UPI (test mode), Netbanking (test)
4. Select **Card** → Enter test card details
5. Razorpay shows mock bank authentication page → Click **Success**
6. Checkout closes → Frontend verifies payment with backend
7. See "Payment verified. Your invoice is paid." success message
8. Appointment shows as **Paid** with transaction reference

---

## Appointment Payment Eligibility Rules

The backend enforces strict eligibility rules in `appointment_payment_eligibility.py`:

| Appointment State | Can Pay? | Reason |
|-------------------|----------|--------|
| Scheduled/Confirmed, future date | ✅ Yes | Eligible for payment |
| Scheduled/Confirmed, past date | ❌ No | "Past appointments cannot start a new consultation payment" |
| Cancelled | ❌ No | "Cancelled appointments cannot start a new consultation payment" |
| Already paid | ✅ Shows receipt | Payment already recorded |
| Doctor has no fee | ❌ No | "The clinician has no billable consultation fee" |

**Date Comparison:** Uses UTC-aware timezone handling. An appointment is "past" if `scheduled_for <= current_time` (both in UTC).

---

## Troubleshooting Guide

### Problem: "Pay Now" opens demo simulator instead of Razorpay

**Cause:** `PAYMENT_MODE=demo` in `.env`

**Fix:**
```bash
# Edit .env
PAYMENT_MODE=live

# Restart backend
docker compose restart backend
```

### Problem: "Online payments are not configured" error

**Cause:** Missing or invalid Razorpay credentials

**Fix:**
1. Check `.env` has `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET`
2. Verify Key ID starts with `rzp_test_` (for development)
3. Restart backend: `docker compose restart backend`

### Problem: Razorpay Checkout opens but no Card option

**Cause:** Cards not enabled in Razorpay Dashboard

**Fix:**
1. Go to https://dashboard.razorpay.com/app/checkout
2. Switch to **Test Mode**
3. Navigate to **Payment Methods**
4. Enable **Cards**
5. Try payment again (no restart needed)

### Problem: "Past appointments cannot start a new consultation payment"

**Cause:** Appointment date is in the past OR timezone handling issue

**Fix:**
1. Book a new appointment with a future date
2. Check that appointment `scheduled_for` is actually in the future
3. Verify system timezone is correct

**Debug:**
```bash
# Check appointment date in database
docker compose exec backend python -c "
from datetime import datetime, timezone
from app.core.database import SessionLocal
from app.models.providers import Appointment
db = SessionLocal()
apt = db.query(Appointment).filter(Appointment.id == YOUR_APPOINTMENT_ID).first()
print(f'Scheduled: {apt.scheduled_for}')
print(f'Now (UTC): {datetime.now(timezone.utc)}')
print(f'Is future: {apt.scheduled_for > datetime.now(timezone.utc)}')
"
```

### Problem: Payment signature verification fails

**Cause:** Wrong `RAZORPAY_KEY_SECRET` or signature tampering

**Fix:**
1. Verify you copied the correct Key Secret from Razorpay Dashboard
2. Ensure no extra spaces in `.env` file
3. Restart backend after changing secret

### Problem: Checkout SDK doesn't load / "Razorpay is not defined"

**Cause:** Network issue loading https://checkout.razorpay.com/v1/checkout.js

**Fix:**
1. Check browser console for errors
2. Verify internet connection
3. Try a different browser/network
4. Check browser doesn't block third-party scripts

### Problem: Test card payment fails with "Card declined"

**Cause:** Using wrong test card or Live Mode keys with test card

**Fix:**
1. Verify you're in Test Mode (check dashboard top-left)
2. Use official test card: `4111 1111 1111 1111`
3. Ensure Key ID starts with `rzp_test_`

---

## Webhook Setup (Optional)

Webhooks provide asynchronous payment confirmations and are recommended for production.

### Configure Webhook in Razorpay Dashboard

1. Go to **Settings → Webhooks** (https://dashboard.razorpay.com/app/webhooks)
2. Click **Create Webhook**
3. **Webhook URL:** `https://YOUR_PUBLIC_DOMAIN/api/v1/billing/webhooks/razorpay`
   - For local testing: Use ngrok or similar tunnel
   - Example: `https://abc123.ngrok.io/api/v1/billing/webhooks/razorpay`
4. **Secret:** Generate a random secret (or use `openssl rand -hex 32`)
5. **Events:** Subscribe to:
   - `payment.captured`
   - `payment.failed`
   - `refund.processed`
   - `refund.failed`
6. Save webhook and copy the **Secret**

### Update .env

```bash
RAZORPAY_WEBHOOK_SECRET=whsec_YourWebhookSecret
```

Restart backend:
```bash
docker compose restart backend
```

### Test Webhook

Razorpay Dashboard provides a webhook test tool. Send a test `payment.captured` event and check backend logs:

```bash
docker compose logs -f backend | grep webhook
```

---

## Security Checklist

✅ **Do:**
- Use `rzp_test_*` keys in development
- Keep `RAZORPAY_KEY_SECRET` server-side only
- Verify payment signature on backend before marking paid
- Validate payment amount/currency from database, not client
- Use HTTPS in production
- Rotate credentials if exposed

❌ **Don't:**
- Commit `.env` to Git
- Send `RAZORPAY_KEY_SECRET` to frontend
- Trust client-supplied amounts
- Use Test Mode keys in production
- Store card numbers or CVV
- Skip signature verification

---

## Database Schema

### Invoices

```sql
CREATE TABLE invoices (
    id SERIAL PRIMARY KEY,
    owner_user_id INT NOT NULL,
    hospital_id INT,
    appointment_id INT UNIQUE,  -- One invoice per appointment
    invoice_number VARCHAR(40) UNIQUE NOT NULL,
    description VARCHAR(240) NOT NULL,
    amount_minor INT NOT NULL,  -- Amount in paise (₹125.00 = 12500)
    currency VARCHAR(3) DEFAULT 'INR',
    status VARCHAR(24) DEFAULT 'unpaid',  -- unpaid, paid, refunded, partially_refunded
    created_at TIMESTAMPTZ DEFAULT NOW(),
    paid_at TIMESTAMPTZ
);
```

### Payments

```sql
CREATE TABLE payments (
    id SERIAL PRIMARY KEY,
    invoice_id INT NOT NULL,
    provider_order_id VARCHAR(80) UNIQUE NOT NULL,  -- Razorpay order_XXX or demo_XXX
    provider_payment_id VARCHAR(80) UNIQUE,  -- Razorpay pay_XXX
    status VARCHAR(24) DEFAULT 'created',  -- created, paid, failed, cancelled, expired
    failure_code VARCHAR(80),
    failure_description TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

### Refunds

```sql
CREATE TABLE payment_refunds (
    id SERIAL PRIMARY KEY,
    payment_id INT NOT NULL,
    requested_by_user_id INT NOT NULL,
    idempotency_key VARCHAR(128) UNIQUE NOT NULL,
    provider_refund_id VARCHAR(80) UNIQUE,  -- Razorpay rfnd_XXX
    amount_minor INT NOT NULL,
    currency VARCHAR(3) NOT NULL,
    status VARCHAR(24) DEFAULT 'pending',  -- pending, processing, processed, failed
    reason VARCHAR(500) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## API Reference

### Get Billing Configuration

```http
GET /api/v1/billing/config
Authorization: Bearer {token}
```

Response:
```json
{
  "payment_mode": "live",
  "online_payment_enabled": true,
  "provider_checkout_enabled": true,
  "provider_test_mode": true,
  "demo_payment_enabled": false,
  "checkout_enabled": true
}
```

### Create Appointment Invoice

```http
POST /api/v1/billing/appointments/{appointment_id}/invoice
Authorization: Bearer {token}
```

Response:
```json
{
  "id": 1,
  "invoice_number": "CV-20261018-A1B2C3D4",
  "description": "Consultation with Dr. Smith",
  "amount_minor": 50000,
  "currency": "INR",
  "status": "unpaid",
  "appointment_id": 123,
  "created_at": "2026-10-18T10:00:00Z",
  "paid_at": null
}
```

### Create Checkout Order

```http
POST /api/v1/billing/checkout
Authorization: Bearer {token}
Content-Type: application/json

{
  "invoice_id": 1
}
```

Response (live mode):
```json
{
  "order_id": "order_MnT8xYz12345",
  "key_id": "rzp_test_YourKeyID",
  "amount_minor": 50000,
  "currency": "INR",
  "invoice_number": "CV-20261018-A1B2C3D4",
  "description": "Consultation with Dr. Smith",
  "mode": "live"
}
```

### Verify Payment

```http
POST /api/v1/billing/verify
Authorization: Bearer {token}
Content-Type: application/json

{
  "invoice_id": 1,
  "razorpay_order_id": "order_MnT8xYz12345",
  "razorpay_payment_id": "pay_AbC9xYz67890",
  "razorpay_signature": "9f8e7d6c5b4a3210..."
}
```

---

## Testing

### Run Automated Tests

```bash
# All billing tests
docker compose exec backend python -m pytest tests/test_billing_flow.py -v

# Appointment payment eligibility tests
docker compose exec backend python -m pytest tests/test_appointment_payment_eligibility.py -v

# Onboarding and demo payment tests
docker compose exec backend python -m pytest tests/test_onboarding_and_demo_payments.py -v
```

All tests use mocked Razorpay responses — no real API calls or charges.

### Frontend Build

```bash
docker compose exec frontend npm run build
```

Should complete without errors.

---

## Production Deployment Checklist

Before deploying to production with real payments:

1. **Switch to Live Mode Keys**
   - Get Live Mode keys from Razorpay Dashboard (requires business verification)
   - Update `.env` with `rzp_live_*` keys
   - Set `APP_ENV=production`

2. **Enable HTTPS**
   - Use TLS certificates (Let's Encrypt recommended)
   - Razorpay requires HTTPS for live mode

3. **Configure Webhooks**
   - Set up webhook URL with valid SSL certificate
   - Subscribe to payment and refund events
   - Configure `RAZORPAY_WEBHOOK_SECRET`

4. **Security Hardening**
   - Use secrets manager (AWS Secrets Manager, HashiCorp Vault, etc.)
   - Enable rate limiting
   - Set up monitoring and alerts
   - Configure backup and disaster recovery

5. **Compliance**
   - Review Razorpay's terms of service
   - Ensure DPDP Act compliance
   - Set up payment reconciliation process
   - Configure refund policy (`APPOINTMENT_REFUND_POLICY`)

6. **Testing**
   - Test complete payment flow with Live Mode test cards
   - Verify webhook delivery
   - Test refund flow
   - Load test checkout endpoint

---

## Support and Resources

- **Razorpay Documentation:** https://razorpay.com/docs/
- **Test Card Details:** https://razorpay.com/docs/payments/payments/test-card-upi-details/
- **Razorpay Dashboard:** https://dashboard.razorpay.com/
- **CareVoice Backend Code:** `backend/app/routes/billing_routes.py`
- **CareVoice Frontend Code:** `frontend/src/components/Billing.jsx`

---

## Current Implementation Status

✅ **Complete and Working:**
- Backend Razorpay order creation
- Backend payment signature verification
- Backend webhook handling (idempotent)
- Frontend Razorpay Checkout SDK integration
- Appointment payment eligibility logic
- Database models and migrations
- Invoice creation for appointments
- Patient-staff role separation
- Refund request flow
- Automated test coverage

⚠️ **Requires Configuration:**
- Razorpay Test Mode credentials (user must obtain from dashboard)
- Webhook secret (optional, only if using webhooks)

🚀 **Ready for Production (after checklist):**
- Complete payment lifecycle
- Security best practices implemented
- Error handling and retry logic
- Audit trail for all payment actions

---

**Last Updated:** 2026-10-18  
**Integration Version:** Production-ready, awaiting credentials

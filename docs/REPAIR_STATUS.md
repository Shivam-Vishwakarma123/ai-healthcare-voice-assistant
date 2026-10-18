# Repair status

## Baseline and architecture

- React/Vite frontend calls a FastAPI API; SQLAlchemy/Alembic persists accounts, appointments, invoices, payments, and webhook events. Docker Compose starts PostgreSQL and the app. See `docs/ARCHITECTURE.md`, `docs/END_TO_END_FLOWS.md`, and `README.md`.
- Frontend API wrapper: `frontend/src/services/api.js`; billing routes: `backend/app/routes/billing_routes.py`; Razorpay HTTP adapter: `backend/app/services/payment_service.py`; billing records: `backend/app/models/billing.py`.
- Initial worktree had an unrelated untracked `frontend/.vite/` directory. No reset or cleanup was performed.

## Confirmed findings and changes

- `Headers` instances lowercase header names. The API wrapper converted them directly to a plain object, so callers inspecting `Idempotency-Key` did not find the expected key. Header names are now converted to conventional casing before passing fetch options. Plain object headers remain unchanged.
- The Razorpay billing test assumed live payment mode, but Compose sets `PAYMENT_MODE=demo`. The test now explicitly selects `live`, matching its mocked-provider intent; application behavior was not changed.
- Payment lifecycle inspected: backend creates Razorpay orders from invoice amount/currency, persists a created payment, verifies checkout HMAC and provider-reported order/amount/currency/captured status, and can reconcile signed, deduplicated `payment.captured`/`payment.failed` webhooks. Demo mode has a separate owner-scoped simulated completion endpoint. No real payment or provider credential was used.

## Validation

- `frontend/tests/api.test.js`: 9 passed after the header fix.
- `backend/tests/test_billing_flow.py`: 1 passed after making its mode explicit (Docker test environment, mocked Razorpay transport).
- Full frontend suite: 16 passed, 0 failed; `npm run build` succeeded in Docker.
- Full backend `pytest -q` completed with exit success in Docker; output was truncated before the numeric summary, so exact count is not recorded here.
- Host lacked `npm` and pytest; Docker was used. One Starlette/httpx deprecation warning appeared in the billing test.

## Outstanding

- No live Razorpay sandbox integration was attempted; keys and an external provider callback were not available/needed for offline verification.
- The broad security, authentication/RBAC, appointment, RAG, migration, and deployment audit in the master prompt has not been completed. No production readiness conclusion is supported.
- The earlier broad audit phases (auth/RBAC, RAG and deployment) were not completed; do not treat them as production-reviewed.

## Appointment payment/refund follow-up

- Booking remains pay-later: the patient sees doctor/hospital/fee, but there is no configured advance-payment requirement. The clinic issues an invoice, and the patient pays it.
- Cancellation does not automatically refund. `APPOINTMENT_REFUND_POLICY` is configurable as `manual_review` (default) or `no_refunds`; no clinic-approved refund eligibility window is supplied by the repository.
- Added durable `payment_refunds` records and migrations `0013_payment_refunds` and `0014_invoice_refund_status`, Razorpay refund submission, provider webhook reconciliation, scoped refund history, and an admin Billing action. Refunds remain pending/processing until provider confirmation; timeout is not blindly retried. Cancelled unpaid appointment invoices and created payment attempts are made non-payable; a later provider capture is reconciled as paid and can be reviewed for refund.
- Development/test live mode now rejects non-test Razorpay key IDs. README documents the supplied test card (test mode only) and merchant settlement behavior; flow/API/database/run docs were updated.
- Targeted backend: 10 passed. Full backend: 98 passed, 0 failed (one Starlette/httpx deprecation warning). Full frontend: 16 passed, 0 failed; production build passed.
- Local development database upgraded through `0014_invoice_refund_status`; `alembic check` reported no new upgrade operations. Refund integration remains mocked; no card entry or provider sandbox call was performed.

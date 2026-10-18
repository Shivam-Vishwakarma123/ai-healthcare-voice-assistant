# Project completion audit

Updated 2026-10-17. This audit records repository evidence and distinguishes implemented behavior from remaining work.

## Verified architecture and current changes

- React/Vite SPA in `frontend/src/App.jsx`; page components in `frontend/src/components/`; FastAPI routes in `backend/app/routes/`; SQLAlchemy models/Alembic migrations under `backend/app/models/` and `backend/migrations/versions/`.
- Five roles are defined in backend auth and UI navigation. Billing is owner/hospital scoped; appointment access is checked in `_appointment_access`.
- Appointments book against server-validated slots and are idempotent. Current policy is pay-later: a hospital may issue an invoice at the clinician's stored fee; booking does not require advance payment.
- Root cause: appointment booking never created an invoice, and Pay Now was rendered only when an unpaid invoice already existed. Patients had no route to create one; only clinic staff could issue appointment invoices.
- Patient appointment responses now include the stored fee, invoice state, and latest payment state. A patient can explicitly start payment from an upcoming fee-bearing appointment; the API creates or returns one invoice at the doctor’s stored fee. No invoice/payment is created until the patient asks, and no charge occurs until checkout is completed.
- Billing configuration now reports provider-hosted checkout separately from demo simulation. A demo checkout no longer sets `online_payment_enabled`; the UI explains that demo mode has no card form and names the Test Mode setup path. Payment history exposes the invoice's verified `paid_at` time.
- Appointment UI distinguishes payment due/pending/failed/cancelled/paid/refunded, supports retry and status refresh, and links paid appointments to receipt details in Billing. Legacy appointments are not automatically charged.
- Razorpay live checkout has backend order creation, HMAC and provider-state verification, signed webhook deduplication, and the new manual-review refund flow. Demo payment remains a separate simulation.
- Theme preference now supports persisted Light, Dark, and System modes and applies before page rendering. The language switch updates the document language attribute; translations remain inline and incomplete.
- The recent worktree includes user-requested refund/schema/frontend changes plus the earlier API header regression fix. Existing untracked `frontend/.vite/` was present before this audit and remains untouched.

## Prioritized completion status

### P0 — Payment truth and billing

- Implemented: payment orders/verification/webhooks, cancellation of unpaid appointment invoices, provider refund API requests, durable refund rows, idempotency keys, refund webhooks, partial/full refund statuses, and role-scoped refund records.
- Implemented: refund policy setting `APPOINTMENT_REFUND_POLICY` (`manual_review` default or `no_refunds`). No clinic-approved time window is supplied, so no automatic refund eligibility claim is made.
- Unverified: real Razorpay test-mode checkout/webhook and provider settlement configuration. Automated provider calls are mocked.

### P1 — UI completeness and accessibility

- Existing UI already has reusable page, loading, empty, error, card, and dialog patterns; responsive CSS and language toggle exist.
- Gap: English/Hindi is mixed inline, not centrally catalogued, and several staff/payment strings remain English in Hindi mode.
- Partial: a browser screenshot review covered the public landing page in default and dark themes. Dark-mode readability overrides were adjusted from that review; authenticated routes, all roles, mobile breakpoints, keyboard flows, and console/network errors still need a broader pass.

### P1 — Appointment, AI and roles

- Implemented: patient/provider appointment booking, reschedule/cancel/history; backend server-scoped roles; deterministic emergency triage, optional RAG and provider abstraction.
- Partial: local browser verified a fictional patient can see Pay Now, the API-created invoice uses the stored fee, Billing opens, demo cancellation preserves the unpaid invoice, and existing paid appointments show View receipt. No live Razorpay checkout was verified.
- Remaining review: broader role/resource matrix, role-change/session revocation, doctor clinical data view, RAG grounding/privacy, and notification UX.

### P2 — Deployment and operations

- Compose, health checks, migrations, dev seed scripts, environment example, and developer guides exist. Local DB is migrated through `0014_invoice_refund_status` and Alembic reports no drift.
- Remaining review: full Compose/security configuration audit, production CORS/secrets posture, backup/restore, dependency/security scan, and operational refund reconciliation runbook.

## Latest automated evidence

- Backend: 99 passed, 0 failed; one Starlette/httpx deprecation warning (rerun 2026-10-17).
- Frontend: 24 passed, 0 failed; Vite 6.4.4 production build passed (rerun 2026-10-17).
- Docker Compose config passed; local PostgreSQL schema is at `0014_invoice_refund_status`; `alembic check` reports no new operations.
- Current local `.env` selects `PAYMENT_MODE=demo`; Razorpay key ID, secret, and webhook secret are absent. No real Razorpay credentials/card transaction or sandbox webhook was used. The local test booking was cancelled after verifying the flow; no payment was completed.
- Browser QA previously used the documented fictional patient account and test directory for the demo cancellation flow. This rerun inspected the landing page in English/Hindi and light/dark, verified appointment payment actions and the demo-only billing message as a synthetic patient, then signed out and restored English/System. It did not cover all roles, responsive breakpoints, or browser console/network logs.

## Next actions

1. Configure Razorpay Test Mode keys and webhook secret in the local `.env`, set `PAYMENT_MODE=live`, restart services, then verify a sandbox payment and webhook reconciliation; see `docs/FINAL_COMPLETION_REPORT.md`.
2. Centralize and complete the supported English/Hindi strings for primary navigation, appointment, billing, auth, and account actions.
3. Run a browser visual and interaction pass across all roles, mobile breakpoints, keyboard navigation, and browser console/network output.
4. Continue the auth/RBAC, healthcare AI, deployment and visual audit; do not label production-ready until provider sandbox evidence and approved refund terms are available.

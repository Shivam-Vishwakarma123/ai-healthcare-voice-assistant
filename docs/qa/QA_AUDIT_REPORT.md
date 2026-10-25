# CareVoice Health QA Audit

**Run date:** 2026-10-25  
**Overall result:** **PARTIAL PASS** — the local application is running, core UI journeys pass for all five roles, and the Test Mode checkout opens. Several write workflows and payment settlement cases remain untested.

## Runtime and data safety

- The working tree was already modified when this continuation began. Existing edits were preserved. This run additionally changed `backend/app/core/config.py`, `backend/tests/test_runtime_configuration.py`, and `frontend/test_all_roles_end_to_end.mjs`, and updated these QA documents.
- Docker CLI and daemon access were verified. Compose services were already running; the backend was restarted once to load the payment configuration guard. Final state: PostgreSQL and backend healthy, frontend healthy, Ollama healthy, and pgAdmin running.
- Verified local URLs: frontend [http://127.0.0.1:3000](http://127.0.0.1:3000), backend [http://127.0.0.1:8000](http://127.0.0.1:8000), PostgreSQL `127.0.0.1:5432`. `/api/v1/health/live` and `/api/v1/health/ready` returned **200** after restart.
- Runtime settings were inspected without displaying secrets: `APP_ENV=development`, database host `db` on the local Compose network, `PAYMENT_MODE=test`, and the configured Razorpay key ID has the `rzp_test_` prefix. The user's `.env` was not read into output or modified.
- The database contained 42 users, five marked RBAC test accounts, and one marked RBAC test hospital. The browser journeys used the repository's fictional `.test` demo identities and marked synthetic invoice. Running the repository's additive demo seeder reported **zero database rows created**.
- A source review found a legacy branch in `backend/app/seed_demo.py` that could attach synthetic records to an existing patient selected by a hard-coded identity without requiring `is_test_account`. That identity was not used in browser QA, and the live seeder reported zero database rows created. The branch now requires a marked test account. The seeder and its tests now write PDFs to temporary test directories. Thirteen PDFs that appeared in the repository during this audit were absent at the start and were removed; database rows and the pre-existing medical-document image were left untouched.
- A fixed-description ₹1 synthetic QA service invoice was created through the platform-admin UI only if absent. The invoice is still unpaid. Its Test Mode payment-order state is `created`; no payment details were entered and no payment was captured.

## Payment configuration and checkout

- **PASS:** Development and test configurations now reject `PAYMENT_MODE=demo` and `PAYMENT_MODE=live`; they require `PAYMENT_MODE=test`. The default and `.env.example` are also set to `test`. Production retains its separate explicit configuration path. A development/test key ID with a live prefix remains rejected.
- **PASS:** The Billing page displayed “Razorpay Test Mode ready” and the no-real-payment message. The Razorpay Test Mode `/billing/checkout` request returned **200**, and the hosted checkout iframe became visible.
- An existing `DEMO-SEED-V1` unpaid invoice was rejected with **409** because it belongs to a past appointment. This is the intended past-appointment payment guard. A marker-named manual service invoice was then created for the fictional demo patient and used for the Test Mode order.
- **NOT TESTED:** Payment completion, decline, timeout, server-side signature acceptance/rejection, and webhook handling. No payment was made. The browser automation could not identify the hosted checkout close button in the iframe; its browser session ended before payment details were entered. The invoice remains unpaid and the test order remains uncompleted.

## Executed checks

| Check | Result | Evidence |
|---|---|---|
| Docker / Compose runtime | **PASS** | Final `docker compose ps`: database, backend, and frontend healthy; optional Ollama healthy and pgAdmin running. |
| Frontend health | **PASS** | `http://127.0.0.1:3000/` loaded in the in-app browser and Playwright. |
| Backend health | **PASS** | Live and readiness endpoints returned 200 after backend restart. |
| Frontend unit tests | **PASS** | `npm test`: 13 test files, 13 passed, 0 failed. |
| Frontend production build | **PASS** | `npm run build` completed. Vite reported a 609.99 kB minified JS chunk, above its 500 kB advisory threshold. |
| Backend tests | **PASS** | `docker exec healthcare-backend pytest -q`: 168 passed, 3 deprecation warnings. |
| API smoke / access control | **PASS** | Authenticated provider directory, speech-to-text config, notifications, billing config/invoices/payments/refunds returned 200. Unauthenticated patient/provider/admin routes returned 401. |
| UI login, routing, refresh, logout | **PASS** | Patient, doctor, hospital staff, hospital admin, and platform admin logged in through the rendered sign-in form, reached their expected dashboard, persisted session on reload, and logged out. |
| Browser Console / API diagnostics | **PASS with dev noise** | Role journeys recorded 0 uncaught page errors and 0 HTTP API errors. Two provider fetches were reported as `net::ERR_ABORTED` during React Strict Mode effect cleanup; the corresponding provider list requests returned 200. |
| Demo seeder data boundary | **PASS after fix** | A legacy source path was found that did not require a marked test account. The path now requires `is_test_account=True`; a regression test covers an unmarked existing patient. The seed call reported zero database rows created. |
| Patient routes | **PASS (render smoke)** | Find Care, Appointments, Health Records, Symptom Check, Assistant, Health Profile, Notifications, and Billing rendered. Health Records displayed 12 tabs and six synthetic prescription records. Provider list responses were 200. |
| Responsive/theme/language | **PASS (patient overview scope)** | Light and Dark at 320, 375, 390, 430, 768, 1024, 1280, and 1440 px; no horizontal overflow. System theme followed emulated light and dark OS preferences. Hindi navigation/lang switch passed and Hindi dashboard had no overflow at 390 px. |
| Razorpay Test Mode | **PARTIAL PASS** | Runtime mode and test-key prefix verified; Billing UI configuration passed; hosted checkout opened. Payment completion/cancellation callback behavior was not verified. |
| Hosted checkout close/cancel | **BLOCKED** | Checkout iframe opened, but automation could not locate its close control. No card/UPI details were entered; invoice remains unpaid. |
| Payment success, decline, signatures, webhooks | **NOT TESTED** | No payment was completed; provider callback and signature paths were not exercised. |

## Role results

| Role | UI login and expected dashboard | Role-specific rendered checks | Browser errors |
|---|---|---|---|
| Patient | **PASS** — Overview | Health records/prescriptions, responsive/theme/language matrix, core route rendering, Billing Test Mode readiness | 0 JS, 0 HTTP API; 2 expected aborted duplicate provider requests |
| Doctor | **PASS** — Doctor workspace | Overview KPIs, seven workspace tabs, Ambient Scribe, Protocol Monitor | 0 JS, 0 HTTP API |
| Hospital staff | **PASS** — Provider dashboard | Reception queue and operations KPIs | 0 JS, 0 HTTP API |
| Hospital admin | **PASS** — Administration | Management workspace and sections | 0 JS, 0 HTTP API |
| Platform admin | **PASS** — Administration | Management workspace and sections | 0 JS, 0 HTTP API |

Screenshots from the current browser run are in the ignored `frontend/qa-screenshots/` folder: role dashboards, patient 320px Dark and 1440px Light, and Billing Test Mode.

## Coverage still not established

**NOT TESTED:** booking and schedule conflicts; appointment confirmation, rescheduling, cancellation, receipts and persistence; profile updates/deletion; notification preference writes; symptom form submission and clinical safety outcomes; AI chat responses, voice recording/transcription, microphone permission and RAG citations; clinical notes, prescriptions, report generation and signing; invoice PDF/refund mutation; checkout success/failure and signature/webhook cases; admin user provisioning/deactivation; cross-patient ownership and cross-hospital tenant isolation; full Hindi translation and toast rendering across every route; all roles at every viewport; keyboard/focus and screen-reader behavior.

The browser checks were real local UI checks, but route rendering should not be read as proof that each listed workflow's mutations and failure cases work end to end.

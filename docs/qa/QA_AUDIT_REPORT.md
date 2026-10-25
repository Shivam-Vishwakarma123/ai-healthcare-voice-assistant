# CareVoice Health QA Audit

**Run date:** 2026-10-25  
**Result:** **PASS for the requested UI audit** — all five roles and 27 signed-in views were checked across English/Hindi, Light/Dark/System themes, and responsive widths. Patient core views and interactive tabs also passed focused workflows. **NOT TESTED:** clinical/admin writes, live AI/voice outcomes, hosted checkout outcomes, and assistive technology behavior.

**Status counts:** **PASS** — frontend 13/13, backend 168/168, production build, 436 role/view/theme/language/responsive layout checks, and focused patient/doctor/admin workflows. **FAIL** — no product failure confirmed in completed checks. **BLOCKED** — no eligible unbilled synthetic hospital appointment for creating another scoped invoice. **NOT TESTED** — live checkout outcomes, clinical/admin mutation workflows, and assistive technology behavior.

## Runtime and data safety

- **PASS:** The working tree was clean at audit start. Existing project files and database contents were preserved.
- **PASS:** `docker compose ps` showed PostgreSQL, backend, and frontend healthy; Ollama was healthy and pgAdmin was running. Frontend `http://127.0.0.1:3000/` and backend `/api/v1/health/live` both returned HTTP 200.
- **PASS:** Browser checks used the repository's ignored local QA credential file for marked synthetic QA accounts. No credentials or environment values were printed in this report.
- **PASS:** The app exposed “Razorpay Test Mode ready”; the patient had a marked synthetic unpaid invoice with an enabled Pay now action. No checkout was opened and no payment was submitted in this run.
- **BLOCKED:** Hospital staff had no unbilled synthetic appointment available to create a new hospital-scoped test invoice. The audit script now skips that write and records the limitation rather than creating an unrelated manual invoice.

## Route and role inventory

The frontend uses a single React app with state-based workspace navigation rather than separate URL routes for each signed-in page. Public path states in `frontend/src/App.jsx` include `/`, `/reset-password`, and `/setup/administrator`. The available signed-in workspace views discovered in source are:

| View | Role availability | Browser result |
|---|---|---|
| Overview / patient dashboard | Patient; provider dashboard is rendered for non-patients if selected | **PASS** patient render and refresh |
| Find care | Patient and staff roles | **PASS** patient render; provider directory requests returned successfully, with two React Strict Mode aborts during cleanup |
| Appointments | Patient and staff roles | **PASS** patient render smoke |
| Health records / Medical records alias | Patient-facing | **PASS** patient 12-tab view; six prescription cards rendered |
| Symptom check | Patient-facing | **PASS** patient render smoke; form outcomes not submitted |
| CareVoice assistant | Patient-facing | **PASS** render smoke; no AI chat or voice request submitted |
| Health profile | Patient-facing | **PASS** render smoke; profile writes not submitted |
| DPDP Privacy | Patient-facing | **PASS** patient view across all themes/languages and responsive widths; Hindi labels reviewed at 320 px |
| Notifications | Patient-facing | **PASS** render smoke; preference writes not submitted |
| Billing | Patient, hospital staff/admin, platform admin | **PASS** Test Mode status and synthetic unpaid invoice displayed; no checkout completion |
| Provider dashboard | Hospital staff and hospital admin; role-dependent for other providers | **PASS** hospital staff and hospital admin landing views |
| Doctor workspace | Doctor | **PASS** overview, seven tabs, Ambient Scribe, and Protocol Monitor render |
| Administration | Hospital admin and platform admin | **PASS** management workspace render for both roles |
| Sign in / registration | Public | **PASS** used to sign in through UI; registration validation not exercised |
| Password recovery and initial administrator setup | Public paths above | **NOT TESTED** |

## Browser results

- **PASS:** Patient overview was checked at 320, 375, 390, 430, 768, 1024, 1280, and 1440 px in Light and Dark: 16 combinations, no horizontal overflow. Rechecked after the updated slate dark palette and typography changes.
- **PASS:** Patient dashboard followed emulated System Light and Dark preferences. Hindi navigation was toggled and the Hindi dashboard had no overflow at 390 px.
- **PASS:** Patient, doctor, hospital staff, hospital admin, and platform admin sign-in, role landing, refresh persistence, and logout were exercised. The platform admin passed on an isolated retry after a timeout during the first full run.
- **PASS:** The final browser run recorded zero uncaught page errors and zero failed API responses on all five roles. Two provider requests were aborted during React Strict Mode cleanup; corresponding provider requests returned successfully.
- **PASS:** The all-role matrix checked 436 page/theme/language/width combinations with zero off-screen content, empty views, failed API responses, or uncaught page errors. Each of the 27 role views was checked at 320, 430, 768, and 1440 px; patient Overview additionally used 375, 390, 1024, and 1280 px. Every view was checked in English Light and Hindi Dark plus explicit Light, Dark, and OS-following System in both languages.
- **PASS:** Patient Overview and DPDP Privacy were visually inspected at 320 px in Hindi Dark. Health-record navigation activated all 12 tabs; dashboard vitals metric and time-range controls were exercised. The appointment receipt opened and closed in place. No payment or clinical record was submitted.
- **NOT TESTED:** Keyboard-only navigation, screen reader behavior, modal focus trapping, live toast appearance, complete translation review of every dynamic/server-generated message, and mutation/API authorization workflows.

## Razorpay and billing

- **PASS:** Runtime Billing UI reported Razorpay Test Mode ready. A marked synthetic unpaid invoice displayed an enabled Pay now action.
- **PASS (automated):** Backend payment, signature, webhook/idempotency, and Test Mode suites are included in the passing backend suite (168 tests total). These use test fixtures/mocks; they do not represent a live provider settlement.
- **NOT TESTED:** Hosted checkout open/cancel, provider decline, successful test payment, payment signature acceptance/rejection against Razorpay, and live webhook delivery. No payment was submitted.
- **BLOCKED:** No unbilled synthetic hospital appointment was available to issue another scoped invoice during this run.
- **Security note:** Payment is not marked paid by opening checkout; server verification and webhook behavior were not manually exercised in this browser run.

## Commands and outcomes

| Command/check | Result |
|---|---|
| `git status --short` at start | **PASS** — clean working tree |
| `docker compose ps` | **PASS** — database, frontend, backend healthy; Ollama healthy |
| Local frontend and backend health requests | **PASS** — HTTP 200 / HTTP 200 |
| `cd frontend && npm test` (after UI fixes) | **PASS** — 13 files, 13 passed, 0 failed |
| `cd frontend && npm run build` (latest visual fixes) | **PASS with advisory** — build succeeded; 613.52 kB minified JS chunk exceeds Vite's 500 kB advisory threshold |
| `docker compose exec -T backend pytest -q` | **PASS** — 168 passed, 3 deprecation warnings, 59.31s |
| `node test_all_roles_end_to_end.mjs` (Playwright, escalated for browser access) | **PASS for patient visual recheck** — patient routes, notification list, and viewport/theme matrix passed; checkout remained unpaid |
| `node audit_all_roles_ui_matrix.mjs` (Playwright) | **PASS** — 436 checks; five roles, 26 views, English/Hindi, Light/Dark/System, no layout or runtime/API findings |
| `node verify_all_pages_and_viewports.mjs` (Playwright) | **PASS** — ten patient widths, all 12 record tabs, dashboard charts/ranges, receipt modal, all patient pages, doctor workspace, hospital administration; zero page errors |
| `CV_QA_ROLE_FILTER=patient CV_QA_VIEW_FILTER='DPDP Privacy' node audit_all_roles_ui_matrix.mjs` | **PASS** — 16 focused layout/theme/language checks after Hindi copy and secure-PIN default fixes |
| Playwright audit without escalation | **BLOCKED by sandbox** — Chrome exited with SIGTRAP/operation-not-permitted; the same audit ran with approved local browser access |

## Confirmed fixes

- `frontend/src/healthcare.css`: added explicit Noto Sans Devanagari and common Windows Indic fallback families to the shared body/display font stacks.
- `frontend/src/App.css`: corrected an invalid shadow color value on primary buttons.
- Dark theme surface tokens now use neutral slate shades while green remains the action/selection accent. Body text uses Inter with Noto Sans Devanagari fallback; insight and health-record preview copy is more readable.
- Notifications now render as separated, responsive rows with aligned channel/status badges.
- Fixed 320 px clipping in patient insight/record cards and DPDP privacy panels by allowing their responsive grids to shrink below the desktop 320 px card minimum.
- DPDP Privacy Hindi mode now localizes the visible status, share-link, verification, guide, and export controls. Removed the prefilled `1234` share PIN; patients must choose their own 4–8 digit PIN.
- `frontend/test_all_roles_end_to_end.mjs`: invoice setup now uses the hospital staff account and only selects an unbilled hospital appointment. It skips the invoice write when no eligible appointment exists. This fixed the harness's incorrect assumption that a manually entered patient ID was billable for that hospital.

## Remaining issues and exact next steps

- **P2 — Bundle size:** Vite warns that the main JS chunk is 613.52 kB minified. Reproduce with `cd frontend && npm run build`; inspect lazy loading before changing bundling.
- **P1 — Payment outcome coverage:** use Razorpay Test Mode only. Verify checkout close/failure leaves the invoice unpaid, and test server signature/webhook behavior with provider test tooling or fixtures. The current run did not submit a payment.
- **P1 — Scoped synthetic billing fixture:** create or identify a marked synthetic appointment without an invoice at the hospital assigned to the QA staff account; rerun the role script to test checkout initialization.
- **P2 — Accessibility follow-up:** keyboard focus, modal focus trapping, toast announcements, contrast sampling, screen-reader landmarks, and form validation need a dedicated assistive technology audit.
- **P2 — Mutation/API coverage:** exercise appointment booking/conflicts/cancel/reschedule, profile and notification writes, symptom assessment, AI response/voice, clinical note/prescription workflows, refunds, admin mutations, and cross-patient/tenant access using isolated synthetic records.

## Files changed in this run

- `frontend/src/App.css`, `frontend/src/healthcare.css` — readable Inter/Devanagari font stack, neutral slate dark surfaces, green action accents, valid primary action shadow, and responsive privacy card grid.
- `frontend/src/patientDashboard.css` — more readable insight and record preview typography; narrow cards now shrink correctly.
- `frontend/src/components/DPDPPrivacyCenter.jsx` — localized Hindi privacy UI and no default/predictable share PIN.
- `frontend/src/components/PortalScreens.jsx` — semantic notification row structure.
- `frontend/test_all_roles_end_to_end.mjs` — role-correct invoice fixture setup and updated visual screenshots.
- `frontend/audit_all_roles_ui_matrix.mjs`, `frontend/verify_all_pages_and_viewports.mjs` — exhaustive responsive/theme/language and focused workflow browser checks.
- `docs/qa/QA_AUDIT_REPORT.md`, `docs/qa/UI_UX_AUDIT.md`, `docs/qa/REPAIR_BACKLOG.md` — current run findings and evidence.

## Screenshot-driven follow-up (2026-10-25)

- Fixed appointment row alignment by separating payment details from receipt controls, adding stable wide-screen columns, responsive action grids, and Hindi labels for appointment statuses.
- Fixed mobile clinical-record modal collapse: the narrow layout now reserves a readable report scroller, compacts the record header, gives actions a two-column layout, and keeps the footer visible. Verified its single-scroll behavior at 320, 768, and 1440 px.
- Fixed symptom form label/hint spacing and removed the narrow desktop-width cap from its responsive card. Aligned assistant voice and chat panels and replaced raw Ollama/Docker model errors with a localized safe fallback.
- Browser audit now opens and closes provider, booking, receipt, history, and reschedule dialogs at mobile/tablet/desktop widths; activates all 12 health-record tabs; submits synthetic symptom and assistant prompts; and checks doctor/admin landing views. Result: **PASS, zero page errors**.
- Re-ran `node audit_all_roles_ui_matrix.mjs`: **436 checks, 27 role views, five roles, zero visual findings, zero page/API errors** across English/Hindi, Light/Dark/System, and responsive widths.
- Re-ran `cd frontend && npm test`: **13 passed, 0 failed**. `npm run build` succeeds; the 614.48 kB minified JS chunk remains above Vite's 500 kB advisory threshold. `git diff --check` passes.

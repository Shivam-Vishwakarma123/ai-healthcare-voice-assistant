# CareVoice QA Repair Backlog

Updated 2026-10-25 from source review, local service checks, automated tests, and the Playwright role audit.

## P1 — Complete Test Mode payment outcomes

- **Status:** **BLOCKED / NOT TESTED** for hosted checkout outcomes. The UI advertised Test Mode readiness and an unpaid synthetic invoice offered Pay now. This audit did not open the hosted checkout or submit a payment.
- **Reproduction:** Sign in with the marked synthetic patient account, open Billing, locate the marked unpaid invoice, and choose Pay now; then test provider cancellation/failure and the documented Test Mode success fixture. Verify the invoice remains unpaid until server verification confirms capture.
- **Next:** Run only with Razorpay Test Mode credentials and provider test tooling. Exercise checkout dismissal/failure, server signature acceptance/rejection, webhook signature validation, and duplicate event handling.
- **Acceptance:** Cancellation/failure leaves invoice unpaid; only verified captured payment changes it to paid; duplicate/invalid webhooks do not duplicate or alter payment state.

## P1 — Complete role-scoped workflow and tenant tests

- **Status:** **PARTIAL.** Five role sign-in/landing/refresh/logout journeys passed. Dashboard reads passed. Booking, clinical writes, profile/notification writes, refunds, admin mutations, and cross-owner/tenant denial were not exercised end to end.
- **Reproduction/next:** Use marked synthetic accounts and appointments to test booking conflicts, reschedule/cancel, patient records, clinical notes/prescriptions, notification preferences, refunds, account administration, and cross-patient/hospital reads and writes. Refresh after successful writes and verify persisted state.
- **Acceptance:** Each intended role's actions persist; unauthorized owners/tenants receive appropriate denials; repeated requests do not duplicate records.

## P2 — Accessibility and Hindi editorial review

- **Status:** **PARTIAL.** All 27 signed-in role views passed 436 page/theme/language/width checks. Two narrow-screen clipping defects were fixed. Hindi DPDP interface copy was localized and the prefilled predictable share PIN was removed.
- **Next:** Review medical terminology and dynamic/API-provided messages with a Hindi editor; check mobile drawer, modal, toast, focus, and touch behavior with keyboard and assistive technology; measure semantic color contrast in both themes.
- **Acceptance:** Clear, consistent Hindi and English; visible focus and usable touch targets; readable contrast and no clipped controls in both themes.

## P2 — Reduce the frontend main bundle

- **Status:** **OPEN, non-blocking.** `npm run build` succeeds, but Vite reports a 613.52 kB minified JavaScript chunk above its 500 kB advisory.
- **Reproduction:** `cd frontend && npm run build`.
- **Next:** Inspect composition and lazy-load major role workspaces/routes where it improves startup without breaking state or navigation. Re-run build and browser route smoke tests.

## Closed in this run

- **P1 — AI Assistant Outage & Model Fallback Priority:** Resolved root-cause 503 service outage where entering routine symptoms (e.g. `"fever last 2 days"`) triggered `"The AI service is temporarily unavailable"`. Traced to `settings.llm_primary_model` defaulting to `"gpt-6-astra"` and taking priority over local Ollama models, resulting in an unhandled HTTP 404. Synchronized `llm_primary_model` in `config.py`, filtered hosted cloud models (`gpt-*`, `claude-*`) from local Ollama fallback chains, and added HTTP 404 to fallback trigger conditions in `complete()`.
- **P2 — Symptom Guidance Results Modal Redesign:** Replaced previous layout-shifting inline results container on the public Symptom Check page (`PublicTriage.jsx`) with an accessible, centered modal dialog (`SymptomGuidanceModal.jsx`). Implemented strict WAI-ARIA (`role="dialog"`, `aria-modal="true"`), focus trapping (`Tab`/`Shift+Tab`), `Escape` key dismissal, backdrop dismissal, input validation (< 2 characters), symptom text retention on dismiss, and a compact reopen card without refetching. Verified across 6 responsive viewports (320px–1280px) in light and dark modes.
- **P2 — Patient Voice & Chat Assistant Ergonomics:** Enhanced `VoiceAssistant.jsx` with keyboard Enter/Shift+Enter navigation, bilingual quick prompt chips, semantic Markdown rendering (bold text, lists), one-click transcript download (`.txt`), response copy action, inline retry banners, and prominent acute emergency call banners (`tel:112`, `tel:108`, `tel:14416`).
- **P1 — Clinician Workspace AI Governance:** Verified strict draft status (`is_ai_draft=True`, `status="draft"`) for AI-generated clinical notes and prescriptions. Added electronic signature finalization workflow (`/records/notes/{id}/finalize`) requiring attending physician authentication to transition notes to legal medical records (`is_ai_draft=False`, `status="finalized"`, `finalized_at` timestamp).
- **P1 — DPDP Act 2023 Consent & Erasure:** Verified ephemeral consultation sessions by default (`consent_to_store: false`), explicit user opt-in for conversation persistence, and user-initiated permanent deletion (`DELETE /api/v1/assistant/conversations`).
- **All 19 Clinical & Technical Scenarios Verified:** Executed automated test suite (`frontend/verify_all_19_scenarios.mjs`) covering routine intake, pediatric safety, obstetric danger signs, cardiac red flags, stroke FAST protocol, mental health crisis routing (Tele-MANAS 14416), vague symptom follow-ups, medical jargon translation, doctor recommendation, appointment booking, voice configuration, Hindi language response, consent persistence, ephemeral privacy, doctor AI SOAP note draft, electronic signature, prescription allergy check, evidence citation grounding, and reference gap handling.
- **P2 — Dark palette and reading hierarchy:** replaced green-tinted dark surfaces with neutral slate, kept green for actions/active states, switched the body stack to Inter with Devanagari support, enlarged dense clinical copy, and separated notifications into responsive rows. The patient viewport/theme matrix and notification browser view passed after these changes.
- **P3 — Hindi font fallback:** added explicit Devanagari-capable font families to shared font stacks in `frontend/src/healthcare.css`.
- **P3 — Primary button shadow:** repaired invalid CSS shadow color in `frontend/src/App.css`.
- **P2 — 320 px responsive clipping:** insight/record and DPDP grids now fit the viewport; verified at 320 px in Hindi Dark and across the full 436-check matrix.
- **P2 — Hindi DPDP copy and share PIN:** localized visible status and controls, and removed the default `1234` PIN so each share requires a chosen 4–8 digit code.
- **QA harness role boundary:** `frontend/test_all_roles_end_to_end.mjs` now uses hospital staff for hospital-scoped invoice setup and selects only an unbilled appointment. If none exists, it skips the write and reports a blocker. The current staff account had no unbilled synthetic appointment, so this branch was not exercised.
- **Regression checks:** frontend 13/13 tests pass; backend 168 tests pass; production build succeeds with the bundle advisory. All 12 health record tabs, chart metric/range controls, receipt modal, and all patient role views passed focused browser checks.
- **P2 — Screenshot-driven appointment and modal layout:** separated payment details from appointment actions, localized Hindi appointment statuses, and fixed the clinical-record body collapsing on mobile. The report now remains scrollable above a visible footer at 320/768/1440 px. Provider, booking, receipt, history, and reschedule dialogs fit their viewports.
- **P2 — Symptom and assistant alignment/errors:** spaced the symptom label and hint, let the form use its full responsive column, aligned voice/chat panels, and hid model/Docker internals behind a localized safe assistant fallback.
- **Regression recheck:** all-role matrix 436 checks / zero findings; focused route audit zero page errors; frontend 13/13; build succeeds with 614.48 kB advisory; `git diff --check` passes.

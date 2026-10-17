# End-to-end workflows

These are source-backed flows through the current implementation. The principal React shell is `frontend/src/App.jsx`; routes are registered in `backend/app/main.py`. For the full list of request contracts, see [API reference](./API_REFERENCE.md).

## Workflow A: Patient registration and login

1. `AuthScreen` collects name/email/password (registration) or email/password (login).
2. `App.submitAuth` calls `POST /api/v1/auth/register` or `/login` via `apiRequest`.
3. `RegisterIn`/`LoginIn` normalizes and validates email and bounds password length. `register()` always sets role `patient`; the client cannot select a privileged role.
4. `hash_password()` stores the Argon2 hash. `issue_access_token()` creates an `auth_sessions` row and returns an HS256 JWT with expiry and session ID. Audit event is committed with the account/login.
5. FastAPI returns `{access_token,token_type,expires_in,user}`. The browser caches token and non-secret user details in `localStorage`; the token is short-lived (default 20 minutes).
6. On token change/reload, `App` calls `/auth/me` and, for patients, `/patients/`. It selects Overview for patients, Provider dashboard for other roles. A patient-profile record is separate; a new account may have no profile.
7. Authenticated API calls use `Authorization: Bearer <token>`. `get_current_user` verifies JWT and persisted session, checks revocation/expiry/user active/current role, and validates clinician/hospital provisioning.
8. Logout calls `/auth/logout` to revoke the current session, then clears the browser keys. Password-reset request/confirm use one-time hashed tokens and configured SMTP.

Relevant files: `frontend/src/App.jsx`; `frontend/src/services/api.js`; `backend/app/routes/auth_routes.py`; `backend/app/auth/security.py`; `backend/app/models/user.py`; `backend/app/models/security.py`.

**Failure behavior:** duplicate email is 409; malformed inputs are 422; invalid credentials are 401; unassigned managed roles may be 403; absent SMTP makes reset request 503. The app does not create a `Patient` row automatically on registration.

## Workflow B: Hospital and doctor discovery

1. Patient signs in; `CareDirectoryPage` mounts from `App`'s "Find care" navigation.
2. It sends paginated requests in parallel: `GET /providers/doctors?limit=12&offset=...&search=...` and `GET /providers/hospitals?...`.
3. `list_doctors`/`list_hospitals` require authentication and filter to verified records (doctors are also active); query parameters support specialty, city, language, consultation type, text search, and paging.
4. Responses include `{items,total,limit,offset}`. React shows current page and retains query/page state. Requests are abortable to avoid stale results.
5. Clicking a profile expands details inline. Details are lazily fetched from `/providers/doctors/{id}` or `/hospitals/{id}` and cached by entity type/id; loading, retry and error states are per-profile.
6. Optional recommendations post specialty/city/language/consultation type and symptom text to `/providers/recommendations`. The score is a configured weighted match, not a diagnosis, and returned recurring schedules are not real-time available slots.

No fake cards or synthetic schedule entries are generated in the UI. Only database profiles passing verification filters are returned.

## Workflow C: Appointment booking and confirmation

1. Patient selects a verified doctor, consultation type and available date. The UI calls `GET /providers/doctors/{id}/available-slots?day=YYYY-MM-DD&consultation_type=...`.
2. Backend obtains active published recurring schedules; interprets local wall time using each schedule's IANA zone; emits 30-minute starts within the requested IST date and in the future; subtracts slot starts held in `appointment_slot_locks`.
3. Patient chooses a slot and optionally adds notes. UI submits `POST /providers/appointments` with a timezone-aware `scheduled_for` and `Idempotency-Key`.
4. Pydantic rejects timezone-naive dates, invalid consultation type, overlong notes or invalid IDs. The route requires patient role, revalidates doctor/hospital verified/active state and slot/schedule, computes a stable request fingerprint, and checks prior command with same actor/key.
5. Within a transaction it creates `appointments` (`scheduled`), slot lock, idempotency command and `appointment_events` record; it records audit outcome. Unique `(doctor_id,slot_start)` and command-key constraints prevent concurrent duplicates. Constraint conflict is rolled back and returned as 409; same exact command replay returns the existing appointment.
6. On success, the API returns `AppointmentRead`. `CareDirectoryPage` verifies the response has an ID and `scheduled` status, stores it as recent booking, and `AppointmentsPage` merges it into the visible list; a normal refresh refetches server state.
7. Clinician/staff/admin can confirm; authorized participants/providers can cancel or reschedule. These mutations add history events and update slot locks. `/appointments/{id}/history` returns event rows. Access helpers check patient ownership, linked doctor, hospital tenant, or platform-admin privilege.

When booking fails, retain the typed API status/message. Do not assume a displayed slot is reserved, silently change the date, or retry with a new idempotency key for the same logical request.

## Workflow D: Billing and demo payments

1. `Billing` loads `/billing/invoices`, `/config`, and `/payments`; staff/admin also load `/billable-appointments`.
2. Authorized staff can create service invoice by entering patient ID, description, amount in UI currency units; UI converts to integer `amount_minor`. For an appointment-linked invoice, backend loads appointment and doctor and uses `Doctor.fee_minor`; the client cannot override that value. Unique appointment invoice constraint prevents duplicate appointment invoices.
3. Patient chooses an invoice and posts only `{invoice_id}` to `/billing/checkout`. Backend checks ownership, unpaid status, mode and loads amount/currency from DB.
4. In `PAYMENT_MODE=demo`, backend creates a pending `Payment` with a demo-prefixed order ID and returns `mode:"demo"`. UI opens a modal explicitly stating no real money, provider call, card or bank details; user selects simulated success/failure/cancel.
5. `/billing/demo/complete` checks current owner, demo order, attempt still pending and allowed outcome. Success marks payment/invoice paid and returns a simulated reference; failed/cancelled attempts remain unpaid. Replays cannot settle an already completed attempt. This is local database state only—not a receipt or transfer.
6. In `PAYMENT_MODE=live`, `_payment_service()` creates a Razorpay order using database amount. Frontend Checkout completes; it submits provider IDs/signature to `/billing/verify`. Backend verifies HMAC and queries Razorpay for captured status, matching order, amount and currency before setting invoice/payment paid. The optional signed webhook performs separate idempotent processing.

No real payment gateway call was made as part of the documentation. Automated tests mock provider HTTP; live mode requires private backend keys, webhook setup and reconciliation. Never add card fields to CareVoice or treat a demo reference as proof of payment.

## Workflow E: AI symptom analysis and voice

### Deterministic triage

`PublicTriage` posts symptom text to public `/assistant/triage`; `evaluate_triage` normalizes text and checks a hard-coded list of red-flag terms including chest pain, breathing difficulty, stroke signs, severe bleeding, seizure, loss of consciousness, anaphylaxis, poisoning, head injury, selected pregnancy/infant concerns, and self-harm phrases. It also recognizes selected Hindi/Hinglish phrases and prompt-injection patterns. The response includes urgency/category/summary/guidance/contact numbers/flags.

This matching is limited and can miss synonyms, language variants, context, or atypical symptoms. A non-emergency result does not rule out an emergency. The UI directs users to 112/108 and states this is not diagnosis.

### Chat and speech

1. `VoiceAssistant` requests `/assistant/speech-to-text/config`. With browser provider, it calls browser `SpeechRecognition`/`webkitSpeechRecognition`; with a configured remote provider, it records via `getUserMedia`/`MediaRecorder` then uploads multipart audio to `/assistant/speech-to-text`.
2. User must review/confirm transcript before sending. Audio size/type and provider availability are bounded. The browser stops microphone tracks when recording ends or component unmounts.
3. Typed or confirmed transcript is appended to component memory and last 20 messages are sent to authenticated `/assistant/chat`. Chat is not persisted in this app database.
4. Backend validates final message is user role, runs triage and personal-treatment/prompt safety checks before model use. If RAG enabled, it retrieves public-health chunks, rejects missing embedding service, and avoids synthesizing conflicting retrieved guidance.
5. `get_llm_provider()` sends a constrained structured request to local Ollama by default or configured compatible provider. The result is validated and safety-screened; citations are attached from retrieved source metadata. Browser `speechSynthesis` is available when user presses speak.

Hosted model/transcription providers receive content/audio when enabled. Review their privacy/retention policies. No model response is a clinical diagnosis; emergency phrases are not exhaustive.

## Workflow F: Role-based administration

`App` fetches `/auth/me`; `role` controls visible navigation. Patients see overview, find-care, appointments, symptom check, assistant, profile, notifications, and billing. Provider roles see provider dashboard and permitted navigation; administration is rendered for platform/hospital admins.

Backend roles are `patient`, `doctor`, `hospital_staff`, `hospital_admin`, and `platform_admin`. `get_current_user` reloads role from DB, compares with JWT role and validates provider assignment. Each route then uses `require_roles` or explicit ownership/hospital predicates. Hospital admin is tenant-scoped; platform admin can access cross-hospital data.

`AdminManagement` creates managed doctor/hospital-admin accounts, activates/deactivates or changes eligible managed roles, sees aggregate counts and operational lists. `ProviderDashboardPage` handles hospital/doctor profile/schedule management and platform verification review. API checks prevent patient accounts from becoming admins through public registration. A hidden button alone would never protect one of these actions.

## Workflow G: Dashboard data refresh

Most dashboards use a mount effect to fetch snapshots. `DashboardPage` uses `Promise.allSettled` for appointments/doctors/hospitals and reports per-source failure; `AdminManagement` loads several admin endpoints and `load()` is reused after mutations. `Billing` reloads after create/checkout completion. `AppointmentsPage` reloads after actions and merges a newly booked appointment immediately.

There is no WebSocket, event bus, global query cache, or continuous polling. Another user's changes appear after a refresh or component re-fetch. A count can be stale if a page is left open; diagnose by comparing endpoint response, role/tenant scope and UI calculation.

For development commands and failure diagnosis see [Run and debug](./RUN_AND_DEBUG.md).

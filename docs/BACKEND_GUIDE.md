# Backend guide

The API is a Python/FastAPI modular monolith. The running app is created in `backend/app/main.py`; route modules are registered beneath the configured `/api/v1` prefix. Request handlers use SQLAlchemy sessions from `app.core.database.get_db`, and response models serialize ORM objects or explicit dictionaries.

## Request lifecycle

```text
HTTP request
  -> CORS / FastAPI routing
  -> Pydantic path, query, header, body validation
  -> dependencies (get_db, get_current_user, require_roles)
  -> route-level ownership / hospital scope checks
  -> service/controller/repository or route's SQLAlchemy operations
  -> commit / rollback
  -> response model serialization
```

`main.py` imports `app.models` so SQLAlchemy mappings are registered; configures credentialed CORS for configured origins and methods; includes six routers; exposes `/`, `/api/v1/health/live`, `/api/v1/health/ready`, and `/api/v1/health` (the latter is a readiness alias). The readiness handler executes `SELECT 1`, returning 503 if the database is unavailable. A last-resort exception handler logs an exception and returns a generic 500 body; it does not expose the traceback to clients.

## Module responsibilities

| Module | Main responsibility |
| --- | --- |
| `app/core/config.py` | Pydantic Settings reads environment and `.env`; validates production JWT/database/payment settings, payment mode, provider limits, CORS origin syntax, optional SMTP/SMS pairing, and provider-match weights. |
| `app/core/database.py` | `Base`, SQLAlchemy engine (`pool_pre_ping`, `pool_recycle`), `SessionLocal`, and generator dependency `get_db`; rolls back when an exception escapes a request. |
| `app/auth/security.py` | `hash_password`, `verify_password`, `issue_access_token`, `get_current_user`, `require_roles`, session revocation. Uses Argon2 through pwdlib and HS256 JWTs backed by `auth_sessions`. |
| `app/auth/rate_limit.py` | Applies configured limits to authentication operations. |
| `app/routes/auth_routes.py` | Bootstrap, patient registration/login/logout, password reset, `/me` and contact update. Password-reset email is optional SMTP. |
| `app/routes/patient_routes.py` | Patient profile CRUD; delegates through `PatientController` → `PatientService` → `PatientRepository`. |
| `app/routes/provider_routes.py` | Verified directory, recommendations, provider dashboards/profile/schedule/review, available slots, appointment lifecycle and history. Performs SQLAlchemy operations directly in the route module. |
| `app/routes/assistant_routes.py` | Speech configuration/transcription, deterministic triage, RAG search, and AI chat orchestration. |
| `app/routes/billing_routes.py` | Invoice ownership/eligibility, checkout, demo completion, live payment verification, webhooks, audit and notification calls. `_payment_service()` supplies the `PaymentService` protocol implementation for Razorpay. |
| `app/routes/admin_routes.py` | Role- and hospital-scoped account provisioning, overview counts, account changes, appointment/payment/audit/notification views. |
| `app/services/patient_service.py` | Patient duplicate and ownership rules. |
| `app/repositories/patient_repository.py` | Owner-filtered SQLAlchemy patient query and CRUD. |
| `app/services/payment_service.py` | `PaymentService` protocol and `RazorpayPaymentService` HTTP adapter; verifies returned order fields and turns provider/network failures into `PaymentProviderError`. Demo flow remains local in billing routes. |
| `app/services/llm_provider.py` | Provider abstraction and structured chat completion for Ollama/OpenAI-compatible configurations; validates structured model output. |
| `app/services/assistant_safety.py`, `triage_service.py` | Deterministic checks and safety response shaping before the AI call. |
| `app/services/rag_service.py`, `embedding_provider.py` | Sanitizes/chunks text, embeds/searches knowledge records, and prepares source metadata/citations. |
| `app/services/speech_to_text.py` | Browser/configured-provider selection, endpoint availability and bounded audio transcription. |
| `app/services/audit_service.py`, `notification_service.py` | Audit row creation and optional generic sign-in notification dispatch/outcome persistence. |
| `app/core/exceptions.py`, `email_validation.py` | Shared domain exceptions and normalized email validation. |

This layering is strongest for patient profile CRUD. Other routes intentionally own more orchestration and persistence logic. Follow the local domain pattern rather than assuming every route has a service object.

## Authentication and authorization

There are five valid role values: `patient`, `doctor`, `hospital_staff`, `hospital_admin`, `platform_admin`.

1. Registration normalizes email, hashes the password, creates role `patient`, creates an `AuthSession`, and returns a signed token and public user details.
2. The bearer token carries `sub`, role, session ID (`jti`), issue/expiry time, and token type. Default access lifetime comes from `ACCESS_TOKEN_MINUTES`.
3. `get_current_user` verifies JWT signature/type/expiry, loads the matching database session, checks not revoked and not expired, reloads the user, checks active status and current role, and validates hospital/doctor assignment for provider roles.
4. `require_roles("...")` restricts route entry. Other endpoints perform per-resource checks in route logic.
5. Patient profile repository queries always include `owner_user_id`. Provider appointment queries scope by patient, linked doctor, hospital, or platform role. Admin scope derives from `hospital_id`.
6. Logout revokes the current session. Password reset invalidates prior tokens and revokes active user sessions.

The frontend's `visibleNavigation` only controls presentation. Server dependencies and query filters enforce access. A hidden page is not a security feature.

## Domain flow notes

### Patient profile

`patient_routes.py` applies `patient_user = require_roles("patient")`. Pydantic input models normalize name/email and constrain age/gender. `PatientController` maps duplicate/not-found domain errors to 409/404. `PatientService` checks duplicate email and calls `PatientRepository`, whose reads include both profile ID and owner user ID. Unique email conflicts are rolled back and translated to 409.

### Provider directory and appointments

`provider_routes.py` filters directory queries to active/verified doctors and verified hospitals. Schedules are recurring local wall-clock windows. `list_available_slots` maps schedule ranges to 30-minute UTC instants, then removes times already present in `appointment_slot_locks`. `create_appointment` requires a patient role, timezone-aware datetime, and a 16–128 character `Idempotency-Key`; it validates the target and schedule, inserts an appointment, slot lock, command fingerprint and event, then commits. Unique slot/command constraints arbitrate races. Reschedule uses the same idempotency model and releases/reclaims slot locks. See [workflow traces](./END_TO_END_FLOWS.md).

### Billing and payments

`billing_routes.py` scopes invoice/payment reads by current role and owner/hospital. Staff/admin invoice issue is constrained to allowed hospital scope; an appointment invoice uses the doctor fee stored in the database and is unique per appointment. Checkout accepts only an invoice ID, loads the amount/currency from the invoice, and requires the patient owner. Demo creates a `demo_...` order and the separate `/demo/complete` endpoint only accepts pending attempts with `success`, `failed`, or `cancelled`. It never calls a gateway. Live checkout invokes `PaymentService.create_order`; verification checks the HMAC and fetches provider payment state/amount/currency before marking paid. The signed Razorpay webhook validates exact raw-body signature and records event IDs for replay protection.

### Assistant and voice

- `POST /assistant/triage` calls `evaluate_triage` without any model or database write. Exact red-flag terms are enumerated in `triage_service.py`; unmatched symptoms are not clinically ruled out.
- `POST /assistant/chat` requires authentication and a final user message. It runs deterministic triage and treatment/prompt-injection checks before RAG/model calls. If RAG is enabled it searches approved public-health content; source conflict yields a cautious response. Then a configured LLM provider returns a validated structured answer. The API does not persist chat history.
- `POST /assistant/speech-to-text` accepts bounded multipart audio only when a remote STT provider is configured. With `browser` provider, endpoint returns 409 because recognition is expected in browser APIs. Supported language codes are `hi` and `en`; transcript response signals that user confirmation is required.
- Browser speech synthesis lives in `VoiceAssistant.jsx`; it is not server TTS.

### Administration and notifications

`admin_routes.py` treats `platform_admin` as global and `hospital_admin` as hospital-scoped. Hospital admins can provision doctor accounts and activate/deactivate hospital staff but cannot grant arbitrary roles. Platform admin account changes enforce role/hospital/doctor consistency, cannot self-edit here, and protect the last active platform admin. `notify_user` records an outcome; missing provider settings or provider failures are designed not to roll back the core operation. The admin API exposes delivery records; the patient-facing notifications page is still a placeholder.

## Exceptions, logging, and data handling

- FastAPI/Pydantic validation errors are 422; route code explicitly raises 400/401/403/404/409/413/415/502/503/504 as appropriate.
- `get_db` rolls back on exceptions. Mutation routes often wrap flush/commit in explicit `IntegrityError` handling to protect uniqueness and concurrent operations.
- The global exception handler logs server-side details but returns only `"An unexpected server error occurred."`.
- Appointment logging added in `provider_routes.py` reports outcome without patient IDs or appointment details. Audit rows can include actor/resource IDs and limited operational details; treat the audit database as sensitive too.
- Do not log passwords, tokens, raw health conversation, audio bytes, payment secrets, or full provider responses.

## Security boundaries and known limitations

- Access tokens are held in browser `localStorage`, so an XSS bug could expose the current bearer token. The app uses authorization headers rather than an auth cookie; still apply output/input handling and a production browser security policy. No refresh-token flow or MFA implementation was found.
- `enforce_auth_rate_limit` stores counters in a process-local `OrderedDict` protected by a lock. This limits one process, not a multi-replica deployment; the README calls for a shared rate-limit store before scaling.
- Email and phone destinations are not verified. SMTP/SMS are optional and are not configured by default. Do not use delivery as proof of identity.
- Compose is a local-development stack, not a production TLS/reverse-proxy deployment. Its ports bind to loopback, but production needs managed secrets, HTTPS, least privilege, monitoring, backup/restore testing, incident response, and privacy/legal review.
- RAG and model outputs are not clinical validation. The deterministic red-flag matcher has limited language/phrase coverage; do not rely on it to exclude emergencies.
- Razorpay live code is conditional on private credentials and has not been verified against a live provider in this documentation work. Demo payment is not real settlement.

These are implementation/deployment boundaries, not a complete vulnerability assessment. Follow the repository's deployment-readiness checklist before handling real patient data.

## Migrations and testing

Alembic's configuration is `backend/alembic.ini`; `backend/migrations/env.py` loads `app.models` metadata and configured database URL. The backend container runs `alembic upgrade head` before Uvicorn. Current revisions are `0001_portal_billing` through `0014_invoice_refund_status`. Add and review a migration for model changes; runtime startup does not call `Base.metadata.create_all`.

Tests are under `backend/tests/`. Database workflows usually use isolated SQLite fixtures; provider HTTP calls are mocked. Run:

```sh
docker compose exec -T backend python -m pytest -q
docker compose exec -T backend alembic current
docker compose exec -T backend alembic check
```

See [API reference](./API_REFERENCE.md), [database guide](./DATABASE_GUIDE.md), and [run/debug guide](./RUN_AND_DEBUG.md).

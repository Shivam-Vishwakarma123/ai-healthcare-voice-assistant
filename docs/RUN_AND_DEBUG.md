# Run and debug CareVoice

These commands use the repository's Docker Compose service names. Commands are non-destructive. Use synthetic data only; do not copy secrets or real patient information into logs, screenshots, or issues.

## Configuration and services

Copy `.env.example` to `.env` only if `.env` does not already exist. Replace example secrets with separate random secrets. Never overwrite an existing `.env`, print it, or commit it.

| Service | Container role | Host binding → container | Notes |
| --- | --- | --- | --- |
| `frontend` | React/Vite dev server | `127.0.0.1:3000` → 5173 | Uses `VITE_API_BASE_URL=http://localhost:8000/api/v1` because the browser calls the host-published API. |
| `backend` | FastAPI/Uvicorn | `127.0.0.1:8000` → 8000 | Uses `DATABASE_URL` with Compose hostname `db`; applies Alembic migrations before startup. |
| `db` | PostgreSQL 16 | `127.0.0.1:5432` → 5432 | Named volume `postgres_data`; health check uses `pg_isready`. |
| `ollama` | Optional local model server | `127.0.0.1:11434` → 11434 | Named volume `ollama_data`; LLM model/provider are configurable. |
| `pgadmin` | Local DB browser | `127.0.0.1:5050` → 80 | Named volume `pgadmin_data`; configure a unique password. |

`frontend_node_modules` is a named container dependency volume. Compose binds service ports to loopback; do not expose this development stack to the internet. `docker compose down` keeps database/model/admin volumes. Do not use `docker compose down -v` as a normal troubleshooting step; it permanently removes volumes.

## Start and inspect

```sh
# From repository root; if .env already exists, leave it in place.
docker compose config --quiet
docker compose up --build -d
docker compose ps
```

Check HTTP health:

```sh
curl -i http://localhost:8000/api/v1/health/live
curl -i http://localhost:8000/api/v1/health/ready
curl -i http://localhost:3000/
```

Open the portal at <http://localhost:3000> and API docs at <http://localhost:8000/docs>. The `/api/v1/health` route aliases readiness. Liveness can succeed while the database is unavailable; readiness cannot.

Logs and service status:

```sh
docker compose logs --tail=150 backend
docker compose logs --tail=150 frontend
docker compose logs --tail=150 db
docker compose logs --tail=150 ollama
docker compose ps
```

Follow logs with `docker compose logs -f backend` (Ctrl-C stops log viewing, not the container). Never run `docker compose config` without `--quiet` in a context where rendered environment values could be exposed.

## Database and migration inspection

```sh
docker compose exec -T db psql -U healthcare_user -d healthcare_db -c '\dt'
docker compose exec -T db psql -U healthcare_user -d healthcare_db -c 'SELECT version_num FROM alembic_version'
docker compose exec -T backend alembic current
docker compose exec -T backend alembic check
```

For local synthetic data, inspect only fields needed:

```sh
docker compose exec -T db psql -U healthcare_user -d healthcare_db -c \
  'SELECT id, role, hospital_id, doctor_id, is_active FROM users ORDER BY id LIMIT 20'
docker compose exec -T db psql -U healthcare_user -d healthcare_db -c \
  'SELECT id, patient_user_id, doctor_id, scheduled_for, status FROM appointments ORDER BY id DESC LIMIT 20'
docker compose exec -T db psql -U healthcare_user -d healthcare_db -c \
  'SELECT id, invoice_number, amount_minor, currency, status FROM invoices ORDER BY id DESC LIMIT 20'
```

Interactive access: `docker compose exec db psql -U healthcare_user -d healthcare_db`, then `\dt`, `\d appointments`, and `\q`. These examples rely on the `.env.example` database names; use corresponding non-secret local names if your setup differs.

The data volume is persistent. Backend startup applies forward migrations; do not manually drop tables or downgrade to fix an application error. Back up valuable data and test migration upgrades separately.

## Tests and build

```sh
docker compose exec -T backend python -m pytest -q
docker compose exec -T backend alembic check
docker compose exec -T frontend npm test
docker compose exec -T frontend npm run build
```

The backend tests use isolated/synthetic database fixtures and mock external payment/AI providers in relevant tests. The frontend uses Node's built-in test runner (`node --test`). No configured ESLint or TypeScript typecheck script is present in `frontend/package.json`.

Useful targeted backend tests:

```sh
docker compose exec -T backend python -m pytest -q tests/test_auth_security.py tests/test_account_boundaries.py
docker compose exec -T backend python -m pytest -q tests/test_appointment_workflow.py tests/test_provider_directory.py
docker compose exec -T backend python -m pytest -q tests/test_billing_flow.py tests/test_onboarding_and_demo_payments.py
docker compose exec -T backend python -m pytest -q tests/test_triage.py tests/test_rag_and_provider_safety.py
```

## Environment settings at a glance

The full example and validation are in `.env.example` and `backend/app/core/config.py`.

| Setting group | Variables | Use |
| --- | --- | --- |
| App/database | `APP_NAME`, `APP_ENV`, `API_V1_PREFIX`, `DATABASE_URL`, `BACKEND_CORS_ORIGINS` | API title/prefix, production checks, database connection and browser origins. |
| Database/admin UI | `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `PGADMIN_DEFAULT_EMAIL`, `PGADMIN_DEFAULT_PASSWORD` | Compose database and local pgAdmin setup. |
| Browser API | `VITE_API_BASE_URL` | Host-visible API base; browser cannot use Compose's internal `backend` DNS name. |
| Identity | `JWT_SECRET_KEY`, `ACCESS_TOKEN_MINUTES`, `PASSWORD_RESET_MINUTES`, `AUTH_RATE_LIMIT_ATTEMPTS`, `AUTH_RATE_LIMIT_WINDOW_SECONDS`, `ADMIN_BOOTSTRAP_TOKEN` | Token signing/expiry, throttling and one-time bootstrap. |
| Email/SMS | `SMTP_*`, `SMS_API_URL`, `SMS_API_TOKEN`, `APP_PUBLIC_URL` | Optional password reset and generic sign-in notification. Secrets remain backend-only. |
| Chat model | `LLM_PROVIDER`, `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`, `LLM_TEMPERATURE`, `LLM_MAX_TOKENS`, `LLM_TIMEOUT_SECONDS`, `LLM_MAX_RETRIES` | Local Ollama or compatible AI provider and bounded request settings. |
| RAG/embeddings | `RAG_ENABLED`, `EMBEDDING_PROVIDER`, `EMBEDDING_MODEL`, `EMBEDDING_TIMEOUT_SECONDS`, `EMBEDDING_DIMENSIONS`, `RAG_CHUNK_SIZE`, `RAG_CHUNK_OVERLAP`, `RAG_APPROVED_SOURCE_HOSTS` | Opt-in source retrieval and embedding/ingestion policy. Default RAG is off; hash embedding is an offline lexical baseline, not semantic inference. |
| Speech | `SPEECH_TO_TEXT_PROVIDER`, `SPEECH_TO_TEXT_BASE_URL`, `SPEECH_TO_TEXT_API_KEY`, `SPEECH_TO_TEXT_MODEL`, `SPEECH_TO_TEXT_TIMEOUT_SECONDS`, `SPEECH_TO_TEXT_MAX_AUDIO_BYTES` | Browser, OpenAI-compatible, or externally hosted IndicConformer adapter mode. |
| Provider matching | `PROVIDER_MATCH_SPECIALTY_WEIGHT`, `PROVIDER_MATCH_CITY_WEIGHT`, `PROVIDER_MATCH_LANGUAGE_WEIGHT`, `PROVIDER_MATCH_CONSULTATION_WEIGHT` | Weights for directory recommendation scoring. |
| Payments | `PAYMENT_MODE`, `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET`, `RAZORPAY_API_BASE_URL` | Demo/live behavior and backend Razorpay integration. Production rejects demo mode. |

Never paste the actual local `.env` into documentation. Hosted AI/speech provider use sends data outside the local stack; review terms before configuring.

## Troubleshooting by symptom

| Symptom | Debug order | Relevant files / likely cause |
| --- | --- | --- |
| Browser says “Failed to fetch” | Open DevTools Network; check frontend `3000`, API `8000`, `/health/live`; then inspect OPTIONS request and CORS response. Confirm origin includes exact scheme/host/port and `Idempotency-Key` is allowed for booking. | `frontend/src/services/api.js`, `backend/app/core/config.py`, `backend/app/main.py`, `docker-compose.yml`; wrong URL, stopped backend, CORS mismatch, DNS/network. |
| 401 | Check `/auth/me`, expiry and active account. Sign in again; inspect backend logs for auth failure without printing token. | `auth/security.py`, `auth_routes.py`, `App.jsx`; expired/revoked session or invalid JWT. |
| 403 | Confirm role and provisioning (`hospital_id`, linked `doctor_id`, active doctor); do not bypass server checks. | `get_current_user`, route `require_roles`, admin/provider route scope. |
| 404 | Confirm exact `/api/v1` prefix, trailing slash for `/patients/`, resource ID and that role-scoped query permits visibility. | Router registration in `main.py`, route prefix and owner/tenant filters. |
| 422 | Inspect response `detail` and compare JSON field names/types/timezone/header with Pydantic schema. | `backend/app/schemas/`, request models in routes, caller form body. |
| 500 | Capture request time/path/status (not body containing health data); inspect `docker compose logs --tail=150 backend`. Check traceback server-side and DB state. | Global exception handler logs exception; route/service operation. Never hide by converting all failures to empty results. |
| Database not ready | Check `docker compose ps`, db health, `pg_isready`, backend readiness endpoint and backend logs. Verify DB hostname is `db` inside container and URL-encode special chars in URL password. | Compose health dependency, `.env.example`, config/database, Alembic startup. |
| Profile or appointment missing | Call list endpoint as same account; inspect role-scoped response, FK IDs, verification/status and current DB row using synthetic data. Refresh because UI uses snapshots. | Patient owner filter, provider role filters, verified state; no real-time push. |
| Appointment booking/confirmation fails | Inspect returned status; 409 means slot/idempotency conflict, 422 means malformed timezone/header, 401 expired token, 403 wrong role/scope. Refresh available slots and retry identical request with same key if outcome is uncertain. | `provider_routes.py`, `AppointmentCreate`, `appointment_slot_locks`, `appointment_commands`; slot availability is not a hold. |
| Dashboard count looks wrong | Compare raw API page and `total`; check `status`, hospital scope, page limit and whether a failed `Promise.allSettled` source is shown as unavailable. | `DashboardPage`, `/admin/overview`; no global cache or push updates. |
| Duplicate API calls | Inspect Network initiator, effects, selected page, retry buttons and handler submission state. Prevent duplicate mutations in UI, but still use backend idempotency for appointments/payments. | React effect dependencies, submit `busy` state, `Idempotency-Key`, uniqueness constraints. |
| Duplicate appointment | Compare appointment `id`, user/doctor/slot and command replay; same-key same-payload should return same record. Different keys for a repeated user intent are separate commands but unique slot lock still blocks same slot. | `AppointmentCommand`, `AppointmentSlotLock`, create/reschedule routes. |
| Invoice/payment mismatch | Refresh `/billing/invoices` and `/billing/payments`; check invoice status, payment attempt state and mode. Demo records are local simulation only. Live mode relies on server verification/webhook; do not mark paid from browser callback alone. | `billing_routes.py`, `payment_service.py`, `PaymentWebhookEvent`, `Billing.jsx`. |
| React UI not refreshing | Use page Refresh action or navigate/remount; verify mutation response succeeded then list endpoint. | Local `useState`/effects; no global cache/WebSocket/polling. |
| Container fails startup | `docker compose ps`, inspect service logs; for backend check migration output before Uvicorn; for frontend check build/Vite output; for Ollama check model availability. | Dockerfiles, Compose healthchecks, config, migrations. Don't delete volumes as a first fix. |

## Optional operator commands

Create a managed staff account from an interactive terminal (the command prompts for password; do not pass a real password in shell history):

```sh
docker compose exec backend python -m app.cli create-staff clinic@example.com
```

Pull the configured local Ollama model only if intentionally using chat and the model is missing:

```sh
docker compose exec ollama ollama list
docker compose exec ollama ollama pull llama3.2:1b-instruct-q4_K_M
```

Do not run a volume deletion or database reset to repair an ordinary startup issue.

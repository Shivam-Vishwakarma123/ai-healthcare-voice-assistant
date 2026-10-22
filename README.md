# CareVoice — AI healthcare portal (development)

CareVoice is a Docker Compose development application for a patient portal. It currently includes account registration and login, private patient profiles, live clinic-directory and appointment workflows, a browser voice/text assistant, and clinic-issued invoices with optional Razorpay Checkout.

> **Important:** This is a development scaffold, not a medical device or production healthcare service. It is not certified for HIPAA, India's DPDP Act, or any other healthcare/privacy regulation. Use synthetic data only. Do not enter real patient or payment-card information. The assistant is not a clinician and must not be used for diagnosis or emergencies.

## What's working

- **Accounts and access control:** Argon2 password hashing, five server-enforced roles, short-lived JWTs backed by revocable database sessions, login/reset rate limits, one-time password reset tokens, and audit records for authentication and sensitive patient/appointment/billing actions.
- **Private patient profiles:** Authenticated endpoints scope patient records to their owner. The database migration associates old profiles to an account with the same email when possible; unmatched legacy records remain inaccessible to patient accounts.
- **AI-First Healthcare Assistant:** Authenticated voice/text consultation via configurable LLMs (`gpt-6-astra` hosted or local Ollama `llama3.2:1b-instruct-q4_K_M`), strict structured JSON schema enforcement, bounded retries/timeouts, output safety post-filters, and Web Speech API transcription review/audio playback. Patient consultations support explicit opt-in consent, full conversation history lifecycle (create, list, view, clear, delete), and strict cross-patient isolation.
- **Evidence-Grounded RAG Pipeline:** Verified public health medical knowledge from NIH MedQuAD, MedlinePlus, WHO, and Indian Ministry of Health & Family Welfare (MoHFW) with explicit HTTPS provenance, version tracking, vector embeddings, and conflict detection. Curated knowledge can be ingested via `python -m app.cli ingest-knowledge`.
- **Deterministic Emergency Clinical Triage:** A deterministic clinical safety triage engine that preempts all LLM and vector retrieval inference for acute red flags across English, Hindi, and Hinglish. Automatically routes to emergency helplines: 112 (National Emergency), 108 (Ambulance), and Tele-MANAS 14416 (Mental Health Crisis). Emergency triage operates 100% offline even if AI services are unavailable.
- **Verified Doctor Recommendations:** Explainable clinician matching querying active, verified doctor profiles from PostgreSQL. Matches based on specialty hints, symptoms, consultation types, and hospital location with transparent match reasons and 1-click appointment booking navigation.
- **Care discovery and appointments:** Paginated, verified-only doctor/hospital directory with persistent qualifications, specialties, languages, consultation types, recurring schedules, verification review, profile pages, and role-scoped dashboards. Appointment slots are generated from published schedules; booking and rescheduling are idempotent and protected by database slot locks. The UI displays appointment dates and times in IST. No ratings or appointment slots are fabricated.
- **Billing:** Patient-owned invoice/payment access; hospital staff/admin can issue service invoices or invoice an appointment at the clinician's recorded fee, with duplicate appointment invoices prevented. Explicit demo checkout works without provider credentials; Razorpay remains available in live mode with signed verification and an optional signed webhook.
- **Responsive bilingual interface:** Landing and authentication screens, patient dashboards, profile management, symptom triage, assistant, care discovery, appointment history, and billing use responsive layouts with English/Hindi labels on supported screens. Voice transcription is configurable between browser recognition, an OpenAI-compatible transcription API, and an operator-hosted AI4Bharat IndicConformer adapter; transcripts require user review before sending.
- **Administration and notifications:** Platform and hospital admins have scoped account, appointment, payment-status, audit, and aggregate views. Optional SMTP/SMS notifications record explicit outcomes and send only a generic sign-in reminder; contact addresses are not verified. Medical-record exchange is not integrated.
- **Database changes:** Alembic migrations run automatically before the API starts.
- **Longitudinal Patient Health Records:** Centralized, persistent longitudinal health record aggregating patient profiles, pre-consultation triage sessions, clinical consultation notes, doctor-authored prescriptions, active allergies and conditions, uploaded diagnostic documents, and care plans into an encounter-scoped chronological timeline (`/records/timeline`).
- **Doctor Clinical Workspace:** Authorized, encounter-scoped clinician workspace (`frontend/src/components/DoctorWorkspace.jsx`) supporting assigned patient rosters, appointment schedules, pre-consultation triage inbox reviews, AI-assisted consultation note drafting, physical examination recording, and electronic finalization signatures.
- **AI-Assisted Prescriptions with Drug-Allergy Safety Pre-Screening:** Structured digital prescription builder (`RX-YYYYMMDD-XXXXXX`) featuring dosage forms, administration routes, clinical frequencies, durations, and specific patient instructions. Prescribing engine runs automated real-time drug-allergy cross-reactivity screening (penicillin, cephalosporins, NSAIDs, sulfa drugs, fluoroquinolones, macrolides) before saving or signing. Clinician electronic signatures mark prescriptions immutable.
- **Server-Side Clinical PDF Generation:** Automated ReportLab streaming producing downloadable, high-fidelity PDFs for doctor-signed digital prescriptions and structured AI medical assessment reports, complete with hospital headers, practitioner credentials, medication grids, allergy warnings, and electronic verification stamps.
- **HL7 FHIR Release 4 Interoperability:** Standards-compliant HL7 FHIR R4 JSON Bundle exporter (`/records/fhir/export`) transforming relational clinical records into interoperable `Patient`, `AllergyIntolerance`, `Encounter`, `MedicationRequest`, `DiagnosticReport`, and `Provenance` resources for export into external hospital EHR systems.
- **Explicit integrations:** Optional email/SMS notifications record delivery outcomes; no provider credentials are configured by default, and no demo records are presented as real data.

Triage rules are a limited development safeguard, not a clinically validated screening system. Language coverage is incomplete; do not rely on it to rule out an emergency or delay professional care. For emergencies in India, call 112 or 108.

## AI Platform Architecture, Safety & Operations Documentation

Comprehensive engineering specifications, research reviews, safety benchmarks, and compliance documentation are maintained under `docs/`:

- **Longitudinal Patient Records & Doctor Workflow:** [`docs/PATIENT_RECORDS_AND_DOCTOR_WORKFLOW.md`](./docs/PATIENT_RECORDS_AND_DOCTOR_WORKFLOW.md)
- **Scientific AI Research Review:** [`docs/AI_RESEARCH_REVIEW.md`](./docs/AI_RESEARCH_REVIEW.md)
- **Model Selection & Benchmark Decision:** [`docs/AI_MODEL_SELECTION.md`](./docs/AI_MODEL_SELECTION.md)
- **Clinical Dataset Strategy & Knowledge Base Provenance:** [`docs/AI_DATASET_STRATEGY.md`](./docs/AI_DATASET_STRATEGY.md)
- **Clinical Safety, Governance & Limitations:** [`docs/AI_SAFETY_AND_CLINICAL_LIMITATIONS.md`](./docs/AI_SAFETY_AND_CLINICAL_LIMITATIONS.md)
- **AI-First Platform Architecture:** [`docs/AI_ARCHITECTURE.md`](./docs/AI_ARCHITECTURE.md)
- **Clinical Safety & Evaluation Methodology:** [`docs/AI_SAFETY_AND_EVALUATION.md`](./docs/AI_SAFETY_AND_EVALUATION.md)
- **Verified Evaluation Results:** [`docs/AI_EVALUATION_RESULTS.md`](./docs/AI_EVALUATION_RESULTS.md)
- **AI Setup & Operational Guide:** [`docs/AI_SETUP.md`](./docs/AI_SETUP.md)
- **AI Assistant API Reference:** [`docs/AI_API_REFERENCE.md`](./docs/AI_API_REFERENCE.md)
- **Current-State Codebase Audit:** [`docs/audit/current-state.md`](./docs/audit/current-state.md)
- **Feature Inventory & Status Classification:** [`docs/audit/feature-inventory.md`](./docs/audit/feature-inventory.md)
- **Security & Privacy Findings (OWASP ASVS / DPDP Act):** [`docs/audit/security-findings.md`](./docs/audit/security-findings.md)
- **Data, AI/ML & Clinical Safety Audit:** [`docs/audit/data-and-ml-findings.md`](./docs/audit/data-and-ml-findings.md)
- **Target Architecture (Modular Monolith):** [`docs/architecture/target-architecture.md`](./docs/architecture/target-architecture.md)
- **Role-Permission Matrix & Access Policy:** [`docs/security/role-permission-matrix.md`](./docs/security/role-permission-matrix.md)
- **Operational Runbook & Disaster Recovery:** [`docs/operations/runbook.md`](./docs/operations/runbook.md)
- **AI Model Card & Clinical Limits:** [`docs/ml/model-card.md`](./docs/ml/model-card.md)
- **Production Compose Specification:** [`compose.production.yaml`](./compose.production.yaml)

## Requirements

- Docker Desktop with Docker Compose v2.
- For live AI or payment testing: provider credentials (both are optional for starting the app).

## Start the app

1. From the project folder, copy `.env.example` to `.env` if you do not already have a local `.env`.
2. Replace the example `JWT_SECRET_KEY`, `POSTGRES_PASSWORD`, and `PGADMIN_DEFAULT_PASSWORD` with separate random secrets. Generate a one-time `ADMIN_BOOTSTRAP_TOKEN` using `openssl rand -hex 32`; use a unique token of at least 32 characters and keep it private. `.env.example` selects `PAYMENT_MODE=demo` for local testing. URL-encode reserved characters in `POSTGRES_PASSWORD` when setting `DATABASE_URL`. Never commit `.env`.
3. Start the app:

   ```powershell
   docker compose up --build -d
   ```

4. Open the portal at <http://localhost:3000>. The API liveness and database readiness endpoints are <http://localhost:8000/api/v1/health/live> and <http://localhost:8000/api/v1/health/ready>; `/api/v1/health` remains a readiness-compatible alias. Interactive API docs are at <http://localhost:8000/docs>.
5. Create a patient account from the portal. The first page load validates the saved access token; sign in again if it has expired.

The database is persisted in the `postgres_data` Docker volume. Stop the app with `docker compose down`. That keeps database data. Migrations are additive and run before the backend starts; they do not reset existing tables or the volume. To erase the database, explicitly remove the volume with `docker compose down -v` (this permanently deletes local data).

pgAdmin is bound to localhost at <http://localhost:5050>; configure a unique `PGADMIN_DEFAULT_PASSWORD` before using it. Its settings are stored in the `pgadmin_data` volume. The API can start and serve deterministic emergency triage when Ollama is unavailable; AI chat will report provider failures until the configured model service is available.

`PAYMENT_MODE=demo` enables a clearly labeled local simulation without contacting Razorpay or requesting card or banking details. Patients can choose a simulated success, failure, or cancellation from Billing & Payments; only a pending owner-authorized demo attempt can be completed, and failed/cancelled attempts leave the invoice unpaid. A successful demo updates the local invoice and payment history but is not evidence of a money transfer. Production configuration rejects demo mode.

For provider-processed payments, set `PAYMENT_MODE=live` and configure Razorpay **Test Mode** `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET`; webhook processing additionally requires the matching secret configured in the Razorpay dashboard. The Razorpay key ID should start with `rzp_test_` in development/test. In the Razorpay Test Mode dashboard, ensure Cards are enabled under the Checkout payment configuration; the app uses Razorpay's hosted Checkout and does not construct its own card form. Configure the webhook URL as `https://<your-api-host>/api/v1/billing/webhooks/razorpay` and subscribe to `payment.captured`, `payment.failed`, `refund.processed`, and `refund.failed`. The API verifies checkout signatures and provider payment state server-side, validates webhook signatures against the exact raw request body, and stores processed event IDs for safe retries. Only the public key ID is returned for checkout; the key secret and webhook secret must remain backend-only. Automated tests mock the provider and never perform real charges. `PAYMENT_MODE=demo` only provides an explicitly simulated checkout; it does not display a card-entry form.

Appointment booking currently does not require advance payment: a patient books a slot, then can explicitly choose Pay Now in Appointments. That action creates or retrieves one invoice using the doctor's stored fee and opens Billing checkout; it does not charge automatically. Clinic staff can also issue invoices through Billing. The clinic/business account configured in the Razorpay merchant dashboard receives settlement under that merchant's account configuration; this app does not split or pay funds to doctors or hospitals. Configure and verify the merchant legal entity, bank account, settlement schedule, and any marketplace/transfer product separately before live use. `APPOINTMENT_REFUND_POLICY=manual_review` is the safe default: cancelling does not automatically refund, and a hospital/platform administrator must review and request the refund. Set it to `no_refunds` to disable refund requests. No clinic-approved cancellation terms are supplied by this repository. Refunds stay pending until a provider response/webhook confirms processing. Razorpay API refunds use the original captured payment and may be partial; external settlement timing is controlled by the provider and issuing bank.

For Razorpay Checkout **Test Mode only**, use test API keys beginning `rzp_test_`. The documented Visa test card is `4100 2800 0000 1007`; use any random CVV and a future expiry date. The mock bank page can simulate success or failure. Do not use this card or test keys in live mode. See [Razorpay's official test integration guide](https://razorpay.com/docs/payments/payment-gateway/web-integration/standard/test-integration/). The app rejects non-test Razorpay key IDs when `APP_ENV=development` or `test` and live mode is selected. Automated checks use mocked provider calls, not the card or a live sandbox transaction.

To switch the local UI from the no-card simulation to Razorpay's hosted Test Mode checkout, set `PAYMENT_MODE=live` in `.env` and add the Test Mode keys above, then run `docker compose up -d --build backend frontend`. Sign in as a patient, open **Appointments**, and choose **Pay Now** on an upcoming eligible appointment, or open **Billing** for an unpaid invoice. Card entry and any mock-bank success/failure step occur on Razorpay Checkout, not in CareVoice. If the provider checkout opens without a Card method, enable Cards in the Razorpay Test Mode account's Checkout payment configuration. The current local `.env` has no Razorpay keys, so this card journey is not yet available in this environment.

Email notifications reuse the optional SMTP configuration. SMS is opt-in and uses `SMS_API_URL` plus `SMS_API_TOKEN`; the HTTPS endpoint must accept a bearer token and JSON `{"to": "+<E.164>", "message": "..."}` and return a 2xx status on acceptance. Users may save or clear their own E.164 notification number from profile/admin settings. Neither email addresses nor phone numbers are verified, so both channels contain only a generic sign-in reminder, never appointment, billing, or health details. Delivery attempts store only user/hospital IDs, channel, event type, outcome, and a failure code; message contents, destination addresses, and provider response bodies are not stored. Missing configuration/contact and provider errors are shown as explicit delivery outcomes and never change the result of the appointment, verification, or billing operation. No email/SMS credentials are configured by default.

## Accounts, roles, and password reset

Public registration creates patient accounts only. For a new installation, set `ADMIN_BOOTSTRAP_TOKEN` in `.env` to a unique token generated with `openssl rand -hex 32`, start or restart the app, and open **Initial administrator setup** on the public page (or go directly to `/setup/administrator`). Enter the token along with the administrator's name, email, and a strong password (12+ characters with uppercase, lowercase, number, and symbol). If the token is missing or the setup state is unavailable, the page explains the required configuration instead of silently hiding setup. The bootstrap is database-locked, succeeds once, and is closed after an administrator exists. Subsequent privileged accounts are created in **Administration** by a platform administrator; a hospital administrator can create doctor accounts only for clinician profiles at their assigned hospital.

Onboarding from the website:

1. Sign in as the platform administrator and open **Provider dashboard**.
2. Select **Add a hospital profile**. The page displays its generated ID and pending-verification status after saving.
3. Open **Administration → Create a staff account**, select **Hospital administrator**, choose that hospital, and enter the account details. Hospital administrators can then sign in and add clinician profiles from their Provider dashboard; the hospital association comes from their account and is enforced by the API.
4. A platform administrator verifies the hospital and clinician in the Provider dashboard review queue. Unverified records are not shown in the public directory.
5. To enable a doctor's login, use **Administration → Create a staff account**, select **Doctor login**, and link the account to the existing clinician profile. A hospital administrator can create doctor logins only within their own hospital.
6. Patients register from **Create account**; public registration cannot assign staff or administrator roles.

### Seed fictional demo data (local development only)

The optional seed adds three clearly labeled fictional hospitals, ten synthetic clinicians, twenty patient accounts/profiles, scoped hospital-admin and doctor logins, schedules, appointment history, and simulated invoices/payment attempts. It is additive and rerunnable: it does not reset tables, delete records, or change the existing platform-administrator account. If a seeded identity or appointment marker conflicts with an existing record, the transaction fails rather than taking it over. Run it only against a local development/test database; it refuses other `APP_ENV` values.

```sh
docker compose exec backend python -m app.seed_demo
```

All seeded patient, doctor, and hospital-admin accounts use the development-only password `CareVoiceDemo2026!`; for example, sign in as `patient01@demo.carevoice.test`, `doctor01@demo.carevoice.test`, or `hospital-admin01@demo.carevoice.test`. The remaining accounts follow the same numbered pattern (`01` onward; three hospital admins, ten doctors, twenty patients). The seed does not create a platform administrator: continue using the platform-admin account already configured for this installation. Change or remove these synthetic accounts before sharing an environment, and never use this password or data in production.

Trusted operators can still provision other staff roles, such as `hospital_staff`, from the CLI after the hospital exists:

```sh
docker compose exec backend python -m app.cli create-account doctor@example.com --role doctor --hospital-id 1 --doctor-id 1
docker compose exec backend python -m app.cli create-account staff@example.com --role hospital_staff --hospital-id 1
docker compose exec backend python -m app.cli create-account admin@example.com --role hospital_admin --hospital-id 1
docker compose exec backend python -m app.cli create-account platform@example.com --role platform_admin
```

The role values are `patient`, `doctor`, `hospital_staff`, `hospital_admin`, and `platform_admin`. Hospital-scoped accounts without a hospital assignment are rejected; doctor accounts must reference an active clinician profile at that same hospital. The `0004_auth_tenant_security` migration preserves legacy accounts and maps their former `staff`/`admin` role names to `hospital_staff`/`platform_admin`; legacy staff without an assigned hospital cannot sign in until an operator provisions them with `create-account` using their existing email, mapped role, and hospital ID. That operator action also resets the password. Existing stateless access tokens have no persisted session and require users to sign in again. Existing invoices retain their data but have no hospital assigned and are visible only to platform administrators until reconciled.

Sessions are stored in PostgreSQL and checked on every authenticated request. Logout revokes the current session; successful password reset revokes every session for that account. Configure SMTP in `.env` (`SMTP_HOST`, `SMTP_FROM_EMAIL`, and the appropriate TLS/credentials) and `APP_PUBLIC_URL` to enable the forgot-password email flow. Reset tokens are sent only by email; only their hashes are stored. Without SMTP configuration, reset requests return a setup error. Authentication throttling currently uses per-process memory; deploy a shared rate-limit store before running multiple backend replicas. Audit data includes account IDs, action/resource identifiers, source IP, and user-agent metadata; apply an appropriate retention and access policy before production use.

These controls are application-level development safeguards, not a security or regulatory certification. Use TLS, manage secrets outside source control, configure SMTP credentials securely, and review the tenant/role policy before production deployment.

### Development RBAC test accounts

Run `docker compose exec backend alembic upgrade head` before provisioning. The API and login form accept either the existing email address or a username. The role-test usernames are `platform.admin`, `hospital.admin`, `hospital.staff`, `doctor`, and `patient`. To seed them, provide `RBAC_TEST_PLATFORM_ADMIN_PASSWORD`, `RBAC_TEST_HOSPITAL_ADMIN_PASSWORD`, `RBAC_TEST_HOSPITAL_STAFF_PASSWORD`, `RBAC_TEST_DOCTOR_PASSWORD`, and `RBAC_TEST_PATIENT_PASSWORD` through a protected development-only runtime environment, then run `docker compose exec backend python -m app.seed_rbac_test_accounts`. The script is disabled outside `APP_ENV=development` or `test`, refuses non-local PostgreSQL targets, stores Argon2id hashes, marks each account as a test account, and creates only the synthetic hospital/clinician relationship required by the staff, hospital-admin, and doctor roles. Rerunning it leaves existing passwords unchanged; identity conflicts stop the transaction. Never put the supplied passwords in source control, command history, or logs.

## Configure AI chat and models

**Local and Hosted Model Architecture:**
CareVoice supports both offline local models via Ollama and hosted OpenAI-compatible providers. Settings support modern `AI_*` variables or legacy `LLM_*` / `EMBEDDING_*` keys with automatic bidirectional synchronization:

- **Local Inference (Default fallback):** `llama3.2:1b-instruct-q4_K_M` running locally via Ollama. No API key required.
- **Hosted Inference:** Configurable OpenAI-compatible model, defaulting to `gpt-6-astra` where configured.

Ollama starts automatically with `docker compose up`. Download the default quantized model once:

```powershell
docker compose exec ollama ollama pull llama3.2:1b-instruct-q4_K_M
```

The model downloads to a Docker volume and is reused on later starts. Once the model download completes, open **Voice Assistant** and chat or use microphone input.

To opt into hosted inference (`gpt-6-astra`), set provider credentials and model explicitly in `.env`:

```dotenv
AI_PROVIDER=openai_compatible
AI_API_KEY=your-provider-key
AI_BASE_URL=https://api.openai.com/v1
AI_MODEL=gpt-6-astra
```
*(Legacy `LLM_PROVIDER`, `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL` are also supported and kept automatically in sync).*

Prompts sent to a hosted provider leave your computer. The provider review and evaluation methodology are in [docs/llm_provider_evaluation.md](docs/llm_provider_evaluation.md). Browser speech recognition may also use a browser-vendor service. Do not submit names, contact details, or identifying medical information. The assistant provides general health education only and is not a clinician.

Speech-to-text provider configuration, audio handling, and the AI4Bharat IndicConformer assessment are documented in [docs/speech_to_text.md](docs/speech_to_text.md). Uploaded audio is bounded, sent only to the explicitly configured provider, processed without persistence, and never forwarded to the LLM until its transcript is reviewed and submitted. Emergency triage runs deterministically before RAG and LLM calls; it remains available when AI services are unavailable.

## Curated medical knowledge RAG

CareVoice includes a curated medical knowledge corpus located in `backend/data/knowledge/` containing reviewed public health literature from NIH MedQuAD, MedlinePlus, WHO, and Indian MOHFW with explicit HTTPS provenance URLs.

To ingest the curated knowledge corpus into PostgreSQL:

```sh
docker compose exec backend python -m app.cli ingest-knowledge
```

Or ingest with a custom manifest:

```sh
docker compose exec backend python -m app.cli ingest-knowledge --manifest data/knowledge/manifest.jsonl
```

The ingestion process is idempotent, verifies HTTPS source URLs, enforces approved health agency domains (NIH, MedlinePlus, WHO, MoHFW India, NHS, CDC), computes chunk embeddings, and detects conflicting medical claims.

For semantic search, configure `EMBEDDING_PROVIDER=ollama` or `openai_compatible` and its model. If no matching evidence exists or the embedding provider fails, the assistant is instructed to disclose the evidence gap and uses cautious general guidance; emergency triage does not depend on RAG.

## Evaluation

```sh
docker compose exec backend python scripts/evaluate_datasets.py
docker compose exec backend python scripts/evaluate_models.py
```

The deterministic command measures the local synthetic triage checks and missing-evidence behavior. Model evaluation makes no calls unless explicitly invoked with `--run`; requests may incur charges and use the configured provider. It reports small-sample schema, latency, token/cost, language-script, and refusal heuristics, not clinical accuracy. No real patient data should be used.

## Configure Razorpay payments

Use Razorpay **test keys** for local development. Add the keys to `.env`, then restart the backend:

```dotenv
RAZORPAY_KEY_ID=rzp_test_...
RAZORPAY_KEY_SECRET=...
RAZORPAY_WEBHOOK_SECRET=...
RAZORPAY_API_BASE_URL=https://api.razorpay.com/v1
```

In the Razorpay dashboard, configure the webhook URL as `https://<public-api-host>/api/v1/billing/webhooks/razorpay`, subscribe to `payment.captured`, `payment.failed`, `refund.processed`, and `refund.failed`, and use the same webhook secret. A public HTTPS callback is needed to test webhooks; local-only checkout verification is also implemented.

The clinic staff operator issues an invoice through **Billing & Payments** after the patient account ID is known. Create a staff account once, from the project folder:

```powershell
docker compose exec backend python -m app.cli create-staff clinic@example.com
```

The command securely prompts for a password and stores only its Argon2 hash. Sign in with that account to issue invoices; patients can see only their own invoices. Invoice amounts use INR paise internally. Never enable live payment keys until a real deployment has appropriate access controls, auditing, reconciliation, and legal/privacy review.

## Useful commands

```powershell
docker compose ps
docker compose logs -f backend
docker compose logs -f frontend
docker compose exec backend pytest -q
docker compose exec frontend npm run build
```

Backend migrations run during container startup. Check the applied revision and schema drift with `docker compose exec backend alembic current` and `docker compose exec backend alembic check`. To create a future schema revision, work from `backend` and use Alembic against the configured database; review generated operations and commit migration scripts with the application change. Backend tests run with `docker compose exec backend python -m pytest -q`; frontend tests and the production build run with `docker compose exec frontend npm test` and `docker compose exec frontend npm run build`. This JavaScript/JSX project currently has no configured lint or static type-check scripts; production build validates JSX/module syntax but is not a type check.

## Beginner project guide

For the detailed, source-verified developer guides covering architecture, project structure, React, FastAPI, PostgreSQL, endpoints, workflows, feature extensions, testing, and troubleshooting, start with [docs/PROJECT_OVERVIEW.md](docs/PROJECT_OVERVIEW.md). The printable older walkthrough is [the CareVoice Project Guide](docs/PROJECT_GUIDE.pdf), with [PROJECT_GUIDE.html](docs/PROJECT_GUIDE.html) as its source.

## Project structure

```text
backend/
  app/
    auth/          Password hashing and JWT authentication
    controllers/   Patient API coordination
    core/          Settings, database sessions, errors
    models/        SQLAlchemy entities
    repositories/  Persistence queries
    routes/        Auth, patient, assistant, billing APIs
    services/      Patient business logic
  migrations/      Versioned Alembic database changes
  tests/
frontend/
  src/
    components/    Voice assistant and billing UI
    services/      Shared API and formatting helpers
    App.jsx        Portal layout, auth, profile, navigation
```

## API overview

All application routes are under `/api/v1`.

| Endpoint | Access | Purpose |
| --- | --- | --- |
| `POST /auth/register`, `POST /auth/login` | Public | Register or sign in |
| `GET /auth/bootstrap/status`, `POST /auth/bootstrap/platform-admin` | Public, one-time token required for creation | Check and perform initial platform-admin setup |
| `GET /auth/me` | Signed in | Current account |
| `/patients` | Signed in, owner-scoped | Read and update the current patient's profile |
| `GET /assistant/health` | Public | Assistant health check distinguishing app health from AI provider health |
| `POST /assistant/triage` | Public | Deterministic clinical emergency triage (English/Hindi/Hinglish) |
| `POST /assistant/chat` | Signed in | AI-first healthcare chat with consent, RAG retrieval & doctor recommendation |
| `GET /assistant/assessments` | Signed in, owner-scoped | List patient's structured clinical assessments |
| `GET /assistant/assessments/{assessment_id}` | Signed in, owner-scoped | Get structured clinical assessment by UUID or ID (owner-isolated) |
| `GET /assistant/knowledge/status` | Staff / Admin | Knowledge ingestion and vector chunk status |
| `GET /assistant/conversations` | Signed in, owner-scoped | List patient's saved consultations with message count & timestamps |
| `POST /assistant/conversations` | Signed in, owner-scoped | Create a consultation with explicit opt-in privacy consent |
| `GET /assistant/conversations/{id}` | Signed in, owner-scoped | Retrieve full message thread and clinical metadata for a consultation |
| `DELETE /assistant/conversations/{id}` | Signed in, owner-scoped | Permanently delete a consultation and associated messages |
| `DELETE /assistant/conversations` | Signed in, owner-scoped | Clear all consultation history for the authenticated patient |
| `POST /assistant/speech-to-text` | Signed in | Transcribe uploaded audio via configured speech engine |
| `POST /assistant/rag/search` | Public | Query ingested evidence corpus with provenance citations |
| `GET /billing/invoices`, `/billing/payments`, `/billing/config` | Signed in, owner/tenant-scoped | Invoice history, payment history, and mode/readiness |
| `GET /billing/billable-appointments` | Clinic staff | List unbilled appointments within the caller's tenant |
| `POST /billing/invoices` | Clinic staff | Issue a service invoice or an appointment invoice priced from the clinician's stored fee |
| `POST /billing/checkout` | Invoice owner | Create a demo attempt or Razorpay checkout order |
| `POST /billing/demo/complete` | Invoice owner, demo mode only | Complete one pending simulated attempt as success, failure, or cancellation |
| `POST /billing/verify` | Invoice owner, live mode | Verify Razorpay checkout signature and captured provider payment |
| `POST /billing/webhooks/razorpay` | Razorpay signature | Mark captured payment from webhook |
| `GET /providers/doctors`, `/providers/hospitals` | Signed in | Paginated verified directory and filters |
| `GET /providers/doctors/{id}`, `/providers/hospitals/{id}` | Signed in | Verified provider profile details |
| `GET /providers/dashboard` | Signed in, role-scoped | Doctor, hospital, or platform dashboard |
| `GET /providers/review-queue` | Platform administrator | Pending provider verification |
| `PATCH /providers/doctors/{id}`, `/providers/doctors/{id}/schedules` | Doctor owner or hospital administrator in tenant | Update profile and recurring schedule |
| `PATCH /providers/hospitals/{id}` | Hospital administrator in tenant | Update hospital profile |
| `POST /providers/recommendations` | Signed in | Deterministic recommendations with match reasons |
| `GET /providers/doctors/{id}/available-slots?day=YYYY-MM-DD` | Signed in | Published future slots for an IST calendar day |
| `POST /providers/appointments` | Patient | Book an available slot; requires an `Idempotency-Key` header |
| `GET /providers/appointments`, `/providers/appointments/{id}/history` | Signed in, owner/tenant-scoped | Appointment list and event history |
| `POST /providers/appointments/{id}/confirm` | Assigned clinician or hospital care team | Confirm a scheduled appointment |
| `PATCH /providers/appointments/{id}/cancel`, `/providers/appointments/{id}/reschedule` | Authorized appointment participant | Cancel or reschedule; rescheduling requires an `Idempotency-Key` |
| `/admin/overview`, `/admin/users`, `/admin/appointments`, `/admin/payments`, `/admin/audit-logs`, `/admin/notifications` | Platform or hospital administrator | Scoped operational views; analytics are aggregated and small counts suppressed |
| `GET /admin/hospitals`, `GET /admin/doctors`, `POST /admin/accounts` | Platform or tenant hospital administrator | Select scoped hospitals/clinicians and create authorized staff accounts |
| `PATCH /admin/users/{id}` | Platform administrator; hospital admin for own staff activation only | Update managed role/access and revoke active sessions |
| `PATCH /auth/me` | Signed in | Set or clear the account's optional E.164 notification phone number |

Provider profile data, schedule semantics, tenant permissions, verification policy, and recommendation scoring are documented in [docs/provider_profiles.md](docs/provider_profiles.md).

Appointments are stored as timezone-aware timestamps and returned in UTC; slot metadata and the portal render times in `Asia/Kolkata` (IST). Booking/rescheduling requests are protected against retries with actor-scoped idempotency keys. A unique database constraint on each occupied 30-minute doctor slot arbitrates concurrent bookings; cancelled appointments release those locks. Migration `0006_transactional_appointments` backfills history and locks for existing active appointments and stops rather than silently rewriting overlapping active bookings.

Payment webhook receipts and captured/failed payment state are persisted by migration `0007_payment_webhook_idempotency`. Repeated event IDs with the same body are acknowledged without reapplying state; reuse of an event ID with different content is rejected. Migration `0010_admin_bootstrap_state` stores the one-time bootstrap lock/state, and `0011_appointment_invoices` adds the optional appointment association and unique billable-event constraint. Migrations `0013_payment_refunds` and `0014_invoice_refund_status` add refund audit/state records and distinct partial/full refund states. Demo attempts expire after 15 minutes, are owner- and invoice-scoped, and keep failure/cancellation separate from settlement. Migration `0009_align_metadata_indexes` aligns ORM indexes with the database and removes redundant token-hash uniqueness while preserving the unique index. Automated payment tests use simulated attempts or mocked Razorpay responses; they do not establish live credentials, webhook configuration, or settlement.

Run checks from the project root:

```sh
cd backend && pytest -q
cd ../frontend && npm test && npm run build
```

## Before production

This project still needs a real deployment/security and clinical-readiness program: managed secrets, HTTPS, a shared rate-limit store, MFA, monitoring, backup/restore tests, formal migrations review, staff administration and least privilege, privacy/legal review, payment reconciliation, clinical safety review, and tests against production-like infrastructure. Appointment booking is implemented in this project; integration with a real clinic's scheduling system and medical-record exchange remain additional work. Do not expose the development Compose stack or its database port to the public internet. See [docs/deployment.md](docs/deployment.md) for validation, backup, and deployment boundaries.
# AI-Healthcare-Voice-Assistant
# AI-Healthcare-Voice-Assistant

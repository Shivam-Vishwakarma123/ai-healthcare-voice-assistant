# CareVoice project structure

This guide focuses on source that helps explain, debug, and safely extend the application. `__pycache__`, `node_modules`, `dist`, and compiled assets are generated; they are not source-of-truth files.

## Compact tree

```text
.
├── docker-compose.yml
├── .env.example
├── README.md
├── docs/
│   ├── PROJECT_OVERVIEW.md
│   ├── PROJECT_STRUCTURE.md
│   ├── FRONTEND_GUIDE.md
│   ├── BACKEND_GUIDE.md
│   ├── DATABASE_GUIDE.md
│   ├── API_REFERENCE.md
│   ├── END_TO_END_FLOWS.md
│   ├── ADDING_FEATURES.md
│   └── RUN_AND_DEBUG.md
├── frontend/
│   ├── Dockerfile, package.json, vite.config.js, index.html
│   ├── tests/
│   └── src/
│       ├── main.jsx, App.jsx
│       ├── components/
│       ├── services/
│       └── *.css
└── backend/
    ├── Dockerfile, requirements.txt, alembic.ini
    ├── migrations/
    │   ├── env.py, script.py.mako
    │   └── versions/0001...0011_*.py
    ├── scripts/
    ├── tests/
    └── app/
        ├── main.py, cli.py, seed_demo.py
        ├── auth/, core/, controllers/, models/
        ├── repositories/, routes/, schemas/, services/
```

## Frontend

| Path | Responsibility and dependencies | Importance / safe-change note |
| --- | --- | --- |
| `frontend/src/main.jsx` | Vite entry; mounts the React application in `App`. | Essential. Global entry changes affect the whole UI. |
| `frontend/src/App.jsx` | Auth screen, browser session/token initialization, in-memory page navigation, role-based navigation visibility, top-level profile state, logout, account/profile updates. Renders `PortalScreens`, `Billing`, `VoiceAssistant`, and `AdminManagement`. | Essential. There is no React Router setup; page selection is component state except the reset/setup path handling. Keep auth and role navigation in sync with server behavior. |
| `frontend/src/services/api.js` | Shared `apiRequest`, API base URL selection, token header, JSON/multipart handling, HTTP/network errors, cached user parsing, currency display. | Essential cross-cutting helper. New API calls should use it, not ad hoc `fetch`. |
| `frontend/src/services/appointments.js` | IST date/time formatting and appointment idempotency-key creation. Used by directory/booking screens. | Essential to the booking UI. Preserve timezone handling and command key reuse on retries. |
| `frontend/src/components/PortalScreens.jsx` | Patient dashboard, symptom-check wrapper, notification placeholder, profile, provider dashboard, care directory, inline details, booking dialog, appointment list/history, unavailable screen. | Core portal module. Split only if behavior can remain consistent; add state and API handling here for these pages. |
| `frontend/src/components/Billing.jsx` | Staff invoice form; patient invoice/payment list; demo and Razorpay checkout UX. | Core billing page. Never add card inputs or trust client amounts as authoritative. |
| `frontend/src/components/VoiceAssistant.jsx` | Chat, browser speech recognition and synthesis, optional recorded audio upload, transcript confirmation, citations. | Core but provider-dependent. Preserve typed input, transcript review, cleanup of microphone tracks, and safety errors. |
| `frontend/src/components/PublicTriage.jsx` | Account-free symptom text form calling deterministic `/assistant/triage`. | Useful public safety UI; do not present the result as diagnosis or complete emergency screening. |
| `frontend/src/components/AdminManagement.jsx` | Platform/hospital administrator controls and aggregate/account tables. | Backend still enforces all permissions; UI must not be treated as security. |
| `frontend/src/components/NotificationContactForm.jsx` | Updates the current user's optional E.164 notification number using `/auth/me`. | Optional notifications contact settings, not an inbox. |
| `frontend/src/App.css`, `portal.css`, `healthcare.css` | App shell/auth styling, older portal styling, and healthcare portal/layout/component styling. | Presentation only. Check all responsive and reduced-motion states when changing layout. |
| `frontend/package.json`, `vite.config.js`, `index.html` | React/Vite dependencies, dev/test/build scripts, bundler config, and HTML entry. | Essential for frontend toolchain. Tests use Node's built-in test runner; do not add dependencies without a need. |
| `frontend/tests/` | Node tests for API request handling and appointment utilities. | Removing these does not change runtime but removes regression coverage for shared behavior. |

### Main component/page relationships

`App` controls which screen is mounted:

```text
App
├── AuthScreen (defined in App.jsx; login/register/bootstrap/reset)
├── DashboardPage
├── CareDirectoryPage
│   └── ProviderInlineDetails + booking dialog
├── AppointmentsPage
├── TriagePage
│   ├── PublicTriage
│   └── VoiceAssistant
├── ProfilePage
├── NotificationsPage (explicit placeholder)
├── Billing
└── ProviderDashboardPage / AdminManagement
```

Refer to [the frontend guide](./FRONTEND_GUIDE.md) for each page's calls, state, and limitations.

## Backend

| Path | Responsibility and dependencies | Importance / safe-change note |
| --- | --- | --- |
| `backend/app/main.py` | Creates FastAPI, CORS and exception handling, registers versioned routers, health checks, and imports models so metadata is registered. | Essential app composition. Router registration must happen here. |
| `backend/app/core/config.py` | Typed environment settings and startup validation for secrets, provider modes, CORS, and limits. | Essential. Never commit local `.env` secrets. |
| `backend/app/core/database.py` | SQLAlchemy `Base`, engine, session factory, and request-scoped `get_db`. | Essential persistence boundary. |
| `backend/app/core/email_validation.py`, `exceptions.py` | Shared normalized email validation and domain exceptions. | Shared helpers; reuse rather than copy validation/error types. |
| `backend/app/auth/security.py` | Argon2 hash/verify, JWT issue/parse, persisted/revocable auth sessions, current-user and role dependencies. | Security-critical. Test all changes against role and owner boundaries. |
| `backend/app/auth/rate_limit.py` | Authentication request limiting. | Security support; inspect implementation before changing authentication limits. |
| `backend/app/models/` | SQLAlchemy table definitions for users, patients, providers/appointments, billing, security/audit/notification, and knowledge documents/chunks. | Schema source-of-truth for ORM; every schema change needs a migration. |
| `backend/app/schemas/` | Pydantic patient/provider inputs and outputs; field validation and serialization. | API contract. Do not make persisted changes only in ORM without updating API schema. |
| `backend/app/routes/` | FastAPI endpoints: `auth_routes.py`, `patient_routes.py`, `provider_routes.py`, `assistant_routes.py`, `billing_routes.py`, `admin_routes.py`. | HTTP/auth boundaries; route prefixes are registered in `main.py`. |
| `backend/app/controllers/patient_controller.py` | Patient route coordination and maps domain exceptions to HTTP statuses. | Part of the more layered patient CRUD path. |
| `backend/app/repositories/patient_repository.py` | Owner-filtered SQLAlchemy queries and patient persistence. | Keep owner filters at query level. |
| `backend/app/services/patient_service.py` | Patient duplicate/ownership business rules around repository calls. | Patient domain logic. |
| `backend/app/services/` | Audit, notifications, LLM, speech-to-text, embeddings, RAG, triage, patient, and payment-provider integration. | Reuse the domain adapter/service where it exists; route organization varies by domain. |
| `backend/app/cli.py` | Interactive provisioning of hospital staff accounts. | Development/operations tool; use a secure terminal and avoid scripting a real password. |
| `backend/app/seed_demo.py` | Rerunnable fictional local demo dataset setup. | Development only. It is not an application migration or a reason to reset the database. |
| `backend/migrations/` | Alembic environment/template and ordered schema revisions `0001` through `0011`. | Essential to evolve PostgreSQL safely. Do not replace with `create_all`. |
| `backend/scripts/` | `evaluate_datasets.py`, `evaluate_models.py`, and `ingest_public_health.py`. | Optional operator/development tasks; inspect flags before invoking. |
| `backend/tests/` | Isolated API/database tests for auth, role boundaries, profiles, appointments, admin, billing, AI, triage, config, and demo seeding. | Essential safety net. Reuse fixtures and synthetic data patterns. |
| `backend/requirements.txt`, `alembic.ini`, `Dockerfile` | Python dependencies, Alembic script location, backend image/start command. | Essential runtime/tooling files. |

## Operations and documentation

- `docker-compose.yml` defines PostgreSQL, FastAPI, Vite, Ollama, and pgAdmin plus named volumes and health checks.
- `.env.example` documents setting names and development defaults; `.env` is local and ignored by `.gitignore`. Never print or copy its values into docs/issues.
- Root `README.md` explains setup, account/bootstrap, payment modes, safety, and user roles.
- `docs/deployment.md`, `docs/speech_to_text.md`, and the evaluation/source-registry documents cover specialized operations. Verify their assumptions against current source.
- `docs/PROJECT_GUIDE.html` and `.pdf` are pre-generated artifacts and are not changed by this Markdown guide set.

## Source of truth when files disagree

Prefer executable Python/JSX, schema definitions, migrations, and Compose configuration over old generated guides. For new work, update code, tests, migration (if needed), and the related current Markdown guide together. See [adding features](./ADDING_FEATURES.md) and [database safety](./DATABASE_GUIDE.md).

**Removal impact:** deleting `main.py`, `App.jsx`, shared API/database/auth modules, or router/model registration prevents core startup or requests from working. Removing a page/component removes that UI workflow; removing a model without a migration breaks persistence; removing a migration can strand existing databases at an incompatible revision. Removing tests reduces regression protection. Evaluation scripts, optional providers, and docs can be unused at runtime, but deleting them removes those specific operations or guidance. Files under `dist`, `node_modules`, and `__pycache__` are generated and should be recreated with their package/build tools rather than edited by hand.

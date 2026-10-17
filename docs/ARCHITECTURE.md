# CareVoice architecture

This page is retained as a short entry point. For current, source-verified details, start at [Project overview](./PROJECT_OVERVIEW.md) and continue through the [project structure](./PROJECT_STRUCTURE.md), [frontend](./FRONTEND_GUIDE.md), [backend](./BACKEND_GUIDE.md), [database](./DATABASE_GUIDE.md), and [API reference](./API_REFERENCE.md).

## Runtime shape

CareVoice is a development-oriented modular monolith:

```text
React/Vite browser
    -> FastAPI REST API
        -> authentication + role/ownership/tenant checks
        -> route/domain operations and services
        -> SQLAlchemy ORM
            -> PostgreSQL
        -> optional AI, transcription, payment, and notification integrations
```

Docker Compose defines the frontend, backend, PostgreSQL, Ollama, and pgAdmin services. Alembic upgrades the schema before the backend starts. The React app uses state-based page navigation; it does not have a general React Router configuration.

## Feature boundaries

- Owner-scoped patient profiles, provider discovery, recurring schedules, and appointment booking/lifecycle are implemented in the current source.
- Appointment creation uses an idempotency command record and database slot locks to guard retries and concurrent bookings.
- Billing supports a local simulated demo flow and optional Razorpay live checkout/signature verification/webhook handling. A demo payment is not a money transfer.
- Deterministic triage and AI chat are different paths. Triage is a limited rule-based safety check; chat uses a configurable model and optional, disabled-by-default RAG.
- Browser speech APIs and optional configured server-side transcription support voice input; they do not make this a clinically validated voice-triage system.
- The patient-facing notifications page and clinical-record exchange remain unconnected. Optional backend email/SMS is limited to generic sign-in reminders and delivery outcomes.

This is not a production-ready or clinically validated healthcare system. Use synthetic data only. See [Run and debug](./RUN_AND_DEBUG.md) for local operation and explicit limits.

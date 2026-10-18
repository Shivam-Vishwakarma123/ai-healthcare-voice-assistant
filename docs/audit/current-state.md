# CareVoice Healthcare Platform — Current-State Audit Report

**Date of Audit:** October 18, 2026  
**Auditor / Principal Architect:** AI Engineering Team  
**Repository Branch:** `fix/onboarding-demo-billing`  
**Current Head Commit:** `3d21ca6 set up`

---

## 1. Executive Summary

This document reports the baseline audit of the **CareVoice** healthcare voice assistant and patient portal repository. CareVoice is architected as a **modular monolith** with a modern Python FastAPI backend, a React 18 / Vite 6 frontend, and a PostgreSQL 16 relational database running in a Docker Compose development environment, supplemented by an Ollama local LLM instance and a pgAdmin container.

The codebase features substantial architectural foundations, including server-enforced role-based access control (RBAC) across five roles, cryptographic session tracking, transactional appointment slot locking, idempotent command patterns, and a dual-mode billing pipeline supporting both Razorpay hosted checkout and an explicit local demo simulation.

The objective of this engineering audit is to catalog verified implementations, identify architectural and security limitations, evaluate data and AI/ML pipelines, and establish a clear roadmap for production hardening and enterprise healthcare compliance.

---

## 2. Infrastructure & Environment Topology

### 2.1 Containerized Runtime Topology
The development environment is orchestrated via Docker Compose (`docker-compose.yml`) defining 5 interconnected services:

| Service Name | Container Name | Base Image / Build | Port Mappings | Healthcheck / Readiness | Persistence / Volume |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **db** | `healthcare-postgres` | `postgres:16-alpine` | `127.0.0.1:5432:5432` | `pg_isready -U healthcare_user -d healthcare_db` | `postgres_data:/var/lib/postgresql/data` |
| **backend** | `healthcare-backend` | `./backend` (Python 3.12-slim) | `127.0.0.1:8000:8000` | `GET /api/v1/health/ready` (checks `SELECT 1`) | Bind mount `./backend:/app` |
| **frontend** | `healthcare-frontend` | `./frontend` (Node 22-alpine) | `127.0.0.1:3000:5173` | Node `fetch('http://127.0.0.1:5173')` | Bind mount `./frontend:/app` + `frontend_node_modules` |
| **ollama** | `healthcare-ollama` | `ollama/ollama:latest` | `127.0.0.1:11434:11434` | `ollama list` | `ollama_data:/root/.ollama` |
| **pgadmin** | `healthcare-pgadmin` | `dpage/pgadmin4:latest` | `127.0.0.1:5050:80` | None (service dependent on `db: healthy`) | `pgadmin_data:/var/lib/pgadmin` |

### 2.2 Operational Verification
- **All 5 containers** are verified running and healthy.
- Port bindings are strictly bound to loopback `127.0.0.1`, preventing inadvertent external network exposure.
- Backend startup sequence executes `alembic upgrade head` before spawning `uvicorn app.main:app --host 0.0.0.0 --port 8000`.
- PostgreSQL migrations are current at revision `0014_invoice_refund_status`. `alembic check` passes with zero schema drift.

---

## 3. Backend Architecture Audit

### 3.1 Framework, Core, and Dependencies
- **FastAPI (0.115+) & Uvicorn**: Async ASGI framework with typed Pydantic models.
- **SQLAlchemy (2.0.x)**: Modern Mapped-column ORM with connection pooling.
- **Pydantic Settings**: Strongly typed configuration in `app/core/config.py` enforcing:
  - Strong password and secret length validation when `APP_ENV=production`.
  - Prohibition of wildcard `*` in `BACKEND_CORS_ORIGINS` when credential cookies/headers are enabled.
  - Strict boundary checks on LLM timeouts, max tokens, rate limits, and audio byte limits.
  - Safe restriction requiring `rzp_test_` keys in development/test when `PAYMENT_MODE=live`.

### 3.2 Route Handlers & Domain Modules
The backend API is mounted under prefix `/api/v1` with six route modules:

1. **`auth_routes.py` (465 LOC)**:
   - Registration (`/auth/register`): Creates patient accounts with Argon2id hashing.
   - Login (`/auth/login`): Supports email or username with rate limiting (5 attempts / 60s).
   - Session tracking (`/auth/me`, `/auth/logout`): Validates database-backed `AuthSession`.
   - Password reset (`/auth/password-reset/request`, `/auth/password-reset/confirm`): One-time sha256 token hashes with 30-minute expiry; requires SMTP configuration.
   - Platform Admin Bootstrap (`/auth/bootstrap/platform-admin`): One-time setup gated by `ADMIN_BOOTSTRAP_TOKEN` and database locking (`AdminBootstrapState`).

2. **`patient_routes.py` (47 LOC)**:
   - Full CRUD for patient health profiles (`/patients/`), strictly restricted to `require_roles("patient")` and scoped by `owner_user_id == current_user.id`.

3. **`provider_routes.py` (1165 LOC)**:
   - Hospital and doctor directory listing with multi-attribute filtering (city, specialty, language, consultation mode).
   - Verification queue management for administrators (`/providers/review-queue`).
   - Slot calculation engine (`/providers/doctors/{id}/available-slots`): Computes real available appointment slots in `Asia/Kolkata` (IST) from recurring doctor schedules against existing bookings.
   - Appointment booking (`POST /providers/appointments`): Protected by `AppointmentSlotLock` table and `AppointmentCommand` idempotency key.
   - Appointment lifecycle (`confirm`, `cancel`, `reschedule`, `history`): Immutable audit logging in `AppointmentEvent`.

4. **`assistant_routes.py` (435 LOC)**:
   - Deterministic emergency symptom triage (`POST /assistant/triage`): Multi-lingual red flag screening (English, Hindi, Hinglish) prior to any LLM invocation.
   - LLM Chat (`POST /assistant/chat`): Structured response validation with provider abstraction (Ollama, OpenAI, Azure).
   - Speech-to-text (`POST /assistant/speech-to-text`): Supports Web Speech API, OpenAI-compatible transcription, and IndicConformer adapter.
   - RAG search (`POST /assistant/rag/search`): Semantic/lexical retrieval over ingested public health documents.

5. **`billing_routes.py` (910 LOC)**:
   - Invoicing: Allows hospital staff/admin to issue invoices and patients to generate a server-priced invoice for upcoming fee-bearing appointments.
   - Dual checkout engine:
     - `demo`: Simulates payment outcomes locally without external API calls or payment card entry.
     - `live`: Server-side Razorpay order generation, HMAC SHA256 signature verification, and webhook event deduplication.
   - Refunds: Implements `manual_review` refund policy, tracking refund requests, status (`pending`, `processed`, `failed`), and idempotency.

6. **`admin_routes.py` (570 LOC)**:
   - Account provisioning: Platform and hospital admins can provision staff and doctor accounts with strict tenancy constraints.
   - User status management: Account deactivation, role adjustment, and session revocation.
   - Aggregate reporting, audit log inspection, and notification delivery history.

---

## 4. Frontend Architecture Audit

### 4.1 Framework, Bundler, and Build Pipeline
- **React 18.3.1** and **Vite 6.0.5** with `@vitejs/plugin-react`.
- Native ES Modules (`type: "module"`).
- Component-level architecture under `frontend/src/components/`:
  - `PortalScreens.jsx` (1,135 LOC): Core views (`DashboardPage`, `CareDirectoryPage`, `AppointmentsPage`, `ProfilePage`, `NotificationsPage`, `ProviderDashboardPage`).
  - `Billing.jsx` (334 LOC): Invoices, demo checkout, payment history, receipts.
  - `AdminManagement.jsx` (320 LOC): Role and tenancy administration.
  - `VoiceAssistant.jsx` (248 LOC): Audio capture, speech synthesis, and AI chat.
  - `PublicTriage.jsx` (69 LOC): Standalone emergency symptom screener on public landing.
- Design System & Styling:
  - `healthcare.css` (2,500+ LOC): Comprehensive CSS custom property theme token system with responsive breakpoints, light/dark mode support, focus outlines, and accessible form controls.
  - `portal.css`: Layout and component rules for portal workflows.
  - `App.css`: Base utility classes.

### 4.2 State Management & Accessibility
- State is managed via React hooks (`useState`, `useEffect`, `useMemo`, `useRef`).
- Client-side token storage in `localStorage` (`ahva_token` and `ahva_user`).
- Bilingual support: Dynamic toggle between English (`en`) and Hindi (`hi`).
- Dark mode: Three-way toggle (`system`, `light`, `dark`) persisting to `localStorage` and syncing with OS `prefers-color-scheme`.
- Accessibility: Focus management, ARIA landmarks, `cv-sr-only` screen-reader labels, mobile hamburger drawer with `Escape` key listeners and backdrop traps.

---

## 5. Database Schema & Data Integrity

### 5.1 Tables & Entity Relationships
The schema comprises 14 primary entities across 14 migrations:
1. `users`: Identity, authentication credentials, role, hospital/doctor bindings.
2. `auth_sessions`: Active user sessions with expiration and revocation timestamps.
3. `password_reset_tokens`: Cryptographic hash tokens for password recovery.
4. `patients`: Owner-scoped health profiles (age, gender, emergency contacts).
5. `hospitals`: Hospital organizations with verification status and metadata.
6. `doctors`: Clinicians with specialties, fees, consultation modes, and verification badges.
7. `doctor_qualifications`: Verified academic and clinical credentials.
8. `doctor_schedules`: Weekly recurring availability blocks with timezone awareness.
9. `appointments`: Consultations linking patient, doctor, and hospital.
10. `appointment_slot_locks`: Database-level unique constraints preventing double booking.
11. `appointment_commands`: Idempotency log for booking and rescheduling.
12. `appointment_events`: Immutable state transition history.
13. `invoices`, `payments`, `payment_refunds`, `payment_webhook_events`: Financial ledger.
14. `knowledge_documents`, `knowledge_chunks`: Vector and lexical RAG store.
15. `audit_logs`, `notification_deliveries`, `admin_bootstrap_state`: Compliance & operations.

---

## 6. Verification and Test Results

### 6.1 Backend Automated Test Suite
- Executed: `pytest -q` inside `healthcare-backend`.
- **Result:** **102 passed, 0 failed** in 32.69s.
- Test categories verified:
  - Account boundaries and patient data ownership (`test_account_boundaries.py`)
  - Authentication security and brute-force rate limiting (`test_auth_security.py`)
  - Multi-tenant RBAC enforcement (`test_rbac_authentication.py`)
  - Appointment concurrency, slot locking, and idempotency (`test_appointment_workflow.py`)
  - Billing checkout, webhook signature verification, and refunds (`test_billing_flow.py`)
  - Emergency triage rules and safety filters (`test_triage.py`, `test_rag_and_provider_safety.py`)
  - Deterministic synthetic dataset evaluation (`test_evaluation_harness.py`)

### 6.2 Frontend Automated Test Suite
- Executed: `node --test` inside `frontend`.
- **Result:** **25 passed, 0 failed** in 224ms.
- Test categories verified:
  - RBAC administration permissions and self-demotion guards.
  - API request wrapper, header management, and error handling.
  - Appointment payment eligibility and retry state transitions.
  - Timezone date/time formatting (IST).
  - Theme preference persistence and system media-query switching.

### 6.3 Build & Compilation Gate
- Executed: `npm run build` in `frontend`.
- **Result:** **Zero warnings**, producing clean production distribution in `frontend/dist/`.

# CareVoice Platform — Comprehensive Feature Inventory

**Audit Date:** October 18, 2026  
**Classification Standards:**
- **Working and tested:** Feature is implemented in frontend/backend, verified with passing automated tests.
- **Implemented but not adequately tested:** Code is complete, but edge-case tests or end-to-end integration coverage is sparse.
- **Partially implemented:** Functional foundations exist, but key business workflows, UI routes, or integrations are missing.
- **Broken:** Feature exhibits defects, runtime failures, or regressions under standard operation.
- **Missing:** Required by the product mission but no implementation exists in the codebase.
- **Blocked by external credentials or approvals:** Implementation is ready at the code level, but blocked from end-to-end live testing due to unconfigured third-party production credentials or legal approvals.

---

## 1. Domain Feature Matrix

| Feature Area | Specific Functionality | Status | Current Implementation Notes & Gaps |
| :--- | :--- | :--- | :--- |
| **Identity & Authentication** | Patient Registration | **Working and tested** | Public signup with Argon2id hashing, email normalization, strong password checks. |
| | Multi-role Login | **Working and tested** | Supports email or username login for all 5 roles with per-process rate limiting (5 attempts/min). |
| | Session Tracking & Revocation | **Working and tested** | Short-lived JWTs backed by database `AuthSession` records; revocable on sign-out and password reset. |
| | Password Reset (Forgot Password) | **Partially implemented** | SHA-256 token hashing and email trigger implemented; blocked if SMTP credentials are unset. |
| | Platform Admin Bootstrap | **Working and tested** | One-time locked setup with `ADMIN_BOOTSTRAP_TOKEN` via web UI and API; database concurrency locked. |
| | Multi-Factor Authentication (MFA) | **Missing** | No TOTP/SMS MFA implementation exists for privileged administrator or doctor roles. |
| **Authorisation & Permissions** | Server-Enforced RBAC (5 Roles) | **Working and tested** | Roles: `patient`, `doctor`, `hospital_staff`, `hospital_admin`, `platform_admin`. Authoritative in backend. |
| | Hospital Tenancy Scoping | **Working and tested** | Hospital admins and staff are strictly restricted to their assigned `hospital_id`. |
| | Patient Data Isolation | **Working and tested** | Patients can only read, update, or delete their own health profiles (`owner_user_id`). |
| | Last Platform Admin Protection | **Working and tested** | System prevents self-demotion or deactivation of the last remaining active platform admin. |
| | Resource Ownership Cross-Checks | **Implemented but not adequately tested** | Direct-API test matrix for every cross-hospital endpoint combination needs ongoing regression suite. |
| **Patient Management** | Patient Profile CRUD | **Working and tested** | Create, view, update, delete patient demographic and emergency profile data. |
| | Patient Consent Management | **Missing** | No explicit digital consent capture for data sharing, teleconsultation, or data retention. |
| | Medical History & Allergies | **Partially implemented** | Basic demographic info stored; structured clinical history/allergies/medications not yet modeled. |
| **Hospital & Branch Management** | Hospital Onboarding Request | **Partially implemented** | Admins can create hospitals, but public onboarding application workflow is not yet exposed to public users. |
| | Hospital Verification Review Queue | **Working and tested** | Admins can inspect pending hospitals, verify them, or reject them. Public directory only displays verified. |
| | Multi-Branch Management | **Missing** | Hospitals are modeled as single entities; parent organization with multiple geographic branches is not modeled. |
| | Department Configuration | **Working and tested** | Comma-delimited departments stored and displayed in directory. |
| **Doctor & Credential Management** | Doctor Profile & Bio | **Working and tested** | Full name, bio, experience years, primary specialty, additional specialties array (JSON). |
| | Academic & Clinical Qualifications | **Working and tested** | `doctor_qualifications` table with degree, institution, completion year, and verification status. |
| | Consultation Modes & Fees | **Working and tested** | Supports `in_person`, `online`, `phone` with integer `fee_minor` (paise). |
| | Doctor Verification Review | **Working and tested** | Admins verify clinician credentials before appearance in public search. |
| **Search & Discovery** | Multi-attribute Doctor Search | **Working and tested** | Filter by specialty, city, language, consultation mode, and name. |
| | Hospital Directory | **Working and tested** | Filter hospitals by name, city, department. |
| | AI Doctor Recommendations | **Working and tested** | Weighted scoring algorithm based on specialty, city, language, and consultation mode. |
| | Geolocation / Distance Sorting | **Missing** | No latitude/longitude coordinates or spatial indexing in database; relies on text city matching. |
| | Patient Ratings & Reviews | **Missing (By Design)** | Fabricated reviews are explicitly prohibited; real verified review collection pipeline not yet built. |
| **Scheduling & Availability** | Recurring Weekly Schedule Slots | **Working and tested** | Doctors configure days of week, start/end times, consultation mode, timezone (`Asia/Kolkata`). |
| | Dynamic Available Slot Calculation | **Working and tested** | Backend computes available 30-min slots for any future calendar date, subtracting existing bookings. |
| | Timezone Handling (IST) | **Working and tested** | Strictly pinned to `Asia/Kolkata` with explicit ISO calendar conversions. |
| **Appointments & Consultations** | Appointment Booking | **Working and tested** | Patients book available slots; backed by `AppointmentSlotLock` to prevent double booking. |
| | Idempotent Booking & Rescheduling | **Working and tested** | Enforced via `AppointmentCommand` table and `Idempotency-Key` headers. |
| | Rescheduling & Cancellation Rules | **Working and tested** | Patients and staff can reschedule/cancel upcoming appointments; past/completed visits are immutable. |
| | Audit Event Log | **Working and tested** | Every status transition (`scheduled`, `rescheduled`, `cancelled`, `completed`) recorded in `AppointmentEvents`. |
| | Teleconsultation Video/Audio Room | **Missing** | Teleconsultation link metadata placeholder exists; WebRTC/video room integration not implemented. |
| **Clinical Records & Consent** | Electronic Health Records (EHR) | **Missing** | Document storage, clinical notes, and prescription management are not yet integrated. |
| | External Interoperability (ABDM/FHIR)| **Missing** | Future integration boundary documented; M1/M2/M3 milestone adapters not yet implemented. |
| **Symptom Guidance & ML** | Deterministic Emergency Triage | **Working and tested** | High-precision red flag screening (English, Hindi, Hinglish); immediate 112/108 emergency escalation. |
| | AI Chat Assistant | **Working and tested** | Structured JSON response validation, bounds checks, persona enforcement, clinical disclaimers. |
| | Local LLM Integration (Ollama) | **Working and tested** | Connects to `healthcare-ollama` container (`llama3.2:1b-instruct-q4_K_M`). |
| | Public-Health RAG Pipeline | **Partially implemented** | Document ingestion, chunking, and vector retrieval exist; disabled by default pending domain corpus. |
| | Speech-to-Text Transcription | **Working and tested (Browser)** / **Partially (Server)** | Web Speech API works in browser; server-side Whisper/IndicConformer adapter implemented but unconfigured. |
| | Disease Prediction ML Pipeline | **Missing** | Predictive diagnostic model is not trained/deployed; relies on triage and LLM safety guidance. |
| **Billing & Payments** | Automated Appointment Invoicing | **Working and tested** | Patients can request invoice for upcoming fee-bearing appointments; stored doctor fee is authoritative. |
| | Manual Staff Invoicing | **Working and tested** | Hospital staff can issue custom service invoices. |
| | Demo Payment Simulation | **Working and tested** | Safe local development simulation with distinct success, failure, and cancellation paths. |
| | Razorpay Hosted Checkout | **Blocked by external credentials** | Server order creation, signature verification, and webhook handling implemented; needs live test keys. |
| | Manual Review Refund Workflow | **Working and tested** | Admin review queue, durable `payment_refunds` tracking, idempotency, refund status transitions. |
| **Notifications** | Audit Delivery Log | **Working and tested** | Notification delivery attempts recorded in database with status and failure codes. |
| | SMTP Email Reminders | **Blocked by external credentials** | Adapter implemented; requires valid SMTP server credentials. |
| | SMS Notification Adapter | **Blocked by external credentials** | Webhook JSON adapter implemented; requires external SMS provider endpoint and token. |
| | In-App Patient Notification Bell | **Partially implemented** | Notifications page exists in frontend UI; real-time push/inbox backend query is stubbed. |
| **Platform Administration** | Account Creation & Provisioning | **Working and tested** | Provision hospital admins, doctors, and staff with password policies. |
| | System Metrics & Overview | **Working and tested** | Real-time counts of users, hospitals, doctors, appointments, and billing totals. |
| | Compliance Audit Trail | **Working and tested** | Detailed JSON logging of actor, IP address, user-agent, action, and target resource. |
| **Docker & Operations** | Multi-container Compose Setup | **Working and tested** | Postgres, Backend, Frontend, Ollama, pgAdmin fully automated with healthchecks. |
| | Production Deployment Config | **Partially implemented** | Multi-stage production Dockerfiles and hardened compose profiles need formalization. |

---

## 2. Root Cause Analysis of Priority Gaps

1. **In-App Notification Inbox (`/notifications`)**:
   - *Current State:* The frontend renders a static notifications screen explaining that email/SMS are configured on the backend.
   - *Root Cause:* There is no dedicated `/patients/notifications` endpoint; notification rows in `notification_deliveries` are currently only exposed to administrators under `/admin/notifications`.
   - *Required Fix:* Add a patient-scoped notification feed endpoint allowing patients to see reminders and status updates directly in their portal.

2. **Cross-Hospital Resource Isolation Test Coverage**:
   - *Current State:* Backend controllers filter by `hospital_id`, but comprehensive end-to-end integration tests asserting that Hospital A admin cannot modify Hospital B doctors/appointments needed expansion.
   - *Root Cause:* Existing tests primarily focused on authentication and single-hospital flows.
   - *Required Fix:* Add dedicated multi-tenant boundary tests executing unauthorized cross-tenant mutations to verify HTTP 403/404 responses.

3. **Production Docker Deployment Configuration**:
   - *Current State:* `docker-compose.yml` mounts local source code volumes and runs `uvicorn --reload` and `vite` dev servers.
   - *Root Cause:* Designed for rapid local development rather than immutable production containers.
   - *Required Fix:* Create a production-hardened `compose.production.yaml` with multi-stage builds, Nginx static asset serving for React, Gunicorn/Uvicorn worker pools, and non-root user execution.

# CareVoice Healthcare Platform — Target Architecture Specification

**Architecture Pattern:** Modular Monolith with Layered Clean Domain Boundaries  
**Target Deployment:** Docker Compose / Containerized Micro-PaaS  
**Primary Language/Runtime:** Python 3.12 (FastAPI) + React 18 / Vite 6 + PostgreSQL 16  
**Date:** October 18, 2026  
**Principal Architect:** AI & Healthcare Systems Team  

---

## 1. Architectural Strategy & Rationale

### 1.1 The Modular Monolith Choice
CareVoice selects a **Modular Monolith** architecture as the optimal target pattern. 

**Why not microservices at this stage?**
- Distributed microservices introduce significant operational overhead: distributed transactions (two-phase commit / saga patterns), network latency, inter-service authentication, eventual consistency issues in appointment booking, and complex local developer environments.
- In healthcare platforms handling appointments, invoicing, and patient records, **atomic transactions (ACID)** across appointments, slot locks, and payments are essential to prevent double-booking and payment-status discrepancies.
- A well-designed modular monolith preserves strict domain separation through distinct module interfaces, dependency injection, and decoupled schemas. If a specific domain (such as AI/ML inference or real-time WebRTC consultation) requires independent scaling in the future, it can be cleanly extracted without rewriting the core business logic.

---

## 2. Target Domain Module Taxonomy

The application is structured into 15 cohesive domain modules:

```
backend/app/
├── modules/
│   ├── identity/               # 1. Identity, Auth, Password Hash, Sessions
│   ├── tenancy/                # 2. RBAC, Hospital Memberships, Context
│   ├── patient/                # 3. Patient Demographic Profiles, Records
│   ├── organization/           # 4. Hospitals, Branches, Departments
│   ├── provider/               # 5. Doctors, Qualifications, Verification
│   ├── discovery/              # 6. Provider Search, Filtering, Recommendations
│   ├── scheduling/             # 7. Schedules, IST Availability Slot Engine
│   ├── appointment/            # 8. Booking, Slot Locks, Lifecycle, State Machine
│   ├── clinical_consent/       # 9. Consent Ledger, Teleconsultation Consent
│   ├── triage_ai/              # 10. Stage-0 Red Flag Triage, LLM Adapter, RAG
│   ├── billing/                # 11. Invoicing, Razorpay Gateway, Demo Engine, Refunds
│   ├── notification/           # 12. Email, SMS, In-App Notification Feed
│   ├── audit/                  # 13. Regulatory Compliance Logs, Access History
│   ├── platform_admin/         # 14. Hospital Onboarding Review, User Provisioning
│   └── analytics/              # 15. Operational Metrics, Utilization Reports
```

### Module Responsibilities & Clear Interfaces

#### 1. Identity & Tenancy (`identity`, `tenancy`)
- **Interface:** `authenticate_user()`, `issue_session_token()`, `revoke_session()`, `resolve_security_context()`.
- **Invariants:** Every request must resolve an active `SecurityContext(user_id, role, hospital_id, doctor_id)`. All protected endpoints evaluate this context authoritatively on the server.

#### 2. Patient & Consent (`patient`, `clinical_consent`)
- **Interface:** `get_patient_profile()`, `record_consent(patient_id, consent_type, version, ip)`.
- **Invariants:** Patient health data is strictly owner-scoped. No clinician or staff member can access a patient record without an established appointment relationship or explicit consent.

#### 3. Organization & Provider (`organization`, `provider`)
- **Interface:** `create_hospital()`, `verify_hospital()`, `register_doctor()`, `verify_qualifications()`.
- **Invariants:** Doctors must belong to a verified hospital. Only verified hospitals and doctors with active schedules appear in public search results.

#### 4. Scheduling & Appointments (`scheduling`, `appointment`)
- **Interface:** `calculate_available_slots(doctor_id, date)`, `book_appointment(payload, idempotency_key)`, `reschedule_appointment()`, `cancel_appointment()`.
- **Invariants:** 
  - Time calculations are strictly localized to `Asia/Kolkata` (IST).
  - An atomic transaction creates the `Appointment` and locks the unique `(doctor_id, slot_start)` in `AppointmentSlotLock`.
  - Duplicate booking requests sharing the same `(actor_user_id, idempotency_key)` in `AppointmentCommand` return the cached appointment representation without double charging or double booking.

#### 5. Billing & Payments (`billing`)
- **Interface:** `create_appointment_invoice(appointment_id)`, `initiate_checkout(invoice_id)`, `verify_payment(order_id, payment_id, signature)`, `process_webhook(event)`, `request_refund(payment_id)`.
- **Invariants:**
  - Amount is calculated on the server from the doctor's stored fee (`doctor.fee_minor`).
  - Webhooks verify HMAC SHA256 signatures against the raw binary request payload.
  - Refund requests follow the configured policy (`manual_review` or `no_refunds`).

#### 6. Triage & AI Guidance (`triage_ai`)
- **Interface:** `evaluate_emergency_triage(text, lang)`, `generate_assistant_reply(messages)`.
- **Invariants:** Stage 0 deterministic triage executes with zero external dependencies. Stage 1 LLM chat runs only if emergency red flags are absent. Drug prescriptions and specific dosage recommendations are strictly intercepted and blocked.

#### 7. Notifications & Audit (`notification`, `audit`)
- **Interface:** `enqueue_notification(recipient, channel, event, template)`, `log_audit_event(actor, action, resource, details)`.
- **Invariants:** Delivery failures in external notification providers (SMTP/SMS) never roll back transactional healthcare workflows. Audit records are append-only.

---

## 3. Data Tier Architecture (PostgreSQL 16)

PostgreSQL remains the primary ACID relational store:
- **Connection Management:** Connection pool sized via SQLAlchemy `pool_size=10, max_overflow=20`.
- **Isolation Level:** `READ COMMITTED` default, with row-level locks (`SELECT ... FOR UPDATE`) or unique index constraints for slot allocation and idempotency.
- **Migration Pipeline:** Version-controlled Alembic migrations with strict zero-loss policies. Schema changes must be backward-compatible with preceding code revisions.

---

## 4. Frontend Architecture (React 18 + Vite 6)

### 4.1 Layered Architecture
```
frontend/src/
├── app/                  # App shell, root routing, global providers
├── components/           # Reusable UI library (buttons, inputs, cards, dialogs)
├── features/             # Domain views (auth, patient, care, billing, admin)
├── services/             # API client, auth token, theme persistence, IST date helpers
└── styles/               # healthcare.css (tokens), portal.css (layout)
```

### 4.2 Accessibility & UI Standards
- Adherence to **WCAG 2.2 AA** contrast ratios in both light and dark themes.
- Responsive breakpoints tested at 320px, 375px, 430px, 768px, 1024px, 1280px, and 1440px.
- Zero unexpected horizontal scrollbars (`overflow-x: hidden` on viewport roots).
- Keyboard accessibility: full tab index sequence, visible focus rings (`--cv-focus-ring`), and `Escape` key listeners for modal overlays and mobile navigation drawers.

---

## 5. Security & Isolation Matrix

```
Client Tier (Browser)
   │  HTTPS (TLS 1.3)
   ▼
Edge / Reverse Proxy (Nginx in Production / Vite Proxy in Dev)
   │  Security Headers, Rate Limiting, Static Asset Serving
   ▼
FastAPI Application Tier (Modular Monolith)
   ├── Auth Middleware (JWT Validation, Session Status Check)
   ├── Rate Limiting (5 req / 60s window)
   ├── Domain Controllers & Business Invariants
   └── ORM Layer (SQLAlchemy 2.0 Parameterized Queries)
   │
   ▼
Data & Integration Tier
   ├── PostgreSQL 16 (Relational Database, Persistent Volume)
   ├── Ollama LLM Container (Isolated Internal Docker Network)
   └── External Gateways (Razorpay API via TLS, SMTP Server)
```

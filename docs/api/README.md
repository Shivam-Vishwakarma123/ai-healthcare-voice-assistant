# CareVoice Platform — API Reference & Integration Guide

The complete API specification is documented in [API Reference](../API_REFERENCE.md).

## Quick Overview of API Groups

| Router Prefix | Domain | Primary Roles | Key Operations |
| :--- | :--- | :--- | :--- |
| `/api/v1/health` | System Status | Public | Liveness probe (`/health/live`), DB readiness probe (`/health/ready`) |
| `/api/v1/auth` | Identity & Sessions | Public / Authenticated | Register, login, session validation (`/me`), password reset, admin bootstrap |
| `/api/v1/patients` | Patient Portal | `patient` | Patient health profile CRUD, notification inbox (`/notifications`) |
| `/api/v1/providers` | Clinics & Appointments | Public / Multi-role | Doctor/hospital search, IST slot calculation, booking with idempotency, lifecycle |
| `/api/v1/assistant` | Triage & AI Guidance | Public / Authenticated | Emergency triage, safe AI chat, speech-to-text, RAG public health search |
| `/api/v1/billing` | Invoicing & Checkout | Patient / Staff / Admin | Invoice creation, Razorpay hosted checkout, demo simulation, refunds |
| `/api/v1/admin` | Hospital & Platform Admin | `hospital_admin`, `platform_admin` | Account provisioning, role modification, audit trails, delivery logs |

Interactive OpenAPI documentation is available in local development at:
- **Swagger UI:** <http://localhost:8000/docs>
- **ReDoc:** <http://localhost:8000/redoc>

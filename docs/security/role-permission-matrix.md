# CareVoice Platform — Role-Permission Matrix & Access Control Policy

**Standard:** OWASP ASVS v4.0.3 Chapter 4 (Access Control Verification)  
**Enforcement Level:** Server-Side Authoritative via FastAPI `Depends(get_current_user)` & `Depends(require_roles)`  
**Date:** October 18, 2026  

---

## 1. Principles of Access Control

1. **Deny by Default:** Any endpoint without explicit permissions defaults to rejecting unauthenticated requests (HTTP 401 Unauthorized) or unauthorized roles (HTTP 403 Forbidden).
2. **Server-Side Authoritative Enforcement:** Frontend navigation guards and button visibility are considered user-experience conveniences only. The server evaluates user identity, role, active session, and tenant ownership on every request.
3. **Tenant & Context Isolation:** A user assigned to `hospital_id = 1` cannot read or mutate data belonging to `hospital_id = 2`, even if they hold the `hospital_admin` or `hospital_staff` role.
4. **Least Privilege:** Users receive only the minimum access permissions necessary to perform their healthcare or administrative responsibilities.
5. **Separation of Platform vs Clinical Roles:** A `platform_admin` governs hospital verification, user accounts, and system health, but does not possess unrestricted access to private patient clinical profiles.

---

## 2. Comprehensive Endpoint Authorization Matrix

### Legend
- **`ALLOW`**: Permitted for this role without restriction.
- **`OWN`**: Permitted only for resources owned by the authenticated user (e.g. `owner_user_id == current_user.id`).
- **`HOSP`**: Permitted only for resources scoped to the user's assigned hospital (`hospital_id == current_user.hospital_id`).
- **`DOC`**: Permitted only for resources where the user is the assigned clinician (`doctor_id == current_user.doctor_id`).
- **`DENY`**: Explicitly forbidden (returns HTTP 403 or HTTP 404).
- **`PUB`**: Publicly accessible without authentication.

---

### 2.1 Authentication & System Endpoints (`/api/v1/auth`, `/api/v1/health`)

| Endpoint Path | HTTP Method | Public | Patient | Doctor | Hospital Staff | Hospital Admin | Platform Admin | Server Enforcement Rule |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| `/health/live` | `GET` | `ALLOW` | `ALLOW` | `ALLOW` | `ALLOW` | `ALLOW` | `ALLOW` | Unauthenticated liveness probe |
| `/health/ready` | `GET` | `ALLOW` | `ALLOW` | `ALLOW` | `ALLOW` | `ALLOW` | `ALLOW` | Verifies database `SELECT 1` |
| `/auth/register` | `POST` | `ALLOW` | `DENY` | `DENY` | `DENY` | `DENY` | `DENY` | Public registration creates `patient` accounts only |
| `/auth/login` | `POST` | `ALLOW` | `ALLOW` | `ALLOW` | `ALLOW` | `ALLOW` | `ALLOW` | Rate limited (5 attempts / 60s); returns JWT + session ID |
| `/auth/logout` | `POST` | `DENY` | `ALLOW` | `ALLOW` | `ALLOW` | `ALLOW` | `ALLOW` | Revokes the current `auth_sessions` record |
| `/auth/me` | `GET` | `DENY` | `OWN` | `OWN` | `OWN` | `OWN` | `OWN` | Validates session; returns active user details |
| `/auth/me` | `PATCH` | `DENY` | `OWN` | `OWN` | `OWN` | `OWN` | `OWN` | Update user phone number |
| `/auth/password-reset/request` | `POST` | `ALLOW` | `ALLOW` | `ALLOW` | `ALLOW` | `ALLOW` | `ALLOW` | Rate limited; sends token hash via email |
| `/auth/password-reset/confirm` | `POST` | `ALLOW` | `ALLOW` | `ALLOW` | `ALLOW` | `ALLOW` | `ALLOW` | Validates one-time token; revokes all existing sessions |
| `/auth/bootstrap/status` | `GET` | `ALLOW` | `ALLOW` | `ALLOW` | `ALLOW` | `ALLOW` | `ALLOW` | Reports whether platform admin setup is open |
| `/auth/bootstrap/platform-admin`| `POST` | `ALLOW` | `DENY` | `DENY` | `DENY` | `DENY` | `DENY` | Single-use setup gated by `ADMIN_BOOTSTRAP_TOKEN` |

---

### 2.2 Patient Profile Endpoints (`/api/v1/patients`)

| Endpoint Path | HTTP Method | Public | Patient | Doctor | Hospital Staff | Hospital Admin | Platform Admin | Server Enforcement Rule |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| `/patients/` | `POST` | `DENY` | `OWN` | `DENY` | `DENY` | `DENY` | `DENY` | `require_roles("patient")`; sets `owner_user_id = user.id` |
| `/patients/` | `GET` | `DENY` | `OWN` | `DENY` | `DENY` | `DENY` | `DENY` | Returns only profiles owned by `user.id` |
| `/patients/{id}` | `GET` | `DENY` | `OWN` | `DENY` | `DENY` | `DENY` | `DENY` | Scoped by `owner_user_id == user.id`; 404 if not found |
| `/patients/{id}` | `PATCH` | `DENY` | `OWN` | `DENY` | `DENY` | `DENY` | `DENY` | Scoped by `owner_user_id == user.id` |
| `/patients/{id}` | `DELETE` | `DENY` | `OWN` | `DENY` | `DENY` | `DENY` | `DENY` | Permanently deletes own demographic record |

---

### 2.3 Provider Directory & Appointment Endpoints (`/api/v1/providers`)

| Endpoint Path | HTTP Method | Public | Patient | Doctor | Hospital Staff | Hospital Admin | Platform Admin | Server Enforcement Rule |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| `/providers/hospitals` | `GET` | `ALLOW` | `ALLOW` | `ALLOW` | `ALLOW` | `ALLOW` | `ALLOW` | Public directory returns only verified hospitals |
| `/providers/hospitals/{id}` | `GET` | `ALLOW` | `ALLOW` | `ALLOW` | `ALLOW` | `ALLOW` | `ALLOW` | Hospital public details |
| `/providers/hospitals` | `POST` | `DENY` | `DENY` | `DENY` | `DENY` | `DENY` | `ALLOW` | `require_roles("platform_admin")` |
| `/providers/hospitals/{id}` | `PATCH` | `DENY` | `DENY` | `DENY` | `DENY` | `HOSP` | `ALLOW` | Hospital Admin can only edit own hospital |
| `/providers/doctors` | `GET` | `ALLOW` | `ALLOW` | `ALLOW` | `ALLOW` | `ALLOW` | `ALLOW` | Returns only verified, active doctors |
| `/providers/doctors/{id}` | `GET` | `ALLOW` | `ALLOW` | `ALLOW` | `ALLOW` | `ALLOW` | `ALLOW` | Verified doctor profile and schedules |
| `/providers/doctors/{id}` | `PATCH` | `DENY` | `DENY` | `DOC` | `DENY` | `HOSP` | `ALLOW` | Doctor edits own profile; Hospital Admin edits hospital doctors |
| `/providers/doctors/{id}/available-slots` | `GET` | `ALLOW` | `ALLOW` | `ALLOW` | `ALLOW` | `ALLOW` | `ALLOW` | Computed IST 30-min available booking slots |
| `/providers/recommendations` | `POST` | `ALLOW` | `ALLOW` | `ALLOW` | `ALLOW` | `ALLOW` | `ALLOW` | Weighted doctor matching algorithm |
| `/providers/review-queue` | `GET` | `DENY` | `DENY` | `DENY` | `DENY` | `DENY` | `ALLOW` | Verification queue for unverified providers |
| `/providers/hospitals/{id}/verification` | `PATCH` | `DENY` | `DENY` | `DENY` | `DENY` | `DENY` | `ALLOW` | Platform Admin verifies/rejects hospital |
| `/providers/doctors/{id}/verification` | `PATCH` | `DENY` | `DENY` | `DENY` | `DENY` | `DENY` | `ALLOW` | Platform Admin verifies/rejects doctor |
| `/providers/appointments` | `POST` | `DENY` | `ALLOW` | `DENY` | `DENY` | `DENY` | `DENY` | Patient booking with slot lock & idempotency key |
| `/providers/appointments` | `GET` | `DENY` | `OWN` | `DOC` | `HOSP` | `HOSP` | `ALLOW` | Scoped by role: Patient sees own; Doctor sees assigned |
| `/providers/appointments/{id}/confirm` | `POST` | `DENY` | `DENY` | `DOC` | `HOSP` | `HOSP` | `ALLOW` | Clinician or staff marks appointment confirmed |
| `/providers/appointments/{id}/cancel` | `PATCH` | `DENY` | `OWN` | `DOC` | `HOSP` | `HOSP` | `ALLOW` | Patient or staff cancels future appointment |
| `/providers/appointments/{id}/reschedule` | `PATCH` | `DENY` | `OWN` | `DENY` | `HOSP` | `HOSP` | `ALLOW` | Atomic slot transfer with idempotency |
| `/providers/appointments/{id}/history` | `GET` | `DENY` | `OWN` | `DOC` | `HOSP` | `HOSP` | `ALLOW` | Immutable status transition audit log |

---

### 2.4 AI Assistant & Triage Endpoints (`/api/v1/assistant`)

| Endpoint Path | HTTP Method | Public | Patient | Doctor | Hospital Staff | Hospital Admin | Platform Admin | Server Enforcement Rule |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| `/assistant/triage` | `POST` | `ALLOW` | `ALLOW` | `ALLOW` | `ALLOW` | `ALLOW` | `ALLOW` | Public deterministic red-flag triage |
| `/assistant/chat` | `POST` | `DENY` | `ALLOW` | `ALLOW` | `ALLOW` | `ALLOW` | `ALLOW` | Authenticated chat with safety post-filter |
| `/assistant/speech-to-text/config` | `GET` | `DENY` | `ALLOW` | `ALLOW` | `ALLOW` | `ALLOW` | `ALLOW` | Audio transcription provider settings |
| `/assistant/speech-to-text` | `POST` | `DENY` | `ALLOW` | `ALLOW` | `ALLOW` | `ALLOW` | `ALLOW` | Audio transcription (max 10MB) |
| `/assistant/rag/search` | `POST` | `DENY` | `ALLOW` | `ALLOW` | `ALLOW` | `ALLOW` | `ALLOW` | Semantic vector search on public health docs |

---

### 2.5 Billing & Invoicing Endpoints (`/api/v1/billing`)

| Endpoint Path | HTTP Method | Public | Patient | Doctor | Hospital Staff | Hospital Admin | Platform Admin | Server Enforcement Rule |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| `/billing/config` | `GET` | `DENY` | `ALLOW` | `ALLOW` | `ALLOW` | `ALLOW` | `ALLOW` | Returns active payment mode (`demo` or `live`) |
| `/billing/invoices` | `GET` | `DENY` | `OWN` | `DENY` | `HOSP` | `HOSP` | `ALLOW` | Patient sees own invoices; staff sees hospital invoices |
| `/billing/payments` | `GET` | `DENY` | `OWN` | `DENY` | `HOSP` | `HOSP` | `ALLOW` | Payment history scoped to owner or hospital |
| `/billing/invoices` | `POST` | `DENY` | `DENY` | `DENY` | `HOSP` | `HOSP` | `ALLOW` | Staff issues custom service invoice |
| `/billing/appointments/{id}/invoice` | `POST` | `DENY` | `OWN` | `DENY` | `HOSP` | `HOSP` | `ALLOW` | Patient requests invoice for own appointment |
| `/billing/checkout` | `POST` | `DENY` | `OWN` | `DENY` | `DENY` | `DENY` | `DENY` | Creates Razorpay order or demo attempt |
| `/billing/demo/complete` | `POST` | `DENY` | `OWN` | `DENY` | `DENY` | `DENY` | `DENY` | Completes demo payment simulation (demo mode only) |
| `/billing/verify` | `POST` | `DENY` | `OWN` | `DENY` | `DENY` | `DENY` | `DENY` | Verifies Razorpay HMAC SHA-256 signature |
| `/billing/webhooks/razorpay` | `POST` | `PUB` | `PUB` | `PUB` | `PUB` | `PUB` | `PUB` | Validates HMAC signature against raw body |
| `/billing/refunds` | `GET` | `DENY` | `OWN` | `DENY` | `HOSP` | `HOSP` | `ALLOW` | Scoped refund list |
| `/billing/refunds` | `POST` | `DENY` | `DENY` | `DENY` | `DENY` | `HOSP` | `ALLOW` | Administrator submits refund request |

---

### 2.6 Administration Endpoints (`/api/v1/admin`)

| Endpoint Path | HTTP Method | Public | Patient | Doctor | Hospital Staff | Hospital Admin | Platform Admin | Server Enforcement Rule |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| `/admin/overview` | `GET` | `DENY` | `DENY` | `DENY` | `DENY` | `HOSP` | `ALLOW` | Aggregated metrics scoped by hospital |
| `/admin/users` | `GET` | `DENY` | `DENY` | `DENY` | `DENY` | `HOSP` | `ALLOW` | List staff & doctor accounts (scoped) |
| `/admin/accounts` | `POST` | `DENY` | `DENY` | `DENY` | `DENY` | `HOSP` | `ALLOW` | Provision doctor or staff accounts |
| `/admin/users/{id}` | `PATCH` | `DENY` | `DENY` | `DENY` | `DENY` | `HOSP` | `ALLOW` | Update user status, role, or active flag |
| `/admin/audit-logs` | `GET` | `DENY` | `DENY` | `DENY` | `DENY` | `HOSP` | `ALLOW` | Compliance audit trail |
| `/admin/notifications` | `GET` | `DENY` | `DENY` | `DENY` | `DENY` | `HOSP` | `ALLOW` | Notification delivery logs |

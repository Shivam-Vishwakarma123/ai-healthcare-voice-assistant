# CareVoice Platform — Security and Privacy Findings Audit

**Audit Standard:** OWASP Application Security Verification Standard (ASVS 4.0.3) Level 2 & NIST SSDF  
**Compliance Context:** Digital Personal Data Protection Act (DPDP Act, India 2023) Healthcare Guidelines  
**Date:** October 18, 2026  
**Auditor:** Principal Security & Systems Architect  

---

## 1. Threat Model & Security Boundaries

### 1.1 Trust Domains & Boundaries
The platform defines four distinct trust domains:
1. **Public Internet / Untrusted Client Tier:** Web browsers, mobile devices, external webhooks. All input arriving across this boundary is untrusted.
2. **Application Boundary (FastAPI API Gateway):** Authentication filter, TLS termination, CORS validation, rate limiting, and request schema validation via Pydantic.
3. **Internal Service Network (Docker Bridge):** Internal communication between Backend, PostgreSQL, and Ollama. Accessible only via loopback on the host (`127.0.0.1`).
4. **Data Persistence Tier (PostgreSQL):** Stores hashed credentials, patient demographic data, appointment records, and financial transaction metadata.

### 1.2 Core Assets & Sensitivity Classification
- **Critical (Tier 1):** User passwords (hashed), JWT secrets, database connection credentials, payment gateway webhook secrets.
- **High (Tier 2 - Sensitive Personal Data / Health Data):** Patient demographic data, medical triage notes, emergency symptoms, appointment history, clinician schedules.
- **Medium (Tier 3):** Hospital listings, verified clinician profiles, public educational materials.
- **Low (Tier 4):** System logs, aggregated anonymized counts.

---

## 2. Authentication & Session Management (OWASP ASVS V2 & V3)

### 2.1 Cryptographic Password Storage
- **Mechanism:** Implemented using `pwdlib` with the `argon2` algorithm (`argon2id` variant).
- **Parameters:** Memory cost: 64 MiB (`m=65536`), time cost: 3 iterations (`t=3`), parallelism: 4 threads (`p=4`). Meets and exceeds OWASP password storage recommendations.
- **Timing Attack Mitigation:** Authentication code executes `dummy_password_hash()` in constant time even when an unknown email/username is supplied, preventing account enumeration via timing discrepancies.

### 2.2 Token Lifecycle & Revocation
- **Access Tokens:** Signed JWTs using `HS256` with an enforced minimum 256-bit secret key. Default expiration is 20 minutes (`ACCESS_TOKEN_MINUTES=20`).
- **Database Session Binding:** Each access token embeds a unique `session_id` (JTI). The backend validates that the session exists in the `auth_sessions` table and has not been revoked (`revoked_at IS NULL`) or expired on every authenticated request.
- **Revocation Triggers:** Explicit user logout (`/auth/logout`) and password changes revoke the relevant database session immediately, terminating compromised tokens before natural expiration.

### 2.3 Rate Limiting & Brute-Force Abuse Prevention
- **Implementation:** `enforce_auth_rate_limit()` in `backend/app/auth/rate_limit.py`.
- **Threshold:** 5 failed attempts per client IP/identifier within a sliding 60-second window. Returns HTTP 429 Too Many Requests with informative retry headers.
- **Finding (P2 - Architecture):** The rate limiter currently maintains state in per-process memory (`collections.defaultdict`). In a multi-worker or horizontally scaled cluster, rate limiting state will not be shared across replicas. A shared key-value store (e.g. Redis) is required for distributed production deployments.

---

## 3. Authorisation & Tenancy Isolation (OWASP ASVS V4)

### 3.1 Role-Based Access Control (RBAC)
- Five distinct roles are enforced at the router and controller level:
  - `platform_admin`: Platform-wide governance, hospital verification review, user role assignment.
  - `hospital_admin`: Hospital-scoped user and provider management for their assigned `hospital_id`.
  - `hospital_staff`: Operational scheduling and invoice creation within their assigned `hospital_id`.
  - `doctor`: Profile and schedule management; access to consultations where assigned as the clinician.
  - `patient`: Owner-scoped profile, appointments, and billing.
- **Finding:** The authorization checks are executed server-side via FastAPI dependencies (`get_current_user`, `require_roles`). Frontend navigation guards are strictly navigational and never trusted as security boundaries.

### 3.2 Insecure Direct Object References (IDOR) & Tenant Isolation
- **Patient Profile:** `patient_routes.py` enforces `owner_user_id == user.id`. Direct requests to `/patients/{id}` for an unowned ID return HTTP 404 (preventing existence enumeration) or HTTP 403.
- **Hospital Scope:** Hospital admins and staff cannot query or mutate records from other hospitals; queries include explicit `hospital_id == current_user.hospital_id` filters.
- **Self-Demotion Safeguard:** The platform admin update handler checks `SELECT count(*) FROM users WHERE role = 'platform_admin' AND is_active = true`. If an admin attempts to remove their own admin role while being the last remaining admin, the request is rejected with HTTP 409 Conflict.

---

## 4. Input Validation, Injection & Data Integrity (OWASP ASVS V5)

### 4.1 SQL Injection
- **Framework:** SQLAlchemy ORM 2.0. All database queries utilize parameterized statement builders (`select()`, `insert()`, `update()`) or compiled ORM relationships.
- **Direct Queries:** Readiness probe uses parameterized `text("SELECT 1")`. No raw string concatenation is used in SQL statements.

### 4.2 Cross-Site Scripting (XSS) & Content Security
- **Frontend Escaping:** React automatically HTML-encodes all JSX string interpolations, preventing DOM-based and Reflected XSS.
- **Markdown & Chat Output:** Voice assistant chat responses are strictly validated through a Pydantic schema requiring plain text strings, preventing arbitrary HTML tag injection.
- **Recommendation:** Deploy a strict `Content-Security-Policy` (CSP) header in production Nginx configuration (`default-src 'self'`).

### 4.3 Payment & Webhook Signature Verification
- **Order Creation:** Stored doctor fees in the database are authoritative. Client requests cannot specify or manipulate consultation fees.
- **HMAC Signature Check:** Razorpay payment callbacks verify `hmac.new(key_secret, f"{order_id}|{payment_id}", hashlib.sha256).hexdigest()` against `razorpay_signature` using `hmac.compare_digest()` to prevent timing attacks.
- **Webhook Deduplication:** Incoming Razorpay webhooks record the `x-razorpay-event-id` in the `payment_webhook_events` table within a serializable transaction to prevent replay attacks.

---

## 5. Privacy, Healthcare Data Governance & DPDP Act Compliance

### 5.1 DPDP Act (India 2023) Assessment
1. **Notice & Consent:**
   - *Requirement:* Data fiduciaries must present an explicit notice explaining what personal data is collected and for what purpose before processing.
   - *Current State:* The application displays prominent landing and registration disclaimers.
   - *Finding:* A structured consent ledger capturing timestamp, IP, version, and purpose (consultation, billing, communication) should be formalized in the database before production deployment.
2. **Data Minimization:**
   - The application only requires full name, email, age, and gender for patient registration. No unnecessary biometric or financial details (card numbers, CVV) are ever stored.
3. **Data Retention & Erasure (Right to Erasure):**
   - The patient profile endpoint supports `DELETE /patients/{id}`, permanently clearing personal demographic records while retaining decoupled financial transaction records required by tax and accounting regulations.

---

## 6. Summary of Security Action Items

| Priority | Finding / Vulnerability | Remediation | Status |
| :--- | :--- | :--- | :--- |
| **High** | Per-process rate limit storage | Migrate rate limit storage to Redis when deploying multiple replicas | Planned for Phase L |
| **Medium** | Missing Security Response Headers | Add `Strict-Transport-Security`, `X-Content-Type-Options`, `X-Frame-Options`, and `CSP` | Implemented in Production Nginx config |
| **Medium** | Formal Patient Consent Ledger | Create dedicated `patient_consents` table tracking DPDP consent events | Design documented in Target Architecture |
| **Low** | Lack of Multi-Factor Authentication | Implement TOTP MFA for `platform_admin` and `hospital_admin` accounts | Post-MVP Roadmap |

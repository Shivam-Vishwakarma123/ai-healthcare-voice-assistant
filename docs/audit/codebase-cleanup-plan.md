# CareVoice Codebase Cleanup and Restructuring Plan

**Date:** 2026-10-18  
**Project:** AI Healthcare Voice Assistant (React + FastAPI + PostgreSQL + Docker)  
**Author:** Antigravity / Claude Code

---

## 1. Executive Summary

This plan outlines the audit findings, candidate classifications, risk assessments, and step-by-step remediation strategy for cleaning up and optimizing the CareVoice codebase. The application is substantially developed, with active end-to-end functionality including role-based access control (RBAC), multi-hospital provider scheduling, AI clinical triage, voice assistant interactions, and Razorpay payment integration (with active Test Mode auto-capture and webhook event handling).

The cleanup protects all active functionality, preserves existing user modifications, and removes only verified safe redundancies.

---

## 2. Baseline Status & Verification

### 2.1 Git Status & In-Flight User Modifications (MUST BE PRESERVED)
- **Modified files:**
  - `backend/app/routes/billing_routes.py`: Contains active implementation of Razorpay payment auto-capture (`payment_capture=1`, capturing `authorized` payments upon verification), enhanced webhook handling for `order.paid` and missing payment entities, and idempotency persistence safety.
  - `backend/app/services/payment_service.py`: Contains active implementation of `capture_payment` method on `RazorpayPaymentService` and `PaymentService` protocol.
- **Untracked files:**
  - `backend/tests/test_razorpay_test_mode.py`: Test suite for Razorpay Test Mode checkout and verification.
  - `backend/tests/test_razorpay_webhooks.py`: Comprehensive test suite for webhook signature validation, idempotency, refund processing, and capture events.
  - `.vscode/settings.json`: Local IDE setting (`"python.terminal.useEnvFile": true`).

**Policy:** These in-flight changes are active features and will be completely preserved without rollbacks or overwrites.

### 2.2 Baseline Test Execution Results
- **Backend Test Suite:**
  - Command: `docker exec healthcare-backend pytest`
  - Result: **124 passed**, 2 warnings in 37.51s (100% pass rate).
- **Frontend Test Suite:**
  - Command: `npm test` (via native `node --test`)
  - Result: **25 passed**, 0 failed in 228ms (100% pass rate).
- **Frontend Production Build:**
  - Command: `npm run build` (Vite 6.4.4)
  - Result: 45 modules transformed, output in `dist/assets/` built in 1.51s with zero errors.
- **Docker Compose Configuration:**
  - `docker compose config` (dev): **Valid**
  - `docker compose -f compose.production.yaml config` (prod): **Valid**

---

## 3. Detailed Audit Findings & Candidate Classification

Each candidate is categorized using the required risk schema:
- **SAFE:** Clearly unused, verified, zero risk to runtime or tests.
- **REVIEW:** Indirectly or dynamically used; requires deep tracing before touch.
- **KEEP:** Active runtime code, tests, documentation, or essential configuration.

### 3.1 Empty Directories
| Directory | Findings & Evidence | Classification | Proposed Action |
|-----------|---------------------|----------------|-----------------|
| `frontend/docs/audit` | Empty folder; zero files. Root `docs/` is the project docs home. | **SAFE** | Remove directory |
| `backend/docs/security` | Empty folder; zero files. Real docs exist in root `docs/security/`. | **SAFE** | Remove directory |
| `backend/docs/audit` | Empty folder; zero files. Real docs exist in root `docs/audit/`. | **SAFE** | Remove directory |
| `backend/docs/ml` | Empty folder; zero files. Real docs exist in root `docs/ml/`. | **SAFE** | Remove directory |
| `backend/docs/architecture` | Empty folder; zero files. Real docs exist in root `docs/architecture/`. | **SAFE** | Remove directory |
| `backend/docs/api` | Empty folder; zero files. Real docs exist in root `docs/api/`. | **SAFE** | Remove directory |
| `backend/docs/operations` | Empty folder; zero files. Real docs exist in root `docs/operations/`. | **SAFE** | Remove directory |

### 3.2 Source Files Reachability
| File / Module | Findings & Evidence | Classification | Proposed Action |
|---------------|---------------------|----------------|-----------------|
| All 46 `.py` files in `backend/app/` | Traced across routes, models, services, core, and repositories. All imported and active. | **KEEP** | Retain all backend app source files |
| All 20 JS/JSX/CSS files in `frontend/src/` | Traced across components, services, and styles. All reachable. | **KEEP** | Retain all frontend source files |
| `AdminUserRow.js` in `frontend/src/components/` | Authored as `.js` with `createElement` so `node --test` can test it without Babel/JSX compiler. | **KEEP** | Retain as `.js` to preserve native Node test execution |

### 3.3 Unused Imports
| File | Unused Import | Classification | Proposed Action |
|------|---------------|----------------|-----------------|
| `backend/app/controllers/patient_controller.py` | `status` from `fastapi` | **SAFE** | Remove unused import |
| `backend/app/models/knowledge.py` | `Float` from `sqlalchemy` | **SAFE** | Remove unused import |
| `backend/app/models/security.py` | `Text` from `sqlalchemy` | **SAFE** | Remove unused import |
| `backend/app/routes/provider_routes.py` | `and_` from `sqlalchemy` | **SAFE** | Remove unused import |
| `backend/tests/test_appointment_workflow.py` | `pytest`, `AppointmentEvent` | **SAFE** | Remove unused test imports |
| `backend/tests/test_billing_flow.py` | `get_current_user` | **SAFE** | Remove unused test import |
| `backend/tests/test_onboarding_and_demo_payments.py` | `get_current_user` | **SAFE** | Remove unused test import |
| `backend/tests/test_patient_notifications_and_isolation.py` | `Invoice` | **SAFE** | Remove unused test import |
| `backend/tests/test_provider_directory.py` | `Appointment` | **SAFE** | Remove unused test import |
| `backend/tests/test_provider_profiles.py` | `datetime`, `timedelta`, `timezone` | **SAFE** | Remove unused test imports |
| `backend/tests/test_rag_and_provider_safety.py` | `create_access_token` | **SAFE** | Remove unused test import |
| `backend/tests/test_razorpay_webhooks.py` | `IntegrityError` | **SAFE** | Remove unused test import |
| `backend/app/main.py` | `from app import models` | **KEEP** | Intentional side-effect import to register ORM models |
| `frontend/src/main.jsx` | `import "./App.css";` | **SAFE** | Remove duplicate import (`App.jsx` already imports it) |

### 3.4 Duplicate Helper Functions & Business Logic
| Functionality | Locations | Classification | Proposed Action |
|---------------|-----------|----------------|-----------------|
| `_as_utc(value: datetime) -> datetime` | `app.auth.security`, `app.routes.auth_routes`, `app.routes.billing_routes`, `app.routes.provider_routes` (100% duplicate) | **SAFE** | Centralize in `app.auth.security` as `as_utc` and import across routes |
| Password & confirmation validators (`validate_strong_password`, `validate_confirmation`, `strip_full_name`) | `app.routes.auth_routes`, `app.routes.admin_routes`, `app.schemas.patient` | **SAFE** | Consolidate common validators in `app.core.validators` |

### 3.5 Styling & CSS Hygiene
| Area | Findings & Evidence | Classification | Proposed Action |
|------|---------------------|----------------|-----------------|
| `frontend/src/App.css` | Contains 61 obsolete CSS selectors (`.auth-art`, `.auth-wrap`, `.art-copy`, `.mobile-brand`, `.switch`, etc.) from an early mockup that were completely replaced by `.cv-auth-*` in `healthcare.css`. | **SAFE** | Clean up obsolete unused rules while strictly preserving font imports, CSS reset, and classes used by `Billing.jsx` and `VoiceAssistant.jsx` |
| Font & Theme Tokens | `healthcare.css` (3347 LOC) defines complete `--cv-*` token architecture with dark/light themes. `App.css` provides the Google Font loading and basic HTML element resets. | **KEEP** | Maintain theme tokens and accessible contrast |

### 3.6 Dependency Manifests
| Manifest | Analysis | Classification | Proposed Action |
|----------|----------|----------------|-----------------|
| `backend/requirements.txt` | 12 dependencies: `fastapi`, `uvicorn[standard]`, `sqlalchemy`, `alembic`, `psycopg[binary]`, `pydantic-settings`, `email-validator`, `pytest`, `httpx`, `python-multipart`, `python-jose[cryptography]`, `pwdlib[argon2]`. Every single package is in active use. | **KEEP** | No packages to remove; perfectly lean manifest |
| `frontend/package.json` | 4 dependencies: `react`, `react-dom`, `@vitejs/plugin-react`, `vite`. All are essential. | **KEEP** | Retain all frontend dependencies |

### 3.7 Repository Hygiene & Secrets Protection
| Item | Findings & Evidence | Classification | Proposed Action |
|------|---------------------|----------------|-----------------|
| `.gitignore` | Missing `.vscode/`, `.coverage`, `coverage/`, `*.log`, `*.egg-info/`, `.DS_Store`. | **SAFE** | Update `.gitignore` with comprehensive patterns |
| Local Secrets | Verified `.env` is untracked and in `.gitignore`. `.env.example` has placeholder-only secrets. No hardcoded API keys exist. | **KEEP** | Preserve current configuration hygiene |

---

## 4. Execution Plan & Validation Gates

The cleanup will execute in four focused, non-destructive batches:

### Batch 1: Repository Hygiene & Empty Directory Removal
- Remove empty directories: `backend/docs/*`, `frontend/docs/*`.
- Update `.gitignore` with `.vscode/`, coverage, and log patterns.
- Gate: Run `git status` to ensure only intended changes occurred.

### Batch 2: Python Codebase Cleanup (Backend)
- Remove verified unused imports across `backend/app/` and `backend/tests/`.
- Centralize `as_utc` and common validators (`strip_full_name`, `validate_strong_password`, `validate_confirmation`) into `app.core.validators` and `app.auth.security`.
- Update imports across route files while preserving all route endpoints and contracts.
- Gate: Run `docker exec healthcare-backend pytest` to verify all 124 tests pass.

### Batch 3: Frontend Codebase & CSS Cleanup
- Remove duplicate `./App.css` import in `frontend/src/main.jsx`.
- Clean up obsolete, unused CSS selectors in `frontend/src/App.css`.
- Ensure dark/light themes, contrast, and layout remain pixel-perfect.
- Gate: Run `npm test` (all 25 tests pass) and `npm run build` (clean Vite bundle).

### Batch 4: Full System Validation & Final Audit Reporting
- Re-run full test suites (backend 124 tests, frontend 25 tests).
- Re-validate Docker Compose configurations.
- Verify patient management, RBAC, appointment booking, and Razorpay payment flows remain intact.
- Generate `docs/audit/codebase-cleanup-report.md`.

# CareVoice Platform — Migration and Implementation Plan

**Objective:** Safely transition CareVoice from a development scaffold to a secure, modular, production-ready multi-hospital healthcare platform without data loss or functional disruption.  
**Execution Strategy:** Phased, test-gated, reversible increments.  
**Date:** October 18, 2026  

---

## 1. Migration Principles & Zero-Downtime Safeguards

1. **Data Preservation Above All:**
   - Database volumes (`postgres_data`) must never be dropped or recreated as a shortcut.
   - All schema modifications must use versioned Alembic migrations (`alembic upgrade head`) with forward and backward compatibility.
2. **Reversible Increments:**
   - Every code refactoring or enhancement must be committed in small, self-contained stages that can be rolled back without cascading breaks.
3. **Automated Verification Gates:**
   - Every stage must pass all existing backend tests (`pytest`), frontend tests (`node --test`), frontend build (`vite build`), and container healthchecks before advancing to the next stage.

---

## 2. Phased Implementation Roadmap

```
┌──────────────────────────────────────────────────────────┐
│ Phase 1: Audit, Governance & Documentation (Complete)    │
│  - System inventory, threat model, ML evaluation         │
└────────────────────────────┬─────────────────────────────┘
                             │
┌────────────────────────────▼─────────────────────────────┐
│ Phase 2: Role-Permission Matrix & Tenancy Fortification  │
│  - Endpoint-by-endpoint RBAC documentation & enforcement │
│  - Formalize cross-hospital boundary test suite          │
└────────────────────────────┬─────────────────────────────┘
                             │
┌────────────────────────────▼─────────────────────────────┐
│ Phase 3: Patient Notification Feed & Consent Ledger     │
│  - Patient notification inbox endpoint & UI integration  │
│  - Digital health consent data model                     │
└────────────────────────────┬─────────────────────────────┘
                             │
┌────────────────────────────▼─────────────────────────────┐
│ Phase 4: UI/UX Refinement & Responsive Polish            │
│  - Complete English/Hindi dictionary consolidation       │
│  - Viewport verification across mobile & desktop widths  │
└────────────────────────────┬─────────────────────────────┘
                             │
┌────────────────────────────▼─────────────────────────────┐
│ Phase 5: Production Docker Hardening & Release Artifacts │
│  - Production multi-stage Dockerfiles                    │
│  - Hardened compose.production.yaml with Nginx reverse   │
│    proxy and security headers                            │
└────────────────────────────┬─────────────────────────────┘
                             │
┌────────────────────────────▼─────────────────────────────┐
│ Phase 6: Final Verification, Acceptance & Handover       │
│  - Complete test rerun, coverage check, audit summary    │
└──────────────────────────────────────────────────────────┘
```

---

## 3. Detailed Phase Breakdown

### Phase 2: Role-Permission Matrix & Tenancy Fortification (Phase C & D)
- **Action:** Formulate `docs/security/role-permission-matrix.md` mapping all 5 roles against every API endpoint.
- **Backend Task:** Implement dedicated multi-tenant integration tests in `backend/tests/test_tenant_isolation.py` verifying that:
  - Hospital Admin A cannot update, view, or delete Hospital B's clinicians, schedules, or invoices.
  - Doctor A cannot view consultations assigned to Doctor B unless assigned to the same hospital.
  - Patients cannot query other patients' records (IDOR protection).
- **Verification Gate:** `pytest backend/tests/test_tenant_isolation.py` passes 100%.

### Phase 3: Patient Notification Feed & Consent Ledger (Phase J & G)
- **Action:** Add a patient-facing notification feed endpoint (`GET /api/v1/patient/notifications`) retrieving user-scoped notices (booking reminders, payment status updates, cancellation alerts) from `notification_deliveries`.
- **Frontend Task:** Connect the `NotificationsPage` component in `frontend/src/components/PortalScreens.jsx` to this endpoint with real-time loading, empty, and item states.
- **Verification Gate:** Frontend tests pass; simulated notification appears in the patient portal.

### Phase 4: Frontend Bilingual & Accessibility Harmonization (Phase E)
- **Action:** Centralize bilingual strings in `frontend/src/services/i18n.js` to eliminate remaining inline English strings when Hindi (`hi`) is active.
- **Verification Gate:** `npm test` and `npm run build` pass with zero warnings. Verify mobile viewport layout at 320px, 375px, 768px, and 1280px.

### Phase 5: Production Docker Hardening (Phase L)
- **Action:** Create `compose.production.yaml` with:
  - Multi-stage production `frontend/Dockerfile.prod` compiling static assets served by unprivileged Nginx with security headers (`CSP`, `HSTS`, `X-Frame-Options`, `X-Content-Type-Options`).
  - Production `backend/Dockerfile.prod` executing Gunicorn with Uvicorn workers as a non-root user.
  - Hardened environment variable requirements forbidding default development secrets.
- **Verification Gate:** `docker compose -f compose.production.yaml config` passes with zero errors.

### Phase 6: Operational Runbook & Final Acceptance (Phase M, N, O)
- **Action:** Deliver operational runbooks for backup/restore, migration execution, secret rotation, and payment gateway onboarding.
- **Verification Gate:** Full test suite execution across backend and frontend containers.

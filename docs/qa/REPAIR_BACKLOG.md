# CareVoice QA Repair Backlog

Updated from the live audit on 2026-10-25. Items distinguish confirmed code/runtime findings from flows that still lack test evidence.

## P1 — Finish hosted checkout close and payment outcome coverage

- **Evidence:** Runtime is safely in Razorpay Test Mode; a Test Mode order request returned 200 and the hosted checkout iframe became visible. The synthetic invoice remains unpaid and its order remains uncompleted. Automated inspection did not identify the hosted iframe's close control.
- **Affected:** `frontend/src/components/Billing.jsx`, `backend/app/routes/billing_routes.py`, `backend/app/services/payment_service.py`, Razorpay checkout QA harness.
- **Next step:** Identify and verify the supported close/cancel interaction without entering payment details. Then exercise the provider's documented Test Mode success/failure cases, signature verification, and webhook idempotency using synthetic fixtures.
- **Acceptance:** Closing or failing checkout leaves the invoice unpaid; verified Test Mode success alone marks it paid; invalid signatures and duplicate webhooks do not change state.

## P1 — Complete write workflows and tenant-boundary checks

- **Evidence:** UI login, role landing, refresh persistence, logout, dashboard loads, and several read routes pass for all five roles. Booking, schedule conflicts, profile/notification writes, clinical mutations, admin mutations, patient ownership, and cross-hospital isolation were not exercised live.
- **Affected:** Provider, patient, clinical, assistant, billing, and admin route families.
- **Next step:** Continue with the marked RBAC test accounts and isolated synthetic records. Verify validation, persistence, duplicate submissions, 401/403/404 behavior, and tenant boundaries without changing non-test data.
- **Acceptance:** Expected reads and writes pass for each role; cross-owner/tenant access is denied; state remains correct after refresh and repeated requests.

## P2 — Expand rendered UI matrix beyond the patient overview

- **Evidence:** Patient Overview passed Light/Dark at all eight requested widths and System mode under both emulated OS preferences. Hindi navigation and 390px overflow passed. Other roles/routes and complete translation coverage were not inspected in every combination.
- **Affected:** `frontend/src/App.jsx`, shared theme tokens, role pages, forms, tables, modals, toasts, and mobile navigation.
- **Next step:** Run the route-by-route visual matrix for every role at 320, 375, 390, 430, 768, 1024, 1280, and 1440px; cover Light, Dark, System light, System dark, English, and Hindi where applicable.
- **Acceptance:** No clipped controls or unintended overflow; readable contrast and visible focus; translations, toasts, and mobile navigation work across tested pages.

## P2 — Reduce or split the frontend bundle

- **Evidence:** Production build succeeds with a 609.99 kB minified JavaScript chunk, above Vite's 500 kB advisory threshold.
- **Affected:** `frontend/src/App.jsx` and Vite build configuration.
- **Next step:** Inspect bundle composition and consider lazy-loading major role workspaces/pages.
- **Acceptance:** Reduce the main chunk or document an intentional threshold, then rerun build and route smoke checks.

## Closed / verified in this run

- **Development payment-mode default risk:** default and example configuration now use Test Mode; development/test validation rejects Demo and Live modes, and a live-prefixed key is rejected. Backend suite passes with the new guard.
- **Startup/access blocker:** Docker daemon access worked with granted permission; Compose stack is healthy and the backend readiness endpoint returns 200.
- **Demo fixture readiness:** the idempotent local demo seeder completed with zero creations; one fixed-marker synthetic service invoice was created/reused for Test Mode QA. No records were deleted.
- **Demo seeder patient-safety guard:** an unsafe legacy fixture branch could attach synthetic records to an existing unmarked patient. It now requires `is_test_account=True`; a regression test verifies that unmarked patient receives no seeded clinical rows. Pytest-generated PDFs are isolated in temporary directories. Thirteen generated PDFs observed during this audit were removed because they were absent at the start; the database and pre-existing medical-document image were preserved.

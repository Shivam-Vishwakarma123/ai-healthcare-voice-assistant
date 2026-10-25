# CareVoice UI/UX Audit

**Run date:** 2026-10-25  
**Result:** **PASS for visual/layout coverage** — all 27 signed-in role views passed the English/Hindi, Light/Dark/System, and responsive matrix. Two 320 px clipping defects and several visible Hindi strings were fixed. Dedicated accessibility and full dynamic-translation review remain open.

## Design system review

- The app already centralizes colors, spacing, radii, typography, focus rings, and theme aliases in `frontend/src/healthcare.css`.
- **Fixed:** dark mode previously tinted the page, sidebar, cards, and borders green. The dark palette now uses neutral slate surfaces with green reserved for primary actions, active navigation, and meaningful status accents.
- **Fixed:** the shared font stack now uses Inter for body text, Manrope for display headings, and Noto Sans Devanagari plus common system Indic families for Hindi glyphs.
- **Fixed:** the primary button shadow used malformed CSS (`var(--cv-accent)1a`), which browsers reject. Replaced it with a valid `color-mix()` value tied to the primary accent.
- **Fixed:** dashboard insight and health-record preview text was small and dense for clinical summaries. Summary/record body text now uses a larger size and more relaxed line height. Notification items now have clear separation, readable copy, and aligned status badges.
- **Fixed:** at 320 px, patient insight cards and privacy panels retained desktop minimum widths and were clipped. Their grids now shrink to the available width.
- **Fixed:** Hindi DPDP Privacy showed English status/control copy. The visible status, PIN link, verification, guide, and export copy now follows the selected language. The secure share PIN no longer defaults to a predictable `1234`.
- Before/after: dark screenshots now have a charcoal/slate canvas and lighter neutral cards with green accents, instead of green-tinted panels throughout. The notification view now presents distinct row cards. Longer clinical text uses a clearer reading rhythm.

## Visual and interaction coverage

| Area | Result | Evidence / scope |
|---|---|---|
| All roles and signed-in views | **PASS** | Five roles, 27 role views, 436 viewport/theme/language checks; no clipping, empty views, page errors, or failed API responses |
| Responsive layout | **PASS** | Each role view at 320, 430, 768, and 1440 px; patient Overview also at 375, 390, 1024, and 1280 px |
| Light, Dark, and System theme | **PASS** | Every role view changed through all three modes in both interface languages; OS Light/Dark emulation updated System mode |
| English and Hindi | **PASS with copy follow-up** | Every view checked in both language modes; DPDP copy fixed after screenshot review. Dynamic server messages and all medical terminology still need editorial review |
| Patient Health Records | **PASS (interaction)** | All 12 record tabs were activated; each reported selected state and rendered its panel |
| Patient Overview charts | **PASS (interaction)** | All physiological metric tabs and time-range buttons were activated |
| Doctor workspace | **PASS (desktop smoke)** | Role workspace renders. The seven tabs and Ambient Scribe/Protocol Monitor also passed in the existing role audit |
| Hospital staff dashboard | **PASS (desktop smoke)** | Reception queue and operation metrics visible |
| Hospital admin and platform admin | **PASS (desktop smoke)** | Administration management workspace visible for each role |
| Notifications | **PASS (visual recheck)** | 24 items displayed as separated rows with channel/status badges; screenshot captured in updated dark palette |
| Billing | **PASS (visual smoke)** | Razorpay Test Mode status and unpaid invoice/Pay now action visible; no checkout was submitted |
| Sign-in | **PASS (smoke)** | Each of five synthetic roles signed in through the rendered form |
| Patient appointment, symptom, assistant, profile, notifications | **PASS (render smoke)** | Views mounted; receipt modal opened and closed; mutation/response outcomes were not submitted |
| DPDP Privacy | **PASS (visual)** | Patient view in both languages/themes; Hindi Dark screenshot at 320 px inspected after localization and PIN default fix |
| Public password recovery/bootstrap | **NOT TESTED** | No live visual inspection in this run |
| Toast, modal, mobile navigation, focus/keyboard, screen reader | **NOT TESTED** | Requires targeted interaction audit |
| Keyboard, focus, and screen-reader behavior | **NOT TESTED** | Needs a dedicated accessibility audit |

## Browser diagnostics

The full role/view matrix recorded zero uncaught page errors, failed API responses, and layout findings across 436 checks. The first concurrent workflow run hit a QA login timeout while the matrix was signing in; rerunning the workflow sequentially passed. No payment or clinical write was submitted.

Role screenshots are stored in ignored `frontend/qa-screenshots/` files, including `patient-overview-320-dark-hi.png`, `patient-privacy-320-dark-hi.png`, `patient-overview-dark-updated.png`, and `notifications-dark-refresh.png`. Existing source screenshots in `docs/screenshots/` and `frontend/` were inspected as additional references. The screenshots are local development data and do not establish clinical or production readiness.

## Remaining design QA

- Review all medical terminology and API-provided/dynamic messages with a Hindi editor.
- Check mobile drawer behavior, dialogs, toasts, focus visibility, and touch targets at 320–430 px with keyboard and assistive technology.
- Measure contrast for semantic states and focus indicators in both themes.
- Address the 613.52 kB minified main chunk warning through measured lazy loading; the current build succeeds.

## Screenshot-driven modal and workflow recheck (2026-10-25)

- Fixed crowded appointment rows: visit, fee/payment state, and action controls now align in separate responsive groups; Hindi appointment statuses are localized.
- Fixed the clinical-record modal on 320 px screens, where the report body previously collapsed between a tall patient header and action footer. The report now has a usable single scroll area, compact mobile metadata, and a visible responsive action footer. Browser assertions passed at 320, 768, and 1440 px.
- Assistant panels now align as equal columns. Assistant infrastructure failures show a localized, non-technical fallback instead of exposing model names or Docker commands. Symptom label/help text now have explicit separation, and the form fills its available responsive column.
- Provider profile, booking, receipt, appointment history, reschedule, and clinical-record dialogs passed fit/close checks. Symptom submission and assistant response/fallback checks passed using non-personal synthetic prompts.
- Latest rerun: 436 all-role language/theme/responsive checks with zero visual findings or page/API errors; focused browser workflow audit passed with zero page errors; frontend tests 13/13; production build passed with a 614.48 kB main-chunk advisory.

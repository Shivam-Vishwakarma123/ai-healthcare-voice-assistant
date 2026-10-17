# Frontend guide

The UI is a React single-page application bundled and served by Vite. It has no configured React Router dependency: `App.jsx` stores the selected page in React state and renders the corresponding page component. A couple of auth flows use explicit browser paths (`/setup/administrator` and `/reset-password`).

## Entry point, API, and shared state

- `frontend/src/main.jsx` mounts `<App />`.
- `frontend/src/App.jsx` owns the access token, cached account, language, current page, patient profile list, and newly booked appointment.
- `frontend/src/services/api.js` exports `apiRequest(path, token, options)`. It uses `VITE_API_BASE_URL` (default `http://localhost:8000/api/v1`), adds JSON content type for JSON bodies, leaves multipart content type to the browser, adds `Authorization: Bearer …`, parses response JSON, and raises useful HTTP/network errors. Aborted requests remain `AbortError`s.
- `localStorage` keys: `ahva_token`, `ahva_user`, and `carevoice_language`. The token is an access token and expires; on startup the app calls `/auth/me` instead of trusting cached role data. This is browser storage, not an HttpOnly cookie.
- Protected routes are not present as a router layer. The app conditionally renders signed-in screens after token/account loading; API dependencies are the real security boundary.

## Authentication screens and lifecycle

`AuthScreen` is defined inside `App.jsx`; `authMode` selects landing, login, register, bootstrap, reset-request, or reset-password. `submitAuth` sends `POST /auth/login`, `/auth/register`, or `/auth/bootstrap/platform-admin`; it stores the returned token/account. Role determines initial selected page: patients go to Overview; other roles go to Provider dashboard.

On startup, `App` calls public `/auth/bootstrap/status`; when a token exists it calls `/auth/me`, and for a patient loads `/patients/`. A 401/403 invokes `signOut`, which calls `/auth/logout` and clears local storage. A network failure is surfaced without pretending sign-out or account loading succeeded. Password reset request and confirmation call the corresponding auth routes. The reset page clears a browser-stored session before rendering the form.

`changeAuthMode` updates only the bootstrap path specially; the rest of the login/register mode is UI state. The `popstate` handler recognizes bootstrap setup; it is not a general client-side routing system.

## Page map and behavior

| Page/component | Entry/navigation | API and state | What to know before changing |
| --- | --- | --- | --- |
| `DashboardPage` (`PortalScreens.jsx`) | Overview in patient navigation; provider roles also see dashboard-style operational summary | Fetches appointments, doctors, hospitals with `Promise.allSettled`; metrics and upcoming visits are derived in React | A failed endpoint is shown separately; lists are not pushed live. Refresh/revisit refetches. |
| `ProfilePage` + `App.saveProfile` | Patient Health profile | `POST /patients/` for first profile, `PATCH /patients/{id}` thereafter; parent `App` owns profile data | Account creation and patient-profile creation are separate. Values are Pydantic-validated at API. Delete requires a browser confirmation and calls `DELETE`. |
| `CareDirectoryPage` | Find care | Paginated `/providers/doctors` and `/providers/hospitals`; search, optional recommendation `/providers/recommendations`; profile details fetched lazily from detail endpoints | Detail responses are cached per type/id and expanded inline. Loading/error/retry state is local to a card. Directory supports abortable fetches. |
| Appointment booking dialog | Opened from a doctor card in Find care | Reads `/providers/doctors/{id}/available-slots`; `POST /providers/appointments` with doctor, ISO datetime, consultation type, notes, and `Idempotency-Key` | Key is reused only for an identical retry payload. The UI requires returned ID and `scheduled` status before success and stores the response for immediate appointment display. |
| `AppointmentsPage` | Appointments navigation | Loads `/providers/appointments`; cancel/confirm/reschedule and history call their respective provider endpoints | Role-scoped data is provided by the backend. Local state is updated/refetched after mutation; this is not real-time push. |
| `ProviderDashboardPage` | Provider dashboard for clinicians, hospital staff/admins, platform admins | `/providers/dashboard`; modifies profiles/schedules, adds hospital/doctor data, and platform review actions through provider endpoints | UI differs by role. Backend scope validation is required for every action. |
| `AdminManagement` | Administration, visible to `platform_admin` and `hospital_admin` | Parallel loads: overview, users, appointments, payments, audit logs, notification deliveries, hospitals, doctors; create accounts/update role or activation | Platform admin can manage accounts differently from a hospital admin. Backend filters tenant scope and forbids self-role/status changes. |
| `Billing` | Patient and staff/admin roles allowed by the UI | Loads invoices/config/payments and for staff billable appointments; creates invoices; starts demo or Razorpay flow | Demo checkout has no card input, no provider call, and explicit simulated success/failure/cancel. In live mode browser Checkout returns IDs/signature; server verifies before marking paid. |
| `TriagePage` + `PublicTriage` | Symptom check | Public `POST /assistant/triage`, no token; symptom text is sent as `text` | Deterministic emergency/safety heuristics, not diagnosis. The page explicitly warns that it cannot rule out emergencies. |
| `VoiceAssistant` | Assistant; also embedded under TriagePage | Authenticated `/assistant/chat`, `/assistant/speech-to-text/config`, optional multipart `/assistant/speech-to-text` | Conversations live in component state only. Browser recognition may use browser-vendor services. User reviews transcript before submit. `speechSynthesis` reads aloud on request. |
| `NotificationsPage` | Notifications | No inbox API is called | Deliberate placeholder: appointment reminders/messages are not displayed here. Backend delivery logs are admin-visible operational records, not an inbox. |
| `NotificationContactForm` | Embedded in admin management | `PATCH /auth/me` for current user's phone number | Optional E.164 contact setting; phone numbers are not verified. |

### Doctor and hospital workspaces

`ProviderDashboardPage` is the entry component for doctor, hospital staff/admin, and platform administrator workspaces. `GET /providers/dashboard` returns a role-specific shape:

- Doctor: linked doctor profile, hospital, and scoped appointments.
- Hospital staff/admin: hospital and its clinicians/appointments, according to role.
- Platform admin: platform-wide operational summary and review queue access.

The screen edits doctor profile fields/qualifications and replaces recurring schedules through `PUT /providers/doctors/{id}/schedules`; hospital admins edit their hospital and add doctors. The platform administrator creates/reviews hospitals and verification records. Schedule times are whole-minute local wall-clock ranges with an IANA timezone, and backend checks reject overlaps/invalid timezones.

## Form validation, loading, and refresh conventions

- Use controlled React state for forms and disable submit while a request is in flight.
- Keep API validation authoritative; frontend checks improve feedback but do not replace Pydantic and role/ownership checks.
- Catch endpoint errors and show them through `role="alert"` notices. Do not swallow a failed data request as an empty successful result.
- Directory uses `AbortController` when query/page changes. Avoid applying stale results after abort.
- Most successful mutations explicitly reload relevant state. A new appointment is merged into the appointment screen immediately, then normal API load maintains canonical state.
- The app has no global query cache, Redux store, WebSocket, or polling layer; treat data as fetched snapshots.

## Accessibility and language

Navigation is button/state based and indicates active page; inline profile detail uses `aria-expanded`/`aria-controls`; booking uses focus management and Escape handling. CSS includes reduced-motion behavior. Supported pages have English/Hindi strings, but do not assume every message is translated. Keep semantic labels and text fallbacks when extending forms.

## Safe extension recipe

1. Identify the page and its owning state in `App.jsx` or `PortalScreens.jsx`.
2. Add an API call with `apiRequest`; define request/response expectations from `docs/API_REFERENCE.md`.
3. Model pending, empty, error, success, and retry states explicitly.
4. For sensitive data, implement server role/tenant/owner checks first; hiding the UI is not security.
5. Add a test under `frontend/tests/` for shared formatting/request behavior where applicable.
6. Run `docker compose exec -T frontend npm test` and `docker compose exec -T frontend npm run build`.

For guided examples, see [Adding features](./ADDING_FEATURES.md). For API response contracts, see [API reference](./API_REFERENCE.md).

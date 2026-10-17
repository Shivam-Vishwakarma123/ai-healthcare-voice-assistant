# CareVoice API reference

Versioned API paths below include `/api/v1`, configured by `API_V1_PREFIX`; routers are registered in `backend/app/main.py`. The home endpoint is `GET /` and FastAPI's interactive OpenAPI UI is `/docs`. Both are unversioned.

**Role notation:** `Public` means no bearer token; `Signed-in` means any valid user; other roles are named explicitly. `HA` = hospital admin, `HS` = hospital staff, `PA` = platform admin. Backend role/scope checks are authoritative. Standard errors include 401 invalid/expired token, 403 forbidden role/scope, 404 missing or not visible resource, 409 uniqueness/state conflict, 422 request validation, plus endpoint-specific provider errors.

## Health and authentication

| Method + path | Access | Request | Response / behavior | Frontend caller |
| --- | --- | --- | --- | --- |
| `GET /` | Public | — | `{message}` | None |
| `GET /health/live` | Public | — | `{status:"alive", service:"backend"}` | Operations |
| `GET /health/ready` | Public | — | DB `SELECT 1`; healthy JSON or 503 | Operations/Compose health check |
| `GET /health` | Public | — | Readiness-compatible alias | Operations |
| `GET /auth/bootstrap/status` | Public | — | `{setup_available, reason}` | `App.jsx` |
| `POST /auth/bootstrap/platform-admin` | Public + bootstrap secret | `full_name,email,password,password_confirmation,bootstrap_token` | 201 `{access_token,token_type,expires_in,user}`; one-time operation | `App.jsx` setup form |
| `POST /auth/register` | Public | `full_name,email,password` (10–128 chars) | 201 token envelope; always creates role `patient` | `App.jsx` |
| `POST /auth/login` | Public | `email,password` | Token envelope and public user object | `App.jsx` |
| `POST /auth/logout` | Signed-in | Bearer token | 204; revokes current session | `App.signOut` |
| `POST /auth/password-reset/request` | Public | `email` | 202 `{message}`; requires SMTP setup to send reset link | `App.jsx` |
| `POST /auth/password-reset/confirm` | Public | `token,new_password` | `{message}`; token must be valid, unused, unexpired | `App.jsx` |
| `GET /auth/me` | Signed-in | Bearer token | `{id,full_name,email,role,phone_number}` | `App.jsx`, `NotificationContactForm` |
| `PATCH /auth/me` | Signed-in | `{phone_number}` (null or E.164 `+...`) | Updated public user object | `NotificationContactForm` |

Password reset request explicitly reports unavailable configuration if SMTP is not configured. Email/password registration/login are rate-limited. See [backend authentication](./BACKEND_GUIDE.md#authentication-and-authorization).

## Patient profiles

All endpoints require role `patient`, and IDs are additionally scoped to the authenticated owner.

| Method + path | Request/query | Response / behavior | Frontend caller |
| --- | --- | --- | --- |
| `POST /patients/` | `full_name,email,age,gender` | 201 patient `{id,full_name,email,age,gender,created_at}`; 409 duplicate | `App.saveProfile` |
| `GET /patients/` | `skip` (>=0), `limit` (1–100; default 50) | Owner's patient-profile array | `App` account initialization |
| `GET /patients/{patient_id}` | — | Owner's profile; non-owned/not found is 404 | No separate page call currently |
| `PATCH /patients/{patient_id}` | Any subset of `full_name,email,age,gender` | Updated patient; duplicate email 409 | `App.saveProfile` |
| `DELETE /patients/{patient_id}` | — | 204; UI asks for confirmation first | `App.deleteProfile` |

`gender` is one of `female`, `male`, `other`, `prefer_not_to_say`; age is 0–120. Account registration is separate from profile creation.

## Hospitals, doctors, and appointments

The directory and appointment endpoints require a valid signed-in account. Mutation endpoints impose additional role and scope rules.

| Method + path | Access | Request/query | Response / behavior | Frontend caller |
| --- | --- | --- | --- | --- |
| `GET /providers/hospitals` | Signed-in | `search,city,state,limit,offset` | Page `{items,total,limit,offset}`; only verified hospitals | `CareDirectoryPage` |
| `GET /providers/hospitals/{hospital_id}` | Signed-in | — | Verified `HospitalRead`; otherwise 404 | Inline details |
| `GET /providers/doctors` | Signed-in | `search,specialty,city,language,consultation_type,limit,offset` | Page of active/verified `DoctorRead`; unverified hospital profiles excluded | `CareDirectoryPage` |
| `GET /providers/doctors/{doctor_id}` | Signed-in | — | Active verified `DoctorRead` with qualifications/schedules/hospital; otherwise 404 | Inline details |
| `POST /providers/recommendations` | Signed-in | `symptoms,specialty,city,language,consultation_type` | Up to six scored doctor recommendations, match reasons and recurring schedule data; not a diagnosis or actual slot reservation | `CareDirectoryPage` |
| `GET /providers/dashboard` | Doctor, HS, HA, or PA | — | Doctor: `{role,doctor}`; HS/HA: `{role,hospital,doctors,doctor_count,appointment_count}`; PA: `{role,hospital_count,doctor_count,pending_hospitals,pending_doctors}` | `ProviderDashboardPage` |
| `POST /providers/hospitals` | PA | `name,city,state,departments,description,address,phone,website` | 201 pending hospital profile | Platform provider dashboard |
| `PATCH /providers/hospitals/{hospital_id}` | HA or PA; hospital-admin scope enforced | Partial hospital profile fields | Updated `HospitalRead` | `ProviderDashboardPage` |
| `POST /providers/hospitals/{hospital_id}/doctors` | HA or PA; hospital scope enforced | `full_name,specialty,fee_minor,experience_years,bio` | 201 clinician profile, initially subject to review | `ProviderDashboardPage` |
| `PATCH /providers/doctors/{doctor_id}` | Linked doctor, HA for its hospital, or PA | Partial profile (`bio,specialty,specialties,languages,consultation_types,qualifications`) | Updated `DoctorRead` | `ProviderDashboardPage` |
| `PUT /providers/doctors/{doctor_id}/schedules` | Linked doctor, HA for its hospital, or PA | Array of `{day_of_week,starts_at,ends_at,timezone,consultation_type,is_active}` | Replaces schedule collection; rejects overlap, invalid times/timezone | `ProviderDashboardPage` |
| `PATCH /providers/doctors/{doctor_id}/verification` | PA | `{verification_status:"pending"|"verified"|"rejected"}` | Updated clinician | Platform review screen |
| `PATCH /providers/hospitals/{hospital_id}/verification` | PA | Verification status | Updated hospital | Platform review screen |
| `PATCH /providers/qualifications/{qualification_id}/verification` | PA | Verification status | Updated qualification | Platform review screen |
| `GET /providers/review-queue` | PA | — | `{hospitals:HospitalRead[],doctors:DoctorRead[],qualifications:[{id,doctor_id,degree,institution}]}` for pending items | `ProviderDashboardPage` |
| `GET /providers/doctors/{doctor_id}/available-slots` | Signed-in | Required `day` (date); `consultation_type` | Array of `{scheduled_for,local_date,local_time,timezone,consultation_type}` | `CareDirectoryPage` |
| `GET /providers/appointments` | Signed-in patient, doctor, HS, HA, or PA | — | `AppointmentRead[]`, filtered to role's patient/doctor/hospital or platform scope | Dashboard, appointments, administration |
| `POST /providers/appointments` | Patient | `doctor_id,scheduled_for,consultation_type,notes`; header `Idempotency-Key` (16–128 chars) | 201 appointment; retry replay returns 200 same appointment; occupied slot conflict 409 | `CareDirectoryPage` |
| `POST /providers/appointments/{appointment_id}/confirm` | Doctor, HS, HA, or PA; resource access checked | — | Updated appointment status/event | `AppointmentsPage`, `AdminManagement` |
| `PATCH /providers/appointments/{appointment_id}/cancel` | Scoped appointment participant/authorized staff (see route access logic) | Optional `{reason}` | Updated appointment; slot lock released | `AppointmentsPage`, `AdminManagement` |
| `PATCH /providers/appointments/{appointment_id}/reschedule` | Patient or authorized provider/admin with access | `scheduled_for,consultation_type,reason`; idempotency header | Updated appointment, event and slot lock; conflicts 409 | `AppointmentsPage` |
| `GET /providers/appointments/{appointment_id}/history` | Scoped appointment participant/provider/admin | — | `AppointmentEventRead[]` | `AppointmentsPage` |

`AppointmentRead` contains `id,patient_user_id,doctor_id,hospital_id,scheduled_for,duration_minutes,consultation_type,status,notes,created_at` plus display names/specialty. Datetimes must include a timezone. Scheduling uses 30-minute blocks and database uniqueness in `appointment_slot_locks`; published availability is not a reservation.

## Billing and payments

| Method + path | Access | Request | Response / behavior | Frontend caller |
| --- | --- | --- | --- | --- |
| `GET /billing/config` | Signed-in | — | `{payment_mode,online_payment_enabled,demo_payment_enabled}` | `Billing` |
| `GET /billing/invoices` | Signed-in; rows filtered by role/owner/hospital | — | Invoice array `{id,invoice_number,description,amount_minor,currency,status,appointment_id,created_at,paid_at}` | `Billing` |
| `GET /billing/payments` | Signed-in; rows scoped similarly | — | Array with `id,invoice_id,invoice_number,transaction_id,status,amount_minor,currency,is_demo,created_at,updated_at` | `Billing` |
| `GET /billing/billable-appointments` | HS, HA, PA | — | Eligible appointment, patient, doctor, and stored fee details | `Billing` invoice form |
| `POST /billing/invoices` | HS, HA, PA with hospital scope | `patient_user_id,description,amount_minor? ,appointment_id?,hospital_id?` | 201 invoice; appointment invoice amount uses doctor fee in DB and duplicate appointment invoice rejected | `Billing` |
| `POST /billing/checkout` | Invoice-owning patient | `{invoice_id}` | `CheckoutOrder`: `order_id,key_id?,amount_minor,currency,invoice_number,description,mode` | `Billing` |
| `POST /billing/demo/complete` | Invoice-owning patient | `{order_id,outcome:"success"|"failed"|"cancelled"}` | Simulated invoice/payment result; cannot complete live order, replay settled attempt, or pay another user's invoice | `Billing` |
| `POST /billing/verify` | Invoice-owning patient | `invoice_id,razorpay_order_id,razorpay_payment_id,razorpay_signature` | Invoice only after valid HMAC and server-side provider state/amount/currency verification | `Billing` Razorpay handler |
| `POST /billing/webhooks/razorpay` | Public webhook; signature and event ID required | Raw body + `X-Razorpay-Signature`, `X-Razorpay-Event-Id` | 204 for accepted/replayed event; invalid signature/payload or unsafe conflict returns 4xx | Razorpay server, not React |

All amounts are integer INR paise. In demo mode the browser offers simulation buttons and the backend writes clearly tagged local records; no real money changes hands and no card/banking details are requested. Live checkout is conditional on backend Razorpay keys. See [billing flow](./END_TO_END_FLOWS.md#workflow-d-billing-and-demo-payments).

## AI, triage, and speech

| Method + path | Access | Request | Response / behavior | Frontend caller |
| --- | --- | --- | --- | --- |
| `GET /assistant/speech-to-text/config` | Signed-in | — | `{provider,transcription_enabled,max_audio_bytes,supported_languages}` | `VoiceAssistant` |
| `POST /assistant/speech-to-text` | Signed-in | Multipart `file`, `language` (`hi` or `en`) | `{transcript,language,provider,requires_confirmation}`; type/size/provider errors return explicit 4xx/5xx | `VoiceAssistant` server-recording path |
| `POST /assistant/triage` | Public | `{text,age_band?,pregnancy?,chronic_condition?}` | `{urgency,category,summary,guidance,emergency_numbers,flags,is_medical_guidance_only,safety_block}` | `PublicTriage` |
| `POST /assistant/rag/search` | Public | `{query,category?}` | Up to five source records with citation/provenance/license/snippet/score; 503 if embedding provider is unavailable | No current first-party UI caller |
| `POST /assistant/chat` | Signed-in | `{messages:[{role:"user"|"assistant",content}]}` (1–20; latest must be user) | `{reply,citations,evidence_available,source_conflict}`; deterministic safety checks precede model | `VoiceAssistant` |

Triage is limited deterministic keyword logic. Chat can contact configured Ollama or compatible hosted model; RAG is opt-in. Neither is clinically validated.

## Administration

All `/admin/*` endpoints require a platform administrator or hospital administrator. Hospital admins see only their hospital and have narrower write permissions.

| Method + path | Request/query | Response / behavior | Frontend caller |
| --- | --- | --- | --- |
| `GET /admin/hospitals` | — | Global list for PA; hospital-scoped summary for HA | `AdminManagement` |
| `GET /admin/doctors` | — | Global/scoped clinician list | `AdminManagement` |
| `POST /admin/accounts` | `full_name,email,role,hospital_id,doctor_id?,password,password_confirmation`; role is doctor or hospital_admin | 201 managed account. Hospital admin may only create doctor account; link and password policy checked | `AdminManagement` |
| `GET /admin/overview` | — | `data_source,demo_records,users_by_role,appointments_by_status,payments_by_status,invoices_by_status,doctors_by_verification,hospitals_by_verification`; counts 1–4 are suppressed | `AdminManagement` |
| `GET /admin/users` | `limit,offset,role?` | `{items,total,limit,offset}`; HA sees only hospital staff for its own hospital; PA sees managed non-patient users | `AdminManagement` |
| `PATCH /admin/users/{user_id}` | `role?,hospital_id?,doctor_id?,is_active?` | Updated managed account; sessions revoked. Cannot self-edit or deactivate last active PA | `AdminManagement` |
| `GET /admin/appointments` | `limit,offset,status?` | Paged appointment summary, optionally status-filtered | `AdminManagement` |
| `GET /admin/payments` | `limit,offset` | Paged payment summary | `AdminManagement` |
| `GET /admin/audit-logs` | `limit,offset,action?,since?,until?` | Paged records with `id,actor_user_id,hospital_id,action,resource_type,resource_id,created_at` | `AdminManagement` |
| `GET /admin/notifications` | `limit,offset` | Paged outcomes with `id,user_id,channel,event_type,status,failure_code,created_at`; no message contents | `AdminManagement` |

## Adding an endpoint

1. Choose the existing domain router and define a Pydantic request/response model (or reuse a domain schema).
2. Add `@router.<method>` and dependencies for `get_db`, authentication, and required role.
3. Scope every database lookup by current user/hospital before returning or mutating it.
4. Use existing service/controller/repository where the domain has one; preserve transaction and audit patterns.
5. Register a new router in `main.py` only if it is a new module.
6. Add tests for success, validation, forbidden role, cross-tenant/owner access, missing row and conflict.
7. Add the endpoint and caller to this reference; run backend tests.

See [Adding features](./ADDING_FEATURES.md) for examples and [Run and debug](./RUN_AND_DEBUG.md) for commands.

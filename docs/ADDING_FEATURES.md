# Adding features safely

These examples are **guides for future changes**, not features being implemented by this document. Follow the repository's existing flow: UI/API schema/model/migration/tests when the change crosses those boundaries. Never bypass ownership or tenant checks.

## Example 1 — Add a patient profile field

Suppose a future feature needs a non-sensitive field such as `preferred_language`.

**Files to inspect/change**

- `backend/app/models/patient.py` — persisted column.
- `backend/app/schemas/patient.py` — `PatientCreate`, `PatientUpdate`, `PatientRead` validation/serialization.
- `backend/migrations/versions/` — new Alembic revision.
- `frontend/src/App.jsx` — `emptyProfile`, profile load/save and form state.
- `frontend/src/components/PortalScreens.jsx` — `ProfilePage` form/control.
- `backend/tests/test_schemas.py`, `test_account_boundaries.py`; add frontend test if formatting/behavior is testable.

**Sequence**

1. Define allowed values, default, nullability and behavior for existing profiles.
2. Add model and Pydantic fields. Keep request validation in the schema.
3. Create an additive migration with safe handling for existing rows. Do not call `create_all` or reset the volume.
4. Add the form field and include it in profile submit state.
5. Verify list/create/read/update serialization and ownership filters are preserved.
6. Test upgrade on an isolated database and run the commands below.

**Illustrative schema shape** (use only if the domain choice is approved):

```python
class PatientUpdate(BaseModel):
    preferred_language: str | None = Field(default=None, max_length=20)
```

**Expected:** A patient can save and reload the field; another account cannot read or edit it. Test defaults for existing rows and malformed input. Common mistake: adding only the ORM column; then the API silently omits it.

## Example 2 — Add a doctor filter

**Files:** `frontend/src/components/PortalScreens.jsx` (`CareDirectoryPage`, `loadDirectory`, `createParams`), `backend/app/routes/provider_routes.py` (`list_doctors`), and `backend/app/schemas/providers.py` only if a reusable filter schema is appropriate.

**Sequence**

1. Add a controlled filter and append its value to the doctors URLSearchParams; reset the offset when filter changes.
2. Add a bounded `Query(...)` argument in `list_doctors`.
3. Apply the filter to the existing SQLAlchemy `select(Doctor, Hospital)` query; retain active/verified hospital filters, ordering, pagination and count query.
4. Add provider-directory tests for matching, no matches, invalid value, paging and tenant/security regression.
5. Check `items,total,limit,offset` remain consistent and that hospital cards are unaffected.

**Illustrative query fragment:**

```python
language: str | None = Query(default=None, max_length=80)
# Apply it alongside the existing conditions in list_doctors.
```

`list_doctors` already accepts `search`, `specialty`, `city`, `language`, `consultation_type`, `limit`, and `offset`. Avoid filtering only in React: that produces incorrect totals and pages.

## Example 3 — Add an appointment field

**Files:** `backend/app/models/providers.py` (`Appointment`), `backend/app/schemas/providers.py` (`AppointmentCreate`, `AppointmentRead`, and any update schema), `backend/app/routes/provider_routes.py` (create/reschedule/read serializer), a new migration, `frontend/src/components/PortalScreens.jsx` (booking form and appointment display), and appointment tests.

**Sequence**

1. Define whether the value is optional, immutable after booking, sensitive, or included in appointment event history.
2. Add migration/model field, then validated schema input/output.
3. Update create/read and applicable reschedule/cancel code. Preserve request fingerprinting so idempotent retries with different values cannot be mistaken as the same operation.
4. Update the UI and include the value in booking request only if allowed.
5. Test timezone, ownership, role access, idempotent replay, conflicts, event/history, and old-row migration.

**Illustrative input pattern:**

```python
new_field: str | None = Field(default=None, max_length=120)
```

Do not accept a patient ID from the browser for a patient booking: the route derives the patient user from the authenticated account.

## Example 4 — Add a dashboard statistic

**Files:** `backend/app/routes/admin_routes.py` (`admin_overview`) or the domain dashboard route, `frontend/src/components/AdminManagement.jsx` or `PortalScreens.jsx`, and `backend/tests/test_admin_workflows.py`.

**Sequence**

1. Decide the metric's exact numerator, denominator, time range, status definitions, and privacy thresholds.
2. Query with SQL aggregation, not by loading every row into React.
3. Reuse hospital scoping (`_admin_hospital`) and suppression for small groups if the metric could expose individual activity.
4. Add the response field and UI rendering with loading/error states.
5. Test zero rows, each status, hospital scope, global scope, and the under-five suppression boundary.

Current `GET /admin/overview` already aggregates users, appointments, payments, invoices, doctors and hospitals; `_visible_count` suppresses small groups.

## Example 5 — Add a new API endpoint

**Files:** the correct `backend/app/routes/<domain>_routes.py`; request/response Pydantic models in its existing schema module (or route module when conventions do so); `backend/app/main.py` only when registering a new router; test module for the domain; frontend caller if user-facing.

**Sequence**

1. Confirm no existing endpoint already represents the operation. Check `docs/API_REFERENCE.md`.
2. Add a validated response contract and route using existing `get_db`, `get_current_user`/`require_roles`, and service helpers.
3. Add SQL filters for owner and `hospital_id` before loading data.
4. Use a transaction and map known duplicate/missing/conflict errors to standard HTTP responses.
5. Add positive and adversarial tests: missing auth, wrong role, other user's resource, other hospital, invalid input, duplicate/race.
6. Add `apiRequest` caller with clear loading/error/success states; document the endpoint.

**Illustrative route shape—not an existing endpoint:**

```python
@router.get("/resource/{resource_id}", response_model=ResourceRead)
def read_resource(
    resource_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return resource_service.read_for_user(db, resource_id, user.id)
```

The owner-filtered service in the actual code should make unauthorized resources indistinguishable where the existing domain convention uses 404.

## Example 6 — Add a role-protected page

**Files:** `frontend/src/App.jsx` (navigation and conditional page render), a component under `frontend/src/components/`, matching backend router and tests.

**Sequence**

1. Add UI navigation for the intended role and render condition. Avoid a direct URL route assumption; current navigation is `page` state.
2. Add server endpoint(s) guarded by `require_roles`; add per-record scope checks.
3. Make all UI API calls through `apiRequest` with active token.
4. Test forbidden direct API calls even when a user manually opens a hidden page or uses browser devtools.
5. Add cases for another hospital, inactive account, missing linked doctor and changed role/session.

**Important:** `visibleNavigation` and hidden buttons are not access control. Server authorization and row filtering are mandatory.

## Commands and tests for changes

```sh
docker compose exec -T backend python -m pytest -q
docker compose exec -T backend alembic check
docker compose exec -T frontend npm test
docker compose exec -T frontend npm run build
```

For a model change, first run migrations against a disposable/isolated database, not a valuable local database. See [Database guide](./DATABASE_GUIDE.md) and [Run and debug](./RUN_AND_DEBUG.md).

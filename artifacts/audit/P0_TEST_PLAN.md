# DataForge Scraper - P0 Test Plan

Date: 2026-06-12
Scope: tests to add or preserve before implementation fixes.

## Add First

1. **Export cross-tenant denial**
   - Create Org A and Org B with persistent API keys.
   - Seed a completed job owned by Org B with results.
   - Assert Org A READ and WRITE keys cannot access:
     - `GET /api/jobs/{job_id}/export/csv`
     - `GET /api/jobs/{job_id}/export/json`
     - `GET /api/jobs/{job_id}/export/excel`
     - `POST /api/exports/batch`
   - Assert Org B owner can export.
   - Assert denied exports do not record successful export usage.

2. **Workflow cross-tenant denial**
   - Org B creates a workflow with owner/org/project fields stamped from auth.
   - Org A cannot list, get, update, delete, run, or preview it.
   - Org B can perform the same operations.
   - Admin/operator all-access behavior is explicit and separately tested.

3. **Auth profile cross-tenant denial**
   - Org B creates an auth profile.
   - Org A cannot list, get, or delete it.
   - Responses never include encrypted storage state or raw cookies/tokens.
   - Owner can manage the profile.

4. **Scheduled monitoring cross-tenant denial**
   - Org B creates a schedule.
   - Org A cannot list, get, update, delete, or read changes for it.
   - Owner can manage it.
   - This requires the LocalASGIClient PUT helper fix before the update test reaches app code.

5. **SaaS route mutation policy**
   - Assert signup/org/project mutation routes have the intended policy.
   - Keep `test_route_auth_matrix_has_no_user_level_mutations` passing unless a route is deliberately allowlisted with rationale.

6. **Storage ownership parity**
   - SQLite: create/reload/list/filter jobs with `created_by`, `owner_id`, `user_id`, `org_id`, and `project_id`.
   - Postgres: run the same cases against repository/migration-backed storage.
   - Existing rows without new ownership columns should migrate to safe defaults.

## Required P0 Areas

### P0-AUTH-001 - Session/cookie auth and route RBAC consistency

- **current evidence:** Existing tests in `backend/tests/test_p0_auth_tenant.py` cover operator key to session cookie to protected operator endpoints, user cookie denied from operator endpoint, malformed cookie denied, expired cookie denied, and API-key/bearer auth still working.
- **status:** Covered by targeted tests that passed in the current baseline.
- **keep/add:** Add frontend E2E later for browser session state; backend resolver path should remain centralized through `resolve_auth_context`.

### P0-AUTH-002 - Protected API routes fail closed

- **current evidence:** Existing tests cover no API keys plus insecure dev auth disabled for `/api/jobs`, `/api/recycle_bin`, and `/api/system/status` returning 403. `/api/session/me` remains explicitly public and returns unauthenticated state.
- **status:** Covered by targeted tests that passed in the current baseline.
- **keep/add:** Add any newly protected route to the fail-closed matrix.

### P0-TENANT-001 - Tenant/user/project isolation

- **current evidence:** Existing tests cover jobs, job details, results, events, recycle-bin list, and persistent READ/WRITE key job listing isolation.
- **verified gaps:** Exports, workflows, auth profiles, and scheduled monitoring need tests and fixes.
- **add:** The "Add First" tests above.

### P0-STORAGE-001 - Ownership persistence parity

- **current evidence:** Code includes ownership fields, but Postgres parity tests were not run in Phase 0.
- **status:** Candidate issue, needs verification.
- **add:** SQLite/Postgres parity tests for ownership persistence and filters before storage changes.

### P0-BILLING-001 - Invoice due date date-math bug

- **current evidence:** `backend/app/utils/billing.py` uses `now + timedelta(days=due_days)` and rejects negative due days. `backend/tests/test_p0_billing_usage.py` covers January 31 + 30 days, leap year, due_days = 0, negative due_days, and timezone-aware due dates.
- **status:** Covered/fixed in current code.
- **keep/add:** Keep these tests in every P0 safety run.

### P0-QUOTA-001 - Usage quota enforcement

- **current evidence:** `backend/app/utils/usage_ledger.py` enforces quota in `record_usage` under a lock and supports idempotency keys. Existing P0 tests cover below/above limit, concurrent usage, API request enforcement, export quota enforcement, idempotent retries, and failed-export non-charging.
- **status:** Covered by targeted tests.
- **keep/add:** Add workflow/scheduled/browser-minute quota tests when those features become active.

## Suggested Command Set After P0 Tests Are Added

```bash
export DATAFORGE_DOTENV_PATH=/dev/null
export DATAFORGE_ENV=test
export DATAFORGE_STORAGE_BACKEND=sqlite
export DATAFORGE_API_KEY=user-key
export DATAFORGE_OPERATOR_API_KEY=operator-key
export DATAFORGE_ADMIN_API_KEY=admin-key
export DATAFORGE_SESSION_SECRET=test-session-secret-change-me
export DATAFORGE_ALLOW_INSECURE_DEV_AUTH=false
export DATAFORGE_SKIP_DB_CHECK=true
export PYTHONPATH=backend

python3 -m pytest backend/tests/test_p0_auth_tenant.py backend/tests/test_p0_billing_usage.py -q
python3 -m pytest backend/tests/test_route_auth_matrix_generator.py -q
python3 -m pytest backend/tests/test_repository_parity.py backend/tests/test_postgres_repository.py -q
```

Do not proceed from Phase 1 until the new P0 tests fail for the current defects, then pass after focused fixes.

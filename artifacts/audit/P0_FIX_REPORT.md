# DataForge Scraper - P0 Fix Report

Date: 2026-06-12
Commit: `7d47045`
Scope: verified P0 blockers from `artifacts/audit/ISSUE_LEDGER.md`.

No product features were added. Fixes are limited to auth/tenant route safety, route-policy clarity, and the minimal test-client helper needed to exercise update routes.

## Work Order Result

| Work Order Area | Result | Evidence |
| --- | --- | --- |
| Auth/session consistency | No implementation change required. Existing shared resolver path was already present. | `backend/tests/test_p0_auth_tenant.py` covers cookie/API-key/bearer auth and passes. |
| Protected API fail-closed | No implementation change required for existing protected routes. Signup was made an explicit public allowlist route. | `/api/jobs`, `/api/recycle_bin`, `/api/system/status` fail-closed tests pass. |
| Tenant/user/project isolation | Fixed verified gaps in exports, workflows, auth profiles, and scheduled monitoring. | New P0 tests fail before fix and pass after fix. |
| Storage ownership persistence parity | Not fixed because this remained a candidate issue, not a verified P0. | SQLite/non-Postgres parity tests pass; Postgres integration cases skipped without `--run-postgres`. |
| Billing due-date correctness | No implementation change required. | Existing P0 billing tests pass. |
| Usage quota enforcement | No implementation change required. | Existing P0 quota and metering tests pass. |
| Other verified P0 | Fixed SaaS route mutation policy. | Route-auth matrix passes; signup public and org/project creation operator/admin. |

## P0 Issues Fixed

### P0-EXPORT-001

- Added cross-tenant export regression tests in `backend/tests/test_p0_auth_tenant.py`.
- Exports now use `require_principal([ADMIN, OPERATOR])`.
- Export router checks `created_by`, `org_id`, and `project_id` before building or streaming export data.
- Cross-org persistent WRITE keys are denied for CSV, JSON, Excel, and batch export.
- Denied exports do not record successful export usage.

### P0-WORKFLOW-001

- Workflow create now stamps `user_id`, `org_id`, and `project_id` from the authenticated principal.
- Workflow list/get/update/delete/run/preview enforce scoped access.
- Cross-org persistent WRITE keys cannot see or mutate another org/project workflow.

### P0-AUTHPROFILE-001

- Auth profile create now stamps `user_id`, `org_id`, and `project_id` from the authenticated principal.
- Auth profile list/get/delete enforce scoped access.
- API responses strip `encrypted_storage_state` from create/list/get responses.
- `P1-AUTHPROFILE-002` remains open for duplicate model/contract cleanup.

### P0-SCHEDULE-001

- Scheduled job create now stamps `user_id`, `org_id`, and `project_id`.
- Scheduled job list/get/update/delete/changes enforce scoped access.
- Added `.put()`/`.patch()` helpers to `LocalASGIClient` so update tests exercise the actual route.

### P0-SAAS-ROUTE-001

- `/api/saas/signup` is explicitly public/self-service in middleware and route matrix.
- `/api/saas/orgs` and `/api/saas/projects` creation are operator-or-admin.
- Added tests proving public signup works without configured keys and READ/user-level SaaS keys cannot create orgs/projects.
- Route auth matrix no longer reports user-level mutation drift.

## Tests Added Or Updated

- `test_project_scoped_write_key_cannot_export_another_orgs_job`
- `test_project_scoped_key_cannot_access_another_orgs_workflow`
- `test_project_scoped_key_cannot_access_another_orgs_auth_profile`
- `test_project_scoped_key_cannot_access_another_orgs_schedule`
- `test_saas_signup_is_explicit_public_when_keys_are_not_configured`
- `test_user_level_saas_key_cannot_create_org_or_project`
- Route matrix unauthenticated mutation allowlist now documents `/api/saas/signup`.
- `LocalASGIClient.put()` and `LocalASGIClient.patch()` added for route tests.

## Red/Green Evidence

### Expected Failing Run Before Fix

Command:

```bash
python3 -m pytest backend/tests/test_p0_auth_tenant.py -q
```

Result: exit 1. New P0 tests failed as expected:

- Cross-org export CSV/JSON/Excel returned 200 instead of 403/404.
- Cross-org workflow was visible in list.
- Auth profile create response exposed `encrypted_storage_state`.
- Cross-org schedule was visible in list.
- Public signup returned 403 with no keys.
- User-level SaaS key could create an org.

### Passing Targeted Runs After Fix

| Command | Result |
| --- | --- |
| `python3 -m pytest backend/tests/test_p0_auth_tenant.py -q` | PASS, 33 tests |
| `python3 -m pytest backend/tests/test_p0_billing_usage.py -q` | PASS, 28 tests |
| `python3 -m pytest backend/tests/test_route_auth_matrix_generator.py -q` | PASS, 4 tests |
| `python3 -m pytest backend/tests/test_workflow.py backend/tests/test_scheduled_monitoring.py -q` | PASS, 27 tests |
| `python3 -m pytest backend/tests/test_saas_router.py -q` | PASS, 11 tests |
| `python3 -m pytest backend/tests/test_exports_router.py -q` | PASS, 56 tests |
| `python3 -m pytest backend/tests/test_exports_sheet_collision_edge_cases.py -q` | PASS, 5 tests |
| `python3 -m pytest backend/tests/test_p0_auth_tenant.py backend/tests/test_p0_billing_usage.py backend/tests/test_route_auth_matrix_generator.py -q` | PASS, 65 tests |

### Storage Verification

| Command | Result |
| --- | --- |
| `python3 -m pytest backend/tests/test_repository_parity.py -q -rs` | PASS for runnable cases; 13 skipped needing `--run-postgres` |
| `python3 -m pytest backend/tests/test_postgres_repository.py -q -rs` | PASS for runnable cases; 2 skipped needing `--run-postgres` |

No Postgres integration pass is claimed.

### Final Baseline

| Command | Result |
| --- | --- |
| `python -m compileall -q backend scripts architecture_validator.py` | FAIL, `python` executable missing |
| `python3 -m compileall -q backend scripts architecture_validator.py` | PASS |
| `PYTHONPATH=backend python3 architecture_validator.py` | PASS |
| `python3 scripts/check_research_boundary.py` | PASS |
| `python3 scripts/validate_dependency_bounds.py` | PASS |
| `python3 -m pytest backend/tests -q` | FAIL, 3 remaining non-P0 failures |

Remaining full-suite failures:

- `backend/tests/test_auth_profiles.py::TestAuthProfileModel::test_create_profile`
- `backend/tests/test_auth_profiles.py::TestAuthProfileModel::test_storage_state_not_exposed`
- `backend/tests/test_pyflakes_fixes.py::test_pyflakes_clean`

## Remaining P0 Status

No verified P0 issue from the Prompt 2 issue ledger remains open.

`CAND-P0-STORAGE-001` remains candidate/needs verification because Postgres integration tests were skipped unless `--run-postgres` is supplied.

## Remaining P1/P2 Risks

- `P1-AUTHPROFILE-002`: duplicate/mismatched AuthProfile model contract.
- `P1-CI-001`: full backend suite still red due remaining non-P0 failures.
- `P1-TESTNET-001`: default tests can still attempt Telegram network calls in some paths.
- `P2-LINT-001`: pyflakes/ruff drift remains.
- `P2-FRONTEND-LINT-001`: frontend Prettier drift remains.
- Production readiness remains unverified.

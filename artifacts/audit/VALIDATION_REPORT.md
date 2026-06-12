# DataForge Scraper - Validation Report

_Phase 0 baseline regenerated 2026-06-12 from current checkout
`7d47045`._

This report records commands actually run in this turn. Do not treat
older status documents as evidence unless their claims match this file
or a fresh command run.

## Environment

| Tool | Result |
| --- | --- |
| `python --version` | **FAIL** - `/bin/bash: line 1: python: command not found` |
| `python3 --version` | `Python 3.12.3` |
| `node --version` | `v24.12.0` |
| `npm --version` | `11.12.1` |
| `git rev-parse --short HEAD` | `7d47045` |
| `git status --short` | dirty tree: 14 modified, 19 untracked |
| `python3 -m pytest --version` | `pytest 9.0.3` |
| `python3 -m ruff --version` | `ruff 0.15.0` |
| `python3 -m mypy --version` | `mypy 2.1.0` |
| `python3 -m pyflakes --version` | `3.4.0 Python 3.12.3 on Linux` |
| `python3 -m bandit --version` | `bandit 1.9.4` |
| `python3 -m pip_audit --version` | `pip-audit 2.10.0` |

Python validation commands used this environment:

```bash
DATAFORGE_DOTENV_PATH=/dev/null
DATAFORGE_ENV=test
DATAFORGE_STORAGE_BACKEND=sqlite
DATAFORGE_API_KEY=user-key
DATAFORGE_OPERATOR_API_KEY=operator-key
DATAFORGE_ADMIN_API_KEY=admin-key
DATAFORGE_SESSION_SECRET=test-session-secret-change-me
DATAFORGE_ALLOW_INSECURE_DEV_AUTH=false
DATAFORGE_SKIP_DB_CHECK=true
PYTHONPATH=backend
```

## Commands Run

| # | Command | Exit | Result |
| ---: | --- | ---: | --- |
| 1 | `python --version` | 127 | **FAIL** - command not found |
| 2 | `node --version` | 0 | `v24.12.0` |
| 3 | `npm --version` | 0 | `11.12.1` |
| 4 | `git rev-parse --short HEAD` | 0 | `7d47045` |
| 5 | `git status --short` | 0 | dirty tree: 14 modified, 19 untracked |
| 6 | `python -m compileall -q backend scripts architecture_validator.py` | 127 | **FAIL** - command not found |
| 7 | `PYTHONPATH=backend python architecture_validator.py` | 127 | **FAIL** - command not found |
| 8 | `python scripts/check_research_boundary.py` | 127 | **FAIL** - command not found |
| 9 | `python scripts/validate_dependency_bounds.py` | 127 | **FAIL** - command not found |
| 10 | `python3 -m compileall -q backend scripts architecture_validator.py` | 0 | **PASS** - no output |
| 11 | `PYTHONPATH=backend python3 architecture_validator.py` | 0 | **PASS** - `VALIDATION PASSED: Architecture is lawful.` |
| 12 | `python3 scripts/check_research_boundary.py` | 0 | **PASS** - `141 product-kernel files are free of top-level research imports.` |
| 13 | `python3 scripts/validate_dependency_bounds.py` | 0 | **PASS** - `25 prod packages, 13 dev packages.` |
| 14 | `python3 -m pytest backend/tests/test_url_safety.py backend/tests/test_research_boundary.py -q` | 0 | **PASS** - 32 tests passed |
| 15 | `python3 -m pytest backend/tests -q` | 1 | **FAIL** - six failures; see below |
| 16 | `npm ci` | 0 | **PASS** - 205 packages added/audited, 0 vulnerabilities |
| 17 | `npm run test` | 0 | **PASS** - 15 test files, 269 tests passed |
| 18 | `npm run lint:js` | 1 | **FAIL** - Prettier reports `frontend/styles.css` formatting drift |
| 19 | `python3 scripts/route_auth_matrix.py` | 0 | **PASS** - matrix generated; shows three SaaS mutation routes needing review |
| 20 | `python3 -m pytest backend/tests/test_route_auth_matrix_generator.py::test_route_auth_matrix_has_no_user_level_mutations -q -vv` | 1 | **FAIL** - three user-level mutation rows remain |
| 21 | `python3 -m ruff check backend scripts` | 1 | **FAIL** - 53 errors, 34 fixable |
| 22 | `python3 -m pyflakes backend/app backend/tests` | 1 | **FAIL** - seven warnings/errors listed below |
| 23 | `python3 -m bandit -r backend -q` | 0 | **PASS** - no failed issues; printed nosec/comment warnings |
| 24 | `python3 -m py_compile artifacts/audit/gen_full_ledger.py` | 0 | **PASS** |
| 25 | `python3 artifacts/audit/gen_full_ledger.py` | 0 | **PASS** - 29,148 ledger rows |

## Full Backend Pytest Failures

`python3 -m pytest backend/tests -q` completed with exit 1. The
verified failures were:

| Test | Verified failure |
| --- | --- |
| `backend/tests/test_auth_profiles.py::TestAuthProfileModel::test_create_profile` | `AuthProfile` has no `usage_count` attribute |
| `backend/tests/test_auth_profiles.py::TestAuthProfileModel::test_storage_state_not_exposed` | test expects `storage_state` in `model_dump()`, current model has `encrypted_storage_state` |
| `backend/tests/test_pyflakes_fixes.py::test_pyflakes_clean` | pyflakes reports seven warnings/errors |
| `backend/tests/test_route_auth_matrix_generator.py::test_route_auth_matrix_has_no_user_level_mutations` | unsafe list has three rows |
| `backend/tests/test_scheduled_monitoring.py::TestScheduledMonitoringEndpoints::test_update_schedule` | `LocalASGIClient` has no `.put()` method |
| `backend/tests/test_workflow.py::TestWorkflowEndpoints::test_update_workflow` | `LocalASGIClient` has no `.put()` method |

The same full pytest run also printed a Telegram notification network
error after the failure summary:

```text
Telegram send_message network error
requests.exceptions.SSLError: HTTPSConnectionPool(host='api.telegram.org', port=443): Max retries exceeded ...
```

This is evidence that at least one test path can attempt an external
Telegram request under the current test environment.

## Route Auth Matrix Finding

The route-auth matrix generated successfully. The focused invariant
test fails because these mutation routes are classified as
`authenticated-user` rather than operator/admin or explicitly
allowlisted:

- `POST /api/saas/orgs`
- `POST /api/saas/projects`
- `POST /api/saas/signup`

Do not infer exploitability from the matrix alone; it is route
registration evidence, not a penetration test. It is still a verified
authorization review item.

## Pyflakes Findings

`python3 -m pyflakes backend/app backend/tests` reported:

```text
backend/app/models.py:566:1: redefinition of unused 'AuthProfile' from line 469
backend/app/url_analyzer.py:478:5: local variable 'parsed' is assigned to but never used
backend/app/routers/auth_profiles.py:18:1: 'app.models.AuthProfileStatus' imported but unused
backend/app/saas/router.py:24:1: 'app.saas.models.User' imported but unused
backend/app/saas/router.py:24:1: 'app.saas.models.UserStatus' imported but unused
backend/tests/test_scheduled_monitoring.py:3:1: 'pytest' imported but unused
backend/tests/test_auth_profiles.py:3:1: 'pytest' imported but unused
```

## Ruff Findings

`python3 -m ruff check backend scripts` reported 53 errors, 34
fixable. The first classes of issues include unsorted imports,
exception-message style warnings, the duplicate `AuthProfile`
definition, unused imports, `Query(...)` parameters not wrapped in
`Annotated`, missing trailing commas, and unused function arguments.

## Frontend Findings

Root `package.json` exists and was used for frontend tooling. There is
no `frontend/package.json`, but the requested root commands are
runnable.

- `npm ci`: pass, 0 vulnerabilities reported.
- `npm run test`: pass, 15 test files / 269 tests.
- `npm run lint:js`: fail, Prettier wants changes in
  `frontend/styles.css`.

## Inventory Command

`python3 artifacts/audit/gen_full_ledger.py` produced:

```text
Wrote 29148 ledger rows
Project-owned: 821, deep-inspected: 818, skipped: 28330, follow-up: 17
```

The three project-owned skipped files are machine-generated lockfiles:

- `package-lock.json`
- `uv.lock`
- `backend/tests/test_semantic_state.json.lock`

## What Passed

- `python3` compile gate.
- Architecture validator.
- Research boundary check.
- Dependency bounds validation.
- Targeted URL safety and research-boundary tests.
- Root `npm ci`.
- Root frontend unit tests.
- Bandit, with warnings only.
- Full file inventory and ledger generation.

## What Failed

- Literal `python ...` commands fail because `python` is not installed
  under that name.
- Full backend pytest has six failures.
- Route-auth-matrix invariant has three SaaS mutation rows to review.
- Pyflakes has seven findings.
- Ruff has 53 findings.
- `npm run lint:js` fails on `frontend/styles.css` formatting.

## What Hung

Nothing hung. Long-running commands were executed with timeouts where
appropriate.

## What Was Not Run

- Mypy full check.
- pip-audit full vulnerability scan.
- Postgres parity/integration tests.
- Playwright browser E2E tests.
- Load tests.
- Staging deployment validation.
- TLS, secrets, backup, restore-drill, monitoring, alert-delivery, or
  incident-runbook drills.

## Known Risks From This Baseline

| ID | Severity | Risk | Evidence |
| --- | --- | --- | --- |
| P1-001 | P1 | Full backend suite is not green. | `python3 -m pytest backend/tests -q` exit 1, six failures. |
| P1-002 | P1 | AuthProfile model contract is inconsistent. | duplicate `AuthProfile`; missing `usage_count`; storage-state mismatch. |
| P1-003 | P1 | Route auth matrix flags user-level SaaS mutation routes. | `POST /api/saas/orgs`, `POST /api/saas/projects`, `POST /api/saas/signup`. |
| P1-004 | P1 | Test environment can attempt external Telegram network call. | SSL error to `api.telegram.org` during full pytest output. |
| P1-005 | P1 | Local ASGI test client lacks `.put()` while tests use it. | workflow and scheduled-monitoring update tests fail. |
| P2-001 | P2 | Ruff and pyflakes drift. | 53 ruff errors; seven pyflakes findings. |
| P2-002 | P2 | Frontend formatting drift. | `npm run lint:js` fails on `frontend/styles.css`. |
| P2-003 | P2 | Production readiness is unverified. | no staging/TLS/secrets/backups/load/alert evidence in this turn. |

## Safe Next Tasks

1. Fix the backend full-suite failures with tests first where behavior
   is P0/P1.
2. Decide and test the intended authorization for the three SaaS
   mutation routes.
3. Disable or mock Telegram network sends in tests.
4. Run a focused lint cleanup for pyflakes/ruff.
5. Format `frontend/styles.css`.
6. Re-run full backend pytest, frontend lint, mypy, pip-audit,
   Postgres parity, and browser E2E after fixes.

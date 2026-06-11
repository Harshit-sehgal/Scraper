# Agent Truth - DataForge Scraper

**Date:** 2026-06-11
**Commit inspected:** `81a3c2f5e1f44a315a1e20c2a806ab315bf36d74`
**Checkout state:** dirty before this work started. Pre-existing modified files included backend scraper, rate limiter, LLM bridge, Postgres queue/repository base files, and related tests.
**Rule:** older status files and archived plans are historical unless their claims are reproduced by fresh commands in this checkout.

## Environment

| Item | Value |
| --- | --- |
| Python | `Python 3.12.3` from `.venv/bin/python` |
| pip | `26.1.2` |
| Node | `v24.12.0` |
| npm | `11.12.1` |
| pytest | `9.0.3` |
| ruff | `0.15.15` |
| mypy | `2.1.0` |
| pyflakes | `3.4.0` |
| bandit | `1.9.4` |
| pip-audit | `2.10.0` |

Full version log: `artifacts/validation/environment_2026-06-11.log`.

## Commands Run

| Command | Result | Log |
| --- | --- | --- |
| `python3.12 -m venv .venv` | pass | terminal output |
| `.venv/bin/python -m pip install -U pip wheel setuptools` | pass after network was enabled | terminal output |
| `.venv/bin/python -m pip install -e '.[dev]'` | pass | terminal output |
| `.venv/bin/python -m playwright install chromium` | pass, emitted OS fallback warning | terminal output |
| `npm ci` | pass, `found 0 vulnerabilities` | terminal output |
| `python -m compileall -q backend scripts architecture_validator.py` | pass | `artifacts/validation/baseline_compileall_2026-06-11.log` |
| `PYTHONPATH=backend python architecture_validator.py` | pass, `VALIDATION PASSED: Architecture is lawful.` | `artifacts/validation/baseline_architecture_validator_2026-06-11.log` |
| `python scripts/check_research_boundary.py` | pass, `128 product-kernel files` | `artifacts/validation/baseline_research_boundary_2026-06-11.log` |
| `python scripts/validate_dependency_bounds.py` | pass, `25 prod packages, 13 dev packages` | `artifacts/validation/baseline_dependency_bounds_2026-06-11.log` |
| `python -m pytest backend/tests/test_url_safety.py backend/tests/test_research_boundary.py -q` | pass, `32 passed` | `artifacts/validation/baseline_url_research_tests_2026-06-11.log` |
| P0 characterization tests before fixes | failed as expected | `artifacts/validation/p0_characterization_failures_2026-06-11.log` |
| P0 targeted tests after fixes | pass, `35 passed` | `artifacts/validation/p0_targeted_after_lint_fix_2026-06-11.log` |
| Adjacent auth/storage tests | pass with Postgres integration tests skipped by default | `artifacts/validation/adjacent_auth_storage_tests_2026-06-11.log` |
| Touched-file `ruff check` | pass | terminal output |
| Post-fix baseline gate bundle | pass | `artifacts/validation/baseline_after_p0_fixes_2026-06-11.log` |
| Final baseline gate bundle | pass | `artifacts/validation/baseline_final_2026-06-11.log` |
| `python -m pytest backend/tests -q` | pass after auth, tenant, metering, static, and Postgres fixes | `artifacts/validation/full_pytest_backend_after_all_metering_fixes_2026-06-11.log` |
| Auth-focused tests after session-parser hardening | pass, `31 passed` | `artifacts/validation/auth_after_session_parser_hardening_2026-06-11.log` |
| `ruff check backend scripts` | pass | `artifacts/validation/ruff_final_after_auto_fix_2026-06-11.log` |
| `mypy backend` | pass, `511 source files` | `artifacts/validation/mypy_final_2026-06-11.log` |
| `pyflakes backend scripts` | pass | `artifacts/validation/pyflakes_final_2026-06-11.log` |
| `bandit -r backend` | pass, no issues identified | `artifacts/validation/bandit_final_2026-06-11.log` |
| `pip-audit` | pass, no known vulnerabilities; local editable package skipped | `artifacts/validation/pip_audit_final_2026-06-11.log` |
| `npm run lint:js` | pass | `artifacts/validation/npm_lint_js_final_2026-06-11.log` |
| `npm run test` | pass, `15` files and `269` tests | `artifacts/validation/npm_test_final_2026-06-11.log` |
| `pytest --run-postgres -m postgres backend/tests/test_repository_parity.py backend/tests/test_postgres_repository.py -q` | pass against Docker-backed Postgres | `artifacts/validation/postgres_repository_parity_after_fixture_fix_2026-06-11.log` |
| `python scripts/check_prod_env.py --env-file .env.production.local` | pass against a disposable local Postgres container; file is git-ignored and contains generated local secrets | `artifacts/validation/prod_env_local_gate_with_ready_postgres_2026-06-11.log` |
| `python scripts/check_prod_env.py --env-file .env.production.example` | fail as intended for placeholder values | `artifacts/validation/prod_env_example_gate_2026-06-11.log` |
| `python scripts/route_inventory_split.py --write` | pass, stable `45`, experimental `80`, diff `35` | `artifacts/validation/route_inventory_split_final_2026-06-11.log` |
| `python scripts/route_auth_matrix.py --format markdown > docs/ROUTE_AUTH_MATRIX.md` | pass | `artifacts/validation/route_auth_matrix_final_2026-06-11.log` |
| `python scripts/generate_status.py` | pass after script correction | `artifacts/validation/generate_status_final_after_metering_2026-06-11.log` |

## Current P0 Status

| ID | Current Evidence |
| --- | --- |
| P0-AUTH-001 session cookie auth | Fixed for RBAC-protected system/storage endpoints. Shared resolver added in `app.utils.rbac.resolve_auth_context`. |
| P0-AUTH-002 public read routes with no keys | Fixed for tested `/api/jobs`, `/api/recycle_bin`, and `/api/system/status`; `/api/session/me` remains intentionally public. |
| P0-TENANT-001 read-path tenant isolation | Fixed for tested job list/detail/results/events and recycle-bin list using MVP `created_by` owner filtering. Admin/operator all-job policy is explicit in tests. |
| P0-TENANT-002 Postgres `created_by` persistence | Fixed in shared jobs schema, Postgres row mapping, and created_by index generation; Docker-backed Postgres parity tests now pass with `--run-postgres`. |
| P0-BILLING-001 invoice due date | Fixed with timezone-aware `timedelta` math and negative due-day rejection. |
| P0-BILLING-002 quota enforcement | Usage ledger now enforces quotas atomically, supports idempotency keys, and can persist quotas/events to SQLite. Job creation, protected API requests, and export generation record/enforce usage. Page fetches, browser minutes, scheduled jobs, and external billing-provider flows are not yet fully metered. |
| P0-SAAS-001 account/org/project model | Not implemented. The repo still uses env-backed API keys and an MVP `created_by` owner model, not full SaaS identity. |

## Unreproduced Or Historical Claims

- Any old status, roadmap, or "production-ready" claim remains historical unless backed by the commands above.
- `.env.production.local` was generated locally with random values and is ignored by git. The production gate passed only against a disposable local Postgres container, not a real staging or production deployment.
- Full SaaS identity, org/project scoping, hashed persistent API keys, revocable sessions, billing provider integration, page-fetch/browser-minute/scheduled-job metering, staging deployment, backups, load tests, alert delivery, and compliance workflows are still not implemented/proven.

## Exact Next Actions

1. Add persistent SaaS identity tables and flows: users, organizations, memberships, projects, hashed API keys, and revocable sessions.
2. Move job ownership from MVP `created_by` user ownership to org/project ownership with membership-scoped access checks.
3. Extend usage enforcement to page fetches, browser minutes, scheduled jobs, retries, and all remaining worker-side execution paths.
4. Add billing provider integration in test mode plus subscription/plan records and webhook tests.
5. Prove staging operations: deployment, TLS, secrets, backups, restore drill, monitoring, alerting, load tests, and incident runbooks.

## Refresh — 2026-06-11 (this turn)

| Action | Result |
| --- | --- |
| Added `scripts/run_validation.sh` (reproducible one-shot baseline + P0 + full pytest gate) | pass |
| `bash scripts/run_validation.sh --skip-postgres` | **All checks passed** (compileall, architecture, research boundary, dep bounds, URL safety smoke, P0 auth-tenant, P0 billing-usage, full backend pytest); log: `artifacts/validation/run_validation_script_first_run_2026-06-11.log` |
| Added "Historical document" banner to `docs/CURRENT_STATUS.md` | pass |
| Added "Historical plan document" banner to `docs/ROADMAP.md` | pass |
| Added "Historical readiness checklist" banner to `docs/PRODUCTION_READINESS.md` | pass |
| `PROJECT_STATUS.md` already carries a historical banner pointing to this file | no-op |

### Updated SaaS readiness score (no change from previous refresh; P0 fixes still hold, but no new P0/P1 was finished in this turn)

- Internal prototype: 70/100
- Pre-production backend: 70/100
- SaaS readiness: 45/100 (full account/org/project model still missing)
- Production safety: 50/100
- Agent readiness: 80/100 (truth-source docs + reproducible baseline + historical banners)

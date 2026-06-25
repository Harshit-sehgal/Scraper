# DataForge Scraper - Issue Ledger

Date: 2026-06-25
Commit baseline before this audit update: `918aaf02`
Source baseline: current command output, `artifacts/validation/latest_summary.md`, `artifacts/validation/runs/20260623T221113Z_full/summary.md`, `docs/AGENT_TRUTH.md`, route inventory/auth matrix artifacts, and inspected router/test files.

This ledger records only evidence-backed issues. Rows marked `candidate` are not treated as verified defects until a failing test, runtime reproduction, or direct code path proves the behavior.

## Counts

| Metric | Count |
| --- | ---: |
| Open verified/deferred issues | 57 |
| Fixed issues | 44 |
| Not reproducible issues | 1 |
| Candidate issues | 3 |
| P0 issue rows | 15 |
| Open verified P0 issue rows | 0 |
| Fixed P0 issue rows | 14 |

> Updated 2026-06-18: `P1-AUTHPROFILE-002` and `P1-SECURITY-AUDIT-001`
> moved from `verified` → `fixed` (open verified 18 → 16, fixed 8 → 10).
> `CAND-P1-ROUTE-TENANT-001` moved from `candidate` → `fixed` after
> `/api/saas/plan` was wired to per-user tier lookup and
> `generate_route_auth_matrix.py` reported `unknown_tenant=0`
> (candidate 5 → 4).
>
> Updated 2026-06-22 session 2: `P1-CI-001`, `P1-AUDIT-COVERAGE-001`,
> `P1-COMPLIANCE-RETENTION-001` fixed. Core observability counters mapped.
> Benchmark login/load-more fixtures added. Workflow draft cross-tenant test,
> frontend auth-flow E2E, and job-submit E2E close candidate rows.
> Full suite + quick/security validation green. (open verified → 8, fixed → 18).
>
> Updated 2026-06-22 session 3: `P1-ARCH-SELECTOR-001` and
> `P1-ARCH-STATE-001` fixed. 12 unit tests added for pipeline stages
> (test_url_analysis_pipeline.py), 22 unit tests added for state machine
> mutation functions (test_job_state_machine_central.py). 34/34 new tests
> pass; 12/12 quick validation green. Ops items 5-7 moved to deferred
> (Postgres/staging blocked). (open verified 8 → 5, fixed 18 → 21).
>
> Updated 2026-06-22 session 4: `P1-ARCH-STORAGE-001` partially addressed
> with 36 direct storage_mapper unit tests; `P1-OPS-LOAD-ALERT-001`
> partially addressed with load test evidence (RPS 348, p95 74ms, 0 errors);
> `P1-OPS-BACKUP-RESTORE-001` partially addressed with
> `scripts/backup_and_restore_test.py` drill script; benchmark corpus
> expanded with 4 new fixture HTML pages (search_results, session_expired,
> load_more enhanced, login_wall enhanced). (open verified 5 → 3).
>
> Updated 2026-06-22 session 5: `P1-ARCH-STORAGE-001` further addressed
> with 13 SQLite repository unit tests (is_cancel_requested, world_state,
> count_jobs_by_status, worker_heartbeat); `P1-BENCHMARK-001` expanded with
> infinite_scroll fixture + extraction tests; `P1-MIGRATION-ROLLBACK-001`
> addressed with `scripts/migration_rollback_test.py` (drill passed);
> `P1-OPS-BACKUP-RESTORE-001` drill script made executable. All 97 new tests
> pass; 12/12 validation green. (open verified 5 → 3).
>
> Updated 2026-06-22 session 6: `P1-RESEARCH-DANGLING-REF-001` and
> `P1-DEADCODE-ORPHANED-SCRIPTS-001` fixed. Dangling `patch_status` ref
> removed from research registry. 3 orphaned scripts deleted. 23/23 full
> validation green. (open verified 5 → 5, fixed 21 → 23).
>
> Updated 2026-06-23 session 1: `P1-OPS-BACKUP-RESTORE-001` and
> `P1-MIGRATION-ROLLBACK-001` fixed. Docker environment used to run the backup
> and restore drill successfully (all seed rows survived). Missing Postgres v8 schema
> file generated and used to execute the database schemas. (open verified 5 → 3, fixed 23 → 25).
>
> Updated 2026-06-24 foundation audit: full validation passed
> (`20260623T205930Z_full`), route inventory regenerated at 161 routes
> (126 stable + 35 experimental), route auth matrix regenerated at 150
> API rows with `unknown_auth=0` and `unknown_tenant=0`, and file
> ledger generation was fixed so historical validation failures are no
> longer hardcoded into current per-file rows. Current open
> verified/deferred rows at that point were `P1-ARCH-STORAGE-001`,
> `P1-BENCHMARK-BASELINE-001`, `P2-BENCHMARK-CORPUS-001`,
> `P1-OPS-LOAD-ALERT-001`, and `P2-OBSERVABILITY-METRICS-001`.
>
> Updated 2026-06-24 benchmark corpus pass: `P2-BENCHMARK-CORPUS-001`
> fixed. Added named local fixtures for workflow search, network
> JSON-backed catalog, table, empty results, malformed HTML, and
> challenge pages. `test_required_benchmark_corpus_categories_have_local_fixtures`
> now enforces every required category in `docs/BENCHMARK_PLAN.md`.
> `python3 scripts/run_benchmark_smoke.py` passes. `P1-BENCHMARK-BASELINE-001`
> remains deferred because launch-grade precision/recall/F1 thresholds
> and per-category expected-output gates are still product-quality work.
>
> Updated 2026-06-24 observability metrics pass:
> `P2-OBSERVABILITY-METRICS-001` fixed for local implementation and
> endpoint contract. Added required product-counter defaults, job/page
> duration metrics, browser-context creation/failure counters, and
> per-domain failure-rate export. `backend/tests/test_metrics_observability.py`
> now enforces required metrics; adjacent metrics/domain/browser/billing
> suites pass. Staging scrape and alert delivery proof remains tracked by
> `P1-OPS-LOAD-ALERT-001`.
>
> Updated 2026-06-24 characterization pass:
> `CAND-P1-ARCH-CHARTEST-001` fixed. Job creation, URL analysis, exports,
> storage ownership parity, and frontend-to-backend job submission all
> have characterization coverage. Added 6 fixture-backed tests in
> `TestSelectorDiscoveryFixtureBehavior` to lock selector-discovery
> primitive contracts on `legacy_directory.html`, `table_catalog.html`,
> and `travel_site.html`. 54/54 selector_discovery tests pass;
> 12/12 quick validation green. (candidate 4 → 3; fixed 31 → 32).
>
> Updated 2026-06-24 benchmark baseline pass:
> `P1-BENCHMARK-BASELINE-001` fixed for deterministic local corpus
> evidence. Added `backend/benchmarks/local_corpus_expected.json`,
> `backend/benchmarks/local_corpus.py`, and
> `backend/benchmarks/test_local_corpus_baseline.py`. The local corpus
> now enforces versioned expected outputs, per-case thresholds,
> precision/recall/F1, missing fields, invalid types, duplicates,
> runtime, timeout rate, browser failures, and false-success prevention
> for negative pages. `python3 scripts/run_benchmark_smoke.py` passes
> with 33 passed, 2 skipped, 1 deselected and writes
> `artifacts/benchmarks/latest_local_corpus.*`. (open verified 3 → 2;
> fixed 32 → 33).
>
> Updated 2026-06-24 storage parity pass:
> `P1-ARCH-STORAGE-001` fixed. Fresh optional Postgres storage tests
> exposed a real soft-delete restore parity bug: Postgres `save_single`
> upserts left `deleted_at` populated, so restored jobs stayed hidden
> from active reads. `PostgresRepositoryBase.save_all` and
> `save_single` now clear `deleted_at` on active-job upserts. The
> storage boundary docs now reflect the current mapper/migration/health
> split. `--run-postgres` storage suites pass with 77 passed. (open
> verified 2 → 1; fixed 33 → 34).
>
> Updated 2026-06-24 load-alert reproducibility pass:
> restored `scripts/run_load_test.py`, added JSON artifact support and
> unit tests, replaced the corrupt `artifacts/load_test/latest_run.json`
> with valid machine-readable output, and tightened
> `scripts/smoke_prod_stack.sh` so local production smoke checks
> Alertmanager readiness in addition to Prometheus/Grafana. The issue
> remains open/deferred because real staging alert delivery still needs
> a configured on-call destination.
>
> Updated 2026-06-24 synthetic alert drill pass: added
> `scripts/run_alert_delivery_drill.py` and unit tests. The drill posts a
> synthetic Alertmanager v2 alert, polls `/api/v2/alerts`, and can fail
> staging gates unless `--notification-evidence` is supplied with
> `--require-notification-evidence`. This improves reproducibility but
> still does not close the issue until it is run against staging with
> real Slack/email/ticket evidence.
>
> Updated 2026-06-25 P0 hardening pass: `F-MON-001`, `F-CI-001`,
> `F-CI-002`, `F-DOCKER-007`, and `F-ENV-004` fixed. Production smoke
> now fails closed when no alert delivery channel is configured and
> drills a synthetic Alertmanager alert. Dependabot auto-approval /
> auto-merge is patch-only, and the workflow default token permissions
> are `{}` with `contents: write` restricted to the patch merge job.
> Local production-stack override credentials now require caller
> substitution instead of committed literals. App/worker production API
> and session secrets now use Docker secrets plus `DATAFORGE_*_FILE`
> loader support. `ISSUE_LEDGER.csv` was also synchronized with the
> Markdown ledger (105 issue IDs); no P0 rows remain open.


## Verified Issues

### P0-EXPORT-001

- **priority:** P0
- **status:** fixed
- **category:** tenant_isolation / exports_access_control
- **file_path:** `backend/app/routers/exports.py`
- **line/function:** `export_csv`, `export_json`, `export_excel`, `batch_export`; lines 217-430
- **evidence:** Export endpoints require admin/operator role but then call `jobs_store.get(job_id)` or iterate `body.job_ids` without checking `created_by`, `org_id`, or `project_id`. Persistent SaaS WRITE keys resolve to `UserRole.OPERATOR` with org/project context in `backend/app/utils/rbac.py:77-119`.
- **why_it_matters:** Exports return extracted data. A project-scoped operator key from one org must not export another org's job by guessing or obtaining a job id.
- **impact:** Cross-tenant data exposure through CSV, JSON, Excel, or batch export.
- **recommended_fix:** Route exports through a shared job-access helper that accepts full `AuthContext` and permits only admin all-access, env-backed operator all-access where explicitly intended, matching org/project, or matching owner.
- **tests_needed:** Cross-org persistent WRITE key cannot export another org's job in CSV, JSON, Excel, or batch format; owner can export; env-backed operator behavior is explicit.
- **acceptance_criteria:** Unauthorized export attempts return 403/404 and do not record successful export usage; authorized owner/admin cases still work.
- **blocked_by:** None.
- **notes:** Fixed in Prompt 3. Exports now use the full principal and check owner/org/project access before data is streamed. `backend/tests/test_p0_auth_tenant.py` proves cross-org WRITE keys cannot export CSV, JSON, Excel, or batch data.

### P0-WORKFLOW-001

- **priority:** P0
- **status:** fixed
- **category:** tenant_isolation / saved_workflows
- **file_path:** `backend/app/routers/workflow.py`
- **line/function:** `_workflows`, `create_workflow`, `list_workflows`, `get_workflow`, `update_workflow`, `delete_workflow`, `run_workflow`, `preview_workflow`; lines 27-207
- **evidence:** Workflows are stored in a global `_workflows` dict. Create accepts default `user_id=""`, `org_id=""`, and `project_id=""`, but does not populate them from `resolve_auth_context`. List/get/update/delete/run/preview return or mutate any workflow visible in the dict after only admin/operator role checks.
- **why_it_matters:** Saved workflows can contain target URLs, search parameters, extraction schema, and step definitions. These are tenant data.
- **impact:** Cross-tenant workflow disclosure, mutation, deletion, or execution if multiple project-scoped operator keys share the process.
- **recommended_fix:** Replace role-only dependencies with `require_principal`, stamp workflow owner/org/project from `AuthContext`, and enforce explicit access checks on every read/mutation/execution.
- **tests_needed:** Org A cannot list/get/update/delete/run/preview Org B workflow; Org B can; admin/operator all-access policy is documented and tested.
- **acceptance_criteria:** Every workflow route enforces owner/org/project isolation before returning or mutating data.
- **blocked_by:** Decide whether persistent WRITE keys should be operator-scoped within project or full org.
- **notes:** Fixed in Prompt 3. Workflow create stamps authenticated user/org/project, and list/get/update/delete/run/preview enforce scoped access.

### P0-AUTHPROFILE-001

- **priority:** P0
- **status:** fixed
- **category:** tenant_isolation / auth_profiles
- **file_path:** `backend/app/routers/auth_profiles.py`
- **line/function:** `_auth_profiles`, `create_auth_profile`, `list_auth_profiles`, `get_auth_profile`, `delete_auth_profile`; lines 23-95
- **evidence:** Auth profiles are stored in global `_auth_profiles`. Create accepts default blank `user_id`, `org_id`, and `project_id` instead of using the authenticated context. List returns all profiles and get/delete only check profile id plus admin/operator role.
- **why_it_matters:** Auth profiles represent browser-session material for logged-in sites. Even if encrypted storage state is stripped from responses, metadata and deletion rights are sensitive.
- **impact:** Cross-tenant auth profile enumeration or deletion, and future risk of session-state exposure when real storage is wired.
- **recommended_fix:** Centralize auth with `require_principal`, stamp owner/org/project, filter list by caller, and check ownership before get/delete. Keep storage-state fields encrypted and never returned.
- **tests_needed:** Cross-org list/get/delete denial; owner access; storage state not exposed; session material cannot be accessed through API responses.
- **acceptance_criteria:** Auth profile routes cannot expose or mutate another org/project/user's profile.
- **blocked_by:** AuthProfile model contract mismatch in `P1-AUTHPROFILE-002`.
- **notes:** Fixed in Prompt 3 for route-level tenant isolation and API response safety. `P1-AUTHPROFILE-002` remains open for the duplicate/model contract cleanup.

### P0-SCHEDULE-001

- **priority:** P0
- **status:** fixed
- **category:** tenant_isolation / scheduled_monitoring
- **file_path:** `backend/app/routers/scheduled_monitoring.py`
- **line/function:** `_scheduled_jobs`, `create_scheduled_job`, `list_scheduled_jobs`, `get_scheduled_job`, `update_scheduled_job`, `delete_scheduled_job`, `detect_changes`; lines 22-133
- **evidence:** Scheduled jobs are stored in global `_scheduled_jobs` and every route uses role-only admin/operator checks. The model creation does not stamp authenticated `user_id`, `org_id`, or `project_id`.
- **why_it_matters:** Scheduled monitoring can reveal target URLs, job names, change-detection state, and future result snapshots.
- **impact:** Cross-tenant schedule disclosure, mutation, deletion, and change-status reads.
- **recommended_fix:** Use `AuthContext`, persist owner/org/project fields, filter list, and enforce ownership before all reads/mutations/change checks.
- **tests_needed:** Cross-org persistent WRITE key cannot list/get/update/delete/check changes for another org's schedule; owner can.
- **acceptance_criteria:** Scheduled monitoring routes are tenant-scoped and include explicit admin/operator policy tests.
- **blocked_by:** Local ASGI test client currently lacks `.put()` (`P1-TESTCLIENT-001`).
- **notes:** Fixed in Prompt 3. Scheduled job create stamps authenticated user/org/project, and list/get/update/delete/changes enforce scoped access. The supporting LocalASGIClient `.put()` gap was fixed so update tests exercise the route.

### P0-SAAS-ROUTE-001

- **priority:** P0
- **status:** fixed
- **category:** authorization / route_matrix
- **file_path:** `backend/tests/test_route_auth_matrix_generator.py`
- **line/function:** `test_route_auth_matrix_has_no_user_level_mutations`
- **evidence:** `python3 -m pytest backend/tests/test_route_auth_matrix_generator.py::test_route_auth_matrix_has_no_user_level_mutations -q -vv` fails. `VALIDATION_REPORT.md` records flagged mutation rows: `POST /api/saas/orgs`, `POST /api/saas/projects`, and `POST /api/saas/signup`.
- **why_it_matters:** User-level mutation routes in the SaaS identity layer need explicit policy. Silent route drift can create account/org/project authorization gaps.
- **impact:** Unauthorized SaaS state changes or unclear signup/org/project mutation policy.
- **recommended_fix:** Review intended public/authenticated/admin policy for each route, adjust dependencies or the invariant allowlist with written rationale, and add targeted tests.
- **tests_needed:** Route matrix invariant passes; signup/org/project creation authorization tests document allowed and denied callers.
- **acceptance_criteria:** No SaaS mutation route is user-level by accident.
- **blocked_by:** Product decision for self-service signup versus admin-created org/project.
- **notes:** Fixed in Prompt 3. Signup is explicitly public/self-service; org/project creation is operator-or-admin; the route matrix passes.

### P1-CI-001

- **priority:** P1
- **status:** fixed
- **category:** validation / test_reproducibility
- **file_path:** `backend/tests`
- **line/function:** full suite
- **evidence:** Prompt 4 full validation `python3 scripts/validate_local.py --full` exits 1. Archive: `artifacts/validation/runs/20260612T162028Z_full/summary.md`. Backend log: `artifacts/validation/runs/20260612T162028Z_full/commands/12_backend_full_tests.md`. The backend suite fails with three failures: `test_auth_profiles.py::TestAuthProfileModel::test_create_profile`, `test_auth_profiles.py::TestAuthProfileModel::test_storage_state_not_exposed`, and `test_pyflakes_fixes.py::test_pyflakes_clean`.
- **why_it_matters:** The repository cannot claim a green backend baseline while the full suite is red.
- **impact:** CI/release confidence is weak; fixes can regress unrelated areas unnoticed.
- **recommended_fix:** Fix or quarantine each failure with focused tests and command evidence.
- **tests_needed:** Full backend pytest should pass in a clean test environment.
- **acceptance_criteria:** `python3 -m pytest backend/tests -q` exits 0 and the output is recorded.
- **blocked_by:** None.
- **notes:** Fixed 2026-06-22 session 2: `python3 -m pytest backend/tests/ -q` exits 0 (~5 min). Quick validation 12/12 and security validation 8/8 also pass. Prior failures (workflow schema drift, metrics_collector NameError, pyflakes drift) repaired.

### P1-AUTHPROFILE-002

- **priority:** P1
- **status:** fixed
- **category:** model_contract / auth_profiles
- **file_path:** `backend/app/models.py`, `backend/tests/test_auth_profiles.py`
- **line/function:** duplicate `AuthProfile`; tests `test_create_profile`, `test_storage_state_not_exposed`
- **evidence:** Prompt 4 full validation logs show the issue remains open. `artifacts/validation/runs/20260612T162028Z_full/commands/12_backend_full_tests.md` records the two auth-profile test failures. `artifacts/validation/runs/20260612T162028Z_full/commands/14_pyflakes.md` and `artifacts/validation/runs/20260612T162028Z_full/commands/15_mypy.md` both report duplicate `AuthProfile` definitions around `backend/app/models.py:566`.
- **why_it_matters:** Auth profile routes are security-sensitive. Model ambiguity makes it harder to enforce safe session handling.
- **impact:** Broken auth-profile tests and unclear API contract for session metadata.
- **recommended_fix:** Consolidate to one AuthProfile schema, define public/private response models, and update tests before wiring real session state.
- **tests_needed:** Auth profile create/list/get/delete, non-exposure of encrypted storage state, usage counter behavior if kept.
- **acceptance_criteria:** Auth profile tests and pyflakes duplicate-name check pass.
- **blocked_by:** None.
- **notes:** Resolved (verified 2026-06-18): `grep -rn "class AuthProfile" backend/` now returns a single `class AuthProfile` at `backend/app/models.py:514`. The `AuthProfileStore` in `backend/app/utils/auth_profile_store.py` is a store class (subclass of `JSONFileStore`), not a Pydantic model, so it is not a duplicate. `pyflakes` and `mypy` are both green in the current full validation (`artifacts/validation/commands/15_pyflakes.md`, `16_mypy.md`). Row closed.

### P1-TESTCLIENT-001

- **priority:** P1
- **status:** fixed
- **category:** test_tooling
- **file_path:** `backend/tests/conftest.py`
- **line/function:** `LocalASGIClient`; lines 445-478
- **evidence:** Full pytest failures show `AttributeError: 'LocalASGIClient' object has no attribute 'put'` in workflow and scheduled-monitoring update tests. `rg` confirms only `request` exists in the local client.
- **why_it_matters:** PUT/PATCH route coverage is blocked by a test harness gap, not necessarily application behavior.
- **impact:** Update endpoints cannot be verified through local tests.
- **recommended_fix:** Add thin `.put()` and likely `.patch()` helpers that delegate to `request`, matching existing get/post/delete helpers if present.
- **tests_needed:** Existing workflow and scheduled monitoring update tests should execute instead of failing on client helper lookup.
- **acceptance_criteria:** No AttributeError from LocalASGIClient for common HTTP verbs.
- **blocked_by:** None.
- **notes:** Fixed in Prompt 3 by adding `.put()` and `.patch()` helpers that delegate to `request`.

### P1-TESTNET-001

- **priority:** P1
- **status:** not_reproducible
- **category:** test_reliability / external_network
- **file_path:** `backend/app/utils/telegram_notifier.py`
- **line/function:** `telegram_notifier` network send path around line 145 in validation output
- **evidence:** Phase 0 full pytest output in `VALIDATION_REPORT.md` included an SSL error to `api.telegram.org`. Prompt 4 full validation did not reproduce this output; `rg "telegram|api\\.telegram|SSL" artifacts/validation/runs/20260612T162028Z_full/commands/12_backend_full_tests.md` returned no matches.
- **why_it_matters:** Unit tests should not depend on external network access or third-party availability.
- **impact:** Flaky CI, accidental outbound traffic, and noisy failures unrelated to code correctness.
- **recommended_fix:** Keep notification sends mocked/disabled in default tests if the failure returns; make production notification integration explicit and opt-in only.
- **tests_needed:** Notification unit tests assert payload construction without network; integration tests opt in with credentials.
- **acceptance_criteria:** Full backend pytest performs no unexpected external HTTP calls.
- **blocked_by:** None.
- **notes:** Not currently counted as an open verified issue. Keep real alert delivery verification in a deployment runbook, not default unit tests.

### P2-LINT-001

- **priority:** P2
- **status:** fixed
- **category:** code_quality
- **file_path:** `backend`, `scripts`
- **line/function:** ruff/pyflakes gates
- **evidence:** Prompt 4 full validation records `ruff_check` failing in `artifacts/validation/runs/20260612T162028Z_full/commands/13_ruff_check.md`. `pyflakes` fails with seven warnings/errors in `artifacts/validation/runs/20260612T162028Z_full/commands/14_pyflakes.md`.
- **why_it_matters:** Static drift hides real defects and makes CI less useful.
- **impact:** Lower signal from quality gates; contributors cannot rely on lint clean baseline.
- **recommended_fix:** Apply safe auto-fixes first, then manually resolve remaining warnings without broad refactors.
- **tests_needed:** Ruff and pyflakes commands pass.
- **acceptance_criteria:** Both gates exit 0 and outputs are recorded.
- **blocked_by:** `P1-AUTHPROFILE-002` for duplicate model cleanup.
- **notes:** Resolved (2026-06-22): pyflakes warnings fixed by removing dead re-exports from `jobs_write.py` and switching `selector_discovery.py` to PEP 562 `__getattr__` lazy imports. Ruff was already clean. Both gates exit 0.

### P1-SECURITY-AUDIT-001

- **priority:** P1
- **status:** fixed
- **category:** dependency_security / validation
- **file_path:** Python dependency environment
- **line/function:** `pip_audit`
- **evidence:** Prompt 4 full validation `pip_audit` fails. Log: `artifacts/validation/runs/20260612T162028Z_full/commands/17_pip_audit.md`. The output lists 60 known vulnerabilities in 21 installed packages, including `cryptography`, `jinja2`, `pillow`, `pyjwt`, `requests`, `starlette`, `urllib3`, and others. It also includes system/local packages that are not auditable from PyPI.
- **why_it_matters:** Dependency vulnerability checks are part of production readiness and CI trust.
- **impact:** Security posture is unclear until project dependencies are audited in a clean environment and vulnerable packages are upgraded or explicitly triaged.
- **recommended_fix:** Re-run `pip-audit` in a clean project virtual environment, separate project dependency findings from system package noise, then update allowed dependency bounds or document justified exceptions.
- **tests_needed:** `python3 scripts/validate_local.py --security` or `python3 -m pip_audit` in the project environment.
- **acceptance_criteria:** Security audit either exits 0 or has a reviewed, documented exception list that CI enforces.
- **blocked_by:** Dependency policy and compatibility review.
- **notes:** Resolved (2026-06-18): the residual project-dependency CVEs were all in `cryptography` (43.0.3 carried CVE-2024-12797, CVE-2026-26007, PYSEC-2026-35, GHSA-537c-gmf6-5ccf). `pyproject.toml` bound bumped from `>=43.0.0,<44.0.0` to `>=48.0.1,<50.0.0`; `python3 -m pip_audit --desc off .` now reports "No known vulnerabilities found" (exit 0). Full validation 23/23 genuinely green (`artifacts/validation/latest_summary.md`). Row closed.

### P2-FRONTEND-LINT-001

- **priority:** P2
- **status:** fixed
- **category:** frontend_quality
- **file_path:** `frontend/styles.css`
- **line/function:** Prettier formatting
- **evidence:** Prompt 4 full validation records `npm run lint:js` failing because Prettier wants changes in `frontend/styles.css`. Log: `artifacts/validation/runs/20260612T162028Z_full/commands/21_frontend_lint_js.md`.
- **why_it_matters:** Frontend lint drift breaks reproducible validation.
- **impact:** CI/lint failure even when frontend tests pass.
- **recommended_fix:** Run the existing formatter or make equivalent focused CSS formatting edits.
- **tests_needed:** `npm run lint:js`.
- **acceptance_criteria:** Frontend lint exits 0.
- **blocked_by:** None.
- **notes:** Resolved (2026-06-22): Prettier formatting applied to `frontend/styles.css` via existing formatter. `npm run lint:js` exits 0.

### P1-DOCS-001

- **priority:** P1
- **status:** fixed
- **category:** documentation_truth
- **file_path:** `PROJECT_STATUS.md`, `docs/CURRENT_STATUS.md`, `docs/PRODUCTION_READINESS.md`, `docs/ROADMAP.md`, `docs/LIMITATIONS.md`, `README.md`, `docs/TESTING.md`
- **line/function:** document claims audited in `artifacts/audit/DOCS_TRUTH_CHECK.md`
- **evidence:** Phase 0 doc truth check identifies production/SaaS readiness and large passing-test-count claims that are not reproduced by current validation. Current backend full suite is red and production readiness gates were not run.
- **why_it_matters:** Future agents and operators can make unsafe decisions from stale readiness claims.
- **impact:** Overconfident release posture, missed security/test gaps, and wasted engineering time.
- **recommended_fix:** Add historical banners or update docs to cite current command evidence only.
- **tests_needed:** Documentation review plus current validation logs.
- **acceptance_criteria:** No doc calls the project production-ready or 100/100 SaaS-ready without current evidence.
- **blocked_by:** None.
- **notes:** Resolved (2026-06-22): `PROJECT_STATUS.md`, `docs/CURRENT_STATUS.md`, `docs/PRODUCTION_READINESS.md`, `docs/ROADMAP.md` no longer exist. `docs/LIMITATIONS.md` and `docs/TESTING.md` already have historical banners pointing to `docs/AGENT_TRUTH.md`. `README.md` already says "pre-production candidate" with a "Banned Overclaims" section. No doc calls the project production-ready or 100/100 SaaS-ready without current evidence.

### P2-ENV-001

- **priority:** P2
- **status:** fixed
- **category:** developer_environment
- **file_path:** `docs/AGENT_TRUTH.md`, validation command output
- **line/function:** baseline command compatibility
- **evidence:** Literal `python --version` and `python -m ...` commands fail because `python` is not installed; `python3` commands pass. Prompt 4 documents the local `python3` runner in `docs/VALIDATION.md`, `AGENTS.md`, and `README.md`.
- **why_it_matters:** Baseline instructions using `python` are not reproducible in this workspace.
- **impact:** Onboarding friction and misleading failure reports.
- **recommended_fix:** Fixed for local docs by documenting `python3 scripts/validate_local.py ...` commands.
- **tests_needed:** Rerun baseline commands exactly as documented.
- **acceptance_criteria:** Baseline docs match the executable available in the workspace.
- **blocked_by:** None.
- **notes:** GitHub Actions still uses `python` after `actions/setup-python`; local docs use `python3`.

### P1-VALIDATION-002

- **priority:** P1
- **status:** fixed
- **category:** validation_reproducibility / reporting
- **file_path:** `scripts/run_validation.sh`, `scripts/verify_all.sh`, `Makefile`, `.github/workflows/ci.yml`
- **line/function:** local validation entry points
- **evidence:** Prompt 4 inspection found no prior one-command Python validation runner that produced Markdown and JSON summaries, per-command logs, timeouts, redaction, and archived runs. `Makefile` also had a `validate` target without a recipe and an accidental `scripts/verify_all.sh` invocation under `api-docs-check`.
- **why_it_matters:** Future agents need a reproducible way to know whether the project is healthy without relying on stale docs or terminal-only output.
- **impact:** Validation failures could be hidden, overwritten, or described inconsistently.
- **recommended_fix:** Fixed by adding `scripts/validate_local.py`, validation artifacts under `artifacts/validation/`, `docs/VALIDATION.md`, Makefile targets, CI quick validation, parseable JSON stdout, and updated truth docs.
- **tests_needed:** Run quick and full validation paths.
- **acceptance_criteria:** Quick validation exits 0, writes logs, `--json` stdout parses as JSON, and full validation captures current failures with log paths.
- **blocked_by:** None.
- **notes:** Prompt 4 quick validation passes; full validation is red for the separately tracked issues above.

### P1-ARCH-ROUTER-001

- **priority:** P1
- **status:** fixed
- **category:** architecture / route_complexity / duplicated_route_logic
- **file_path:** `backend/app/routers/jobs_write.py`, `backend/app/services/job_mutation_service.py`, `backend/tests/test_jobs_write_characterization.py`, `backend/tests/test_job_mutation_service.py`
- **line/function:** `register_jobs_write_routes`, `JobCancellerService`, `JobBackfillService`, `JobReclenerService`
- **evidence:** Code verified 2026-06-22: `register_jobs_write_routes` delegates cancel, backfill, and reclean to `JobCancellerService`, `JobBackfillService`, and `JobReclenerService` in `app/services/job_mutation_service.py`. The router handles only HTTP/dependency wiring. 26 characterization tests in `test_jobs_write_characterization.py` (created Session 4) pin the HTTP contract. 14 isolated unit tests in `test_job_mutation_service.py` (added 2026-06-22) exercise service classes directly: cancel lifecycle, tenant isolation, access control, backfill source-type inference, reclean validation guards, and reclean success path.
- **why_it_matters:** Service extraction and focused tests reduce regression risk when URL Intelligence, Workflow Replay, or SaaS usage enforcement touch job creation.
- **impact:** Future feature work can change auth, quota, or persistence in the service layer without altering router HTTP wiring.
- **recommended_fix:** Completed: service extraction + characterization tests + isolated unit tests.
- **tests_needed:** Covered: 26 HTTP characterization tests (create/cancel/delete/clear/restore/hard-delete) + 14 unit tests (cancel lifecycle, backfill inference, reclean guards/success).
- **acceptance_criteria:** All 40 tests pass. Routes delegate business decisions to tested service code. `python3 -m pytest tests/test_jobs_write_characterization.py tests/test_job_mutation_service.py -q` exits 0.
- **blocked_by:** None.
- **notes:** Fixed 2026-06-22. Service extraction (JobCancellerService, JobBackfillService, JobReclenerService) was done in Session 4. Characterization tests (26) were also added in Session 4. Isolated unit tests (14) added in the current session, covering: missing-job 404, terminal-job early return, pending auto-cancel, running cancel without status change, cross-org denial, admin all-access, backfill source inference, backfill skip when known, reclean running/rejected/no-results/no-schema/denied/success. All 40 tests pass; P0 regression suite (53 tests) also green.

### P1-ARCH-SELECTOR-001

- **priority:** P1
- **status:** fixed
- **category:** architecture / extraction_pipeline_complexity
- **file_path:** `backend/app/services/url_analysis_pipeline.py`, `backend/tests/test_url_analysis_pipeline.py`
- **line/function:** `URLAnalysisPipeline`, `run()`, all 8 stages
- **evidence:** Session 4 created `url_analysis_pipeline.py` (614 LOC, 8 stages + orchestrator). Session 3 added 12 unit tests in `test_url_analysis_pipeline.py`: `_build_error_response` shape + suggestions, `_stage_resolve_url` error passthrough, `_stage_detect_session` config-gated call, `_stage_fetch_page` error/empty/success paths, `_stage_analyze_page` detection calls, `run()` happy path, `run()` fetch error early return, `run()` escalation loop. All 34 pipeline+state-machine tests pass; 12/12 quick validation green.
- **why_it_matters:** URL Intelligence and Workflow Replay depend on the same page-analysis concepts. A large mixed pipeline makes it hard to change classification, preview, or field detection safely.
- **impact:** Product feature work can regress existing extraction/discovery behavior or accidentally mix experimental heuristics into stable paths.
- **recommended_fix:** Completed: `url_analysis_pipeline.py` extracts the pipeline into 8 stage methods + orchestrator. 12 unit tests pin each stage's contract including error paths, escalation, and the empty-page guard.
- **tests_needed:** Covered: error response shape, fetch error/empty/success, session detection gate, page analysis detection, happy-path run, fetch-error early return, escalation recursion.
- **acceptance_criteria:** All pipeline stage unit tests pass; 12/12 quick validation green.
- **blocked_by:** None.
- **notes:** Fixed 2026-06-22 session 3. Pipeline extraction (8 stages) was done in Session 4; unit tests added in Session 3 (this session). `selector_discovery.py` was refactored to use PEP 562 `__getattr__` for lazy research-module imports (Session 4). No remaining open architecture concerns for this issue.

### P1-ARCH-STATE-001

- **priority:** P1
- **status:** fixed
- **category:** architecture / job_state_model
- **file_path:** `backend/app/services/job_state_machine.py`, `backend/tests/test_job_state_machine_central.py`
- **line/function:** `transition_to`, `mark_canceled`, `mark_recovered_failed`, `can_transition`, `is_terminal`, `valid_transitions_from`
- **evidence:** Session 4 created `job_state_machine.py` (200 LOC, 6 public functions, comprehensive transition table). Session 3 added 22 unit tests covering all mutation functions: `transition_to` valid/invalid/idempotent/error/cancel/terminal-timestamp, `mark_canceled` from PENDING/DISCOVERING/RUNNING/terminal, `mark_recovered_failed` from PENDING/RUNNING/terminal, `can_transition` valid/invalid, `is_terminal`, `valid_transitions_from`, `_TERMINAL_STATUSES` completeness. Existing 5 previous tests (central source, valid paths, invalid paths, terminal identification, timestamp) preserved. Two inline bypass spots documented with comments: `jobs_read.py:174` (cache sync, not a transition) and `postgres_repository_base.py:799` (SQL persists state-machine decision). All 27 state machine tests pass; 12/12 quick validation green.
- **why_it_matters:** Job state drives user-visible status, retries, cancellation, result availability, and future workflow monitoring.
- **impact:** Adding workflow preview/runs, monitoring, retries, or billing gates can create invalid or inconsistent job states.
- **recommended_fix:** Fully centralized: `job_state_machine.py` is the single source of truth for all transitions. `mark_canceled`, `mark_recovered_failed`, and `transition_to` handle all mutation paths with H7 invalid-transition guard. Inline assignments in `jobs_read.py` and `postgres_repository_base.py` are documented as intentional (cache sync / DB persistence).
- **tests_needed:** Covered: all 12 declared transitions, 3 invalid paths, 4 terminal states, cancel from 3 non-terminal states, recovery from 2 non-terminal states, idempotent same-status, error/cancel_requested/completed_at metadata, `valid_transitions_from` for pending and terminal.
- **acceptance_criteria:** All 27 state machine tests pass; no uncommented inline status assignments exist; 12/12 quick validation green.
- **blocked_by:** None.
- **notes:** Fixed 2026-06-22 session 3. Centralization (Session 4) created the state machine. Mutation tests and inline comments added in Session 3 (this session). Remaining runner and startup-recovery paths already use `mark_recovered_failed` or `transition_to`. No open concerns remain.

### P1-ARCH-STORAGE-001

- **priority:** P1
- **status:** fixed
- **category:** architecture / storage_repository_boundaries
- **file_path:** `backend/app/storage_interface.py`, `backend/app/job_store.py`, `backend/app/postgres_repository_base.py`, `backend/app/storage_mapper.py`, `backend/app/storage_migrations.py`, `backend/app/storage_health.py`, `docs/STORAGE_BOUNDARIES.md`
- **line/function:** `JobRepository`, `SQLiteJobRepository`, `PostgresRepositoryBase`
- **evidence:** Fresh optional Postgres suite on 2026-06-24: `python3 -m pytest --run-postgres backend/tests/test_repository_parity.py backend/tests/test_postgres_repository.py backend/tests/test_postgres_integration.py -q -o addopts= --tb=short` failed before the fix on two soft-delete restore tests, then passed after the fix with 77 passed. `docs/STORAGE_BOUNDARIES.md` now reflects the current split: `storage_mapper.py` owns row serialization, `storage_migrations.py` owns DDL/migrations, `storage_health.py` owns health/status checks, and routers call repository interface methods.
- **why_it_matters:** Tenant isolation, retention/deletion, exports, audit logs, and workflow storage all depend on clear repository boundaries.
- **impact:** Storage changes can drift between SQLite and Postgres or bypass owner/org/project persistence expectations.
- **recommended_fix:** Fixed for current boundary and parity scope. Continue future storage work through repository interfaces plus mapper/migration/health helper modules; do not add new router imports of storage-private helpers.
- **tests_needed:** Covered by `backend/tests/test_repository_parity.py`, `backend/tests/test_postgres_repository.py`, `backend/tests/test_postgres_integration.py`, `backend/tests/test_storage_mapper.py`, and SQLite repository tests.
- **acceptance_criteria:** Repository interfaces expose explicit ownership-aware methods and SQLite/Postgres behavior is covered by parity tests.
- **blocked_by:** None for local Docker/testcontainers parity. Production/staging failover, backups, and alert delivery remain separate ops evidence categories.
- **notes:** Session 4 (2026-06-22) created `storage_mapper.py` to deduplicate serialization/deserialization between `job_store.py` and `postgres_repository_base.py`. Postgres schema v8 was added. SQLite ownership parity tests were added (+6 tests). Session 4 follow-up (2026-06-22): added 36 direct `storage_mapper` unit tests in `test_storage_mapper.py`. Session 5 (2026-06-22): added 13 SQLite repository unit tests in `test_sqlite_repository_untested.py` covering `is_cancel_requested`, `save_world_state`/`load_world_state`, `count_jobs_by_status`, `record_worker_heartbeat`/`get_worker_health`/`get_all_worker_healths`. 2026-06-24: current code has `storage_migrations.py` and `storage_health.py`, storage status/ready routes use repository interface methods, and fresh `--run-postgres` storage suites pass. The same run exposed and fixed Postgres active upserts over soft-deleted rows by clearing `deleted_at` in `PostgresRepositoryBase.save_all` and `save_single`.

### P1-BENCHMARK-BASELINE-001

- **priority:** P1
- **status:** fixed
- **category:** benchmark_readiness / quality_baseline
- **file_path:** `backend/benchmarks/local_corpus_expected.json`, `backend/benchmarks/local_corpus.py`, `backend/benchmarks/test_local_corpus_baseline.py`, `docs/BENCHMARK_PLAN.md`, `scripts/run_benchmark_smoke.py`
- **line/function:** Prompt 7 benchmark baseline
- **evidence:** `python3 scripts/run_benchmark_smoke.py` passed on 2026-06-24 with 33 passed, 2 skipped, 1 deselected. `artifacts/benchmarks/latest_local_corpus.json` records 14 deterministic local cases, `row_f1=1.0`, `field_f1=1.0`, `false_positive_records=0`, `browser_failures=0`, and no live sites.
- **why_it_matters:** Product feature work needs a repeatable quality baseline before changing extraction and workflow behavior.
- **impact:** Without a fuller baseline, URL Intelligence, Workflow Replay, and extraction-depth work can regress quality without a clear signal.
- **recommended_fix:** Fixed for deterministic local corpus. Keep staging/browser/golden-live/load proof tracked separately and do not treat local corpus success as production readiness.
- **tests_needed:** Covered by `backend/benchmarks/test_local_corpus_baseline.py`, `backend/tests/test_extraction_precision.py`, and `backend/tests/test_zero_result_classifier.py`.
- **acceptance_criteria:** Benchmark report includes precision, recall, F1, missing fields, duplicates, invalid types, runtime, timeout rate, and browser failures for every required corpus category.
- **blocked_by:** None for local deterministic corpus.
- **notes:** Existing live golden tests are observational and must not be used as deterministic proof. Deferred 2026-06-22 — corpus expansion is product-quality work, not a safety defect. Session 4 follow-up (2026-06-22): added 4 new fixture HTML pages (`search_results.html`, `session_expired.html`, enhanced `load_more_mock.html`, enhanced `login_wall_mock.html`). Session 5 (2026-06-22): added `infinite_scroll_mock.html` with extraction test. search_results and infinite_scroll now wired into `test_fixture_extraction_yields_records`. 2026-06-24: all required fixture categories now have named local fixtures and an enforcement test. 2026-06-24 follow-up: local expected outputs and thresholds are versioned in `backend/benchmarks/local_corpus_expected.json`; smoke now runs `backend/benchmarks/test_local_corpus_baseline.py` and writes `artifacts/benchmarks/latest_local_corpus.*`.

### P2-BENCHMARK-CORPUS-001

- **priority:** P2
- **status:** fixed
- **category:** benchmark_corpus / fixture_coverage
- **file_path:** `backend/tests/fixtures/pages`, `backend/tests/golden_dataset`, `artifacts/audit/BENCHMARK_READINESS_REVIEW.md`
- **line/function:** required corpus coverage table
- **evidence:** Current corpus coverage is enforced by `backend/tests/test_benchmark_fixtures.py::test_required_benchmark_corpus_categories_have_local_fixtures`. Named fixtures now cover static product, listing, table, article, search, pagination, infinite scroll, load-more, session/workflow, network JSON-backed, empty/no-result, malformed HTML, login-required, and challenge pages.
- **why_it_matters:** Extraction quality cannot be compared across releases without representative local fixtures.
- **impact:** Feature work can optimize for a narrow fixture set and miss common user workflows.
- **recommended_fix:** Fixed for fixture coverage. Keep expected-output and threshold work under `P1-BENCHMARK-BASELINE-001`.
- **tests_needed:** Covered by `backend/tests/test_benchmark_fixtures.py`; local benchmark smoke uses no live-site dependency.
- **acceptance_criteria:** Required corpus categories are present, documented, and run without live-site dependency.
- **blocked_by:** None.
- **notes:** Fixed 2026-06-24. Added `workflow_search_mock.html`, `network_catalog_page.html`, `network_catalog_payload.json`, `table_catalog.html`, `empty_results.html`, `malformed_listing.html`, and `challenge_mock.html`; `python3 scripts/run_benchmark_smoke.py` passes.

### P1-OPS-BACKUP-RESTORE-001

- **priority:** P1
- **status:** fixed
- **category:** ops_readiness / backup_restore
- **file_path:** `scripts/backup_postgres.sh`, `scripts/restore_postgres.sh`, `artifacts/audit/OPS_READINESS_REVIEW.md`
- **line/function:** Postgres backup and restore utilities
- **evidence:** Prompt 7 inspection confirms backup and restore scripts exist, but no current staging backup/restore drill was run or recorded.
- **why_it_matters:** Production readiness requires proof that data can be restored, not only a backup script.
- **impact:** A failed migration or data loss event may be unrecoverable in practice.
- **recommended_fix:** Run a disposable Postgres backup/restore drill and record command evidence, backup metadata, and verification queries.
- **tests_needed:** Backup creates valid gzip dump; restore into disposable DB; app `/ready` and row-count checks after restore.
- **acceptance_criteria:** Restore drill evidence is stored in audit artifacts and repeated before production launch.
- **blocked_by:** None.
- **notes:** Fixed 2026-06-23. The Postgres v8 schema file was dumped from the active production-like container to `backend/migrations/008_postgres_storage_v8.sql` and used in `scripts/backup_and_restore_test.py` to run the self-contained Postgres backup/restore drill inside a disposable docker database. The drill completed successfully, confirming full data restoration without row losses, and wrote its findings to `artifacts/backup_drill/latest_drill.json`.

### P1-OPS-LOAD-ALERT-001

- **priority:** P1
- **status:** deferred (blocked by staging environment)
- **category:** ops_readiness / load_tests_alerting
- **file_path:** `artifacts/audit/OPS_READINESS_REVIEW.md`, `docs/OPS_READINESS_CHECKLIST.md`
- **line/function:** load tests and alert delivery
- **evidence:** Prompt 7 ops review marked load testing as missing and alert delivery as unverified. Local load-test evidence now exists and is reproducible with `scripts/run_load_test.py`; staging alert delivery remains unverified.
- **why_it_matters:** Scraper workloads can exhaust browser, queue, storage, or target-domain budgets under load.
- **impact:** Production incidents may not alert operators or may appear only after user-facing degradation.
- **recommended_fix:** Add bounded load tests and run the staging alert-delivery drill with documented thresholds and recipients.
- **tests_needed:** Load test for job creation/queue/browser caps; alert test for worker heartbeat, failed-job rate, auth failures, and quota denials. Use `scripts/run_alert_delivery_drill.py --require-notification-evidence` for synthetic Alertmanager routing plus real notification proof.
- **acceptance_criteria:** Load and alert drill artifacts exist and are linked from ops readiness docs.
- **blocked_by:** Staging environment and alert destination.
- **notes:** No product behavior was changed in Prompt 7. Session 4 follow-up (2026-06-22): `python3 scripts/run_load_test.py --requests 100 --concurrency 10` ran against local `/health`: 100/100 success, 348 RPS, p50 12ms, p95 74ms, p99 127ms, 0 failures. 2026-06-24 reproducibility pass restored the deleted load runner, added `--json` / `--json-file`, regenerated `artifacts/load_test/latest_run.json` as valid JSON, and reran local `/health`: 100/100 success, 340.26 RPS, p50 12.59ms, p95 73.62ms, p99 127.57ms, 0 failures. `scripts/smoke_prod_stack.sh` now requires Alertmanager to be running and checks Prometheus readiness/rules, Grafana health, and Alertmanager readiness. 2026-06-24 synthetic alert drill pass added `scripts/run_alert_delivery_drill.py` with unit tests; it verifies Alertmanager acceptance/API visibility and explicitly requires human notification evidence for staging readiness. Alert delivery drill remains blocked by staging environment and a real destination.

### P1-COMPLIANCE-RETENTION-001

- **priority:** P1
- **status:** fixed
- **category:** compliance / acceptable_use / retention
- **file_path:** `docs/SAFETY_AND_ACCEPTABLE_USE.md`, `artifacts/audit/COMPLIANCE_BASELINE.md`
- **line/function:** data retention and acceptable-use controls
- **evidence:** Prompt 7 compliance baseline documents acceptable-use rules and finds retention/deletion policy only partial. Recycle/delete paths exist, but a formal retention/delete policy and tests are not complete.
- **why_it_matters:** SaaS use requires clear handling of scraped data lifecycle and abuse controls.
- **impact:** Legal/privacy risk and unclear customer/operator expectations.
- **recommended_fix:** Define retention windows, hard-delete behavior, export logs, abuse flags, and admin workflows; add tests.
- **tests_needed:** Retention expiration, hard delete, restore window, export logging, audit event, and tenant isolation tests.
- **acceptance_criteria:** Retention/delete behavior is documented, tested, and visible to operators.
- **blocked_by:** Product/legal retention decisions.
- **notes:** Closed 2026-06-22 session 2: defaults enforced in code (`data_retention.py`), tests in `test_retention.py`, operator policy documented in `docs/COMPLIANCE_RETENTION.md`. Legal/customer-facing terms still require product review.

### P1-AUDIT-COVERAGE-001

- **priority:** P1
- **status:** fixed
- **category:** audit_logging / coverage_baseline
- **file_path:** `backend/app/audit_logger.py`, `backend/tests/test_audit_logger.py`, `artifacts/audit/COMPLIANCE_BASELINE.md`
- **line/function:** audit event coverage map
- **evidence:** Audit logger and tests exist for auth, RBAC, admin, data access, job, and system events. Prompt 7 baseline records that full resource coverage has not been mapped across auth failures, tenant denials, quota denials, exports, deletes, workflow/profile use, and domain blocks.
- **why_it_matters:** Incident response and compliance require knowing which security-sensitive actions are auditable.
- **impact:** Operators may be unable to investigate data access, abuse, or tenant-boundary violations.
- **recommended_fix:** Build an audit coverage matrix and add missing event assertions for security-sensitive routes.
- **tests_needed:** Route-level audit assertions for auth failure, tenant denial, quota denial, export access, delete/restore, workflow run, auth profile use, and URL safety block.
- **acceptance_criteria:** Audit coverage matrix has no unknown rows for P0/P1 resources.
- **blocked_by:** Route/resource inventory update after future feature work.
- **notes:** Closed 2026-06-22 session 2. All P0/P1 security-sensitive routes in the audit matrix now have code + tests, including workflow draft cross-tenant denial (`test_project_scoped_key_cannot_access_another_orgs_workflow_draft`).

### P2-OBSERVABILITY-METRICS-001

- **priority:** P2
- **status:** fixed
- **category:** observability / metrics_baseline
- **file_path:** `docs/OBSERVABILITY.md`, `backend/app/metrics_collector.py`, `backend/app/routers/system.py`
- **line/function:** required future metrics and events
- **evidence:** Current `backend/tests/test_metrics_observability.py` enforces the required local product counters, duration metrics, browser-context counters, and domain failure-rate metric. `/metrics` emits the required series in the fallback renderer and the `prometheus_client` renderer. Adjacent metrics/domain/browser/billing suites pass.
- **why_it_matters:** Operators need stable signals for jobs, browser failures, quota denials, auth failures, tenant denials, exports, workflows, and domain health.
- **impact:** Missing or unmapped metrics delay incident detection and launch readiness.
- **recommended_fix:** Fixed for local implementation and endpoint contract. Keep staging scrape and alert threshold proof under `P1-OPS-LOAD-ALERT-001`.
- **tests_needed:** Covered locally by `backend/tests/test_metrics_observability.py`, `backend/tests/test_metrics.py`, `backend/tests/test_domain_runtime_policy.py`, `backend/tests/test_browser_pool.py`, and `backend/tests/test_p0_billing_usage.py`.
- **acceptance_criteria:** Required metrics/events are implemented or explicitly deferred with rationale and tests.
- **blocked_by:** None.
- **notes:** Session 2 (2026-06-22): Core product counters implemented in `metrics_collector.py`, wired via audit logger / job creation / finalization / exports / workflow routes, exposed on `/metrics`. Fixed 2026-06-24: product counters now have stable zero defaults, normal metrics rendering exposes them, job/page duration histograms are recorded, browser-context counters are wired to `BrowserPool`, and domain failure rate is exported from `DomainRuntimePolicy`. Staging scrape proof and alert thresholds remain ops follow-up in `P1-OPS-LOAD-ALERT-001`.

### P1-MIGRATION-ROLLBACK-001

- **priority:** P1
- **status:** fixed
- **category:** migration_rollback / data_safety
- **file_path:** `docs/MIGRATION_AND_ROLLBACK_POLICY.md`, `scripts/migration_rollback_test.py`, `scripts/backup_postgres.sh`, `scripts/restore_postgres.sh`, storage migration tests
- **line/function:** migration and rollback policy
- **evidence:** Prompt 7 created a migration/rollback policy. Existing migration tests and backup/restore scripts exist, but no current migration rollback or restore drill evidence was produced. Session 5 (2026-06-22): `scripts/migration_rollback_test.py` created and passed — creates schema, seeds data, applies additive columns, rolls them back, verifies core data survives, re-applies migration.
- **why_it_matters:** Schema changes for workflows, auth profiles, billing, and SaaS models can cause data loss without tested rollback paths.
- **impact:** Failed migrations can break production or corrupt tenant data.
- **recommended_fix:** Add migration tests for new schema changes and run backup/restore drill before destructive or high-risk migrations.
- **tests_needed:** Existing-row migration, new-row read/write, SQLite/Postgres parity, restore drill, owner/org/project preservation.
- **acceptance_criteria:** Each schema change links to migration tests and rollback/restore evidence.
- **blocked_by:** None.
- **notes:** Fixed 2026-06-23. The migration rollback policy is fully implemented. The rollback verification script `scripts/migration_rollback_test.py` was executed and completed successfully, verifying that all database columns can be added, rolled back (retaining the core seed datasets), and re-migrated cleanly without data corruption on SQLite. Results written to `artifacts/migration_drill/latest_drill.json`.

### P2-URL-INTELLIGENCE-001

- **priority:** P2
- **status:** fixed
- **category:** product_feature / url_intelligence / guided_scrape_entry
- **file_path:** `backend/app/url_analyzer.py`, `backend/app/routers/system.py`, `backend/app/routers/intelligence.py`, `frontend/js/analyzer.js`, `frontend/app.js`, `frontend/index.html`, `docs/URL_INTELLIGENCE.md`
- **line/function:** `analyze_url`, `UrlAnalysisResult.to_guided_dict`, `POST /api/url/analyze`, `renderIntelligencePanel`
- **evidence:** Prompt 8 targeted tests pass: `PYTHONPATH=backend python3 -m pytest backend/tests/test_url_analyzer.py -q` reports 53 passed; `npm run test -- frontend/js/analyzer.test.js` reports 25 passed.
- **why_it_matters:** Users need guidance before scraping brittle session URLs, login-looking pages, unsafe URLs, or normal public pages.
- **impact:** Without this, users can save expiring session URLs or attempt unsafe/blocked targets without clear explanation.
- **recommended_fix:** Implemented: no-fetch URL analysis, session parameter scoring without generic `id`, sensitive value redaction, stable start URL suggestions, guided frontend panel, and workflow draft entry.
- **tests_needed:** Classifier/unit tests, API tests for no-fetch and unsafe URL behavior, frontend panel rendering tests.
- **acceptance_criteria:** Normal URLs recommend Direct Scrape; session URLs recommend Workflow Replay and redact values; unsafe URLs return `blocked_or_unsafe`; frontend shows mode-specific actions.
- **blocked_by:** None.
- **notes:** Full Workflow Replay execution remains Prompt 9 scope.

### P1-RESEARCH-DANGLING-REF-001

- **priority:** P1
- **status:** fixed
- **category:** code_quality / dangling_reference
- **file_path:** `backend/app/research/__init__.py`
- **line/function:** lines 186, 357 (registry tuples)
- **evidence:** `backend/app/patch_status.py` was deleted but the string `"patch_status"` remained in two research-module registry tuples. If the experimental module loader resolved this string, it would fail with `ModuleNotFoundError`.
- **why_it_matters:** Dangling references in registry code can cause runtime failures when experimental routes are enabled.
- **impact:** Experimental mode startup could crash.
- **recommended_fix:** Remove `"patch_status"` from both registry tuples.
- **tests_needed:** Research boundary check; experimental mode smoke test.
- **acceptance_criteria:** Registry only references existing modules.
- **blocked_by:** None.
- **notes:** Fixed 2026-06-22 session 6: `"patch_status"` removed from both registry tuples in `research/__init__.py`.

### P1-DEADCODE-ORPHANED-SCRIPTS-001

- **priority:** P1
- **status:** fixed
- **category:** code_quality / dead_code
- **file_path:** `backend/tests/distributed_divergence.py`, `backend/tests/evolutionary_ecology.py`, `backend/tests/verify_symmetry.py`
- **line/function:** entire files
- **evidence:** Three scripts in `backend/tests/` (281 total lines) that are not prefixed with `test_` and are never collected by pytest. They compile successfully and contain `test_*` functions but are never imported or executed by any test runner. They import heavy modules (`SemanticWorldState`, `semantic_ir`) without providing test coverage value.
- **why_it_matters:** Dead code in the tests directory creates noise, increases maintenance burden, and can mislead about actual test coverage.
- **impact:** Directory clutter and wasted CI setup time if accidentally collected.
- **recommended_fix:** Delete the three files.
- **tests_needed:** Confirm no test file references them; full pytest collection stays clean.
- **acceptance_criteria:** All three files removed from git tracking; pytest collection count unchanged.
- **blocked_by:** None.
- **notes:** Fixed 2026-06-22 session 6: all three files deleted via `git rm`.

## Candidate Issues

### P2-WORKFLOW-REPLAY-FOUNDATION-001

- **priority:** P2
- **status:** fixed
- **category:** product_feature / workflow_replay / fixture_backed_foundation
- **file_path:** `backend/app/routers/workflow.py`, `backend/app/models.py`, `backend/app/services/workflow_runner.py`, `frontend/js/analyzer.js`, `frontend/index.html`, `docs/WORKFLOW_REPLAY.md`
- **line/function:** `detect_workflow_draft_fields`, `create_workflow_from_manual_mapping`, `preview_workflow`, `renderWorkflowDraftPanel`
- **evidence:** Prompt 9 targeted tests pass: `PYTHONPATH=backend python3 -m pytest backend/tests/test_workflow.py -q` reports 25 passed; `npm run test -- frontend/js/analyzer.test.js` reports 26 passed. Tests cover draft from session URL, field detection on fixture HTML, manual mapping to steps, snapshot preview sample rows, missing selector failure, sensitive value redaction, unsafe start URL rejection, and frontend draft panel rendering.
- **why_it_matters:** Session/search/form sites need reliable replay from a stable start page instead of depending on a temporary result URL.
- **impact:** Users can create a replay draft, confirm a stable start URL, map fields, and preview deterministic fixture-backed extraction with timeline/failure output.
- **recommended_fix:** Implemented for deterministic local HTML snapshots and frontend handoff. Keep live Playwright navigation and persistent database storage as separate verified follow-up work.
- **tests_needed:** Current targeted tests above; future browser-backed replay tests should use local fixture servers and `--run-browser`.
- **acceptance_criteria:** Draft creation, field detection, manual mapping, bounded snapshot preview, timeline/sample/failure response, redaction, unsafe URL rejection, and frontend draft panel all have passing tests.
- **blocked_by:** None for snapshot foundation.
- **notes:** This does not claim full live-site Playwright replay or Postgres workflow persistence.

### CAND-P2-WORKFLOW-REPLAY-BROWSER-001

- **priority:** P2
- **status:** candidate
- **category:** candidate_issue / workflow_replay / browser_execution_gap
- **file_path:** `backend/app/services/workflow_runner.py`, `backend/app/routers/workflow.py`
- **line/function:** `preview_workflow_snapshot`, `POST /api/workflows/{workflow_id}/preview`
- **evidence:** Prompt 9 preview currently requires `html_snapshot`; without one it returns `failure_type=preview_input_required` with warning that full browser preview is deferred behind the workflow runner boundary.
- **why_it_matters:** Real Workflow Replay must open a stable start page, execute bounded browser steps, and extract from the resulting page.
- **impact:** The current implementation is useful for deterministic fixtures and UI/API contract work, but not yet a full live browser replay feature.
- **recommended_fix:** Add Playwright-backed execution behind `backend/app/services/workflow_runner.py`, using only public start URLs validated by URL safety, bounded waits, no auth/CAPTCHA/paywall bypass, screenshot capture where safe, and local fixture-server tests.
- **tests_needed:** `--run-browser` local fixture tests for goto/fill/select/click/wait/extract, timeout caps, selector failure, screenshot artifact, resource cleanup, and no secret leakage.
- **acceptance_criteria:** Preview can execute against a local fixture HTTP server through Playwright and return sample rows/timeline/failure without live-site dependency.
- **blocked_by:** Browser fixture runner and Playwright runtime availability.
- **notes:** Candidate product gap, not a reproduced safety defect.

### CAND-P1-WORKFLOW-STORAGE-001

- **priority:** P1
- **status:** candidate
- **category:** candidate_issue / workflow_storage / persistence_parity
- **file_path:** `backend/app/routers/workflow.py`, storage repositories, migrations
- **line/function:** `_persist_workflows`, workflow CRUD
- **evidence:** Prompt 9 persists workflow definitions best-effort to a JSON file, but no SQLite/Postgres migration or repository parity was implemented or tested for workflows.
- **why_it_matters:** Durable SaaS workflows need the same owner/org/project persistence guarantees as jobs and exports.
- **impact:** Workflow definitions may not survive process/container lifecycle reliably and are not yet proven across storage backends.
- **recommended_fix:** Add repository-backed workflow storage with safe migrations, owner/org/project indexes, and SQLite/Postgres parity tests.
- **tests_needed:** SQLite workflow CRUD/reload, Postgres workflow CRUD/reload if available, migration existing-row handling, owner filtering after reload.
- **acceptance_criteria:** Workflows persist durably and tenant filters behave identically across supported storage backends.
- **blocked_by:** Storage architecture pass and Postgres test environment.
- **notes:** Candidate because no storage parity failure was reproduced; the current implementation is intentionally lightweight.

### CAND-P0-STORAGE-001

- **priority:** P0
- **status:** candidate
- **category:** candidate_issue / storage_parity / needs_verification
- **file_path:** `backend/app/job_store.py`, `backend/app/postgres_repository_base.py`, storage migrations/tests
- **line/function:** ownership fields `created_by`, `owner_id`, `user_id`, `org_id`, `project_id`
- **evidence:** Code inspection shows ownership fields in current models/repository paths, but Postgres parity/integration tests were not run in Phase 0.
- **why_it_matters:** Tenant isolation depends on ownership fields surviving storage round trips in every backend.
- **impact:** If parity is broken, a backend swap could leak or hide tenant data.
- **recommended_fix:** Add/refresh SQLite and Postgres parity tests for all ownership fields and migrations before changing storage code.
- **tests_needed:** Create/read/list/filter jobs with owner/org/project in SQLite and Postgres; migration handling for existing rows.
- **acceptance_criteria:** Same ownership fields and filters work in both storage backends.
- **blocked_by:** Postgres test environment availability.
- **notes:** Candidate only; no current parity failure was reproduced.

### CAND-P1-FRONTEND-AUTH-001

- **priority:** P1
- **status:** fixed
- **category:** candidate_issue / frontend_auth_flow / needs_verification
- **file_path:** `frontend/index.html`, `frontend/js/*`, session endpoints
- **line/function:** frontend session state and protected API calls
- **evidence:** Backend session-cookie tests pass, but no current frontend E2E test proves login/session state matches protected backend authorization.
- **why_it_matters:** Users interact through the frontend; backend auth can be correct while the browser flow is broken or misleading.
- **impact:** Failed login UX, stale session display, or protected actions attempted without clear authorization state.
- **recommended_fix:** Add browser/UI tests for login, logout/session expiry display, and protected API calls with cookie-only auth.
- **tests_needed:** Playwright or equivalent frontend E2E for session login and denied operator action as user.
- **acceptance_criteria:** Frontend session state tracks backend `/api/session/me` and protected route outcomes.
- **blocked_by:** Frontend E2E setup not currently verified.
- **notes:** Closed 2026-06-22 session 2: `frontend/e2e/auth-flow.spec.js` covers authenticated job creation and form validation.

### CAND-P1-ROUTE-TENANT-001

- **priority:** P1
- **status:** fixed
- **category:** candidate_issue / route_auth_matrix / tenant_scope_needs_verification
- **file_path:** `backend/app/saas/router.py`, `docs/ROUTE_AUTH_MATRIX.md`, `artifacts/audit/ROUTE_AUTH_MATRIX.json`
- **line/function:** `GET /api/saas/plan`, `get_plan_info`
- **evidence:** Prompt 8 regenerated route auth matrix reports `unknown_tenant_scope_count=2`; one unknown row is `GET /api/saas/plan`, protected by `require_role_with_user`, with tenant scope marked `unknown`.
- **why_it_matters:** The route returns plan/billing-facing information. Future SaaS work needs to know whether this is global, per-user, per-org, or per-project before adding paid plan data.
- **impact:** If the endpoint later returns tenant-specific plan or billing data without explicit scoping, it could expose or misrepresent SaaS account state.
- **recommended_fix:** Decide and document whether `/api/saas/plan` is global default-plan metadata or tenant-scoped plan state. If tenant-scoped, require org/project context and add ownership tests. If global, document it and mark the route as not tenant-scoped in the generator with rationale.
- **tests_needed:** Route-auth matrix assertion for zero unknown tenant-scope rows; focused `/api/saas/plan` tests for user/admin/operator behavior and, if scoped, cross-org denial.
- **acceptance_criteria:** `python3 scripts/generate_route_auth_matrix.py` reports `unknown_tenant=0`, and `/api/saas/plan` scope is documented with matching tests.
- **blocked_by:** Product decision for global free-plan metadata versus tenant plan state.
- **notes:** Resolved (2026-06-18): `GET /api/saas/plan` now derives the tier from the authenticated `user_id` via `app.plan_enforcer.get_user_tier`, making the route explicitly per-user scoped. `python3 scripts/generate_route_auth_matrix.py` now reports `unknown_tenant=0` (was 2). The no-drift contract test `test_plan_limits_match_enforcement_source_of_truth` in `backend/tests/test_saas_router.py` pins the behavior. Row closed.

### CAND-P1-ROUTE-TENANT-002

- **priority:** P1
- **status:** fixed
- **category:** candidate_issue / route_auth_matrix / tenant_scope_needs_verification
- **file_path:** `backend/app/routers/workflow.py`, `docs/ROUTE_AUTH_MATRIX.md`, `artifacts/audit/ROUTE_AUTH_MATRIX.json`
- **line/function:** `POST /api/workflow-drafts/from-url-analysis`, `POST /api/workflow-drafts/{draft_id}/detect-fields`, `POST /api/workflow-drafts/{draft_id}/manual-mapping`
- **evidence:** Prompt 9 regenerated route auth matrix reports `unknown_tenant=4`; three unknown rows are workflow draft routes protected by `require_principal`. Prompt 9 tests prove draft create/detect/manual-mapping happy paths and unsafe start URL rejection, but no cross-tenant draft denial test was added.
- **why_it_matters:** Workflow drafts contain target URLs, suggested start URLs, and future workflow setup state.
- **impact:** If draft mutation endpoints are later expanded without explicit scope tests, tenant workflow setup data could become exposed.
- **recommended_fix:** Add persistent draft lifecycle tests for owner/org/project denial, update route-auth matrix classification for draft routes, or document draft routes as mutation-only with explicit scope helper rationale.
- **tests_needed:** Cross-org draft detect-fields/manual-mapping denial; route-auth matrix assertion for documented draft tenant scope.
- **acceptance_criteria:** `python3 scripts/generate_route_auth_matrix.py` reports no unknown tenant scope for workflow draft routes, or the matrix generator documents the exact tenant-scope rationale with matching tests.
- **blocked_by:** Draft lifecycle/test design.
- **notes:** Closed 2026-06-22 session 2: `test_project_scoped_key_cannot_access_another_orgs_workflow_draft` in `test_p0_auth_tenant.py`. Route matrix reports tenant scope `yes` for all draft routes.

### CAND-P1-ARCH-CHARTEST-001

- **priority:** P1
- **status:** fixed
- **category:** candidate_issue / missing_characterization_tests / locked
- **file_path:** `backend/tests/test_jobs_write_characterization.py`, `backend/tests/test_run_job_characterization.py`, `backend/tests/test_url_analyzer_characterization.py`, `backend/tests/test_selector_discovery.py`, `backend/tests/test_exports_router.py`, `backend/tests/test_repository_parity.py`, `frontend/e2e/auth-flow.spec.js`, `frontend/e2e/form.spec.js`
- **line/function:** job creation, selector discovery, workflow/direct-scrape frontend-to-backend flow
- **evidence:** Prompt 6 review identified refactor-sensitive areas and required characterization tests before splitting route/service/storage code. The current corpus now covers job creation contract (`test_jobs_write_characterization.py` 26 tests, `test_run_job_characterization.py` 18 tests), URL analysis pipeline (`test_url_analyzer_characterization.py` 18 tests), selector discovery primitives and fixture behavior (`test_selector_discovery.py::TestSelectorDiscoveryFixtureBehavior` 6 new tests, 2026-06-24), exports contract (`test_exports_router.py` ~1143 lines), storage ownership parity (`test_repository_parity.py`), and frontend-to-backend job submission (`frontend/e2e/auth-flow.spec.js`, `frontend/e2e/form.spec.js`). The Playwright auth-flow spec navigates the new-job form and verifies a queued job in the jobs list.
- **why_it_matters:** Architecture refactors without behavior locks can change API responses, state transitions, quota behavior, or extraction results.
- **impact:** Regression risk during feature work is now bounded by characterization tests on every refactor-sensitive module.
- **recommended_fix:** Fixed by completed characterization coverage. Each new architecture refactor should still add/extend its own characterization tests for the boundary it touches.
- **tests_needed:** Covered by the modules above. `python3 scripts/validate_local.py --quick` exits 0 and `backend/tests/test_selector_discovery.py` reports 54/54 passing.
- **acceptance_criteria:** All refactor-sensitive modules have characterization tests that exercise their public contract; relevant tests pass before and after any future refactor.
- **blocked_by:** None.
- **notes:** Closed 2026-06-24. Added `TestSelectorDiscoveryFixtureBehavior` with 6 fixture-backed characterization tests (legacy_directory, table_catalog, travel_site) that pin the contracts of `_analyze_page_data_type`, `_classify_value`, `_rename_generic_fields`, and `discover_selectors` (non-dict LLM payload handling). Job creation, exports, URL analysis, storage parity, and frontend-to-backend flow already had characterization tests when the 2026-06-22 and earlier session passes verified, so the candidate was a coverage gap rather than a missing test target.

### CAND-P1-ARCH-FRONTEND-FLOW-001

- **priority:** P1
- **status:** fixed
- **category:** candidate_issue / frontend_backend_flow_mismatch / needs_verification
- **file_path:** `frontend/js/form.js`, `frontend/js/api.js`, `frontend/e2e/form.spec.js`, `backend/app/routers/jobs_write.py`
- **line/function:** `submitJob`, `apiFetch`, `POST /api/jobs`
- **evidence:** Source inspection shows `frontend/js/form.js` submits jobs through `apiFetch` to `/api/jobs`, and `frontend/js/api.js` sends cookie credentials. Existing frontend E2E tests exercise form UI elements, but Prompt 6 did not verify an end-to-end authenticated job creation flow against the backend.
- **why_it_matters:** Backend auth and job creation can be correct while the browser job flow still fails due session state, payload shape, or UI assumptions.
- **impact:** Users may be unable to create jobs from the frontend even when API tests pass.
- **recommended_fix:** Add an E2E or contract test that logs in or configures auth, submits the frontend job form, and verifies the backend-created job response.
- **tests_needed:** Authenticated frontend job submission, denied unauthenticated submission, and payload compatibility tests.
- **acceptance_criteria:** Frontend job creation is verified against the current backend auth and request model.
- **blocked_by:** Verified frontend E2E backend wiring.
- **notes:** Closed 2026-06-22 session 2: `frontend/e2e/auth-flow.spec.js` submits a job via the UI and verifies it appears in the jobs list.

## Session 80 — New findings added 2026-06-25 (consolidated pre-existing scan)

This section adds 61 pre-existing problems found across infrastructure
(Docker/nginx/CI/monitoring/db migrations/env/scripts), security
(encryption/auth/tenant), and code-quality sweeps. Severity totals:

| Priority | Count |
|---|---|
| P0 | 9 |
| P1 | 22 |
| P2 | 30 |
| P3 | 5 |
| **Total** | **66** |

Every entry uses the same shape as the rest of the ledger
(priority / status / category / file_path / line_function /
evidence / why_it_matters / impact / recommended_fix /
tests_needed / acceptance_criteria / blocked_by / notes).
Status is `verified` unless noted.

### F-ENC-001

- **priority:** P0
- **status:** fixed
- **category:** security / encryption / silent_default_salt
- **file_path:** `backend/app/utils/encryption.py`
- **line_function:** `encrypt`; line 265
- **evidence:** `salt = os.environ.get("DATAFORGE_ENCRYPTION_SALT", "default-salt-change-in-prod")`. If `DATAFORGE_ENCRYPTION_SALT` is unset in production, per-user AES keys are derived via `hmac.new((user_id + salt).encode(...), salt.encode(...), hashlib.sha256)` — and `salt` is the source-visible literal string `"default-salt-change-in-prod"`. Anyone reading the repo who can guess or enumerate `user_id` strings can reproduce the per-user derived key and decrypt any AuthProfile/session-secret ciphertext.
- **why_it_matters:** Plaintext-equivalent leak for encrypted AuthProfile and session-secret fields. The non-dev path for app-level keys (lines 286-300) fails closed, but the per-user branch silently succeeds with the default salt.
- **impact:** Cross-account decryption of encrypted AuthProfile/session data if operators run without setting `DATAFORGE_ENCRYPTION_SALT`.
- **recommended_fix:** Remove the silent default; raise `EncryptionError` (or, in dev/test only, keep the fallback) when `DATAFORGE_ENCRYPTION_SALT` is unset in non-dev envs.
- **tests_needed:** Unit test asserting that encrypt with a `user_id` and unset `DATAFORGE_ENCRYPTION_SALT` raises in non-dev envs; existing round-trip tests continue to pass.
- **acceptance_criteria:** No code path derives AES keys from the literal `"default-salt-change-in-prod"` in staging or production.
- **blocked_by:** None.
- **notes:** New finding (Session 80). **Fix shipped:** salt constant renamed to `_DEFAULT_PER_USER_SALT = "dataforge-dev-only-per-user-salt-do-not-use-in-prod"` and the literal `"default-salt-change-in-prod"` is no longer used. `encrypt()` raises `EncryptionError` (and `decrypt()` raises `DecryptionError`) when `DATAFORGE_ENCRYPTION_SALT` is unset in any non-`{development,test}` env. Per-user payloads carry a `pu` flag + recorded `uid`; decrypt re-derives the same HMAC key only when the matching `user_id` is supplied. `auth_profiles.py` records `encrypted_by_user_id` alongside the ciphertext so `get_decrypted_storage_state` / `_try_live_session_check` can pass the right key. Guarded by `backend/tests/test_encryption.py::TestPerUserEncryptionSaltPolicy` (5 new tests).

### F-DOCKER-001

- **priority:** P0
- **status:** fixed
- **category:** infrastructure / docker / default_target_reload_debug
- **file_path:** `Dockerfile`, `docker-compose.yml`, `docker-compose.override.yml`
- **line_function:** Dockerfile `CMD` (dev stage, formerly line 91); `docker-compose.yml` build target; `docker-compose.override.yml` target + env var.
- **evidence:** Default target in `docker-compose.yml` is `dev`. Dev stage CMD runs `uvicorn app.main:app --reload --log-level debug`. Override mounts `./backend:/app/backend` and `./scripts:/app/scripts` from host. Combine with `PYTHONDEVMODE=1` in `docker-compose.override.yml:14` and Playwright browser contexts restart on every code reload.
- **why_it_matters:** A fresh `docker compose up` starts a debugger-enabled, host-write-watched reload loop. Tracebacks leak to container logs; `.pyc` files written as user `dataforge` against host UID-owned mounts.
- **impact:** Operators expecting a dev stack actually get noisy traceback logs, broken Playwright contexts on reload, and silent permission-denied issues.
- **recommended_fix:** Make `target: production` the default in `docker-compose.yml`; gate `--reload` and `--log-level debug` on `DATAFORGE_ENABLE_RELOAD` env. Optionally rename `dev` → `local-dev`.
- **tests_needed:** `python3 scripts/validate_local.py --quick` exits 0 after the change. `make up` no longer restarts the browser process on a host edit to unrelated files.
- **acceptance_criteria:** Default `docker compose up` does not pass `--reload`.
- **blocked_by:** None.
- **notes:** New finding (Session 80). **Fix shipped (Session 80 follow-up):** dev-stage `CMD` now runs a small shell wrapper that branches on `${DATAFORGE_ENABLE_RELOAD:-}` so `--reload --log-level debug` is opt-in. `docker-compose.yml` default flips from `target: dev` to `target: production`; `docker-compose.override.yml` now opts in to dev mode via `build.target: dev` plus `DATAFORGE_ENABLE_RELOAD=1`. Guarded by `backend/tests/test_docker_dev_target.py` (4 tests).

### F-NGINX-003

- **priority:** P0
- **status:** fixed
- **category:** infrastructure / nginx / path_traversal_rate_limit_bypass
- **file_path:** `nginx.conf`, `nginx.local.conf`
- **line_function:** `location /dashboard/` block in both files
- **evidence:** `location /dashboard/` used `proxy_pass http://dataforge_api;` without a URI component. nginx normalizes `..` segments before proxying: `/dashboard/../api/admin/foo` resolves to `proxy_pass http://dataforge_api/api/admin/foo` after normalization. The `/api/` location has `limit_req zone=api burst=20 nodelay`, but the `/dashboard/../api/...` path matches the prefix location and bypasses that throttle entirely. The same block in `nginx.local.conf` (used by `docker-compose.override.local.yml`) also lacks rate-limiting.
- **why_it_matters:** Unbounded request rate to `/api/admin/*` (and the rest of `/api/`) via the `/dashboard/` front-door. Combined with no `/api/admin` deny block in `nginx.local.conf`, attackers reach protected FastAPI routes at unlimited rate.
- **impact:** Admin endpoint probing, brute force, and DoS are all enabled by this single nginx config drift.
- **recommended_fix:** Move the rate-limit guard to `location ~ ^/(api|dashboard)/` regex block, or add `rewrite ^/dashboard/(.*)$ /dashboard/$1 break;` to force normalization before rate limiting.
- **tests_needed:** Integration test: burst 100 requests to `/dashboard/../api/health` and assert nginx returns 503/429 after the limit. Verify legitimate `/api/health` still answers.
- **acceptance_criteria:** Requests for `/api/...` paths trigger the `limit_req` regardless of the prefix used.
- **blocked_by:** None.
- **notes:** New finding (Session 80). **Fix shipped:** `nginx.conf` and `nginx.local.conf` `location /dashboard/` blocks both apply `limit_req zone=api burst=20 nodelay;` (same zone as `/api/`). Guarded by `backend/tests/test_nginx_rate_limit.py` (3 tests) which parses the uncommented server block from `nginx.conf`, extracts the `/dashboard/` location body, and asserts the zone is `api` (so a future refactor that introduces a fresh zone for dashboard would still fail).

### F-MON-001

- **priority:** P0
- **status:** fixed
- **category:** infrastructure / monitoring / alertmanager_silent_drop
- **file_path:** `scripts/smoke_prod_stack.sh`, `backend/tests/test_alerting_channel_smoke.py`
- **line_function:** new pre-drill step in smoke_prod_stack.sh, after `ALERT_READY` check, before worker logs
- **evidence:** `smtp_smarthost: '__ALERTMANAGER_SMTP_HOST__'` substitutes `''` (empty) if env unset. Same pattern for `__ALERTMANAGER_SLACK_WEBHOOK_URL__`. The pre-fix smoke only checked `/-/ready` which serves 200 even when both channels are empty. If both channels are empty, all `critical`/`warning`/`info` alerts are silently dropped. `scripts/run_alert_delivery_drill.py` exists but was not wired into `scripts/smoke_prod_stack.sh`.
- **why_it_matters:** Operators may believe the alerting pipeline works (Alertmanager shows alerts as "firing"), but no email/Slack delivery occurs. The drag-fail to deploy phase is invisible.
- **impact:** On-call never pages during real incidents; MTTR climbs; the "production-ready" claim is misleading.
- **recommended_fix:** Add a healthcheck to Alertmanager that asserts both channels reachable. Wire `python3 scripts/run_alert_delivery_drill.py` into `scripts/smoke_prod_stack.sh` so missing-channel deploys fail.
- **tests_needed:** Smoke test asserts a synthetic alert's receipt on each enabled channel; fails deployment if any channel is empty.
- **acceptance_criteria:** `make prod` cannot succeed when both `ALERTMANAGER_SMTP_HOST` and `ALERTMANAGER_SLACK_WEBHOOK_URL` are unset.
- **blocked_by:** None.
- **notes:** New finding (Session 80). Mitigates the existing `P1-OPS-LOAD-ALERT-001` gap. **Fix shipped:** added a fail-closed pre-drill check to `scripts/smoke_prod_stack.sh` that reads `.env.production` (falling back to `.env`) and refuses deploy when both `ALERTMANAGER_SMTP_HOST` and `ALERTMANAGER_SLACK_WEBHOOK_URL` are unset. Added the synthetic alert delivery drill via `scripts/run_alert_delivery_drill.py` inside the dataforge container as a follow-up regression sentinel. Guarded by `backend/tests/test_alerting_channel_smoke.py` (5 tests).

### F-DB-001

- **priority:** P0
- **status:** fixed
- **category:** infrastructure / db_migrations / non_idempotent_dump
- **file_path:** `backend/migrations/008_postgres_storage_v8.sql`, `scripts/normalize_migration_008.py`, `backend/migrations/008_postgres_storage_v8.sql.original`
- **line_function:** post-normalized file is structured as CREATE EXTENSION → CREATE TABLE IF NOT EXISTS → CREATE INDEX IF NOT EXISTS → guarded ALTER OWNER DO blocks → schema_version upsert
- **evidence:** Original file began with `\restrict fRKAyhUraWQwVaATmxbYMFspXTvDR27nZM2IShtu4LmwPtevKjM07DEsQblPrmN` and contained raw pg_dump 16 artifact metadata + bare CREATE TABLE / CREATE INDEX / ALTER OWNER lines that were not idempotent against a partially-migrated database.
- **why_it_matters:** Operators cannot bootstrap a fresh Postgres cluster via the migrations directory. The pattern was a per-version raw dump, not a migration step. The leading `\restrict` macro also breaks any tool that runs migrations through stdin (psql anti-paste token).
- **impact:** Disaster recovery from a `pg_dump` alone was not safe; `init-db/init.sql:13-21` only creates extensions (`uuid-ossp`, `pg_trgm`) and the actual schema creation is delegated to `app.postgres_repository._ensure_schema()`. There was no way to know which schema versions are applied from outside the app.
- **recommended_fix:** Use `pg_dump --schema-only --no-owner --no-privileges` for per-version DDL files. Drop `COPY` data. Track schema versions in a `schema_version` table that `_ensure_schema()` reads on boot.
- **tests_needed:** Restart-from-empty Postgres applies DDL files in order with no errors. `_ensure_schema()` idempotency test on already-migrated DB.
- **acceptance_criteria:** `psql -f migrations/<N>.sql` is replayable against any state and reports its version.
- **blocked_by:** None.
- **notes:** New finding (Session 80). **Fix shipped:** added `scripts/normalize_migration_008.py` (a deterministic, idempotent-on-itself transformer) and regenerated `backend/migrations/008_postgres_storage_v8.sql` from the raw dump (kept alongside as `.original` for forensic reference). The new file strips `\restrict`/`\unrestrict`, pg-dump session SETs, owner comments; rewrites CREATE TABLE / CREATE INDEX / CREATE SEQUENCE / CREATE UNIQUE INDEX to IF NOT EXISTS; wraps every `ALTER TABLE / SEQUENCE … OWNER TO` in a `DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '<role>')` guard so missing roles no-op; and tail-appends a `schema_version` upsert so operators can verify replay. Guarded by `backend/tests/test_db_migrations_008.py` (8 tests) including a fixed-point round-trip that runs the normalizer twice and asserts byte equality on the second pass.

### F-CI-001

- **priority:** P0
- **status:** fixed
- **category:** infrastructure / ci / unsanctioned_auto_merge
- **file_path:** `.github/workflows/dependabot-auto-merge.yml`
- **line_function:** `Approve PR` step at lines 38-43, `Enable auto-merge` at lines 47-48
- **evidence:** Approval runs unconditionally on any Dependabot PR; auto-merge gates only on `semver-patch OR semver-minor` after that approval. Major-version bumps (e.g. FastAPI 0→1) carry a bot approval mark and auto-merge without human review.
- **why_it_matters:** Misleading audit trail. A breaking change can land via Dependabot without any human changelog review. The audit log shows a bot approval as if a maintainer blessed it.
- **impact:** Sudden major-version regressions in FastAPI, SQLAlchemy, requests, etc.
- **recommended_fix:** Restrict approval AND auto-merge to `version-update:semver-patch` only. Leave `semver-minor` and `semver-major` for human review.
- **tests_needed:** Synthetic Dependabot PR with `semver-major` label does not auto-merge; `/approve` step is skipped.
- **acceptance_criteria:** No Dependabot major/minor PR lands without human approval.
- **blocked_by:** None.
- **notes:** New finding (Session 80). **Fix shipped:** `.github/workflows/dependabot-auto-merge.yml` now splits metadata, `approve-patch`, `enable-patch-auto-merge`, and human-review jobs. Only `version-update:semver-patch` PRs are auto-approved and auto-merged; minor/major updates require human review. Guarded by `backend/tests/test_dependabot_auto_merge.py`.

### F-CI-002

- **priority:** P0
- **status:** fixed
- **category:** infrastructure / ci / token_scope_bloat
- **file_path:** `.github/workflows/dependabot-auto-merge.yml`
- **line_function:** workflow-level `permissions` block at lines 21-23
- **evidence:** Workflow runs with `contents: write + pull-requests: write` at the workflow level for every Dependabot PR. `secrets.GITHUB_TOKEN` only narrows to merge-time, not to step scope.
- **why_it_matters:** A compromised step or injection race inherits write permissions through the lifetime of the run. Combined with mutable-tag `uses:` refs (F-CI-003) this is a vector for repo-wide takeover.
- **impact:** Repo-wide privilege escalation if any step in a Dependabot run is compromised.
- **recommended_fix:** Set `permissions: {}` at the workflow level, then per-job `permissions: { contents: read, pull-requests: write }`, escalating only at the merge step.
- **tests_needed:** Inspect job token scopes via `gh api` or a fixture workflow that asserts no `contents: write` until the explicit merge step.
- **acceptance_criteria:** No job in this workflow exposes write scope before its merge step runs.
- **blocked_by:** None.
- **notes:** New finding (Session 80). **Fix shipped:** workflow-level permissions are `{}`. Metadata/approval jobs only receive read or pull-request write scope; `contents: write` exists only on the patch merge job. Guarded by `backend/tests/test_dependabot_auto_merge.py`.

### F-DOCKER-007

- **priority:** P0
- **status:** fixed
- **category:** infrastructure / docker / hardcoded_credentials
- **file_path:** `docker-compose.override.local.yml`
- **line_function:** lines 27, 41, 55, 107
- **evidence:** Hardcoded plaintext credentials:
  - line 27: `DATAFORGE_DATABASE_URL=postgresql://dataforge:wxXv4_eSGypDSVxiZlxIRQ@postgres:5432/dataforge`
  - line 41: same credential
  - line 55: `GF_SECURITY_ADMIN_PASSWORD=Nz4HdRUjt_GnwrP9-TzFkA`
  - line 107: `DATA_SOURCE_NAME=postgresql://dataforge:wxXv4_eSGypDSVxiZlxIRQ@postgres:5432/dataforge?sslmode=disable`
  - plus dummy Slack webhook URL at line 74.
  The same DB password appears in `.env.production` (mode 0600). Anyone rebuilding the local stack from a fresh clone commits these credentials to memory; if a remote `postgres` host exposes port 5432, those creds work.
- **why_it_matters:** A file marked "local testing override" is actually wiring production-environment-mirror credentials. Anyone with a `git clone` can reuse them against an exposed remote.
- **impact:** Database takeover + Grafana admin takeover via the committed local override.
- **recommended_fix:** Replace hardcoded credentials with `${DATAFORGE_DB_PASSWORD}` / `${GRAFANA_PASSWORD}` substitution. Delete the dummy Slack webhook URL. Document the env-var requirements in `.env.example`.
- **tests_needed:** `grep -E "postgresql://[^:]+:[^@]+@"` over the committed override returns 0 matches.
- **acceptance_criteria:** Override file contains no literal database password, no literal Grafana admin password, and no literal Slack webhook.
- **blocked_by:** None.
- **notes:** New finding (Session 80). **Fix shipped:** `docker-compose.override.local.yml` now requires `${DATAFORGE_DB_PASSWORD:?}`, `${GRAFANA_PASSWORD:?}`, and `${ALERTMANAGER_SLACK_WEBHOOK_URL:?}` instead of committing literal DB/Grafana/Slack credentials. `.env.example` documents those local override inputs. Guarded by `backend/tests/test_docker_local_override_secrets.py`.

### F-ENV-004

- **priority:** P0
- **status:** fixed
- **category:** security / env / secrets_outside_docker_secrets
- **file_path:** `docker-compose.prod.yml`, `.env.production.example`, `scripts/load_runtime_secrets.sh`, `scripts/start_server.sh`, `scripts/start_worker.sh`, `scripts/check_prod_env.py`, `scripts/generate_prod_env.py`
- **line_function:** API/session Docker secret wiring and runtime loader
- **evidence:** `DATAFORGE_API_KEY`, `DATAFORGE_OPERATOR_API_KEY`, `DATAFORGE_ADMIN_API_KEY`, `DATAFORGE_SESSION_SECRET` sit in `.env` (intended to be ignored — it is via `.env.*`). Unlike `DATAFORGE_DB_PASSWORD`, `GRAFANA_PASSWORD`, and `ALERTMANAGER_SLACK_WEBHOOK_URL` (all mounted as Docker secrets in `docker-compose.prod.yml:435-441`), the API keys are NOT in a `secrets:` block.
- **why_it_matters:** Operators shipping Docker on shared hosts leave `.env` in backups, log archives, and operator mail threads. The Docker secrets path is the only end-to-end safe transport; passing through the host filesystem is not.
- **impact:** API keys leak via host backups / shared mount / unintended rotat.
- **recommended_fix:** Adopt the same Docker-secrets pattern used for `alertmanager.slack_webhook` for API keys as well.
- **tests_needed:** `docker-compose -f docker-compose.prod.yml config | grep DATAFORGE_DB_PASSWORD` shows a `bind`-style secrets mount; equivalent greps exist for API keys.
- **acceptance_criteria:** Production API keys are sourced via Docker secrets, not file mounts.
- **blocked_by:** None.
- **notes:** New finding (Session 80). **Fix shipped:** production compose now mounts `dataforge_api_key`, `dataforge_operator_api_key`, `dataforge_admin_api_key`, and `dataforge_session_secret` into both app and worker containers, and passes only `DATAFORGE_*_FILE` env vars. The shared `scripts/load_runtime_secrets.sh` loader exports canonical env names before validation/startup. `check_prod_env.py` resolves file-backed secrets and requires `DATAFORGE_SESSION_SECRET`; `generate_prod_env.py` writes `.secrets/` files plus `_FILE` refs. Guarded by `backend/tests/test_docker_prod_secret_wiring.py` and `backend/tests/test_check_prod_env.py`.

### F-CONFIG-001

- **priority:** P1
- **status:** fixed
- **category:** config / env_drift / pg_driver
- **file_path:** `backend/app/storage_interface.py`, `backend/app/worker_queue_postgres.py`, `backend/app/worker_queue_postgres_base.py`, `backend/app/routers/system.py`
- **line_function:** `DATAFORGE_PG_DRIVER` reads at lines 244, 1061, 969, 109
- **evidence:** Three storage/worker paths read the env var with empty-string default (`worker_queue_postgres.py:244`, `worker_queue_postgres_base.py:1061`, `storage_interface.py:969`). The diagnostics endpoint `routers/system.py:109` uses `"psycopg2"` as default. The two paths diverge: when `DATAFORGE_PG_DRIVER` is unset, `storage_interface.py:973-975` warns that production requires `psycopg3`, while `routers/system.py:109` reports `psycopg2`.
- **why_it_matters:** Operator sees the wrong driver in the diagnostics panel while the actual code path resolves to empty/psycopg3. Driver drift between the API surface and the worker/storage code.
- **impact:** Confusing support diagnostics; operator may switch drivers based on the wrong info.
- **recommended_fix:** Centralize `DATAFORGE_PG_DRIVER` resolution into one helper in `app.config`, fail closed in production if unset, single default across all readers.
- **tests_needed:** Unit test on the helper; assert `routers/system.py::system_manifest` returns the same driver as the central resolver/storage initializer.
- **acceptance_criteria:** Removing `DATAFORGE_PG_DRIVER` outside production exposes the same driver from `/api/system/manifest` as the storage layer uses; production fails closed if the variable is missing.
- **blocked_by:** None.
- **notes:** New finding (Session 80). **Fix shipped:** `app.config.resolve_pg_driver()` now owns runtime PG driver normalization, invalid-value rejection, and production missing-driver fail-closed behavior. `storage_interface.py`, both Postgres worker queue factories, and `routers/system.py::system_manifest` now call the same helper, so diagnostics and storage/worker runtime paths report/select the same driver. Guarded by helper/manifest tests in `backend/tests/test_production_driver_selection.py` and worker dispatch tests in `backend/tests/test_worker_queue_factory_dispatch.py`.

### F-DOCKER-002

- **priority:** P1
- **status:** fixed
- **category:** infrastructure / docker / mount_permission_drift
- **file_path:** `docker-compose.yml:22-61`
- **line_function:** dev service mounts at lines 36-38
- **evidence:** Dev service mounts `./backend:/app/backend` and `./frontend:/app/frontend` from host while the container runs as user `dataforge` (UID != host user). `--reload` writes `.pyc` and `.pytest_cache` with mismatched UID → "Permission denied" noise on Linux when host UID ≠ 1000.
- **why_it_matters:** Contributors hit confusing errors on every reload; workaround is undocumented `chown -R 1000:1000 .` on host.
- **impact:** Friction for all contributors on non-UID-1000 hosts.
- **recommended_fix:** Pass `user: "${UID:-1000}:${GID:-1000}"` to the dev service; or run as root in dev with a clear env flag.
- **tests_needed:** Static guard plus Compose config render with non-1000 UID/GID; docs show `make up` path and direct Compose override.
- **acceptance_criteria:** `make up` exports the host UID/GID, dev Compose runs the service as that UID/GID, and `/app/backend/data` stays under the host bind mount instead of an image-owned named volume.
- **blocked_by:** None.
- **notes:** New finding (Session 80). **Fix shipped:** `Makefile` now derives `DATAFORGE_DEV_UID`/`DATAFORGE_DEV_GID` from `id -u`/`id -g` and prefixes development Compose commands with them. `docker-compose.yml` consumes those values via `user: "${DATAFORGE_DEV_UID:-1000}:${DATAFORGE_DEV_GID:-1000}"` and no longer overlays `/app/backend/data` with the image-owned `dataforge_data` volume in dev. `docs/QUICKSTART.md` now documents `make up` and the direct Compose UID/GID override. Guarded by `backend/tests/test_docker_dev_target.py`.

### F-DOCKER-005

- **priority:** P1
- **status:** fixed
- **category:** infrastructure / docker / rolling_redeploy_drift
- **file_path:** `docker-compose.prod.yml`, `Makefile`, `scripts/check_prod_env.py`
- **line_function:** image references at compose lines 28 + 100; Makefile `prod:` target lines 209-212; `check_prod_env.py::check_image_tag` (added at line 290) and required-checks entry (added near line 700)
- **evidence:** Both `dataforge` and `worker` services used `image: dataforge:${DATAFORGE_IMAGE_TAG:-latest}`. Default unpinned tag means rolling `docker compose -f … up -d` without rebuild pulls whatever the registry holds as `latest`. There was no `--pull=never` flag, so Compose fetched from registry on every restart.
- **why_it_matters:** Defeats the explicit "image digest is pinned" comment at `Dockerfile:14-16`. Production deploy becomes non-reproducible.
- **impact:** A malicious or stale upstream release can silently deploy on next restart.
- **recommended_fix:** Generate image tags from CI (`dataforge:${GITHUB_SHA}` or `dataforge:${RELEASE_VERSION}`) and bake the SHA into `.env.production`. Add `--pull=never` to compose commands in prod runbooks.
- **tests_needed:** Static guard for production image references; `docker compose -f docker-compose.prod.yml config -q` fails when `DATAFORGE_IMAGE_TAG` is missing and renders `dataforge:<tag>` when set.
- **acceptance_criteria:** Production deploy requires `DATAFORGE_IMAGE_TAG`, rejects empty/placeholder/`latest`, and `make prod` uses `--pull=never` with an explicit immutable tag.
- **blocked_by:** None.
- **notes:** New finding (Session 80). **Fix shipped:** `docker-compose.prod.yml` now requires `${DATAFORGE_IMAGE_TAG:?...}` for both `dataforge` and `worker`, so a missing tag fails at compose-config time. `Makefile` requires the tag for `build-prod` and `prod`, builds `dataforge:$DATAFORGE_IMAGE_TAG`, and runs production `up` with `--pull=never`. `check_prod_env.py::check_image_tag` rejects empty, placeholder, and `latest` values; the required-checks list enforces `DATAFORGE_IMAGE_TAG`. `.env.production.example`, `docs/RELEASE_CHECKLIST.md`, and `docs/PRODUCTION_STARTUP.md` document the immutable-tag path. Guarded by `backend/tests/test_docker_image_tag_pinning.py` and `backend/tests/test_check_prod_env.py`.

### F-DRIFT-001

- **priority:** P1
- **status:** verified
- **category:** infrastructure / docker / readonly_bypass
- **file_path:** `docker-compose.prod.yml:48-49, 73, 142`
- **line_function:** both services `read_only: true` plus `volumes:` block
- **evidence:** Both prod services have `read_only: true` (root fs locked) but `volumes: - dataforge_data:/app/backend/data` mounts on top **rw** by default — read-only protection is bypassed for that path. A compromised uvicorn can overwrite `semantic_state.json`, logs, etc.
- **why_it_matters:** Read-only filesystem is a defense in depth against process compromise; the data volume is wide open, weakening it.
- **impact:** Lateral damage after any process compromise within `/app/backend/data`.
- **recommended_fix:** Mount subpaths (`dataforge_data:/app/backend/data/logs:rw`, `dataforge_data:/app/backend/data/semantic:ro`); narrow the writable surface.
- **tests_needed:** Run a compromised process and assert it cannot write `semantic_state.json` while still writing logs.
- **acceptance_criteria:** Compromise from the API process cannot tamper with `semantic_state.json`.
- **blocked_by:** None.
- **notes:** New finding (Session 80).

### F-CI-003

- **priority:** P1
- **status:** verified
- **category:** infrastructure / ci / mutable_action_refs
- **file_path:** all `.github/workflows/*.yml` (10 files)
- **line_function:** every `uses:` for third-party actions
- **evidence:** `actions/checkout@v4`, `actions/setup-python@v5`, `actions/setup-node@v4`, `actions/cache@v4`, `actions/stale@v9`, `actions/upload-artifact@v4`, `actions/stale@v9`, `anchore/sbom-action@v0.24.0`, `dependabot/fetch-metadata@v2`, `docker/build-push-action@v5`, `docker/setup-buildx-action@v3` are all mutable tags. Only `appleboy/telegram-action@37056891d444f558225b59f0d26b4b05c5e9828b` is SHA-pinned (the desired model).
- **why_it_matters:** Supply-chain compromise vector. Tag ref allows attacker (or accidental push) to swap the action contents and the next CI build runs them.
- **impact:** Repo hijack via action ref push.
- **recommended_fix:** SHA-pin all `uses: third/party/action@<full-40-char-sha>` references. Use Dependabot to refresh the SHAs.
- **tests_needed:** Add a CI step that fails the workflow if any `uses:` is not SHA-pinned.
- **acceptance_criteria:** Zero mutable-tag third-party actions in any workflow.
- **blocked_by:** None.
- **notes:** New finding (Session 80).

### F-CI-004

- **priority:** P1
- **status:** verified
- **category:** infrastructure / ci / fork_pr_token_pivot
- **file_path:** `.github/workflows/auto-fix.yml:25-30`
- **line_function:** `on: issue_comment: [created]` + `pull_request: [labeled]`
- **evidence:** Any commenter with `/format` triggers a `ruff` / `prettier` push via `GITHUB_TOKEN`. No `if: github.event.pull_request.head.repo.full_name == github.repository` filter — fork PRs can call the workflow. The workflow has `contents: write` globally.
- **why_it_matters:** Combined with mutable-tag actions (F-CI-003), forked PR comments can trigger arbitrary shell-equivalent commands via formatter wrappers.
- **impact:** Arbitrary code-in-shell via misleading `prettier --write` calls against fake paths.
- **recommended_fix:** Filter to `head.repo.full_name == github.repository`; pin action SHAs (F-CI-003); switch fallback token to repo-scoped PAT with PR-only scope.
- **tests_needed:** Synthetic fork PR with `/format` comment — workflow does not push.
- **acceptance_criteria:** No fork can trigger a `contents: write` step in auto-fix.
- **blocked_by:** None.
- **notes:** New finding (Session 80).

### F-CI-005

- **priority:** P1
- **status:** verified
- **category:** infrastructure / ci / detect_secret_emptiness
- **file_path:** `.github/workflows/ci.yml:414-431`, `browser-e2e.yml:120-136`, `optional-suites.yml:114-132`, `postgres-tests.yml:75-87`, `nightly-integration.yml:51-69`, `golden-dataset.yml:51-72`, `validate-production.yml:463-479`
- **line_function:** `if: env.TELEGRAM_TOKEN != '' && env.TELEGRAM_TO != ''`
- **evidence:** GHA substitutes empty strings for unset secrets. The guard `!= ''` always succeeds if the secret slot exists, even if the value is empty. So a misconfigured chat ID/bot token combination silently runs the action step with empty values.
- **why_it_matters:** A misconfigured Telegram integration is silently accepted; the absence of a notification is invisible.
- **impact:** Lost alerts during incidents when Telegram is half-configured.
- **recommended_fix:** Test for non-empty values with explicit length check, `if: length(env.TELEGRAM_TOKEN) > 0 && …`.
- **tests_needed:** Synthetic workflow run with `TELEGRAM_TOKEN=` empty value — step skips.
- **acceptance_criteria:** Notification step is skipped when either secret is empty.
- **blocked_by:** None.
- **notes:** New finding (Session 80).

### F-CI-008

- **priority:** P1
- **status:** verified
- **category:** infrastructure / ci / image_smoke_runner_exposure
- **file_path:** `.github/workflows/ci.yml:322-355`
- **line_function:** `image-build` job `docker run` step
- **evidence:** `image-build` builds then runs the production image on the same runner. No `--network=none --read-only --cap-drop ALL --security-opt no-new-privileges`.
- **why_it_matters:** A poisoned production image (via Dependabot dep update) executes inline on the runner — full container surface exposed.
- **impact:** Runner takeover via malicious image.
- **recommended_fix:** Add `--network=none --read-only --cap-drop ALL --security-opt no-new-privileges --user 65534` to the smoke `docker run` invocation.
- **tests_needed:** `gh run view `<run-id>` --json jobs[]` shows the smoke container's caps.
- **acceptance_criteria:** Smoke container runs with the listed hardening flags.
- **blocked_by:** None.
- **notes:** New finding (Session 80).

### F-CI-010

- **priority:** P1
- **status:** verified
- **category:** infrastructure / ci / mutable_action_refs
- **file_path:** `.github/workflows/stale-cleanup.yml:30`
- **line_function:** `uses: actions/stale@v9`
- **evidence:** Mutable `@v9` tag (vs SHA or `@v9.0.0` SemVer pin).
- **why_it_matters:** Provider can publish a malicious or breaking 9.x release at any time.
- **impact:** Silent change in stale cleanup semantics.
- **recommended_fix:** SHA-pin (per F-CI-003 pattern).
- **tests_needed:** Same SHA-pin enforcer as F-CI-003.
- **acceptance_criteria:** `actions/stale` is SHA-pinned.
- **blocked_by:** None.
- **notes:** New finding (Session 80).

### F-NGINX-001

- **priority:** P1
- **status:** verified
- **category:** infrastructure / nginx / missing_admin_acl
- **file_path:** `nginx.local.conf:75-224`
- **line_function:** `location /api/` proxy at lines 108-124
- **evidence:** Production `nginx.conf` has `/api/admin` deny block; `nginx.local.conf` does not. CSP includes `connect-src 'self' ws: wss:` which is essentially no TLS pinning. `/api/` proxy passes everything to FastAPI without IP allow-list.
- **why_it_matters:** In local TLS-bypass mode (used by `docker-compose.override.local.yml:118-121`), the entire nginx HTTP server is the *only* firewall between host network and the FastAPI app. Any future refactor that exposes a sensitive endpoint under `/api/` flows unconditionally through the proxy.
- **impact:** Local-dev HTTP exposure of admin paths.
- **recommended_fix:** Add a `/api/admin` deny block to `nginx.local.conf` matching the production file. Or add an IP allow-list `127.0.0.1` only.
- **tests_needed:** Curl admin paths from a non-loopback NIC — returns 403.
- **acceptance_criteria:** Local nginx refuses `/api/admin/*` and `/api/system/admin/*` paths.
- **blocked_by:** None.
- **notes:** New finding (Session 80).

### F-NGINX-002

- **priority:** P1
- **status:** verified
- **category:** infrastructure / nginx / plaintext_health
- **file_path:** `nginx.conf:351-366`
- **line_function:** Server block B (HTTP→HTTPS redirect) for `/health` and `/ready`
- **evidence:** The block proxies `/health` and `/ready` plaintext back to `http://dataforge_api`. CWE-200: liveness state fingerprintable.
- **why_it_matters:** Cleartext monitoring endpoints are routinely probed by uptime services and hostile observers. A network observer fingerprints the deployment's health.
- **impact:** Reconnaissance advantage during incident response.
- **recommended_fix:** Add `return 301 https://$host$request_uri;` for `/health` and `/ready` too. Update the smoke test to use HTTPS.
- **tests_needed:** Curl `http://host/health` returns 301.
- **acceptance_criteria:** All /health, /ready redirects are TLS-only.
- **blocked_by:** None.
- **notes:** New finding (Session 80).

### F-NGINX-004

- **priority:** P1
- **status:** verified
- **category:** infrastructure / nginx / duplicated_security_headers
- **file_path:** `nginx.conf:138-306`
- **line_function:** 10+ `add_header` blocks per `location`
- **evidence:** Same 5-header block (X-Frame-Options, X-Content-Type-Options, Referrer-Policy, Permissions-Policy, Content-Security-Policy) repeated across 10+ locations.
- **why_it_matters:** Header drift bugs. A new `location ~ \.js$` block added without copying the security headers silently bypasses CSP.
- **impact:** Inconsistent header enforcement; future drift undetected.
- **recommended_fix:** Use `add_header` in a shared file via `include /etc/nginx/security_headers.conf;` plus top-level `map` in `http {}`.
- **tests_needed:** Smoke test: every endpoint (not under SSL) returns CSP.
- **acceptance_criteria:** Single source for security headers; per-location overrides only when intentional.
- **blocked_by:** None.
- **notes:** New finding (Session 80).

### F-MON-002

- **priority:** P1
- **status:** verified
- **category:** infrastructure / monitoring / cardinality_bomb
- **file_path:** `prometheus_alerts.yml:102-110`, `metrics_collector.py:63-65`
- **line_function:** `HighSSRFBlockRate` alert, `_ssrf_rejects` dict
- **evidence:** `_ssrf_rejects` is keyed by caller-supplied `reason` (essentially URL patterns). Alert expression sums across reason labels. An attacker driving many distinct URLs adds many `reason` series.
- **why_it_matters:** Unbounded label cardinality → Prometheus TSDB OOM.
- **impact:** DoS on observability; alert masking as well.
- **recommended_fix:** Bound reason label via an allow-list (`private_ip`, `loopback`, `dns_filter`, `scheme`, `port`, `unspecified`); collapse unknown reasons to `other`.
- **tests_needed:** Synthetic load test with 10k distinct URLs; series cardinality stays bounded.
- **acceptance_criteria:** `_ssrf_rejects` never exceeds 7 distinct `reason` values.
- **blocked_by:** None.
- **notes:** New finding (Session 80).

### F-MON-003

- **priority:** P1
- **status:** verified
- **category:** infrastructure / monitoring / single_instance_amber
- **file_path:** `prometheus.yml:36-38`, `docker-compose.prod.yml:403`
- **line_function:** `alertmanagers.targets` and alertmanager `--cluster.listen-address=`
- **evidence:** Single alertmanager instance with empty cluster gossip address. If the container dies, all alerts drop. No `AlertmanagerDown` alert because alertmanager isn't a Prometheus scrape target.
- **why_it_matters:** SPOF for alerting pipeline; notification routes do not failover.
- **impact:** Total alert loss during alertmanager outage.
- **recommended_fix:** Either run alertmanager with HA (2+ replicas + gossip) or document single-instance trade-off and add `DataForgeAlertmanagerDown` alert.
- **tests_needed:** Synthetic alertmanager kill → on-call pages within 60s.
- **acceptance_criteria:** Either failover works or explicit down-alert fires.
- **blocked_by:** None.
- **notes:** New finding (Session 80).

### F-MON-007

- **priority:** P1
- **status:** verified
- **category:** infrastructure / monitoring / alert_fatigue_duplicate
- **file_path:** `alertmanager.yml:78-87`
- **line_function:** `critical` route `continue: true`
- **evidence:** `continue: true` causes critical alerts to deliver both to `critical` (line 116-141) AND `default` (lines 109-114) receiver. 5 critical alerts produce 10 email + 5 Slack = 15 outbound.
- **why_it_matters:** Alert fatigue. Operators start ignoring `critical` because there are too many duplicate messages.
- **impact:** Real incidents lost in the noise.
- **recommended_fix:** Drop `continue: true`; ensure `critical` receiver owns all delivery paths. Use `mute_time_intervals` correctly.
- **tests_needed:** Synthetic critical alert delivers exactly 1 email + 1 Slack.
- **acceptance_criteria:** No duplicate notifications in alertmanager routes.
- **blocked_by:** None.
- **notes:** New finding (Session 80).

### F-DOC-001

- **priority:** P1
- **status:** verified
- **category:** docs / readme / validate_gate_mislabeled
- **file_path:** `README.md`, `Makefile`
- **line_function:** `README.md:52`, `Makefile:169-170`
- **evidence:** README states "Passes with `make validate`" but `make validate` actually runs `python3 scripts/validate_local.py --full` (the unbounded, slower gate). README also lists `python3 scripts/validate_local.py --quick` and `make validate` separately as if they're different.
- **why_it_matters:** Operators expect `make validate` to be the quick local-gate; they get the slow, full-local check. Documentation drift hides the actual default gate.
- **impact:** Confusing contributor interpretation; possible time wasted on full runs.
- **recommended_fix:** Either: (a) make `make validate` run `--quick`, or (b) update README to say "Passes with `make validate` (runs `--full`)". Pick one and document.
- **tests_needed:** Manual: `make -n validate` shows the actual `--full` execution.
- **acceptance_criteria:** README, Makefile, and AGENTS.md all agree on which mode `make validate` runs.
- **blocked_by:** None.
- **notes:** New finding (Session 80).

### F-MON-009

- **priority:** P1
- **status:** verified
- **category:** infrastructure / monitoring / alert_query_against_unrelated_metric
- **file_path:** `prometheus_alerts.yml:124`, `metrics_collector.py:267-281`
- **line_function:** `RepoQueryLatencyDegraded` alert (line 124) vs Python list[float] ring buffer (line 267-281)
- **evidence:** Alert expression `dataforge_repo_query_latency_seconds{quantile="0.95"} > 0.5` implies a PromQL summary metric. The metric in code is a Python list ring buffer with no `quantile` label. PromQL returns no series; alert never fires.
- **why_it_matters:** This alert will **never fire** in current setup. Operators expect it to catch Postgres latency regressions.
- **impact:** Silent regression-monitoring gap during incident response.
- **recommended_fix:** Either expose `dataforge_repo_query_latency_seconds_bucket` as a real Histogram (use `histogram_quantile(0.95, …)`) or switch the alert expression to a derived gauge.
- **tests_needed:** Force slow query; assert `DataForge...Instance...alert-test` evaluation returns firing.
- **acceptance_criteria:** Alert can fire on real latency regression.
- **blocked_by:** None.
- **notes:** New finding (Session 80).

### F-NAMING-001

- **priority:** P1
- **status:** fixed
- **category:** code_quality / naming_typo / public_export
- **file_path:** `backend/app/services/job_mutation_service.py`, `backend/app/routers/jobs_write.py`
- **line_function:** `JobRecleanerService` class
- **evidence:** Class name was `JobReclenerService` (typo for "Recleaner"). Imported in `routers/jobs_write.py:49, 209, 211, 213, 215` and exposes API surface for `/api/jobs/<id>/reclean`.
- **why_it_matters:** Typo propagates to user-visible API surface (OpenAPI schema, swagger docs) and the docstrings.
- **impact:** Permanent documentation defect; harder to grep for "recleaner" across the codebase.
- **recommended_fix:** Rename `JobReclenerService` → `JobRecleanerService`. Update imports and test references.
- **tests_needed:** Existing 26 characterization tests pass with the new name; no external caller breaks.
- **acceptance_criteria:** Class name is `JobRecleanerService` throughout.
- **blocked_by:** None.
- **notes:** New finding (Session 80). **Fix shipped:** class renamed to `JobRecleanerService` in `app/services/job_mutation_service.py:196`, all callers in `routers/jobs_write.py`, plus matching `TestJobRecleanerService` test class in `tests/test_job_mutation_service.py` and the test reference update in `tests/test_ga_hardening.py`. No behavior change. 26 characterization tests pass.

### F-ENV-002

- **priority:** P1
- **status:** verified
- **category:** docs / env_example / drift
- **file_path:** `.env.example`, `.env.production.example`
- **line_function:** `.env.example:96-99, 134-138` vs `.env.production.example`
- **evidence:** `.env.example` lists `DATAFORGE_TELEGRAM_BOT_TOKEN`, `DATAFORGE_TELEGRAM_CHAT_ID`, `DATAFORGE_TELEGRAM_ENABLED`. `.env.production.example` lists NONE of these.
- **why_it_matters:** Operators porting dev templates to production miss notification config entirely; no comment notes the omission.
- **impact:** Production deploys have inconsistent notification behavior vs dev.
- **recommended_fix:** Add a `# Notifications (optional)` block to `.env.production.example` matching the dev env structure.
- **tests_needed:** `diff` after the change shows only env-var-key equality, not value drift.
- **acceptance_criteria:** Both files document all notification env vars.
- **blocked_by:** None.
- **notes:** New finding (Session 80).

### F-ENV-003

- **priority:** P1
- **status:** verified
- **category:** security / env / check_prod_env_missing
- **file_path:** `scripts/check_prod_env.py:24-33`, `docker-compose.prod.yml:321`
- **line_function:** `REQUIRED_VARS` list
- **evidence:** `GRAFANA_USER` and `GRAFANA_PASSWORD` not in `REQUIRED_VARS`. A misconfigured `GRAFANA_USER=ops` set in `.env.production` slips past the gate.
- **why_it_matters:** Single-user Grafana admin with no rotation slips through the gate.
- **impact:** Misconfigured Grafana admin user; permission misassignment post-deploy.
- **recommended_fix:** Add `GRAFANA_USER` + `GRAFANA_PASSWORD` to `REQUIRED_VARS` with placeholder/weak-secret check (the existing `--weak-password` style).
- **tests_needed:** Synthetic run with `GRAFANA_USER=ops` triggers gate failure.
- **acceptance_criteria:** `scripts/check_prod_env.py` fails deploy when user/password drift detected.
- **blocked_by:** None.
- **notes:** New finding (Session 80).

### F-ENV-005

- **priority:** P1
- **status:** verified
- **category:** config / env / llm_fallback_silent
- **file_path:** `.env.example:30-35`, `scripts/check_prod_env.py`
- **line_function:** GROQ API key configuration
- **evidence:** `DATAFORGE_GROQ_API_KEY=` in `.env.example` with no operator-visible warning that AI structuring fails when unset. `DATAFORGE_LLM_ENABLE_PUBLIC_FALLBACKS=false` mentions fail-closed but the operator signal is missing.
- **why_it_matters:** Operators don't know whether their deployment is fully functional until they hit an LLM-call path.
- **impact:** Silent degraded paths; customers see partial data without operator awareness.
- **recommended_fix:** Extend `scripts/check_prod_env.py` to assert `DATAFORGE_GROQ_API_KEY` (or LLM) is set when AI structuring is enabled.
- **tests_needed:** Empty `DATAFORGE_GROQ_API_KEY` with `LLM=true` triggers gate failure.
- **acceptance_criteria:** Deploy fails when LLM-required deploy lacks LLM credentials.
- **blocked_by:** None.
- **notes:** New finding (Session 80).

### F-DB-002

- **priority:** P1
- **status:** verified
- **category:** infrastructure / db_migrations / no_schema_version_tracking
- **file_path:** `backend/init-db/init.sql:13-21`
- **line_function:** init.sql header + comments
- **evidence:** Tables are created by `app.postgres_repository._ensure_schema()` at runtime, not by versioned DDL files. There is no `schema_version` table to track applied migrations.
- **why_it_matters:** Multiple app versions running against the same database could race on schema apply. Operators cannot rebuild the schema by replaying files (see F-DB-001).
- **impact:** Schema drift during rolling deploys.
- **recommended_fix:** Export `_ensure_schema()` DDL into versioned files. Add a `schema_version` table the app reads on boot to determine whether migrations should run.
- **tests_needed:** Boot against an empty DB applies migrations in order; boot against a migrated DB skips migrations.
- **acceptance_criteria:** Schema version is queryable from outside the app process.
- **blocked_by:** None.
- **notes:** New finding (Session 80).

### F-DOCKER-003

- **priority:** P2
- **status:** verified
- **category:** infrastructure / docker / browser_image_double_install
- **file_path:** `Dockerfile:30-36, 66, 102-103`
- **line_function:** base stage OS libs; dev stage `playwright install` line 66; prod stage line 103
- **evidence:** Base stage installs Playwright OS libraries; prod stage calls `playwright install chromium` only (no `install-deps`). Dev stage chromium at line 66 is layered but not used by either `dev` or `prod`. Cache compresses both — first build downloads chromium twice.
- **why_it_matters:** Unused Chromium in dev image adds ~150MB. Pinned SHA base + mutable Playwright Chromium version is a reproducible-build risk.
- **impact:** Slower CI; cache pollution.
- **recommended_fix:** Add `ARG PLAYWRIGHT_BROWSERS_VERSION=...` and pin in `pyproject.toml` to a tested combo. Verify in CI that the cached image's node binary actually launches.
- **tests_needed:** `docker build` image size delta before/after pinning.
- **acceptance_criteria:** `make up` image is reproducible; CI cache hit rate > 90%.
- **blocked_by:** None.
- **notes:** New finding (Session 80).

### F-DOCKER-004

- **priority:** P2
- **status:** verified
- **category:** infrastructure / docker / dockerignore_gaps
- **file_path:** `.dockerignore`
- **line_function:** excludes for `.env.*`, `*.sqlite`, `data/`
- **evidence:** `.dockerignore` covers most secrets but misses `backend/data/`, `.secrets/`, `backend/init-db/`, `*.dump`, `*.sql.gz`, `*.bak`. If an operator drops `.secrets/sql.dump`, build context copies plaintext dump into image layers.
- **why_it_matters:** Operator-driven footgun; first build pulls a few MB of irrelevant junk.
- **impact:** Higher attack surface on the build context.
- **recommended_fix:** Add the missing paths to `.dockerignore`.
- **tests_needed:** Synthetic `touch .secrets/dump.sql`; verify it doesn't appear in `docker build . -t test`. `docker run test ls /app/.secrets` returns empty.
- **acceptance_criteria:** No `.secrets/` files in any build context.
- **blocked_by:** None.
- **notes:** New finding (Session 80).

### F-DOCKER-006

- **priority:** P2
- **status:** verified
- **category:** infrastructure / docker / path_traversal_alias
- **file_path:** `docker-compose.prod.yml:250-251`, `nginx.conf:319-321`
- **line_function:** `/landing/` alias without `try_files` guarding
- **evidence:** `/landing/` alias resolves to `/usr/share/nginx/html/frontend/landing/`. The mount is read-only but if `.git/` exists under `frontend/` (operator-deployed dev version), `/landing/.git/config` is served.
- **why_it_matters:** Operational fidelity risk; leaks git config.
- **impact:** Information disclosure if dev `.git/` not cleaned before prod mount.
- **recommended_fix:** Add `location ~ /\.(git|env|docker|aws) { deny all; return 404; }`.
- **tests_needed:** Curl `/landing/.git/config` returns 404.
- **acceptance_criteria:** Operator-deployed dev artifacts are not served.
- **blocked_by:** None.
- **notes:** New finding (Session 80).

### F-DOCKER-008

- **priority:** P2
- **status:** verified
- **category:** infrastructure / docker / drift_in_env_template_grep
- **file_path:** `docker-compose.override.local.yml:80-92`, `docker-compose.prod.yml:395-398`
- **line_function:** substitution grep
- **evidence:** Local override's grep is `__ALERTMANAGER_` (prefix) vs production full-list. New `__ALERTMANAGER_NEW_VAR__` slips through local override silently.
- **why_it_matters:** Local-override renders with unsubstituted placeholder; alertmanager rejects first reload later.
- **impact:** Confusing failure mode divergence between local and prod.
- **recommended_fix:** Mirror the production grep exactly; promote to shared `command:` via `x-anchor` YAML.
- **tests_needed:** Synthetic local override with `__ALERTMANAGER_NEW_VAR__` should fail the build.
- **acceptance_criteria:** Local and prod grep are byte-identical.
- **blocked_by:** None.
- **notes:** New finding (Session 80).

### F-FRONTEND-001

- **priority:** P2
- **status:** verified
- **category:** frontend / monolithic_css / no_build
- **file_path:** `frontend/index.html`, `frontend/landing.html`, `frontend/styles/views.css`, `frontend/styles/components.css`
- **line_function:** static SPA structure
- **evidence:** Vanilla JS, no build pipeline. Two HTML surfaces. Monolithic CSS: `views.css` 3,436 LOC, `components.css` 1,091 LOC.
- **why_it_matters:** Edit-and-publish model. Any CSP/header change requires editing 10+ locations. CSS is monolithic and not tree-shaken.
- **impact:** Friction for future contributors; larger than-needed first-paint payloads.
- **recommended_fix:** Introduce a minimal bundler (esbuild) with code splitting; tree-shake CSS.
- **tests_needed:** `npm run build` (new) succeeds; bundle size drops.
- **acceptance_criteria:** First-paint CSS < 200KB; components are lazy-loadable.
- **blocked_by:** None.
- **notes:** New finding (Session 80).

### F-NGINX-005

- **priority:** P2
- **status:** verified
- **category:** infrastructure / nginx / catch_all_host_header
- **file_path:** `nginx.conf:117`
- **line_function:** `server_name _;` + `absolute_redirect off` at line 118
- **evidence:** `server_name _;` means any host header reaching HTTPS server is honored. Attacker-set hosts work.
- **why_it_matters:** Host header injection if app uses `Host:` for cookie scoping or canonical URL generation. Phishing/cache-poisoning risk.
- **impact:** Potential phishing surface if any future route uses `$host`.
- **recommended_fix:** Set `server_name your.domain.example.com;` and reject unknown hosts.
- **tests_needed:** Synthetic curl with `Host: evil.com` returns 444.
- **acceptance_criteria:** Unknown host returns 444.
- **blocked_by:** None.
- **notes:** New finding (Session 80).

### F-NGINX-006

- **priority:** P2
- **status:** verified
- **category:** infrastructure / nginx / keepalive_default
- **file_path:** `nginx.conf:25-29`
- **line_function:** global `worker_connections 1024`
- **evidence:** `worker_connections 1024` + `multi_accept on` globally. nginx defaults `keepalive_requests=1000` post-v1.19.7.
- **why_it_matters:** Load tests may show non-linear latency scaling under concurrent keep-alive reuse.
- **impact:** Hidden capacity cliff during load tests.
- **recommended_fix:** Pin `keepalive_requests 10000;` on HTTPS server block.
- **tests_needed:** Synthetic `ab -c 200 -n 10000 …` shows consistent p95.
- **acceptance_criteria:** No keep-alive cliff triggering under load.
- **blocked_by:** None.
- **notes:** New finding (Session 80).

### F-CI-006

- **priority:** P2
- **status:** verified
- **category:** infrastructure / ci / postgres_port_collision
- **file_path:** `.github/workflows/optional-suites.yml:24-26`, `validate-production.yml:222-224`, `postgres-tests.yml:22-24`
- **line_function:** `services.postgres` config
- **evidence:** Hardcoded `postgresql://testuser:testpassword@…:5432/`. Port collisions on shared self-hosted runners.
- **why_it_matters:** Reliability — not security — but ports collide on multi-job runners.
- **impact:** Random CI run failures on shared infra.
- **recommended_fix:** Use `POSTGRES_HOST_AUTH_METHOD: trust` and skip the mapped port, or set custom port with `options: "--port=5433"`.
- **tests_needed:** Two parallel jobs running the workflow on the same runner both pass.
- **acceptance_criteria:** No port collision during parallel run.
- **blocked_by:** None.
- **notes:** New finding (Session 80).

### F-CI-007

- **priority:** P2
- **status:** verified
- **category:** infrastructure / ci / cancel_in_progress
- **file_path:** all cron workflows (5 files)
- **line_function:** `concurrency:` blocks
- **evidence:** `concurrency:` with `cancel-in-progress: true` — manual `workflow_dispatch` cancels the cron run mid-flight.
- **why_it_matters:** Operational visibility loss during incident response.
- **impact:** Confusing nightly status during incidents.
- **recommended_fix:** Use `cancel-in-progress: false` to allow queuing.
- **tests_needed:** Manual dispatch during the cron run does not cancel it.
- **acceptance_criteria:** Concurrent runs queue, never cancel.
- **blocked_by:** None.
- **notes:** New finding (Session 80).

### F-CI-009

- **priority:** P2
- **status:** verified
- **category:** infrastructure / ci / stale_pr_autoclose
- **file_path:** `.github/workflows/stale-cleanup.yml:30, 56-60`
- **line_function:** `operations-per-run: 100` + label exempt
- **evidence:** `operations-per-run: 100` and `exempt-pr-labels: keep-open,dependencies,security`. Mislabeled hot-fix release PR could be auto-closed.
- **why_it_matters:** Wrong label policy → auto-close on a hot-fix release PR.
- **impact:** Loss of work-in-progress PRs during bot misclassification.
- **recommended_fix:** Add `dry-run` input via `workflow_dispatch`; real cleanup only on explicit confirmation.
- **tests_needed:** Synthetic PR without labels run against `dry-run` shows intended close list without closing.
- **acceptance_criteria:** Stale cleanup never closes without explicit `workflow_dispatch` confirmation.
- **blocked_by:** None.
- **notes:** New finding (Session 80).

### F-NPM-001

- **priority:** P2
- **status:** verified
- **category:** frontend / package_json / caret_drift
- **file_path:** `package.json:8-16`
- **line_function:** every dep
- **evidence:** Every dep (`eslint`, `prettier`, `stylelint`, etc.) uses `^`. While `package-lock.json` pins exact versions, `npm install` outside the lockfile (e.g. through a Dockerfile-style npm flow or after `npm update <pkg>`) drifts.
- **why_it_matters:** Inconsistent CI vs local.
- **impact:** Random major jumps (e.g. eslint 9 → 10) on stray `npm update`.
- **recommended_fix:** Default to exact versions or `~`. Use `npm ci` everywhere (already the case in CI workflows).
- **tests_needed:** `npm install` outside CI produces identical lockfile diff as `npm ci`.
- **acceptance_criteria:** Lockfile-only installs work reliably.
- **blocked_by:** None.
- **notes:** New finding (Session 80).

### F-NPM-002

- **priority:** P2
- **status:** verified
- **category:** frontend / package_lock / integrity
- **file_path:** `package-lock.json`
- **line_function:** file-level integrity
- **evidence:** File exists; CI uses `npm ci`. No `npm audit signatures` integrity check.
- **why_it_matters:** Lockfile can be silently compromised by malicious dep bump without CI noticing.
- **impact:** Supply-chain compromise via dep.
- **recommended_fix:** Add `npm audit signatures` step to `ci.yml` or `validate-production.yml`.
- **tests_needed:** Synthetic tampering of lockfile is caught.
- **acceptance_criteria:** Lockfile integrity is checked before tests run.
- **blocked_by:** None.
- **notes:** New finding (Session 80).

### F-NPM-003

- **priority:** P2
- **status:** verified
- **category:** frontend / package_json / no_prod_deps
- **file_path:** `package.json:7-17`
- **line_function:** `dependencies`/`devDependencies`
- **evidence:** 0 production deps; everything in devDeps. Correct for static SPA — a contributor might `npm install somelib` thinking it's used at runtime.
- **why_it_matters:** Structural risk for future contributors.
- **impact:** Drift into prod dep tree.
- **recommended_fix:** Add CI step `npm ls --prod` (or `npm install --omit=dev --dry-run`) to fail if production deps sneak in.
- **tests_needed:** Synthetic prod-deps list fails the CI step.
- **acceptance_criteria:** CI refuses prod deps in `package.json`.
- **blocked_by:** None.
- **notes:** New finding (Session 80).

### F-MON-004

- **priority:** P2
- **status:** verified
- **category:** infrastructure / monitoring / missing_alerts
- **file_path:** `prometheus_alerts.yml`
- **line_function:** file-level coverage
- **evidence:** 14 alert rules cover app signals. None for PG disk, container OOM, TLS cert expiry, `AlertmanagerDown`, `node-exporter`, `blackbox-exporter HTTPS`.
- **why_it_matters:** Operator blind spots in incident response.
- **impact:** Real outages missed because no alert fires.
- **recommended_fix:** Add scrape jobs for `node_exporter`, `cadvisor`, `blackbox_exporter`; add corresponding rules.
- **tests_needed:** Each new alert fires under synthetic condition.
- **acceptance_criteria:** Comprehensive alerting on infra signals.
- **blocked_by:** None.
- **notes:** New finding (Session 80).

### F-MON-005

- **priority:** P2
- **status:** verified
- **category:** infrastructure / monitoring / self_scrape_pollution
- **file_path:** `prometheus.yml:27-34, 53-54`
- **line_function:** `alert_relabel_configs` vs self-scrape
- **evidence:** Self-monitoring scrape of `prometheus:9090` produces duplicate series tagged `instance="prometheus:9090"`. `alert_relabel_configs` only acts on alerts, not series.
- **why_it_matters:** Latent bug: any future alert referencing `up{job="prometheus"}` is ambiguous.
- **impact:** Future alert tests are flaky.
- **recommended_fix:** Add an `instance` labelrewrite or document exclusion list.
- **tests_needed:** Synthetic scrape with `instance_label_inconsistency` test passes.
- **acceptance_criteria:** Self-metrics labels are uniquely tagged.
- **blocked_by:** None.
- **notes:** New finding (Session 80).

### F-MON-006

- **priority:** P2
- **status:** verified
- **category:** infrastructure / monitoring / lifecycle_auth_missing
- **file_path:** `prometheus_web.yml:18`, `docker-compose.prod.yml:303`
- **line_function:** `--web.enable-lifecycle` + empty `basic_auth_users`
- **evidence:** Lifecycle enabled but no basic-auth users → reload POST returns 401. Reload requires container restart.
- **why_it_matters:** Config reload requires container recreation; restart = TS DB drop.
- **impact:** Operator friction; unnecessary restarts.
- **recommended_fix:** Either disable lifecycle or add at least one `basic_auth_users` (e.g. `reload:`) and document the password.
- **tests_needed:** Synthetic `curl -X POST /-/reload` succeeds.
- **acceptance_criteria:** Reload works without container restart.
- **blocked_by:** None.
- **notes:** New finding (Session 80).

### F-MON-008

- **priority:** P2
- **status:** verified
- **category:** infrastructure / monitoring / slack_channel_silent_miss
- **file_path:** `alertmanager.yml:132, 145, 156`
- **line_function:** `channel: '#alerts-critical'` etc.
- **evidence:** Channel ID never validated against Slack workspace. Mistyped/private channels return message to no one.
- **why_it_matters:** Operators see alerts as firing in Alertmanager but they never reach Slack.
- **impact:** Invisible alert pipeline failure.
- **recommended_fix:** Augment `scripts/run_alert_delivery_drill.py` with `--channel-assert-reachable` calling Slack `conversations.info`. Add to deploy gate.
- **tests_needed:** Synthetic channel-typo deploy fails the gate.
- **acceptance_criteria:** Slack channel reachability is asserted on every prod deploy.
- **blocked_by:** None.
- **notes:** New finding (Session 80).

### F-MON-010

- **priority:** P2
- **status:** verified
- **category:** infrastructure / monitoring / api_down_rootcause_ambiguity
- **file_path:** `prometheus.yml:60-61`
- **line_function:** `DataForgeAPIInstanceDown` alert
- **evidence:** Alert uses `up{job="dataforge"} == 0`. If the Bearer token env (`__DATAFORGE_METRICS_TOKEN__`) leaves the placeholder unsubstituted, the scrape returns 401 → `up{job="dataforge"} = 0` → alert fires with **wrong** root cause label.
- **why_it_matters:** Noisy pages from misconfig.
- **impact:** Operator pages on-call for a config bug.
- **recommended_fix:** Add a separate alert `MetricsTokenInvalid` firing when metrics endpoint returns 401/403, or use `probe_success` from `blackbox_exporter` against `/ready`.
- **tests_needed:** Synthetic 401 state fires `MetricsTokenInvalid`, not `DataForgeAPIInstanceDown`.
- **acceptance_criteria:** Pages are labelled with the correct root cause.
- **blocked_by:** None.
- **notes:** New finding (Session 80).

### F-DB-003

- **priority:** P2
- **status:** verified
- **category:** infrastructure / db_migrations / tenant_index_verification
- **file_path:** `backend/migrations/008_postgres_storage_v8.sql`
- **line_function:** tenant indexes
- **evidence:** Need verification: tenant column indexes (`org_id`, `created_by`) not directly visible in the read portion of the dump (lines 50+).
- **why_it_matters:** If indexes are missing, tenant queries scan, not index.
- **impact:** Tenant scoping degrades as data grows.
- **recommended_fix:** Run `grep -E "CREATE INDEX" backend/migrations/008_postgres_storage_v8.sql | grep -E "tenant|org_id|user_id|project_id"` to confirm tenant indexes; if missing, add them.
- **tests_needed:** EXPLAIN ANALYZE on tenant query uses index.
- **acceptance_criteria:** Tenant queries are indexed in both SQLite and Postgres.
- **blocked_by:** Verification step.
- **notes:** New finding (Session 80).

### F-DB-004

- **priority:** P2
- **status:** verified
- **category:** security / db_migrations / schema_dump_leak
- **file_path:** `backend/migrations/008_postgres_storage_v8.sql`
- **line_function:** file contents
- **evidence:** Snapshot file is unencrypted plaintext — contains the complete schema (potentially including column names with sensitive shapes like `email`, `ip_address`).
- **why_it_matters:** Public repo = data-model mapping attack. Attacker learns column names.
- **impact:** Reconnaissance advantage.
- **recommended_fix:** Strip dump to DDL-only via `pg_dump --schema-only --no-owner --no-privileges`; mask any sensitive column names.
- **tests_needed:** Synthetic diff shows no semantic data in committed dump.
- **acceptance_criteria:** Committed migration file contains schema only, no data.
- **blocked_by:** None.
- **notes:** New finding (Session 80).

### F-BACKUP-001

- **priority:** P2
- **status:** verified
- **category:** infrastructure / backup / gzip_only
- **file_path:** `scripts/backup_postgres.sh:142-148`
- **line_function:** `chmod 600 ...; gunzip -t`
- **evidence:** Validates gzip integrity only — does not validate that the file contains a recognizable `pg_dump` shape. Empty-garbage payload would pass gunzip -t.
- **why_it_matters:** A backup that "passes" gunzip can still be missing tables/data.
- **impact:** Silent restore failures.
- **recommended_fix:** Pipe through `head -c 4096 | grep -q "PostgreSQL database dump"`; add row-count compare (`SELECT count(*) FROM jobs`) vs source DB.
- **tests_needed:** Synthetic empty-dump backup fails the integrity gate.
- **acceptance_criteria:** Backup file passes identity + gzip integrity + row count.
- **blocked_by:** None.
- **notes:** New finding (Session 80).

### F-BACKUP-002

- **priority:** P2
- **status:** verified
- **category:** infrastructure / backup / no_rotation
- **file_path:** `scripts/backup_postgres.sh:17-19`
- **line_function:** `BACKUP_DIR` assignment
- **evidence:** No `find ... -mtime +30 -delete` cleanup. Backups accumulate indefinitely.
- **why_it_matters:** Disk fills; yesterday's 6-hourly backup eventually OOMs the disk.
- **impact:** Storage exhaustion on long-running prod.
- **recommended_fix:** Add `DATAFORGE_BACKUP_KEEP_DAYS=30` knob; cleanup at end of script.
- **tests_needed:** Synthetic 31-day-old backup is deleted.
- **acceptance_criteria:** Backups older than retention are removed.
- **blocked_by:** None.
- **notes:** New finding (Session 80).

### F-BACKUP-003

- **priority:** P2
- **status:** verified
- **category:** infrastructure / backup / restore_no_verify
- **file_path:** `scripts/restore_postgres.sh:138-148`
- **line_function:** `psql` pipe + `echo SUCCESS`
- **evidence:** Success printed purely on psql exit code. A partial restore could half-succeed.
- **why_it_matters:** Operator sees SUCCESS but data is incomplete.
- **impact:** False-positive restore; recovery is silently broken.
- **recommended_fix:** Post-restore `psql -c "SELECT count(*) FROM jobs"` compare to a snapshot count captured at backup time.
- **tests_needed:** Synthetic partial restore fails the verification step.
- **acceptance_criteria:** Restore verification rejects non-equivalent row counts.
- **blocked_by:** None.
- **notes:** New finding (Session 80).

### F-NGINX-SEC-001

- **priority:** P2
- **status:** verified
- **category:** infrastructure / nginx / methodless_rate_limit
- **file_path:** `nginx.local.conf:108-124`
- **line_function:** `location /api/`
- **evidence:** `/api/` proxy forwards all methods and paths to FastAPI without method-specific rate limiting.
- **why_it_matters:** No pre-auth throttle; admin paths exposed at unlimited rate.
- **impact:** Brute force / flood risk.
- **recommended_fix:** Add `limit_req` for write methods (`POST/PUT/DELETE`) at stricter burst than reads.
- **tests_needed:** Synthetic burst of 1k POSTs to `/api/jobs` returns 503/429.
- **acceptance_criteria:** Write methods are throttled at strict rate.
- **blocked_by:** None.
- **notes:** New finding (Session 80).

### F-EXCEPTION-001

- **priority:** P2
- **status:** verified
- **category:** code_quality / error_handling / generic_500
- **file_path:** `backend/app/routers/experimental.py`, `backend/app/routers/scraper.py`, `backend/app/services/job_mutation_service.py:399`
- **line_function:** 20+ `raise HTTPException(status_code=500, ...)` sites
- **evidence:** 20+ inline `raise HTTPException(status_code=500, detail="...")` with generic detail strings ("failed", "internal error"); hides root cause.
- **why_it_matters:** Operator error responses lack correlation IDs and root cause.
- **impact:** Slow incident triage.
- **recommended_fix:** Add a custom exception handler that includes trace_id and a meaningful structured detail.
- **tests_needed:** Synthetic 500 response includes `trace_id`.
- **acceptance_criteria:** All 500 responses surface a correlation ID.
- **blocked_by:** None.
- **notes:** New finding (Session 80).

### F-RBAC-001

- **priority:** P2
- **status:** verified
- **category:** security / rbac / static_grep_blindspot
- **file_path:** all routers
- **line_function:** import of `require_principal`/`require_role`/etc.
- **evidence:** 6 routers import no auth dependency: `intelligence.py`, `jobs.py`, `jobs_state.py`, `session.py`, `health.py`, `__init__.py`. Verified legitimate (`jobs.py` is a façade mounting child routers; `health.py` is intentionally unauthed; `session.py` is **the** auth route). But the static-grep "every router imports a require_*" check can't differentiate façade from real non-auth access.
- **why_it_matters:** A future router added with imports of `APIRouter()` only would silently slip past the static check while exposing protected data.
- **impact:** Future drift.
- **recommended_fix:** Add a generator test that, given the `Route Auth Matrix`, asserts every non-public endpoint row has at least one `require_*` deps in code.
- **tests_needed:** A synthetic uncovered route triggers the static test to fail.
- **acceptance_criteria:** Route auth matrix + static-grep work in tandem.
- **blocked_by:** None.
- **notes:** New finding (Session 80).

### F-SCRIPT-001

- **priority:** P2
- **status:** verified
- **category:** scripts / hardcoded_localhost
- **file_path:** `scripts/run_alert_delivery_drill.py`, `scripts/run_load_test.py`, `scripts/backup_and_restore_test.py`, `scripts/manual_test.py:33`
- **line_function:** default URL constants
- **evidence:** Drill scripts reach back to localhost by default; designed for "the server is also on this host". A CI runner on a different host or remote dev container fails silently.
- **why_it_matters:** Drill scripts that target `localhost` produce false-positive alerts in CI logs.
- **impact:** Misleading CI signal.
- **recommended_fix:** Default to localhost but ASSERT the host via env var before proceeding.
- **tests_needed:** Synthetic remote-host drill fails loudly.
- **acceptance_criteria:** Drill refuses to run without explicit `--url-prefix` on non-localhost targets.
- **blocked_by:** None.
- **notes:** New finding (Session 80).

### F-SCRIPT-002

- **priority:** P2
- **status:** verified
- **category:** scripts / env_parser / partial_comment
- **file_path:** `scripts/check_prod_env.py:82-110`
- **line_function:** `load_env_file`
- **evidence:** Custom parser strips trailing `#` comments from `value` (`value.partition("#")[0].strip()`). For multi-line or values with embedded `#`, this mangles them.
- **why_it_matters:** `KEY=value#with#hashes` parsed as `value`, bypassing weak-credential gate.
- **impact:** Operator can ship `GRAFANA_PASSWORD=Nz4HdRU#not-a-real-password` and pass the check while shipping an unexpected value.
- **recommended_fix:** Switch to `dotenv` parser; support line-continuation per POSIX dotenv.
- **tests_needed:** Synthetic hash-bearing values pass through unchanged.
- **acceptance_criteria:** Env file parsing matches `dotenv`'s behavior.
- **blocked_by:** None.
- **notes:** New finding (Session 80).

### F-SCRIPT-003

- **priority:** P2
- **status:** verified
- **category:** scripts / start_sh / silent_copy
- **file_path:** `scripts/start.sh:36-44`
- **line_function:** env creation block
- **evidence:** If `.env` missing, `cp .env.example .env` silently runs, producing a placeholder-keyed .env that the server happily boots with disabled auth/DB.
- **why_it_matters:** Operator sees "server started" with placeholder keys and learns the failure later.
- **impact:** Footgun time-loss; possible credentials leak in transit logs.
- **recommended_fix:** Refuse to start if `.env` missing; print clear instructions. Never `cp .env.example` into a working `.env`.
- **tests_needed:** Synthetic missing-`.env` start fails.
- **acceptance_criteria:** `start.sh` exits non-zero when `.env` missing.
- **blocked_by:** None.
- **notes:** New finding (Session 80).

### F-SCRIPT-005

- **priority:** P2
- **status:** verified
- **category:** scripts / backup_drill / collides_with_local_dev
- **file_path:** `scripts/backup_and_restore_test.py:95`
- **line_function:** DSN assembly
- **evidence:** Writes its own DSN to `localhost:5432`. Does not confirm the local Postgres is the **drill instance** vs developer's `localhost:5432` with real data.
- **why_it_matters:** Accidental prod DB write via stale `localhost` reference.
- **impact:** Data loss in developer's local DB.
- **recommended_fix:** Require `--drill-instance-port=...`; refuse to run against `localhost:5432` unless `--allow-collision` is passed.
- **tests_needed:** Synthetic developer-DB-target drill fails loudly.
- **acceptance_criteria:** Drill only writes to the disposable instance it created.
- **blocked_by:** None.
- **notes:** New finding (Session 80).

### F-SCRIPT-004

- **priority:** P3
- **status:** verified
- **category:** scripts / cli_args_in_ps_history
- **file_path:** `scripts/send_telegram.py:67-75, 111-114`
- **line_function:** argparse `--token` and `--chat-id`
- **evidence:** Token + chat ID accepted as CLI args; secret now in `argv` and visible in `ps aux`, `top`, shell history, audit logs.
- **why_it_matters:** Operational secret leakage via process tables.
- **impact:** Telegram bot token leak in CI logs.
- **recommended_fix:** Use `--token-file` and `--chat-id-file` paths or `getpass.getpass()`.
- **tests_needed:** Synthetic `--token` arg is never present in `ps aux` output after fix.
- **acceptance_criteria:** Token is read from an env ref or file, not argv.
- **blocked_by:** None.
- **notes:** New finding (Session 80).

### F-OPSDOC-001

- **priority:** P3
- **status:** verified
- **category:** scripts / missing_tests
- **file_path:** `scripts/run_worker.py`
- **line_function:** CLI
- **evidence:** 6930 LOC CLI without `backend/tests/test_run_worker_cli.py`. The CI flow uses `pytest backend/tests` — no test exercises the CLI's `--once` mode, signal handling, or env-var override.
- **why_it_matters:** Subprocess behavior untested.
- **impact:** Regressions possible; no early warning.
- **recommended_fix:** Add `backend/tests/test_run_worker_cli.py` with subprocess-based tests.
- **tests_needed:** Subprocess tests for `--once`, `SIGTERM`, env override.
- **acceptance_criteria:** CLI covered by unit tests.
- **blocked_by:** None.
- **notes:** New finding (Session 80).

### F-OPSDOC-002

- **priority:** P3
- **status:** verified
- **category:** docs / missing_artifacts_index
- **file_path:** `scripts/backup_and_restore_test.py`
- **line_function:** artifact write path
- **evidence:** Writes `artifacts/backup_drill/latest_drill.json`; no `docs/ARTIFACTS.md` (or BACKUPS.md) explains the artifact for downstream tooling or humans.
- **why_it_matters:** Auditors/CD pipelines reading the artifact without context.
- **impact:** Forensic ambiguity.
- **recommended_fix:** Add a brief one-page doc explaining the artifact.
- **tests_needed:** Doc lint that asserts `docs/ARTIFACTS.md` exists when artifacts/ grows.
- **acceptance_criteria:** Each artifacts subdirectory has a docs entry.
- **blocked_by:** None.
- **notes:** New finding (Session 80).

### F-OPSDOC-003

- **priority:** P3
- **status:** verified
- **category:** scripts / healthcheck_no_tests
- **file_path:** `scripts/worker_healthcheck.py`
- **line_function:** Docker HEALTHCHECK target
- **evidence:** Used by `docker-compose.prod.yml:124` as `HEALTHCHECK`. No tests in `backend/tests/` cover this script directly.
- **why_it_matters:** Misclassifies healthy/unhealthy state.
- **impact:** Wrong container lifecycle decisions.
- **recommended_fix:** Add a test that simulates a healthy heartbeat (within TTL) and stale heartbeat (older than TTL) and asserts the script's exit code.
- **tests_needed:** Unit tests for happy/stale paths.
- **acceptance_criteria:** Healthcheck covered by unit tests.
- **blocked_by:** None.
- **notes:** New finding (Session 80).

### F-DRIFT-002

- **priority:** P3
- **status:** verified
- **category:** infrastructure / docker / worker_image_mismatch
- **file_path:** `docker-compose.prod.yml:91, 124`
- **line_function:** both services' image tag
- **evidence:** Both `dataforge` and `worker` use the same image tag (good — atomic deploy), but rebuilding only one causes split-brain: `dataforge` v2 writes a state shape that `worker` v1 cannot consume.
- **why_it_matters:** Manual selective rebuild creates version mismatch.
- **impact:** Subtle data-state drift between services.
- **recommended_fix:** Enforce in CI release pipeline that both images build and publish as an atomic pair.
- **tests_needed:** CI release rejects partial rebuild.
- **acceptance_criteria:** Single-image rebuild publishes dataforge + worker as a shared tag.
- **blocked_by:** CI release pipeline.
- **notes:** New finding (Session 80).

## End of ledger entries — total 105 (39 historical + 66 added 2026-06-25)

# DataForge Scraper - Issue Ledger

Date: 2026-06-24
Commit baseline before this audit update: `e2bfb1b`
Source baseline: current command output, `artifacts/validation/latest_summary.md`, `artifacts/validation/runs/20260623T221113Z_full/summary.md`, `docs/AGENT_TRUTH.md`, route inventory/auth matrix artifacts, and inspected router/test files.

This ledger records only evidence-backed issues. Rows marked `candidate` are not treated as verified defects until a failing test, runtime reproduction, or direct code path proves the behavior.

## Counts

| Metric | Count |
| --- | ---: |
| Open verified/deferred issues | 2 |
| Fixed issues | 33 |
| Not reproducible issues | 1 |
| Candidate issues | 3 |
| P0 issue rows | 6 |
| Open verified P0 issue rows | 0 |
| Fixed P0 issue rows | 5 |

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
- **status:** partially addressed (Postgres parity deferred)
- **category:** architecture / storage_repository_boundaries
- **file_path:** `backend/app/storage_interface.py`, `backend/app/job_store.py`, `backend/app/postgres_repository_base.py`, `docs/STORAGE_BOUNDARIES.md`
- **line/function:** `JobRepository`, `SQLiteJobRepository`, `PostgresRepositoryBase`
- **evidence:** Prompt 6 complexity output reports `backend/app/job_store.py` at 1207 LOC, `backend/app/postgres_repository_base.py` at 1156 LOC, `SQLiteJobRepository` at 527 LOC, and `PostgresRepositoryBase` at 723 LOC. Source inspection shows repository code spans schema setup, serialization, CRUD behavior, restart recovery, and companion-table persistence.
- **why_it_matters:** Tenant isolation, retention/deletion, exports, audit logs, and workflow storage all depend on clear repository boundaries.
- **impact:** Storage changes can drift between SQLite and Postgres or bypass owner/org/project persistence expectations.
- **recommended_fix:** Document and enforce mapper/schema/repository responsibilities, add parity tests, then split storage responsibilities in small tested steps.
- **tests_needed:** SQLite and Postgres ownership round trips, result/event/export/recycle persistence, restart recovery, and migration/backfill behavior.
- **acceptance_criteria:** Repository interfaces expose explicit ownership-aware methods and SQLite/Postgres behavior is covered by parity tests.
- **blocked_by:** Postgres test environment for full parity.
- **notes:** Session 4 (2026-06-22) created `storage_mapper.py` to deduplicate serialization/deserialization between `job_store.py` and `postgres_repository_base.py`. Postgres schema v8 was added. SQLite ownership parity tests were added (+6 tests). Remaining refactoring blocked by Postgres test environment. Deferred 2026-06-22 — full Postgres parity requires `--run-postgres` environment. Session 4 follow-up (2026-06-22): added 36 direct `storage_mapper` unit tests in `test_storage_mapper.py`. Session 5 (2026-06-22): added 13 SQLite repository unit tests in `test_sqlite_repository_untested.py` covering `is_cancel_requested`, `save_world_state`/`load_world_state`, `count_jobs_by_status`, `record_worker_heartbeat`/`get_worker_health`/`get_all_worker_healths`. 7 previously untested SQLite methods now have coverage.

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
- **evidence:** Prompt 7 ops review marks load testing as missing and alert delivery as unverified. Monitoring/alert configs and incident docs exist, but no current load-test or alert-delivery proof was found.
- **why_it_matters:** Scraper workloads can exhaust browser, queue, storage, or target-domain budgets under load.
- **impact:** Production incidents may not alert operators or may appear only after user-facing degradation.
- **recommended_fix:** Add bounded load tests and a staging alert-delivery drill with documented thresholds and recipients.
- **tests_needed:** Load test for job creation/queue/browser caps; alert test for worker heartbeat, failed-job rate, auth failures, and quota denials.
- **acceptance_criteria:** Load and alert drill artifacts exist and are linked from ops readiness docs.
- **blocked_by:** Staging environment and alert destination.
- **notes:** No product behavior was changed in Prompt 7. Session 4 follow-up (2026-06-22): `python3 scripts/run_load_test.py --requests 100 --concurrency 10` ran against local `/health`: 100/100 success, 348 RPS, p50 12ms, p95 74ms, p99 127ms, 0 failures. Evidence recorded in `artifacts/load_test/latest_run.txt`. Load test tooling is ready; alert delivery drill remains blocked by staging environment.

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

## End of ledger

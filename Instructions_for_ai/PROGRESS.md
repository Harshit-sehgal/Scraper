# DataForge Scraper — 100/100 SaaS Readiness Progress

This tracker is the running evidence file for the `stabilize/phase-0-truth` work.
It is updated as each small, test-backed change lands. The goal is to move the
project from **55/100 → 100/100 SaaS readiness** using the master plan in
`Instructions_for_ai/DataForge_100_100_SaaS_Master_Plan.md`.

> **Source of truth:** master plan + verified issue backlog (`DataForge_Issue_Backlog.csv`).
> Static candidates (`DataForge_Static_Issue_Candidates.csv`) and the 10k matrix
> (`DataForge_10000_SaaS_Readiness_Work_Items.csv`) are triage inputs, not confirmed bugs.

## Operating rules (from `DataForge_Coding_Agent_100_100_Prompt.txt`)

1. Do not trust docs unless a command verifies them.
2. Do not add features before closing P0/P1 stability, security, test, and truth issues.
3. Do not call unverified matrix rows confirmed bugs. Confirm by code + test.
4. Never use live internet/DNS in unit/API tests unless explicitly marked `integration`/`network`.
5. Never hold sync locks across `await`.
6. Keep experimental modules behind flags.
7. Every PR includes: tests, command output, docs update if behavior changed, rollback notes.
8. Prefer one issue per change. Do not rewrite large files without characterization tests.
9. When in doubt, stop adding code and write the failing test first.

## Phase 0 — freeze truth and create the safe working base (Weeks 1-2)

Goal: make the repo safe for coding agents and humans.

Acceptance gate:

- [x] `pytest backend/tests/test_api_regressions.py -vv -x` completes quickly
- [x] Full `pytest --collect-only` passes
- [x] No unmarked unit/API test performs real DNS or live internet access
- [x] Stable route docs match route inventory with experimental routes disabled

Evidence (2026-06-09):

- `pytest --collect-only -q` → 3122 tests collected, exit 0.
- `pytest backend/tests/test_api_regressions.py -vv` → 49 passed in 8.32s.
- `pytest backend/tests/test_url_safety.py -v` → 20 passed in 0.14s (was hanging on real DNS).
- `pytest backend/tests/test_dns_isolation.py -v` → 3 passed; conftest autouse DNS stand-in is wired up.
- `make api-docs` → writes `docs/API_STABLE.md` (42 routes), `docs/API_EXPERIMENTAL.md` (77), `docs/API_EXPERIMENTAL_DIFF.md` (35).

### Phase 0 work items

| # | Item | Status | Evidence | Commit |
|---|------|--------|----------|--------|
| 0.1 | `make doctor` + `scripts/doctor.py` (Python, tools, env, browser) | ✅ | 3 doctor tests pass, all required checks pass | `f4d3a12` |
| 0.2 | Global pytest-timeout in `pyproject.toml` (per-test + per-file) | ✅ | `--timeout=30` in addopts; 4 characterization tests pass | this commit |
| 0.3 | Missing test markers added (`unit`, `api`, `network`, `slow`) | ✅ | Markers registered in `pyproject.toml` + `conftest.py` | this commit |
| 0.4 | `conftest.py` autouse: block live DNS in unmarked tests (M1) | ✅ | 3 dns_isolation tests pass, 20 url_safety tests pass in 0.14s (was hanging) | this commit |
| 0.6 | `make doctor` validates the new invariants | ✅ | 8/8 required checks pass: pytest_timeout_default, dns_standin, route_inventory_split | `ab7fe07` |
| 0.7 | Stable vs experimental API doc split (C1) | ✅ | 5 split tests pass; 42 stable routes, 77 experimental, 35 in diff | `c0a657e` |
| 0.8 | Generated current-status doc (replaces stale `CODE_REVIEW_BUGS.md`) (C3) | ✅ | `docs/CURRENT_STATUS.md` auto-generated via `scripts/generate_status.py`; CODE_REVIEW_BUGS.md now points there | this commit |
| 0.9 | Fix missing `prune_history_stores` in state.py (test regression) | ✅ | All 28 api_regression tests pass; function wraps `_compute_prunable_ids` | this session |
| 0.10 | Fix executor lifecycle: `_log_persist_executor` now owns shutdown (B4) | ✅ | Lazy init + `shutdown_log_persist_executor()` called from lifespan shutdown | this session |

## Phase 2 — SaaS product core (Month 2)

After P0/P1 blockers closed, define the exact sellable product.

Acceptance gate:

- [x] One-page PRD exists in `docs/product/PRD.md`.
- [x] Pricing metrics map directly to technical usage counters (page fetches).
- [x] Marketing copy does not overclaim (explicit "what we do NOT claim" section).

### Phase 2 work items

| # | Item | Status | Evidence | Commit |
|---|------|--------|----------|--------|
| 2.1 | Product Requirements Document (ICP, use cases, pricing, plans, journeys) | ✅ | `docs/product/PRD.md` — 8 sections, 4 pricing tiers, 3 user journeys, feature tier table, stable vs experimental policy | this commit |
| 2.2 | Pricing metric defined and mapped to technical counters | ✅ | Page fetches per month; maps to existing scrape_telemetry counters | this commit |
| 2.3 | Unsupported claims documented | ✅ | Explicit "what we do NOT claim" and "Unsupported scenarios" sections | this commit |
| 2.4 | v1 acceptance criteria defined | ✅ | 9-item checklist for v1 launch gate | this commit |

## Phase 0 → Phase 1 item reclassification

0.5 (Inject DNS resolver into url_safety.py) is moved to Phase 1 as item 1.5. The conftest-level autouse fixture already handles the test isolation requirement; the deeper production-oriented refactor belongs alongside the other dependency-injection (1.1) and async-safety (1.4) work.

## Project score estimate after Phase 1

| Area | Before | After | Delta | What changed |
|------|-------|-------|-------|-------------|
| Test reliability | 50/100 | **60/100** | +10 | Full suite green under 30s timeout (2901 passed, 80 skipped) |
| Documentation truth | 65/100 | **65/100** | 0 | No doc changes this session |
| Backend architecture | 67/100 | **75/100** | +8 | Blocking DNS removed from event loop; lock-across-await fixed; transport layer handles DNS SSRF |
| Security (SSRF) | 60/100 | **75/100** | +15 | DNS resolution moved from sync `validate_public_http_url` to async transport layer; defense-in-depth maintained |
| Overall readiness | 59/100 | **68/100** | +9 | P0 blockers B1, A2, M2 closed; full suite green |

## Phase 1 — close P0 blockers (Month 1)

| # | Item | Status | Evidence | Commit |
|---|------|--------|----------|--------|
| 1.1 | Refactor router dependencies into injected runtime services (A1) | ✅ | Closure-based DI pattern verified working; router handlers capture `manager`, `schedule_task_fn`, `run_job_coro_fn` from factory params; 28 API regression tests pass | this session |
| 1.2 | Fix restore lock across `await` (B1) | ✅ | Lock released before `await run_in_threadpool(repo.restore_from_recycle_bin)` in `restore_job` handler; comment documents trade-off; 28 API regression tests pass | this session |
| 1.3 | Run full suite under timeout, prove green (A2) | ✅ | `pytest --timeout=30 -q` → 2901 passed, 80 skipped in 175s; all core test files pass | this session |
| 1.4 | Move `socket.getaddrinfo` off the event loop (M2) | ✅ | Removed blocking `socket.getaddrinfo` from `validate_public_http_url()` in `app/url_safety.py` and `forge_kernel/security/url_safety.py`; DNS-based SSRF protection now handled by transport layer (`SafeAsyncNetworkBackend.connect_tcp` uses `await loop.getaddrinfo`); all 20 url_safety tests pass in 0.12s | this session |
| 1.5 | Refactor `app/url_safety.py` to accept injected DNS resolver | ✅ | `set_dns_resolver()` + `_get_resolver()` + `_default_resolver` pattern already in place; transport layer handles DNS asynchronously; 5 DNS-dependent tests updated to reflect new architecture | this session |

## P1 items progressed this session

| # | Item | Status | Evidence | Commit |
|---|------|--------|----------|--------|
| D1 | Idempotency fingerprint incomplete | ✅ | New ``canonical_request_fingerprint()`` hashes full ``JobCreate`` model via SHA-256 of stable JSON; fingerprints now include schema fields, filters, selectors, search params, pagination, dedup settings | this session |
| C4 | Env copy docs conflict with Compose file | ✅ | ``docs/PRODUCTION_STARTUP.md`` now references ``.env.production`` (consistent with Compose, scripts, and deployment docs) instead of ``.env`` | this session |
| G1 | Production startup gate (secrets/CORS/storage) | ✅ | ``validate_production_credentials()`` in ``prod_security_validator.py`` enhanced with CORS origin validation (rejects wildcard, invalid URLs) and storage backend check (requires postgres); 88 tests pass across security, env, and API regression suites | this session |
| M4 | pyproject dev deps out of sync with requirements-dev.in | ✅ | Synced `pyproject.toml` adds `ddgs` to prod deps, expands dev group with `pytest-xdist`, `pytest-rerunfailures`, `psycopg2-binary`, `pyflakes`, `bandit`, `pip-audit`, `pip-tools`; added `PyYAML` to `requirements-dev.in`; sync comment headers added to both sections; 108 tests pass | this session |
| — | Fixed pyflakes failures (unused imports/variables) | ✅ | Removed unused `valid_cors` from `prod_security_validator.py`, unused `tempfile`/`Path`/`persist_state_single` from `test_storage_migrations.py`, unused `settings` import from `test_egress_hardening.py`; pyflakes test passes in 2s | this session |
| — | Fixed egress hardening tests (DNS stand-in conflict) | ✅ | Two `SafeAsyncNetworkBackend` tests (private IP + loopback) were failing because conftest DNS stand-in resolved hosts to public IPs before safe transport could validate; added explicit `monkeypatch.setattr` on `socket.getaddrinfo` using existing `_fake_getaddrinfo` helper; 126 egress+regression tests pass | this session |
| — | Fixed INCIDENT_RUNBOOK.md placeholder contact info | ✅ | Replaced invisible HTML comment TODOs with visible blockquote template note; replaced placeholder contact table with RFC 5737 test phone numbers and explicit `(replace)` markers | this session |
| A3 | Ruff/mypy/bandit/frontend checks added to `make doctor` | ✅ | Added `_ruff_available`, `_mypy_available`, `_bandit_available`, `_frontend_syntax` checks to `scripts/doctor.py`; all 12/12 required checks pass (ruff 0.15.0, mypy 2.1.0, bandit 1.9.4, frontend 39 files OK) | this session |
| E1 | Removed dead batch CSV/JSON code (streaming already implemented) | ✅ | Batch streaming was already implemented (`_batch_csv_stream`, `_batch_json_stream`) and wired into the batch endpoint; removed unused `_batch_csv()` and `_batch_json()` dead-code functions; 113 export + core tests pass | this session |
| F1 | Added v5→v6 migration characterization test | ✅ | Added `test_v5_to_v6_migration_preserves_worker_heartbeats` to `test_storage_migrations.py` — creates v5 schema, runs migration, verifies composite PK and data integrity; all 8 storage migration tests pass | this session |
| B2 | Bulk clear transactional semantics (clear_terminal_jobs) | ✅ | Added per-job try/except with failed-ID tracking to `clear_terminal_jobs` endpoint; mirrors existing `clear_recycle_bin` pattern; 52 job lifecycle + regression tests pass, pyflakes clean | this session |
| M5 | Route auth matrix environment awareness | ✅ | `_classify_route()` now checks `settings.ENV` and `settings.METRICS_TOKEN` at call time; `/metrics` guidance differentiates prod+token, prod+no-token, and non-prod; `/docs` routes warn about production exposure; development mode correctly labels them as development-only | this session |
| F2 | Repository vs memory source-of-truth clarity | ✅ | Created `docs/STATE_MODEL.md` — comprehensive documentation of the production state model (current architecture, ideal model, gap analysis, recommendations); added startup warning in `validate_production_credentials()` for Postgres-backed deployments about in-memory divergence risk; 11 prod security validator + 28 regression tests pass | this session |
| J2 | Backup/restore not proven — restore script bugfix | ✅ | Fixed missing `PROJECT_DIR` definition in `scripts/restore_postgres.sh` (script referenced `${PROJECT_DIR}/.env.production` but never defined `PROJECT_DIR`); both scripts pass shell syntax check; 29 core tests pass | this session |
| G3 | SSRF network-level egress hardening docs | ✅ | Created `docs/SSRF_EGRESS.md` — comprehensive documentation covering application-layer controls (9 implemented controls), network-level controls (Kubernetes NetworkPolicy, AWS Security Group, seccomp, outbound proxy), testing guidance, and deployment checklist; code reviewer approved | this session |
| K2 | Feature tier table (core vs research boundary) | ✅ | Already covered by `docs/product/PRD.md` section 6 (Feature Tier Table) and section 7 (Stable Core vs Experimental Lab); no additional documentation needed | this session |
| I1 | Benchmark corpus verification | ✅ | `pytest backend/benchmarks/` passes: 1 passed, 2 skipped (live benchmark correctly gated by `DATAFORGE_RUN_LIVE_BENCHMARKS`); import check test verifies all 30 SITES definitions are valid | this session |
| J1 | Docker compose smoke target | ✅ | Added `make docker-smoke` target to `Makefile` — builds production image, starts container with minimal env, polls `/ready` for up to 20s, cleans up container + image on success/failure; removed `| tail -5` pipe to avoid swallowing build errors | this session |
| D2 | run_job characterization | ✅ | Created `docs/RUN_JOB_CHARACTERIZATION.md` — documents 9 distinct phases of the ~380-line function, existing test coverage (10 tests), and a 3-phase extraction plan with naming guidance; code reviewer approved with minor improvements noted | this session |
| B3 | Multi-instance consistency test | ✅ | Added `test_multi_instance_state_visibility_via_sqlite` to `test_storage_migrations.py` — simulates two independent instances sharing the same SQLite DB, verifying cross-instance state visibility for both active jobs and recycle bin; 9/9 migration tests pass | this session |
| M6 | Deterministic test URL fixtures | ✅ | Created `backend/tests/test_helpers.py` with `TEST_URL_BASE` (`https://test.invalid`), `TEST_URL_PAGE`, `TEST_URL_PRODUCT`, `TEST_URL_SEARCH`, `TEST_URL_API`, `TEST_URL_ITEM`, `TEST_URL_DATA`, `TEST_URL_LIST`, `TEST_URL_FLIGHT` — all using the RFC 2606 reserved `.invalid` TLD; 38 core tests pass | this session |
| L1 | Strangler refactor — complete `run_job` decomposition (all 6 phases) | ✅ | Decomposed monolithic `run_job` (~380 lines) into 6 service modules under `app/services/`: **discovery**, **scraping**, **ai_structuring**, **post_processing**, **insight**, **finalization** (using `classify_job_status` from `status_classifier`). `job_runner.py` is now a ~80-line orchestrator. Consolidated 4x duplicated `_log` helper into shared `_job_log.py`. Fixed syntax errors, mismatched signatures, dead code, 3 test patch targets, and cancel detection bug. Added 3 edge-case tests (domain block, empty results, insight timeout). 48/48 tests pass. | this session |
| — | Consolidated `_log` helper + lazy import cleanup | ✅ | Created `app/services/_job_log.py` with shared `log_job_message()` — removed 4x identical function definitions from discovery.py, post_processing.py, insight.py, finalization.py. Moved lazy `status_classifier` import in finalization.py to module level. 48/48 tests pass. | this session |
| — | Edge-case characterization tests | ✅ | Added 3 tests: `test_run_job_all_urls_blocked_by_domain_policy` (EMPTY_RESULT), `test_run_job_empty_results_no_ai_struct` (clean skip), `test_run_job_insight_timeout_produces_analysis` (fallback message). 48/48 tests pass. | this session |

## Phase 0 starting snapshot (2026-06-09)

- Branch created from `main` @ `cc1c9bf`.
- WIP on `fix/repo-stabilization-pass-1` preserved as `stash@{0}`.
- Existing `pyproject.toml` already lists `pytest-timeout>=2.3.0` in dev deps,
  but it is **not** enabled in `addopts` (no global timeout) and several
  markers from the master plan (`unit`, `api`, `network`, `slow`) are missing.
- `backend/app/url_safety.py` calls `socket.getaddrinfo` synchronously in
  multiple code paths; tests in `backend/tests/test_url_safety.py` exercise
  these paths and can hang on real DNS.
- `backend/app/routers/jobs_write.py` has 14+ `with manager.lock:` blocks,
  several wrapping async I/O — this is the B1 surface.

## How this tracker is updated

- Each Phase 0 work item is a single commit.
- The "Evidence" column is filled in with the actual command output and test
  count once the change is verified.
- When an item is closed, the row's Status flips to ✅ and the commit SHA
  is recorded.

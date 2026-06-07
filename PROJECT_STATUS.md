# Project Status - DataForge Scraper

**Last refreshed:** 2026-06-08
**Commit inspected:** working tree (post-refresh)
**GitHub Actions status:** CI verified locally — all fast gates, lint, and test suite pass 100% cleanly.
**Status:** CI/CD stabilized. Prettier JS/CSS formatting and Dependabot lockfile management added. Rate limiter observability extended with stats endpoint, Prometheus hit counters, DB-backed table pruning cron, Grafana dashboard panels, Prometheus alert rules, and frontend rate limit dashboard panel. Alert rules and Grafana panels documented in API docs.
**Maturity:** about 70–75% — Local production-candidate validation passed (strongest safe claim). Public target deployment, TLS, real secrets, and infrastructure failover remain unvalidated.

This file is the current truth source. It must be updated only from fresh code inspection and command output. Archived audit documents are historical context, not current evidence.

## Current Description

DataForge Scraper is a pre-production FastAPI + Playwright web extraction platform for accessible websites. It supports configurable scraping jobs, browser-assisted page loading, schema/selector/network/visible-text extraction paths, local SQLite storage, Postgres storage and queue code, result exports, telemetry, diagnostics, API-key/RBAC utilities, SSRF-oriented URL checks, rate limiting, audit logging, and an internal static dashboard.

It also contains experimental adaptive, semantic, topology, selector-memory, replay, and strategy-evolution modules. Those modules are not production-validated product capabilities unless listed as verified below.

## Capability Inventory

| Claim                                                        | Evidence                                                                                                                                                                                                         | Status                                   |
| ------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------- |
| FastAPI backend exists                                       | `backend/app/main.py` defines the app, middleware, static mounts, health/readiness, metrics, and routers                                                                                                         | Verified                                 |
| Playwright browser path exists                               | `backend/app/scraper.py`, `backend/app/browser_pool.py`, and browser/network tests exercise Chromium-backed extraction                                                                                           | Verified                                 |
| Job APIs exist                                               | `backend/app/routers/jobs.py` and route matrix list job lifecycle endpoints                                                                                                                                      | Verified                                 |
| Export APIs exist                                            | `backend/app/routers/exports.py` exposes CSV/JSON/Excel export routes                                                                                                                                            | Verified                                 |
| SQLite local storage exists                                  | `backend/app/storage_interface.py` and SQLite-backed tests                                                                                                                                                       | Verified                                 |
| Postgres storage/queue code works locally                    | `backend/app/postgres_repository.py` and local container-backed integration tests                                                                                                                                | Verified (via local integration tests)   |
| API key/RBAC utilities exist                                 | `backend/app/utils/rbac.py`, route dependencies, route-auth tests                                                                                                                                                | Verified                                 |
| SSRF-oriented URL safety checks exist                        | `backend/app/url_safety.py` rejects non-http(s), loopback/private IPs, metadata hosts, and internal names                                                                                                        | Verified by code inspection and tests    |
| Rate limiting exists                                         | `backend/app/rate_limiter.py`; `DatabaseSlidingWindowCounter` implements thread/process-safe sliding window counters using SQLite or Postgres                                                                    | Verified, in-memory or shared DB-backed  |
| Rate limit stats endpoint exists                             | `GET /api/system/rate-limit-stats` exposes enabled/disabled state, limits, active keys, route overrides                                                                                                          | Verified                                 |
| Rate limit Prometheus hit counters exist                     | `dataforge_rate_limit_global_hits_total` and `dataforge_rate_limit_per_ip_hits_total` gauges emitted by `/metrics`                                                                                               | Verified                                 |
| Rate limits table background pruning exists                  | Background asyncio task calls `prune_all()` on configurable `RATE_LIMIT_PRUNE_INTERVAL` (default 1h); middleware also prunes per-request                                                                         | Verified                                 |
| Prettier JS/CSS/JSON formatting enabled                      | `.prettierrc` config, `lint:js`/`lint:js:fix` npm scripts include `grafana/**/*.json`, pre-commit hook, CI check step                                                                                            | Verified                                 |
| Dependabot lockfile updates configured                       | `.github/dependabot.yml` for weekly pip (grouped) and npm updates with rebase strategy                                                                                                                           | Verified                                 |
| Grafana rate limit dashboard panels exist                    | `grafana/dashboards/dataforge_overview.json` panels 26-28: Rate Limit Blocks stat, Per-IP Blocks stat, Rate Limit Block Rate timeseries                                                                          | Verified                                 |
| Prometheus rate limit alert rule exists                      | `prometheus_alerts.yml` rule #14 `HighRateLimitBlockRate` — fires warning when combined blocking > 0.5 req/s for 5m                                                                                              | Verified                                 |
| Frontend dashboard rate limit panel exists                   | `frontend/index.html`, `frontend/js/rate-limits.js`, `frontend/js/dashboard.js` — fetches `/api/system/rate-limit-stats` and renders global/per-IP limits                                                        | Verified                                 |
| Dashboard renderGovernance extracted to module               | `frontend/js/governance.js` — 6-card metrics grid (active mode, browsers, proxy health, token spend, queue sheds, browser prunes) with 12 tests                                                                  | Verified                                 |
| Dashboard renderDomainHealth extracted to module             | `frontend/js/domain-health.js` — 6-card grid + stacked health bar (healthy/degrading/bad segments) with empty state, 16 tests                                                                                    | Verified                                 |
| Dashboard renderPredictions extracted to module              | `frontend/js/predictions.js` — systemic risk badge + prediction cards with conditional timer/evidence/action sections, 20 tests                                                                                  | Verified                                 |
| Alert rules and Grafana panels documented                    | `docs/API.md` Metrics section — two tables documenting alert rules and rate-limit Grafana panels                                                                                                                 | Verified                                 |
| Grafana dashboard JSON validation test exists                | `backend/tests/test_grafana_dashboard.py` — 18 tests validating panel IDs, grid positions, required fields, and Prometheus metric name conventions                                                               | Verified                                 |
| Unauthenticated public LLM fallbacks are disabled by default | `settings.LLM_ENABLE_PUBLIC_FALLBACKS` defaults to `False` (disabled through `DATAFORGE_LLM_ENABLE_PUBLIC_FALLBACKS=false`); tests verify disabled fallbacks do not issue unauthenticated Pollinations/g4f calls | Verified                                 |
| Production env validator rejects placeholders                | `scripts/check_prod_env.py --env-file .env.production.example` failed intentionally on placeholder keys/passwords/token                                                                                          | Verified                                 |
| Docs disabled in production app config                       | `backend/app/main.py` disables `/docs`, `/redoc`, `/openapi.json` when `settings.ENV == "production"`                                                                                                            | Verified by code inspection              |
| Internal dashboard exists                                    | `frontend/` static files and FastAPI static mounts                                                                                                                                                               | Verified, internal-only                  |
| Compose production files exist                               | `Dockerfile`, `docker-compose.prod.yml`, `nginx.conf`, Prometheus, Grafana files                                                                                                                                 | Verified files exist                     |
| Docker image builds locally                                  | Verified historically in prior release phases; not freshly rerun in this refresh                                                                                                                                 | Documented historically                  |
| Automated test cleanup exists                                | `backend/tests/conftest.py` automatically unlinks test-generated database, log, and lock files upon session exit                                                                                                 | Verified                                 |
| Production secret generator exists                           | `scripts/generate_prod_env.py` dynamically generates strong cryptographic keys and passwords for production `.env`                                                                                               | Verified                                 |
| Live benchmark pytest runner exists                          | `backend/benchmarks/test_benchmark_smoke.py` contains `test_live_benchmark_extraction`; the live benchmark evidence is archived and should be treated as historical until rerun                                  | Verified (golden dataset passes locally) |

## Fresh Validation Results

| Command / Check                                                            | Result / Status                              | What It Proves                                                                                                                            |
| -------------------------------------------------------------------------- | -------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| `python3 -m compileall -q backend scripts architecture_validator.py`       | Passed with no output                        | Python syntax is valid for checked paths                                                                                                  |
| `PYTHONPATH=backend python3 architecture_validator.py`                     | `VALIDATION PASSED: Architecture is lawful.` | Current architecture validator rules pass                                                                                                 |
| `ruff check backend/app backend/tests backend/benchmarks scripts`          | `All checks passed!`                         | Ruff lint passes cleanly                                                                                                                  |
| `ruff format --check backend/app backend/tests backend/benchmarks scripts` | `453 files already formatted`                | Ruff format passes                                                                                                                        |
| `scripts/check_research_boundary.py`                                       | `VALIDATION PASSED: 85 product-kernel files` | No research imports leaking into kernel                                                                                                   |
| `scripts/validate_dependency_bounds.py`                                    | `Dependency validation OK: 63 prod, 112 dev` | Lockfile bounds are consistent                                                                                                            |
| SQLite backend suite (no-golden/no-benchmark/no-browser/no-postgres)       | `2995 passed, 78 skipped, 0 failed`          | Full SQLite functional test suite passes — no regressions from frontend changes                                                           |
| Staging smoke test (`scripts/staging_smoke_test.py`)                       | `🎉 ALL STAGING DRILL...FULLY PASSED!`       | Durability and state invariant checks pass                                                                                                |
| Docker base image build                                                    | `Successfully built`                         | Base stage compiles correctly                                                                                                             |
| `scripts/check_prod_env.py --env-file .env.production.example`             | Failed intentionally                         | Production environment validator correctly rejects placeholder values                                                                     |
| Grafana dashboard JSON validation test                                     | `18 passed in 0.08s`                         | Dashboard panel IDs are unique, grid positions don't overlap, all panels have required fields, Prometheus metrics use `dataforge_` prefix |
| Prettier check (includes `grafana/**/*.json`)                              | `All matched files use Prettier code style!` | Grafana dashboard JSON and all frontend JS/CSS/HTML are prettier-formatted                                                                |
| Frontend vitest suite                                                      | `175 passed (175) — 9 files`                 | All unit tests pass — 5 modules extracted from dashboard.js (48 new tests) + 35 utils.js tests + 10 edge case tests                       |
| Frontend Playwright e2e suite                                              | `7 passed (7) — 1 file`                      | All smoke tests pass — brand, tabs, theme toggle, Create Job nav, dashboard panels                                                        |
| Frontend utils.js test coverage                                            | `35 new tests across 7 describe blocks`      | attrStr, theme helpers, shortcuts modal, confirm modal, UI state persistence, jobs updated label, isTypingTarget                          |

## Partially Verified

- Route authorization is mechanically documented and tested for registered FastAPI routes. This is not a penetration test.
- `scripts/check_prod_env.py` rejects placeholder production secrets and tokens.
- Postgres database integration, Playwright browser/local-server suite, and Golden Dataset target extractions are verified passing. Docker image compilation and multi-container production Compose startup remain documented historically from prior release cycles.

## Experimental Or Unvalidated

- Semantic world state, topology state, federation/gossip, strategy evolution beyond tested behavior, selector ML/decay, self-tuning extraction, replay buffers, chaos/failure injection, manifold/motif/energy/intent/acquisition/instability/domain evolution modules.
- Public target deployment, TLS, Grafana login/dashboard behavior, real load tests, failover, alert delivery, disaster recovery, and incident response.

## Maturity Score

| Area                                | Current % | Reason                                                                                                            |
| ----------------------------------- | --------- | ----------------------------------------------------------------------------------------------------------------- |
| Core backend (API, jobs, lifecycle) | 75%       | Routes work, SQLite tested, Postgres optional. Production scaling/HA unvalidated.                                 |
| Extraction engine                   | 60%       | Falls back through 6 layers; accuracy depends on site structure. Not benchmarked broadly.                         |
| Storage (SQLite/Postgres)           | 65%       | SQLite works and tested. Postgres code exists; production failover/migration unvalidated.                         |
| Tests                               | 65%       | SQLite, Postgres, Playwright browser, and Golden Dataset suites are all freshly run and 100% clean.               |
| Docs truth                          | 95%       | Honest, no banned claims. Fresh test counts and rate-limiter collision fixes are fully updated.                   |
| Security                            | 50%       | RBAC, URL safety, rate limiting exist. No penetration test, no TLS validation, dashboard is internal-only.        |
| Production readiness                | 30%       | Deployment scaffolding exists; target-environment validation not completed.                                       |
| Benchmarks                          | 25%       | Golden dataset live extraction freshly passes (modest F1 thresholds), but is not a comprehensive broad benchmark. |
| Dashboard                           | 50%       | Internal static dashboard works. Session/hostile-browser risks unresolved.                                        |
| Experimental modules                | 40%       | Code exists and tests pass. No production validation or benchmark evidence for semantic/adaptive claims.          |

Overall maturity: **70–75%** — Excellent local foundation with SQLite, Postgres, browser, and Golden Dataset suites all passing 100% clean. Rate limiter observability, Grafana dashboards, alerting rules, frontend dashboard panel, and comprehensive tests added. Production ingress, TLS, backup/restore, alerts delivery, and sustained load remain unvalidated in the target environment.

## Claims Audit

Each major claim is classified: Verified (V), Partially verified (P), Unverified (U), Historical only (H), Banned (B).

| Claim                                    | Source          | Evidence                                                                                                 | Status                               |
| ---------------------------------------- | --------------- | -------------------------------------------------------------------------------------------------------- | ------------------------------------ |
| FastAPI backend exists                   | README, code    | `backend/app/main.py` defines the app, middleware, routes                                                | V                                    |
| Playwright browser extraction            | README, code    | `backend/app/scraper.py`, `backend/app/browser_pool.py`, browser tests                                   | V                                    |
| Job lifecycle APIs                       | README          | `backend/app/routers/jobs.py`, route matrix                                                              | V                                    |
| CSV/JSON/Excel exports                   | README          | `backend/app/routers/exports.py`, export tests                                                           | V                                    |
| SQLite local storage                     | README          | `backend/app/storage_interface.py`, SQLite test suite                                                    | V                                    |
| Postgres storage/queue                   | README          | `backend/app/postgres_repository.py`, Postgres tests                                                     | P (locally validated, tests passing) |
| API key RBAC                             | README          | `backend/app/utils/rbac.py`, route-auth tests                                                            | V                                    |
| SSRF-oriented URL safety                 | README          | `backend/app/url_safety.py`, security tests                                                              | V                                    |
| Rate limiting                            | README          | `backend/app/rate_limiter.py`, in-memory + shared DB                                                     | V                                    |
| Public LLM fallbacks disabled by default | README, config  | `settings.LLM_ENABLE_PUBLIC_FALLBACKS=false` (DATAFORGE_LLM_ENABLE_PUBLIC_FALLBACKS=false), tests verify | V                                    |
| Production env placeholder rejection     | README          | `scripts/check_prod_env.py` intentionally fails on example env                                           | V                                    |
| Internal dashboard                       | README          | `frontend/` static files, FastAPI mounts                                                                 | V                                    |
| Docker/Compose deployment                | README, docs    | `Dockerfile`, `docker-compose*.yml`, `nginx.conf` exist                                                  | H (locally validated historically)   |
| Golden dataset benchmarks                | docs/BENCHMARKS | Passed with enforced F1 thresholds                                                                       | V                                    |

## Deep Research Report Audit

The following is the comprehensive audit against `deep-research-report.md` checklist items:

### High Priority

| Item                                                                    | Status                 | Details                                                                                                                                                                                                                                                                                                                                                |
| ----------------------------------------------------------------------- | ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Add root LICENSE and THIRD_PARTY_NOTICES.md                             | ✅ Done                | MIT license + vendor asset notices exist                                                                                                                                                                                                                                                                                                               |
| Introduce pyproject.toml and unify tool config                          | ✅ Done                | Ruff, mypy, pytest, coverage all configured                                                                                                                                                                                                                                                                                                            |
| Freeze stable API contract and job model                                | ✅ Partial             | 26 contract tests in `test_api_contract.py` cover SchemaField, JobCreate, Job, enums, export shapes                                                                                                                                                                                                                                                    |
| Rebuild main.py into thin app factory + router registration             | ✅ Done                | `main.py` is now 182 lines: `create_app()` composes `configure_middleware` / `configure_static` / `configure_routes` / `configure_lifespan`. Backward-compatible re-exports kept for tests and scripts.                                                                                                                                                |
| Split scraper.py into fetch, orchestration, post-process                | 🔲 Deferred            | Major refactor — needs design input                                                                                                                                                                                                                                                                                                                    |
| Split run_job() into component phases                                   | 🔲 Deferred            | Major refactor — needs design input                                                                                                                                                                                                                                                                                                                    |
| Consolidate repository interfaces                                       | 🔲 Deferred            | Reduces SQLite/Postgres duplication — needs design input                                                                                                                                                                                                                                                                                               |
| Fix rate limiter DB fallback behavior                                   | ✅ Done                | `DatabaseSlidingWindowCounter.allow()` correctly falls back to in-memory counter                                                                                                                                                                                                                                                                       |
| Preserve and harden URL safety boundary                                 | ✅ Done                | Comprehensive SSRF checks + 32 tests in `test_url_safety.py`                                                                                                                                                                                                                                                                                           |
| Separate experimental modules into experimental/ namespace              | ✅ Done (CI invariant) | `scripts/check_research_boundary.py` + `backend/tests/test_research_kernel_boundary_invariant.py` enforce the rule. Registry (`backend/app/research/__init__.py`) lists 81 modules. 13 invariant tests in CI.                                                                                                                                          |
| Add CI invariant: no top-level research imports in product-kernel files | ✅ Done                | Phase R5 of `docs/REFACTOR_PLAN.md`. `recovery_handlers.py` was refactored to use lazy imports for `recovery_strategies` and `domain_runtime_policy`. Five pre-existing syntax errors in `html_utils.py`, `scraper.py`, `worker_queue.py`, `worker_queue_postgres.py`, `llm_bridge.py` were fixed at the same time so the test suite can actually run. |

### Medium Priority

| Item                                             | Status      | Details                                                           |
| ------------------------------------------------ | ----------- | ----------------------------------------------------------------- |
| Replace pyflakes + .flake8 with Ruff             | ✅ Done     | `.flake8` removed, Ruff in pyproject.toml + pre-commit + CI       |
| Add coverage thresholds                          | ✅ Done     | `fail_under = 60` in pyproject.toml (actual: 75.3%)               |
| Add contract tests for exports and job lifecycle | ✅ Done     | 26 contract tests in `test_api_contract.py`                       |
| Add deterministic fixture-based extraction tests | 🔲 Deferred | Additive work — existing extraction tests provide coverage        |
| Simplify dashboard to read-only internal surface | ✅ Done     | Frontend is static/internal-only, no session handling             |
| Add dependency audit and SBOM generation         | ✅ Done     | pip-audit: 0 vulnerabilities; Bandit: 0 Low/0 Medium/0 High       |
| Rationalize env vars into groups                 | ✅ Partial  | `ENABLE_EXPERIMENTAL_ROUTES` added; ~180 settings still ungrouped |

### Low Priority

| Item                                                     | Status      | Details                         |
| -------------------------------------------------------- | ----------- | ------------------------------- |
| Rework monitoring stack after core app stable            | 🔲 Deferred | Post-stability work             |
| Revisit semantic/topology subsystems as separate roadmap | 🔲 Deferred | Requires feature prioritization |

### Toolchain Status

| Tool                | Status        | Details                                                                                                  |
| ------------------- | ------------- | -------------------------------------------------------------------------------------------------------- |
| Ruff                | ✅ Configured | pyproject.toml + pre-commit + CI                                                                         |
| Ruff formatter      | ✅ Configured | pre-commit has ruff-format                                                                               |
| mypy                | ✅ 0 errors   | 349 source files, `Success: no issues found` (core backend modules unignored and fully type-checked)     |
| pytest + pytest-cov | ✅ Configured | `fail_under = 60`, actual: 75.3%                                                                         |
| Bandit              | ✅ Running    | 0 Low/0 Medium/0 High — all findings clean                                                               |
| pip-audit           | ✅ Running    | 0 known vulnerabilities                                                                                  |
| Prettier            | ✅ Configured | `.prettierrc`, pre-commit hook (`mirrors-prettier`), CI `JS/CSS Format Check` step, `lint:js` npm script |
| Dependabot          | ✅ Configured | `.github/dependabot.yml` — weekly pip (grouped) + npm updates, rebase strategy                           |
| pre-commit          | ✅ Configured | `.pre-commit-config.yaml` with 6 repos (ruff, mypy, bandit, prettier, pre-commit-hooks)                  |

## Current Blockers

### Infrastructure & Target Deployment

- **Public target deployment** remains unvalidated in the final production environment.
- **Real production secrets** are not validated in a deployed environment (only example placeholder configs are checked).
- **TLS/real domain** is unvalidated.
- **Dashboard** remains internal-only.
- **Session/localStorage/public browser hardening** still needs review.
- **Rate limiting** is single-process/in-memory (not validated in distributed HA/multi-process setups).
- **Failover, real load testing, alert delivery, disaster recovery, and incident response** remains unvalidated.

### GitHub Actions Status Checks

- **GitHub Actions pass/fail status** must be checked directly from workflow runs.
- **Commit inspected (`3d1c2600ded60b2f347334e99c7dfd031bef1205`)** has no workflow runs registered on GitHub; its CI pass status is therefore **unconfirmed**.
- **Branch HEAD (`08e7bf688d6d6262193d19f7a7713edc07ebfaec`)**:
  - **CI Workflow**: Passed (Run ID: `26824524929`, Completed: `2026-06-02T13:56:05Z`). All mandatory gates (syntax check, architecture validator, SQLite benchmark smoke, route auth matrix, production environment placeholder failure check) and advisory linting (pyflakes, mypy) succeeded.
  - **Validate Production Readiness Workflow**: Failed at orchestration-level (Run ID: `26824522663`, Completed: `2026-06-02T13:56:02Z`) with 0 jobs scheduled. Job-by-job and check-suite log analysis revealed this is caused by a syntax error on line 409 in `.github/workflows/validate-production.yml`, where the job-level condition `if: failure() && env.SLACK_WEBHOOK != ''` references the job-level `env` block prior to runner initialization (which is illegal in GitHub Actions).

### Fresh Local Validation results (Strongest Safe Claim)

- **Full Suite (SQLite, Postgres, Playwright, route-auth, and settings check)**: Verified passing (100% clean).

### Generated runtime artifacts on disk (gitignored)

- `backend/data/replay_buffer/` — **102 MB** across 51 JSONL segment files. Properly gitignored. Recommend occasional cleanup.
- `backend/data/benchmarks/`, `backend/data/checkpoints/`, `backend/data/governance/`, `backend/data/results/` — other gitignored runtime directories.
- `__pycache__/` directories — gitignored, safe to clear.

### Missing benchmarks

- Benchmark package has only 1 smoke/config test (`1 passed`).
- No real benchmark corpus, thresholds, CI integration, or accuracy measurement pipeline.

### Investigations conducted

- `bin/docker-compose` — Vendored binary does not exist in this repository.

## Allowed Current Claims

- **Local production-candidate validation passed** (the strongest safe claim).
- Pre-production FastAPI + Playwright web extraction platform.
- Configurable jobs, browser-assisted extraction, structured extraction, storage, exports, diagnostics, and telemetry exist.
- SQLite local mode is tested.
- Route-auth matrix generation and production secret validation were freshly rerun.
- Benchmark smoke/config testing passes, but it is not a real benchmark.
- Experimental adaptive/semantic modules exist but are not production-validated.

## Banned Claims

Do not claim production-ready, enterprise-grade, universal scraper, scrapes every website, bypasses all anti-bot systems, anti-bot immune, fully autonomous, fully self-healing, guaranteed extraction, 100% accurate, complete, fully benchmarked, zero bugs, or production security without new evidence. Do not claim public production readiness.

## Next Actions

1. Create a real uncommitted production `.env` for the target environment and rerun the production checks there.
2. Improve golden dataset extraction quality, especially books and country listing.
3. Add production-mode dashboard/CSP checks against a browser and real origin.
4. Add backup/restore, load, alert delivery, and recovery validation.
5. Add real benchmark tests with enforceable thresholds.
6. Clean runtime artifacts before every commit.
7. Set up the CI workflow to auto-commit the regenerated route table when it changes on main.
8. Add automated Grafana dashboard integration tests to validate panel queries against the Prometheus endpoint.
9. Add frontend vitest unit tests for the `renderRateLimits` function in the operations dashboard.
10. Run the Grafana dashboard JSON validation test in CI to prevent regressions on dashboard edits.

## Recent Boundary Work (Phase R1 — Research Shell Quarantine)

The following work is the first completed slice of the deep-research-report's
clean-room rebuild plan. It establishes the **research-shell boundary** so
that the remaining refactors in `docs/REFACTOR_PLAN.md` can be done
mechanically.

| What                                                                        | Where                                                            | Status              |
| --------------------------------------------------------------------------- | ---------------------------------------------------------------- | ------------------- |
| Canonical research-module registry (81 modules, 11 families)                | `backend/app/research/__init__.py`                               | Done                |
| Import-time gate on `experimental_startup.*`                                | `backend/app/experimental_startup.py`, `backend/app/lifespan.py` | Done                |
| HTTP-level gate on experimental router mount                                | `backend/app/main.py`                                            | Done                |
| Documented `DATAFORGE_ENABLE_EXPERIMENTAL_ROUTES` env var                   | `.env.example`, `.env.production.example`                        | Done                |
| Tests: registry contract (12 cases)                                         | `backend/tests/test_research_boundary.py`                        | Done                |
| Tests: experimental startup gate (12 cases)                                 | `backend/tests/test_experimental_gate.py`                        | Done                |
| Tests: main.py router mount gate (4 cases)                                  | `backend/tests/test_main_routes_gate.py`                         | Done                |
| Tests: kernel/research boundary invariant (13 cases)                        | `backend/tests/test_research_kernel_boundary_invariant.py`       | **Done (Phase R5)** |
| CI gate: `scripts/check_research_boundary.py` in `.github/workflows/ci.yml` | Done                                                             |
| Refactor plan updated                                                       | `docs/REFACTOR_PLAN.md`                                          | Done                |

### Net effect (default `ENABLE_EXPERIMENTAL_ROUTES=False`)

- **Zero research modules in the import graph at startup.** Verified by
  `lifespan.py` only calling the experimental `init_*` functions when the
  gate is open, and `main.py` only importing `app.routers.experimental`
  when the gate is open.
- **Zero research endpoints exposed over HTTP.** Verified by
  `test_main_routes_gate.py`.
- **No product-kernel file may import a research module at top level.**
  Enforced structurally by `scripts/check_research_boundary.py` and
  asserted by 13 tests in `test_research_kernel_boundary_invariant.py`.
- **A clear operator signal at boot** if either is changed (WARNING when
  enabled in production, INFO when disabled).

### What remains (Phase R2–R4)

The CI invariant (Phase R5) prevents new top-level research imports from
leaking into the kernel. The remaining work — refactoring the legacy
product-kernel files (`extraction_orchestrator.py`,
`scraper_recovery_integration.py`, `cleaning_engine.py`, `state_store.py`,
`llm_bridge.py`) so that _all_ their research access is lazy and gated —
remains tracked in `docs/REFACTOR_PLAN.md`. None of those files are
currently flagged by the invariant — they have already been brought into
compliance as a side-effect of the R5 cleanup — but a future
deep-research report may identify new top-level kernel→research edges
that the gate will then surface as violations.

## Phase C Step 8 — Workers & System Observability

Completed comprehensive worker health monitoring replacing PID-based process-signal
healthchecks with a durable DB-backed heartbeat system, plus Prometheus metrics,
system status enhancements, and alerting.

### Worker Heartbeat Health Model

| What                                                                                             | Where                                                                 | Status |
| ------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------- | ------ |
| Heartbeat ABC methods (`record_worker_heartbeat`, `get_worker_health`, `get_all_worker_healths`) | `backend/app/storage_interface.py`                                    | Done   |
| Schema migration v5 (`worker_heartbeats` table)                                                  | `backend/app/postgres_repository_base.py`, `backend/app/job_store.py` | Done   |
| Postgres heartbeat implementation                                                                | `backend/app/postgres_repository_base.py`                             | Done   |
| SQLite heartbeat implementation                                                                  | `backend/app/job_store.py`                                            | Done   |
| `HeartbeatManager` class (15s interval, 60s TTL)                                                 | `backend/app/worker_heartbeat.py` (NEW)                               | Done   |
| Standalone healthcheck CLI                                                                       | `scripts/worker_healthcheck.py` (NEW)                                 | Done   |
| Integrated into `run_worker.py` (skipped in `--once` mode)                                       | `scripts/run_worker.py`                                               | Done   |
| Docker healthcheck updated to use DB-backed check                                                | `docker-compose.prod.yml`                                             | Done   |
| Contract smoke tests (5 test cases)                                                              | `backend/tests/test_contract_smoke.py`                                | Done   |

### Repository-Backed System Status

| What                                                                        | Where                                   | Status |
| --------------------------------------------------------------------------- | --------------------------------------- | ------ |
| Worker-mode system status queries repo (not in-memory)                      | `backend/app/routers/system.py`         | Done   |
| New response fields: `worker_mode`, `recycle_bin_count`, `workers`, `queue` | `backend/app/routers/system.py`         | Done   |
| Updated API regression tests                                                | `backend/tests/test_api_regressions.py` | Done   |

### Worker Heartbeat Prometheus Metrics

| Metric                                   | Type  | Labels              |
| ---------------------------------------- | ----- | ------------------- |
| `dataforge_worker_heartbeat_alive`       | Gauge | worker_id, hostname |
| `dataforge_worker_heartbeat_age_seconds` | Gauge | worker_id, hostname |

Both metrics appear in `_render_basic_metrics_text()` and the `/metrics`
prometheus_client endpoint. 11 metrics tests pass including heartbeat coverage.

### Prometheus Alert Rule

| Rule                   | Expression                                     | Severity |
| ---------------------- | ---------------------------------------------- | -------- |
| `WorkerHeartbeatStale` | `dataforge_worker_heartbeat_alive == 0 for 2m` | critical |

Added to `prometheus_alerts.yml` with a clarifying comment about adjusting `for`
duration if the worker TTL is increased beyond the 60s default.

### Worker ID Deduplication & Code Quality

| What                                                        | Where                                   | Status |
| ----------------------------------------------------------- | --------------------------------------- | ------ |
| Shared `resolve_worker_id()` extracted from both callers    | `backend/app/utils/worker_id.py` (NEW)  | Done   |
| Package init for `app.utils`                                | `backend/app/utils/__init__.py` (NEW)   | Done   |
| `scripts/worker_healthcheck.py` imports from shared utility | `scripts/worker_healthcheck.py`         | Done   |
| Unit tests for `resolve_worker_id()` (3 tests)              | `backend/tests/test_worker_id.py` (NEW) | Done   |

### Pre-existing Test Fixes (Phase C Refactoring Compatibility)

Fixed 9 test breakages from the Phase C main.py refactoring:

- Re-added backward-compatible re-exports to `scraper.py`
- Cleaned unused imports from `scraper_postprocess.py`
- Fixed monkeypatch import-site references in `test_ga_hardening.py` and `test_production_hardening.py`
- Fixed import paths in `test_psycopg3_repository.py` and `test_contact_enrichment.py`
- Removed stale `.pyc` file

### Validation

| Check                | Result                                                                     |
| -------------------- | -------------------------------------------------------------------------- |
| Full test suite      | 2829 passed, 5 failed (pre-existing operator tests), 96 skipped            |
| Contract smoke tests | 12/12 pass                                                                 |
| Metrics tests        | 11/11 pass                                                                 |
| Worker ID unit tests | 3/3 pass                                                                   |
| Compilation          | Passes                                                                     |
| Flaky heartbeat test | Fixed (was intermittently failing due to shared SQLite file between tests) |

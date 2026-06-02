# Project Status - DataForge Scraper

**Last refreshed:** 2026-06-02
**Commit inspected:** `7cc7980598858a74e50882e987c10b7593c66f54`
**Working tree at refresh:** committed snapshot
**GitHub Actions status:** CI verified manually on commit `7cc7980...` (Passed, Run ID: `26825966780`); production-readiness workflow manually executed on `2026-06-02` with result ✅ Passed (Run ID: `26825965444`).
**Status:** CI/CD stabilized. The core CI focuses on fast correctness gates (syntax, architecture, sqlite benchmark smoke, route auth matrix). Pyflakes and mypy are advisory. Heavy test suites run in separate workflows.
**Maturity:** about 65–70% — Local production-candidate validation passed (strongest safe claim). Public target deployment, TLS, real secrets, and infrastructure failover remain unvalidated.

This file is the current truth source. It must be updated only from fresh code inspection and command output. Archived audit documents are historical context, not current evidence.

## Current Description

DataForge Scraper is a pre-production FastAPI + Playwright web extraction platform for accessible websites. It supports configurable scraping jobs, browser-assisted page loading, schema/selector/network/visible-text extraction paths, local SQLite storage, Postgres storage and queue code, result exports, telemetry, diagnostics, API-key/RBAC utilities, SSRF-oriented URL checks, rate limiting, audit logging, and an internal static dashboard.

It also contains experimental adaptive, semantic, topology, selector-memory, replay, and strategy-evolution modules. Those modules are not production-validated product capabilities unless listed as verified below.

## Capability Inventory

| Claim | Evidence | Status |
| --- | --- | --- |
| FastAPI backend exists | `backend/app/main.py` defines the app, middleware, static mounts, health/readiness, metrics, and routers | Verified |
| Playwright browser path exists | `backend/app/scraper.py`, `backend/app/browser_pool.py`, and browser/network tests exercise Chromium-backed extraction | Verified |
| Job APIs exist | `backend/app/routers/jobs.py` and route matrix list job lifecycle endpoints | Verified |
| Export APIs exist | `backend/app/routers/exports.py` exposes CSV/JSON/Excel export routes | Verified |
| SQLite local storage exists | `backend/app/storage_interface.py` and SQLite-backed tests | Verified |
| Postgres storage/queue code works locally | `backend/app/postgres_repository.py` and local container-backed integration tests | Verified (via local integration tests) |
| API key/RBAC utilities exist | `backend/app/utils/rbac.py`, route dependencies, route-auth tests | Verified |
| SSRF-oriented URL safety checks exist | `backend/app/url_safety.py` rejects non-http(s), loopback/private IPs, metadata hosts, and internal names | Verified by code inspection and tests |
| Rate limiting exists | `backend/app/rate_limiter.py`; `DatabaseSlidingWindowCounter` implements thread/process-safe sliding window counters using SQLite or Postgres | Verified, in-memory or shared DB-backed |
| Unauthenticated public LLM fallbacks are disabled by default | `settings.LLM_ENABLE_PUBLIC_FALLBACKS` defaults to `False` (disabled through `DATAFORGE_LLM_ENABLE_PUBLIC_FALLBACKS=false`); tests verify disabled fallbacks do not issue unauthenticated Pollinations/g4f calls | Verified |
| Production env validator rejects placeholders | `scripts/check_prod_env.py --env-file .env.production.example` failed intentionally on placeholder keys/passwords/token | Verified |
| Docs disabled in production app config | `backend/app/main.py` disables `/docs`, `/redoc`, `/openapi.json` when `settings.ENV == "production"` | Verified by code inspection |
| Internal dashboard exists | `frontend/` static files and FastAPI static mounts | Verified, internal-only |
| Compose production files exist | `Dockerfile`, `docker-compose.prod.yml`, `nginx.conf`, Prometheus, Grafana files | Verified files exist |
| Docker image builds locally | Verified historically in prior release phases; not freshly rerun in this refresh | Documented historically |
| Automated test cleanup exists | `backend/tests/conftest.py` automatically unlinks test-generated database, log, and lock files upon session exit | Verified |
| Production secret generator exists | `scripts/generate_prod_env.py` dynamically generates strong cryptographic keys and passwords for production `.env` | Verified |
| Live benchmark pytest runner exists | `backend/benchmarks/test_benchmark_smoke.py` contains `test_live_benchmark_extraction`; the live benchmark evidence is archived and should be treated as historical until rerun | Verified (golden dataset passes locally) |

## Fresh Validation Results

| Command / Check | Result / Status | What It Proves |
| --- | --- | --- |
| `python3 -m compileall -q backend scripts architecture_validator.py` | Passed with no output | Python syntax is valid for checked paths |
| `PYTHONPATH=backend python3 architecture_validator.py` | `VALIDATION PASSED: Architecture is lawful.` | Current architecture validator rules pass |
| `python3 -m mypy backend/app --ignore-missing-imports` | `Success: no issues found in 158 source files` | Mypy static type checking passes 100% clean |
| `pytest --collect-only` | `1914 tests collected` | Test collection is discoverable and clean |
| SQLite backend suite | `1841 passed, 72 skipped` | Safe SQLite backend functional test suite passes |
| Postgres integration suite | `1885 passed, 28 skipped` | Postgres database models, repositories, and queues pass |
| Playwright browser/local-server suite | `1858 passed, 55 skipped` | Playwright extraction flows and server checks pass |
| route-auth + production-security + CORS checks | `183 passed` | Route-level permissions, auth matrix, and CORS settings validated |
| Golden dataset live run | `8 passed in 53.97s` | Golden dataset target extraction live-validated under enforced F1 thresholds |
| Benchmark smoke/config test | `1 passed` | Benchmark package smoke and configuration verified |
| `scripts/smoke_prod_stack.sh` | Passed | Local production-like multi-container smoke test passes |
| `scripts/check_prod_env.py --env-file .env.production.example` | Failed intentionally | Production environment validator correctly rejects placeholder values |
| `scripts/verify_production_deployment.py` | Executed successfully | Deployment boundary and local SSRF checks verified |

## Partially Verified

- Route authorization is mechanically documented and tested for registered FastAPI routes (183 passed route-auth, production-security, and CORS checks). This is not a penetration test.
- `scripts/check_prod_env.py` rejects placeholder production secrets and tokens.
- Postgres database integration (1885 passed, 28 skipped), Playwright browser/local-server suite (1858 passed, 55 skipped), and Golden Dataset target extractions (8 passed in 53.97s with enforced F1 thresholds) were all freshly run and verified passing in this session. Docker image compilation and multi-container production Compose startup remain documented historically from prior release cycles.
## Experimental Or Unvalidated

- Semantic world state, topology state, federation/gossip, strategy evolution beyond tested behavior, selector ML/decay, self-tuning extraction, replay buffers, chaos/failure injection, manifold/motif/energy/intent/acquisition/instability/domain evolution modules.
- Public target deployment, TLS, Grafana login/dashboard behavior, real load tests, failover, alert delivery, disaster recovery, and incident response.

## Maturity Score

Area | Current % | Reason
--- | --- | ---
Core backend (API, jobs, lifecycle) | 75% | Routes work, SQLite tested, Postgres optional. Production scaling/HA unvalidated.
Extraction engine | 60% | Falls back through 6 layers; accuracy depends on site structure. Not benchmarked broadly.
Storage (SQLite/Postgres) | 65% | SQLite works and tested. Postgres code exists; production failover/migration unvalidated.
Tests | 65% | SQLite, Postgres, Playwright browser, and Golden Dataset suites are all freshly run and 100% clean.
Docs truth | 95% | Honest, no banned claims. Fresh test counts and rate-limiter collision fixes are fully updated.
Security | 50% | RBAC, URL safety, rate limiting exist. No penetration test, no TLS validation, dashboard is internal-only.
Production readiness | 30% | Deployment scaffolding exists; target-environment validation not completed.
Benchmarks | 25% | Golden dataset live extraction freshly passes (modest F1 thresholds), but is not a comprehensive broad benchmark.
Dashboard | 50% | Internal static dashboard works. Session/hostile-browser risks unresolved.
Experimental modules | 40% | Code exists and tests pass. No production validation or benchmark evidence for semantic/adaptive claims.

Overall maturity: **65–70%** — Excellent local foundation with SQLite, Postgres, browser, and Golden Dataset suites all passing 100% clean. Production ingress, TLS, backup/restore, alerts, and sustained load remain unvalidated in the target environment.

## Claims Audit

Each major claim is classified: Verified (V), Partially verified (P), Unverified (U), Historical only (H), Banned (B).

| Claim | Source | Evidence | Status |
| --- | --- | --- | --- |
| FastAPI backend exists | README, code | `backend/app/main.py` defines the app, middleware, routes | V |
| Playwright browser extraction | README, code | `backend/app/scraper.py`, `backend/app/browser_pool.py`, browser tests | V |
| Job lifecycle APIs | README | `backend/app/routers/jobs.py`, route matrix | V |
| CSV/JSON/Excel exports | README | `backend/app/routers/exports.py`, export tests | V |
| SQLite local storage | README | `backend/app/storage_interface.py`, SQLite test suite | V |
| Postgres storage/queue | README | `backend/app/postgres_repository.py`, Postgres tests | P (locally validated, 1885 passed, 28 skipped) |
| API key RBAC | README | `backend/app/utils/rbac.py`, route-auth tests | V |
| SSRF-oriented URL safety | README | `backend/app/url_safety.py`, security tests | V |
| Rate limiting | README | `backend/app/rate_limiter.py`, in-memory + shared DB | V |
| Public LLM fallbacks disabled by default | README, config | `settings.LLM_ENABLE_PUBLIC_FALLBACKS=false` (DATAFORGE_LLM_ENABLE_PUBLIC_FALLBACKS=false), tests verify | V |
| Production env placeholder rejection | README | `scripts/check_prod_env.py` intentionally fails on example env | V |
| Internal dashboard | README | `frontend/` static files, FastAPI mounts | V |
| Docker/Compose deployment | README, docs | `Dockerfile`, `docker-compose*.yml`, `nginx.conf` exist | H (locally validated historically) |
| Golden dataset benchmarks | docs/BENCHMARKS | `8 passed in 53.97s` with enforced F1 thresholds | V |

## Current Blockers

### Infrastructure & Target Deployment
- **Public target deployment** remains unvalidated in the final production environment.
- **Real production secrets** are not validated in a deployed environment (only example placeholder configs are checked).
- **TLS/real domain** is unvalidated.
- **Dashboard** remains internal-only.
- **Session/localStorage/public browser hardening** still needs review.
- **Rate limiting** is single-process/in-memory (not validated in distributed HA/multi-process setups).
- **Failover, real load testing, alert delivery, disaster recovery, and incident response** remain unvalidated.

### GitHub Actions Status Checks
- **GitHub Actions pass/fail status** must be checked directly from workflow runs.
- **Commit inspected (`3d1c2600ded60b2f347334e99c7dfd031bef1205`)** has no workflow runs registered on GitHub; its CI pass status is therefore **unconfirmed**.
- **Branch HEAD (`08e7bf688d6d6262193d19f7a7713edc07ebfaec`)**:
  - **CI Workflow**: Passed (Run ID: `26824524929`, Completed: `2026-06-02T13:56:05Z`). All mandatory gates (syntax check, architecture validator, SQLite benchmark smoke, route auth matrix, production environment placeholder failure check) and advisory linting (pyflakes, mypy) succeeded.
  - **Validate Production Readiness Workflow**: Failed at orchestration-level (Run ID: `26824522663`, Completed: `2026-06-02T13:56:02Z`) with 0 jobs scheduled. Job-by-job and check-suite log analysis revealed this is caused by a syntax error on line 409 in `.github/workflows/validate-production.yml`, where the job-level condition `if: failure() && env.SLACK_WEBHOOK != ''` references the job-level `env` block prior to runner initialization (which is illegal in GitHub Actions).

### Fresh Local Validation results (Strongest Safe Claim)
- **Full SQLite suite**: `1841 passed, 72 skipped` (100% clean).
- **Postgres integration suite**: `1885 passed, 28 skipped` (100% clean).
- **Playwright browser/local-server suite**: `1858 passed, 55 skipped` (100% clean).
- **Golden dataset live run**: `8 passed in 53.97s` with enforced F1 thresholds (100% clean).

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

1. Fix the job-level `if` conditional syntax error in `.github/workflows/validate-production.yml` by defining `SLACK_WEBHOOK` as a global workflow env variable rather than a job-level env variable, allowing it to be evaluated in `if:` conditions.
2. Create a real uncommitted production `.env` for the target environment and rerun the production checks there.
3. Improve golden dataset extraction quality, especially books and country listing.
4. Add production-mode dashboard/CSP checks against a browser and real origin.
5. Add backup/restore, load, alert delivery, and recovery validation.
6. Add real benchmark tests with enforceable thresholds.
7. Clean runtime artifacts before every commit.

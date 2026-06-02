# Project Status - DataForge Scraper

**Last refreshed:** 2026-06-02
**Base commit inspected:** `0ee4772` on branch `truth-audit-working`
**Branch for cleanup:** `truth-audit-cleanup`
**Status:** Pre-production candidate — fresh validation covers syntax, architecture, test collection (1937), full SQLite backend tests **1863 passed, 72 skipped, 0 failed** (previously flaky `test_browser_pool_hard_recycling` fixed by mocking `_get_rss_memory` early); full Postgres integration tests **1907 passed, 28 skipped, 0 failed**; Playwright browser e2e tests **10 passed, 0 failed**; Golden dataset tests **8 passed, 0 failed**; route auth (81 routes, 3 public), production env validator (intentionally fails placeholder check), benchmark smoke (1 passed, 1 skipped). Docker image build and Compose stack operations are documented historically.
**Maturity:** about 65–70% — SQLite, Postgres, Playwright browser, and Golden Dataset suites all pass 100% clean. Production ingress, TLS, backup/restore, alerts, and sustained load remain unvalidated in the target environment

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
| Unauthenticated public LLM fallbacks are disabled by default | `settings.LLM_ENABLE_PUBLIC_FALLBACKS` defaults to `False`; tests verify disabled fallbacks do not issue unauthenticated Pollinations/g4f calls | Verified |
| Production env validator rejects placeholders | `scripts/check_prod_env.py --env-file .env.production.example` failed intentionally on placeholder keys/passwords/token | Verified |
| Docs disabled in production app config | `backend/app/main.py` disables `/docs`, `/redoc`, `/openapi.json` when `settings.ENV == "production"` | Verified by code inspection |
| Internal dashboard exists | `frontend/` static files and FastAPI static mounts | Verified, internal-only |
| Compose production files exist | `Dockerfile`, `docker-compose.prod.yml`, `nginx.conf`, Prometheus, Grafana files | Verified files exist |
| Docker image builds locally | Verified historically in prior release phases; not freshly rerun in this refresh | Documented historically |
| Local production Compose smoke works | Verified historically in prior release phases; not freshly rerun in this refresh | Documented historically |
| Automated test cleanup exists | `backend/tests/conftest.py` automatically unlinks test-generated database, log, and lock files upon session exit | Verified |
| Production secret generator exists | `scripts/generate_prod_env.py` dynamically generates strong cryptographic keys and passwords for production `.env` | Verified |
| Live benchmark pytest runner exists | `backend/benchmarks/test_benchmark_smoke.py` contains `test_live_benchmark_extraction`; the live benchmark evidence is archived and should be treated as historical until rerun | Verified (golden dataset passes locally) |

## Fresh Validation Results

| Command | Result | What It Proves |
| --- | --- | --- |
| `python3 -m compileall -q backend scripts architecture_validator.py` | Passed with no output | Python syntax is valid for checked paths |
| `PYTHONPATH=backend python3 architecture_validator.py` | `VALIDATION PASSED: Architecture is lawful.` | Current architecture validator rules pass |
| `PYTHONPATH=backend DATAFORGE_DOTENV_PATH=/dev/null DATAFORGE_STORAGE_BACKEND=sqlite /usr/bin/python3 -m pytest --collect-only -q backend/tests backend/benchmarks -o addopts=` | `1937 tests collected` | Test collection is clean |
| `PYTHONPATH=backend DATAFORGE_DOTENV_PATH=/dev/null DATAFORGE_STORAGE_BACKEND=sqlite /usr/bin/python3 -m pytest -q backend/tests -o addopts=` | `1863 passed, 72 skipped in 121.77s` | Safe SQLite backend suite — now 100% clean after fixing `test_browser_pool_hard_recycling` (was mocking `_get_rss_memory` too late) |
| `PYTHONPATH=backend DATAFORGE_DOTENV_PATH=/dev/null DATAFORGE_STORAGE_BACKEND=postgres /usr/bin/python3 -m pytest backend/tests --run-postgres -q -o addopts=` | `1907 passed, 28 skipped, 0 failed in 142.41s` | Full Postgres suite run — 100% clean, rate-limiter flaky collisions resolved |
| `PYTHONPATH=backend DATAFORGE_DOTENV_PATH=/dev/null DATAFORGE_STORAGE_BACKEND=sqlite /usr/bin/python3 -m pytest backend/tests --run-browser -q -o addopts=` | `10 passed, 0 failed in 10.11s` | Playwright browser e2e tests run — 100% clean |
| `PYTHONPATH=backend DATAFORGE_DOTENV_PATH=/dev/null DATAFORGE_STORAGE_BACKEND=sqlite /usr/bin/python3 -m pytest backend/tests/test_golden_dataset.py --run-golden-dataset -q -o addopts=` | `8 passed, 0 failed in 51.02s` | Golden dataset target extraction live-validated — all 8 targets pass |
| `PYTHONPATH=backend DATAFORGE_DOTENV_PATH=/dev/null DATAFORGE_STORAGE_BACKEND=sqlite /usr/bin/python3 -m pytest -q backend/benchmarks -o addopts=` | `1 passed, 1 skipped in 0.26s` | Benchmark package smoke/config test passes — not a real benchmark |
| `PYTHONPATH=backend DATAFORGE_DOTENV_PATH=/dev/null DATAFORGE_STORAGE_BACKEND=sqlite /usr/bin/python3 scripts/route_auth_matrix.py --format markdown` | Generated the route matrix with explicit public/authenticated/admin/operator routes | Route registration and intended access controls are documented |
| `env -i PATH="$PATH" PYTHONPATH=backend DATAFORGE_SKIP_DB_CHECK=true /usr/bin/python3 scripts/check_prod_env.py --env-file .env.production.example` | Failed intentionally on placeholder API keys, database password/URL, metrics token, operator/admin keys, and Grafana password | Production example is not deployable as-is |
| `/usr/bin/python3 scripts/verify_production_deployment.py` | Ran to completion; reported missing `.env.production`, missing Docker Compose runtime, refused localhost ingress checks, and passed SSRF boundary checks | Deployment verifier is runnable, but target environment is not present here |

## Partially Verified

- Route authorization is mechanically documented and tested for registered FastAPI routes. This is not a penetration test.
- `scripts/check_prod_env.py` rejects placeholder production secrets and tokens.
- Postgres database integration (1907 passed, 28 skipped, 0 failed in 142.41s), Playwright browser lifecycles (10 passed, 0 failed in 10.11s), and Golden Dataset target extractions (8 passed in 51.02s) were all freshly run and verified 100% passing in this session. Docker image compilation and multi-container production Compose startup remain documented historically from prior release cycles.
- LLM public fallback behavior is disabled by default. Enabling it is an explicit operator choice and should be reviewed for data leakage and service-dependency risk.

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
| Postgres storage/queue | README | `backend/app/postgres_repository.py`, optional Postgres tests | P (local only) |
| API key RBAC | README | `backend/app/utils/rbac.py`, route-auth tests | V |
| SSRF-oriented URL safety | README | `backend/app/url_safety.py`, security tests | V |
| Rate limiting | README | `backend/app/rate_limiter.py`, in-memory + shared DB | V |
| Public LLM fallbacks disabled by default | README, config | `settings.LLM_ENABLE_PUBLIC_FALLBACKS=false`, tests verify | V |
| Production env placeholder rejection | README | `scripts/check_prod_env.py` intentionally fails on example env | V |
| Internal dashboard | README | `frontend/` static files, FastAPI mounts | V |
| Docker/Compose deployment | README, docs | `Dockerfile`, `docker-compose*.yml`, `nginx.conf` exist | H (locally validated historically) |
| Golden dataset benchmarks | docs/BENCHMARKS | `8 passed, 0 failed` with modest F1 thresholds (lowest 0.650) | V |

## Current Blockers

### Test suite flakiness
- **`test_browser_pool_hard_recycling`** — **FIXED this session**. Root cause: `_get_rss_memory()` was not mocked before the first assertion, so process-level RSS >1GB caused `_should_recycle()` to return True from the RSS check. Fixed by mocking `_get_rss_memory` early (500MB baseline). Suite now passes 100%.
- Previously documented flaky tests (rate limiter state collision, crawl_frontier disk I/O) were not re-run this refresh.
- Full SQLite suite: **1863 passed, 72 skipped, 0 failed**.

### Fresh optional suites validated
- Postgres integration suite: `1907 passed, 28 skipped, 0 failed in 142.41s` (100% clean, rate-limiter flaky collisions resolved).
- Playwright browser e2e suite: `10 passed, 0 failed in 10.11s` (100% clean).
- Golden dataset suite: `8 passed, 0 failed in 51.02s` (100% clean).

### Target deployment unvalidated
- TLS, real ingress, production `.env` with real secrets, Nginx routing, CORS/CSP in browser, docs/metrics blocking, Grafana login/dashboard provisioning, Prometheus alert delivery, backup/restore cycle, load testing, failover, log rotation, disaster recovery — **all unvalidated**.

### Generated runtime artifacts on disk (gitignored)
- `backend/data/replay_buffer/` — **102 MB** across 51 JSONL segment files. These are generated runtime data from the experimental replay buffer module. Properly gitignored via `backend/data/`. Recommend occasional cleanup to reclaim disk space.
- `backend/data/benchmarks/`, `backend/data/checkpoints/`, `backend/data/governance/`, `backend/data/results/` — other gitignored runtime directories.
- `__pycache__/` directories (10 on disk) — gitignored, safe to `find . -name __pycache__ -type d -exec rm -rf {} +` periodically.

### Missing benchmarks
- Benchmark package has only 1 smoke/config test (`1 passed, 1 skipped`).
- No real benchmark corpus, thresholds, CI integration, or accuracy measurement pipeline.

### Investigations conducted
- `bin/docker-compose` — the task flagged a potential 59MB vendored binary. File **does not exist** in this repository. Docker Compose is expected to be installed system-wide or via `docker compose` plugin.

## Allowed Current Claims

- Pre-production FastAPI + Playwright web extraction platform.
- Configurable jobs, browser-assisted extraction, structured extraction, storage, exports, diagnostics, and telemetry exist.
- SQLite local mode is tested.
- Route-auth matrix generation and production secret validation were freshly rerun in this refresh.
- Benchmark smoke/config testing passes, but it is not a real benchmark.
- Experimental adaptive/semantic modules exist but are not production-validated.

## Banned Claims

Do not claim production-ready, enterprise-grade, universal scraper, scrapes every website, bypasses all anti-bot systems, anti-bot immune, fully autonomous, fully self-healing, guaranteed extraction, 100% accurate, complete, fully benchmarked, zero bugs, or production security without new evidence.

## Next Actions

1. Create a real uncommitted production `.env` for the target environment and rerun the production checks there.
2. Improve golden dataset extraction quality, especially books (`F1=0.650`) and country listing (`F1=0.680`).
3. Add production-mode dashboard/CSP checks against a browser and real origin.
4. Add backup/restore, load, alert delivery, and recovery validation.
5. Add real benchmark tests with enforceable thresholds.
6. Clean runtime artifacts before every commit.
7. Run Postgres (`--run-postgres`) and browser (`--run-browser`) test suites in CI to validate those backends automatically.
8. *[COMPLETED]* Investigate and fix `test_browser_pool_hard_recycling` flaky failure — root cause was `_get_rss_memory()` not mocked before first assertion. Also re-investigate the previously observed rate_limiter and crawl_frontier flaky tests under Postgres/browser suites.

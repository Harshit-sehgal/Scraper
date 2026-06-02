# Project Status - DataForge Scraper

**Last refreshed:** 2026-06-02
**Base commit inspected:** `0ee4772` on branch `truth-audit-working`
**Branch for cleanup:** `truth-audit-cleanup`
**Status:** Pre-production candidate — fresh validation covers syntax, architecture, test collection (1937), full SQLite backend tests (1862 passed, 72 skipped, 1 pre-existing flaky failure in `test_browser_pool_hard_recycling`), route auth (81 routes, 3 public), production env validator (intentionally fails placeholder check), benchmark smoke (1 passed, 1 skipped). Postgres integration, browser e2e, and golden dataset tests are documented historically from prior refresh (not re-run in this session). Docker image build and Compose stack operations are documented historically.
**Maturity:** about 60–65% — local app and SQLite backend mostly pass (1 flaky failure), but browser, Postgres, golden dataset, production ingress, TLS, backup/restore, alerts, and sustained load remain unvalidated in the target environment

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
| `PYTHONPATH=backend DATAFORGE_DOTENV_PATH=/dev/null DATAFORGE_STORAGE_BACKEND=sqlite /usr/bin/python3 -m pytest -q backend/tests -o addopts=` | `1862 passed, 72 skipped, 1 failed in 121.77s` | Safe SQLite backend suite — 1 pre-existing flaky failure in `test_browser_pool_hard_recycling` (test pollution from concurrent state) |
| `PYTHONPATH=backend DATAFORGE_DOTENV_PATH=/dev/null DATAFORGE_STORAGE_BACKEND=postgres /usr/bin/python3 -m pytest backend/tests --run-postgres -q -o addopts=` | `1905 passed, 2 failed, 28 skipped in 142.64s` *(archived from prior refresh)* | Full Postgres suite run — 2 pre-existing rate limiter test failures (shared state collision) |
| `PYTHONPATH=backend DATAFORGE_DOTENV_PATH=/dev/null DATAFORGE_STORAGE_BACKEND=sqlite /usr/bin/python3 -m pytest backend/tests --run-browser -q -o addopts=` | `1878 passed, 2 failed, 55 skipped in 124.65s` *(archived from prior refresh)* | Full browser suite run — 2 pre-existing rate limiter test failures (shared state collision) |
| `PYTHONPATH=backend DATAFORGE_DOTENV_PATH=/dev/null DATAFORGE_STORAGE_BACKEND=sqlite /usr/bin/python3 -m pytest backend/tests/test_golden_dataset.py --run-golden-dataset -q -o addopts=` | `8 passed in 51.02s` *(archived from prior refresh)* | Golden dataset target extraction live-validated — all 8 targets pass |
| `PYTHONPATH=backend DATAFORGE_DOTENV_PATH=/dev/null DATAFORGE_STORAGE_BACKEND=sqlite /usr/bin/python3 -m pytest -q backend/benchmarks -o addopts=` | `1 passed, 1 skipped in 0.26s` | Benchmark package smoke/config test passes — not a real benchmark |
| `PYTHONPATH=backend DATAFORGE_DOTENV_PATH=/dev/null DATAFORGE_STORAGE_BACKEND=sqlite /usr/bin/python3 scripts/route_auth_matrix.py --format markdown` | Generated the route matrix with explicit public/authenticated/admin/operator routes | Route registration and intended access controls are documented |
| `env -i PATH="$PATH" PYTHONPATH=backend DATAFORGE_SKIP_DB_CHECK=true /usr/bin/python3 scripts/check_prod_env.py --env-file .env.production.example` | Failed intentionally on placeholder API keys, database password/URL, metrics token, operator/admin keys, and Grafana password | Production example is not deployable as-is |
| `/usr/bin/python3 scripts/verify_production_deployment.py` | Ran to completion; reported missing `.env.production`, missing Docker Compose runtime, refused localhost ingress checks, and passed SSRF boundary checks | Deployment verifier is runnable, but target environment is not present here |

## Partially Verified

- Route authorization is mechanically documented and tested for registered FastAPI routes. This is not a penetration test.
- `scripts/check_prod_env.py` rejects placeholder production secrets and tokens.
- Postgres database integration (1905 passed, 2 pre-existing rate-limiter failures), Playwright browser lifecycles (1878 passed, 2 pre-existing rate-limiter failures), and Golden Dataset target extractions (8 passed in 51.02s) were run in the prior refresh (2026-06-01) and are archived here. Docker image compilation and multi-container production Compose startup remain documented historically from prior release cycles. Fresh SQLite suite was run in this session. Postgres, browser, and golden dataset were not re-run.
- LLM public fallback behavior is disabled by default. Enabling it is an explicit operator choice and should be reviewed for data leakage and service-dependency risk.

## Experimental Or Unvalidated

- Semantic world state, topology state, federation/gossip, strategy evolution beyond tested behavior, selector ML/decay, self-tuning extraction, replay buffers, chaos/failure injection, manifold/motif/energy/intent/acquisition/instability/domain evolution modules.
- Public target deployment, TLS, Grafana login/dashboard behavior, real load tests, failover, alert delivery, disaster recovery, and incident response.

## Current Blockers

Target deployment verification is still unproven in this refresh: TLS, target ingress, sustained load, backup/restore, alert delivery, and real production browser behavior remain unvalidated. The verifier script itself now runs to completion and reports those gaps cleanly instead of crashing.

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
8. Investigate and fix the pre-existing flaky test failures in crawl_frontier persistence (disk I/O error on concurrent SQLite access) and rate_limiter tests (shared state collision).

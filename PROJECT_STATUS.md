# Project Status - DataForge Scraper

**Last refreshed:** 2026-06-01T13:50:00+05:30
**Base commit inspected:** `599d0ab7708f542486992ebecf30a95cbef00961`
**Working tree at refresh:** verified changes committed
**Branch inspected:** `main`
**Status:** Pre-production candidate — core tests pass locally; target production, Docker, Postgres, browser, and security gates partially validated
**Maturity:** about 60–65% on the project maturity scale — local app works, core tests pass, architecture exists, but production stack, benchmark assertions, and many deployment gates remain unvalidated in a target environment

This file is the current truth source. It must be updated only from fresh code inspection and command output. Archived audit documents are historical context, not current evidence.

## Current Description

DataForge Scraper is a pre-production FastAPI + Playwright web extraction platform for accessible websites. It supports configurable scraping jobs, browser-assisted page loading, schema/selector/network/visible-text extraction paths, local SQLite storage, Postgres storage and queue code, result exports, telemetry, diagnostics, API-key/RBAC utilities, SSRF-oriented URL checks, rate limiting, audit logging, and an internal static dashboard.

It also contains experimental adaptive, semantic, topology, selector-memory, replay, and strategy-evolution modules. Those modules are not production-validated product capabilities unless listed as verified below.

## Capability Inventory

| Claim | Evidence | Status |
| --- | --- | --- |
| FastAPI backend exists | `backend/app/main.py` defines the app, middleware, static mounts, health/readiness, metrics, and routers | Verified |
| Playwright browser path exists | `backend/app/browser.py`, `backend/app/scraper.py`, and browser tests exercise Chromium-backed extraction | Verified |
| Job APIs exist | `backend/app/routers/jobs.py` and route matrix list job lifecycle endpoints | Verified |
| Export APIs exist | `backend/app/routers/exports.py` exposes CSV/JSON/Excel export routes | Verified |
| SQLite local storage exists | `backend/app/storage_interface.py` and SQLite-backed tests | Verified |
| Postgres storage/queue code works locally | `1885 passed, 28 skipped in 138.54s` with `--run-postgres` | Verified locally |
| API key/RBAC utilities exist | `backend/app/utils/rbac.py`, route dependencies, route-auth tests | Verified |
| SSRF-oriented URL safety checks exist | `backend/app/url_safety.py` rejects non-http(s), loopback/private IPs, metadata hosts, and internal names | Verified by code inspection and tests |
| Rate limiting exists | `backend/app/rate_limiter.py`; `DatabaseSlidingWindowCounter` implements thread/process-safe sliding window counters using SQLite or Postgres | Verified, in-memory or shared DB-backed |
| Unauthenticated public LLM fallbacks are disabled by default | `settings.LLM_ENABLE_PUBLIC_FALLBACKS` defaults to `False`; tests verify disabled fallbacks do not issue unauthenticated Pollinations/g4f calls | Verified |
| Production env validator rejects placeholders | `.env.production.example` fails validation intentionally, including metrics token placeholder; production security tests pass | Verified |
| Docs disabled in production app config | `backend/app/main.py` disables `/docs`, `/redoc`, `/openapi.json` when `settings.ENV == "production"` | Verified by code inspection |
| Internal dashboard exists | `frontend/` static files and FastAPI static mounts | Verified, internal-only |
| Compose production files exist | `Dockerfile`, `docker-compose.prod.yml`, `nginx.conf`, Prometheus, Grafana files | Verified files exist |
| Docker image builds locally | Production smoke built image `796fe80630f771d4da8257eb7ec3f07a003f92f63d668ac1ffc3b43007ee9fc9` | Verified locally |
| Local production Compose smoke works | Temporary ignored `.env`, backend/worker/Postgres healthy, Nginx health/readiness/app routes checked, docs/OpenAPI/metrics blocked externally, Prometheus targets up, container Chromium launches, one worker job completed with four records | Verified locally, not target production |

## Fresh Validation Results

| Command | Result | What It Proves |
| --- | --- | --- |
| `python3 -m compileall -q backend scripts architecture_validator.py` | Passed with no output | Python syntax is valid for checked paths |
| `PYTHONPATH=backend python3 architecture_validator.py` | `VALIDATION PASSED: Architecture is lawful.` | Current architecture validator rules pass |
| `PYTHONPATH=backend DATAFORGE_DOTENV_PATH=/dev/null DATAFORGE_STORAGE_BACKEND=sqlite python3 -m pytest --collect-only -q backend/tests backend/benchmarks -o addopts=` | `1916 tests collected in 0.40s` | Test collection is clean |
| `PYTHONPATH=backend DATAFORGE_DOTENV_PATH=/dev/null DATAFORGE_STORAGE_BACKEND=sqlite python3 -m pytest -q backend/tests -o addopts=` | `1843 passed, 72 skipped, 0 failed` | Safe SQLite backend suite passes locally |
| `PYTHONPATH=backend DATAFORGE_DOTENV_PATH=/dev/null DATAFORGE_STORAGE_BACKEND=sqlite python3 -m pytest -q backend/benchmarks -o addopts=` | `1 passed in 0.26s` | Benchmark package smoke/config test passes — not a real benchmark |
| `PYTHONPATH=backend DATAFORGE_DOTENV_PATH=/dev/null DATAFORGE_STORAGE_BACKEND=sqlite python3 -m pytest -q backend/tests/test_route_auth_matrix.py backend/tests/test_route_auth_matrix_generator.py backend/tests/test_check_prod_env.py backend/tests/test_prod_security_validator.py backend/tests/test_production_hardening.py::test_backend_cors_origins_enforcement -o addopts=` | `183 passed in 1.83s` | Combined route-auth, production-security, and CORS preflight checks pass |
| `env -i PATH="$PATH" PYTHONPATH=backend DATAFORGE_SKIP_DB_CHECK=true python3 scripts/check_prod_env.py --env-file .env.production.example` | Failed intentionally on placeholder API keys, database password/URL, metrics token, operator/admin keys, and Grafana password | Production example is not deployable as-is |
| `PYTHONPATH=backend DATAFORGE_DOTENV_PATH=/dev/null DATAFORGE_STORAGE_BACKEND=postgres python3 -m pytest backend/tests --run-postgres -q -o addopts=` | `1885 passed, 28 skipped in 138.54s` | Postgres repository and queue tests pass locally |
| `PYTHONPATH=backend DATAFORGE_DOTENV_PATH=/dev/null DATAFORGE_STORAGE_BACKEND=sqlite python3 -m pytest backend/tests --run-browser -q -o addopts=` | `1858 passed, 55 skipped in 125.64s` | Browser/local-server tests pass locally |
| `bash scripts/smoke_prod_stack.sh` | Built image `796fe80630f771d4da8257eb7ec3f07a003f92f63d668ac1ffc3b43007ee9fc9`; all smoke tests passed | Local production-like stack works with generated ignored `.env` |
| Nginx smoke via `curl http://127.0.0.1:18080...` | `/health` 200, `/ready` 200, `/app/` 200, `/docs` 404, `/redoc` 404, `/openapi.json` 404, `/metrics` 404 | Public Nginx route behavior works locally |
| Container browser smoke | `docker exec dataforge-scraper ... playwright chromium ...` printed `chromium 148.0.7778.96` | Chromium launches in the built API container |
| Prometheus config and target check | `promtool check config /tmp/prometheus.yml` found 1 rule file and 5 rules; `dataforge` and `prometheus` targets were `up` with empty `lastError` | Prometheus config and internal scrape work locally |
| Grafana health | `docker exec dataforge-grafana wget -qO- http://localhost:3000/api/health` returned `database: ok`, version `11.0.0` | Grafana service is healthy locally |
| Worker smoke through Nginx | One local deterministic smoke-page job completed with 4 records | Worker, Postgres queue/storage, browser extraction path, and Nginx API routing work for a minimal local smoke case |
| CORS through Nginx | Allowed origin `https://yourdomain.com` returned `200` with `access-control-allow-origin`; disallowed origin returned `400` without allow-origin | Production CORS preflight path works locally |
| Postgres backup/restore smoke | `pg_dump` restored into a temporary database with 7 public tables | Basic local backup/restore path works |
| Request burst smoke | 60/60 health/readiness/authenticated status requests returned `200` | Basic local request burst works; not a load test |
| `PYTHONPATH=backend DATAFORGE_DOTENV_PATH=/dev/null DATAFORGE_STORAGE_BACKEND=sqlite python3 -m pytest backend/tests/test_golden_dataset.py --run-golden-dataset -q -s --tb=short -o addopts=` | `8 passed in 53.97s`; F1: books `0.650`, quotes `1.000`, countries `0.680`, example `1.000`, httpbin `1.000` | Live golden dataset now has enforced thresholds |

## Partially Verified

- Route authorization is mechanically documented and tested for registered FastAPI routes. This is not a penetration test.
- `/metrics` is protected when `DATAFORGE_METRICS_TOKEN` is configured. Local Compose verified Nginx blocks public `/metrics` and Prometheus scrapes the internal route with a bearer token.
- Browser extraction is validated against local tests, not against a broad real-world website corpus.
- Postgres repository and queue behavior is validated locally, including a minimal Compose worker smoke and a basic dump/restore drill. Failover and production backup operations are not validated.
- CSP headers are served by Nginx locally; browser-enforced production behavior was not validated against a real domain.
- LLM public fallback behavior is disabled by default. Enabling it is an explicit operator choice and should be reviewed for data leakage and service-dependency risk.

## Experimental Or Unvalidated

- Semantic world state, topology state, federation/gossip, strategy evolution beyond tested behavior, selector ML/decay, self-tuning extraction, replay buffers, chaos/failure injection, manifold/motif/energy/intent/acquisition/instability/domain evolution modules.
- Public target deployment, TLS, Grafana login/dashboard behavior, real load tests, failover, alert delivery, disaster recovery, and incident response.

## Current Blockers

1. The local Compose smoke used a temporary generated `.env`, not real production secrets or a public target environment.
2. Dashboard remains internal-only until session and hostile-browser risks are reviewed.
3. TLS, Grafana dashboard/login behavior, real load, failover, alert delivery, disaster recovery, and incident-response gates are unvalidated.
4. Benchmark suite is a single smoke test — no real benchmark assertions with precision/recall/F1 thresholds enforced.
5. Runtime artifacts (DB files, lock files, log files, semantic_state.json) are recreated during test runs and must be cleaned before commits. `.gitignore` blocks them from tracking, but they remain on disk.

## Allowed Current Claims

- Pre-production FastAPI + Playwright web extraction platform.
- Configurable jobs, browser-assisted extraction, structured extraction, storage, exports, diagnostics, and telemetry exist.
- SQLite local mode is tested.
- Postgres repository and queue tests pass locally with `--run-postgres`.
- Browser/local-server tests pass locally with `--run-browser`.
- Docker image build and a minimal local production Compose smoke pass from current source.
- Golden dataset live tests pass with enforced modest thresholds.
- Route-auth matrix tests and production secret validation tests pass locally.
- Docker/Nginx/Postgres/Prometheus/Grafana deployment files exist.
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

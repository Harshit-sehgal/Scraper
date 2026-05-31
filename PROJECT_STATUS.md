# Project Status - DataForge Scraper

**Last refreshed:** 2026-06-01T00:49:22+05:30
**Commit inspected:** `7fa1640130249ff504e0f2557e5e30c50cf25cb4`
**Branch inspected:** `main`
**Backup branch created before edits:** `backup-dataforge-truth-baseline-20260531-230634`
**Status:** Pre-production candidate
**Maturity:** about 72% as a pre-production platform, not production-ready

This file is the current truth source. It must be updated only from fresh code inspection and command output. Archived audit documents are historical context, not current evidence.

## Current Description

DataForge Scraper is a pre-production FastAPI + Playwright web extraction platform for accessible websites. It supports configurable scraping jobs, browser-assisted page loading, schema/selector/network/visible-text extraction paths, local SQLite storage, Postgres storage and queue code, result exports, telemetry, diagnostics, API-key/RBAC utilities, SSRF-oriented URL checks, rate limiting, audit logging, and an internal static dashboard.

It also contains experimental adaptive, semantic, topology, selector-memory, replay, and strategy-evolution modules. Those modules are not production-validated product capabilities unless listed as verified below.

## Verified Capabilities

| Claim | Evidence | Status |
| --- | --- | --- |
| FastAPI backend exists | `backend/app/main.py` defines the app, middleware, static mounts, health/readiness, metrics, and routers | Verified |
| Playwright browser path exists | `backend/app/browser.py`, `backend/app/scraper.py`, and browser tests exercise Chromium-backed extraction | Verified |
| Job APIs exist | `backend/app/routers/jobs.py` and route matrix list job lifecycle endpoints | Verified |
| Export APIs exist | `backend/app/routers/exports.py` exposes CSV/JSON/Excel export routes | Verified |
| SQLite local storage exists | `backend/app/storage_interface.py` and SQLite-backed tests | Verified |
| Postgres storage/queue code works locally | `1883 passed, 28 skipped in 129.55s` with `--run-postgres` | Verified locally |
| API key/RBAC utilities exist | `backend/app/utils/rbac.py`, route dependencies, route-auth tests | Verified |
| SSRF-oriented URL safety checks exist | `backend/app/url_safety.py` rejects non-http(s), loopback/private IPs, metadata hosts, and internal names | Verified by code inspection and tests |
| Rate limiting exists | `backend/app/rate_limiter.py`; route key bug not observed in current code | Verified, single-process only |
| Production env validator rejects placeholders | `.env.production.example` fails validation intentionally, including metrics token placeholder; production security tests pass | Verified |
| Docs disabled in production app config | `backend/app/main.py` disables `/docs`, `/redoc`, `/openapi.json` when `settings.ENV == "production"` | Verified by code inspection |
| Internal dashboard exists | `frontend/` static files and FastAPI static mounts | Verified, internal-only |
| Compose production files exist | `Dockerfile`, `docker-compose.prod.yml`, `nginx.conf`, Prometheus, Grafana files | Verified files exist |
| Docker image builds locally | `docker build -f Dockerfile -t dataforge:local .` built image `2d6822c8ca4f` | Verified locally |
| Local production Compose smoke works | Temporary ignored `.env`, backend/worker/Postgres healthy, Nginx health/readiness/app routes checked, docs/OpenAPI/metrics blocked externally, Prometheus targets up, container Chromium launches, one worker job completed with one record | Verified locally, not target production |

## Fresh Validation Results

| Command | Result | What It Proves |
| --- | --- | --- |
| `python3 -m compileall -q backend scripts architecture_validator.py` | Passed with no output | Python syntax is valid for checked paths |
| `PYTHONPATH=backend python3 architecture_validator.py` | `VALIDATION PASSED: Architecture is lawful.` | Current architecture validator rules pass |
| `PYTHONPATH=backend DATAFORGE_DOTENV_PATH=/dev/null DATAFORGE_STORAGE_BACKEND=sqlite python3 -m pytest --collect-only -q backend/tests backend/benchmarks -o addopts=` | `1912 tests collected in 0.41s` | Test collection is clean |
| `PYTHONPATH=backend DATAFORGE_DOTENV_PATH=/dev/null DATAFORGE_STORAGE_BACKEND=sqlite python3 -m pytest -q backend/tests -o addopts=` | `1839 passed, 72 skipped in 107.06s` | Safe SQLite backend suite passes locally |
| `PYTHONPATH=backend DATAFORGE_DOTENV_PATH=/dev/null DATAFORGE_STORAGE_BACKEND=sqlite python3 -m pytest -q backend/benchmarks -o addopts=` | `1 passed in 0.27s` | Benchmark package smoke/config test passes |
| `PYTHONPATH=backend DATAFORGE_DOTENV_PATH=/dev/null DATAFORGE_STORAGE_BACKEND=sqlite python3 -m pytest -q backend/tests/test_route_auth_matrix.py backend/tests/test_route_auth_matrix_generator.py -o addopts=` | `134 passed in 1.25s` | Route-auth matrix tests pass |
| `PYTHONPATH=backend DATAFORGE_DOTENV_PATH=/dev/null DATAFORGE_STORAGE_BACKEND=sqlite python3 -m pytest -q backend/tests/test_check_prod_env.py backend/tests/test_prod_security_validator.py -o addopts=` | `48 passed in 0.09s` | Production secret validation tests pass |
| `PYTHONPATH=backend DATAFORGE_DOTENV_PATH=/dev/null DATAFORGE_STORAGE_BACKEND=sqlite python3 -m pytest -q backend/tests/test_route_auth_matrix.py backend/tests/test_route_auth_matrix_generator.py backend/tests/test_check_prod_env.py backend/tests/test_prod_security_validator.py -o addopts=` | `182 passed in 1.31s` | Combined route-auth and production-security checks pass |
| `env -i PATH="$PATH" PYTHONPATH=backend DATAFORGE_SKIP_DB_CHECK=true python3 scripts/check_prod_env.py --env-file .env.production.example` | Failed intentionally on placeholder API keys, database password/URL, metrics token, operator/admin keys, and Grafana password | Production example is not deployable as-is |
| `PYTHONPATH=backend DATAFORGE_DOTENV_PATH=/dev/null DATAFORGE_STORAGE_BACKEND=postgres python3 -m pytest backend/tests --run-postgres -q -o addopts=` | `1883 passed, 28 skipped in 129.55s` | Postgres repository and queue tests pass locally with Docker/testcontainers |
| `PYTHONPATH=backend DATAFORGE_DOTENV_PATH=/dev/null DATAFORGE_STORAGE_BACKEND=sqlite python3 -m pytest backend/tests --run-browser -q -o addopts=` | `1856 passed, 55 skipped in 116.73s` | Browser/local-server tests pass locally |
| `docker build -f Dockerfile -t dataforge:local .` | Successfully built `2d6822c8ca4f` and tagged `dataforge:local` | Docker image builds locally |
| `./bin/docker-compose -f docker-compose.prod.yml up -d --build dataforge worker nginx prometheus` with a temporary ignored `.env` | Backend and worker healthy; Postgres healthy; Nginx, Prometheus, and Grafana running | Local Compose startup works in this environment |
| Nginx smoke via `curl http://127.0.0.1:18080...` | `/health` 200, `/ready` 200, `/app/` 200, `/docs` 404, `/redoc` 404, `/openapi.json` 404, `/metrics` 404 | Public Nginx route behavior works locally |
| Container browser smoke | `docker exec dataforge-scraper ... playwright chromium ...` printed `ok` | Chromium launches in the built API container |
| Prometheus target check | `dataforge up '' http://dataforge:8000/metrics`; `prometheus up '' http://localhost:9090/metrics` | Prometheus scrapes internal metrics with the configured bearer token |
| Worker smoke through Nginx | One `https://example.com` manual job completed with `total_records: 1`, `error: null`, `quality_final_records: 1` | Worker, Postgres queue/storage, browser extraction path, and Nginx API routing work for a minimal local smoke case |
| `python3 -m pytest backend/tests/test_golden_dataset.py --run-golden-dataset -q -o addopts=` | Stopped after one visible test and several minutes with no progress | Live golden dataset run is not validated in this pass |

## Partially Verified

- Route authorization is mechanically documented and tested for registered FastAPI routes. This is not a penetration test.
- `/metrics` is protected when `DATAFORGE_METRICS_TOKEN` is configured. Local Compose verified Nginx blocks public `/metrics` and Prometheus scrapes the internal route with a bearer token.
- Browser extraction is validated against local tests, not against a broad real-world website corpus.
- Postgres repository and queue behavior is validated locally, including a minimal Compose worker smoke. Failover, backup, restore, and load behavior are not validated.
- CSP headers are served by Nginx locally; browser-enforced production behavior was not validated against a real domain.

## Experimental Or Unvalidated

- Semantic world state, topology state, federation/gossip, strategy evolution beyond tested behavior, selector ML/decay, self-tuning extraction, replay buffers, chaos/failure injection, manifold/motif/energy/intent/acquisition/instability/domain evolution modules.
- Golden dataset live accuracy. Expected files exist, but thresholds are not enforced and the live run did not complete.
- Public target deployment, TLS, Grafana login/dashboard behavior, backups, load tests, failover, alert delivery, disaster recovery, and incident response.

## Current Blockers

1. The local Compose smoke used a temporary generated `.env`, not real production secrets or a public target environment.
2. Live golden dataset validation timed out/stalled and does not prove extraction accuracy.
3. Dashboard remains internal-only until session and hostile-browser risks are reviewed.
4. Rate limiting is in-memory and single-process only.
5. TLS, Grafana dashboard/login behavior, production backup/restore, load, alert delivery, disaster recovery, and incident-response gates are unvalidated.

## Allowed Current Claims

- Pre-production FastAPI + Playwright web extraction platform.
- Configurable jobs, browser-assisted extraction, structured extraction, storage, exports, diagnostics, and telemetry exist.
- SQLite local mode is tested.
- Postgres repository and queue tests pass locally with `--run-postgres`.
- Browser/local-server tests pass locally with `--run-browser`.
- Docker image build and a minimal local production Compose smoke pass.
- Route-auth matrix tests and production secret validation tests pass locally.
- Docker/Nginx/Postgres/Prometheus/Grafana deployment files exist.
- Experimental adaptive/semantic modules exist but are not production-validated.

## Banned Claims

Do not claim production-ready, enterprise-grade, universal scraper, scrapes every website, bypasses all anti-bot systems, anti-bot immune, fully autonomous, fully self-healing, guaranteed extraction, 100% accurate, complete, fully benchmarked, zero bugs, or production security without new evidence.

## Next Actions

1. Create a real uncommitted production `.env` for the target environment and rerun the production checks there.
2. Add timeout controls and enforced thresholds to golden dataset tests.
3. Add production-mode dashboard/CSP checks against a browser and real origin.
4. Add backup/restore, load, alert delivery, and recovery validation.

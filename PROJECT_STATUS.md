# Project Status - DataForge Scraper

**Date:** 2026-05-31 (cleanup pass)
**Classification:** Current truth-first status report
**Project status:** Pre-production candidate
**Overall maturity:** ~65% as a pre-production platform (Postgres + browser E2E validated, benchmark naming corrected, stale docs archived)

This document is an active status snapshot. It must be updated from fresh file inspection
and command output. Older audit notes and archive documents are historical context only.

## Current Truth Snapshot

DataForge Scraper is a FastAPI and Playwright web extraction backend with job APIs,
storage code, export endpoints, telemetry, security utilities, and an internal static
dashboard. It also contains adaptive, semantic, and benchmark modules that need careful
validation before they are described as product capabilities.

The project should not be described as production-ready, universal, fully autonomous,
self-healing, anti-bot immune, or guaranteed accurate.

## Verified In Current Cleanup Pass

- Verified: production environment validation now rejects generated placeholder secrets
  such as `CHANGE_ME_GENERATE_STRONG_*` and `replace_this_*`.
- Verified: production environment validation now rejects reused user/operator/admin API
  keys.
- Verified: `.env.production.example` contains placeholders instead of generated-looking
  secrets and intentionally fails production validation until real values are supplied.
- Verified: route-auth matrix tooling exists at `scripts/route_auth_matrix.py`.
- Verified: the generated route-auth matrix currently reports 81 registered route
  entries:
  - 47 authenticated-user routes
  - 15 operator-or-admin routes
  - 11 admin routes
  - 4 development-docs routes
  - 3 public routes
  - 1 metrics route protected only when `DATAFORGE_METRICS_TOKEN` is configured
- Verified: generated route-auth tests passed:

  ```bash
  PYTHONPATH=backend DATAFORGE_DOTENV_PATH=/dev/null DATAFORGE_STORAGE_BACKEND=sqlite \
    python3 -m pytest -q backend/tests/test_route_auth_matrix.py \
    backend/tests/test_route_auth_matrix_generator.py -o addopts= -p no:cacheprovider
  # 134 passed in 1.88s
  ```

- Verified: production secret validation tests passed:

  ```bash
  PYTHONPATH=backend DATAFORGE_DOTENV_PATH=/dev/null DATAFORGE_STORAGE_BACKEND=sqlite \
    python3 -m pytest -q backend/tests/test_check_prod_env.py \
    backend/tests/test_prod_security_validator.py -o addopts= -p no:cacheprovider
  # 48 passed in 0.08s
  ```

- Verified: touched Python files compiled successfully:

  ```bash
  python3 -m py_compile scripts/route_auth_matrix.py scripts/check_prod_env.py \
    backend/app/utils/prod_security_validator.py backend/app/routers/scraper.py \
    backend/tests/test_route_auth_matrix_generator.py
  ```

- Verified: repository test collection is currently clean for tests and benchmarks:

  ```bash
  PYTHONPATH=backend DATAFORGE_DOTENV_PATH=/dev/null DATAFORGE_STORAGE_BACKEND=sqlite \
    python3 -m pytest --collect-only -q backend/tests backend/benchmarks -o addopts= -p no:cacheprovider
  # 1910 tests collected in 0.41s
  ```

- Verified: benchmark pytest entry point no longer errors during default execution:

  ```bash
  PYTHONPATH=backend DATAFORGE_DOTENV_PATH=/dev/null DATAFORGE_STORAGE_BACKEND=sqlite \
    python3 -m pytest -q backend/benchmarks -o addopts= -p no:cacheprovider
  # 1 passed in 0.36s
  ```

- Verified: full default backend pytest suite currently passes with SQLite when optional
  browser/local-server, golden dataset, and Postgres tests are skipped by default:

  ```bash
  PYTHONPATH=backend DATAFORGE_DOTENV_PATH=/dev/null DATAFORGE_STORAGE_BACKEND=sqlite \
    python3 -m pytest -q backend/tests -o addopts= -p no:cacheprovider
  # 1837 passed, 72 skipped in 105.19s
  ```

- Verified: Postgres test suite passes with a live Postgres service:

  ```bash
  docker run --rm -d --name df-postgres \
    -e POSTGRES_USER=dataforge -e POSTGRES_PASSWORD=test -e POSTGRES_DB=dataforge \
    -p 5432:5432 postgres:16-alpine
  # Create test user expected by conftest.py
  docker exec df-postgres psql -U dataforge \
    -c "CREATE USER testuser WITH PASSWORD 'testpassword' CREATEDB;"
  docker exec df-postgres psql -U dataforge \
    -c "CREATE DATABASE testdb OWNER testuser;"

  PYTHONPATH=backend DATAFORGE_DATABASE_URL=postgresql://dataforge:test@localhost:5432/dataforge \
    DATAFORGE_STORAGE_BACKEND=postgres \
    python3 -m pytest -q backend/tests --run-postgres -o addopts= -p no:cacheprovider
  # 1881 passed, 28 skipped in 119.73s
  ```

- Verified: browser E2E tests pass with Playwright + Chromium:

  ```bash
  PYTHONPATH=backend DATAFORGE_DOTENV_PATH=/dev/null DATAFORGE_STORAGE_BACKEND=sqlite \
    python3 -m pytest -q backend/tests/test_playwright_browser_e2e.py \
    backend/tests/test_session_bound_e2e.py --run-browser -o addopts= -p no:cacheprovider
  # 39 passed in 10.76s
  ```

## Partially Verified

- Partially verified: route-level authorization is now mechanically documented and tested
  for registered routes. This is not a penetration test and does not prove complete
  security.
- Partially verified: production secret validation has stronger placeholder and duplicate
  key detection. It still depends on operators supplying strong secrets outside source
  control.
- Partially verified: `/metrics` has optional token protection. It is unsafe to expose
  publicly unless `DATAFORGE_METRICS_TOKEN` and network controls are configured.
- Partially verified: FastAPI docs routes are classified as development-docs routes.
  Production deployment must disable or block them.

## Implemented But Unvalidated

- Implemented but unvalidated: Docker Compose stack with Nginx, Prometheus, and Grafana
  files exist, but this status snapshot does not verify that the full production stack
  starts end to end.
- Implemented but unvalidated: adaptive, semantic, topology, and recovery modules exist.
  They must remain experimental until real-world behavior and failure modes are measured.

## Now Validated

- Validated: Postgres storage and queue backend with 1881 passing tests against a live
  Postgres 16 service. Postgres tests require `--run-postgres` and a running database.
- Validated: Playwright + Chromium browser E2E tests with 39 passing tests against
  local mock web servers. Browser tests require `--run-browser`.
- Validated: Route auth matrix with 134 passing tests covering 81 registered routes.
- Validated: Production secret validation with 48 passing tests rejecting placeholders.## Simulated Or Fixture-Based

- Simulated: hostile, longevity, replay, and similar benchmark scripts (`benchmark_*.py`)
use fixtures or generated conditions unless explicitly run against a documented live
dataset.
- Partially verified: golden dataset has `sites.json` (5 targets) and `expected/` output
files. These are **observational tests** (log F1 but do not fail on mismatch). They do
not prove real-world extraction accuracy until validated against live targets.## Unknown In This Snapshot

- Unknown: Docker Compose production stack startup with Nginx, Prometheus, and Grafana.
- Unknown: Nginx proxy and reverse-proxy behavior.
- Unknown: dashboard behavior under a browser-enforced production CSP.
- Unknown: live extraction accuracy against a real golden dataset.
- Unknown: anti-bot effectiveness against real anti-bot systems.
- Unknown: failure-recovery, load-testing, and backup/restore procedures.

## Known Blockers Before Production

1. Production deployment is not validated end to end.
2. Post-cleanup safe local test baseline exists, but CI must reproduce it from a fresh
   checkout before treating it as release evidence.
3. Postgres is validated locally (1881 passing tests), but worker queue + migration
   behavior in a deployed environment needs service validation.
4. Dashboard authentication/session handling is not suitable for public hostile-browser
   environments.
5. Metrics and docs routes need verified production exposure controls.
6. CORS, CSP, API docs, rate limits, and route authorization need a production-mode smoke
   test.
7. Real-world benchmark data with expected outputs is required before making accuracy
   claims.
8. Docker Compose production stack (Nginx, Prometheus, Grafana) needs smoke-test validation.

## Allowed Current Claims

- DataForge Scraper is a pre-production FastAPI and Playwright web extraction platform.
- It has job APIs, extraction modules, storage code, exports, telemetry, diagnostics, and
  security utilities.
- It supports local SQLite mode and Postgres backend (validated with 1881 passing tests).
- It includes validated Playwright + Chromium browser E2E tests (39 passing tests).
- Route authorization is mechanically documented by a generated matrix (134 passing tests).
- It includes an internal dashboard.
- It includes experimental adaptive and semantic modules.
- Benchmark package has 1 honest pytest collection check; 3 standalone benchmark scripts
  are named `benchmark_*.py` (not falsely collected as tests).
- Runtime artifacts (logs, DBs, lock files) have been removed from disk.
- 15 stale audit documents have been archived to `docs/archive/`.

## Banned Claims

- Production-ready
- Enterprise-grade
- Universal scraper
- Works on every website
- Fully autonomous
- Fully self-healing
- Anti-bot immune
- Guaranteed accurate
- 100% complete
- All tests pass, unless followed by the exact fresh command and output

## Production Readiness Checklist

See **[docs/PRODUCTION_READINESS.md](docs/PRODUCTION_READINESS.md)** for the complete gate-by-gate checklist (secrets, deployment, health, security, database, dashboard, monitoring, extraction, operations) that must pass before the project can be described as production-ready.

## Reproducible Commands

Use these commands to regenerate the current status before updating this file:

```bash
python3 -m compileall -q backend scripts architecture_validator.py

PYTHONPATH=backend DATAFORGE_DOTENV_PATH=/dev/null DATAFORGE_STORAGE_BACKEND=sqlite \
  python3 -m pytest --collect-only -q backend/tests backend/benchmarks -o addopts=

PYTHONPATH=backend DATAFORGE_DOTENV_PATH=/dev/null DATAFORGE_STORAGE_BACKEND=sqlite \
  python3 -m pytest -q backend/tests -o addopts=

PYTHONPATH=backend DATAFORGE_DOTENV_PATH=/dev/null DATAFORGE_STORAGE_BACKEND=sqlite \
  python3 -m pytest -q backend/benchmarks -o addopts=

PYTHONPATH=backend DATAFORGE_DOTENV_PATH=/dev/null DATAFORGE_STORAGE_BACKEND=sqlite \
  python3 scripts/route_auth_matrix.py --format markdown

env -i PATH="$PATH" PYTHONPATH=backend DATAFORGE_SKIP_DB_CHECK=true \
  python3 scripts/check_prod_env.py --env-file .env.production.example

# Postgres tests (requires running Postgres container + testuser/testdb):
PYTHONPATH=backend DATAFORGE_DATABASE_URL=postgresql://dataforge:test@localhost:5432/dataforge \
  DATAFORGE_STORAGE_BACKEND=postgres \
  python3 -m pytest -q backend/tests --run-postgres -o addopts=

# Browser E2E tests (requires Playwright + Chromium installed):
PYTHONPATH=backend DATAFORGE_DOTENV_PATH=/dev/null DATAFORGE_STORAGE_BACKEND=sqlite \
  python3 -m pytest -q backend/tests/test_playwright_browser_e2e.py \
  backend/tests/test_session_bound_e2e.py --run-browser -o addopts=
```

The `.env.production.example` validation command is expected to fail because the file
contains placeholders. A passing production check requires real strong secrets supplied
outside the repository.

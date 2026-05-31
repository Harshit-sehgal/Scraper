# DataForge Scraper

DataForge Scraper is a pre-production web extraction platform built with FastAPI
and Playwright. It is designed to run configurable scraping jobs, extract structured
records from accessible web pages, store results, export data, and expose telemetry
and diagnostics.

It is not a universal scraper and it is not production-ready without further
validation.

## What It Does

- Creates, lists, cancels, recleans, deletes, restores, and exports scraping jobs.
- Uses browser-assisted extraction for pages that need rendering.
- Supports schema and selector-based extraction with validation and fallback paths.
- Stores job state and results using local SQLite by default, with Postgres-related
  code available for configured deployments.
- Exports job results as CSV, JSON, and Excel.
- Exposes health, readiness, metrics, telemetry, and diagnostic endpoints.
- Provides API-key authentication, RBAC utilities, SSRF-oriented URL checks, and
  production environment validation.
- Includes a static internal dashboard.
- Includes experimental adaptive, semantic, topology, selector-memory, replay, and
  strategy-evolution modules.

## What It Does Not Do

- It does not work on every website.
- It does not bypass all anti-bot systems.
- It does not guarantee extraction accuracy.
- It does not provide public-production security out of the box.
- It does not prove real-world benchmark accuracy yet.
- It does not provide validated autonomous self-healing.

## Current Status

Status: pre-production candidate.

Current verified snapshot, generated on 2026-05-31:

| Area | Current evidence |
| --- | --- |
| Python syntax | `python3 -m compileall -q backend scripts architecture_validator.py` passed |
| Pytest collection | `1910 tests collected in 0.41s` for `backend/tests backend/benchmarks` |
| Route auth matrix | Generated from registered FastAPI routes; 81 route entries |
| Route auth tests | `134 passed in 1.88s` for route-auth matrix tests |
| Production secret tests | `48 passed in 0.08s` for production secret validation tests |
| Benchmarks package | `1 passed in 0.36s`; this is an import/configuration check, not a live benchmark |
| Architecture validator | `VALIDATION PASSED: Architecture is lawful.` |
| Full default backend test run | `1837 passed, 72 skipped in 105.19s` with SQLite and optional browser/golden/Postgres groups skipped |
| Docker/Postgres/Nginx stack | Unknown in this snapshot; not validated here |

See [PROJECT_STATUS.md](PROJECT_STATUS.md) for the current truth table.

## Quick Start

```bash
cp .env.example .env
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

Start the API from the repository root:

```bash
PYTHONPATH=backend DATAFORGE_STORAGE_BACKEND=sqlite uvicorn app.main:app --reload
```

Smoke check:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
```

Most `/api/*` routes require an API key once keys are configured.

## Validation Commands

Use explicit local settings so `.env` does not accidentally force Postgres during
local checks:

```bash
python3 -m compileall -q backend scripts architecture_validator.py
```

```bash
PYTHONPATH=backend DATAFORGE_DOTENV_PATH=/dev/null DATAFORGE_STORAGE_BACKEND=sqlite \
  python3 -m pytest --collect-only -q backend/tests backend/benchmarks -o addopts=
```

```bash
PYTHONPATH=backend DATAFORGE_DOTENV_PATH=/dev/null DATAFORGE_STORAGE_BACKEND=sqlite \
  python3 -m pytest -q backend/tests -o addopts=
```

```bash
PYTHONPATH=backend DATAFORGE_DOTENV_PATH=/dev/null DATAFORGE_STORAGE_BACKEND=sqlite \
  python3 -m pytest -q backend/benchmarks -o addopts=
```

```bash
PYTHONPATH=backend DATAFORGE_DOTENV_PATH=/dev/null DATAFORGE_STORAGE_BACKEND=sqlite \
  python3 scripts/route_auth_matrix.py --format markdown
```

Production template validation is expected to fail until placeholders are replaced:

```bash
env -i PATH="$PATH" PYTHONPATH=backend DATAFORGE_SKIP_DB_CHECK=true \
  python3 scripts/check_prod_env.py --env-file .env.production.example
```

## Project Structure

```text
backend/
  app/
    main.py                         FastAPI app, middleware, health/readiness/metrics
    routers/                        API routers
    services/                       job and background service helpers
    utils/                          auth, export, validation, security utilities
    scraper.py                      scraping entry points
    extraction_orchestrator.py      extraction coordination
    storage_interface.py            storage backend selection
    worker_queue.py                 local worker queue
    worker_queue_postgres.py        Postgres-backed queue code
  tests/                            pytest suite
  benchmarks/                       benchmark scripts and lightweight pytest checks
frontend/                           static internal dashboard
docs/                               current and historical documentation
scripts/                            validation and operational helper scripts
```

## Production Warning

Do not deploy this publicly without completing production validation:

- Generate strong, unique user/operator/admin API keys.
- Replace all placeholders in `.env.production.example` outside source control.
- Validate Postgres, worker queue, migrations/init, and storage behavior.
- Validate Docker image build and production Compose startup.
- Verify Nginx routing, CSP, CORS, docs exposure, metrics exposure, health, and
  readiness in production mode.
- Treat the dashboard as internal-only until session handling and hostile-browser
  risks are addressed.
- Run a real route authorization matrix test against the deployed environment.
- Add real-world benchmark datasets with expected outputs before making accuracy
  claims.

## Documentation

- [PROJECT_STATUS.md](PROJECT_STATUS.md) - current truth-first status snapshot
- [docs/ROUTE_AUTH_MATRIX.md](docs/ROUTE_AUTH_MATRIX.md) - generated route authorization evidence
- [docs/SECURITY.md](docs/SECURITY.md) - current security posture and limitations
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) - architecture overview
- [docs/LIMITATIONS.md](docs/LIMITATIONS.md) - known limitations
- [docs/PRODUCTION.md](docs/PRODUCTION.md) - production readiness notes
- [docs/BENCHMARKS.md](docs/BENCHMARKS.md) - benchmark scope and limitations

Archived docs are historical unless they explicitly say they are current.

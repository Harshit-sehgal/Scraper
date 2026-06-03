# DataForge Scraper

DataForge Scraper is a pre-production FastAPI + Playwright web extraction platform for accessible websites. It provides configurable scraping jobs, browser-assisted loading, schema/selector-based extraction paths, result storage, exports, diagnostics, telemetry, API-key/RBAC utilities, SSRF-oriented URL checks, rate limiting, and an internal static dashboard.

Do not claim this project is a universal scraper, anti-bot proof, fully autonomous, or production-ready without the deployment gates in `docs/PRODUCTION_READINESS.md`.

## What It Does

- Creates, lists, cancels, recleans, deletes, restores, and exports scraping jobs.
- Uses Playwright-backed browser extraction when JavaScript rendering is needed.
- Supports schema fields, selectors, network payload extraction, visible-text fallback, cleaning, and validation utilities.
- Uses SQLite for local storage by default and includes Postgres repository/queue code.
- Exports results as CSV, JSON, and Excel.
- Exposes health, readiness, metrics, diagnostics, telemetry, and route-auth tooling.
- Provides API-key authentication helpers, RBAC route dependencies, SSRF-oriented URL safety checks, rate limiting, audit logging, and production environment validation.
- Includes a static internal dashboard.
- Includes adaptive, semantic, topology, selector-memory, replay, and strategy-evolution modules that are experimental unless a specific test result says otherwise.

## What It Does Not Do

- It does not work on every website.
- It does not bypass all anti-bot systems.
- It does not guarantee extraction accuracy.
- It does not prove public-production security.
- It does not prove real-world benchmark accuracy yet.
- It does not provide validated autonomous self-healing.

## Current Status

Status: pre-production candidate.

| Gate | Status |
|------|--------|
| Ruff lint | ✅ 0 errors |
| Mypy | ✅ 0 errors (349 files, `--check-untyped-defs`) |
| Tests (SQLite) | ✅ 1970 passed, 73 skipped, 0 RuntimeWarnings |
| Compile | ✅ Clean |

For the latest verified status, including exact compile results, collected/passed test counts (SQLite, Postgres, Playwright browser, and Golden Dataset live extraction), and other detailed validation evidence, see [PROJECT_STATUS.md](PROJECT_STATUS.md).

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

Most `/api/*` routes require an API key once keys are configured. Development mode with no configured keys is permissive and must not be treated as a production security model.

## Validation Commands

Use explicit local settings so `.env` does not accidentally change the result:

```bash
python3 -m compileall -q backend scripts architecture_validator.py
PYTHONPATH=backend python3 architecture_validator.py
PYTHONPATH=backend DATAFORGE_DOTENV_PATH=/dev/null DATAFORGE_STORAGE_BACKEND=sqlite python3 -m pytest --collect-only -q backend/tests backend/benchmarks -o addopts=
PYTHONPATH=backend DATAFORGE_DOTENV_PATH=/dev/null DATAFORGE_STORAGE_BACKEND=sqlite python3 -m pytest -q backend/tests -o addopts=
PYTHONPATH=backend DATAFORGE_DOTENV_PATH=/dev/null DATAFORGE_STORAGE_BACKEND=sqlite python3 -m pytest -q backend/benchmarks -o addopts=
PYTHONPATH=backend DATAFORGE_DOTENV_PATH=/dev/null DATAFORGE_STORAGE_BACKEND=sqlite python3 scripts/route_auth_matrix.py --format markdown
env -i PATH="$PATH" PYTHONPATH=backend DATAFORGE_SKIP_DB_CHECK=true python3 scripts/check_prod_env.py --env-file .env.production.example
```

Optional checks:

```bash
PYTHONPATH=backend DATAFORGE_DOTENV_PATH=/dev/null DATAFORGE_STORAGE_BACKEND=postgres python3 -m pytest backend/tests --run-postgres -q -o addopts=
PYTHONPATH=backend DATAFORGE_DOTENV_PATH=/dev/null DATAFORGE_STORAGE_BACKEND=sqlite python3 -m pytest backend/tests --run-browser -q -o addopts=
PYTHONPATH=backend DATAFORGE_DOTENV_PATH=/dev/null DATAFORGE_STORAGE_BACKEND=sqlite python3 -m pytest backend/tests/test_golden_dataset.py --run-golden-dataset -q -o addopts=
```

## Project Structure

```text
backend/
  app/
    main.py                         FastAPI app, middleware, health/readiness/metrics
    routers/                        API routers for jobs, exports, scraper, operator
    services/                       job and background service helpers
    utils/                          auth, export, validation, security utilities
    scraper.py                      scraping orchestration
    extraction_orchestrator.py      extraction coordination and fallbacks
    storage_interface.py            SQLite/Postgres storage selection
    worker_queue.py                 local worker queue
    worker_queue_postgres.py        Postgres-backed queue code
  tests/                            automated pytest suite plus manual scripts
  benchmarks/                       pytest smoke check and standalone benchmark scripts
frontend/                           static internal dashboard
docs/                               current and archived documentation
scripts/                            operational and validation helpers
```

## Production Warning

Do not deploy publicly until the production checklist is validated in the target environment:

- Generate strong, unique user/operator/admin API keys outside source control.
- Replace every placeholder in `.env.production.example`.
- Re-validate Docker image build, production Compose startup, Postgres, worker queue, browser behavior inside the image, Nginx routing, docs exposure, metrics exposure, CORS, CSP, health, readiness, persistence, backup/restore, monitoring alerts, and load behavior in the target environment.
- Treat the dashboard as internal-only until session handling and hostile-browser risks are reviewed.
- Add real benchmark thresholds before making extraction accuracy claims.

## Documentation

- `PROJECT_STATUS.md` - current truth source
- `docs/ARCHITECTURE.md` - actual architecture map
- `docs/API.md` - manually verified route summary
- `docs/SECURITY.md` - security posture and remaining risks
- `docs/LIMITATIONS.md` - known limitations
- `docs/TESTING.md` - test commands and what they prove
- `docs/BENCHMARKS.md` - benchmark truth and gaps
- `docs/PRODUCTION.md` - production deployment notes
- `docs/PRODUCTION_READINESS.md` - gate checklist
- `docs/MODULE_CLASSIFICATION.md` - core/stable/experimental classification

Archived docs under `docs/archive/` are historical unless explicitly refreshed.

## Banned Overclaims

Do not claim this project is production-ready, enterprise-grade, universal, anti-bot immune, fully autonomous, fully self-healing, 100% accurate, guaranteed, complete, or fully benchmarked unless future evidence explicitly validates that claim.

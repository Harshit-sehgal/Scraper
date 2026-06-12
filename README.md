# DataForge Scraper

> Current agent truth source: [`docs/AGENT_TRUTH.md`](docs/AGENT_TRUTH.md). Treat older status and roadmap claims as historical unless reproduced by fresh command output.

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
| Quick validation | Passes with `python3 scripts/validate_local.py --quick` |
| Full backend tests | Currently failing; see `docs/AGENT_TRUTH.md` |
| Ruff / pyflakes / mypy | Currently failing; see `docs/AGENT_TRUTH.md` |
| Frontend tests | Passing in the latest full validation run |
| Frontend lint | Currently failing on `frontend/styles.css` formatting |
| Security scan | Bandit passes; pip-audit currently reports vulnerable installed packages |

For the latest verified status, use [`docs/AGENT_TRUTH.md`](docs/AGENT_TRUTH.md) and [`artifacts/validation/latest_summary.md`](artifacts/validation/latest_summary.md). Treat older status files as historical until their claims reproduce in the current checkout.

## API and Dashboard Notes

### API Payload Optimization
To keep polling overhead and network transfer light, `/api/jobs` (and `/api/recycle_bin`) return a summary DTO. For detailed job configurations, logs, or results, query `/api/jobs/{job_id}`, `/api/jobs/{job_id}/results`, or the export endpoints.

### API Security & Development Mode
In development mode (`DATAFORGE_ENV=development`), unauthenticated calls are rejected by default. To enable silent bypass/escalation to `ADMIN` for local testing when API keys are empty, you must explicitly set `DATAFORGE_ALLOW_INSECURE_DEV_AUTH=true`.

### Internal-Only Static Dashboard
The static dashboard is strictly **internal-only** and is not mounted in production (`DATAFORGE_ENV=production`) to reduce the attack surface. In production, serve the frontend assets via Nginx/CDN with explicit network ACLs and/or reverse-proxy level auth.

## Quick Start

```bash
cp .env.example .env
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
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

Use the local validation runner. It sets safe test defaults, applies
timeouts, redacts secrets from logs, and writes evidence under
`artifacts/validation/`:

```bash
python3 scripts/validate_local.py --quick
python3 scripts/validate_local.py --full
python3 scripts/validate_local.py --backend
python3 scripts/validate_local.py --frontend
python3 scripts/validate_local.py --security
```

Makefile shortcuts:

```bash
make validate
make validate-full
make validate-backend
make validate-frontend
make validate-security
```

See [`docs/VALIDATION.md`](docs/VALIDATION.md) for setup,
interpretation, stable checks, and opt-in experimental checks.

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

- `docs/AGENT_TRUTH.md` - current command-evidence truth source
- `docs/VALIDATION.md` - reproducible validation commands and log locations
- `PROJECT_STATUS.md` - historical status unless refreshed by current command output
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

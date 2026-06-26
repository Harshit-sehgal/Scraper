# DataForge Scraper

[![CI](https://github.com/Harshit-sehgal/Scraper/actions/workflows/ci.yml/badge.svg)](https://github.com/Harshit-sehgal/Scraper/actions/workflows/ci.yml)
[![Auto-Fix Formatting](https://github.com/Harshit-sehgal/Scraper/actions/workflows/auto-fix.yml/badge.svg)](https://github.com/Harshit-sehgal/Scraper/actions/workflows/auto-fix.yml)
[![Dependabot](https://img.shields.io/badge/Dependabot-enabled-0366d6?logo=dependabot)](https://github.com/Harshit-sehgal/Scraper/network/dependencies)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-blue?logo=python)](https://www.python.org/downloads/release/python-3120/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> Current agent truth source: [`docs/AGENT_TRUTH.md`](docs/AGENT_TRUTH.md). Treat older status and roadmap claims as historical unless reproduced by fresh command output.

DataForge Scraper is a pre-production FastAPI + Playwright web extraction platform for accessible websites. It provides configurable scraping jobs, browser-assisted loading, schema/selector-based extraction paths, result storage, exports, diagnostics, telemetry, API-key/RBAC utilities, SSRF-oriented URL checks, rate limiting, and an internal static dashboard.

Do not claim this project is a universal scraper, anti-bot proof, fully autonomous, or production-ready — confirm against `python3 scripts/validate_local.py --quick` (the existing deployment gate).

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

| Gate | CI Status |
|------|-----------|
| **Fast Gates** (syntax, architecture, invariants, security audit) | [![Fast Gates](https://github.com/Harshit-sehgal/Scraper/actions/workflows/ci.yml/badge.svg?job=fast-gates)](https://github.com/Harshit-sehgal/Scraper/actions/workflows/ci.yml) |
| **Static Analysis** (ruff, mypy, bandit, pyflakes) | [![Static Analysis](https://github.com/Harshit-sehgal/Scraper/actions/workflows/ci.yml/badge.svg?job=static-analysis)](https://github.com/Harshit-sehgal/Scraper/actions/workflows/ci.yml) |
| **Backend Tests** (+ coverage) | [![Backend Tests](https://github.com/Harshit-sehgal/Scraper/actions/workflows/ci.yml/badge.svg?job=backend-tests)](https://github.com/Harshit-sehgal/Scraper/actions/workflows/ci.yml) |
| **Frontend** (vitest, stylelint, Prettier) | [![Frontend](https://github.com/Harshit-sehgal/Scraper/actions/workflows/ci.yml/badge.svg?job=frontend)](https://github.com/Harshit-sehgal/Scraper/actions/workflows/ci.yml) |
| **Chaos Engineering** | [![Chaos Engineering](https://github.com/Harshit-sehgal/Scraper/actions/workflows/ci.yml/badge.svg?job=chaos-engineering)](https://github.com/Harshit-sehgal/Scraper/actions/workflows/ci.yml) |
| **Docker Image Build & Smoke** | [![Image Build](https://github.com/Harshit-sehgal/Scraper/actions/workflows/ci.yml/badge.svg?job=image-build)](https://github.com/Harshit-sehgal/Scraper/actions/workflows/ci.yml) |
| **SBOM Generation** | [![SBOM](https://github.com/Harshit-sehgal/Scraper/actions/workflows/ci.yml/badge.svg?job=sbom)](https://github.com/Harshit-sehgal/Scraper/actions/workflows/ci.yml) |
| **Dependabot** (auto-merge safe updates) | [![Dependabot](https://github.com/Harshit-sehgal/Scraper/actions/workflows/dependabot-auto-merge.yml/badge.svg)](https://github.com/Harshit-sehgal/Scraper/actions/workflows/dependabot-auto-merge.yml) |
| **Postgres Integration** | [![Postgres](https://github.com/Harshit-sehgal/Scraper/actions/workflows/postgres-tests.yml/badge.svg)](https://github.com/Harshit-sehgal/Scraper/actions/workflows/postgres-tests.yml) |
| **Browser E2E** (Playwright) | [![Browser E2E](https://github.com/Harshit-sehgal/Scraper/actions/workflows/browser-e2e.yml/badge.svg)](https://github.com/Harshit-sehgal/Scraper/actions/workflows/browser-e2e.yml) |
| **Local Validation** | `make validate` runs `python3 scripts/validate_local.py --full`; use `make validate-quick` for the bounded quick gate |

> Note: Per-job status badges use GitHub's per-job query parameter (`?job=...`).
> Replace `Harshit-sehgal/Scraper` in badge URLs with the actual repo owner/name if forked.

For the latest detailed status, run `make validate` for the full local gate, `make validate-quick` for the bounded quick gate, or check the [latest CI run](https://github.com/Harshit-sehgal/Scraper/actions/workflows/ci.yml).

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
make validate-quick
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
- `docs/ARCHITECTURE.md` - actual architecture map
- `docs/API.md` - manually verified route summary
- `docs/SECURITY.md` - security posture and remaining risks
- `docs/LIMITATIONS.md` - known limitations
- `docs/TESTING.md` - test commands and what they prove
- `docs/BENCHMARKS.md` - benchmark truth and gaps
- `docs/PRODUCTION.md` - production deployment notes
- `docs/MODULE_CLASSIFICATION.md` - core/stable/experimental classification

Archived docs under `docs/archive/` are historical unless explicitly refreshed.

## Banned Overclaims

Do not claim this project is production-ready, enterprise-grade, universal, anti-bot immune, fully autonomous, fully self-healing, 100% accurate, guaranteed, complete, or fully benchmarked unless future evidence explicitly validates that claim.

# DataForge Scraper

[![CI](https://github.com/Harshit-sehgal/Scraper/actions/workflows/ci.yml/badge.svg)](https://github.com/Harshit-sehgal/Scraper/actions/workflows/ci.yml)
[![Auto-Fix Formatting](https://github.com/Harshit-sehgal/Scraper/actions/workflows/auto-fix.yml/badge.svg)](https://github.com/Harshit-sehgal/Scraper/actions/workflows/auto-fix.yml)
[![Dependabot](https://img.shields.io/badge/Dependabot-enabled-0366d6?logo=dependabot)](https://github.com/Harshit-sehgal/Scraper/network/dependencies)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-blue?logo=python)](https://www.python.org/downloads/release/python-3120/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**A web scraping SaaS with API keys, job queues, browser rendering, and structured exports.** Create a job, pick schema fields, get results as CSV/JSON/Excel — all through REST APIs or the dashboard.

> Agent truth source: [`docs/AGENT_TRUTH.md`](docs/AGENT_TRUTH.md). That file holds current command-verified evidence. Older status docs are historical unless their claims are reproduced by fresh command output.

## In 60 Seconds: Scrape a Website

```bash
# 1. Set up
cp .env.example .env
cd backend && python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
playwright install chromium

# 2. Start the API
PYTHONPATH=backend DATAFORGE_STORAGE_BACKEND=sqlite uvicorn app.main:app --reload

# 3. Create and run a scraping job
curl -s -X POST http://localhost:8000/api/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "target_url": "https://books.toscrape.com",
    "schema_fields": [
      {"name": "title", "field_type": "string"},
      {"name": "price", "field_type": "string"}
    ],
    "max_pages": 1
  }'

# 4. Check job status
curl -s http://localhost:8000/api/jobs/<job_id>

# 5. Get structured results
curl -s http://localhost:8000/api/jobs/<job_id>/results

# 6. Export as CSV/JSON/Excel
curl -s http://localhost:8000/api/exports/<job_id>/csv > results.csv
curl -s http://localhost:8000/api/exports/<job_id>/json > results.json
curl -s http://localhost:8000/api/exports/<job_id>/xlsx > results.xlsx
```

## What It Does

**Core product flow** — the path every user hits:
- **Job management**: create, list, get, cancel, retry, delete, restore scraping jobs.
- **URL validation**: SSRF protection, deny lists, DNS-resolved IP checks, port blocking.
- **Scraping engine**: Playwright-backed browser rendering, schema/selector extraction, network payload extraction, visible text fallback, pagination.
- **Status tracking**: pending → running → completed/canceled/empty_result, with events stream.
- **Structured results**: schema-defined fields returned as typed records (string, number, boolean, date, list, nested objects).
- **Export**: CSV, JSON, Excel (XLSX) for every completed job. Source URL and scrape timestamp included in every export.

**Platform features** — security, operations, diagnostics:
- **Auth & RBAC**: API key authentication, UserRole enums (ADMIN, OPERATOR, VIEWER), per-route role requirements.
- **Tenant isolation**: user/org/project scoping on all job reads and mutations.
- **Rate limiting**: per-domain rate controls via CrawlPolicyEngine, in-memory or database-backed.
- **Audit logging**: SSRF audit events, access logs, security-relevant events.
- **Health monitoring**: `/health`, `/ready`, `/health/worker`, `/health/db`, `/health/browser` endpoints.
- **Static dashboard**: internal operations UI for job inspection, results browsing, diagnostics.
- **Storage**: SQLite (local/default) or PostgreSQL (production), selectable at startup.

**Experimental modules** — research features kept separate from the product path:
- Selector memory, strategy evolution, semantic world state, topology/federation, replay, chaos engineering, adaptive scoring modules.
- These are documented in [`docs/MODULE_CLASSIFICATION.md`](docs/MODULE_CLASSIFICATION.md) and labeled in the codebase. They do not appear in the default product UI or API surface.

## What You Should Know

- Works on **accessible websites** where scraping is technically feasible and permitted.
- Browser rendering handles JavaScript-heavy pages; static-HTTP fallback handles simple ones.
- Anti-bot detection gracefully identifies blocked pages — it does not circumvent website protections.
- Extraction accuracy varies by site structure. Run benchmarks on your target sites.
- Production deployment requires production-strength secrets, TLS, and network controls (see [`docs/PRODUCTION.md`](docs/PRODUCTION.md)).

## Current Status

The badges above link to the CI workflow file itself (overall workflow status). The
table below describes the *named jobs* the CI workflow contains so you can read a
specific job's badge. For each name use `?job=<job-id>` in your badge URL.

| Job | What it does |
|----|----|
| **`quick-validation`** | Compile, architecture validator, research boundary, dependency bounds, URL safety tests, P0 regression tests, OpenAPI spec |
| **`lint`** | ruff (lint + format check), mypy |
| **`frontend`** | npm ci + audit signatures, vitest tests, esbuild build, eslint/stylelint/prettier, dist artifact checks |
| **`docker-smoke`** | Builds `Dockerfile.smoke` and runs `test_docker_smoke.py` (4 endpoint probes) |
| **`unit-tests`** | Full pytest unit suite with coverage floor checks |
| **`contract-tests`** | API contract tests (maked with `-m api`) |
| **`migrate-check`** | Storage migration / regression / DDL-only Postgres tests |

Local-side static analysis (not part of `ci.yml` but enforced via pre-commit):
**ruff format + lint**, **mypy**, **bandit** (medium+ severity).

`make validate` runs `python3 scripts/validate_local.py --full` (the default
local validation gate). For a faster smoke check use `make validate-quick` or
`python3 scripts/validate_local.py --quick`. Check the [latest CI run](https://github.com/Harshit-sehgal/Scraper/actions/workflows/ci.yml) for current results.

> Adjust the workbook row above (`?job=<job-id>`) to point at any of the jobs
> listed in the table — for example `?job=docker-smoke` or `?job=quick-validation`.

For ongoing test pipelines:
- **Dependabot auto-merge** — see the `dependabot-auto-merge.yml` workflow.
- **Postgres integration** — `postgres-tests.yml` runs weekly and on dispatch.
- **Browser E2E** — `browser-e2e.yml` runs the Playwright browser paths.
- **Golden-dataset** — `golden-dataset.yml` records live extraction accuracy.
- **Nightly integration** — `nightly-integration.yml` runs the heaviest integration suite overnight.

## Quick Start

**Option A — Local Python (no Docker):**

```bash
cp .env.example .env
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
playwright install chromium
npm ci
npm run build
python3 scripts/doctor.py
```

**Option B — Docker:**

```bash
cp .env.example .env
make setup     # pip, npm, playwright, migrate, build, docker compose up
```

Start the API:

```bash
# Local:
PYTHONPATH=backend DATAFORGE_STORAGE_BACKEND=sqlite uvicorn app.main:app --reload

# Docker:
make up
curl http://localhost:8000/health
curl http://localhost:8000/ready
```

## API Notes

### Payload Optimization
`/api/jobs` and `/api/recycle_bin` return summary DTOs. For full job config, logs, or results use `/api/jobs/{job_id}`, `/api/jobs/{job_id}/results`, or export endpoints.

### Security & Development Mode
In development mode (`DATAFORGE_ENV=development`), unauthenticated calls are rejected by default. To allow local testing without API keys:
```bash
export DATAFORGE_ALLOW_INSECURE_DEV_AUTH=true
```

### Static Dashboard
The static dashboard (`/app/`) is an internal operations tool. In production, serve it through Nginx/CDN with network ACLs and reverse-proxy auth. It is not mounted when `DATAFORGE_ENV=production`.

## Validation Commands

```bash
python3 scripts/validate_local.py --quick       # Fast gate (compile, architecture, deps, P0 tests)
python3 scripts/validate_local.py --full        # Full gate including backend and frontend
python3 scripts/validate_local.py --backend     # Backend tests only
python3 scripts/validate_local.py --frontend    # Frontend build + lint + tests
python3 scripts/validate_local.py --security    # Security checks only
```

Makefile shortcuts: `make validate`, `make validate-quick`, `make validate-full`, `make validate-backend`, `make validate-frontend`, `make validate-security`.

See [`docs/VALIDATION.md`](docs/VALIDATION.md) for setup, interpretation, and stable vs experimental check details.

## Project Structure

```text
backend/
  app/
    main.py                         FastAPI app, middleware, health/readiness/metrics
    routers/                        API routers (jobs, exports, scraper, operator)
    services/                       job and background service helpers
    utils/                          auth, export, validation, security utilities
    scraper.py                      scraping orchestration
    extraction_orchestrator.py      extraction coordination and fallbacks
    storage_interface.py            SQLite/Postgres storage selection
    worker_queue.py                 local worker queue
    worker_queue_postgres.py        Postgres-backed queue
  tests/                            automated pytest suite
  benchmarks/                       benchmark suite and corpus
frontend/                           static operations dashboard
docs/                               current documentation
scripts/                            operational and validation helpers
```

## Deploying to Production

Before public deployment:

1. Generate strong, unique API keys for each role (user, operator, admin) — store outside source control.
2. Fill every placeholder in `.env.production.example`.
3. Validate with `make validate-full` then test Docker stack: `make prod` → verify `/health`, `/ready`, `/health/worker`, `/health/db`, `/health/browser`.
4. Configure PostgreSQL (set `DATAFORGE_STORAGE_BACKEND=postgresql` with connection URL).
5. Route traffic through Nginx with TLS, CORS, CSP, and metrics protection.
6. Treat the dashboard as internal-only. Add reverse-proxy auth and network ACLs.
7. Run benchmarks against your target sites before making extraction accuracy claims.

See [`docs/PRODUCTION.md`](docs/PRODUCTION.md) for the full checklist.

## Documentation Index

| Doc | Purpose |
|-----|---------|
| [`docs/AGENT_TRUTH.md`](docs/AGENT_TRUTH.md) | Current command-evidence truth source |
| [`docs/VALIDATION.md`](docs/VALIDATION.md) | Reproducible validation commands |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Architecture map |
| [`docs/API.md`](docs/API.md) | Route summary |
| [`docs/SECURITY.md`](docs/SECURITY.md) | Security posture and risks |
| [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md) | Known limitations |
| [`docs/TESTING.md`](docs/TESTING.md) | Test commands and coverage |
| [`docs/BENCHMARKS.md`](docs/BENCHMARKS.md) | Benchmark suite and corpus |
| [`docs/PRODUCTION.md`](docs/PRODUCTION.md) | Production deployment |
| [`docs/MODULE_CLASSIFICATION.md`](docs/MODULE_CLASSIFICATION.md) | Core/stable/experimental labels |

Archived docs under `docs/archive/` are historical unless explicitly refreshed.

## Ethical and Legal Boundary

Use this project only on websites where scraping is allowed or authorized. Respect robots.txt, terms of service, rate limits, access controls, and applicable law. Do not use it to scrape private, sensitive, or restricted data without permission. Anti-bot detection identifies blocked pages gracefully — it exists for transparency, not circumvention.

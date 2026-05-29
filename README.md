# DataForge Scraper

DataForge Scraper is a pre-production web extraction platform built around a FastAPI backend, Playwright-based browser automation, job orchestration, result export, telemetry, and adaptive extraction components.

It is designed to extract structured data from supported accessible public pages. Success depends on site structure, authentication requirements, anti-bot controls, rate limits, robots/legal constraints, network conditions, and the schema or extraction configuration supplied.

## What This Is Not

This project is not a universal scraper, not a guaranteed anti-bot solution, not fully production-ready, and not proof of perfect extraction accuracy. Several advanced semantic, topology, replay, and adaptive components exist in code, but they are not all validated with production-like tests.

## Current Status

The current source of truth is [PROJECT_STATUS.md](PROJECT_STATUS.md). The full audit report is [docs/AUDIT_REPORT.md](docs/AUDIT_REPORT.md).

Verified locally during this cleanup:

- FastAPI backend imports successfully with `PYTHONPATH=backend`.
- Python sources compile with `python3 -m compileall -q`.
- `pyflakes` reports no issues for `backend/app`, `scripts`, and `architecture_validator.py`.
- `mypy backend/app --ignore-missing-imports` reports no errors, but many function bodies remain unchecked because they are untyped.
- The architecture validator passes.
- Pytest collected 1711 tests and the verified full local run reported 1657 passed and 54 skipped.

Not fully verified:

- Production Docker Compose stack against a real domain.
- Real Postgres CI/service-container validation.
- Live benchmark reliability across changing websites.
- Strict production CSP without CDN dependencies.
- Distributed rate limiting.
- Browser/dashboard authentication suitable for hostile shared environments.

## Features

- FastAPI API for job creation, tracking, cancellation, deletion, and result export.
- Playwright/browser-backed scraping with fallback extraction paths.
- Schema suggestion and URL analysis endpoints for operator/admin use.
- SQLite default storage and Postgres implementation paths.
- Optional worker queue and production compose stack.
- Prometheus metrics endpoint and Grafana/Prometheus deployment files.
- Frontend dashboard for internal/private operation.
- SSRF-oriented URL validation for public HTTP(S) targets.
- Adaptive selector, recovery, semantic topology, replay, and telemetry modules.
- Deterministic fixture tests and manual/live benchmark scripts.

## Quickstart

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
playwright install chromium
PYTHONPATH=backend python3 -m uvicorn app.main:app --reload
```

Open:

- API root: `http://127.0.0.1:8000/`
- Main dashboard: `http://127.0.0.1:8000/app`
- API docs in development: `http://127.0.0.1:8000/docs`

## Configuration

Copy `.env.example` for local settings. Important variables:

- `DATAFORGE_API_KEY`: user-level API key for `/api/*` when configured.
- `DATAFORGE_OPERATOR_API_KEY`: operator key for job creation, discovery, URL analysis, selector mutation, and strategy actions.
- `DATAFORGE_ADMIN_API_KEY`: admin key for destructive/system-level actions.
- `DATAFORGE_CORS_ORIGINS`: JSON array of allowed browser origins.
- `DATAFORGE_STATE_FILE_PATH`: local JSON state path for SQLite mode.
- `DATAFORGE_STORAGE_BACKEND`: `sqlite` by default; `postgres` for production-style deployments.
- `DATAFORGE_DATABASE_URL`: Postgres URL when Postgres is enabled.
- `DATAFORGE_METRICS_TOKEN`: token for direct backend `/metrics` access when exposed.

`DATAFORGE_STATE_FILE` is still accepted as a deprecated fallback. Prefer `DATAFORGE_STATE_FILE_PATH`.

## Tests

```bash
python3 -m compileall -q backend scripts architecture_validator.py
python3 -m pyflakes backend/app scripts architecture_validator.py
PYTHONPATH=backend python3 architecture_validator.py
PYTHONPATH=backend python3 -m pytest --collect-only -q -o addopts=
PYTHONPATH=backend python3 -m pytest -q
```

Some tests are skipped unless Postgres, live LLM credentials, or specific flags are available. Do not count skipped or uncollected manual benchmark scripts as passing tests.

## Production Warning

Production deployment files are present, but this repository should be treated as a pre-production candidate until the release gates in [docs/PRODUCTION.md](docs/PRODUCTION.md) pass in the target environment.

Production startup now runs `scripts/check_prod_env.py` through the server and worker entrypoints when `DATAFORGE_ENV=production`. Placeholder secrets in `.env.production.example` are expected to fail validation.

## Documentation

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- [docs/API.md](docs/API.md)
- [docs/SETUP.md](docs/SETUP.md)
- [docs/PRODUCTION.md](docs/PRODUCTION.md)
- [docs/SECURITY.md](docs/SECURITY.md)
- [docs/TESTING.md](docs/TESTING.md)
- [docs/BENCHMARKING.md](docs/BENCHMARKING.md)
- [docs/LIMITATIONS.md](docs/LIMITATIONS.md)
- [docs/ROADMAP.md](docs/ROADMAP.md)

Historical reports with stale maturity claims are preserved in `docs/archive/`.

## Contribution Rules

- Claims in docs must be backed by code inspection, tests, runtime output, or reproducible evidence.
- Simulated benchmark results must be labeled as simulated.
- Live benchmark results must include date, command, environment, and target list.
- Production readiness must not be claimed until production env validation, Docker Compose, Postgres, browser, proxy, metrics, and security checks are validated together.

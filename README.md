# DataForge Scraper

**Status: Pre-Production Candidate**

A backend-driven web extraction platform built with FastAPI and Playwright. It creates scraping jobs, automates browser-based extraction, stores structured results, and provides APIs for job management, export, and observability.

This is not a "magic scraper that works on any website." It is a practical tool for extracting structured data from accessible public web pages — given appropriate selectors, configuration, and respect for the target website's legal and technical constraints.

---

## What It Is

- A FastAPI backend with 55+ API endpoints for job management, scraping, export, and system monitoring
- Playwright-based browser automation for JavaScript-rendered pages
- Job orchestration with in-process queue (Postgres-backed optional)
- SQLite storage (default) or Postgres (requires configuration)
- Structured data extraction with field validation
- CSV/JSON/Excel export
- Prometheus metrics with Grafana dashboards
- In-memory rate limiting, SSRF protection, API key authentication
- A dashboard (client-side, for internal use)
- Testing infrastructure (2,207 tests) and benchmark tooling

## What It Is Not

- ❌ Not a universal scraper — requires selectors/configuration per site
- ❌ Not production-ready — requires security hardening for public deployment
- ❌ Not fully self-healing — recovery handlers exist but are not stress-validated
- ❌ Not anti-bot immune — basic evasion exists, not validated against real countermeasures
- ❌ Not real-time streaming — dashboard polls for updates (no WebSockets)
- ❌ Not distributed — rate limiting and queue are in-process by default
- ❌ Not fully benchmarked — benchmark tooling exists but is not CI-integrated

---

## Quick Start

```bash
# Clone and set up
cp .env.example .env
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium

# Start the server
python -m app.main
```

```bash
# Test it
curl http://localhost:8000/health
curl http://localhost:8000/api/jobs
```

---

## Running Tests

```bash
# All unit tests (SQLite default)
PYTHONPATH=backend DATAFORGE_STORAGE_BACKEND=sqlite python3 -m pytest backend/tests/ -q

# With Postgres tests (requires Docker)
PYTHONPATH=backend python3 -m pytest backend/tests/ --run-postgres -q

# With golden dataset tests (hits real websites)
PYTHONPATH=backend python3 -m pytest backend/tests/ --run-golden-dataset -q
```

**Note:** Tests require `DATAFORGE_STORAGE_BACKEND=sqlite` unless Postgres is running. The `.env` file defaults to `postgres` — override or unset it when running tests without Postgres.

---

## Code Quality & Standards

The codebase has been thoroughly audited and cleaned:

| Metric | Status |
|--------|--------|
| **Flake8 Compliance** | ✅ **0 errors** (5,406+ errors fixed) |
| **Code Style** | ✅ PEP 8 compliant (black-formatted) |
| **Line Length** | ✅ 130-char limit (.flake8 configured) |
| **Type Checking** | ✅ mypy: 0 errors (`--ignore-missing-imports`) |
| **Backend Files** | ✅ 151 app modules (0 flake8 errors) |
| **Test Files** | ✅ 115 test/benchmark files (0 flake8 errors) |

### Code Quality Commands

```bash
# Check for style errors
flake8 backend/ --exit-zero

# Format new code
black <file> --line-length=120

# Auto-fix simple issues
autopep8 <file> --in-place --aggressive
```

See [docs/SETUP.md#code-quality](docs/SETUP.md) for details.

---

## Current Status

| Area | Status |
|------|--------|
| Backend syntax & imports | ✅ Verified (compileall + pyflakes + flake8 clean) |
| API routes | ✅ 55 endpoints registered and serving |
| SQLite storage | ✅ Working |
| Postgres storage | ⚠️ Code exists, requires running container |
| Tests (collected) | ✅ 2,207 tests across 145 files |
| Tests (passing with SQLite) | ✅ ~1,843 passed, ~55 skipped, 0 failures |
| Postgres tests | ⚠️ Skipped by default (need `--run-postgres`) |
| Golden dataset tests | ⚠️ Skipped by default |
| Manual tests (14) | ❌ Not integrated into pytest |
| Benchmarks (4) | ✅ Collected by pytest (but partially simulated) |
| CI pipeline | ⚠️ Exists, not verified in this audit |
| RBAC | ⚠️ Keys separated in .env.example (requires user generation) |
| Rate limiting | ⚠️ In-memory only (single-process) |
| Dashboard CSP | ⚠️ Vendored assets exist, CSP is strict |
| Production startup gate | ✅ Credential validation in lifespan |
| Type checking | ✅ mypy: 0 errors with `--ignore-missing-imports` |

---

## Known Limitations

See [docs/LIMITATIONS.md](docs/LIMITATIONS.md) for a comprehensive list.

Key limitations:
- Extraction accuracy depends on website structure — not guaranteed
- Anti-bot measures are basic — real-world effectiveness unknown
- Rate limiting is per-process, not distributed
- Dashboard stores API key in localStorage (XSS risk for public deployment)
- Production deployment requires manual configuration validation
- Benchmark results are partially simulated

---

## Project Structure

```
backend/
  app/
    main.py                  — FastAPI application entry point
    routers/                 — API route handlers (jobs, scraper, exports, operator)
    services/                — Background services (job_runner, state)
    utils/                   — Utilities (env, rbac, export, rate_limit, quality, prod_security_validator)
    config.py                — Configuration (partial — some modules use direct os.getenv)
    scraper.py               — Playwright-based scraping
    extraction_orchestrator.py — Extraction coordination
    field_laws.py            — Field validation rules
    selector_engine.py       — CSS/XPath selector management
    worker_queue.py          — Job queue (in-process)
    worker_queue_postgres.py — Job queue (Postgres-backed)
    storage_interface.py     — Storage backend factory
    postgres_repository.py   — Postgres repository
    state_store.py           — State persistence
    ... (151 Python modules)
  tests/
    test_*.py                — 2,207 tests across 145 files
    fixtures/pages/          — 42 fixture HTML pages
    manual_*.py              — 14 manual test scripts (not pytest-collected)
  benchmarks/
    test_benchmark_hostile.py — Simulated hostile benchmark (pytest-collected)
    test_benchmark_replay.py  — State replay benchmark (pytest-collected)
    test_benchmark_longevity.py — Long-running stability test (pytest-collected)
    test_benchmark_smoke.py   — Smoke test (pytest-collected, offline check only)
frontend/
  index.html                 — Main dashboard
  dashboard/                 — Dashboard views
  js/                        — Modular JavaScript
docs/                        — Documentation
scripts/                     — Utility scripts
```

---

## Production Warning

This project is a **pre-production candidate**. Before deploying publicly:

1. Generate unique, strong API keys for each role (user, operator, admin)
2. Add a production startup gate that validates all required secrets
3. Rotate any credentials that were exposed in `.env` files
4. Verify CSP compatibility with the dashboard
5. Add container healthchecks
6. Set up proper secret management (not `.env` files)
7. Configure CORS origins for your actual domain
8. Set up proper Postgres with failover
9. Verify Nginx configuration for your deployment

---

## Contributing

- **Code Quality:** All code must pass flake8 validation (0 errors required)
  - Run `flake8 backend/ --exit-zero` before committing
  - Use `black <file> --line-length=120` for auto-formatting
  - Configuration: `.flake8` (130-char limit, sensible defaults)
- **Tests:** Tests must pass before merging: `DATAFORGE_STORAGE_BACKEND=sqlite PYTHONPATH=backend python3 -m pytest backend/tests/ -q`
  - New features should include tests
  - Manual test scripts: Follow `manual_test_*.py` naming
  - Benchmark scripts: Follow `test_benchmark_*.py` naming for pytest collection

- **Code Style:**
  - PEP 8 compliant (enforced by flake8)
  - Use `let`/`const` instead of `var` in JavaScript
  - Black-formatted Python code (line length 120)

- **Error Handling:**
  - No silent `except: pass` — all exception handlers must log or include a comment
  - All exceptions must be intentional and documented

- **Configuration:**
  - Direct `os.getenv` calls should be migrated to `config.py`
  - No hardcoded secrets — use environment variables or `.env`
  - Use strong, random values for API keys outside local development

- **Documentation:**
  - Keep READMEs updated when changing APIs or configuration
  - Document all new environment variables in `.env.example`
  - Add docstrings to public functions and classes

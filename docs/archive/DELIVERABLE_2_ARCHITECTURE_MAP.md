# Deliverable 2: Architecture Reality Map

**Date:** May 30, 2026
**Method:** Code inspection, route enumeration, module analysis.

---

## What the Project Actually Does

DataForge is a **backend-driven web extraction platform** built with FastAPI + Playwright. It creates scraping jobs, manages browser automation, extracts structured data, stores results, and exposes APIs for job management and export.

---

## Component Breakdown

### 1. Backend Core (`backend/app/main.py`)
- **Status:** Implemented and verified
- FastAPI application with middleware stack: CORS → Exception → BodySize → API Key Auth → Rate Limiter → Latency Tracking
- 55 registered API routes across 4 routers
- Health check (`/health`) and readiness (`/ready`) endpoints respond

### 2. API Routes
- **Status:** Implemented and verified (all routes enumerated)

| Router | Routes | Area |
|--------|--------|------|
| `routers/jobs.py` | 15 | Job CRUD, cancel, reclean, recycle bin, exports |
| `routers/scraper.py` | ~25 | Scraper config, telemetry, trends, selectors, ML, strategy, diagnostics |
| `routers/exports.py` | 3 | CSV/JSON/Excel export |
| `routers/operator.py` | 6 | Operator mode, dashboard, predictions |
| `main.py` | 6 | Root, health, readiness, system status, storage status |

### 3. Scraper / Browser Layer
- **Status:** Implemented but weakly verified
- Uses Playwright via `browser_pool.py` for browser automation
- `scraper.py` handles the scraping lifecycle
- `anti_bot_engine.py` provides anti-detection measures
- `session_url_detector.py` handles session-based URL detection
- `selector_engine.py` manages CSS/XPath selectors
- **Reality:** Works for pre-configured sites. "Works on any website" is false.

### 4. Extraction Layer
- **Status:** Implemented but weakly verified
- `extraction_orchestrator.py` coordinates extraction workflow
- `field_validator.py` validates extracted fields against schema
- `semantic_mapper.py`, `semantic_pipeline.py` provide semantic extraction
- `llm_bridge.py` integrates LLM-based extraction (Groq API)

### 5. Job Orchestration
- **Status:** Implemented and partially verified
- `job_store.py` manages job persistence
- `worker_queue.py` provides in-process and Postgres-backed queue
- `services/job_runner.py` runs jobs as background tasks
- Basic CRUD operations work in local testing

### 6. Storage Layer
- **Status:** Implemented but environment-dependent
- `storage_interface.py` provides factory pattern for SQLite/Postgres
- SQLite: Works locally (default for development)
- Postgres: Code exists, requires running Postgres container
- **Critical issue:** `.env` sets `DATAFORGE_STORAGE_BACKEND=postgres`, causing test failures without Postgres

### 7. Queue / Worker Layer
- **Status:** Partially verified
- `worker_queue.py`: In-process queue (default)
- `worker_queue_postgres.py`: Postgres-backed queue (requires Postgres)
- `services/job_runner.py`: Background job execution
- Queue is in-process by default — not distributed

### 8. Metrics / Telemetry
- **Status:** Implemented and verified
- `metrics_collector.py`: Prometheus metrics
- `scrape_telemetry.py`: Per-scrape telemetry
- `observability.py`: Structured logging
- Prometheus/Grafana dashboards configured

### 9. Dashboard / Frontend
- **Status:** Implemented but client-side only (static files)
- `frontend/index.html`: Main dashboard
- `frontend/dashboard/index.html`: Separate dashboard view
- `frontend/js/`: Modular JS (api.js, jobs.js, results.js, etc.)
- Vendored assets (Tailwind CSS, Chart.js) stored locally
- **CSP conflict:** Nginx enforces strict `script-src 'self'` — vendored assets exist but CSP and CDN references conflict
- API key stored in localStorage (XSS risk)

### 10. Security / Auth
- **Status:** Partially verified, multiple issues
- API key middleware: All routes require `X-API-Key` header (when key is configured)
- RBAC exists (`utils/rbac.py`) with operator/admin roles
- **Critical issue:** All three API keys (user, operator, admin) are the **same value** in `.env` (`0dd9362f...`)
- Rate limiting: In-memory only (per-process, not distributed)
- URL safety: `url_safety.py` blocks private IPs, localhost — code exists, needs test verification
- CORS: Configurable via environment

### 11. Production Deployment
- **Status:** Configuration exists, not validated end-to-end
- `Dockerfile`: Multi-stage build, Python 3.12
- `docker-compose.yml`: Dev stack (app + port changes)
- `docker-compose.prod.yml`: Full production stack (app + Postgres + Nginx + Prometheus + Grafana)
- `nginx.conf`: Reverse proxy with CSP, rate limiting, metrics
- **Missing:** Production startup gate for secret validation, healthcheck correctness

### 12. Testing / Benchmarking
- **Status:** Large suite with significant gaps
- **2,207 tests collected** from 145 files
- **Core issue:** Many tests fail due to `.env` bleeding `DATAFORGE_STORAGE_BACKEND=postgres` into test env
- Benchmarks (4 files in `backend/benchmarks/`) are **not** collected by pytest — not named `test_*.py`
- 15 manual test files not run by pytest
- Some benchmarks use hardcoded/simulated data rather than real scraping

### 13. Advanced Components
- **Status:** Implemented but validation is weak

| Component | Reality |
|-----------|---------|
| Semantic World State | Implemented with CRDT-based state management, weakly tested |
| Topology/Discovery | Code exists for automated selector discovery, minimal live validation |
| Self-healing/Recovery | Recovery handlers exist for common failure modes, not stress-tested |
| Chaos Engineering | `chaos_simulator.py` — simulation of failures, not real chaos testing |
| Adaptive Extraction | Self-tuning extraction exists, accuracy depends on site structure |
| Cognitive Agency | Cognitive steering/scheduling code exists, mostly simulated |
| Federation | Sharded federation code exists, not tested in distributed setup |

---

## What the Project Actually Does Well

- FastAPI backend starts and serves routes
- SQLite-based job storage works
- Playwright-based extraction works for accessible sites
- Job lifecycle management (create, cancel, results, recycle bin)
- Export to CSV/JSON/Excel
- Prometheus metrics with Grafana dashboards
- Large test suite covering many components

## What the Project Does NOT Do (Despite Claims)

- Does NOT work on "any website" — requires specific selectors/configuration
- Does NOT have distributed rate limiting
- Does NOT have effective RBAC (all keys are the same)
- Does NOT have CI-validated Postgres support (tests skipped by default)
- Does NOT have real-world validated benchmarks (simulated data)
- Does NOT have a production-hardened startup (no secret validation gate)
- Does NOT have real-time streaming (polls for updates)
- Does NOT have validated anti-bot resilience

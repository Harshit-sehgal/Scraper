# DataForge Storage & Deployment Architecture

DataForge supports **two storage backends** (SQLite and PostgreSQL) selected explicitly at runtime, plus an **async worker queue** for background job processing and a **Prometheus/Grafana monitoring stack**.

---

## 1. Storage Backends

DataForge uses a repository pattern (`JobRepository` ABC in `app/storage_interface.py`):

```python
from app.storage_interface import get_job_repository
repo = get_job_repository()  # Returns PostgresJobRepository or SQLiteJobRepository
```

The backend is selected by environment variables — **not automatic**.

### SQLite (default)

A transactional, high-performance SQLite backend configured with Write-Ahead Logging (WAL) for safe, concurrent multi-process scraping operations. Default when no Postgres env vars are set.

**When to use:** Development, single-instance deployments, low-to-medium traffic.

### PostgreSQL (opt-in production)

Explicitly opt in by setting **both** environment variables:

```bash
export DATAFORGE_STORAGE_BACKEND=postgres
export DATAFORGE_DATABASE_URL="postgresql://dataforge:password@host:5432/dataforge"
```

The system returns `PostgresJobRepository` when both are set. If `DATAFORGE_STORAGE_BACKEND=postgres` is set but connectivity fails, the server **raises at startup** — no silent fallback. If only `DATAFORGE_DATABASE_URL` is set without `STORAGE_BACKEND=postgres`, Postgres mode is **not** activated (SQLite is used instead).

Postgres is backed by **psycopg2** (synchronous) with `ThreadedConnectionPool`. No async wrappers.

**Postgres Mode Features:**
- Worker queue can use Postgres backend via `DATAFORGE_QUEUE_BACKEND=postgres`
- Semantic world-state persistence (load/save world state)
- Savepoint-safe schema migrations (no transaction aborts on ALTER TABLE)
- Individual repo operations: move_to_recycle_bin, restore, hard_delete, clear_terminal_jobs
- Non-development environments require explicit `DATAFORGE_DATABASE_URL`

**When to use:** Production deployments, high traffic, multi-worker setups.

---

## 2. Local Deployment Guide

### Prerequisites
- Python 3.11 or 3.12
- SQLite 3 (pre-installed on most platforms)
- Playwright browsers: `python -m playwright install chromium`

### Setup & Installation

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Configure Environment

Create a `.env` file in the `backend/` directory:

```env
# SQLite mode (default) — no storage backend vars needed
# Postgres mode — uncomment both:
# DATAFORGE_STORAGE_BACKEND=postgres
# DATAFORGE_DATABASE_URL=postgresql://dataforge:password@localhost:5432/dataforge

# LLM Credentials (optional, fallback engines work without)
GROQ_API_KEY=your_key_here
```

### Start the Server

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Run Tests

```bash
# All tests except Postgres integration (default)
cd backend && python -m pytest -q -m "not postgres"

# Postgres integration tests (requires Docker + testcontainers)
pip install -r requirements-dev.txt
python -m pytest --run-postgres -m postgres -v
```

---

## 3. SQLite Storage Engine

### WAL Mode
SQLite uses **WAL mode** by default for:
- Readers do not block writers
- Writers do not block readers
- Atomic writes prevent corruption during crashes

### Auto-Migration from JSON
Legacy JSON state files (`jobs_state.json`) are automatically detected and migrated to SQLite on first startup.

### Custom DB Path
```bash
export DATAFORGE_STATE_FILE="/custom/path/to/my_state.json"
# DB resolves to "/custom/path/to/my_state.db"
```

### Backup & Restore
```bash
# Online hot-backup
sqlite3 data/jobs_state.db ".backup data/jobs_state_backup.db"

# Restore
cp data/jobs_state_backup.db data/jobs_state.db
rm -f data/jobs_state.db-shm data/jobs_state.db-wal
```

---

## 4. PostgreSQL Deployment

### Enable Postgres

Set **both** environment variables:

```bash
export DATAFORGE_STORAGE_BACKEND=postgres
export DATAFORGE_DATABASE_URL="postgresql://dataforge:password@host:5432/dataforge"
```

Postgres mode is **explicit** — you must set both. If `DATAFORGE_STORAGE_BACKEND=postgres` is set and the database is unreachable, startup fails with a clear error. There is **no silent fallback** to SQLite.

### Production Environment Validation

Before starting the production stack (from the project root directory), validate configuration with:

```bash
python3 scripts/check_prod_env.py --env-file .env.production.example
```

The script validates all required variables:
- `DATAFORGE_API_KEY` — rejects known placeholders, requires ≥16 characters
- `DATAFORGE_CORS_ORIGINS` — must be a JSON array, rejects wildcard `*`, validates URL format
- `DATAFORGE_DB_PASSWORD` — rejects known defaults (`dataforge`, `change-me`, `password`), requires ≥8 characters
- `DATAFORGE_STORAGE_BACKEND` — must be `postgres`
- `DATAFORGE_DATABASE_URL` — must start with `postgresql://` or `postgres://`
- `DATAFORGE_WORKER_QUEUE` — must be `true`
- `DATAFORGE_ENV` — must be `production`

Exit code 0 passes, 1 fails. Do not deploy until all checks pass.

### Docker Postgres Setup

When using `docker-compose.prod.yml`, Postgres starts automatically with:
- Health checks
- Persistent volume (`postgres_data`)
- Init scripts from `backend/init-db/`

The API and worker services have `DATAFORGE_STORAGE_BACKEND=postgres` and `DATAFORGE_DATABASE_URL` set in their environment blocks, so production Docker always uses Postgres.

**Postgres queue:** Set `DATAFORGE_QUEUE_BACKEND=postgres` to use Postgres-backed queue (recommended for multi-node). See section 5 for details.

---

## 5. Worker Queue

The async worker queue provides background job processing with two backends:

| Backend | Env Var | Use Case |
|---------|---------|----------|
| SQLite (default) | `DATAFORGE_QUEUE_BACKEND=sqlite` | Single-node, development |
| Postgres | `DATAFORGE_QUEUE_BACKEND=postgres` | Multi-node, production |

### Enable Worker Queue
```bash
export DATAFORGE_WORKER_QUEUE=true
export DATAFORGE_QUEUE_BACKEND=postgres  # recommended for production
```

When enabled, jobs are enqueued to the persistent queue instead of running inline. A separate worker process picks up and executes tasks:

```bash
python scripts/run_worker.py              # 4 workers
python scripts/run_worker.py --workers 8  # Scale up
python scripts/run_worker.py --once       # Polls until terminal state
```

**Postgres-backed queue** (`app/worker_queue_postgres.py`) provides:
- Same interface as SQLite queue (drop-in replacement via `get_worker_queue()` factory)
- Share-nothing between workers — no shared volume required
- `SKIP LOCKED` atomic dequeue for multi-node safety
- In-flight task cancellation with history archiving
- Stuck-task recovery on worker restart

### Queue Features
- Priority levels (critical, high, normal, low, background)
- Automatic retries with exponential backoff (30s, 60s, 120s...)
- Dead letter queue for permanently failed tasks
- Graceful shutdown with in-flight draining
- Observability via `get_status()`
- `timeout_seconds` preserved in task_history and retry_dead_letter

### Docker Worker
In `docker-compose.prod.yml`, the `worker` service runs `scripts/run_worker.py` alongside the API server. Both have `DATAFORGE_QUEUE_BACKEND=postgres` set so they share the Postgres queue without needing a shared volume.

---

## 6. Production Docker Stack

### Full Production Stack
```bash
docker compose -f docker-compose.prod.yml up -d
```

This starts:
| Service | Container | Description |
|---------|-----------|-------------|
| `dataforge` | API Server | FastAPI application (Uvicorn) |
| `worker` | Worker | Background job processor |
| `postgres` | PostgreSQL 16 | Production database |
| `nginx` | Nginx 1.27 | Reverse proxy with static file serving |
| `prometheus` | Prometheus | Metrics collection |
| `grafana` | Grafana 11 | Metrics visualization |

**Important:** The production Docker stack configures Postgres + worker queue by default. The API service has `DATAFORGE_WORKER_QUEUE=true` with `DATAFORGE_QUEUE_BACKEND=postgres`. Both API and worker services share the Postgres queue — no shared volume needed for the queue.

### Production Docker Smoke Test

Use the smoke test script to validate the full production stack boots correctly:

```bash
# Ensure .env has valid production settings first
export DATAFORGE_API_KEY="your-strong-key"
export DATAFORGE_DB_PASSWORD="your-strong-password"
bash scripts/smoke_prod_stack.sh
```

The script:
1. Runs `check_prod_env.py` to validate `.env`
2. Validates `docker-compose.prod.yml` config
3. Builds production images (`--no-cache`)
4. Starts the full stack
5. Checks `/health`, `/ready` (asserts `backend=postgres`)
6. Checks authenticated endpoints `/api/system/status` and `/api/system/storage/status`
7. Creates a job via the API and verifies the worker processes it
8. Displays worker logs

### Multi-Node Architecture
With `DATAFORGE_QUEUE_BACKEND=postgres`, the stack supports multi-node deployments:
- Multiple API instances can share the same Postgres-backed queue
- Workers can run on separate machines — no shared filesystem required
- `SKIP LOCKED` ensures each task is dequeued exactly once

### Health Checks
```bash
curl http://localhost:8000/health          # Liveness
curl http://localhost:8000/ready           # Readiness (backend-aware, minimal in production)
curl http://localhost:8000/api/system/storage/status # Backend type + health
curl http://localhost:8000/metrics         # Prometheus metrics (job counts, queue depth, backend type)
```

---

## 7. Monitoring Stack

### Prometheus
Configuration: `prometheus.yml`
- Self-monitoring enabled by default
- DataForge `/metrics` is scraped internally from `dataforge:8000`
- Public Nginx intentionally returns 404 for `/metrics`; do not expose metrics publicly unless you add auth/IP restrictions
- PostgreSQL exporter and nginx stub_status targets are commented out until those components are implemented
- Retains data for 30 days
- Supports live config reload
- Alert rules are loaded from `prometheus_alerts.yml`; Alertmanager routing is omitted until an Alertmanager service is deployed

### Grafana
Provisioned dashboards at `grafana/dashboards/dataforge_overview.json`:
- System status, active jobs, queue depth
- Request rates, memory usage, error rates
- LLM call tracking

Start the monitoring stack with:
```bash
docker compose -f docker-compose.prod.yml up -d prometheus grafana
```

Grafana is accessible at `http://localhost:3000` (default: admin/admin).

---

## 8. Production Staging Checklist

- [ ] **`python3 scripts/check_prod_env.py --env-file .env`** passes (all 7 checks)
- [ ] **SQLite** or **PostgreSQL** backend configured and healthy
- [ ] **DATAFORGE_STORAGE_BACKEND** + **DATAFORGE_DATABASE_URL** set for Postgres
- [ ] **DATAFORGE_API_KEY** set to a strong random key (not a placeholder, ≥16 chars)
- [ ] **DATAFORGE_DB_PASSWORD** set to a strong password (not a default, ≥8 chars)
- [ ] **DATAFORGE_ENV** set to `production`
- [ ] **DATAFORGE_CORS_ORIGINS** locked to trusted domains
- [ ] **DATAFORGE_WORKER_QUEUE=true** for background processing
- [ ] **Health `/health`** returns `{"status": "ok"}`
- [ ] **Readiness `/ready`** returns `{"status": "ready"}` with correct backend
- [ ] **System status `/api/system/status`** returns `{"status": "online"}`
- [ ] **Cancellation**: In-flight jobs update to `CANCELED` immediately
- [ ] **Restart Recovery**: Active jobs transition to `FAILED` with recovery log
- [ ] **Benchmark Suite**: `pytest backend/tests/test_benchmark_suite.py` passes
- [ ] **Isolated Tests**: No live API keys needed for regression checks
- [ ] **Worker Queue**: Enqueues jobs correctly when `DATAFORGE_WORKER_QUEUE=true`
- [ ] **In production, enqueue failure returns 503** (no silent inline fallback)
- [ ] **API docs (`/docs`, `/openapi.json`) are protected behind API key in production**
- [ ] **Admin API Key** protects powerful routes (`/api/system/merge`, `/api/system/scheduler`, etc.)
- [ ] **Role-based API keys** — `X-API-Key` for operator routes, `X-Admin-Key` for admin routes
- [ ] **Prometheus /metrics** returns job counts, queue depth, and backend type gauges
- [ ] **CI pipeline** passes on main: lint, mypy, arch-validation, tests, Docker build
- [ ] **Postgres-backed queue** — `DATAFORGE_QUEUE_BACKEND=postgres` for share-nothing multi-node
- [ ] **Postgres Integration**: `pytest --run-postgres -m postgres -v` passes (requires Docker)
- [ ] **Smoke Test**: `bash scripts/smoke_prod_stack.sh` passes

---

## 9. Known Limitations

| Area | Limitation | Timeline |
|------|------------|----------|
| **Postgres world-state** | ✅ Resolved — world_state table with load/save methods | Done |
| **Postgres-backed queue** | ✅ Resolved — PostgresWorkerQueue with factory dispatch | Done |
| **Multi-node scaling** | ✅ Resolved — `SKIP LOCKED` atomic dequeue, share-nothing workers | Done |
| **Prometheus /metrics** | ✅ Resolved — `/metrics` endpoint with job/queue/backend gauges | Done |
| **PostgreSQL exporter** | No postgres-exporter container in compose | Future |
| **nginx stub_status** | No nginx metrics endpoint configured | Future |

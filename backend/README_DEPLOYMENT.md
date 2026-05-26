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

**Limitations (Postgres mode):**
- Worker queue remains SQLite-backed even when Postgres is active
- Semantic world-state persistence is not yet implemented for Postgres
- API and worker containers must share a volume for the SQLite worker queue

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

The script checks required variables: `DATAFORGE_API_KEY`, `DATAFORGE_CORS_ORIGINS`, `DATAFORGE_DB_PASSWORD`,
`DATAFORGE_STORAGE_BACKEND`, and `DATAFORGE_WORKER_QUEUE`.

### Docker Postgres Setup

When using `docker-compose.prod.yml`, Postgres starts automatically with:
- Health checks
- Persistent volume (`postgres_data`)
- Init scripts from `backend/init-db/`

The API and worker services have `DATAFORGE_STORAGE_BACKEND=postgres` and `DATAFORGE_DATABASE_URL` set in their environment blocks, so production Docker always uses Postgres.

**Known limitation:** Even in Postgres mode, the worker queue is still SQLite-backed (`backend/data/worker_queue.db`). The API and worker containers must share the `dataforge_data` volume. See section 6 for multi-node considerations.

---

## 5. Worker Queue

The async worker queue (`app/worker_queue.py`) enables background job processing. It is **always SQLite-backed**, even when the job repository uses Postgres.

### Enable Worker Queue
```bash
export DATAFORGE_WORKER_QUEUE=true
```

When enabled, jobs are enqueued to persistent queue instead of running inline. A separate worker process picks up and executes tasks:

```bash
python scripts/run_worker.py              # 4 workers
python scripts/run_worker.py --workers 8  # Scale up
python scripts/run_worker.py --once       # Requires DATAFORGE_JOB_ID
```

### Queue Features
- Priority levels (critical, high, normal, low, background)
- Automatic retries with exponential backoff (30s, 60s, 120s...)
- Dead letter queue for permanently failed tasks
- Graceful shutdown with in-flight draining
- Observability via `get_status()`

### Docker Worker
In `docker-compose.prod.yml`, the `worker` service runs `scripts/run_worker.py` alongside the API server. Both mount the shared `dataforge_data` volume for the SQLite queue database.

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

**Important:** The production Docker stack configures Postgres + worker queue by default. The API service has `DATAFORGE_WORKER_QUEUE=true` so jobs are automatically enqueued. Both API and worker services mount `dataforge_data:/app/backend/data` for the SQLite worker queue.

### Single-Container Architecture Note
The current production stack is **single-node**: the SQLite worker queue requires a shared filesystem between API and worker. True horizontal scaling requires moving the queue to Postgres or Redis (see section 8).

### Health Checks
```bash
curl http://localhost:8000/health          # Liveness
curl http://localhost:8000/ready           # Readiness (backend-aware)
curl http://localhost:8000/api/system/storage/status # Backend type + health
```

---

## 7. Monitoring Stack

### Prometheus
Configuration: `prometheus.yml`
- Self-monitoring enabled by default
- DataForge `/metrics`, PostgreSQL exporter, and nginx stub_status targets are **commented out** until those components are implemented
- Retains data for 30 days
- Supports live config reload

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

- [ ] **SQLite** or **PostgreSQL** backend configured and healthy
- [ ] **DATAFORGE_STORAGE_BACKEND** + **DATAFORGE_DATABASE_URL** set for Postgres
- [ ] **DATAFORGE_API_KEY** set to a strong random key
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
- [ ] **Postgres Integration**: `pytest --run-postgres -m postgres -v` passes (requires Docker)

---

## 9. Known Limitations

| Area | Limitation | Timeline |
|------|------------|----------|
| **Postgres world-state** | Semantic world-state is not persisted in Postgres mode | Future |
| **Postgres-backed queue** | Worker queue is SQLite even with Postgres storage | Future |
| **Multi-node scaling** | SQLite queue requires shared volume, not horizontally scalable | Future |
| **Prometheus /metrics** | No `/metrics` endpoint in API yet | Future |
| **PostgreSQL exporter** | No postgres-exporter container in compose | Future |
| **nginx stub_status** | No nginx metrics endpoint configured | Future |

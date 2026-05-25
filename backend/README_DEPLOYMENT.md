# DataForge Storage & Deployment Architecture

DataForge supports **two storage backends** (SQLite and PostgreSQL) selected automatically at runtime, plus an **async worker queue** for production job processing and a **Prometheus/Grafana monitoring stack**.

---

## 1. Storage Backends

DataForge uses a repository pattern (`JobRepository` ABC in `app/storage_interface.py`) that automatically resolves the backend:

```python
from app.storage_interface import get_job_repository
repo = get_job_repository()  # Returns PostgresJobRepository or SQLiteJobRepository
```

### SQLite (default)
A transactional, high-performance SQLite backend configured with Write-Ahead Logging (WAL) for safe, concurrent multi-process scraping operations.

**When to use:** Development, single-instance deployments, low-to-medium traffic.

### PostgreSQL (production)
Set `DATAFORGE_DATABASE_URL=postgresql://...` to enable the asyncpg-backed Postgres repository. Provides connection pooling, better concurrency, and production durability.

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
# Storage (SQLite default, or set DATAFORGE_DATABASE_URL for Postgres)
DATAFORGE_STATE_FILE=data/jobs_state.json

# LLM Credentials (optional, fallback engines work without)
GROQ_API_KEY=your_key_here
```

### Start the Server

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
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
Set the following environment variable:
```bash
export DATAFORGE_DATABASE_URL="postgresql://dataforge:password@host:5432/dataforge"
```

The system automatically switches to `PostgresJobRepository`. If Postgres is unreachable, it gracefully falls back to SQLite.

### Docker Postgres Setup
When using `docker-compose.prod.yml`, Postgres starts automatically with:
- Health checks
- Persistent volume (`postgres_data`)
- Init scripts from `backend/init-db/`

---

## 5. Worker Queue

The async worker queue (`app/worker_queue.py`) enables background job processing:

### Enable Worker Queue
```bash
export DATAFORGE_WORKER_QUEUE=true
```

When enabled, jobs are enqueued to SQLite-backed persistent queue instead of running inline. A separate worker process picks up and executes tasks:

```bash
python scripts/run_worker.py          # 4 workers
python scripts/run_worker.py --workers 8   # Scale up
python scripts/run_worker.py --once        # Single task, then exit
```

### Queue Features
- Priority levels (critical, high, normal, low, background)
- Automatic retries with exponential backoff (30s, 60s, 120s...)
- Dead letter queue for permanently failed tasks
- Graceful shutdown with in-flight draining
- Observability via `get_status()`

### Docker Worker
In `docker-compose.prod.yml`, the `worker` service runs `scripts/run_worker.py` alongside the API server.

---

## 6. Production Docker Stack

### Full Production Stack
```bash
docker compose -f docker-compose.prod.yml up -d
```

This starts:
| Service | Container | Description |
|---------|-----------|-------------|
| `dataforge` | API Server | FastAPI application (Gunicorn+Uvicorn) |
| `worker` | Worker | Background job processor |
| `postgres` | PostgreSQL 16 | Production database |
| `nginx` | Nginx 1.27 | Reverse proxy with static file serving |
| `prometheus` | Prometheus | Metrics collection |
| `grafana` | Grafana 11 | Metrics visualization |

### Health Checks
```bash
curl http://localhost:8000/health          # Liveness
curl http://localhost:8000/ready           # Readiness
curl http://localhost:8000/api/system/status # System summary
```

---

## 7. Monitoring Stack

### Prometheus
Configuration: `prometheus.yml`
- Scrapes metrics from dataforge:8000 every 15s
- Retains data for 30 days
- Supports live config reload

### Grafana
Provisioned dashboards at `grafana/dashboards/dataforge_overview.json`:
- System status, active jobs, queue depth
- Request rates, memory usage, error rates
- LLM call tracking

Start the full stack with:
```bash
docker compose -f docker-compose.prod.yml up -d prometheus grafana
```

Grafana is accessible at `http://localhost:3000` (default: admin/admin).

---

## 8. Production Staging Checklist

- [ ] **SQLite WAL Mode** or **PostgreSQL connection pool** healthy
- [ ] **DATAFORGE_STATE_FILE** or **DATAFORGE_DATABASE_URL** configured
- [ ] **Health `/health`** returns `{"status": "ok"}`
- [ ] **Readiness `/ready`** returns `{"status": "ready"}`
- [ ] **System status `/api/system/status`** returns `{"status": "online"}`
- [ ] **Cancellation**: In-flight jobs update to `CANCELED` immediately
- [ ] **Restart Recovery**: Active jobs transition to `FAILED` with recovery log
- [ ] **Benchmark Suite**: `pytest backend/tests/test_benchmark_suite.py` passes
- [ ] **Isolated Tests**: No live API keys needed for regression checks
- [ ] **Worker Queue**: `DATAFORGE_WORKER_QUEUE=true` enqueues jobs correctly

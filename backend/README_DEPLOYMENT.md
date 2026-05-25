# DataForge SQLite Storage & Deployment Architecture

DataForge uses a transactional, high-performance SQLite backend configured with Write-Ahead Logging (WAL) for safe, concurrent multi-process scraping operations.

---

## 1. Local Deployment Guide

To deploy the DataForge scraper platform locally, follow these structured steps:

### Prerequisites
- Python 3.11 or 3.12
- SQLite 3 (pre-installed on most platforms)

### Setup & Installation

1. **Clone & Setup Virtual Environment**
   ```bash
   cd backend
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Configure Environment Variables**
   Create a `.env` file in the `backend/` directory:
   ```env
   # Storage Configuration
   DATAFORGE_STATE_FILE=data/jobs_state.json
   
   # LLM Credentials (Optional for local benchmark)
   GROQ_API_KEY=your_key_here
   
   # Costs per operation
   COST_PER_LLM_CALL=0.01
   COST_PER_URL_SCRAPE=0.02
   ```

3. **Start the FastAPI Web App**
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

---

## 2. SQLite Database & Storage Engine

### WAL (Write-Ahead Logging) Optimization
SQLite is configured by default to use **WAL mode**. WAL offers significantly faster write concurrency and transactional performance:
- Readers do not block writers.
- Writers do not block readers.
- Writes are performed atomically, preventing database corruption during hard scrapers restarts or system crashes.

### Automatic JSON-to-SQLite Migration
If you are upgrading a legacy DataForge installation that used a `jobs_state.json` file:
- On startup, the SQLite engine automatically detects the legacy JSON file.
- It parses and migrates all existing job records and recycle bin logs directly into the fresh SQLite database.
- Legacy list/dict structures (like URLs and results) are safely converted into dynamic, queryable SQLite schema fields.

### Customizing the DB Location
By default, the database is stored alongside the state file under `backend/data/jobs_state.db`. You can customize this by changing `DATAFORGE_STATE_FILE` in your `.env` or system environment:
```bash
export DATAFORGE_STATE_FILE="/custom/path/to/my_state.json"
# The system will automatically resolve the DB path to "/custom/path/to/my_state.db"
```

### Health Monitoring & Integrity
DataForge exposes the following status and readiness endpoints:
1. **`/api/system/status`**: Returns `"status": "online"` along with job counts, runtime limits, and active database state details.
2. **`/api/system/storage/status`**: Exposes details about the SQLite storage engine (WAL mode, migrations status, database path, etc.).
3. **`/ready`**: Returns `"status": "ready"` once FastAPI startup checks and recovery rehydrations complete.

---

## 3. Production Staging Checklist

Before promoting DataForge Scraper from staging to production, verify that all items on this checklist are fully satisfied:

- [ ] **SQLite WAL Mode Enabled**: Confirm readers and writers do not block each other by running database concurrency checks.
- [ ] **DATAFORGE_STATE_FILE Configuration**: Set to a persistent disk path (e.g., in Docker volumes) to avoid state loss on container restart.
- [ ] **Health Check `/api/system/status` Healthy**: Query the status endpoint and ensure it reports `status: "online"`.
- [ ] **Readiness Check `/ready` Ready**: Query `/ready` and verify it reports `status: "ready"`.
- [ ] **Cancellation Test Passed**: Verify that in-flight jobs stop immediately and update their status to `CANCELED` when cancel is requested.
- [ ] **Restart Recovery Test Passed**: Confirm active jobs are cleanly transitioned to `FAILED` with a recovery log when database connection starts after an ungraceful termination.
- [ ] **Benchmark Suite Passed**: Run `.venv/bin/pytest backend/tests/test_benchmark_suite.py` to ensure high extraction success (>85%) and 100% zero-result truthfulness.
- [ ] **Isolated LLM Tests**: Ensure no live Groq API keys are needed to run regression checks (environment variable mocks must remain deterministic).
- [ ] **Logs Directory Writable**: Ensure path configurations for logging files are fully writable by the running user/process.
- [ ] **Results Offload Directory Writable**: Verify that folders for exported scrapings have the necessary read/write permissions.

---

## 4. SQLite Backup and Restore Operations

SQLite databases in production require safe, online hot-backups to prevent locks and corruption during active scrapers. Follow these guidelines to safely back up and restore your SQLite database:

### Safe Online Hot-Backup (Recommended)

Since DataForge runs in WAL mode, running `cp` directly on the database file is unsafe as active transactions may be committed or in-progress. Instead, use SQLite's official online backup API:

```bash
# Safely perform an online hot-backup of the live database
sqlite3 data/jobs_state.db ".backup data/jobs_state_backup.db"
```

This command is non-blocking:
- Active network scraping writes can continue seamlessly.
- Active readers can read without interruptions.

### Restore Procedure

To restore from a backup:
1. Stop the DataForge FastAPI service container/process.
2. Replace the main database file with the backup:
   ```bash
   cp data/jobs_state_backup.db data/jobs_state.db
   ```
3. Remove any left-over WAL journal files to ensure a clean boot state:
   ```bash
   rm -f data/jobs_state.db-shm data/jobs_state.db-wal
   ```
4. Restart the FastAPI service. DataForge will automatically connect and resume operations using the restored state.

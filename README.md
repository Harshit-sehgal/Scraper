# DataForge Studio

DataForge Studio is a FastAPI + vanilla JS web scraping studio for building schema-driven extraction jobs in manual and auto-discovery modes.

## What Is New In This Makeover

- Durable state persistence for jobs and recycle bin across backend restarts.
- Job cancellation endpoint and UI controls for active jobs.
- Live engine status panel backed by server telemetry.
- Runtime limits configurable via environment variables.
- Stronger mode-aware input validation (auto requires topic, manual requires real URLs).
- Richer quality report metrics including `overall_score`, `coverage_ratio`, and average source trust.
- Better auto mode controls in UI (`max pages to discover`, `max URLs per domain`).

## Project Layout

- `backend/app/main.py` FastAPI APIs, job orchestration, exports, quality reporting.
- `backend/app/scraper.py` scraping + AI extraction pipeline.
- `backend/app/discovery.py` search/discovery and source classification.
- `backend/app/state_store.py` durable JSON persistence.
- `frontend/index.html` dashboard UI.
- `frontend/app.js` UI behavior and API client logic.
- `frontend/styles.css` styling.

## Quick Start

1. Create/activate environment (already prepared in this workspace as `.venv`).
2. Install backend dependencies if needed.
3. Start server:

```bash
cd backend
../.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

4. Open dashboard at `http://127.0.0.1:8000/app`.

## Runtime Environment Variables

- `DATAFORGE_STATE_FILE` path to persistence JSON file.
- `DATAFORGE_MAX_DISCOVERY_URLS` maximum discovered URLs per auto job.
- `DATAFORGE_MAX_RECORDS_PER_SOURCE` maximum records retained per scraped URL after dedupe (contact rows are prioritized when trimming).
- `DATAFORGE_PER_URL_TIMEOUT_SECONDS` timeout per URL scrape.
- `DATAFORGE_MAX_JOB_RUNTIME_SECONDS` max wall time per job.
- `DATAFORGE_AI_STRUCTURING_TIMEOUT_SECONDS` timeout for AI structuring phase.
- `DATAFORGE_INSIGHT_TIMEOUT_SECONDS` timeout for AI insight generation.
- `DATAFORGE_MAX_JOB_HISTORY` max number of jobs retained in active store/state file.
- `DATAFORGE_MAX_RECYCLE_BIN_HISTORY` max recycle-bin history retained.

## Operational Endpoints

- `GET /api/system/status` server + jobs telemetry and runtime limits.
- `POST /api/jobs` create job.
- `POST /api/jobs/{job_id}/cancel` request cancellation for active job.
- `POST /api/jobs/{job_id}/reclean` rerun AI cleaning on existing results.
- `DELETE /api/jobs/cleanup/terminal?keep_recent=5` bulk-clear terminal jobs while keeping recent history.
- `DELETE /api/recycle_bin` empty recycle bin in one action.

## Frontend UX Tips

- Keyboard shortcuts:
	- `N` open New Job
	- `/` focus search input (jobs/results/new intent)
	- `Esc` clear active search
- In results table, double-click a cell to copy its value.

## Testing

Run fast regression tests (isolated, no live scraping calls):

```bash
cd /home/harshit/Documents/Work/Money/scraper
.venv/bin/python -m pytest
```

Run repeated runtime smoke cycles against a running backend:

```bash
cd /home/harshit/Documents/Work/Money/scraper
.venv/bin/python backend/tests/smoke_runtime_loop.py --cycles 5
```

Useful smoke options:

- Enforce cancel path strictly (default): `--expected-terminal canceled`
- Allow any terminal state when doing exploratory runs: `--expected-terminal any`
- Cleanup old terminal jobs after the run: `--cleanup-terminal --cleanup-keep-recent 5`

## Notes

- Jobs that were in progress during a backend restart are recovered as failed with a restart-recovery message.
- Auto mode uses discovery caps and per-domain limits to avoid long, unbounded runs.


"""
FastAPI Main Server — DataForge General-Purpose Web Scraper API.
"""

import asyncio
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.routers.jobs import create_jobs_router
from app.routers.exports import create_exports_router
from app.services.job_runner import run_job
from app.services.state import persist_state
from app.state_store import load_state
from app.utils.env import env_int

app = FastAPI(
    title="DataForge — General-Purpose Web Scraper",
    description="AI-powered scraper that extracts structured data from any website",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Runtime safety rails
CONFIG = {
    "max_discovery_urls": env_int("DATAFORGE_MAX_DISCOVERY_URLS", 20, minimum=1, maximum=100),
    "per_url_timeout_seconds": env_int("DATAFORGE_PER_URL_TIMEOUT_SECONDS", 120, minimum=10, maximum=900),
    "max_job_runtime_seconds": env_int("DATAFORGE_MAX_JOB_RUNTIME_SECONDS", 1800, minimum=60, maximum=14400),
    "ai_structuring_timeout_seconds": env_int("DATAFORGE_AI_STRUCTURING_TIMEOUT_SECONDS", 240, minimum=15, maximum=1800),
    "insight_timeout_seconds": env_int("DATAFORGE_INSIGHT_TIMEOUT_SECONDS", 25, minimum=5, maximum=300),
    "max_job_history": env_int("DATAFORGE_MAX_JOB_HISTORY", 300, minimum=25, maximum=5000),
    "max_recycle_bin_history": env_int("DATAFORGE_MAX_RECYCLE_BIN_HISTORY", 300, minimum=25, maximum=5000),
}

# Durable job store
jobs_store, recycle_bin_store = load_state()

def _persist_state_wrapper():
    persist_state(
        jobs_store=jobs_store,
        recycle_bin_store=recycle_bin_store,
        max_job_history=CONFIG["max_job_history"],
        max_recycle_bin_history=CONFIG["max_recycle_bin_history"]
    )

def _schedule_background_task(coro):
    return asyncio.create_task(coro)

async def _run_job_wrapper(job_id: str):
    await run_job(
        job_id=job_id,
        jobs_store=jobs_store,
        persist_state_fn=_persist_state_wrapper,
        max_discovery_urls=CONFIG["max_discovery_urls"],
        max_job_runtime_seconds=CONFIG["max_job_runtime_seconds"],
        per_url_scrape_timeout_seconds=CONFIG["per_url_timeout_seconds"],
        ai_structuring_timeout_seconds=CONFIG["ai_structuring_timeout_seconds"],
        insight_timeout_seconds=CONFIG["insight_timeout_seconds"],
    )

# Include Routers
app.include_router(
    create_jobs_router(
        jobs_store=jobs_store,
        recycle_bin_store=recycle_bin_store,
        persist_state_fn=_persist_state_wrapper,
        schedule_task_fn=_schedule_background_task,
        run_job_coro_fn=_run_job_wrapper,
        config=CONFIG
    )
)

app.include_router(
    create_exports_router(jobs_store=jobs_store)
)

# Serve Frontend
FRONTEND_DIR = Path(__file__).parent.parent.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/app", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")

@app.get("/")
async def root():
    return {"message": "DataForge API v2", "docs": "/docs", "dashboard": "/app"}

@app.get("/api/system/status")
async def system_status():
    from app.models import JobStatus
    counts = {s.value: 0 for s in JobStatus}
    for job in jobs_store.values():
        status_key = str(job.status.value if isinstance(job.status, JobStatus) else job.status)
        if status_key not in counts:
            counts[status_key] = 0
        counts[status_key] += 1

    active = counts.get(JobStatus.PENDING.value, 0) + counts.get(JobStatus.DISCOVERING.value, 0) + counts.get(JobStatus.RUNNING.value, 0)

    from app.state_store import get_state_file_path
    return {
        "status": "online",
        "jobs": {
            "total": len(jobs_store),
            "active": active,
            "completed": counts.get(JobStatus.COMPLETED.value, 0),
            "failed": counts.get(JobStatus.FAILED.value, 0),
            "canceled": counts.get(JobStatus.CANCELED.value, 0),
        },
        "runtime_limits": CONFIG,
        "state_file": str(get_state_file_path()),
    }

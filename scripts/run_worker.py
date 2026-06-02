#!/usr/bin/env python3
"""
DataForge Worker — standalone process that executes queued jobs.

Runs as a background worker in production:
- Connects to the shared SQLite/Postgres job store
- Picks up pending tasks from the worker queue
- Handles job scraping, retries, and error recovery
- Reports progress and completion back to the queue

Usage:
    python scripts/run_worker.py              # Default: 4 workers
    python scripts/run_worker.py --workers 8   # Scale up
    python scripts/run_worker.py --once        # Single task, then exit
"""

import argparse
import asyncio
import logging
import os
import signal
import sys
import time

# Ensure backend is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("worker")


async def scrape_job_handler(task) -> dict:
    """Handler for 'scrape_job' tasks — executes a full job."""
    from app.config import settings
    from app.services.job_runner import run_job
    from app.storage_interface import get_job_repository

    job_id = task.payload.get("job_id")
    if not job_id:
        raise ValueError(f"No job_id in task payload: {task}")

    repo = get_job_repository()
    jobs_store, recycle_bin_store, _ = repo.load_all(recover_in_progress=False)

    job = jobs_store.get(job_id)
    if not job:
        raise ValueError(f"Job not found: {job_id}")

    logger.info("Worker picked up job: %s (%s)", job.name, job_id)

    await run_job(
        job_id=job_id,
        jobs_store=jobs_store,
        persist_state_fn=lambda: repo.save_all(jobs_store, recycle_bin_store),
        max_discovery_urls=settings.MAX_DISCOVERY_URLS,
        max_job_runtime_seconds=settings.MAX_JOB_RUNTIME_SECONDS,
        per_url_scrape_timeout_seconds=settings.PER_URL_TIMEOUT_SECONDS,
        ai_structuring_timeout_seconds=settings.AI_STRUCTURING_TIMEOUT_SECONDS,
        insight_timeout_seconds=settings.INSIGHT_TIMEOUT_SECONDS,
        persist_state_single_fn=lambda: repo.save_single(jobs_store[job_id]),
        persist_state_single_critical_fn=lambda: repo.save_single(jobs_store[job_id]),
    )

    return {
        "job_id": job_id,
        "status": job.status.value if hasattr(job.status, "value") else str(job.status),
        "total_records": job.total_records,
    }


async def main():
    parser = argparse.ArgumentParser(description="DataForge Worker")
    parser.add_argument("--workers", type=int, default=4, help="Max concurrent workers")
    parser.add_argument("--once", action="store_true", help="Process one task then exit")
    args = parser.parse_args()

    from app.worker_queue import Priority, get_worker_queue

    queue = get_worker_queue()
    queue._max_concurrency = args.workers
    queue.register_handler("scrape_job", scrape_job_handler)

    # Set up graceful shutdown
    shutdown_event = asyncio.Event()

    def _signal_handler():
        logger.info("Shutdown signal received, draining workers...")
        shutdown_event.set()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except (ValueError, RuntimeError):
            pass

    await queue.start()
    logger.info(
        "Worker ready: %d max concurrency, polling every %.1fs",
        queue._max_concurrency,
        queue._poll_interval,
    )

    if args.once:
        # Single-task mode: enqueue one specific job and wait for completion
        job_id = os.getenv("DATAFORGE_JOB_ID")
        if not job_id:
            raise SystemExit("DATAFORGE_JOB_ID is required when using --once")
        task_id = await queue.enqueue(
            "scrape_job",
            {"job_id": job_id},
            priority=Priority.HIGH,
        )
        logger.info("Enqueued single task: %s (job_id=%s)", task_id, job_id)
        # Poll until task reaches terminal state using get_task_state
        terminal_task_statuses = {"completed", "failed", "dead_letter", "cancelled"}
        deadline = time.time() + 600  # Max 10 minute wait
        while time.time() < deadline:
            task_state = queue.get_task_state(task_id)
            if task_state is not None:
                ts = task_state.get("status", "")
                if ts in terminal_task_statuses:
                    logger.info(
                        "Task %s reached terminal state: %s",
                        task_id,
                        ts,
                    )
                    break
                logger.debug("Task %s status: %s", task_id, ts)
            await asyncio.sleep(5)
    else:
        # Continuous mode: run until shutdown
        await shutdown_event.wait()
        logger.info("Shutting down worker...")

    await queue.stop(drain=True)
    logger.info("Worker stopped.")


if __name__ == "__main__":
    asyncio.run(main())

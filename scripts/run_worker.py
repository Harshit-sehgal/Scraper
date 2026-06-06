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
        msg = f"No job_id in task payload: {task}"
        raise ValueError(msg)

    repo = get_job_repository()
    jobs_store, recycle_bin_store, _ = repo.load_all(recover_in_progress=False)

    job = jobs_store.get(job_id)
    if not job:
        msg = f"Job not found: {job_id}"
        raise ValueError(msg)

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
    parser.add_argument(
        "--heartbeat-interval",
        type=float,
        default=15.0,
        help="Seconds between heartbeat writes (default: 15)",
    )
    parser.add_argument(
        "--heartbeat-ttl",
        type=float,
        default=60.0,
        help="Seconds before a missing heartbeat is considered dead (default: 60)",
    )
    args = parser.parse_args()

    from app.worker_queue import get_worker_queue

    queue = get_worker_queue()
    queue.set_max_concurrency(args.workers)
    queue.register_handler("scrape_job", scrape_job_handler)

    # Start the heartbeat so Docker healthcheck can verify the worker is alive
    # (skipped in --once mode — single-task execution is too brief to benefit)
    heartbeat = None
    if not args.once:
        from app.worker_heartbeat import HeartbeatManager

        heartbeat = HeartbeatManager(interval=args.heartbeat_interval, ttl=args.heartbeat_ttl)
        await heartbeat.start()

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
        args.workers,
        queue.get_poll_interval(),
    )

    if args.once:
        # Drain mode: dequeue and process whatever pending tasks exist,
        # then exit. This is the *opposite* of the original behaviour,
        # which (mis)used --once to enqueue a fresh scrape — that turned
        # the standalone worker into a job producer and broke operator
        # expectations ("run what is queued, not create more work").
        deadline = time.time() + 600  # 10-minute upper bound
        processed = 0
        while time.time() < deadline:
            task = await queue.dequeue(timeout=2.0)
            if task is None:
                if processed == 0:
                    logger.info("No pending tasks found; exiting.")
                else:
                    logger.info("Queue drained after %d task(s).", processed)
                break
            processed += 1
            handler = queue._handlers.get(task.type)  # internal: enqueue→execute symmetry
            if handler is None:
                await queue.fail(task.id, f"No handler for task type: {task.type}", retry=False)
                continue
            try:
                result = await asyncio.wait_for(handler(task), timeout=task.timeout_seconds)
                if result is False:
                    await queue.fail(task.id, "Handler returned False", retry=True)
                else:
                    await queue.complete(task.id, result)
            except Exception as exc:  # noqa: BLE001
                await queue.fail(task.id, f"{type(exc).__name__}: {exc}", retry=True)
        logger.info("Drain mode processed %d task(s).", processed)
    else:
        # Continuous mode: run until shutdown
        await shutdown_event.wait()
        logger.info("Shutting down worker...")

    await queue.stop(drain=True)
    if heartbeat is not None:
        await heartbeat.stop()
    logger.info("Worker stopped.")


if __name__ == "__main__":
    asyncio.run(main())

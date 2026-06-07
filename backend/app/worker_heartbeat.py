"""Worker Heartbeat Manager — repository-backed worker health tracking.

Replaces the PID-based process-signal healthcheck with a durable DB-backed
approach: the worker writes a heartbeat timestamp every N seconds, and the
Docker healthcheck (or monitoring system) verifies that the heartbeat is
recent by querying the same database.

Usage in ``scripts/run_worker.py``::

    manager = HeartbeatManager()
    await manager.start()
    # ... worker loop ...
    await manager.stop()
"""

from __future__ import annotations

import asyncio
import logging
import os
import socket

from app.utils.worker_id import resolve_worker_id

logger = logging.getLogger(__name__)

_DEFAULT_INTERVAL = 15.0  # seconds between heartbeats
_DEFAULT_TTL = 60.0  # seconds before a worker is considered dead


class HeartbeatManager:
    """Periodically records a heartbeat timestamp to the configured repository.

    The worker calls :meth:`start` after initialisation and :meth:`stop`
    during graceful shutdown. The heartbeat row is upserted into the
    ``worker_heartbeats`` table (created by schema migration v5).
    """

    def __init__(
        self,
        interval: float = _DEFAULT_INTERVAL,
        ttl: float = _DEFAULT_TTL,
    ) -> None:
        self._interval = interval
        self._ttl = ttl
        self._worker_id: str = resolve_worker_id()
        self._hostname: str = socket.gethostname()
        self._pid: int = os.getpid()
        self._task: asyncio.Task | None = None
        self._running = False

    # ── Public API ────────────────────────────────────────────────────

    @property
    def worker_id(self) -> str:
        """Unique identifier for this worker instance."""
        return self._worker_id

    @property
    def interval(self) -> float:
        """Heartbeat interval in seconds."""
        return self._interval

    async def start(self) -> None:
        """Start the background heartbeat loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info(
            "Heartbeat started: worker_id=%s interval=%.1fs ttl=%.1fs",
            self._worker_id,
            self._interval,
            self._ttl,
        )

    async def stop(self) -> None:
        """Stop the heartbeat loop and wait for the task to finish."""
        self._running = False
        if self._task:
            self._task.cancel()
            from contextlib import suppress

            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        logger.info("Heartbeat stopped: worker_id=%s", self._worker_id)

    # ── Internal ──────────────────────────────────────────────────────

    async def _loop(self) -> None:
        """Background loop: record heartbeat every ``interval`` seconds."""
        while self._running:
            try:
                await self._record_heartbeat()
            except Exception as exc:
                logger.warning(
                    "Failed to record heartbeat for %s: %s",
                    self._worker_id,
                    exc,
                )
            await asyncio.sleep(self._interval)

    async def _record_heartbeat(self) -> None:
        """Write a heartbeat row via the configured repository."""
        from app.storage_interface import get_job_repository

        repo = get_job_repository()
        await asyncio.to_thread(
            repo.record_worker_heartbeat,
            self._worker_id,
            self._hostname,
            self._pid,
        )

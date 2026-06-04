"""Postgres-backed Worker Queue — async job processing with psycopg2 persistence.

Provides the same interface as WorkerQueue (SQLite) but uses Postgres for
durable queue storage, enabling multi-node production deployments.

Usage:
    queue = get_postgres_worker_queue()
    await queue.enqueue("scrape_job", {"job_id": "abc"}, priority=Priority.HIGH)
    task = await queue.dequeue()
    await queue.complete(task.id)
"""

import asyncio
import datetime
import json
import logging
import threading
import time
from collections.abc import Callable

from app.postgres_repository import _conn, _execute, _fetch_all, _fetch_one
from app.worker_queue import Priority, QueueTask

logger = logging.getLogger(__name__)


_CURRENT_QUEUE_SCHEMA_VERSION = 3


def _ensure_schema():
    """Create queue tables and run schema migrations."""
    with _conn() as conn:
        # Check table existence via information_schema instead of try / except,
        # which would leave the connection in an aborted transaction state.
        table_exists = _fetch_one(
            conn,
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = 'queue_schema_version'",
        )
        if table_exists:
            # Verify the table has the expected structure
            try:
                old_row = _fetch_one(conn, "SELECT id FROM queue_schema_version LIMIT 1")
            except Exception:
                old_row = None
            if old_row is None:
                _execute(conn, "DROP TABLE IF EXISTS queue_schema_version CASCADE")

        _execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS queue_schema_version (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                version INTEGER NOT NULL
            )
        """,
        )
        row = _fetch_one(conn, "SELECT version FROM queue_schema_version WHERE id = 1")
        current = row["version"] if row and row.get("version") is not None else 0

        if current < _CURRENT_QUEUE_SCHEMA_VERSION:
            if current < 1:
                _execute(
                    conn,
                    """
                    CREATE TABLE IF NOT EXISTS queue_tasks (
                        id TEXT PRIMARY KEY,
                        type TEXT NOT NULL,
                        payload TEXT NOT NULL DEFAULT '{}',
                        priority INTEGER NOT NULL DEFAULT 2,
                        status TEXT NOT NULL DEFAULT 'pending',
                        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                        started_at TIMESTAMP,
                        completed_at TIMESTAMP,
                        attempts INTEGER NOT NULL DEFAULT 0,
                        max_attempts INTEGER NOT NULL DEFAULT 3,
                        last_error TEXT,
                        scheduled_at TIMESTAMP NOT NULL DEFAULT NOW(),
                        timeout_seconds INTEGER NOT NULL DEFAULT 300
                    )
                """,
                )

                _execute(
                    conn,
                    """
                    CREATE INDEX IF NOT EXISTS idx_queue_tasks_status_priority
                        ON queue_tasks(status, priority)
                """,
                )

                _execute(
                    conn,
                    """
                    CREATE INDEX IF NOT EXISTS idx_queue_tasks_scheduled
                        ON queue_tasks(scheduled_at)
                """,
                )

                _execute(
                    conn,
                    """
                    CREATE TABLE IF NOT EXISTS queue_task_history (
                        id TEXT PRIMARY KEY,
                        type TEXT NOT NULL,
                        payload TEXT NOT NULL DEFAULT '{}',
                        priority INTEGER NOT NULL DEFAULT 2,
                        status TEXT NOT NULL,
                        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                        started_at TIMESTAMP,
                        completed_at TIMESTAMP,
                        attempts INTEGER NOT NULL DEFAULT 0,
                        max_attempts INTEGER NOT NULL DEFAULT 3,
                        last_error TEXT,
                        timeout_seconds INTEGER NOT NULL DEFAULT 300,
                        finished_at TIMESTAMP NOT NULL DEFAULT NOW()
                    )
                """,
                )

                _execute(
                    conn,
                    """
                    CREATE INDEX IF NOT EXISTS idx_queue_task_history_type
                        ON queue_task_history(type)
                """,
                )

                _execute(
                    conn,
                    """
                    CREATE INDEX IF NOT EXISTS idx_queue_task_history_finished
                        ON queue_task_history(finished_at DESC)
                """,
                )
                current = 1

            if current < 2:
                # Add result column (used for storing successful task results)
                try:
                    _execute(conn, "ALTER TABLE queue_task_history ADD COLUMN result TEXT")
                except Exception:  # nosec B110
                    pass
                current = 2

            if current < 3:
                # Add execution_time_ms column for tracking task latencies
                try:
                    _execute(conn, "ALTER TABLE queue_task_history ADD COLUMN execution_time_ms INTEGER")
                except Exception:  # nosec B110
                    pass
                current = 3

            _execute(
                conn,
                "INSERT INTO queue_schema_version (id, version) VALUES (1, %s) ON CONFLICT (id) DO UPDATE SET version = EXCLUDED.version",
                (current,),
            )
            logger.info("Postgres queue schema migrated to version %d", current)
        else:
            logger.debug("Postgres queue schema already at version %d", _CURRENT_QUEUE_SCHEMA_VERSION)


class PostgresWorkerQueue:
    """Worker queue backed by Postgres via the shared psycopg2 pool.

    Mirrors the WorkerQueue (SQLite) interface so callers are interchangeable.
    """

    def __init__(self, max_concurrency: int = 5, poll_interval: float = 1.0):
        self._max_concurrency = max_concurrency
        self._poll_interval = poll_interval
        self._running = False
        self._worker_task: asyncio.Task | None = None
        self._in_flight: dict[str, asyncio.Task] = {}
        self._handlers: dict[str, Callable] = {}
        self._in_flight_lock = asyncio.Lock()
        _ensure_schema()

    # ─── Task registration ─────────────────────────────────────────────

    def register_handler(self, task_type: str, handler: Callable):
        """Register an async handler function for a task type.

        The handler receives (task: QueueTask) and should return True on success.
        """
        self._handlers[task_type] = handler

    # ─── Task lifecycle ────────────────────────────────────────────────

    async def enqueue(
        self,
        task_type: str,
        payload: dict | None = None,
        priority: Priority = Priority.NORMAL,
        max_attempts: int = 3,
        timeout_seconds: int = 300,
        task_id: str | None = None,
        scheduled_at: str | None = None,
    ) -> str:
        """Add a new task to the queue. Returns the task ID."""
        task = QueueTask(
            task_type=task_type,
            payload=payload,
            priority=priority,
            max_attempts=max_attempts,
            timeout_seconds=timeout_seconds,
            task_id=task_id,
            scheduled_at=scheduled_at,
        )

        async with self._in_flight_lock:
            await asyncio.to_thread(
                self._enqueue_sync,
                task.id,
                task.type,
                json.dumps(task.payload),
                int(task.priority),
                task.status,
                task.attempts,
                task.max_attempts,
                task.timeout_seconds,
            )

        return task.id

    def _enqueue_sync(
        self,
        task_id: str,
        task_type: str,
        payload_json: str,
        priority: int,
        status: str,
        attempts: int,
        max_attempts: int,
        timeout_seconds: int,
    ) -> None:
        """Synchronous enqueue — runs in a thread to avoid blocking the event loop.

        Uses ``NOW()`` for both ``created_at`` and ``scheduled_at`` so the stored
        timestamps are in Postgres server time (UTC), matching the ``NOW()``
        reference used by the dequeue query.  This avoids timezone mismatches
        when Python's ``datetime.datetime.now()`` returns a different timezone
        (e.g. IST) than the Postgres server (UTC).
        """
        with _conn() as conn:
            _execute(
                conn,
                """INSERT INTO queue_tasks
                   (id, type, payload, priority, status, created_at,
                    scheduled_at, attempts, max_attempts, timeout_seconds)
                   VALUES (%s, %s, %s, %s, %s, NOW(), NOW(), %s, %s, %s)
                   ON CONFLICT (id) DO NOTHING""",
                (
                    task_id,
                    task_type,
                    payload_json,
                    priority,
                    status,
                    attempts,
                    max_attempts,
                    timeout_seconds,
                ),
            )

    async def dequeue(self, timeout: float = 5.0) -> QueueTask | None:
        """Dequeue the highest-priority pending task.

        Blocks up to *timeout* seconds if the queue is empty.
        Returns None if the timeout expires.
        Uses ``asyncio.to_thread`` to avoid blocking the event loop
        on the synchronous ``_dequeue_one`` call.
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            task = await asyncio.to_thread(self._dequeue_one)
            if task:
                return task
            await asyncio.sleep(0.25)
        return None

    def _dequeue_one(self) -> QueueTask | None:
        """Synchronous dequeue from Postgres with priority ordering.

        This is called from an async dequeue loop wrapped via
        ``asyncio.to_thread`` to avoid blocking the event loop.
        """
        try:
            with _conn() as conn:
                # Atomically claim the highest-priority pending task
                row = _fetch_one(
                    conn,
                    """UPDATE queue_tasks
                       SET status = 'running',
                           started_at = NOW(),
                           attempts = attempts + 1
                       WHERE id = (
                           SELECT id FROM queue_tasks
                           WHERE status = 'pending'
                             AND scheduled_at <= NOW()
                           ORDER BY priority ASC, created_at ASC
                           LIMIT 1 FOR UPDATE SKIP LOCKED
                       )
                       RETURNING *""",
                )

                if row is None:
                    return None

                # Normalize Postgres datetime objects to strings for QueueTask
                # compatibility
                _ts_fields = ("created_at", "started_at", "completed_at", "scheduled_at", "finished_at")
                for _f in _ts_fields:
                    v = row.get(_f)
                    if isinstance(v, (datetime.datetime, datetime.date)):
                        row[_f] = v.strftime("%Y-%m-%d %H:%M:%S")

                task = QueueTask.from_dict(
                    {
                        **row,
                        "payload": json.loads(row["payload"]),
                    },
                )
                return task
        except Exception as e:
            logger.error("Postgres dequeue error: %s", e, exc_info=True)
            return None

    async def complete(self, task_id: str, result: dict | None = None):
        """Mark a task as completed successfully."""
        async with self._in_flight_lock:
            await asyncio.to_thread(
                self._complete_sync,
                task_id,
                json.dumps(result) if result else None,
            )

    def _complete_sync(self, task_id: str, result_json: str | None) -> None:
        """Synchronous complete — runs in a thread to avoid blocking the event loop."""
        with _conn() as conn:
            row = _fetch_one(conn, "SELECT * FROM queue_tasks WHERE id = %s", (task_id,))
            if row:
                _execute(
                    conn,
                    """INSERT INTO queue_task_history
                       (id, type, payload, priority, status, created_at,
                        started_at, completed_at, attempts, max_attempts,
                        last_error, result, timeout_seconds, finished_at)
                       VALUES (%s, %s, %s, %s, 'completed', %s,
                               %s, NOW(), %s, %s, %s, %s, %s, NOW())""",
                    (
                        row["id"],
                        row["type"],
                        row["payload"],
                        row["priority"],
                        row["created_at"],
                        row.get("started_at"),
                        row["attempts"],
                        row["max_attempts"],
                        None,
                        result_json,
                        row.get("timeout_seconds", 300),
                    ),
                )
                _execute(conn, "DELETE FROM queue_tasks WHERE id = %s", (task_id,))

    async def fail(
        self,
        task_id: str,
        error: str,
        retry: bool = True,
    ):
        """Mark a task as failed. Retries if attempts remain."""
        async with self._in_flight_lock:
            await asyncio.to_thread(
                self._fail_sync,
                task_id,
                error,
                retry,
            )

    def _fail_sync(self, task_id: str, error: str, retry: bool = True) -> None:
        """Synchronous fail — runs in a thread to avoid blocking the event loop."""
        with _conn() as conn:
            row = _fetch_one(
                conn,
                "SELECT attempts, max_attempts, * FROM queue_tasks WHERE id = %s",
                (task_id,),
            )

            if row:
                attempts = row["attempts"]
                max_attempts = row["max_attempts"]

                if retry and attempts < max_attempts:
                    # Schedule retry with exponential backoff
                    backoff = min(2 ** (attempts - 1) * 30, 3600)
                    _execute(
                        conn,
                        "UPDATE queue_tasks SET status = 'pending', last_error = %s, "
                        "scheduled_at = NOW() + (%s * INTERVAL '1 second') WHERE id = %s",
                        (error, backoff, task_id),
                    )
                    logger.info(
                        "Task %s failed (attempt %d/%d). Retrying in %ds: %s",
                        task_id,
                        attempts,
                        max_attempts,
                        backoff,
                        error,
                    )
                else:
                    # Move to dead letter (archive to history)
                    _execute(
                        conn,
                        """INSERT INTO queue_task_history
                           (id, type, payload, priority, status, created_at,
                            started_at, completed_at, attempts, max_attempts,
                            last_error, result, timeout_seconds, finished_at)
                           VALUES (%s, %s, %s, %s, 'dead_letter', %s,
                                   %s, NOW(), %s, %s, %s, %s, %s, NOW())""",
                        (
                            row["id"],
                            row["type"],
                            row["payload"],
                            row["priority"],
                            row["created_at"],
                            row.get("started_at"),
                            row["attempts"],
                            row["max_attempts"],
                            error,
                            None,
                            row.get("timeout_seconds", 300),
                        ),
                    )
                    _execute(conn, "DELETE FROM queue_tasks WHERE id = %s", (task_id,))
                    logger.warning(
                        "Task %s moved to dead letter after %d attempts: %s",
                        task_id,
                        attempts,
                        error,
                    )

    async def cancel(self, task_id: str) -> bool:
        """Cancel a task. Handles both pending and in-flight tasks.
        Returns True if cancelled.
        """
        async with self._in_flight_lock:
            # Check in-flight tasks first
            if task_id in self._in_flight:
                flight_task = self._in_flight[task_id]
                flight_task.cancel()
                result = await asyncio.to_thread(
                    self._cancel_in_flight_sync,
                    task_id,
                )
                return result

            # Check pending tasks
            result = await asyncio.to_thread(
                self._cancel_pending_sync,
                task_id,
            )
            return result

    def _cancel_in_flight_sync(self, task_id: str) -> bool:
        """Synchronous cancel for in-flight tasks — runs in a thread."""
        with _conn() as conn:
            row = _fetch_one(
                conn,
                "SELECT * FROM queue_tasks WHERE id = %s",
                (task_id,),
            )
            if row:
                _execute(
                    conn,
                    """INSERT INTO queue_task_history
                       (id, type, payload, priority, status, created_at,
                        started_at, completed_at, attempts, max_attempts,
                        last_error, result, timeout_seconds, finished_at)
                       VALUES (%s, %s, %s, %s, 'cancelled', %s,
                               %s, NOW(), %s, %s, %s, %s, %s, NOW())""",
                    (
                        row["id"],
                        row["type"],
                        row["payload"],
                        row["priority"],
                        row["created_at"],
                        row.get("started_at"),
                        row["attempts"],
                        row["max_attempts"],
                        "Cancelled by user (in-flight)",
                        None,
                        row.get("timeout_seconds", 300),
                    ),
                )
                _execute(conn, "DELETE FROM queue_tasks WHERE id = %s", (task_id,))
            return True

    def _cancel_pending_sync(self, task_id: str) -> bool:
        """Synchronous cancel for pending tasks — runs in a thread."""
        with _conn() as conn:
            row = _fetch_one(
                conn,
                "SELECT * FROM queue_tasks WHERE id = %s AND status = 'pending'",
                (task_id,),
            )
            if row is None:
                return False
            _execute(
                conn,
                """INSERT INTO queue_task_history
                   (id, type, payload, priority, status, created_at,
                    started_at, completed_at, attempts, max_attempts,
                    last_error, result, timeout_seconds, finished_at)
                   VALUES (%s, %s, %s, %s, 'cancelled', %s,
                           %s, NOW(), %s, %s, %s, %s, %s, NOW())""",
                (
                    row["id"],
                    row["type"],
                    row["payload"],
                    row["priority"],
                    row["created_at"],
                    row.get("started_at"),
                    row["attempts"],
                    row["max_attempts"],
                    "Cancelled by user",
                    None,
                    row.get("timeout_seconds", 300),
                ),
            )
            _execute(conn, "DELETE FROM queue_tasks WHERE id = %s", (task_id,))
            return True

    # ─── Worker loop ───────────────────────────────────────────────────

    async def start(self):
        """Start the background worker loop with recovery of stuck tasks."""
        if self._running:
            return
        await asyncio.to_thread(self._recover_stuck_tasks)
        self._running = True
        self._worker_task = asyncio.create_task(self._worker_loop())
        logger.info(
            "Postgres worker queue started: max_concurrency=%d, poll_interval=%.1fs",
            self._max_concurrency,
            self._poll_interval,
        )

    def _recover_stuck_tasks(self):
        """Reset any tasks stuck in 'running' state back to 'pending' for retry.

        Synchronous — called via ``asyncio.to_thread`` to avoid blocking the event loop.
        """
        try:
            with _conn() as conn:
                stuck = _fetch_one(conn, "SELECT COUNT(*) AS cnt FROM queue_tasks WHERE status = 'running'")
                count = stuck["cnt"] if stuck else 0
                if count:
                    _execute(
                        conn,
                        "UPDATE queue_tasks SET status = 'pending', started_at = NULL, "
                        "last_error = 'Recovered after worker restart' "
                        "WHERE status = 'running'",
                    )
                    logger.info("Recovered %d stuck task(s) from previous worker crash", count)
        except Exception as e:
            logger.error("Failed to recover stuck tasks: %s", e)

    async def stop(self, drain: bool = True):
        """Stop the worker loop. Optionally drain in-flight tasks."""
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

        if drain:
            await self._drain_in_flight()

        logger.info("Postgres worker queue stopped (drained=%s)", drain)

    async def _worker_loop(self):
        """Main worker loop: dequeue and dispatch tasks."""
        while self._running:
            try:
                async with self._in_flight_lock:
                    active = len(self._in_flight)
                if active >= self._max_concurrency:
                    await asyncio.sleep(self._poll_interval)
                    continue

                task = await self.dequeue(timeout=self._poll_interval)
                if task is None:
                    continue

                t = asyncio.create_task(self._execute_task(task))

                task_id = task.id

                async with self._in_flight_lock:
                    self._in_flight[task_id] = t

                def _on_task_done(fut: object, tid: str = task_id) -> None:
                    asyncio.ensure_future(self._cleanup_in_flight(tid))

                t.add_done_callback(_on_task_done)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Worker loop error: %s", e, exc_info=True)
                await asyncio.sleep(1)

    async def _execute_task(self, task: QueueTask):
        """Execute a single task with timeout."""
        handler = self._handlers.get(task.type)
        if handler is None:
            logger.error("No handler registered for task type: %s", task.type)
            await self.fail(task.id, f"No handler registered for task type: {task.type}", retry=False)
            return

        try:
            result = await asyncio.wait_for(
                handler(task),
                timeout=task.timeout_seconds,
            )
            if result is False:
                await self.fail(task.id, "Handler returned False", retry=True)
            else:
                await self.complete(task.id, result)
        except asyncio.TimeoutError:
            await self.fail(task.id, f"Timeout after {task.timeout_seconds}s", retry=True)
        except Exception as e:
            await self.fail(task.id, f"{type(e).__name__}: {e}", retry=True)

    async def _cleanup_in_flight(self, task_id: str):
        """Remove a task from the in-flight tracker."""
        async with self._in_flight_lock:
            self._in_flight.pop(task_id, None)

    async def _drain_in_flight(self):
        """Wait for all in-flight tasks to complete."""
        async with self._in_flight_lock:
            tasks = list(self._in_flight.values())
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    # ─── Observability ─────────────────────────────────────────────────

    def get_task_state(self, task_id: str) -> dict | None:
        """Return the current state of a specific task by ID.

        Checks the active queue_tasks first, then falls back to queue_task_history.
        Returns None if the task is not found.

        This method is synchronous and performs blocking DB calls. When called
        from an async context, wrap it with ``await asyncio.to_thread(...)``
        to avoid blocking the event loop.
        """
        try:
            with _conn() as conn:
                row = _fetch_one(
                    conn,
                    "SELECT * FROM queue_tasks WHERE id = %s",
                    (task_id,),
                )
                if row:
                    return row
                row = _fetch_one(
                    conn,
                    "SELECT * FROM queue_task_history WHERE id = %s",
                    (task_id,),
                )
                if row:
                    return row
                return None
        except Exception as e:
            logger.error("Failed to get task state for %s: %s", task_id, e)
            return None

    async def get_task_state_async(self, task_id: str) -> dict | None:
        """Async version of ``get_task_state`` — runs the blocking DB call in a thread."""
        return await asyncio.to_thread(self.get_task_state, task_id)

    def get_status(self) -> dict:
        """Return queue status for monitoring.

        This method is synchronous and performs blocking DB calls. When called
        from an async context, use ``await get_status_async()`` instead.
        """
        try:
            with _conn() as conn:
                pending = _fetch_one(conn, "SELECT COUNT(*) AS cnt FROM queue_tasks WHERE status = 'pending'")
                running = _fetch_one(conn, "SELECT COUNT(*) AS cnt FROM queue_tasks WHERE status = 'running'")
                dead_letter = _fetch_one(
                    conn,
                    "SELECT COUNT(*) AS cnt FROM queue_task_history WHERE status = 'dead_letter'",
                )
                completed_24h = _fetch_one(
                    conn,
                    "SELECT COUNT(*) AS cnt FROM queue_task_history WHERE finished_at >= NOW() - INTERVAL '24 hours'",
                )

                top_pending = _fetch_all(
                    conn,
                    """SELECT id, type, priority, created_at, attempts
                       FROM queue_tasks WHERE status = 'pending'
                       ORDER BY priority ASC, created_at ASC LIMIT 10""",
                )

                return {
                    "ok": True,
                    "backend": "postgres",
                    "pending": pending["cnt"] if pending else 0,
                    "running": running["cnt"] if running else 0,
                    "retrying": 0,
                    "dead_letter": dead_letter["cnt"] if dead_letter else 0,
                    "completed_24h": completed_24h["cnt"] if completed_24h else 0,
                    "max_concurrency": self._max_concurrency,
                    "in_flight": len(self._in_flight),
                    "next_tasks": top_pending,
                }
        except Exception as e:
            logger.error("Failed to get Postgres queue status: %s", e)
            return {"ok": False, "backend": "postgres", "error": str(e), "pending": 0, "running": 0}

    async def get_status_async(self) -> dict:
        """Async version of ``get_status`` — runs the blocking DB call in a thread."""
        return await asyncio.to_thread(self.get_status)

    def get_dead_letter_queue(self, limit: int = 50) -> list[dict]:
        """Return dead letter queue entries."""
        try:
            with _conn() as conn:
                rows = _fetch_all(
                    conn,
                    """SELECT * FROM queue_task_history
                       WHERE status = 'dead_letter'
                       ORDER BY finished_at DESC LIMIT %s""",
                    (limit,),
                )
                return rows
        except Exception as e:
            logger.error("Failed to get dead letter queue: %s", e)
            return []

    async def get_dead_letter_queue_async(self, limit: int = 50) -> list[dict]:
        """Async version of ``get_dead_letter_queue`` — runs the blocking DB call in a thread."""
        return await asyncio.to_thread(self.get_dead_letter_queue, limit)

    def retry_dead_letter(self, task_id: str) -> bool:
        """Re-queue a dead letter task."""
        try:
            with _conn() as conn:
                row = _fetch_one(
                    conn,
                    "SELECT * FROM queue_task_history WHERE id = %s AND status = 'dead_letter'",
                    (task_id,),
                )
                if row is None:
                    return False

                timeout = row.get("timeout_seconds", 300)
                _execute(
                    conn,
                    """INSERT INTO queue_tasks
                       (id, type, payload, priority, status, created_at,
                        scheduled_at, attempts, max_attempts, timeout_seconds)
                       VALUES (%s, %s, %s, %s, 'pending', %s,
                               NOW(), 0, %s, %s)""",
                    (
                        row["id"],
                        row["type"],
                        row["payload"],
                        row["priority"],
                        row["created_at"],
                        row["max_attempts"],
                        timeout,
                    ),
                )
                _execute(
                    conn,
                    "DELETE FROM queue_task_history WHERE id = %s AND status = 'dead_letter'",
                    (task_id,),
                )
                return True
        except Exception as e:
            logger.error("Failed to retry dead letter task %s: %s", task_id, e)
            return False

    async def retry_dead_letter_async(self, task_id: str) -> bool:
        """Async version of ``retry_dead_letter`` — runs the blocking DB call in a thread."""
        return await asyncio.to_thread(self.retry_dead_letter, task_id)

    def clear_completed_history(self, older_than_days: int = 7):
        """Clean up old completed task history.

        This method is synchronous and performs blocking DB calls. When called
        from an async context, use ``await clear_completed_history_async()`` instead.
        """
        try:
            with _conn() as conn:
                _execute(
                    conn,
                    """DELETE FROM queue_task_history
                       WHERE finished_at < NOW() - (%s * INTERVAL '1 day')
                       AND status IN ('completed', 'dead_letter')""",
                    (older_than_days,),
                )
        except Exception as e:
            logger.error("Failed to clear completed history: %s", e)

    async def clear_completed_history_async(self, older_than_days: int = 7):
        """Async version of ``clear_completed_history`` — runs the blocking DB call in a thread."""
        await asyncio.to_thread(self.clear_completed_history, older_than_days)


# ───────────────────────────────────────────────────────────────────────
# Factory
# ───────────────────────────────────────────────────────────────────────

_queue_instance: PostgresWorkerQueue | None = None
_queue_lock = threading.Lock()


def get_postgres_worker_queue() -> PostgresWorkerQueue:
    """Get or create the global PostgresWorkerQueue instance."""
    global _queue_instance
    if _queue_instance is None:
        with _queue_lock:
            if _queue_instance is None:
                _queue_instance = PostgresWorkerQueue()
    return _queue_instance


def reset_postgres_worker_queue():
    """Reset the global Postgres queue instance (for testing)."""
    global _queue_instance
    _queue_instance = None

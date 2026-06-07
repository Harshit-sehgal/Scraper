"""Postgres Worker Queue base — driver-agnostic shared logic.

Extracted from ``worker_queue_postgres.py`` to allow both the legacy
``psycopg2`` driver and the new ``psycopg`` (psycopg 3) driver to share
schema, task lifecycle, and worker-loop code. The driver-specific
implementations are:

- ``app.worker_queue_postgres`` (psycopg2) — production-legacy path
- ``app.worker_queue_postgres_psycopg3`` (psycopg 3) — production path

The public factory ``get_postgres_worker_queue()`` lives in
``app.worker_queue_postgres`` for backward compatibility; it dispatches
to the correct driver based on ``DATAFORGE_PG_DRIVER`` (or the
``settings.PG_DRIVER`` value).
"""

from __future__ import annotations

import asyncio
import contextlib
import datetime
import json
import logging
import threading
import time
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterator
from contextlib import contextmanager

from app.worker_queue import Priority, QueueTask

logger = logging.getLogger(__name__)

_CURRENT_QUEUE_SCHEMA_VERSION = 3


def _add_column_if_missing(conn, table: str, column: str, col_type: str) -> None:
    """Run ``ALTER TABLE ADD COLUMN`` safely inside a SAVEPOINT.

    A bare ``try / except`` swallows the error but leaves the connection in an
    aborted transaction state (psycopg2 error state 25P02) so every subsequent
    statement on the same connection raises ``InFailedSqlTransaction``. Using
    SAVEPOINT / ROLLBACK TO SAVEPOINT rolls the failed statement back cleanly
    and keeps the surrounding transaction usable.
    """
    with conn.cursor() as cur:
        cur.execute("SAVEPOINT add_col_sp")
        try:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
        except Exception:
            cur.execute("ROLLBACK TO SAVEPOINT add_col_sp")
        else:
            cur.execute("RELEASE SAVEPOINT add_col_sp")


def _ensure_schema_via(conn, fetch_one, execute) -> None:
    """Create queue tables and run schema migrations.

    The connection is supplied by the caller; we use the supplied
    ``fetch_one`` / ``execute`` helpers so this function is
    driver-agnostic (works with both psycopg2 and psycopg 3).

    Uses ``NOW()`` for both ``created_at`` and ``scheduled_at`` so the stored
    timestamps are in Postgres server time (UTC), matching the ``NOW()``
    reference used by the dequeue query.  This avoids timezone mismatches
    when Python's ``datetime.datetime.now()`` returns a different timezone
    (e.g. IST) than the Postgres server (UTC).
    """
    # Check table existence via information_schema instead of try / except,
    # which would leave the connection in an aborted transaction state.
    table_exists = fetch_one(
        conn,
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'queue_schema_version'",
    )
    if table_exists:
        # Verify the table has the expected structure. Use a SAVEPOINT so any
        # error (e.g. missing column) leaves the connection in a usable
        # transaction state, not an aborted one.
        with conn.cursor() as cur:
            cur.execute("SAVEPOINT schema_check_sp")
            try:
                cur.execute("SELECT id FROM queue_schema_version LIMIT 1")
                old_row = cur.fetchone()
            except Exception:
                old_row = None
                cur.execute("ROLLBACK TO SAVEPOINT schema_check_sp")
            else:
                cur.execute("RELEASE SAVEPOINT schema_check_sp")
        if old_row is None:
            execute(conn, "DROP TABLE IF EXISTS queue_schema_version CASCADE")

    execute(
        conn,
        """
        CREATE TABLE IF NOT EXISTS queue_schema_version (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            version INTEGER NOT NULL
        )
    """,
    )
    row = fetch_one(conn, "SELECT version FROM queue_schema_version WHERE id = 1")
    current = row["version"] if row and row.get("version") is not None else 0

    if current < _CURRENT_QUEUE_SCHEMA_VERSION:
        if current < 1:
            execute(
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

            execute(
                conn,
                """
                CREATE INDEX IF NOT EXISTS idx_queue_tasks_status_priority
                    ON queue_tasks(status, priority)
            """,
            )

            execute(
                conn,
                """
                CREATE INDEX IF NOT EXISTS idx_queue_tasks_scheduled
                    ON queue_tasks(scheduled_at)
            """,
            )

            execute(
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

            execute(
                conn,
                """
                CREATE INDEX IF NOT EXISTS idx_queue_task_history_type
                    ON queue_task_history(type)
            """,
            )

            execute(
                conn,
                """
                CREATE INDEX IF NOT EXISTS idx_queue_task_history_finished
                    ON queue_task_history(finished_at DESC)
            """,
            )
            current = 1

        if current < 2:
            # Add result column (used for storing successful task results).
            # Wrap in a SAVEPOINT so a pre-existing column doesn't leave the
            # connection in an aborted transaction state.
            _add_column_if_missing(conn, "queue_task_history", "result", "TEXT")
            current = 2

        if current < 3:
            # Add execution_time_ms column for tracking task latencies
            _add_column_if_missing(conn, "queue_task_history", "execution_time_ms", "INTEGER")
            current = 3

        execute(
            conn,
            "INSERT INTO queue_schema_version (id, version) VALUES (1, %s)"
            " ON CONFLICT (id) DO UPDATE SET version = EXCLUDED.version",
            (current,),
        )
        logger.info("Postgres queue schema migrated to version %d", current)
    else:
        logger.debug("Postgres queue schema already at version %d", _CURRENT_QUEUE_SCHEMA_VERSION)


class PostgresWorkerQueueBase(ABC):
    """Abstract Postgres worker queue base with all shared logic.

    Subclasses must implement the four connection helpers that the queue
    uses internally (``_conn``, ``_execute``, ``_fetch_one``, ``_fetch_all``).
    Both the psycopg2 and the psycopg 3 implementations provide these.
    """

    def __init__(self, max_concurrency: int = 5, poll_interval: float = 1.0) -> None:
        self._max_concurrency = max_concurrency
        self._poll_interval = poll_interval
        self._running = False
        self._start_lock = asyncio.Lock()
        self._worker_task: asyncio.Task | None = None
        self._in_flight: dict[str, asyncio.Task] = {}
        self._handlers: dict[str, Callable] = {}
        self._in_flight_lock = asyncio.Lock()
        # Semaphore gives us atomic acquire/release for the concurrency
        # budget. Reserving a permit *before* dequeue closes the race in
        # which a task is claimed from the DB (status='running') but not
        # yet registered in ``_in_flight``, allowing the loop to
        # over-subscribe ``max_concurrency``.
        self._concurrency_sem = asyncio.Semaphore(max_concurrency)
        self._ensure_schema()

    # ── Abstract driver hooks (psycopg2 / psycopg 3) ────────────────────

    @abstractmethod
    @contextmanager
    def _conn(self) -> Iterator:
        """Acquire a database connection (context manager)."""

    @abstractmethod
    def _execute(self, conn, sql: str, params=None):
        """Execute a statement, return the cursor."""

    @abstractmethod
    def _fetch_one(self, conn, sql: str, params=None) -> dict | None:
        """Execute a query and return the first row as a dict, or None."""

    @abstractmethod
    def _fetch_all(self, conn, sql: str, params=None) -> list[dict]:
        """Execute a query and return all rows as dicts."""

    def _ensure_schema(self) -> None:
        """Create queue tables and run schema migrations (driver-agnostic)."""
        with self._conn() as conn:
            _ensure_schema_via(conn, self._fetch_one, self._execute)

    # ─── Task registration ─────────────────────────────────────────────

    def register_handler(self, task_type: str, handler: Callable) -> None:
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
        """Synchronous enqueue — runs in a thread to avoid blocking the event loop."""
        with self._conn() as conn:
            self._execute(
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
            with self._conn() as conn:
                # Atomically claim the highest-priority pending task
                row = self._fetch_one(
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
                # compatibility. ``queue_tasks`` does NOT have a ``finished_at``
                # column (that lives on ``queue_task_history`` only).
                _ts_fields = ("created_at", "started_at", "completed_at", "scheduled_at")
                for _f in _ts_fields:
                    v = row.get(_f)
                    if isinstance(v, (datetime.datetime, datetime.date)):
                        row[_f] = v.strftime("%Y-%m-%d %H:%M:%S")

                return QueueTask.from_dict(
                    {
                        **row,
                        "payload": json.loads(row["payload"]),
                    },
                )
        except Exception as e:
            logger.error("Postgres dequeue error: %s", e, exc_info=True)
            return None

    async def complete(self, task_id: str, result: dict | None = None) -> None:
        """Mark a task as completed successfully."""
        await asyncio.to_thread(
            self._complete_sync,
            task_id,
            json.dumps(result) if result else None,
        )

    def _complete_sync(self, task_id: str, result_json: str | None) -> None:
        """Synchronous complete — runs in a thread to avoid blocking the event loop."""
        with self._conn() as conn:
            row = self._fetch_one(conn, "SELECT * FROM queue_tasks WHERE id = %s", (task_id,))
            if row:
                self._execute(
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
                self._execute(conn, "DELETE FROM queue_tasks WHERE id = %s", (task_id,))

    async def fail(
        self,
        task_id: str,
        error: str,
        retry: bool = True,
        retry_after: float | None = None,
        task_type: str | None = None,
    ) -> None:
        """Mark a task as failed. Retries if attempts remain.

        Mirrors the SQLite ``WorkerQueue.fail`` signature so callers can
        treat the two backends interchangeably.
        """
        await asyncio.to_thread(
            self._fail_sync,
            task_id,
            error,
            retry,
            retry_after,
            task_type,
        )

    def _fail_sync(
        self,
        task_id: str,
        error: str,
        retry: bool = True,
        retry_after: float | None = None,
        task_type: str | None = None,
    ) -> None:
        """Synchronous fail — runs in a thread to avoid blocking the event loop."""
        with self._conn() as conn:
            row = self._fetch_one(
                conn,
                "SELECT attempts, max_attempts, * FROM queue_tasks WHERE id = %s",
                (task_id,),
            )

            if row:
                attempts = row["attempts"]
                max_attempts = row["max_attempts"]
                actual_type = task_type or row["type"]

                if retry and attempts < max_attempts:
                    # Use explicit retry-after if provided (rate-limit aware),
                    # otherwise use standard exponential backoff.
                    if retry_after is not None and retry_after > 0:
                        backoff = min(retry_after, 3600.0)
                    else:
                        backoff = float(min(2 ** (attempts - 1) * 30, 3600))
                    self._execute(
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
                    self._execute(
                        conn,
                        """INSERT INTO queue_task_history
                           (id, type, payload, priority, status, created_at,
                            started_at, completed_at, attempts, max_attempts,
                            last_error, result, timeout_seconds, finished_at)
                           VALUES (%s, %s, %s, %s, 'dead_letter', %s,
                                   %s, NOW(), %s, %s, %s, %s, %s, NOW())""",
                        (
                            row["id"],
                            actual_type,
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
                    self._execute(conn, "DELETE FROM queue_tasks WHERE id = %s", (task_id,))
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
        # Capture the in-flight task under the lock, then release the lock
        # before doing any DB I/O. Holding an asyncio.Lock across
        # ``asyncio.to_thread`` blocks every other coroutine that needs
        # the same lock (worker loop, _cleanup_in_flight) for the
        # duration of the synchronous DB call.
        flight_task: asyncio.Task | None = None
        async with self._in_flight_lock:
            flight_task = self._in_flight.get(task_id)

        if flight_task is not None:
            flight_task.cancel()
            return await asyncio.to_thread(
                self._cancel_in_flight_sync,
                task_id,
            )

        return await asyncio.to_thread(
            self._cancel_pending_sync,
            task_id,
        )

    def _cancel_in_flight_sync(self, task_id: str) -> bool:
        """Synchronous cancel for in-flight tasks — runs in a thread."""
        with self._conn() as conn:
            row = self._fetch_one(
                conn,
                "SELECT * FROM queue_tasks WHERE id = %s",
                (task_id,),
            )
            if row:
                self._execute(
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
                self._execute(conn, "DELETE FROM queue_tasks WHERE id = %s", (task_id,))
            return True

    def _cancel_pending_sync(self, task_id: str) -> bool:
        """Synchronous cancel for pending tasks — runs in a thread."""
        with self._conn() as conn:
            row = self._fetch_one(
                conn,
                "SELECT * FROM queue_tasks WHERE id = %s AND status = 'pending'",
                (task_id,),
            )
            if row is None:
                return False
            self._execute(
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
            self._execute(conn, "DELETE FROM queue_tasks WHERE id = %s", (task_id,))
            return True

    # ─── Worker loop ───────────────────────────────────────────────────

    async def start(self) -> None:
        """Start the background worker loop with recovery of stuck tasks.

        ``_start_lock`` makes the ``_running`` check-and-set atomic. Without
        it, two concurrent ``start()`` calls can both pass the ``if
        self._running`` check and spawn duplicate worker loops, each of
        which would race to dequeue the same tasks.
        """
        async with self._start_lock:
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

    def _recover_stuck_tasks(self) -> None:
        """Reset any tasks stuck in 'running' state back to 'pending' for retry.

        Synchronous — called via ``asyncio.to_thread`` to avoid blocking the event loop.
        """
        try:
            with self._conn() as conn:
                stuck = self._fetch_one(conn, "SELECT COUNT(*) AS cnt FROM queue_tasks WHERE status = 'running'")
                count = stuck["cnt"] if stuck else 0
                if count:
                    self._execute(
                        conn,
                        "UPDATE queue_tasks SET status = 'pending', started_at = NULL, "
                        "last_error = 'Recovered after worker restart' "
                        "WHERE status = 'running'",
                    )
                    logger.info("Recovered %d stuck task(s) from previous worker crash", count)
        except Exception:
            logger.exception("Failed to recover stuck tasks")

    async def stop(self, drain: bool = True) -> None:
        """Stop the worker loop. Optionally drain in-flight tasks."""
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._worker_task

        if drain:
            await self._drain_in_flight()

        logger.info("Postgres worker queue stopped (drained=%s)", drain)

    async def _worker_loop(self) -> None:
        """Main worker loop: dequeue and dispatch tasks."""
        while self._running:
            try:
                # Acquire a concurrency permit *before* dequeue so the
                # budget is reserved atomically. If the permit is not
                # available we yield for a poll interval and try again —
                # the semaphore is fair-ish and won't busy-spin.
                acquired = False
                try:
                    await asyncio.wait_for(
                        self._concurrency_sem.acquire(),
                        timeout=self._poll_interval,
                    )
                    acquired = True
                except TimeoutError:
                    continue
                if not acquired:
                    continue

                task = await self.dequeue(timeout=self._poll_interval)
                if task is None:
                    self._concurrency_sem.release()
                    continue

                t = asyncio.create_task(self._execute_task(task))

                task_id = task.id

                async with self._in_flight_lock:
                    self._in_flight[task_id] = t

                def _on_task_done(_fut: object, tid: str = task_id) -> None:
                    # Schedule cleanup on the currently running event loop,
                    # not whichever loop ``asyncio.ensure_future`` happens
                    # to pick up. Avoids a ``RuntimeError`` when the worker
                    # is bound to a different loop from the caller's
                    # context (e.g. across test scopes or shutdown).
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(self._cleanup_in_flight(tid))
                    except RuntimeError:
                        logger.debug(
                            "No running event loop to schedule _cleanup_in_flight for %s",
                            tid,
                        )

                def _release(_fut: object, tid: str = task_id) -> None:
                    # Release the semaphore permit exactly once when the
                    # task finishes (success, failure, or cancellation).
                    try:
                        self._concurrency_sem.release()
                    except ValueError:
                        # Permit already released — should not happen, but
                        # never let a done-callback raise.
                        logger.debug("Semaphore release failed for task %s", tid)

                t.add_done_callback(_on_task_done)
                t.add_done_callback(_release)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Worker loop error: %s", e, exc_info=True)
                # Best-effort release if we acquired a permit but failed
                # before installing the done-callbacks.
                try:
                    self._concurrency_sem.release()
                except ValueError:
                    pass
                await asyncio.sleep(1)

    async def _execute_task(self, task: QueueTask) -> None:
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
        except TimeoutError:
            await self.fail(task.id, f"Timeout after {task.timeout_seconds}s", retry=True)
        except Exception as e:
            await self.fail(task.id, f"{type(e).__name__}: {e}", retry=True)

    async def _cleanup_in_flight(self, task_id: str) -> None:
        """Remove a task from the in-flight tracker."""
        async with self._in_flight_lock:
            self._in_flight.pop(task_id, None)

    async def _drain_in_flight(self) -> None:
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
            with self._conn() as conn:
                row = self._fetch_one(
                    conn,
                    "SELECT * FROM queue_tasks WHERE id = %s",
                    (task_id,),
                )
                if row:
                    return row
                row = self._fetch_one(
                    conn,
                    "SELECT * FROM queue_task_history WHERE id = %s",
                    (task_id,),
                )
                if row:
                    return row
                return None
        except Exception:
            logger.exception("Failed to get task state for %s", task_id)
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
            with self._conn() as conn:
                pending = self._fetch_one(conn, "SELECT COUNT(*) AS cnt FROM queue_tasks WHERE status = 'pending'")
                running = self._fetch_one(conn, "SELECT COUNT(*) AS cnt FROM queue_tasks WHERE status = 'running'")
                # "Effectively retrying" = pending with future scheduled_at
                # (the queue never uses the ``retrying`` TaskStatus value;
                # it transitions failed tasks back to ``pending`` instead).
                retrying = self._fetch_one(
                    conn,
                    "SELECT COUNT(*) AS cnt FROM queue_tasks WHERE status = 'pending' AND scheduled_at > NOW()",
                )
                dead_letter = self._fetch_one(
                    conn,
                    "SELECT COUNT(*) AS cnt FROM queue_task_history WHERE status = 'dead_letter'",
                )
                completed_24h = self._fetch_one(
                    conn,
                    "SELECT COUNT(*) AS cnt FROM queue_task_history WHERE finished_at >= NOW() - INTERVAL '24 hours'",
                )

                top_pending = self._fetch_all(
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
                    "retrying": retrying["cnt"] if retrying else 0,
                    "dead_letter": dead_letter["cnt"] if dead_letter else 0,
                    "completed_24h": completed_24h["cnt"] if completed_24h else 0,
                    "max_concurrency": self._max_concurrency,
                    "in_flight": len(self._in_flight),
                    "next_tasks": top_pending,
                }
        except Exception as e:
            logger.exception("Failed to get Postgres queue status: %s", str(e))
            return {"ok": False, "backend": "postgres", "error": str(e), "pending": 0, "running": 0}

    async def get_status_async(self) -> dict:
        """Async version of ``get_status`` — runs the blocking DB call in a thread."""
        return await asyncio.to_thread(self.get_status)

    def get_dead_letter_queue(self, limit: int = 50) -> list[dict]:
        """Return dead letter queue entries."""
        try:
            with self._conn() as conn:
                return self._fetch_all(
                    conn,
                    """SELECT * FROM queue_task_history
                       WHERE status = 'dead_letter'
                       ORDER BY finished_at DESC LIMIT %s""",
                    (limit,),
                )
        except Exception:
            logger.exception("Failed to get dead letter queue")
            return []

    async def get_dead_letter_queue_async(self, limit: int = 50) -> list[dict]:
        """Async version of ``get_dead_letter_queue`` — runs the blocking DB call in a thread."""
        return await asyncio.to_thread(self.get_dead_letter_queue, limit)

    def retry_dead_letter(self, task_id: str) -> bool:
        """Re-queue a dead letter task."""
        try:
            with self._conn() as conn:
                row = self._fetch_one(
                    conn,
                    "SELECT * FROM queue_task_history WHERE id = %s AND status = 'dead_letter'",
                    (task_id,),
                )
                if row is None:
                    return False

                timeout = row.get("timeout_seconds", 300)
                self._execute(
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
                self._execute(
                    conn,
                    "DELETE FROM queue_task_history WHERE id = %s AND status = 'dead_letter'",
                    (task_id,),
                )
                return True
        except Exception:
            logger.exception("Failed to retry dead letter task %s", task_id)
            return False

    async def retry_dead_letter_async(self, task_id: str) -> bool:
        """Async version of ``retry_dead_letter`` — runs the blocking DB call in a thread."""
        return await asyncio.to_thread(self.retry_dead_letter, task_id)

    def clear_completed_history(self, older_than_days: int = 7) -> None:
        """Clean up old completed task history.

        This method is synchronous and performs blocking DB calls. When called
        from an async context, use ``await clear_completed_history_async()`` instead.
        """
        try:
            with self._conn() as conn:
                self._execute(
                    conn,
                    """DELETE FROM queue_task_history
                       WHERE finished_at < NOW() - (%s * INTERVAL '1 day')
                       AND status IN ('completed', 'dead_letter')""",
                    (older_than_days,),
                )
        except Exception:
            logger.exception("Failed to clear completed history")

    async def clear_completed_history_async(self, older_than_days: int = 7) -> None:
        """Async version of ``clear_completed_history`` — runs the blocking DB call in a thread."""
        return await asyncio.to_thread(self.clear_completed_history, older_than_days)


# ───────────────────────────────────────────────────────────────────────
# Singleton factory and reset helpers (driver-agnostic surface)
# ───────────────────────────────────────────────────────────────────────

_queue_instance: PostgresWorkerQueueBase | None = None
_queue_lock = threading.Lock()


def get_postgres_worker_queue_base() -> PostgresWorkerQueueBase:
    """Get or create the global PostgresWorkerQueueBase instance.

    The factory selects the right driver (psycopg2 vs psycopg 3) based on
    ``DATAFORGE_PG_DRIVER`` (or ``settings.PG_DRIVER``). The returned
    instance is cached as a module-level singleton so all callers share
    the same instance.
    """
    global _queue_instance
    if _queue_instance is None:
        with _queue_lock:
            if _queue_instance is None:
                _queue_instance = _build_postgres_worker_queue()
    return _queue_instance


def _build_postgres_worker_queue() -> PostgresWorkerQueueBase:
    """Build a fresh PostgresWorkerQueueBase using the configured driver."""
    from app.config import settings as _settings

    pg_driver = _settings.PG_DRIVER
    if pg_driver == "psycopg3":
        try:
            from app.worker_queue_postgres_psycopg3 import PostgresWorkerQueuePsycopg3

            return PostgresWorkerQueuePsycopg3()
        except ImportError as e:
            raise RuntimeError(
                f"Failed to import psycopg3 worker queue: {e}. Install psycopg 3 with: pip install 'psycopg[binary,pool]>=3.2'"
            ) from e

    # Default: psycopg2 (legacy)
    from app.worker_queue_postgres import PostgresWorkerQueue

    return PostgresWorkerQueue()


def reset_postgres_worker_queue_base() -> None:
    """Reset the global queue instance (for testing)."""
    global _queue_instance
    _queue_instance = None

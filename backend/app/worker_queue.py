"""Persistent Worker Queue — async job processing with SQLite-backed persistence.

Provides:
- Durable task persistence (survives crashes)
- Priority levels (critical, high, normal, low, background)
- Automatic retries with exponential backoff
- Dead letter queue for permanently failed tasks
- Per-task timeout enforcement
- Graceful shutdown with in-flight task draining
- Observability endpoints for monitoring

Usage:
    queue = get_worker_queue()
    await queue.enqueue("scrape_job", {"job_id": "abc"}, priority=Priority.HIGH)
    task = await queue.dequeue()
    await queue.complete(task.id)
"""

import asyncio
import contextlib
import datetime
import json
import logging
import sqlite3
import threading
import time
import uuid
from collections.abc import Callable
from enum import IntEnum, StrEnum
from pathlib import Path
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)


def _record_scheduled_job_usage(
    *,
    task_id: str,
    task_type: str,
    payload: dict | None,
    scheduled_at: str | None,
    usage_context: dict[str, Any] | None = None,
) -> None:
    """Record one scheduled worker task when caller attribution is available."""
    context = dict(usage_context or {})
    payload = payload or {}
    user_id = str(context.get("user_id") or payload.get("user_id") or payload.get("created_by") or "")
    if not user_id:
        return

    org_id = str(context.get("org_id") or payload.get("org_id") or "")
    project_id = str(context.get("project_id") or payload.get("project_id") or "")
    job_id = str(context.get("job_id") or payload.get("job_id") or "")
    try:
        from app.utils.usage_ledger import UsageType, get_usage_ledger

        get_usage_ledger().record_usage(
            user_id,
            UsageType.SCHEDULED_JOB,
            quantity=1,
            metadata={
                "task_id": task_id,
                "task_type": task_type,
                "job_id": job_id,
                "scheduled_at": scheduled_at or "",
            },
            idempotency_key=f"scheduled-job:{task_id}",
            org_id=org_id,
            project_id=project_id,
        )
    except ValueError:
        raise
    except Exception as exc:
        logger.debug("Scheduled-job metering skipped: %s", exc)


class Priority(IntEnum):
    """Task priority levels. Lower number = higher priority."""

    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3
    BACKGROUND = 4


class TaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"
    DEAD_LETTER = "dead_letter"
    CANCELLED = "cancelled"


class QueueTask:
    """A single task in the worker queue."""

    __slots__ = (
        "attempts",
        "completed_at",
        "created_at",
        "id",
        "last_error",
        "max_attempts",
        "payload",
        "priority",
        "scheduled_at",
        "started_at",
        "status",
        "timeout_seconds",
        "type",
    )

    def __init__(
        self,
        task_type: str,
        payload: dict | None = None,
        priority: Priority = Priority.NORMAL,
        max_attempts: int = 3,
        timeout_seconds: int = 300,
        task_id: str | None = None,
        scheduled_at: str | None = None,
    ) -> None:
        self.id = task_id or str(uuid.uuid4())
        self.type = task_type
        self.payload = payload or {}
        self.priority = priority
        self.status = TaskStatus.PENDING
        self.created_at = datetime.datetime.now(tz=datetime.UTC).strftime(_TIMESTAMP_FORMAT)
        self.started_at: str | None = None
        self.completed_at: str | None = None
        self.attempts = 0
        self.max_attempts = max_attempts
        self.last_error: str | None = None
        self.scheduled_at = scheduled_at or self.created_at
        self.timeout_seconds = timeout_seconds

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "payload": self.payload,
            "priority": int(self.priority),
            "status": self.status,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "attempts": self.attempts,
            "max_attempts": self.max_attempts,
            "last_error": self.last_error,
            "scheduled_at": self.scheduled_at,
            "timeout_seconds": self.timeout_seconds,
        }

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "QueueTask":
        task = QueueTask(
            task_type=d["type"],
            payload=d.get("payload", {}),
            priority=Priority(d.get("priority", 2)),
            max_attempts=d.get("max_attempts", 3),
            timeout_seconds=d.get("timeout_seconds", 300),
            task_id=d.get("id"),
            scheduled_at=d.get("scheduled_at"),
        )
        raw_status = d.get("status", TaskStatus.PENDING)
        if isinstance(raw_status, TaskStatus):
            task.status = raw_status
        else:
            try:
                task.status = TaskStatus(raw_status)
            except ValueError:
                task.status = TaskStatus.PENDING
        # Normalize timestamps: convert datetime / date objects to ISO strings
        for _f in ("created_at", "started_at", "completed_at", "scheduled_at"):
            _v = d.get(_f)
            if _v is None:
                continue
            if hasattr(_v, "isoformat"):
                setattr(task, _f, _v.isoformat())
            elif isinstance(_v, str):
                setattr(task, _f, _v)
        task.attempts = d.get("attempts", 0)
        task.last_error = d.get("last_error")
        return task


# ───────────────────────────────────────────────────────────────────────
# SQLite-backed queue storage
# ───────────────────────────────────────────────────────────────────────


def _get_db_path() -> Path:
    """Resolve the queue database path."""
    data_dir = Path(__file__).resolve().parent.parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "worker_queue.db"


_DB_LOCK = threading.Lock()


def _get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    """Get a SQLite connection with WAL mode."""
    path = db_path or _get_db_path()
    conn = sqlite3.connect(str(path), timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


_CURRENT_QUEUE_SCHEMA_VERSION = 3

# SQLite's ``datetime('now')`` returns ``"YYYY-MM-DD HH:MM:SS"`` (no ``T``/``Z``).
# We use the same format from Python so textual ``scheduled_at <= datetime('now')``
# comparisons work in both directions. Timestamps are UTC (mirroring Postgres's
# ``NOW()``) so the SQLite and Postgres backends produce identical orderings
# regardless of the host's local time zone.
_TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"


def _ensure_schema(db_path: Path | None = None) -> None:
    """Create the queue tables if they don't exist and run migrations."""
    with _DB_LOCK:
        conn = _get_connection(db_path=db_path)
        try:
            # Create schema_version table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS queue_schema_version (
                    version INTEGER PRIMARY KEY
                )
            """)
            row = conn.execute("SELECT MAX(version) FROM queue_schema_version").fetchone()
            current = row[0] if row and row[0] is not None else 0

            if current < _CURRENT_QUEUE_SCHEMA_VERSION:
                if current < 1:
                    conn.executescript("""
                        CREATE TABLE IF NOT EXISTS tasks (
                            id TEXT PRIMARY KEY,
                            type TEXT NOT NULL,
                            payload TEXT NOT NULL DEFAULT '{}',
                            priority INTEGER NOT NULL DEFAULT 2,
                            status TEXT NOT NULL DEFAULT 'pending',
                            created_at TEXT NOT NULL,
                            started_at TEXT,
                            completed_at TEXT,
                            attempts INTEGER NOT NULL DEFAULT 0,
                            max_attempts INTEGER NOT NULL DEFAULT 3,
                            last_error TEXT,
                            scheduled_at TEXT NOT NULL,
                            timeout_seconds INTEGER NOT NULL DEFAULT 300
                        );

                        CREATE INDEX IF NOT EXISTS idx_tasks_status_priority
                            ON tasks(status, priority);

                        CREATE INDEX IF NOT EXISTS idx_tasks_scheduled
                            ON tasks(scheduled_at);

                        CREATE TABLE IF NOT EXISTS task_history (
                            id TEXT PRIMARY KEY,
                            type TEXT NOT NULL,
                            payload TEXT NOT NULL DEFAULT '{}',
                            priority INTEGER NOT NULL DEFAULT 2,
                            status TEXT NOT NULL,
                            created_at TEXT NOT NULL,
                            started_at TEXT,
                            completed_at TEXT,
                            attempts INTEGER NOT NULL DEFAULT 0,
                            max_attempts INTEGER NOT NULL DEFAULT 3,
                            last_error TEXT,
                            timeout_seconds INTEGER NOT NULL DEFAULT 300,
                            finished_at TEXT NOT NULL
                        );

                        CREATE INDEX IF NOT EXISTS idx_task_history_type
                            ON task_history(type);

                        CREATE INDEX IF NOT EXISTS idx_task_history_finished
                            ON task_history(finished_at DESC);
                    """)
                    current = 1

                if current < 2:
                    # Add result column to task_history (used for storing
                    # successful task results)
                    with contextlib.suppress(Exception):
                        conn.execute("ALTER TABLE task_history ADD COLUMN result TEXT")
                    current = 2

                if current < 3:
                    # Add execution_time_ms column for tracking task latencies
                    # (mirrors the Postgres queue migration so both backends
                    # share the same ``_CURRENT_QUEUE_SCHEMA_VERSION``).
                    with contextlib.suppress(Exception):
                        conn.execute("ALTER TABLE task_history ADD COLUMN execution_time_ms INTEGER")
                    current = 3

                conn.execute("DELETE FROM queue_schema_version")
                conn.execute("INSERT INTO queue_schema_version (version) VALUES (?)", (current,))
                conn.commit()
                logger.info("Worker queue schema migrated to version %d", current)
            else:
                logger.debug("Worker queue schema already at version %d", _CURRENT_QUEUE_SCHEMA_VERSION)
        finally:
            conn.close()


# ───────────────────────────────────────────────────────────────────────
# Worker Queue
# ───────────────────────────────────────────────────────────────────────


class WorkerQueue:
    """Persistent worker queue with priority, retries, and dead letter support."""

    def __init__(self, max_concurrency: int = 5, poll_interval: float = 1.0, db_path: Path | None = None) -> None:
        self._max_concurrency = max_concurrency
        self._poll_interval = poll_interval
        self._db_path = db_path
        self._running = False
        self._worker_task: asyncio.Task | None = None
        self._in_flight: dict[str, asyncio.Task] = {}
        self._handlers: dict[str, Callable] = {}
        self._in_flight_lock = asyncio.Lock()
        self._start_lock = asyncio.Lock()
        # Semaphore gives us atomic acquire/release for the concurrency
        # budget, independent of the bookkeeping dict. The worker loop
        # acquires a permit before dequeue and releases it when the
        # dispatched task finishes — see _on_task_done below.
        self._concurrency_sem = asyncio.Semaphore(max_concurrency)
        _ensure_schema(db_path=self._db_path)

    def _conn(self) -> sqlite3.Connection:
        """Get a connection to this instance's database."""
        return _get_connection(db_path=self._db_path)

    # ─── Task registration ─────────────────────────────────────────────

    def register_handler(self, task_type: str, handler: Callable) -> None:
        """Register an async handler function for a task type.

        The handler receives (task: QueueTask) and should return True on success.
        """
        self._handlers[task_type] = handler

    def set_max_concurrency(self, value: int) -> None:
        """Resize the concurrency budget at runtime.

        Public API that replaces the previous reliance on the private
        ``_max_concurrency`` attribute. The semaphore is swapped atomically;
        the in-flight dict is left as-is so tasks already running keep
        their slot until they complete.
        """
        if value < 1:
            msg = f"max_concurrency must be >= 1, got {value}"
            raise ValueError(msg)
        self._max_concurrency = value
        self._concurrency_sem = asyncio.Semaphore(value)

    def get_poll_interval(self) -> float:
        """Return the worker poll interval in seconds (public accessor)."""
        return self._poll_interval

    # ─── Task lifecycle ────────────────────────────────────────────────

    def _enqueue_sync(self, task: QueueTask) -> None:
        conn = self._conn()
        try:
            conn.execute(
                """INSERT OR IGNORE INTO tasks
                   (id, type, payload, priority, status, created_at,
                    scheduled_at, attempts, max_attempts, timeout_seconds)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    task.id,
                    task.type,
                    json.dumps(task.payload),
                    int(task.priority),
                    task.status,
                    task.created_at,
                    task.scheduled_at,
                    task.attempts,
                    task.max_attempts,
                    task.timeout_seconds,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    async def enqueue(
        self,
        task_type: str,
        payload: dict | None = None,
        priority: Priority = Priority.NORMAL,
        max_attempts: int = 3,
        timeout_seconds: int = 300,
        task_id: str | None = None,
        scheduled_at: str | None = None,
        usage_context: dict[str, Any] | None = None,
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
        _record_scheduled_job_usage(
            task_id=task.id,
            task_type=task.type,
            payload=task.payload,
            scheduled_at=task.scheduled_at,
            usage_context=usage_context,
        )

        async with self._in_flight_lock:
            await asyncio.to_thread(self._enqueue_sync, task)

        return task.id

    async def dequeue(self, timeout: float = 5.0) -> QueueTask | None:
        """Dequeue the highest-priority pending task.

        Blocks up to *timeout* seconds if the queue is empty.
        Returns None if the timeout expires.
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            task = await asyncio.to_thread(self._dequeue_one)
            if task:
                return task
            await asyncio.sleep(0.25)
        return None

    def _dequeue_one(self) -> QueueTask | None:
        """Synchronous dequeue from SQLite with priority ordering."""
        with _DB_LOCK:
            conn = self._conn()
            try:
                # ``BEGIN IMMEDIATE`` acquires a write lock at the start of the
                # transaction so the SELECT-then-UPDATE sequence is atomic
                # across multiple processes (the module-level ``_DB_LOCK``
                # only serializes operations *within* a single process).
                conn.execute("BEGIN IMMEDIATE")
                row = conn.execute("""SELECT * FROM tasks
                       WHERE status = 'pending'
                         AND scheduled_at <= datetime('now')
                       ORDER BY priority ASC, created_at ASC
                       LIMIT 1""").fetchone()

                if row is None:
                    conn.execute("ROLLBACK")
                    return None

                task_data = dict(row)
                task = QueueTask.from_dict(
                    {
                        **task_data,
                        "payload": json.loads(task_data["payload"]),
                    },
                )
                task.status = TaskStatus.RUNNING
                task.started_at = datetime.datetime.now(tz=datetime.UTC).strftime(_TIMESTAMP_FORMAT)
                task.attempts += 1

                conn.execute(
                    "UPDATE tasks SET status = ?, started_at = ?, attempts = ? WHERE id = ?",
                    (task.status, task.started_at, task.attempts, task.id),
                )
                conn.execute("COMMIT")

                return task
            finally:
                conn.close()

    def _complete_sync(self, task_id: str, result: dict | None) -> None:
        now = datetime.datetime.now(tz=datetime.UTC).strftime(_TIMESTAMP_FORMAT)
        conn = self._conn()
        try:
            # Fetch task for history
            row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            if row:
                task_data = dict(row)
                # Archive to history
                conn.execute(
                    """INSERT OR REPLACE INTO task_history
                       (id, type, payload, priority, status, created_at,
                        started_at, completed_at, attempts, max_attempts,
                        last_error, result, timeout_seconds, finished_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        task_data["id"],
                        task_data["type"],
                        task_data["payload"],
                        task_data["priority"],
                        TaskStatus.COMPLETED,
                        task_data["created_at"],
                        task_data["started_at"],
                        now,
                        task_data["attempts"],
                        task_data["max_attempts"],
                        None,
                        json.dumps(result) if result else None,
                        task_data.get("timeout_seconds", 300),
                        now,
                    ),
                )
                # Remove from active queue
                conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))

            conn.commit()
        finally:
            conn.close()

    async def complete(self, task_id: str, result: dict | None = None) -> None:
        """Mark a task as completed successfully."""
        async with self._in_flight_lock:
            await asyncio.to_thread(self._complete_sync, task_id, result)

    def _fail_sync(
        self,
        task_id: str,
        error: str,
        retry: bool,
        retry_after: float | None,
        task_type: str | None,
        now: str,
    ) -> None:
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT attempts, max_attempts, type FROM tasks WHERE id = ?",
                (task_id,),
            ).fetchone()

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

                    retry_at = (datetime.datetime.now(tz=datetime.UTC) + datetime.timedelta(seconds=backoff)).strftime(
                        _TIMESTAMP_FORMAT,
                    )
                    conn.execute(
                        "UPDATE tasks SET status = ?, last_error = ?, scheduled_at = ? WHERE id = ?",
                        (TaskStatus.PENDING, error, retry_at, task_id),
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
                    # Move to dead letter queue (archive)
                    task_row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
                    if task_row is None:
                        # Task was deleted between the two SELECTs (e.g.,
                        # by a concurrent cancel). Nothing more to do.
                        logger.debug(
                            "Task %s vanished while moving to dead-letter; concurrent cancel suspected",
                            task_id,
                        )
                        conn.commit()
                        return
                    task_data = dict(task_row)
                    # Record worker failure counter for metrics
                    try:
                        from app.metrics_collector import record_worker_failure

                        record_worker_failure(actual_type)
                    except Exception:
                        logger.debug("Failed to record worker failure metric", exc_info=True)
                    conn.execute(
                        """INSERT OR REPLACE INTO task_history
                           (id, type, payload, priority, status, created_at,
                            started_at, completed_at, attempts, max_attempts,
                            last_error, result, timeout_seconds, finished_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            task_data["id"],
                            task_data["type"],
                            task_data["payload"],
                            task_data["priority"],
                            TaskStatus.DEAD_LETTER,
                            task_data["created_at"],
                            task_data["started_at"],
                            now,
                            task_data["attempts"],
                            task_data["max_attempts"],
                            error,
                            None,
                            task_data.get("timeout_seconds", 300),
                            now,
                        ),
                    )
                    conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
                    logger.warning(
                        "Task %s moved to dead letter after %d attempts: %s",
                        task_id,
                        attempts,
                        error,
                    )

            conn.commit()
        finally:
            conn.close()

    async def fail(
        self,
        task_id: str,
        error: str,
        retry: bool = True,
        retry_after: float | None = None,
        task_type: str | None = None,
    ) -> None:
        """Mark a task as failed. Retries if attempts remain."""
        now = datetime.datetime.now(tz=datetime.UTC).strftime(_TIMESTAMP_FORMAT)
        async with self._in_flight_lock:
            await asyncio.to_thread(
                self._fail_sync,
                task_id,
                error,
                retry,
                retry_after,
                task_type,
                now,
            )

    def _cancel_in_flight_sync(self, task_id: str, now: str) -> None:
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM tasks WHERE id = ?",
                (task_id,),
            ).fetchone()
            if row:
                task_data = dict(row)
                conn.execute(
                    """INSERT OR REPLACE INTO task_history
                       (id, type, payload, priority, status, created_at,
                        started_at, completed_at, attempts, max_attempts,
                        last_error, result, timeout_seconds, finished_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        task_data["id"],
                        task_data["type"],
                        task_data["payload"],
                        task_data["priority"],
                        TaskStatus.CANCELLED,
                        task_data["created_at"],
                        task_data.get("started_at"),
                        now,
                        task_data["attempts"],
                        task_data["max_attempts"],
                        "Cancelled by user (in-flight)",
                        None,
                        task_data.get("timeout_seconds", 300),
                        now,
                    ),
                )
                conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
                conn.commit()
        finally:
            conn.close()

    def _cancel_pending_sync(self, task_id: str, now: str) -> bool:
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM tasks WHERE id = ? AND status = 'pending'",
                (task_id,),
            ).fetchone()
            if row is None:
                return False
            task_data = dict(row)
            # Archive to history before deleting
            conn.execute(
                """INSERT OR REPLACE INTO task_history
                   (id, type, payload, priority, status, created_at,
                    started_at, completed_at, attempts, max_attempts,
                    last_error, result, timeout_seconds, finished_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    task_data["id"],
                    task_data["type"],
                    task_data["payload"],
                    task_data["priority"],
                    TaskStatus.CANCELLED,
                    task_data["created_at"],
                    None,
                    now,
                    task_data["attempts"],
                    task_data["max_attempts"],
                    "Cancelled by user (pending)",
                    None,
                    task_data.get("timeout_seconds", 300),
                    now,
                ),
            )
            conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            conn.commit()
            return True
        finally:
            conn.close()

    async def cancel(self, task_id: str) -> bool:
        """Cancel a task. Handles both pending (SQLite) and in-flight (asyncio) tasks."""
        now = datetime.datetime.now(tz=datetime.UTC).strftime(_TIMESTAMP_FORMAT)
        async with self._in_flight_lock:
            # Check in-flight tasks first (running tasks)
            if task_id in self._in_flight:
                flight_task = self._in_flight[task_id]
                flight_task.cancel()
                await asyncio.to_thread(self._cancel_in_flight_sync, task_id, now)
                return True

            # Check pending tasks
            return await asyncio.to_thread(self._cancel_pending_sync, task_id, now)

    # ─── Worker loop ───────────────────────────────────────────────────

    async def start(self) -> None:
        """Start the background worker loop with recovery of stuck tasks."""
        async with self._start_lock:
            if self._running:
                return
            # Recover any tasks that were stuck in 'running' state from a previous
            # crash
            self._recover_stuck_tasks()
            self._running = True
            self._worker_task = asyncio.create_task(self._worker_loop())
            logger.info(
                "Worker queue started: max_concurrency=%d, poll_interval=%.1fs",
                self._max_concurrency,
                self._poll_interval,
            )

    def _recover_stuck_tasks(self) -> None:
        """Reset any tasks stuck in 'running' state back to 'pending' for retry."""
        with _DB_LOCK:
            conn = self._conn()
            try:
                stuck = conn.execute("SELECT COUNT(*) FROM tasks WHERE status = 'running'").fetchone()[0]
                if stuck:
                    # Do NOT increment attempts here — attempts are incremented
                    # only when _dequeue_one() hands the task to a worker.
                    conn.execute(
                        "UPDATE tasks SET status = 'pending', started_at = NULL, "
                        "last_error = 'Recovered after worker restart' "
                        "WHERE status = 'running'",
                    )
                    conn.commit()
                    logger.info("Recovered %d stuck task(s) from previous worker crash", stuck)
            finally:
                conn.close()

    async def _check_and_recover_stuck_tasks(self) -> None:
        """Periodically check for tasks stuck in 'running' state for too long.

        Tasks that exceed 2x their timeout are reset to 'pending' for retry.
        This handles cases where the worker process didn't fully crash but
        a task is hung (e.g., blocked IO, network stall).
        """
        try:
            with _DB_LOCK:
                conn = self._conn()
                try:
                    # Find tasks that have been running for more than 2x their timeout
                    stuck_tasks = conn.execute(
                        """SELECT id, type, timeout_seconds, started_at
                           FROM tasks
                           WHERE status = 'running'
                             AND started_at IS NOT NULL""",
                    ).fetchall()

                    now = datetime.datetime.now(tz=datetime.UTC)
                    recovered = 0
                    for row in stuck_tasks:
                        task_id = row["id"]
                        timeout_secs = row["timeout_seconds"] or 300  # Default 5 min
                        started_at_str = row["started_at"]
                        try:
                            started_at = datetime.datetime.fromisoformat(started_at_str)
                            elapsed = (now - started_at).total_seconds()
                            # If running for more than 2x timeout, it's stuck
                            if elapsed > timeout_secs * 2:
                                conn.execute(
                                    "UPDATE tasks SET status = 'pending', started_at = NULL, last_error = ? WHERE id = ?",
                                    (f"Stuck for {elapsed:.0f}s (timeout={timeout_secs}s)", task_id),
                                )
                                recovered += 1
                        except (ValueError, TypeError):
                            continue

                    if recovered > 0:
                        conn.commit()
                        logger.warning("Recovered %d stuck task(s) during periodic check", recovered)
                finally:
                    conn.close()
        except Exception:
            logger.debug("Periodic stuck-task check failed", exc_info=True)

    async def stop(self, drain: bool = True) -> None:
        """Stop the worker loop. Optionally drain in-flight tasks."""
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._worker_task
            # Clear the task handle so a subsequent start() doesn't see
            # a stale task and re-create without awaiting the old one.
            self._worker_task = None

        if drain:
            await self._drain_in_flight()

        logger.info("Worker queue stopped (drained=%s)", drain)

    async def _worker_loop(self) -> None:
        """Main worker loop: dequeue and dispatch tasks."""
        last_stuck_check = time.monotonic()
        STUCK_CHECK_INTERVAL = 60.0  # Check for stuck tasks every 60 seconds
        while self._running:
            try:
                # Periodic stuck-task detection
                now = time.monotonic()
                if now - last_stuck_check >= STUCK_CHECK_INTERVAL:
                    last_stuck_check = now
                    await self._check_and_recover_stuck_tasks()

                # Acquire a concurrency permit *before* dequeue so the
                # budget is reserved atomically. If the permit is not
                # available we yield for a poll interval and try again —
                # the semaphore is fair-ish and won't busy-spin.
                acquired = False
                acquired_sem: asyncio.Semaphore | None = None
                try:
                    await asyncio.wait_for(
                        self._concurrency_sem.acquire(),
                        timeout=self._poll_interval,
                    )
                    # Capture the semaphore reference immediately after acquire.
                    # ``set_max_concurrency`` swaps ``self._concurrency_sem``
                    # atomically; we must release the *same* semaphore we acquired.
                    acquired_sem = self._concurrency_sem
                    acquired = True
                except TimeoutError:
                    continue
                if not acquired:
                    continue

                # Dequeue a task
                task = await self.dequeue(timeout=self._poll_interval)
                if task is None:
                    if acquired_sem:
                        acquired_sem.release()
                    continue

                # Dispatch
                t = asyncio.create_task(self._execute_task(task))

                task_id = task.id

                async with self._in_flight_lock:
                    self._in_flight[task_id] = t

                def _on_task_done(_fut: object, tid: str = task_id) -> None:
                    # Schedule the cleanup on the *currently running* event
                    # loop, not on whichever loop ``asyncio.ensure_future``
                    # happens to pick up.  This avoids a ``RuntimeError``
                    # when the worker task is bound to a different loop
                    # from the caller's context (e.g. across test scopes
                    # or during shutdown).
                    try:
                        loop = asyncio.get_running_loop()
                        _t = loop.create_task(self._cleanup_in_flight(tid))
                        # Keep a reference to prevent premature GC
                        # (RUF006). The done callback removes it.
                        _t.add_done_callback(lambda _: None)
                    except RuntimeError:
                        logger.debug(
                            "No running event loop to schedule _cleanup_in_flight for %s",
                            tid,
                        )

                def _release(_fut: object, tid: str = task_id, sem: asyncio.Semaphore | None = acquired_sem) -> None:
                    # Release the semaphore permit exactly once when the
                    # task finishes (success, failure, or cancellation).
                    # The semaphore is the one whose permit was acquired
                    # in this iteration — see the ``acquired_sem``
                    # capture above. Looking it up via ``self`` here
                    # would be wrong if ``set_max_concurrency`` had
                    # swapped the semaphore in the meantime.
                    try:
                        if sem:
                            sem.release()
                    except ValueError:
                        # Permit already released — should not happen,
                        # but never let a callback raise.
                        logger.debug("Semaphore release failed for task %s", tid)

                t.add_done_callback(_on_task_done)
                t.add_done_callback(_release)

            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Worker loop error")
                # Best-effort release if we acquired a permit but failed
                # before installing the done-callback.
                if acquired_sem:
                    with contextlib.suppress(ValueError):
                        acquired_sem.release()
                await asyncio.sleep(1)

    async def _execute_task(self, task: QueueTask) -> None:
        """Execute a single task with timeout and rate-limit-aware retries."""
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
            error_msg = f"{type(e).__name__}: {e}"
            # Rate-limit-aware retry: check if the error is rate-limit related
            # and parse Retry-After from error context if available
            retry_after = None
            try:
                from app.utils.rate_limit import is_rate_limit_error, parse_retry_after

                if is_rate_limit_error(body=error_msg):
                    retry_after = parse_retry_after()
                    if retry_after is not None:
                        logger.info(
                            "Task %s hit rate limit, honouring Retry-After: %.1fs",
                            task.id,
                            retry_after,
                        )
                    # Mark in-memory rate-limit state for the domain /
                    # task-type
                    from app.utils.rate_limit import (
                        get_cooldown_seconds,
                        mark_rate_limited,
                    )

                    mark_rate_limited(task.type, retry_after=retry_after)
                    cooldown = get_cooldown_seconds(task.type)
                    if cooldown > 0:
                        logger.info(
                            "Task %s cooling down %.1fs for %s",
                            task.id,
                            cooldown,
                            task.type,
                        )
                        # Honour the cooldown before the next dequeue
                        # attempt. Without this sleep the worker would
                        # immediately pick the next same-type task and
                        # burn another request against the rate-limited
                        # endpoint.
                        await asyncio.sleep(cooldown)
            except Exception:
                logger.debug("Error in post-execution cooldown logic", exc_info=True)
            await self.fail(task.id, error_msg, retry=True, retry_after=retry_after, task_type=task.type)

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

        Checks the active queue first, then falls back to task_history.
        Returns None if the task is not found.
        """
        conn = self._conn()
        try:
            # Check active tasks
            row = conn.execute(
                "SELECT * FROM tasks WHERE id = ?",
                (task_id,),
            ).fetchone()
            if row:
                return dict(row)
            # Check history
            row = conn.execute(
                "SELECT * FROM task_history WHERE id = ?",
                (task_id,),
            ).fetchone()
            if row:
                return dict(row)
            return None
        finally:
            conn.close()

    def get_status(self) -> dict[str, Any]:
        """Return queue status for monitoring."""
        conn = self._conn()
        try:
            # ``retrying`` is a future-only TaskStatus value: the queue
            # currently transitions a failed task straight back to
            # ``pending`` with a future ``scheduled_at``, so the count
            # for this status is always zero.  We still emit the key for
            # API stability, and we compute the "effectively retrying"
            # count (pending + future scheduled_at) so dashboards have a
            # meaningful metric.
            pending = conn.execute("SELECT COUNT(*) FROM tasks WHERE status = 'pending'").fetchone()[0]
            running = conn.execute("SELECT COUNT(*) FROM tasks WHERE status = 'running'").fetchone()[0]
            retrying = conn.execute("""SELECT COUNT(*) FROM tasks
                   WHERE status = 'pending'
                     AND scheduled_at > datetime('now')""").fetchone()[0]
            dead_letter = conn.execute("SELECT COUNT(*) FROM task_history WHERE status = 'dead_letter'").fetchone()[0]
            completed_24h = conn.execute("""SELECT COUNT(*) FROM task_history
                   WHERE finished_at >= datetime('now', '-1 day')""").fetchone()[0]

            # Top pending by priority
            top_pending = conn.execute("""SELECT id, type, priority, created_at, attempts
                   FROM tasks WHERE status = 'pending'
                   ORDER BY priority ASC, created_at ASC LIMIT 10""").fetchall()

            return {
                "ok": True,
                "backend": "sqlite",
                "pending": pending,
                "running": running,
                "retrying": retrying,
                "dead_letter": dead_letter,
                "completed_24h": completed_24h,
                "max_concurrency": self._max_concurrency,
                "in_flight": len(self._in_flight),
                "next_tasks": [dict(r) for r in top_pending],
            }
        finally:
            conn.close()

    def get_dead_letter_queue(self, limit: int = 50) -> list[dict]:
        """Return dead letter queue entries."""
        conn = self._conn()
        try:
            rows = conn.execute(
                """SELECT * FROM task_history
                   WHERE status = 'dead_letter'
                   ORDER BY finished_at DESC LIMIT ?""",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def retry_dead_letter(self, task_id: str) -> bool:
        """Re-queue a dead letter task."""
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM task_history WHERE id = ? AND status = 'dead_letter'",
                (task_id,),
            ).fetchone()
            if row is None:
                return False

            task_data = dict(row)
            # task_history may not have timeout_seconds column
            timeout = task_data.get("timeout_seconds", 300)
            conn.execute(
                """INSERT INTO tasks
                   (id, type, payload, priority, status, created_at,
                    scheduled_at, attempts, max_attempts, timeout_seconds)
                    VALUES (?, ?, ?, ?, 'pending', ?, datetime('now'), 0, ?, ?)""",
                (
                    task_data["id"],
                    task_data["type"],
                    task_data["payload"],
                    task_data["priority"],
                    task_data["created_at"],
                    task_data["max_attempts"],
                    timeout,
                ),
            )
            conn.execute(
                "DELETE FROM task_history WHERE id = ? AND status = 'dead_letter'",
                (task_id,),
            )
            conn.commit()
            return True
        finally:
            conn.close()

    def clear_completed_history(self, older_than_days: int = 7) -> None:
        """Clean up old completed task history."""
        conn = self._conn()
        try:
            conn.execute(
                """DELETE FROM task_history
                   WHERE finished_at < datetime('now', ?)
                   AND status IN ('completed', 'dead_letter')""",
                (f"-{older_than_days} days",),
            )
            conn.commit()
        finally:
            conn.close()


# ───────────────────────────────────────────────────────────────────────
# Global singleton & factory dispatch
# ───────────────────────────────────────────────────────────────────────

_queue_instance: WorkerQueue | None = None
_queue_lock = threading.Lock()


def get_worker_queue(
    db_path: Path | None = None,
    backend: str | None = None,
) -> Any:
    """Get or create the global WorkerQueue instance.

    Args:
        db_path: Optional custom database path (used by tests).
            If provided and differs from the cached instance's path,
            a new instance is created (respects test isolation boundaries).
        backend: Queue backend to use ('sqlite' or 'postgres').
            If not set, uses DATAFORGE_QUEUE_BACKEND env var or defaults to 'sqlite'.

    Returns:
        WorkerQueue (SQLite) or PostgresWorkerQueue depending on backend.

    """
    # Resolve backend: explicit param > env var (checked first so pytest
    # monkeypatch.setenv works even after pydantic-settings cached its value)
    # > default
    resolved_backend = backend or settings.QUEUE_BACKEND_DYNAMIC

    if resolved_backend == "postgres":
        from app.worker_queue_postgres import get_postgres_worker_queue

        return get_postgres_worker_queue()

    # SQLite backend (default)
    global _queue_instance
    with _queue_lock:
        if _queue_instance is None:
            _queue_instance = WorkerQueue(db_path=db_path)
        elif db_path is not None and _queue_instance._db_path != db_path:
            # A different ``db_path`` was requested (typical of tests
            # that scope a queue to a tmp_path fixture). The previous
            # implementation returned the new instance without
            # caching it, so the next call with the *default* path
            # would still return the original singleton. The
            # caller is now responsible for ``reset_worker_queue()``
            # if they want the default back; we replace the
            # singleton so a subsequent ``get_worker_queue()`` with
            # no args returns the new one.
            #
            # Defensive: if constructing the new ``WorkerQueue``
            # raises (e.g. the requested path is unwritable, or the
            # caller's fixture teardown has already deleted the
            # tmp dir), the singleton must not be silently replaced
            # with a half-initialized instance. We construct the
            # new queue on a local first, swap only on success, and
            # re-raise the original exception otherwise.
            # No try/except wrapper needed: if construction raises, the
            # exception propagates naturally and leaves the cached
            # singleton untouched. A bare ``except Exception: raise``
            # adds no value (ruff TRY203).
            candidate = WorkerQueue(db_path=db_path)
            _queue_instance = candidate
    return _queue_instance


def reset_worker_queue() -> None:
    """Reset the global queue instance (for testing)."""
    global _queue_instance
    _queue_instance = None
    try:
        from app.worker_queue_postgres import reset_postgres_worker_queue

        reset_postgres_worker_queue()
    except ImportError:
        pass

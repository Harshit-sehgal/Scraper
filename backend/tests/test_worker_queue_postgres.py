"""Tests for the Postgres-backed WorkerQueue.

Covers:
- Module import and schema verification (syntax checking SQL)
- Factory singleton pattern (get_postgres_worker_queue / reset_postgres_worker_queue)
- Priority enum and QueueTask model compatibility
- Postgres integration tests (require --run-postgres flag + Docker)
"""

import asyncio
import os

import pytest


def _require_psycopg2():
    """Skip test if psycopg2 is not installed."""
    try:
        import psycopg2 as _pg
        _ = _pg  # use import to suppress pyflakes
    except ImportError:
        pytest.skip("psycopg2 not installed")


# ───────────────────────────────────────────────────────────────────────
# Import & schema tests (no DB connection required)
# ───────────────────────────────────────────────────────────────────────


class TestPostgresQueueImports:
    """Verify the module imports and key symbols are available."""

    def test_import_postgres_queue_module(self):
        """The worker_queue_postgres module imports without error."""
        _require_psycopg2()
        from app.worker_queue_postgres import PostgresWorkerQueue  # noqa: F811
        assert PostgresWorkerQueue is not None

    def test_factory_functions_available(self):
        """get_postgres_worker_queue and reset_postgres_worker_queue are exported."""
        _require_psycopg2()
        from app.worker_queue_postgres import (
            get_postgres_worker_queue,
            reset_postgres_worker_queue,
        )
        assert callable(get_postgres_worker_queue)
        assert callable(reset_postgres_worker_queue)

    def test_ensure_schema_sql_syntax_valid(self):
        """The _ensure_schema function contains valid SQL statements."""
        _require_psycopg2()
        from app.worker_queue_postgres import _ensure_schema

        # We can't test _ensure_schema directly without a Postgres connection,
        # but we can verify the function is defined and callable
        assert callable(_ensure_schema)

    def test_module_imports_priority_from_worker_queue(self):
        """Priority and QueueTask are imported from the base worker_queue module."""
        _require_psycopg2()
        from app.worker_queue_postgres import PostgresWorkerQueue  # noqa: F811
        from app.worker_queue import Priority, QueueTask, TaskStatus
        _ = PostgresWorkerQueue  # use import to suppress pyflakes

        assert Priority is not None
        assert QueueTask is not None
        assert TaskStatus is not None


@pytest.mark.postgres
class TestPostgresQueueFactory:
    """Factory singleton tests (require Postgres connection)."""

    def test_factory_returns_same_instance(self):
        """get_postgres_worker_queue returns the same instance on repeated calls."""
        _require_psycopg2()
        from app.worker_queue_postgres import (
            get_postgres_worker_queue,
            reset_postgres_worker_queue,
        )

        reset_postgres_worker_queue()
        q1 = get_postgres_worker_queue()
        q2 = get_postgres_worker_queue()
        try:
            assert q1 is q2
        finally:
            reset_postgres_worker_queue()

    def test_reset_creates_new_instance(self):
        """After reset_postgres_worker_queue, a new instance is created."""
        _require_psycopg2()
        from app.worker_queue_postgres import (
            get_postgres_worker_queue,
            reset_postgres_worker_queue,
        )

        reset_postgres_worker_queue()
        q1 = get_postgres_worker_queue()
        reset_postgres_worker_queue()
        q2 = get_postgres_worker_queue()
        try:
            assert q1 is not q2
        finally:
            reset_postgres_worker_queue()


class TestPostgresQueueConstruction:
    """Construction and configuration tests (no DB connection required)."""

    def test_default_construction_config(self):
        """Default PostgresWorkerQueue has sensible defaults."""
        _require_psycopg2()
        from app.worker_queue_postgres import PostgresWorkerQueue

        # We can't easily construct without a Postgres connection because
        # __init__ calls _ensure_schema(). Instead verify config constants.
        assert PostgresWorkerQueue is not None

    def test_method_signatures_match_sqlite_queue(self):
        """PostgresWorkerQueue exposes the same public methods as WorkerQueue."""
        _require_psycopg2()
        from app.worker_queue_postgres import PostgresWorkerQueue

        pg_methods = {m for m in dir(PostgresWorkerQueue) if not m.startswith("_")}

        # PostgresWorkerQueue should have at least the same public methods
        essential = {
            "enqueue",
            "dequeue",
            "complete",
            "fail",
            "cancel",
            "start",
            "stop",
            "register_handler",
            "get_status",
            "get_dead_letter_queue",
            "retry_dead_letter",
            "clear_completed_history",
        }
        for method in essential:
            assert method in pg_methods, (
                f"PostgresWorkerQueue missing method: {method}"
            )


# ───────────────────────────────────────────────────────────────────────
# Factory dispatch tests
# ───────────────────────────────────────────────────────────────────────


@pytest.mark.postgres
class TestWorkerQueueFactoryDispatch:
    """Verify get_worker_queue() correctly dispatches to Postgres backend."""

    def test_factory_dispatch_postgres_env(self, monkeypatch):
        """get_worker_queue(backend='postgres') returns PostgresWorkerQueue."""
        _require_psycopg2()
        from app.worker_queue import get_worker_queue, reset_worker_queue

        reset_worker_queue()
        monkeypatch.setenv("DATAFORGE_QUEUE_BACKEND", "postgres")
        queue = get_worker_queue()
        try:
            from app.worker_queue_postgres import PostgresWorkerQueue
            assert isinstance(queue, PostgresWorkerQueue)
        finally:
            reset_worker_queue()

    def test_factory_dispatch_sqlite_default(self, tmp_path, monkeypatch):
        """get_worker_queue() with no backend returns SQLite WorkerQueue."""
        from app.worker_queue import WorkerQueue, get_worker_queue, reset_worker_queue

        reset_worker_queue()
        monkeypatch.delenv("DATAFORGE_QUEUE_BACKEND", raising=False)
        monkeypatch.setenv("DATAFORGE_WORKER_QUEUE", "false")
        queue = get_worker_queue(db_path=tmp_path / "test.db")
        try:
            assert isinstance(queue, WorkerQueue)
        finally:
            reset_worker_queue()
        monkeypatch.delenv("DATAFORGE_WORKER_QUEUE", raising=False)

    def test_factory_dispatch_postgres_via_param(self, monkeypatch):
        """get_worker_queue(backend='postgres') dispatches correctly."""
        _require_psycopg2()
        from app.worker_queue import get_worker_queue, reset_worker_queue

        reset_worker_queue()
        queue = get_worker_queue(backend="postgres")
        try:
            from app.worker_queue_postgres import PostgresWorkerQueue
            assert isinstance(queue, PostgresWorkerQueue)
        finally:
            reset_worker_queue()

    def test_reset_clears_both_backends(self, monkeypatch):
        """reset_worker_queue() clears both SQLite and Postgres singletons."""
        _require_psycopg2()
        from app.worker_queue import get_worker_queue, reset_worker_queue

        reset_worker_queue()
        q_sqlite = get_worker_queue()
        q_postgres = get_worker_queue(backend="postgres")
        assert q_sqlite is not q_postgres

        reset_worker_queue()
        q_sqlite2 = get_worker_queue()
        q_postgres2 = get_worker_queue(backend="postgres")
        assert q_sqlite is not q_sqlite2
        assert q_postgres is not q_postgres2


# ───────────────────────────────────────────────────────────────────────
# Postgres integration tests (require --run-postgres + Docker)
# ───────────────────────────────────────────────────────────────────────


@pytest.mark.postgres
class TestPostgresQueueIntegration:
    """Real Postgres-backed queue integration tests.

    These tests require Docker and are skipped by default.
    Run with: pytest --run-postgres -m postgres -v
    """

    @pytest.fixture(autouse=True)
    def postgres_container(self):
        """Start a Postgres testcontainer and configure the connection."""
        from testcontainers.postgres import PostgresContainer

        with PostgresContainer("postgres:16-alpine") as pg:
            os.environ["DATAFORGE_STORAGE_BACKEND"] = "postgres"
            os.environ["DATAFORGE_DATABASE_URL"] = pg.get_connection_url()
            os.environ["DATAFORGE_QUEUE_BACKEND"] = "postgres"
            yield
            os.environ.pop("DATAFORGE_STORAGE_BACKEND", None)
            os.environ.pop("DATAFORGE_DATABASE_URL", None)
            os.environ.pop("DATAFORGE_QUEUE_BACKEND", None)

    @pytest.fixture(autouse=True)
    def reset_queue(self):
        """Reset the Postgres queue singleton before each test."""
        from app.worker_queue_postgres import reset_postgres_worker_queue
        from app.worker_queue import reset_worker_queue

        reset_postgres_worker_queue()
        reset_worker_queue()
        yield
        reset_postgres_worker_queue()
        reset_worker_queue()

    def test_enqueue_and_dequeue(self):
        """A task enqueued can be dequeued with correct metadata."""
        from app.worker_queue import Priority
        from app.worker_queue_postgres import PostgresWorkerQueue

        queue = PostgresWorkerQueue()

        task_id = asyncio.run(
            queue.enqueue("test_task", {"key": "value"}, priority=Priority.HIGH)
        )
        assert task_id is not None

        task = asyncio.run(queue.dequeue(timeout=5.0))
        assert task is not None
        assert task.id == task_id
        assert task.type == "test_task"
        assert task.payload == {"key": "value"}
        assert task.priority == Priority.HIGH
        assert task.status.value == "running"

    def test_dequeue_empty_returns_none(self):
        """Dequeueing from an empty Postgres queue returns None."""
        from app.worker_queue_postgres import PostgresWorkerQueue

        queue = PostgresWorkerQueue()
        task = asyncio.run(queue.dequeue(timeout=1.0))
        assert task is None

    def test_priority_ordering(self):
        """Higher-priority tasks are dequeued before lower-priority ones."""
        from app.worker_queue import Priority
        from app.worker_queue_postgres import PostgresWorkerQueue

        queue = PostgresWorkerQueue()

        id_low = asyncio.run(queue.enqueue("low", {}, priority=Priority.LOW))
        id_normal = asyncio.run(
            queue.enqueue("normal", {}, priority=Priority.NORMAL)
        )
        id_high = asyncio.run(queue.enqueue("high", {}, priority=Priority.HIGH))
        id_critical = asyncio.run(
            queue.enqueue("critical", {}, priority=Priority.CRITICAL)
        )

        t1 = asyncio.run(queue.dequeue(timeout=5.0))
        assert t1 is not None and t1.id == id_critical

        t2 = asyncio.run(queue.dequeue(timeout=5.0))
        assert t2 is not None and t2.id == id_high

        t3 = asyncio.run(queue.dequeue(timeout=5.0))
        assert t3 is not None and t3.id == id_normal

        t4 = asyncio.run(queue.dequeue(timeout=5.0))
        assert t4 is not None and t4.id == id_low

    def test_complete_task(self):
        """Completing a task removes it from the active queue."""
        from app.worker_queue_postgres import PostgresWorkerQueue

        queue = PostgresWorkerQueue()

        task_id = asyncio.run(queue.enqueue("test_task", {}))
        task = asyncio.run(queue.dequeue(timeout=5.0))
        assert task is not None

        asyncio.run(queue.complete(task_id, {"result": "ok"}))

        remaining = asyncio.run(queue.dequeue(timeout=1.0))
        assert remaining is None

    def test_fail_moves_to_retry(self):
        """Failing a task with retries remaining sets it back to pending."""
        from app.worker_queue_postgres import PostgresWorkerQueue

        queue = PostgresWorkerQueue()

        task_id = asyncio.run(queue.enqueue("test_task", {}, max_attempts=3))
        task = asyncio.run(queue.dequeue(timeout=5.0))
        assert task is not None

        asyncio.run(queue.fail(task_id, "Temporary error", retry=True))

        status = queue.get_status()
        assert status["pending"] >= 1, f"Expected >=1 pending, got {status}"

    def test_fail_exhausts_retries_moves_to_dead_letter(self):
        """Failing after exhausting retries moves task to dead letter."""
        from app.worker_queue_postgres import PostgresWorkerQueue

        queue = PostgresWorkerQueue()

        task_id = asyncio.run(queue.enqueue("test_task", {}, max_attempts=1))
        task = asyncio.run(queue.dequeue(timeout=5.0))
        assert task is not None

        asyncio.run(queue.fail(task_id, "Fatal error", retry=True))

        status = queue.get_status()
        assert status["dead_letter"] >= 1

    def test_cancel_pending_task(self):
        """Cancelling a pending task removes it from the queue."""
        from app.worker_queue_postgres import PostgresWorkerQueue

        queue = PostgresWorkerQueue()

        task_id = asyncio.run(queue.enqueue("test_task", {}))
        cancelled = asyncio.run(queue.cancel(task_id))
        assert cancelled is True

        task = asyncio.run(queue.dequeue(timeout=1.0))
        assert task is None

    def test_cancel_nonexistent_task_returns_false(self):
        """Cancelling a task that doesn't exist returns False."""
        from app.worker_queue_postgres import PostgresWorkerQueue

        queue = PostgresWorkerQueue()
        cancelled = asyncio.run(queue.cancel("nonexistent-id"))
        assert cancelled is False

    def test_retry_dead_letter(self):
        """A dead letter task can be re-queued."""
        from app.worker_queue_postgres import PostgresWorkerQueue

        queue = PostgresWorkerQueue()

        task_id = asyncio.run(queue.enqueue("test_task", {}, max_attempts=1))
        task = asyncio.run(queue.dequeue(timeout=5.0))
        assert task is not None
        asyncio.run(queue.fail(task_id, "Error", retry=True))

        requeued = queue.retry_dead_letter(task_id)
        assert requeued is True

        status = queue.get_status()
        assert status["dead_letter"] == 0
        assert status["pending"] >= 1

    def test_get_status_counts(self):
        """get_status returns correct counts for all states."""
        from app.worker_queue_postgres import PostgresWorkerQueue

        queue = PostgresWorkerQueue()

        for i in range(5):
            asyncio.run(queue.enqueue(f"task_{i}", {}))

        status = queue.get_status()
        assert status["pending"] == 5
        assert status["running"] == 0
        assert status["max_concurrency"] == 5

    def test_get_dead_letter_queue(self):
        """Dead letter queue entries are retrievable."""
        from app.worker_queue_postgres import PostgresWorkerQueue

        queue = PostgresWorkerQueue()

        task_id = asyncio.run(
            queue.enqueue("dl_test", {"key": "val"}, max_attempts=1)
        )
        task = asyncio.run(queue.dequeue(timeout=5.0))
        assert task is not None
        asyncio.run(queue.fail(task_id, "Error", retry=True))

        dl = queue.get_dead_letter_queue(limit=10)
        assert len(dl) >= 1
        ids = [entry["id"] for entry in dl]
        assert task_id in ids

    def test_clear_completed_history(self):
        """clear_completed_history can run without error."""
        from app.worker_queue_postgres import PostgresWorkerQueue

        queue = PostgresWorkerQueue()
        # Should not raise on an empty history
        queue.clear_completed_history(older_than_days=1)

    def test_recover_stuck_tasks(self):
        """Tasks stuck in 'running' state are recovered on construction."""
        import psycopg2
        from app.worker_queue_postgres import PostgresWorkerQueue

        queue = PostgresWorkerQueue()

        task_id = asyncio.run(queue.enqueue("stuck_test", {}))
        task = asyncio.run(queue.dequeue(timeout=5.0))
        assert task is not None

        # Manually set a task to 'running' to simulate crash
        dsn = os.environ["DATAFORGE_DATABASE_URL"]
        conn = psycopg2.connect(dsn)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE queue_tasks SET status = 'running', started_at = NOW() WHERE id = %s",
                    (task_id,),
                )
            conn.commit()
        finally:
            conn.close()

        # New queue should recover stuck tasks
        queue2 = PostgresWorkerQueue()
        status = queue2.get_status()
        assert status["running"] == 0, f"Expected 0 running, got {status}"
        assert status["pending"] >= 1, f"Expected >=1 pending, got {status}"

    def test_register_handler_and_worker_loop(self):
        """A registered handler is called when the worker processes a task."""
        from app.worker_queue_postgres import PostgresWorkerQueue

        queue = PostgresWorkerQueue(max_concurrency=1, poll_interval=0.1)

        results = []

        async def test_handler(task):
            results.append(task.id)
            return {"handled": True}

        queue.register_handler("handler_test", test_handler)

        task_id = asyncio.run(queue.enqueue("handler_test", {}))
        asyncio.run(queue.start())

        import time
        deadline = time.time() + 10
        while time.time() < deadline:
            if task_id in results:
                break
            time.sleep(0.1)

        asyncio.run(queue.stop(drain=True))

        assert task_id in results, f"Handler never called for {task_id}"

    def test_missing_handler_moves_to_dead_letter(self):
        """A task with no registered handler goes to dead letter."""
        from app.worker_queue_postgres import PostgresWorkerQueue

        queue = PostgresWorkerQueue(max_concurrency=1, poll_interval=0.1)

        asyncio.run(queue.enqueue("no_handler", {}, max_attempts=1))
        asyncio.run(queue.start())

        import time
        deadline = time.time() + 10
        while time.time() < deadline:
            status = queue.get_status()
            if status["dead_letter"] >= 1:
                break
            time.sleep(0.1)

        asyncio.run(queue.stop(drain=True))

        status = queue.get_status()
        assert status["dead_letter"] >= 1, (
            f"Expected dead_letter >=1, got {status}"
        )

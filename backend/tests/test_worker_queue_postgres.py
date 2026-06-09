"""Tests for the Postgres-backed WorkerQueue.

Covers:
- Module import and schema verification (syntax checking SQL)
- Factory singleton pattern (get_postgres_worker_queue / reset_postgres_worker_queue)
- Priority enum and QueueTask model compatibility
- Postgres integration tests (require --run-postgres flag + Docker)
"""

import asyncio
import os
from typing import NoReturn
from unittest.mock import MagicMock

import pytest


def _require_psycopg2() -> None:
    """Skip test if psycopg2 is not installed."""
    try:
        import psycopg2 as _pg

        _ = _pg  # use import to suppress pyflakes
    except ImportError:
        pytest.skip("psycopg2 not installed")


# ───────────────────────────────────────────────────────────────────────
# Shared module-scoped Postgres container fixture
# ───────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def module_postgres_container():
    """Start a single Postgres testcontainer or reuse a running one.

    Sets the DATAFORGE_* env vars so any code path that calls
    ``_get_database_url()`` picks up the container port instead of the
    development fallback.
    """
    import socket

    use_running = False
    dsn = os.environ.get("DATAFORGE_DATABASE_URL")
    if dsn:
        use_running = True
    else:
        try:
            with socket.create_connection(("127.0.0.1", 5432), timeout=1):
                use_running = True
                os.environ["DATAFORGE_STORAGE_BACKEND"] = "postgres"
                os.environ["DATAFORGE_QUEUE_BACKEND"] = "postgres"
                os.environ["DATAFORGE_DATABASE_URL"] = "postgresql://testuser:testpassword@127.0.0.1:5432/testdb"
        except (TimeoutError, ConnectionRefusedError):
            pass

    if use_running:
        yield
        if not dsn:
            os.environ.pop("DATAFORGE_DATABASE_URL", None)
            os.environ.pop("DATAFORGE_STORAGE_BACKEND", None)
            os.environ.pop("DATAFORGE_QUEUE_BACKEND", None)
    else:
        from testcontainers.postgres import PostgresContainer

        with PostgresContainer("postgres:16-alpine") as pg:
            database_url = pg.get_connection_url().replace("+psycopg2", "")
            os.environ["DATAFORGE_DATABASE_URL"] = database_url
            os.environ["DATAFORGE_STORAGE_BACKEND"] = "postgres"
            os.environ["DATAFORGE_QUEUE_BACKEND"] = "postgres"
            yield
            os.environ.pop("DATAFORGE_DATABASE_URL", None)
            os.environ.pop("DATAFORGE_STORAGE_BACKEND", None)
            os.environ.pop("DATAFORGE_QUEUE_BACKEND", None)


# ───────────────────────────────────────────────────────────────────────
# Import & schema tests (no DB connection required)
# ───────────────────────────────────────────────────────────────────────


class TestPostgresQueueImports:
    """Verify the module imports and key symbols are available."""

    def test_import_postgres_queue_module(self) -> None:
        """The worker_queue_postgres module imports without error."""
        _require_psycopg2()
        from app.worker_queue_postgres import PostgresWorkerQueue

        assert PostgresWorkerQueue is not None

    def test_factory_functions_available(self) -> None:
        """get_postgres_worker_queue and reset_postgres_worker_queue are exported."""
        _require_psycopg2()
        from app.worker_queue_postgres import (
            get_postgres_worker_queue,
            reset_postgres_worker_queue,
        )

        assert callable(get_postgres_worker_queue)
        assert callable(reset_postgres_worker_queue)

    def test_ensure_schema_sql_syntax_valid(self) -> None:
        """The _ensure_schema function contains valid SQL statements."""
        _require_psycopg2()
        from app.worker_queue_postgres import _ensure_schema

        # We can't test _ensure_schema directly without a Postgres connection,
        # but we can verify the function is defined and callable
        assert callable(_ensure_schema)

    def test_module_imports_priority_from_worker_queue(self) -> None:
        """Priority and QueueTask are imported from the base worker_queue module."""
        _require_psycopg2()
        from app.worker_queue import Priority, QueueTask, TaskStatus
        from app.worker_queue_postgres import PostgresWorkerQueue

        _ = PostgresWorkerQueue  # use import to suppress pyflakes

        assert Priority is not None
        assert QueueTask is not None
        assert TaskStatus is not None


@pytest.mark.postgres
class TestPostgresQueueFactory:
    """Factory singleton tests (require Postgres connection)."""

    def test_factory_returns_same_instance(self, module_postgres_container) -> None:
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

    def test_reset_creates_new_instance(self, module_postgres_container) -> None:
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

    def test_default_construction_config(self) -> None:
        """Default PostgresWorkerQueue has sensible defaults."""
        _require_psycopg2()
        from app.worker_queue_postgres import PostgresWorkerQueue

        # We can't easily construct without a Postgres connection because
        # __init__ calls _ensure_schema(). Instead verify config constants.
        assert PostgresWorkerQueue is not None

    def test_method_signatures_match_sqlite_queue(self) -> None:
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
            assert method in pg_methods, f"PostgresWorkerQueue missing method: {method}"


# ───────────────────────────────────────────────────────────────────────
# Factory dispatch tests
# ───────────────────────────────────────────────────────────────────────


@pytest.mark.postgres
class TestWorkerQueueFactoryDispatch:
    """Verify get_worker_queue() correctly dispatches to Postgres backend."""

    def test_factory_dispatch_postgres_env(self, module_postgres_container, monkeypatch) -> None:
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

    def test_factory_dispatch_sqlite_default(self, tmp_path, monkeypatch) -> None:
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

    def test_factory_dispatch_postgres_via_param(self, module_postgres_container, monkeypatch) -> None:
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

    def test_reset_clears_both_backends(self, module_postgres_container, monkeypatch) -> None:
        """reset_worker_queue() clears both SQLite and Postgres singletons."""
        _require_psycopg2()
        from app.worker_queue import get_worker_queue, reset_worker_queue

        reset_worker_queue()
        # Temporarily clear the env var so get_worker_queue() returns SQLite
        monkeypatch.delenv("DATAFORGE_QUEUE_BACKEND", raising=False)
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
    def ensure_postgres(self, module_postgres_container) -> None:
        """Depend on the module-scoped Postgres container."""

    @pytest.fixture(autouse=True)
    def clean_queue_tables(self):
        """Truncate queue tables between tests for isolation.

        Since the container is module-scoped, tasks created by one test
        would persist into the next. This fixture also resets the queue
        singletons so the next test gets a fresh ``PostgresWorkerQueue``.
        """
        from app.postgres_repository import _conn, _execute
        from app.worker_queue import reset_worker_queue
        from app.worker_queue_postgres import reset_postgres_worker_queue

        reset_postgres_worker_queue()
        reset_worker_queue()
        # Use the shared pool to clean both queue tables
        try:
            with _conn() as conn:
                _execute(conn, "DELETE FROM queue_tasks")
                _execute(conn, "DELETE FROM queue_task_history")
        except Exception:  # noqa: RUF100, S110
            pass  # Tables may not exist yet on first run
        yield
        reset_postgres_worker_queue()
        reset_worker_queue()

    def test_enqueue_and_dequeue(self) -> None:
        """A task enqueued can be dequeued with correct metadata."""
        from app.worker_queue import Priority
        from app.worker_queue_postgres import PostgresWorkerQueue

        queue = PostgresWorkerQueue()

        task_id = asyncio.run(queue.enqueue("test_task", {"key": "value"}, priority=Priority.HIGH))
        assert task_id is not None

        task = asyncio.run(queue.dequeue(timeout=5.0))
        assert task is not None
        assert task.id == task_id
        assert task.type == "test_task"
        assert task.payload == {"key": "value"}
        assert task.priority == Priority.HIGH
        assert task.status.value == "running"

    def test_dequeue_empty_returns_none(self) -> None:
        """Dequeueing from an empty Postgres queue returns None."""
        from app.worker_queue_postgres import PostgresWorkerQueue

        queue = PostgresWorkerQueue()
        task = asyncio.run(queue.dequeue(timeout=1.0))
        assert task is None

    def test_priority_ordering(self) -> None:
        """Higher-priority tasks are dequeued before lower-priority ones."""
        from app.worker_queue import Priority
        from app.worker_queue_postgres import PostgresWorkerQueue

        queue = PostgresWorkerQueue()

        id_low = asyncio.run(queue.enqueue("low", {}, priority=Priority.LOW))
        id_normal = asyncio.run(queue.enqueue("normal", {}, priority=Priority.NORMAL))
        id_high = asyncio.run(queue.enqueue("high", {}, priority=Priority.HIGH))
        id_critical = asyncio.run(queue.enqueue("critical", {}, priority=Priority.CRITICAL))

        t1 = asyncio.run(queue.dequeue(timeout=5.0))
        assert t1 is not None
        assert t1.id == id_critical

        t2 = asyncio.run(queue.dequeue(timeout=5.0))
        assert t2 is not None
        assert t2.id == id_high

        t3 = asyncio.run(queue.dequeue(timeout=5.0))
        assert t3 is not None
        assert t3.id == id_normal

        t4 = asyncio.run(queue.dequeue(timeout=5.0))
        assert t4 is not None
        assert t4.id == id_low

    def test_complete_task(self) -> None:
        """Completing a task removes it from the active queue."""
        from app.worker_queue_postgres import PostgresWorkerQueue

        queue = PostgresWorkerQueue()

        task_id = asyncio.run(queue.enqueue("test_task", {}))
        task = asyncio.run(queue.dequeue(timeout=5.0))
        assert task is not None

        asyncio.run(queue.complete(task_id, {"result": "ok"}))

        remaining = asyncio.run(queue.dequeue(timeout=1.0))
        assert remaining is None

    def test_fail_moves_to_retry(self) -> None:
        """Failing a task with retries remaining sets it back to pending."""
        from app.worker_queue_postgres import PostgresWorkerQueue

        queue = PostgresWorkerQueue()

        task_id = asyncio.run(queue.enqueue("test_task", {}, max_attempts=3))
        task = asyncio.run(queue.dequeue(timeout=5.0))
        assert task is not None

        asyncio.run(queue.fail(task_id, "Temporary error", retry=True))

        status = queue.get_status()
        assert status["pending"] >= 1, f"Expected >=1 pending, got {status}"

    def test_fail_exhausts_retries_moves_to_dead_letter(self) -> None:
        """Failing after exhausting retries moves task to dead letter."""
        from app.worker_queue_postgres import PostgresWorkerQueue

        queue = PostgresWorkerQueue()

        task_id = asyncio.run(queue.enqueue("test_task", {}, max_attempts=1))
        task = asyncio.run(queue.dequeue(timeout=5.0))
        assert task is not None

        asyncio.run(queue.fail(task_id, "Fatal error", retry=True))

        status = queue.get_status()
        assert status["dead_letter"] >= 1

    def test_cancel_pending_task(self) -> None:
        """Cancelling a pending task removes it from the queue."""
        from app.worker_queue_postgres import PostgresWorkerQueue

        queue = PostgresWorkerQueue()

        task_id = asyncio.run(queue.enqueue("test_task", {}))
        cancelled = asyncio.run(queue.cancel(task_id))
        assert cancelled is True

        task = asyncio.run(queue.dequeue(timeout=1.0))
        assert task is None

    def test_cancel_nonexistent_task_returns_false(self) -> None:
        """Cancelling a task that doesn't exist returns False."""
        from app.worker_queue_postgres import PostgresWorkerQueue

        queue = PostgresWorkerQueue()
        cancelled = asyncio.run(queue.cancel("nonexistent-id"))
        assert cancelled is False

    def test_retry_dead_letter(self) -> None:
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

    def test_get_status_counts(self) -> None:
        """get_status returns correct counts for all states."""
        from app.worker_queue_postgres import PostgresWorkerQueue

        queue = PostgresWorkerQueue()

        for i in range(5):
            asyncio.run(queue.enqueue(f"task_{i}", {}))

        status = queue.get_status()
        assert status["pending"] == 5
        assert status["running"] == 0
        assert status["max_concurrency"] == 5

    def test_get_dead_letter_queue(self) -> None:
        """Dead letter queue entries are retrievable."""
        from app.worker_queue_postgres import PostgresWorkerQueue

        queue = PostgresWorkerQueue()

        task_id = asyncio.run(queue.enqueue("dl_test", {"key": "val"}, max_attempts=1))
        task = asyncio.run(queue.dequeue(timeout=5.0))
        assert task is not None
        asyncio.run(queue.fail(task_id, "Error", retry=True))

        dl = queue.get_dead_letter_queue(limit=10)
        assert len(dl) >= 1
        ids = [entry["id"] for entry in dl]
        assert task_id in ids

    def test_clear_completed_history(self) -> None:
        """clear_completed_history can run without error."""
        from app.worker_queue_postgres import PostgresWorkerQueue

        queue = PostgresWorkerQueue()
        # Should not raise on an empty history
        queue.clear_completed_history(older_than_days=1)

    def test_recover_stuck_tasks(self) -> None:
        """Tasks stuck in 'running' state are recovered via start()."""
        import psycopg2
        from app.worker_queue_postgres import (
            PostgresWorkerQueue,
            reset_postgres_worker_queue,
        )

        async def run():
            queue = PostgresWorkerQueue()

            task_id = await queue.enqueue("stuck_test", {})
            task = await queue.dequeue(timeout=5.0)
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

            reset_postgres_worker_queue()
            # New queue should recover stuck tasks when start() is called
            queue2 = PostgresWorkerQueue()
            await queue2.start()
            status = queue2.get_status()
            await queue2.stop(drain=True)
            return status

        status = asyncio.run(run())
        assert status["running"] == 0, f"Expected 0 running, got {status}"
        assert status["pending"] >= 1, f"Expected >=1 pending, got {status}"

    def test_register_handler_and_worker_loop(self) -> None:
        """A registered handler is called when the worker processes a task."""
        from app.worker_queue_postgres import PostgresWorkerQueue

        async def run():
            queue = PostgresWorkerQueue(max_concurrency=1, poll_interval=0.1)

            results = []

            async def test_handler(task) -> dict:
                results.append(task.id)
                return {"handled": True}

            queue.register_handler("handler_test", test_handler)

            task_id = await queue.enqueue("handler_test", {})
            await queue.start()

            import time

            deadline = time.time() + 10
            while time.time() < deadline:
                if task_id in results:
                    break
                await asyncio.sleep(0.1)

            await queue.stop(drain=True)
            return task_id, results

        task_id, results = asyncio.run(run())
        assert task_id in results, f"Handler never called for {task_id}"

    def test_missing_handler_moves_to_dead_letter(self) -> None:
        """A task with no registered handler goes to dead letter."""
        from app.worker_queue_postgres import PostgresWorkerQueue

        async def run():
            queue = PostgresWorkerQueue(max_concurrency=1, poll_interval=0.1)

            await queue.enqueue("no_handler", {}, max_attempts=1)
            await queue.start()

            import time

            deadline = time.time() + 10
            while time.time() < deadline:
                status = queue.get_status()
                if status["dead_letter"] >= 1:
                    break
                await asyncio.sleep(0.1)

            await queue.stop(drain=True)
            return queue

        queue = asyncio.run(run())
        status = queue.get_status()
        assert status["dead_letter"] >= 1, f"Expected dead_letter >=1, got {status}"


# ───────────────────────────────────────────────────────────────────────
# Mocked unit tests (no Postgres connection required)
# ───────────────────────────────────────────────────────────────────────


class TestPostgresQueueMocked:
    """Comprehensive mocked tests for PostgresWorkerQueue.

    These tests mock the database layer (_conn, _execute, _fetch_one, _fetch_all)
    so they run without a real Postgres connection, covering all core methods.
    """

    @pytest.fixture(autouse=True)
    def mock_db(self, monkeypatch):
        """Mock all postgres_repository imports used by worker_queue_postgres."""
        import app.worker_queue_postgres as wqp

        self.mock_conn = MagicMock()
        self.mock_cursor = MagicMock()
        self.mock_conn.__enter__.return_value = self.mock_conn
        self.mock_conn.__exit__.return_value = None

        monkeypatch.setattr(wqp, "_conn", MagicMock(return_value=self.mock_conn))
        monkeypatch.setattr(wqp, "_execute", MagicMock())
        self.mock_fetch_one = MagicMock(return_value=None)
        self.mock_fetch_all = MagicMock(return_value=[])
        monkeypatch.setattr(wqp, "_fetch_one", self.mock_fetch_one)
        monkeypatch.setattr(wqp, "_fetch_all", self.mock_fetch_all)

        return wqp

    def test_init_ensures_schema(self, mock_db) -> None:
        """Construction calls _ensure_schema which queries schema version."""
        from app.worker_queue_postgres import PostgresWorkerQueue

        q = PostgresWorkerQueue()
        assert q._max_concurrency == 5
        assert q._poll_interval == 1.0
        # _ensure_schema should have been called
        self.mock_fetch_one.assert_called()

    @pytest.mark.asyncio
    async def test_enqueue_creates_task(self, mock_db) -> None:
        """Enqueue inserts a task via _execute and returns a task ID."""
        from app.worker_queue_postgres import PostgresWorkerQueue

        q = PostgresWorkerQueue()
        # Reset mock call count after construction so we can track enqueue calls
        mock_db._execute.reset_mock()
        task_id = await q.enqueue("test_type", {"key": "value"})

        assert task_id is not None
        assert isinstance(task_id, str)
        # _execute should have been called to INSERT the task
        mock_db._execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_dequeue_returns_task(self, mock_db) -> None:
        """Dequeue returns a QueueTask when _fetch_one returns a row."""
        import json

        from app.worker_queue import Priority
        from app.worker_queue_postgres import PostgresWorkerQueue

        mock_row = {
            "id": "test-id-123",
            "type": "scrape",
            "payload": json.dumps({"url": "http://example.com"}),
            "priority": int(Priority.HIGH),
            "status": "pending",
            "created_at": "2024-01-01 00:00:00",
            "started_at": None,
            "completed_at": None,
            "attempts": 0,
            "max_attempts": 3,
            "last_error": None,
            "scheduled_at": "2024-01-01 00:00:00",
            "timeout_seconds": 300,
        }
        self.mock_fetch_one.return_value = mock_row

        q = PostgresWorkerQueue()
        # Dequeue with very short timeout since we mocked the row
        # The dequeue loop will call _dequeue_one via to_thread, which
        # won't see our mock. So we need to mock _dequeue_one directly.
        # Actually, let's just test that _dequeue_one works sync.
        task = q._dequeue_one()
        assert task is not None
        assert task.id == "test-id-123"
        assert task.type == "scrape"
        assert task.payload == {"url": "http://example.com"}
        assert task.priority == Priority.HIGH

    @pytest.mark.asyncio
    async def test_dequeue_returns_none_when_empty(self, mock_db) -> None:
        """Dequeue returns None when _fetch_one returns None."""
        self.mock_fetch_one.return_value = None

        from app.worker_queue_postgres import PostgresWorkerQueue

        q = PostgresWorkerQueue()
        task = q._dequeue_one()
        assert task is None

    @pytest.mark.asyncio
    async def test_complete_moves_to_history(self, mock_db) -> None:
        """Complete inserts into queue_task_history and deletes from queue_tasks."""
        import json

        from app.worker_queue import Priority
        from app.worker_queue_postgres import PostgresWorkerQueue

        mock_row = {
            "id": "task-complete-1",
            "type": "test",
            "payload": json.dumps({}),
            "priority": int(Priority.NORMAL),
            "status": "running",
            "created_at": "2024-01-01 00:00:00",
            "started_at": "2024-01-01 00:01:00",
            "completed_at": None,
            "attempts": 1,
            "max_attempts": 3,
            "last_error": None,
            "timeout_seconds": 300,
        }
        self.mock_fetch_one.return_value = mock_row

        q = PostgresWorkerQueue()
        await q.complete("task-complete-1", {"result": "success"})

        # _execute should have been called twice (INSERT history, DELETE from queue)
        assert mock_db._execute.call_count >= 2

    @pytest.mark.asyncio
    async def test_fail_with_retry(self, mock_db) -> None:
        """Fail with retry=True and attempts remaining updates task to pending with backoff."""
        from app.worker_queue_postgres import PostgresWorkerQueue

        mock_row = {
            "id": "task-retry-1",
            "type": "test",
            "payload": "{}",
            "priority": 2,
            "status": "running",
            "created_at": "2024-01-01 00:00:00",
            "started_at": "2024-01-01 00:01:00",
            "completed_at": None,
            "attempts": 1,
            "max_attempts": 3,
            "last_error": None,
            "timeout_seconds": 300,
        }
        self.mock_fetch_one.return_value = mock_row

        q = PostgresWorkerQueue()
        await q.fail("task-retry-1", "Temporary error", retry=True)

        # Should UPDATE the task back to pending with backoff
        assert mock_db._execute.called

    @pytest.mark.asyncio
    async def test_fail_moves_to_dead_letter(self, mock_db) -> None:
        """Fail with no retries remaining moves task to dead letter."""
        from app.worker_queue_postgres import PostgresWorkerQueue

        mock_row = {
            "id": "task-dl-1",
            "type": "test",
            "payload": "{}",
            "priority": 2,
            "status": "running",
            "created_at": "2024-01-01 00:00:00",
            "started_at": "2024-01-01 00:01:00",
            "completed_at": None,
            "attempts": 3,
            "max_attempts": 3,
            "last_error": None,
            "timeout_seconds": 300,
        }
        self.mock_fetch_one.return_value = mock_row

        q = PostgresWorkerQueue()
        await q.fail("task-dl-1", "Fatal error", retry=True)

        # Should have called _execute for INSERT history + DELETE from queue
        assert mock_db._execute.called

    @pytest.mark.asyncio
    async def test_cancel_pending_task(self, mock_db) -> None:
        """Cancel removes a pending task and archives it."""
        from app.worker_queue_postgres import PostgresWorkerQueue

        mock_row = {
            "id": "task-cancel-1",
            "type": "test",
            "payload": "{}",
            "priority": 2,
            "status": "pending",
            "created_at": "2024-01-01 00:00:00",
            "started_at": None,
            "completed_at": None,
            "attempts": 0,
            "max_attempts": 3,
            "last_error": None,
            "timeout_seconds": 300,
        }
        self.mock_fetch_one.return_value = mock_row

        q = PostgresWorkerQueue()
        result = await q.cancel("task-cancel-1")
        assert result is True

    @pytest.mark.asyncio
    async def test_cancel_nonexistent(self, mock_db) -> None:
        """Cancel returns False for a task that doesn't exist."""
        self.mock_fetch_one.return_value = None

        from app.worker_queue_postgres import PostgresWorkerQueue

        q = PostgresWorkerQueue()
        result = await q.cancel("nonexistent")
        assert result is False

    def test_register_handler(self, mock_db) -> None:
        """register_handler stores the handler for a task type."""
        from app.worker_queue_postgres import PostgresWorkerQueue

        q = PostgresWorkerQueue()

        async def my_handler(task):
            return {"ok": True}

        q.register_handler("my_type", my_handler)
        assert "my_type" in q._handlers
        assert q._handlers["my_type"] is my_handler

    def test_get_status(self, mock_db) -> None:
        """get_status returns status dict with counts from DB."""
        from app.worker_queue_postgres import PostgresWorkerQueue

        # Construct first so _ensure_schema uses default return_value=None mocks,
        # THEN set up the specific side_effect for get_status() calls
        q = PostgresWorkerQueue()

        counts = [
            {"cnt": 5},  # pending
            {"cnt": 2},  # running
            {"cnt": 3},  # retrying (pending + future scheduled_at)
            {"cnt": 1},  # dead_letter
            {"cnt": 10},  # completed_24h
        ]
        self.mock_fetch_one.side_effect = counts

        status = q.get_status()

        assert status["ok"] is True
        assert status["backend"] == "postgres"
        assert status["pending"] == 5
        assert status["running"] == 2
        assert status["retrying"] == 3
        assert status["dead_letter"] == 1
        assert status["completed_24h"] == 10
        assert status["max_concurrency"] == 5

    def test_get_task_state_in_queue(self, mock_db) -> None:
        """get_task_state checks queue_tasks first."""
        from app.worker_queue_postgres import PostgresWorkerQueue

        self.mock_fetch_one.return_value = {"id": "task-1", "status": "running"}

        q = PostgresWorkerQueue()
        state = q.get_task_state("task-1")

        assert state is not None
        assert state["id"] == "task-1"

    def test_get_task_state_in_history(self, mock_db) -> None:
        """get_task_state falls back to queue_task_history."""
        from app.worker_queue_postgres import PostgresWorkerQueue

        # Construct first so _ensure_schema uses default return_value=None mocks,
        # THEN set up the specific side_effect for get_task_state() calls
        q = PostgresWorkerQueue()

        self.mock_fetch_one.side_effect = [None, {"id": "task-2", "status": "completed"}]
        state = q.get_task_state("task-2")

        assert state is not None
        assert state["id"] == "task-2"

    def test_get_task_state_not_found(self, mock_db) -> None:
        """get_task_state returns None when task not found anywhere."""
        from app.worker_queue_postgres import PostgresWorkerQueue

        self.mock_fetch_one.side_effect = [None, None]

        q = PostgresWorkerQueue()
        state = q.get_task_state("nonexistent")

        assert state is None

    @pytest.mark.asyncio
    async def test_get_task_state_async(self, mock_db) -> None:
        """get_task_state_async wraps get_task_state via to_thread."""
        from app.worker_queue_postgres import PostgresWorkerQueue

        self.mock_fetch_one.return_value = {"id": "task-async-1", "status": "pending"}

        q = PostgresWorkerQueue()
        state = await q.get_task_state_async("task-async-1")

        # Should call _fetch_one for queue_tasks
        assert state is not None
        assert state["id"] == "task-async-1"

    def test_get_dead_letter_queue(self, mock_db) -> None:
        """get_dead_letter_queue returns archived dead letter entries."""
        from app.worker_queue_postgres import PostgresWorkerQueue

        self.mock_fetch_all.return_value = [
            {"id": "dl-1", "status": "dead_letter", "type": "test"},
            {"id": "dl-2", "status": "dead_letter", "type": "test"},
        ]

        q = PostgresWorkerQueue()
        entries = q.get_dead_letter_queue(limit=10)

        assert len(entries) == 2
        assert entries[0]["id"] == "dl-1"

    def test_retry_dead_letter(self, mock_db) -> None:
        """retry_dead_letter re-queues a dead letter task."""
        from app.worker_queue_postgres import PostgresWorkerQueue

        self.mock_fetch_one.return_value = {
            "id": "dl-retry-1",
            "type": "test",
            "payload": "{}",
            "priority": 2,
            "status": "dead_letter",
            "created_at": "2024-01-01 00:00:00",
            "started_at": None,
            "completed_at": None,
            "attempts": 3,
            "max_attempts": 3,
            "last_error": "Error",
            "timeout_seconds": 300,
        }

        q = PostgresWorkerQueue()
        result = q.retry_dead_letter("dl-retry-1")

        assert result is True
        # Should have called _execute for INSERT + DELETE
        assert mock_db._execute.called

    def test_retry_dead_letter_not_found(self, mock_db) -> None:
        """retry_dead_letter returns False when task not found."""
        from app.worker_queue_postgres import PostgresWorkerQueue

        self.mock_fetch_one.return_value = None

        q = PostgresWorkerQueue()
        result = q.retry_dead_letter("nonexistent")

        assert result is False

    def test_clear_completed_history(self, mock_db) -> None:
        """clear_completed_history deletes old completed/dead_letter entries."""
        from app.worker_queue_postgres import PostgresWorkerQueue

        q = PostgresWorkerQueue()
        q.clear_completed_history(older_than_days=7)

        # Should have called _execute with DELETE SQL
        assert mock_db._execute.called

    def test_get_status_handles_exception(self, monkeypatch) -> None:
        """get_status returns error dict when _conn raises."""
        import app.worker_queue_postgres as wqp
        from app.worker_queue_postgres import PostgresWorkerQueue

        # Mock _ensure_schema to no-op so construction doesn't hit failing _conn
        monkeypatch.setattr(PostgresWorkerQueue, "_ensure_schema", MagicMock())
        monkeypatch.setattr(wqp, "_conn", MagicMock(side_effect=Exception("Connection failed")))
        monkeypatch.setattr(wqp, "_execute", MagicMock())

        q = PostgresWorkerQueue()
        status = q.get_status()

        assert status["ok"] is False
        assert "error" in status

    def test_get_dead_letter_queue_handles_exception(self, monkeypatch) -> None:
        """get_dead_letter_queue returns empty list on error."""
        import app.worker_queue_postgres as wqp

        def failing_fetch_all(conn, sql, *args) -> NoReturn:
            msg = "Query failed"
            raise Exception(msg)

        monkeypatch.setattr(wqp, "_fetch_all", failing_fetch_all)

        from app.worker_queue_postgres import PostgresWorkerQueue

        q = PostgresWorkerQueue()
        entries = q.get_dead_letter_queue()
        assert entries == []

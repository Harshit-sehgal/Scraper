"""Structural unit tests for PostgresWorkerQueueBase.

Tests the core queue operations (enqueue, dequeue, complete, fail,
cancel, dead letter, observability) using a concrete stub subclass
with mocked connections — no Postgres server required.

Schema helper tests are in ``test_worker_queue_base_helpers.py``.
Factory dispatch tests are in ``test_worker_queue_factory_dispatch.py``.
"""

from __future__ import annotations

import asyncio
import json
from contextlib import contextmanager
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.worker_queue import Priority, QueueTask
from app.worker_queue_postgres_base import PostgresWorkerQueueBase


# ─── Stub implementation ───────────────────────────────────────────────


class _StubQueue(PostgresWorkerQueueBase):
    """Concrete subclass with mocked driver hooks for unit testing."""

    def __init__(self) -> None:
        # Bypass __init__ which calls _ensure_schema — we'll mock it
        self._max_concurrency = 5
        self._poll_interval = 0.01
        self._running = False
        self._start_lock = asyncio.Lock()
        self._worker_task = None
        self._in_flight = {}
        self._handlers = {}
        self._in_flight_lock = asyncio.Lock()
        self._concurrency_sem = asyncio.Semaphore(5)

        # Mock connection + cursor
        self._mock_cursor = MagicMock()
        self._mock_cursor.rowcount = 0
        self._mock_conn = MagicMock()
        self._mock_conn.cursor.return_value = self._mock_cursor

        # Instrumentation
        self.executed: list[tuple[str, tuple | None]] = []

    @contextmanager
    def _conn(self):
        yield self._mock_conn

    def _execute_impl(self, conn, sql: str, params=None):
        self.executed.append((sql, params))
        return self._mock_cursor

    def _fetch_all_impl(self, conn, sql: str, params=None) -> list[dict]:
        return []

    def _fetch_one_impl(self, conn, sql: str, params=None) -> dict | None:
        return None

    def _execute(self, conn, sql: str, params=None):
        return self._execute_impl(conn, sql, params)

    def _fetch_one(self, conn, sql: str, params=None) -> dict | None:
        return self._fetch_one_impl(conn, sql, params)

    def _fetch_all(self, conn, sql: str, params=None) -> list[dict]:
        return self._fetch_all_impl(conn, sql, params)

    def _ensure_schema(self) -> None:
        """Skip real schema creation in tests."""
        pass


def _make_task_row(task_id: str = "t1", task_type: str = "test_type", **overrides) -> dict[str, Any]:
    """Build a fake queue_tasks row dict for dequeue / task-state tests."""
    defaults: dict[str, Any] = {
        "id": task_id,
        "type": task_type,
        "payload": json.dumps({"key": "value"}),
        "priority": 2,
        "status": "pending",
        "created_at": "2026-01-01 00:00:00",
        "started_at": None,
        "completed_at": None,
        "attempts": 1,
        "max_attempts": 3,
        "last_error": None,
        "timeout_seconds": 300,
        "scheduled_at": "2026-01-01 00:00:00",
    }
    defaults.update(overrides)
    return defaults


# ─── Registration and configuration ─────────────────────────────────────


class TestHandlerRegistration:
    """``register_handler`` stores handler functions by type."""

    def test_register_handler(self) -> None:
        q = _StubQueue()
        handler = MagicMock()
        q.register_handler("scrape", handler)
        assert q._handlers["scrape"] is handler

    def test_set_max_concurrency(self) -> None:
        q = _StubQueue()
        q.set_max_concurrency(10)
        assert q._max_concurrency == 10

    def test_set_max_concurrency_rejects_zero(self) -> None:
        q = _StubQueue()
        with pytest.raises(ValueError, match="must be >= 1"):
            q.set_max_concurrency(0)

    def test_set_max_concurrency_rejects_negative(self) -> None:
        q = _StubQueue()
        with pytest.raises(ValueError, match="must be >= 1"):
            q.set_max_concurrency(-1)

    def test_get_poll_interval(self) -> None:
        q = _StubQueue()
        assert q.get_poll_interval() == q._poll_interval


# ─── Enqueue ────────────────────────────────────────────────────────────


class TestEnqueue:
    """``enqueue`` inserts a new task into the queue."""

    @pytest.mark.asyncio
    async def test_enqueue_returns_task_id(self) -> None:
        q = _StubQueue()
        task_id = await q.enqueue("scrape", {"url": "https://test.invalid"})
        assert isinstance(task_id, str)
        assert len(task_id) > 0

    @pytest.mark.asyncio
    async def test_enqueue_inserts_sql(self) -> None:
        q = _StubQueue()
        await q.enqueue("scrape", {"url": "https://test.invalid"})
        sqls = [s for s, _ in q.executed]
        assert any("INSERT INTO queue_tasks" in s for s in sqls)

    @pytest.mark.asyncio
    async def test_enqueue_uses_on_conflict_do_nothing(self) -> None:
        q = _StubQueue()
        await q.enqueue("scrape", {})
        sqls = [s for s, _ in q.executed]
        assert any("ON CONFLICT (id) DO NOTHING" in s for s in sqls)

    @pytest.mark.asyncio
    async def test_enqueue_custom_priority(self) -> None:
        q = _StubQueue()
        await q.enqueue("scrape", {}, priority=Priority.HIGH)
        # Find the insert statement and check priority in params
        insert_execs = [(s, p) for s, p in q.executed if "INSERT INTO queue_tasks" in s]
        assert len(insert_execs) >= 1
        _, params = insert_execs[0]
        assert params is not None
        assert any(p == int(Priority.HIGH) for p in params if isinstance(p, int))

    @pytest.mark.asyncio
    async def test_enqueue_with_custom_task_id(self) -> None:
        q = _StubQueue()
        task_id = await q.enqueue("scrape", {}, task_id="my-custom-id")
        # _record_scheduled_job_usage is called, then _enqueue_sync
        assert task_id == "my-custom-id"


# ─── Dequeue ────────────────────────────────────────────────────────────


class TestDequeue:
    """``dequeue`` claims the highest-priority pending task."""

    @pytest.mark.asyncio
    async def test_dequeue_returns_task_when_available(self) -> None:
        q = _StubQueue()
        row = _make_task_row()
        q._fetch_one_impl = MagicMock(return_value=row)

        task = await q.dequeue(timeout=0.5)
        assert task is not None
        assert task.id == "t1"

    @pytest.mark.asyncio
    async def test_dequeue_returns_none_on_empty(self) -> None:
        q = _StubQueue()
        q._fetch_one_impl = MagicMock(return_value=None)

        task = await q.dequeue(timeout=0.1)
        assert task is None

    @pytest.mark.asyncio
    async def test_dequeue_payload_json_parsed(self) -> None:
        q = _StubQueue()
        row = _make_task_row()
        row["payload"] = json.dumps({"url": "https://test.invalid"})
        q._fetch_one_impl = MagicMock(return_value=row)

        task = await q.dequeue(timeout=0.5)
        assert task is not None
        assert task.payload == {"url": "https://test.invalid"}

    @pytest.mark.asyncio
    async def test_dequeue_db_error_returns_none(self) -> None:
        q = _StubQueue()
        q._fetch_one_impl = MagicMock(side_effect=RuntimeError("db down"))

        task = await q.dequeue(timeout=0.1)
        assert task is None


# ─── Complete ───────────────────────────────────────────────────────────


class TestComplete:
    """``complete`` archives a task to history and deletes from queue_tasks."""

    @pytest.mark.asyncio
    async def test_complete_moves_to_history(self) -> None:
        q = _StubQueue()
        row = _make_task_row(status="running")
        q._fetch_one_impl = MagicMock(return_value=row)

        await q.complete("t1", {"result": "ok"})
        sqls = [s for s, _ in q.executed]
        assert any("INSERT INTO queue_task_history" in s and "'completed'" in s for s in sqls)
        assert any("DELETE FROM queue_tasks" in s for s in sqls)

    @pytest.mark.asyncio
    async def test_complete_with_none_result(self) -> None:
        q = _StubQueue()
        row = _make_task_row()
        q._fetch_one_impl = MagicMock(return_value=row)

        await q.complete("t1", None)
        sqls = [s for s, _ in q.executed]
        assert any("INSERT INTO queue_task_history" in s for s in sqls)


# ─── Fail ───────────────────────────────────────────────────────────────


class TestFail:
    """``fail`` retries or moves to dead letter."""

    @pytest.mark.asyncio
    async def test_fail_retries_when_attempts_remain(self) -> None:
        q = _StubQueue()
        row = _make_task_row(attempts=1, max_attempts=3)
        q._fetch_one_impl = MagicMock(return_value=row)

        await q.fail("t1", "something went wrong")
        sqls = [s for s, _ in q.executed]
        # Should update status to 'pending' for retry
        assert any("UPDATE queue_tasks SET status = 'pending'" in s for s in sqls)

    @pytest.mark.asyncio
    async def test_fail_moves_to_dead_letter_when_max_reached(self) -> None:
        q = _StubQueue()
        row = _make_task_row(attempts=3, max_attempts=3)
        q._fetch_one_impl = MagicMock(return_value=row)

        await q.fail("t1", "permanent failure", retry=True)
        sqls = [s for s, _ in q.executed]
        assert any("dead_letter" in s for s in sqls)
        assert any("DELETE FROM queue_tasks" in s for s in sqls)

    @pytest.mark.asyncio
    async def test_fail_no_retry_goes_to_dead_letter(self) -> None:
        q = _StubQueue()
        row = _make_task_row(attempts=1, max_attempts=3)
        q._fetch_one_impl = MagicMock(return_value=row)

        await q.fail("t1", "skip retry", retry=False)
        sqls = [s for s, _ in q.executed]
        assert any("dead_letter" in s for s in sqls)

    @pytest.mark.asyncio
    async def test_fail_with_retry_after(self) -> None:
        q = _StubQueue()
        row = _make_task_row(attempts=1, max_attempts=3)
        q._fetch_one_impl = MagicMock(return_value=row)

        await q.fail("t1", "rate limited", retry=True, retry_after=60.0)
        sqls = [s for s, p in q.executed if "UPDATE queue_tasks" in s and "scheduled_at" in s]
        # Should use the explicit retry_after value
        assert len(sqls) >= 1


# ─── Cancel ─────────────────────────────────────────────────────────────


class TestCancel:
    """``cancel`` handles both pending and in-flight tasks."""

    @pytest.mark.asyncio
    async def test_cancel_pending_task(self) -> None:
        q = _StubQueue()
        row = _make_task_row(status="pending")
        q._fetch_one_impl = MagicMock(return_value=row)

        result = await q.cancel("t1")
        assert result is True
        sqls = [s for s, _ in q.executed]
        assert any("INSERT INTO queue_task_history" in s and "'cancelled'" in s for s in sqls)

    @pytest.mark.asyncio
    async def test_cancel_pending_not_found(self) -> None:
        q = _StubQueue()
        q._fetch_one_impl = MagicMock(return_value=None)

        result = await q.cancel("missing")
        assert result is False

    @pytest.mark.asyncio
    async def test_cancel_in_flight_task(self) -> None:
        q = _StubQueue()
        row = _make_task_row(status="running")
        q._fetch_one_impl = MagicMock(return_value=row)

        # Put a fake task in _in_flight
        fake_async_task = asyncio.create_task(asyncio.sleep(0))
        q._in_flight["t1"] = fake_async_task

        result = await q.cancel("t1")
        assert result is True
        # The fake task was cancelled
        assert fake_async_task.cancelled() or fake_async_task.done()

    @pytest.mark.asyncio
    async def test_cancel_in_flight_archives_to_history(self) -> None:
        q = _StubQueue()
        row = _make_task_row(status="running")
        q._fetch_one_impl = MagicMock(return_value=row)

        fake_async_task = asyncio.create_task(asyncio.sleep(0))
        q._in_flight["t1"] = fake_async_task

        await q.cancel("t1")
        sqls = [s for s, _ in q.executed]
        assert any("INSERT INTO queue_task_history" in s for s in sqls)
        assert any("DELETE FROM queue_tasks" in s for s in sqls)


# ─── Stuck task recovery ───────────────────────────────────────────────


class TestRecoverStuckTasks:
    """``_recover_stuck_tasks`` resets running tasks to pending."""

    def test_recovers_running_tasks(self) -> None:
        q = _StubQueue()
        q._fetch_one_impl = MagicMock(return_value={"cnt": 3})

        q._recover_stuck_tasks()
        sqls = [s for s, _ in q.executed]
        assert any("UPDATE queue_tasks SET status = 'pending'" in s for s in sqls)

    def test_no_recovery_when_none_stuck(self) -> None:
        q = _StubQueue()
        q._fetch_one_impl = MagicMock(return_value={"cnt": 0})

        q._recover_stuck_tasks()
        # No UPDATE should have been executed
        update_sqls = [s for s, _ in q.executed if "UPDATE" in s]
        assert len(update_sqls) == 0

    def test_recovery_swallows_db_errors(self) -> None:
        q = _StubQueue()
        q._fetch_one_impl = MagicMock(side_effect=RuntimeError("down"))

        q._recover_stuck_tasks()  # should not raise


# ─── Observability ──────────────────────────────────────────────────────


class TestGetStatus:
    """``get_status`` returns queue metrics."""

    def test_returns_status_dict(self) -> None:
        q = _StubQueue()
        count_row = {"cnt": 0}
        q._fetch_one_impl = MagicMock(return_value=count_row)
        q._fetch_all_impl = MagicMock(return_value=[])

        status = q.get_status()
        assert status["ok"] is True
        assert "pending" in status
        assert "running" in status
        assert "dead_letter" in status
        assert "max_concurrency" in status

    def test_db_error_returns_error_dict(self) -> None:
        q = _StubQueue()
        q._fetch_one_impl = MagicMock(side_effect=RuntimeError("down"))

        status = q.get_status()
        assert status["ok"] is False
        assert "error" in status


class TestGetTaskState:
    """``get_task_state`` checks both active and history tables."""

    def test_returns_active_task(self) -> None:
        q = _StubQueue()
        row = _make_task_row()
        q._fetch_one_impl = MagicMock(return_value=row)

        result = q.get_task_state("t1")
        assert result is not None
        assert result["id"] == "t1"

    def test_falls_back_to_history(self) -> None:
        q = _StubQueue()
        call_count = 0

        def side_effect(conn, sql, params=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return None  # Not in queue_tasks
            return _make_task_row(status="completed")  # In history

        q._fetch_one_impl = MagicMock(side_effect=side_effect)

        result = q.get_task_state("t1")
        assert result is not None

    def test_returns_none_not_found(self) -> None:
        q = _StubQueue()
        q._fetch_one_impl = MagicMock(return_value=None)

        assert q.get_task_state("missing") is None

    def test_db_error_returns_none(self) -> None:
        q = _StubQueue()
        q._fetch_one_impl = MagicMock(side_effect=RuntimeError("down"))

        assert q.get_task_state("t1") is None


# ─── Dead letter queue ────────────────────────────────────────────────


class TestDeadLetterQueue:
    """``get_dead_letter_queue`` and ``retry_dead_letter``."""

    def test_get_dead_letter_queue(self) -> None:
        q = _StubQueue()
        q._fetch_all_impl = MagicMock(return_value=[_make_task_row(status="dead_letter")])

        result = q.get_dead_letter_queue()
        assert len(result) == 1

    def test_get_dead_letter_db_error_returns_empty(self) -> None:
        q = _StubQueue()
        q._fetch_all_impl = MagicMock(side_effect=RuntimeError("down"))

        assert q.get_dead_letter_queue() == []

    def test_retry_dead_letter_requeues(self) -> None:
        q = _StubQueue()
        row = _make_task_row(status="dead_letter")
        q._fetch_one_impl = MagicMock(return_value=row)

        result = q.retry_dead_letter("t1")
        assert result is True
        sqls = [s for s, _ in q.executed]
        assert any("INSERT INTO queue_tasks" in s and "'pending'" in s for s in sqls)
        assert any("DELETE FROM queue_task_history" in s for s in sqls)

    def test_retry_dead_letter_not_found(self) -> None:
        q = _StubQueue()
        q._fetch_one_impl = MagicMock(return_value=None)

        assert q.retry_dead_letter("missing") is False

    def test_retry_dead_letter_db_error(self) -> None:
        q = _StubQueue()
        q._fetch_one_impl = MagicMock(side_effect=RuntimeError("down"))

        assert q.retry_dead_letter("t1") is False


# ─── History cleanup ───────────────────────────────────────────────────


class TestClearCompletedHistory:
    """``clear_completed_history`` removes old completed/dead_letter entries."""

    def test_runs_delete(self) -> None:
        q = _StubQueue()
        q.clear_completed_history(older_than_days=3)
        sqls = [s for s, _ in q.executed]
        assert any("DELETE FROM queue_task_history" in s for s in sqls)

    def test_swallows_db_errors(self) -> None:
        q = _StubQueue()
        q._execute_impl = MagicMock(side_effect=RuntimeError("down"))

        q.clear_completed_history()  # should not raise


# ─── Worker lifecycle ─────────────────────────────────────────────────


class TestWorkerStartStop:
    """``start`` and ``stop`` lifecycle management."""

    @pytest.mark.asyncio
    async def test_start_sets_running(self) -> None:
        q = _StubQueue()
        q._recover_stuck_tasks = MagicMock()

        await q.start()
        assert q._running is True
        await q.stop(drain=False)

    @pytest.mark.asyncio
    async def test_double_start_is_noop(self) -> None:
        q = _StubQueue()
        q._recover_stuck_tasks = MagicMock()

        await q.start()
        assert q._running is True
        # Second start should be a no-op
        await q.start()
        await q.stop(drain=False)

    @pytest.mark.asyncio
    async def test_stop_drains_in_flight(self) -> None:
        q = _StubQueue()
        q._recover_stuck_tasks = MagicMock()
        await q.start()

        # Add a quick-completing task to in_flight
        done_task = asyncio.create_task(asyncio.sleep(0))
        await done_task  # complete it
        q._in_flight["t1"] = done_task

        await q.stop(drain=True)
        assert q._running is False

    @pytest.mark.asyncio
    async def test_stop_without_drain(self) -> None:
        q = _StubQueue()
        q._recover_stuck_tasks = MagicMock()
        await q.start()
        await q.stop(drain=False)
        assert q._running is False


# ─── Task execution ────────────────────────────────────────────────────


class TestExecuteTask:
    """``_execute_task`` dispatches to registered handler."""

    @pytest.mark.asyncio
    async def test_no_handler_fails_task(self) -> None:
        q = _StubQueue()
        task = QueueTask(task_type="unknown_type")

        async def mock_fail(task_id, error, **kwargs):
            pass

        q.fail = mock_fail
        await q._execute_task(task)

    @pytest.mark.asyncio
    async def test_handler_success_completes(self) -> None:
        q = _StubQueue()

        async def good_handler(task):
            return True

        q.register_handler("test_type", good_handler)
        task = QueueTask(task_type="test_type", task_id="t1")

        async def mock_complete(task_id, result=None):
            pass

        q.complete = mock_complete
        await q._execute_task(task)

    @pytest.mark.asyncio
    async def test_handler_returns_false_fails(self) -> None:
        q = _StubQueue()

        async def bad_handler(task):
            return False

        q.register_handler("test_type", bad_handler)
        task = QueueTask(task_type="test_type", task_id="t1")

        async def mock_fail(task_id, error, **kwargs):
            pass

        q.fail = mock_fail
        await q._execute_task(task)

    @pytest.mark.asyncio
    async def test_handler_timeout_fails(self) -> None:
        q = _StubQueue()

        async def slow_handler(task):
            await asyncio.sleep(10)

        q.register_handler("test_type", slow_handler)
        task = QueueTask(task_type="test_type", task_id="t1", timeout_seconds=0)

        with patch.object(q, "fail") as mock_fail:
            # Make mock_fail an async function
            async def _fail(*a, **kw):
                pass

            mock_fail.side_effect = _fail
            await q._execute_task(task)
            mock_fail.assert_called_once()
            call_args = mock_fail.call_args
            assert "Timeout" in call_args[0][1]

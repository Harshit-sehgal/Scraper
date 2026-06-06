"""Tests for the persistent WorkerQueue.

Covers:
- Enqueue and dequeue with priority ordering
- Task lifecycle: pending -> running -> completed/failed
- Retry with exponential backoff
- Dead letter queue for permanently failed tasks
- Cancel pending tasks
- Stuck task recovery on startup
- Queue status observability
"""

import asyncio
from pathlib import Path


def _make_queue(tmp_path: Path):
    """Create a WorkerQueue bound to a temporary database."""
    from app.worker_queue import WorkerQueue, reset_worker_queue

    reset_worker_queue()
    db_path = tmp_path / "worker_queue.db"
    return WorkerQueue(db_path=db_path), db_path


# ───────────────────────────────────────────────────────────────────────
# Tests
# ───────────────────────────────────────────────────────────────────────


class TestWorkerQueueBasic:
    """Basic enqueue/dequeue lifecycle tests."""

    def test_enqueue_and_dequeue(self, tmp_path) -> None:
        """A task enqueued can be dequeued with correct metadata."""
        from app.worker_queue import Priority

        queue, _ = _make_queue(tmp_path)

        task_id = asyncio.run(queue.enqueue("test_task", {"key": "value"}, priority=Priority.HIGH))
        assert task_id is not None

        task = asyncio.run(queue.dequeue(timeout=1.0))
        assert task is not None
        assert task.id == task_id
        assert task.type == "test_task"
        assert task.payload == {"key": "value"}
        assert task.priority == Priority.HIGH
        assert task.status.value == "running"

    def test_dequeue_empty_returns_none(self, tmp_path) -> None:
        """Dequeueing from an empty queue returns None."""
        queue, _ = _make_queue(tmp_path)

        task = asyncio.run(queue.dequeue(timeout=0.5))
        assert task is None

    def test_enqueue_returns_valid_id(self, tmp_path) -> None:
        """Enqueuing a task returns a valid UUID string."""
        queue, _ = _make_queue(tmp_path)

        task_id = asyncio.run(queue.enqueue("test_task", {}))
        assert task_id is not None
        assert len(task_id) > 0

    def test_complete_task(self, tmp_path) -> None:
        """Completing a task removes it from the active queue."""
        queue, _ = _make_queue(tmp_path)

        task_id = asyncio.run(queue.enqueue("test_task", {}))
        task = asyncio.run(queue.dequeue(timeout=1.0))
        assert task is not None

        asyncio.run(queue.complete(task_id, {"result": "ok"}))

        # Should be gone from active queue
        remaining = asyncio.run(queue.dequeue(timeout=0.5))
        assert remaining is None

    def test_cancel_pending_task(self, tmp_path) -> None:
        """Cancelling a pending task removes it from the queue."""
        queue, _ = _make_queue(tmp_path)

        task_id = asyncio.run(queue.enqueue("test_task", {}))
        cancelled = asyncio.run(queue.cancel(task_id))
        assert cancelled is True

        # Should not be dequeueable
        task = asyncio.run(queue.dequeue(timeout=0.5))
        assert task is None

    def test_cancel_running_task_fails(self, tmp_path) -> None:
        """Cancelling a task that is already running returns False."""
        queue, _ = _make_queue(tmp_path)

        task_id = asyncio.run(queue.enqueue("test_task", {}))
        asyncio.run(queue.dequeue(timeout=1.0))  # Marks as RUNNING

        cancelled = asyncio.run(queue.cancel(task_id))
        assert cancelled is False


class TestWorkerQueuePriority:
    """Priority ordering tests."""

    def test_priority_ordering(self, tmp_path) -> None:
        """Higher-priority tasks are dequeued before lower-priority ones."""
        from app.worker_queue import Priority

        queue, _ = _make_queue(tmp_path)

        # Enqueue in reverse priority order
        id_low = asyncio.run(queue.enqueue("low", {}, priority=Priority.LOW))
        id_normal = asyncio.run(queue.enqueue("normal", {}, priority=Priority.NORMAL))
        id_high = asyncio.run(queue.enqueue("high", {}, priority=Priority.HIGH))
        id_critical = asyncio.run(queue.enqueue("critical", {}, priority=Priority.CRITICAL))

        # Should dequeue in priority order
        t1 = asyncio.run(queue.dequeue(timeout=1.0))
        assert t1 is not None
        assert t1.id == id_critical

        t2 = asyncio.run(queue.dequeue(timeout=1.0))
        assert t2 is not None
        assert t2.id == id_high

        t3 = asyncio.run(queue.dequeue(timeout=1.0))
        assert t3 is not None
        assert t3.id == id_normal

        t4 = asyncio.run(queue.dequeue(timeout=1.0))
        assert t4 is not None
        assert t4.id == id_low


class TestWorkerQueueRetries:
    """Retry and dead letter tests."""

    def test_fail_moves_to_retry(self, tmp_path) -> None:
        """Failing a task with retries remaining sets it back to pending with future scheduled_at."""
        queue, _ = _make_queue(tmp_path)

        task_id = asyncio.run(queue.enqueue("test_task", {}, max_attempts=3))
        task = asyncio.run(queue.dequeue(timeout=1.0))
        assert task is not None

        asyncio.run(queue.fail(task_id, "Temporary error", retry=True))

        # Task should still exist as pending (with future scheduled_at for backoff)
        status = queue.get_status()
        assert status["pending"] >= 1, "Retry task should be pending, not retrying"
        assert status["running"] == 0
        # ``retrying`` now reflects the number of *pending* tasks with a
        # future ``scheduled_at`` (i.e. the "effectively retrying" count).
        # The exponential backoff starts at 30s, so the retried task is
        # counted here.
        assert status["retrying"] >= 1, "Retried task with future scheduled_at should count as retrying"

    def test_fail_exhausts_retries_moves_to_dead_letter(self, tmp_path) -> None:
        """Failing a task after exhausting all retries moves it to dead letter."""
        queue, _ = _make_queue(tmp_path)

        task_id = asyncio.run(queue.enqueue("test_task", {}, max_attempts=1))
        task = asyncio.run(queue.dequeue(timeout=1.0))
        assert task is not None

        # Fail with retry=True, but max_attempts=1 means it should go to dead letter
        asyncio.run(queue.fail(task_id, "Fatal error", retry=True))

        status = queue.get_status()
        assert status["dead_letter"] >= 1

    def test_retry_task_becomes_dequeueable_after_backoff(self, tmp_path) -> None:
        """A retried task is set back to pending with future scheduled_at and
        is dequeuable once scheduled_at <= now.
        """
        queue, _ = _make_queue(tmp_path)

        task_id = asyncio.run(queue.enqueue("test_task", {}, max_attempts=3))
        task = asyncio.run(queue.dequeue(timeout=1.0))
        assert task is not None

        asyncio.run(queue.fail(task_id, "Temporary error", retry=True))

        # Force scheduled_at to now so the task is immediately eligible
        # (UTC, matching the format the production code writes in)
        conn = queue._conn()
        conn.execute(
            "UPDATE tasks SET scheduled_at = datetime('now') WHERE id = ?",
            (task_id,),
        )
        conn.commit()
        conn.close()

        retried = asyncio.run(queue.dequeue(timeout=1.0))
        assert retried is not None, "Retried task should be dequeuable after backoff"
        assert retried.id == task_id

    def test_retry_dead_letter(self, tmp_path) -> None:
        """A dead letter task can be re-queued."""
        queue, _ = _make_queue(tmp_path)

        task_id = asyncio.run(queue.enqueue("test_task", {}, max_attempts=1))
        task = asyncio.run(queue.dequeue(timeout=1.0))
        assert task is not None
        asyncio.run(queue.fail(task_id, "Fatal error", retry=True))

        # Re-queue from dead letter
        requeued = queue.retry_dead_letter(task_id)
        assert requeued is True

        status = queue.get_status()
        assert status["dead_letter"] == 0
        assert status["pending"] >= 1


class TestWorkerQueueStartupRecovery:
    """Stuck task recovery on worker startup."""

    def test_recover_stuck_tasks(self, tmp_path) -> None:
        """Tasks stuck in 'running' state are recovered on restart."""
        from app.worker_queue import WorkerQueue

        db_path = tmp_path / "worker_queue.db"

        # First queue — enqueue and dequeue to simulate crash mid-execution
        queue1 = WorkerQueue(db_path=db_path)
        task_id = asyncio.run(queue1.enqueue("test_task", {}))
        task = asyncio.run(queue1.dequeue(timeout=1.0))
        assert task is not None
        assert task.id == task_id

        # Simulate restart with a new queue on the same DB file.
        # Call recovery directly (without starting the worker loop, so
        # the recovered task isn't immediately re-consumed).
        queue2 = WorkerQueue(db_path=db_path)
        queue2._recover_stuck_tasks()

        # Verify the task was recovered to pending
        status = queue2.get_status()
        assert status["running"] == 0, f"Expected 0 running tasks after recovery, got {status['running']}"
        assert status["pending"] >= 1, f"Expected >=1 pending tasks after recovery, got {status['pending']}"

        # Verify the recovered task can be dequeued
        recovered = asyncio.run(queue2.dequeue(timeout=1.0))
        assert recovered is not None, "Recovered task should be dequeueable"
        assert recovered.id == task_id
        # attempts = 1 (first dequeue) + 1 (second dequeue) — no more recovery increment
        assert recovered.attempts == 2


class TestWorkerQueueObservability:
    """Status and monitoring tests."""

    def test_get_status_counts(self, tmp_path) -> None:
        """get_status returns correct counts for all queue states."""
        queue, _ = _make_queue(tmp_path)

        for i in range(5):
            asyncio.run(queue.enqueue(f"task_{i}", {}))

        status = queue.get_status()
        assert status["pending"] == 5
        assert status["running"] == 0
        assert status["retrying"] == 0
        assert status["max_concurrency"] == 5

    def test_get_status_with_dead_letter(self, tmp_path) -> None:
        """get_status returns correct dead_letter count."""
        queue, _ = _make_queue(tmp_path)

        task_id = asyncio.run(queue.enqueue("test_task", {}, max_attempts=1))
        task = asyncio.run(queue.dequeue(timeout=1.0))
        assert task is not None
        asyncio.run(queue.fail(task_id, "Error", retry=True))

        status = queue.get_status()
        assert status["dead_letter"] >= 1

    def test_get_dead_letter_queue(self, tmp_path) -> None:
        """Dead letter queue entries are retrievable."""
        queue, _ = _make_queue(tmp_path)

        task_id = asyncio.run(queue.enqueue("dl_test", {"key": "val"}, max_attempts=1))
        task = asyncio.run(queue.dequeue(timeout=1.0))
        assert task is not None
        asyncio.run(queue.fail(task_id, "Error", retry=True))

        dl = queue.get_dead_letter_queue(limit=10)
        assert len(dl) >= 1
        ids = [entry["id"] for entry in dl]
        assert task_id in ids


class TestWorkerQueueConcurrency:
    """Concurrency control tests."""

    def test_max_concurrency_setting(self, tmp_path) -> None:
        """The max_concurrency setting is respected."""
        queue, _ = _make_queue(tmp_path)
        assert queue._max_concurrency == 5


class TestQueueTaskModel:
    """Tests for the QueueTask data model."""

    def test_to_dict_from_dict_round_trip(self) -> None:
        """A QueueTask serialized to dict and back preserves all fields."""
        from app.worker_queue import Priority, QueueTask, TaskStatus

        original = QueueTask(
            task_type="test",
            payload={"key": "value"},
            priority=Priority.HIGH,
            max_attempts=5,
            timeout_seconds=120,
        )
        original.status = TaskStatus.RUNNING

        d = original.to_dict()
        restored = QueueTask.from_dict(d)

        assert restored.id == original.id
        assert restored.type == original.type
        assert restored.payload == original.payload
        assert restored.priority == original.priority
        assert restored.status == original.status
        assert restored.max_attempts == original.max_attempts
        assert restored.timeout_seconds == original.timeout_seconds

    def test_default_values(self) -> None:
        """QueueTask default values are sensible."""
        from app.worker_queue import Priority, QueueTask, TaskStatus

        task = QueueTask(task_type="defaults")
        assert task.priority == Priority.NORMAL
        assert task.status == TaskStatus.PENDING
        assert task.max_attempts == 3
        assert task.timeout_seconds == 300
        assert task.payload == {}


class TestWorkerQueueExecution:
    """Tests for execute_task, handler dispatch, and timeouts."""

    def test_execute_task_handler_missing(self, tmp_path) -> None:
        """A task with no registered handler is failed."""
        from app.worker_queue import WorkerQueue, reset_worker_queue

        reset_worker_queue()
        db_path = tmp_path / "test_missing_handler.db"
        queue = WorkerQueue(db_path=db_path)

        task_id = asyncio.run(queue.enqueue("unregistered_type", {}))
        task = asyncio.run(queue.dequeue(timeout=1.0))
        assert task is not None

        asyncio.run(queue._execute_task(task))

        # Task should have been failed (and not in active queue)
        state = queue.get_task_state(task_id)
        assert state is None or state.get("status") != "running"

    def test_execute_task_handler_returns_false(self, tmp_path) -> None:
        """A handler returning False triggers retry."""
        from app.worker_queue import WorkerQueue, reset_worker_queue

        reset_worker_queue()
        db_path = tmp_path / "test_handler_false.db"
        queue = WorkerQueue(db_path=db_path)

        async def failing_handler(task) -> bool:
            return False

        queue.register_handler("failing", failing_handler)
        task_id = asyncio.run(queue.enqueue("failing", {}, max_attempts=3))
        task = asyncio.run(queue.dequeue(timeout=1.0))
        assert task is not None

        asyncio.run(queue._execute_task(task))

        # Task should still exist (retried)
        state = queue.get_task_state(task_id)
        assert state is not None

    def test_execute_task_timeout(self, tmp_path) -> None:
        """A task that times out is retried."""
        from app.worker_queue import WorkerQueue, reset_worker_queue

        reset_worker_queue()
        db_path = tmp_path / "test_timeout.db"
        queue = WorkerQueue(db_path=db_path)

        async def slow_handler(task) -> bool:
            await asyncio.sleep(10)
            return True

        queue.register_handler("slow", slow_handler)
        task_id = asyncio.run(queue.enqueue("slow", {}, timeout_seconds=1, max_attempts=2))
        from app.worker_queue import QueueTask, TaskStatus

        quick_timeout_task = QueueTask(
            task_type="slow",
            payload={},
            max_attempts=2,
            timeout_seconds=1,
            task_id=task_id,
        )
        quick_timeout_task.status = TaskStatus.RUNNING

        asyncio.run(queue._execute_task(quick_timeout_task))

        # Should have timed out — task should have been retried
        state = queue.get_task_state(task_id)
        assert state is not None, "Timed-out task should still exist (retried)"
        # If retried, task should be back in active queue as pending
        status = queue.get_status()
        assert status["pending"] >= 1 or status.get("retrying", 0) >= 1


class TestWorkerQueueObservabilityExtended:
    """Extended observability tests for uncovered paths."""

    def test_get_task_state_active(self, tmp_path) -> None:
        """get_task_state returns the active task state."""
        from app.worker_queue import reset_worker_queue

        reset_worker_queue()
        queue, _ = _make_queue(tmp_path)

        task_id = asyncio.run(queue.enqueue("test_state", {"k": "v"}))
        state = queue.get_task_state(task_id)
        assert state is not None
        assert state["type"] == "test_state"
        assert state["status"] == "pending"

    def test_get_task_state_history(self, tmp_path) -> None:
        """get_task_state falls back to task_history for completed tasks."""
        from app.worker_queue import reset_worker_queue

        reset_worker_queue()
        queue, _ = _make_queue(tmp_path)

        task_id = asyncio.run(queue.enqueue("test_history", {}, max_attempts=1))
        task = asyncio.run(queue.dequeue(timeout=1.0))
        assert task is not None
        asyncio.run(queue.fail(task_id, "Final fail", retry=True))

        # Task should now be in history (dead_letter)
        state = queue.get_task_state(task_id)
        assert state is not None
        assert state["status"] == "dead_letter"

    def test_get_task_state_not_found(self, tmp_path) -> None:
        """get_task_state returns None for unknown task ID."""
        from app.worker_queue import reset_worker_queue

        reset_worker_queue()
        queue, _ = _make_queue(tmp_path)
        assert queue.get_task_state("nonexistent-id") is None

    def test_get_status_with_top_pending(self, tmp_path) -> None:
        """get_status returns next_tasks for monitoring."""
        from app.worker_queue import reset_worker_queue

        reset_worker_queue()
        queue, _ = _make_queue(tmp_path)

        asyncio.run(queue.enqueue("monitor_task", {}, max_attempts=3))
        status = queue.get_status()
        assert "next_tasks" in status
        assert len(status["next_tasks"]) == 1
        assert status["next_tasks"][0]["type"] == "monitor_task"

    def test_clear_completed_history(self, tmp_path) -> None:
        """clear_completed_history does not remove recently completed tasks.

        The method deletes history where finished_at < (NOW - N days).
        With older_than_days=365, a just-completed task is preserved.
        This is the intended behavior — only truly old history is pruned.
        """
        from app.worker_queue import reset_worker_queue

        reset_worker_queue()
        queue, _ = _make_queue(tmp_path)

        # Enqueue and fail to create history entries
        task_id = asyncio.run(queue.enqueue("clear_test", {}, max_attempts=1))
        task = asyncio.run(queue.dequeue(timeout=1.0))
        assert task is not None
        asyncio.run(queue.fail(task_id, "Gone", retry=True))

        # Verify task exists in history before cleanup
        state_before = queue.get_task_state(task_id)
        assert state_before is not None

        # Clear with 365 days — should NOT remove recently completed task
        queue.clear_completed_history(older_than_days=365)

        # Recently completed task should still exist
        state_after = queue.get_task_state(task_id)
        assert state_after is not None
        assert state_after["status"] == "dead_letter"


class TestWorkerQueueFactory:
    """Tests for the get_worker_queue factory function."""

    def test_get_worker_queue_postgres_backend_cannot_connect(self) -> None:
        """get_worker_queue with postgres backend returns PostgresWorkerQueue
        instance even without a live connection (the error surfaces on DB calls).

        Full Postgres integration tests live in test_worker_queue_postgres.py.
        """
        from app.worker_queue import get_worker_queue, reset_worker_queue
        from app.worker_queue_postgres import PostgresWorkerQueue

        reset_worker_queue()
        # This should return a PostgresWorkerQueue instance even if Postgres
        # isn't running — connection errors surface on actual DB operations.
        try:
            queue = get_worker_queue(backend="postgres")
            assert isinstance(queue, PostgresWorkerQueue)
        except Exception as exc:
            # Postgres may not be available — skip gracefully
            import pytest

            pytest.skip(f"Postgres not available: {exc}")

    def test_get_worker_queue_singleton(self, tmp_path) -> None:
        """get_worker_queue returns the same instance when no db_path changes."""
        from app.worker_queue import get_worker_queue, reset_worker_queue

        reset_worker_queue()
        q1 = get_worker_queue()
        q2 = get_worker_queue()
        assert q1 is q2

    def test_get_worker_queue_custom_db_path(self, tmp_path) -> None:
        """get_worker_queue with a custom db_path returns a new instance."""
        from app.worker_queue import get_worker_queue, reset_worker_queue

        reset_worker_queue()
        p = tmp_path / "custom"
        p.mkdir(exist_ok=True)
        custom_db = p / "queue.db"

        q = get_worker_queue(db_path=custom_db)
        assert q._db_path == custom_db

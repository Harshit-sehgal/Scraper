"""Tests for app.lifespan — FastAPI lifecycle utilities."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from app.lifespan import persist_single_wrapper, schedule_background_task


class TestScheduleBackgroundTask:
    @pytest.mark.asyncio
    async def test_schedules_and_runs(self) -> None:
        """Background task completes successfully."""
        executed = False

        async def dummy():
            nonlocal executed
            executed = True

        task = schedule_background_task(dummy())
        await task
        assert executed is True

    @pytest.mark.asyncio
    async def test_handles_attribute_error(self) -> None:
        """Background task with AttributeError is caught by done callback."""

        async def broken():
            msg = "missing attr"
            raise AttributeError(msg)

        task = schedule_background_task(broken())
        # The task is created with a callback that logs the error.
        # Awaiting the task will re-raise, so use exception() instead.
        import asyncio

        await asyncio.sleep(0.01)
        exc = task.exception()
        assert exc is not None
        assert "missing attr" in str(exc)


class TestPersistSingleWrapper:
    def test_skips_missing_job(self) -> None:
        """No crash when job_id is not in jobs_store."""
        # jobs_store is empty by default
        persist_single_wrapper("nonexistent-id")  # Should not raise

    def test_saves_existing_job(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Saves a job that exists in jobs_store."""
        from app.globals import jobs_store
        from app.models import Job

        job = Job(name="test-job", id="test-id")
        jobs_store["test-id"] = job

        from unittest.mock import MagicMock

        mock_repo = AsyncMock()
        mock_repo.save_single = MagicMock()
        monkeypatch.setattr("app.lifespan.get_job_repository", lambda: mock_repo)

        persist_single_wrapper("test-id")
        mock_repo.save_single.assert_called_once_with(job)


@pytest.mark.asyncio
async def test_schedule_background_task_cancelled_does_not_raise() -> None:
    """CancelledError is silently handled."""
    import asyncio

    async def never_completes():
        await asyncio.sleep(999)

    task = schedule_background_task(never_completes())
    task.cancel()
    await asyncio.sleep(0.01)  # Let cancellation propagate
    # No exception should propagate


# ─── reset_lifespan_state ──────────────────────────────────────────────


class TestResetLifespanState:
    """Direct coverage for the test-only ``reset_lifespan_state`` backstop.

    The helper is a no-op in production code paths; it exists purely
    so the conftest autouse fixture (and any direct test driving the
    app through multiple lifespan cycles) can clear the module-level
    references set by an earlier ``lifespan()`` invocation.
    """

    def test_resets_module_state(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """After ``reset_lifespan_state()`` the module globals are cleared."""
        from app import lifespan

        # Simulate a previous lifespan() run by stuffing fake singletons
        # into the module-level names. The helper must clear them.
        monkeypatch.setattr(lifespan, "job_repo", object(), raising=False)
        monkeypatch.setattr(lifespan, "gossip", object(), raising=False)
        monkeypatch.setattr(lifespan, "heartbeat_mgr", object(), raising=False)
        monkeypatch.setattr(lifespan, "_background_tasks", [object()], raising=False)

        # Sanity check that the fixtures are actually in place — if
        # monkeypatch.setattr silently no-ops, the rest of the test
        # would still pass and give a false sense of security.
        assert lifespan.job_repo is not None
        assert lifespan.gossip is not None
        assert lifespan.heartbeat_mgr is not None
        assert lifespan._background_tasks != []

        lifespan.reset_lifespan_state()

        assert lifespan.job_repo is None
        assert lifespan.gossip is None
        assert lifespan.heartbeat_mgr is None
        assert lifespan._background_tasks == []

    def test_can_be_called_repeatedly(self) -> None:
        """Calling twice in a row must not raise."""
        from app.lifespan import reset_lifespan_state

        reset_lifespan_state()
        # Second call must also be a no-op and not raise.
        reset_lifespan_state()

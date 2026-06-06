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

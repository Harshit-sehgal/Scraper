"""Pins the lock-protected cancel-requested read in _scrape_single_url.

Regression test for the fix at :mod:`app.services.scraping` where the
``job.cancel_requested`` read at the start of each scrape task races the
write from the orchestrator cancel-poll loop. Both sites updated the
field but the scrape-task read side did not hold ``_jobs_store_lock``.
A concurrent cancel request could land between the read and write at the
scrape task, leaving the cancellation flag unset long enough to skip
the next page and produce inconsistent partial-result counts.
"""

from __future__ import annotations

import asyncio
import threading
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.models import Job, JobStatus


def _make_job() -> Job:
    return Job(
        id="cancel-race-job",
        name="cancel-race-test",
        created_by="test-user",
        urls=["https://example.com/test"],
        status=JobStatus.RUNNING,
        schema_fields=[],
    )


@pytest.mark.asyncio
async def test_scrape_single_url_uses_jobs_store_lock_when_reading_cancel_flag(monkeypatch) -> None:
    """The cancel-flag read at the top of ``_scrape_single_url`` must
    hold ``_jobs_store_lock`` so it cannot race the orchestrator's write."""
    from app.services import scraping
    from app.services.scraping import _scrape_single_url

    job = _make_job()

    lock_acquired_order: list[tuple[str, str]] = []

    class RecordingLock:
        def __init__(self, name: str, real_lock: threading.Lock) -> None:
            self._name = name
            self._real_lock = real_lock

        def __enter__(self) -> RecordingLock:
            lock_acquired_order.append(("enter", self._name))
            self._real_lock.acquire()
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            lock_acquired_order.append(("exit", self._name))
            self._real_lock.release()

        def __getattr__(self, item):
            return getattr(self._real_lock, item)

    real_lock = threading.Lock()
    recording_lock = RecordingLock("jobs_store_lock", real_lock)

    monkeypatch.setattr("app.globals._jobs_store_lock", recording_lock, raising=False)
    # The function under test imports ``_jobs_store_lock`` lazily via
    # ``from app.globals import _jobs_store_lock`` so patch the
    # already-imported name in ``app.services.scraping`` as well.
    monkeypatch.setattr(scraping, "_jobs_store_lock", recording_lock, raising=False)

    cancel_check_calls = 0

    async def always_cancelled() -> bool:
        nonlocal cancel_check_calls
        cancel_check_calls += 1
        return True

    with (
        patch.object(scraping, "_safe_log", AsyncMock()),
        patch.object(scraping, "_safe_warning", AsyncMock()),
    ):
        await _scrape_single_url(
            job,
            url=job.urls[0],
            idx=1,
            started_at=0.0,
            max_job_runtime_seconds=60,
            max_url_runtime_seconds=30,
            semaphore=asyncio.Semaphore(1),
            policy=MagicMock(),
            cancel_check=always_cancelled,
        )

    assert cancel_check_calls == 1, "cancel_check should fire exactly once"
    lock_acquired_names = {event for _, event in lock_acquired_order}
    assert "jobs_store_lock" in lock_acquired_names, (
        "scrape task must acquire _jobs_store_lock before reading/writing cancel_requested (regression race fix)."
    )


@pytest.mark.asyncio
async def test_cancel_requested_flag_is_set_under_lock_when_cancel_check_fires(monkeypatch) -> None:
    """When cancel_check returns True, cancel_requested must be set under the lock."""
    from app import globals as app_globals
    from app.services import scraping
    from app.services.scraping import _scrape_single_url

    job = _make_job()
    job.cancel_requested = False

    monkeypatch.setattr(scraping, "_jobs_store_lock", app_globals._jobs_store_lock, raising=False)

    async def always_cancelled() -> bool:
        return True

    with (
        patch.object(scraping, "_safe_log", AsyncMock()),
        patch.object(scraping, "_safe_warning", AsyncMock()),
    ):
        await _scrape_single_url(
            job,
            url=job.urls[0],
            idx=1,
            started_at=0.0,
            max_job_runtime_seconds=60,
            max_url_runtime_seconds=30,
            semaphore=asyncio.Semaphore(1),
            policy=MagicMock(),
            cancel_check=always_cancelled,
        )

    assert job.cancel_requested is True, "Cancel flag must be set when cancel_check returns True."


@pytest.mark.asyncio
async def test_cancel_requested_already_true_short_circuits(monkeypatch) -> None:
    """If cancel_requested is already True at the start, cancel_check never fires."""
    from app.services import scraping
    from app.services.scraping import _scrape_single_url

    job = _make_job()
    job.cancel_requested = True

    cancel_check_calls = 0

    async def cancel_check_must_not_fire() -> bool:
        nonlocal cancel_check_calls
        cancel_check_calls += 1
        return True

    with (
        patch.object(scraping, "_safe_log", AsyncMock()),
        patch.object(scraping, "_safe_warning", AsyncMock()),
    ):
        await _scrape_single_url(
            job,
            url=job.urls[0],
            idx=1,
            started_at=0.0,
            max_job_runtime_seconds=60,
            max_url_runtime_seconds=30,
            semaphore=asyncio.Semaphore(1),
            policy=MagicMock(),
            cancel_check=cancel_check_must_not_fire,
        )

    assert cancel_check_calls == 0, "cancel_check must be skipped once cancel_requested is already True."

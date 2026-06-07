"""Tests for ``app.job_store.count_jobs_by_status``.

The function powers the metrics endpoint's job-count gauge. A
silent regression in the storage layer that produces a wrong count
(e.g. re-introducing the legacy ``list_job_summaries(limit=500)``
clamp) would make the dashboard lie. These tests pin the behavior
against the SQLite fixture used by the rest of the suite.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from app.job_store import (
    _DB_LOCK,
    _get_connection,
    count_jobs_by_status,
    reset_job_store_for_tests,
)
from app.models import Job, JobStatus


@pytest.fixture
def fresh_db() -> Generator[None, None, None]:
    """Wipe the ``jobs`` and ``recycle_bin`` tables for each test.

    We cannot drop the tables wholesale because other tests in the
    same process rely on the schema being initialized. A targeted
    ``DELETE`` is enough for ``count_jobs_by_status`` to be observable
    from a known-empty state.
    """
    reset_job_store_for_tests()
    with _DB_LOCK:
        conn = _get_connection()
        try:
            conn.execute("DELETE FROM jobs")
            conn.execute("DELETE FROM recycle_bin")
            conn.commit()
        finally:
            conn.close()
    yield
    # No teardown needed — the autouse ``client`` fixture (when
    # present) and ``pytest_sessionfinish`` clean up the file.


def _make_job(job_id: str, status: JobStatus, name: str | None = None) -> Job:
    """Build a minimal ``Job`` that ``_job_to_row`` can persist.

    The full ``Job`` model has dozens of fields; we only need a
    unique id, a name, and a status for the GROUP BY query to
    distinguish rows.
    """
    return Job(
        id=job_id,
        name=name or f"job-{job_id}",
        status=status,
        urls=["https://example.com"],
        schema_fields=[],
    )


def _insert_job(job: Job) -> None:
    """Persist a single job row into SQLite for test assertions."""
    from app.job_store import persist_state_single

    persist_state_single(job)


def test_count_jobs_by_status_empty_repo(fresh_db) -> None:
    """An empty repository returns an empty mapping.

    The legacy implementation returned ``{'': 0}`` for an empty
    store because of a faulty ``list_job_summaries`` fallback — the
    pin here is that an empty store yields an empty dict, so the
    metrics loop does not render a misleading zero-count gauge.

    The ``include_deleted`` flag toggles whether the ``recycle_bin``
    table is also aggregated. The default ``False`` path queries
    only the ``jobs`` table; the SQLite ``jobs`` schema has no
    ``deleted_at`` column (soft-deleted jobs move to ``recycle_bin``),
    so there is no filter needed on the active side.
    """
    result = count_jobs_by_status(include_deleted=False)
    assert result == {}, f"Empty store must yield {{}}, got {result!r}"


def test_count_jobs_by_status_single_job(fresh_db) -> None:
    """A single job is counted under its own status bucket."""
    _insert_job(_make_job("solo", JobStatus.RUNNING))
    result = count_jobs_by_status(include_deleted=False)
    assert result == {"running": 1}


def test_count_jobs_by_status_mixed_statuses(fresh_db) -> None:
    """Mixed statuses produce one bucket per distinct status value."""
    _insert_job(_make_job("a", JobStatus.RUNNING))
    _insert_job(_make_job("b", JobStatus.RUNNING))
    _insert_job(_make_job("c", JobStatus.COMPLETED))
    _insert_job(_make_job("d", JobStatus.FAILED))
    _insert_job(_make_job("e", JobStatus.PENDING))

    result = count_jobs_by_status(include_deleted=False)
    assert result == {
        "running": 2,
        "completed": 1,
        "failed": 1,
        "pending": 1,
    }


def test_count_jobs_by_status_with_recycle_bin(fresh_db) -> None:
    """When ``include_deleted=True``, soft-deleted jobs in the
    ``recycle_bin`` table are folded into the same buckets, with
    deleted counts added to the active counts for any matching
    status.
    """
    from app.job_store import save_state

    active = {
        "active": _make_job("active", JobStatus.RUNNING),
        "done": _make_job("done", JobStatus.COMPLETED),
    }
    soft_deleted = {
        "soft-deleted-1": _make_job("soft-deleted-1", JobStatus.COMPLETED),
    }
    save_state(active, soft_deleted)

    # include_deleted=False: only the active jobs are counted.
    active_only = count_jobs_by_status(include_deleted=False)
    assert active_only == {"running": 1, "completed": 1}

    # include_deleted=True: the recycle_bin row is added to the
    # ``completed`` bucket (1 active + 1 soft-deleted = 2).
    with_recycle = count_jobs_by_status(include_deleted=True)
    assert with_recycle == {"running": 1, "completed": 2}

"""Round-trip tests for data retention enforcement.

Verifies that ``enforce_retention`` correctly identifies expired jobs
and that the save path persists deletions via ``save_state()``.
"""

from __future__ import annotations

import datetime
from unittest.mock import patch

from app.models import Job, JobStatus


def _fake_job(
    id_: str = "1",
    status: JobStatus = JobStatus.COMPLETED,
    completed_at: str | None = None,
) -> Job:
    """Build a minimal Job for retention testing."""
    return Job(
        id=id_,
        name=f"job-{id_}",
        status=status,
        urls=["https://test.invalid"],
        completed_at=completed_at or "",
        schema_fields=[],
        results=[],
    )


def _days_ago(days: int) -> str:
    """Return ISO-8601 timestamp for *days* ago."""
    return (datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=days)).isoformat()


class TestRetentionRoundTrip:
    """Data retention policy identifies expired jobs and persists deletions."""

    def test_completed_job_within_retention_window_is_skipped(self) -> None:
        from app.utils.data_retention import enforce_retention

        jobs_store: dict[str, Job] = {"job-1": _fake_job("1", completed_at=_days_ago(10))}
        recycle_bin_store: dict[str, Job] = {}
        result = enforce_retention(jobs_store, recycle_bin_store, dry_run=True)
        assert result["jobs_purged"] == 0
        assert result["jobs_skipped"] == 1
        assert "job-1" in jobs_store  # not actually deleted

    def test_expired_completed_job_is_purged(self) -> None:
        from app.utils.data_retention import enforce_retention

        jobs_store: dict[str, Job] = {"job-old": _fake_job("old", completed_at=_days_ago(100))}
        recycle_bin_store: dict[str, Job] = {}
        result = enforce_retention(jobs_store, recycle_bin_store, dry_run=False)
        assert result["jobs_purged"] == 1
        assert "job-old" not in jobs_store

    def test_active_jobs_are_never_purged(self) -> None:
        from app.utils.data_retention import enforce_retention

        jobs_store = {
            "active": _fake_job("active", status=JobStatus.RUNNING),
            "pending": _fake_job("pending", status=JobStatus.PENDING),
        }
        recycle_bin_store: dict[str, Job] = {}
        result = enforce_retention(jobs_store, recycle_bin_store, dry_run=False)
        assert result["jobs_purged"] == 0
        assert "active" in jobs_store
        assert "pending" in jobs_store

    def test_failed_jobs_are_terminal_and_purgeable(self) -> None:
        from app.utils.data_retention import enforce_retention

        jobs_store = {"failed-old": _fake_job("failed-old", status=JobStatus.FAILED, completed_at=_days_ago(100))}
        recycle_bin_store: dict[str, Job] = {}
        result = enforce_retention(jobs_store, recycle_bin_store, dry_run=False)
        assert result["jobs_purged"] == 1
        assert "failed-old" not in jobs_store

    def test_recycle_bin_items_expire(self) -> None:
        from app.utils.data_retention import enforce_retention

        jobs_store: dict[str, Job] = {}
        recycle_bin_store = {"rec-old": _fake_job("rec-old", completed_at=_days_ago(40))}
        result = enforce_retention(jobs_store, recycle_bin_store, dry_run=False)
        assert result["recycle_purged"] == 1
        assert "rec-old" not in recycle_bin_store

    def test_dry_run_does_not_delete(self) -> None:
        from app.utils.data_retention import enforce_retention

        jobs_store: dict[str, Job] = {"job-old": _fake_job("old", completed_at=_days_ago(100))}
        recycle_bin_store: dict[str, Job] = {}
        result = enforce_retention(jobs_store, recycle_bin_store, dry_run=True)
        assert result["jobs_purged"] == 1
        assert "job-old" in jobs_store  # still exists

    def test_save_state_is_called_for_real_deletions(self) -> None:
        r"""When retention actually deletes jobs, save_state must be called.

        `enforce_retention` internally calls `app.state_store.save_state`
        after the in-memory mutation so the purge is durable across
        restart. The pre-fix behaviour only mutated the in-memory dict
        and relied on the next `save_state` from a different caller —
        which produced silent data resurrection on container restart.
        """
        from app.utils.data_retention import enforce_retention

        jobs_store: dict[str, Job] = {"job-old": _fake_job("old", completed_at=_days_ago(100))}
        recycle_bin_store: dict[str, Job] = {}

        with patch("app.state_store.save_state") as mock_save:
            enforce_retention(jobs_store, recycle_bin_store, dry_run=False)

        # The in-memory store must be mutated.
        assert "job-old" not in jobs_store
        # save_state was invoked with the pruned state to persist.
        assert mock_save.called
        call_args = mock_save.call_args
        assert "job-old" not in call_args[0][0]
        assert call_args[0][1] == recycle_bin_store

    def test_save_state_not_called_for_dry_run(self) -> None:
        """A dry-run retention sweep must not call save_state — nothing was mutated."""
        from app.utils.data_retention import enforce_retention

        jobs_store: dict[str, Job] = {"job-old": _fake_job("old", completed_at=_days_ago(100))}
        recycle_bin_store: dict[str, Job] = {}

        with patch("app.state_store.save_state") as mock_save:
            enforce_retention(jobs_store, recycle_bin_store, dry_run=True)

        assert mock_save.call_count == 0

    def test_save_state_not_called_when_nothing_purged(self) -> None:
        """No-op retention sweeps must not call save_state — avoids spurious disk writes."""
        from app.utils.data_retention import enforce_retention

        jobs_store: dict[str, Job] = {"active": _fake_job("active", status=JobStatus.RUNNING)}
        recycle_bin_store: dict[str, Job] = {}

        with patch("app.state_store.save_state") as mock_save:
            enforce_retention(jobs_store, recycle_bin_store, dry_run=False)

        assert mock_save.call_count == 0
        # The in-memory dict is unchanged
        assert "active" in jobs_store

    def test_retention_uses_jobs_store_lock(self) -> None:
        r"""The retention sweep must acquire `_jobs_store_lock` so concurrent
        mutations to `jobs_store` cannot tear-read or pop mid-iteration.
        """
        from app.utils.data_retention import enforce_retention

        jobs_store: dict[str, Job] = {"job-old": _fake_job("old", completed_at=_days_ago(100))}
        recycle_bin_store: dict[str, Job] = {}

        # Patch the lock in `app.globals` — `enforce_retention` reads it
        # lazily. Use a real `threading.Lock` context manager, not a
        # MagicMock, so the `with` statement works correctly.
        import threading

        lock = threading.Lock()
        with patch("app.globals._jobs_store_lock", lock):
            with patch("app.state_store.save_state"):
                result = enforce_retention(jobs_store, recycle_bin_store, dry_run=False)

        assert result["jobs_purged"] == 1
        assert "job-old" not in jobs_store

    def test_retention_config_returns_expected_keys(self) -> None:
        from app.utils.data_retention import get_retention_config

        config = get_retention_config()
        assert "completed_jobs_days" in config
        assert "recycle_bin_days" in config
        assert "idempotency_keys_days" in config
        assert all(isinstance(v, int) and v > 0 for v in config.values())

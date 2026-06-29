from __future__ import annotations

import datetime

from app.models import Job, JobStatus
from app.utils.data_retention import (
    enforce_idempotency_retention,
    enforce_retention,
    get_retention_config,
)


def _make_job(job_id: str, status: JobStatus, days_ago: int = 0) -> Job:
    created_at = (datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=days_ago)).isoformat()
    completed_at = created_at
    return Job(
        name=f"test-{job_id}",
        mode="manual",
        urls=["https://example.com"],
        status=status,
        created_at=created_at,
        completed_at=completed_at,
    )


class TestRetention:
    def test_retention_config_has_expected_keys(self) -> None:
        config = get_retention_config()
        assert "completed_jobs_days" in config
        assert "recycle_bin_days" in config
        assert "idempotency_keys_days" in config

    def test_enforce_retention_purges_old_completed_jobs(self) -> None:
        store = {}
        store["old_job"] = _make_job("old_job", JobStatus.COMPLETED, days_ago=200)
        store["new_job"] = _make_job("new_job", JobStatus.COMPLETED, days_ago=1)
        result = enforce_retention(store, {}, dry_run=False)
        assert result["jobs_purged"] >= 1
        assert "old_job" not in store
        assert "new_job" in store

    def test_enforce_retention_skips_non_terminal_jobs(self) -> None:
        store = {}
        store["pending"] = _make_job("pending", JobStatus.PENDING, days_ago=200)
        result = enforce_retention(store, {}, dry_run=False)
        assert result["jobs_purged"] == 0
        assert "pending" in store

    def test_enforce_retention_purges_old_recycle_items(self) -> None:
        recycle = {}
        recycle["old_recycle"] = _make_job("old_recycle", JobStatus.COMPLETED, days_ago=200)
        result = enforce_retention({}, recycle, dry_run=False)
        assert result["recycle_purged"] >= 1

    def test_dry_run_does_not_delete(self) -> None:
        store = {}
        store["old_job"] = _make_job("old_job", JobStatus.COMPLETED, days_ago=200)
        result = enforce_retention(store, {}, dry_run=True)
        assert result["jobs_purged"] >= 1
        assert "old_job" in store

    def test_get_retention_config_returns_ints(self) -> None:
        config = get_retention_config()
        for v in config.values():
            assert isinstance(v, int)
            assert v > 0

    def test_recycle_items_within_window_are_skipped(self) -> None:
        recycle = {}
        recycle["recent"] = _make_job("recent", JobStatus.COMPLETED, days_ago=1)
        result = enforce_retention({}, recycle, dry_run=False)
        assert result["recycle_purged"] == 0
        assert "recent" in recycle

    def test_enforce_idempotency_retention(self) -> None:
        deleted = enforce_idempotency_retention(dry_run=False)
        assert isinstance(deleted, int)

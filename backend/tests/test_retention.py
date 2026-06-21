"""Tests for data retention enforcement and monitoring."""

from __future__ import annotations

import datetime
from typing import Any

import pytest

from app.models import Job, JobStatus
from app.utils.data_retention import _age_in_days, enforce_retention, get_retention_config
from app.utils.retention_monitoring import RetentionMonitor, get_retention_monitor, record_retention_run


# ─── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def jobs_store() -> dict[str, Any]:
    return {}


@pytest.fixture
def recycle_bin_store() -> dict[str, Any]:
    return {}


@pytest.fixture
def fresh_monitor() -> RetentionMonitor:
    return RetentionMonitor()


# ─── Config ────────────────────────────────────────────────────────────


class TestRetentionConfig:
    def test_returns_defaults(self, monkeypatch):
        monkeypatch.delenv("DATAFORGE_RETENTION_DAYS_COMPLETED", raising=False)
        monkeypatch.delenv("DATAFORGE_RETENTION_DAYS_RECYCLE", raising=False)
        monkeypatch.delenv("DATAFORGE_RETENTION_DAYS_IDEMPOTENCY", raising=False)
        config = get_retention_config()
        assert config["completed_jobs_days"] == 90
        assert config["recycle_bin_days"] == 30
        assert config["idempotency_keys_days"] == 7

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("DATAFORGE_RETENTION_DAYS_COMPLETED", "14")
        monkeypatch.setenv("DATAFORGE_RETENTION_DAYS_RECYCLE", "7")
        config = get_retention_config()
        assert config["completed_jobs_days"] == 14
        assert config["recycle_bin_days"] == 7


# ─── Enforcement ───────────────────────────────────────────────────────


class TestEnforceRetention:
    def _make_job(self, job_id: str, status: str, completed_at: str | None) -> Job:
        now = datetime.datetime.now(datetime.UTC).isoformat()
        return Job(
            id=job_id,
            name=f"Job {job_id}",
            status=status,
            completed_at=completed_at,
            created_at=completed_at or now,
        )

    def test_purges_old_terminal_jobs(self, jobs_store, recycle_bin_store):
        old = (datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=100)).isoformat()
        recent = (datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=1)).isoformat()

        jobs_store["old"] = self._make_job("old", JobStatus.COMPLETED.value, old)
        jobs_store["recent"] = self._make_job("recent", JobStatus.COMPLETED.value, recent)
        jobs_store["pending"] = self._make_job("pending", JobStatus.PENDING.value, None)

        result = enforce_retention(jobs_store, recycle_bin_store, dry_run=False)

        assert result["jobs_purged"] == 1
        assert result["jobs_skipped"] == 1
        assert "old" not in jobs_store
        assert "recent" in jobs_store
        assert "pending" in jobs_store

    def test_purges_old_recycle_items(self, jobs_store, recycle_bin_store):
        old = (datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=40)).isoformat()
        recent = (datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=1)).isoformat()

        recycle_bin_store["old"] = self._make_job("old", JobStatus.COMPLETED.value, old)
        recycle_bin_store["recent"] = self._make_job("recent", JobStatus.FAILED.value, recent)

        result = enforce_retention(jobs_store, recycle_bin_store, dry_run=False)

        assert result["recycle_purged"] == 1
        assert result["recycle_skipped"] == 1
        assert "old" not in recycle_bin_store
        assert "recent" in recycle_bin_store

    def test_dry_run_does_not_mutate(self, jobs_store, recycle_bin_store):
        old = (datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=100)).isoformat()
        jobs_store["old"] = self._make_job("old", JobStatus.COMPLETED.value, old)
        recycle_bin_store["old"] = self._make_job("old", JobStatus.COMPLETED.value, old)

        result = enforce_retention(jobs_store, recycle_bin_store, dry_run=True)

        assert result["jobs_purged"] == 1
        assert result["recycle_purged"] == 1
        assert "old" in jobs_store
        assert "old" in recycle_bin_store

    def test_skips_active_jobs(self, jobs_store, recycle_bin_store):
        old = (datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=100)).isoformat()
        jobs_store["running"] = self._make_job("running", JobStatus.RUNNING.value, None)
        jobs_store["discovering"] = self._make_job("discovering", JobStatus.DISCOVERING.value, None)
        jobs_store["old_completed"] = self._make_job("old_completed", JobStatus.COMPLETED.value, old)

        result = enforce_retention(jobs_store, recycle_bin_store, dry_run=False)

        assert result["jobs_purged"] == 1
        assert "running" in jobs_store
        assert "discovering" in jobs_store


# ─── Monitoring ────────────────────────────────────────────────────────


class TestRetentionMonitor:
    def test_records_success(self):
        record_retention_run(result={"jobs_purged": 2, "recycle_purged": 1})
        monitor = get_retention_monitor()
        health = monitor.get_health_check()
        assert health["ok"] is True
        assert health["total_purged"] == 3

    def test_records_failure(self):
        for _ in range(3):
            record_retention_run(error=RuntimeError("boom"))
        monitor = get_retention_monitor()
        health = monitor.get_health_check()
        assert health["ok"] is False
        assert "Failed" in health["status"]

    def test_never_run_is_unhealthy(self):
        monitor = RetentionMonitor()
        health = monitor.get_health_check()
        assert health["ok"] is False
        assert health["status"] == "Never run"


# ─── Helpers ───────────────────────────────────────────────────────────


class TestAgeInDays:
    def test_parses_iso_timestamp(self):
        past = (datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=5)).isoformat()
        age = _age_in_days(past)
        assert age is not None
        assert 4.9 < age < 5.1

    def test_none_for_unparseable(self):
        assert _age_in_days("not-a-date") is None

    def test_none_for_empty(self):
        assert _age_in_days("") is None
        assert _age_in_days(None) is None

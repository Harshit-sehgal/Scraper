"""Unit tests for previously untested SQLiteJobRepository methods.

Covers: is_cancel_requested, save_world_state, load_world_state,
count_jobs_by_status, record_worker_heartbeat, get_worker_health,
get_all_worker_healths."""

from __future__ import annotations

import pytest
from app.job_store import (
    count_jobs_by_status,
    get_all_worker_healths,
    get_worker_health,
    record_worker_heartbeat,
    reset_job_store_for_tests,
)
from app.models import Job, JobStatus


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    """Point job_store at a fresh temp DB for each test."""
    from app.config import settings

    db_file = tmp_path / "test_jobs.db"
    state_file = db_file.with_suffix(".json")
    monkeypatch.setenv("DATAFORGE_STATE_FILE", str(state_file))
    monkeypatch.setattr(settings, "STATE_FILE_PATH", str(state_file))
    reset_job_store_for_tests()
    yield db_file
    reset_job_store_for_tests()


@pytest.fixture(autouse=True)
def _reset_store() -> None:
    reset_job_store_for_tests()


# ── is_cancel_requested ──────────────────────────────────────────────────


def test_is_cancel_requested_returns_false_by_default(isolated_db) -> None:
    from app.storage_interface import SQLiteJobRepository

    repo = SQLiteJobRepository()
    repo.save_single(Job(id="test-cancel-1", name="test"))
    assert repo.is_cancel_requested("test-cancel-1") is False


def test_is_cancel_requested_returns_true_when_set(isolated_db) -> None:
    from app.storage_interface import SQLiteJobRepository

    repo = SQLiteJobRepository()
    job = Job(id="test-cancel-2", name="test", cancel_requested=True)
    repo.save_single(job)
    assert repo.is_cancel_requested("test-cancel-2") is True


def test_is_cancel_requested_nonexistent_job(isolated_db) -> None:
    from app.storage_interface import SQLiteJobRepository

    repo = SQLiteJobRepository()
    assert repo.is_cancel_requested("nonexistent") is False


# ── save_world_state / load_world_state ─────────────────────────────────


def test_save_and_load_world_state(isolated_db, tmp_path) -> None:
    from app.storage_interface import SQLiteJobRepository

    repo = SQLiteJobRepository()
    payload = {"last_run": "2026-06-22", "job_count": 42}
    repo.save_world_state(payload)
    loaded = repo.load_world_state()
    assert loaded is not None
    assert loaded["last_run"] == "2026-06-22"
    assert loaded["job_count"] == 42


def test_load_world_state_returns_none_when_missing(isolated_db) -> None:
    from app.storage_interface import SQLiteJobRepository

    repo = SQLiteJobRepository()
    assert repo.load_world_state() is None


def test_save_world_state_overwrites(isolated_db, tmp_path) -> None:
    from app.storage_interface import SQLiteJobRepository

    repo = SQLiteJobRepository()
    repo.save_world_state({"version": 1})
    repo.save_world_state({"version": 2})
    loaded = repo.load_world_state()
    assert loaded is not None
    assert loaded["version"] == 2


# ── count_jobs_by_status ────────────────────────────────────────────────


def test_count_jobs_by_status_empty(isolated_db) -> None:
    counts = count_jobs_by_status()
    assert isinstance(counts, dict)
    assert all(v == 0 for v in counts.values())


def test_count_jobs_by_status_with_jobs(isolated_db) -> None:
    from app.storage_interface import SQLiteJobRepository

    repo = SQLiteJobRepository()
    repo.save_single(Job(id="s1", name="a", status=JobStatus.PENDING))
    repo.save_single(Job(id="s2", name="b", status=JobStatus.RUNNING))
    repo.save_single(Job(id="s3", name="c", status=JobStatus.COMPLETED))
    repo.save_single(Job(id="s4", name="d", status=JobStatus.RUNNING))

    counts = count_jobs_by_status()
    assert counts.get("pending", 0) == 1
    assert counts.get("running", 0) == 2
    assert counts.get("completed", 0) == 1


# ── record_worker_heartbeat / get_worker_health / get_all_worker_healths ─


def test_record_and_get_worker_health(isolated_db) -> None:
    record_worker_heartbeat("worker-1", "host-a", 1001)
    health = get_worker_health("worker-1")
    assert health["alive"] is True
    assert health["worker_id"] == "worker-1"
    assert health["hostname"] == "host-a"
    assert health["pid"] == 1001


def test_get_worker_health_unknown_returns_dead(isolated_db) -> None:
    health = get_worker_health("nonexistent-worker")
    assert health["alive"] is False


def test_get_all_worker_healths_returns_multiple(isolated_db) -> None:
    record_worker_heartbeat("w1", "host-a", 1)
    record_worker_heartbeat("w2", "host-b", 2)
    all_health = get_all_worker_healths()
    worker_ids = {h["worker_id"] for h in all_health}
    assert "w1" in worker_ids
    assert "w2" in worker_ids


def test_get_all_worker_healths_empty(isolated_db) -> None:
    all_health = get_all_worker_healths()
    assert all_health == []


def test_get_worker_health_ttl_respected(isolated_db) -> None:
    record_worker_heartbeat("worker-old", "host-a", 1)
    health = get_worker_health("worker-old", ttl_seconds=0)
    assert health["alive"] is False

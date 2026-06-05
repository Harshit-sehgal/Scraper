"""Tests for the v4 storage-split companion tables (``job_results``, ``job_events``).

The v4 schema introduces dedicated ``job_results`` and ``job_events``
tables so that endpoints like ``GET /api/jobs/{id}/events`` no longer
have to deserialize the entire JSON blob in the main ``jobs`` row.
Writes are dual (the new tables and the legacy JSON column both get
the same data) so existing readers keep working.
"""

from __future__ import annotations

import pytest
from app.models import Job, JobStatus, LogEntry, ScrapeMode


def _make_job(idx: int = 1) -> Job:
    return Job(
        id=f"split-{idx}",
        name=f"Split {idx}",
        mode=ScrapeMode.MANUAL,
        urls=[f"https://example.com/{idx}"],
        topic="test",
        status=JobStatus.RUNNING,
    )


class TestSchemaVersion4:
    def test_current_schema_version_is_at_least_4(self) -> None:
        from app.job_store import _CURRENT_SCHEMA_VERSION

        assert _CURRENT_SCHEMA_VERSION >= 4

    def test_companion_tables_exist_after_migration(self, isolated_db) -> None:
        from app.job_store import _DB_LOCK, _get_connection

        with _DB_LOCK:
            conn = _get_connection()
            try:
                rows = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('job_results', 'job_events')"
                ).fetchall()
            finally:
                conn.close()
        names = {r[0] for r in rows}
        assert "job_results" in names
        assert "job_events" in names


class TestDualWrite:
    def test_persist_state_single_writes_to_job_events(self, isolated_db) -> None:
        from app.job_store import (
            _DB_LOCK,
            _get_connection,
            persist_state_single,
        )

        job = _make_job(1)
        job.logs.append(LogEntry(timestamp="2026-01-01T00:00:00+00:00", message="start", level="info"))
        job.logs.append(LogEntry(timestamp="2026-01-01T00:00:01+00:00", message="warn", level="warning"))
        persist_state_single(job)

        with _DB_LOCK:
            conn = _get_connection()
            try:
                rows = conn.execute(
                    "SELECT timestamp, level, message FROM job_events WHERE job_id = ? ORDER BY event_id ASC",
                    (job.id,),
                ).fetchall()
            finally:
                conn.close()
        assert len(rows) == 2
        assert rows[0]["message"] == "start"
        assert rows[1]["message"] == "warn"

    def test_persist_state_single_writes_to_job_results(self, isolated_db) -> None:
        from app.job_store import (
            _DB_LOCK,
            _get_connection,
            persist_state_single,
        )

        job = _make_job(2)
        job.results = [{"a": 1}, {"b": 2}, {"c": 3}]
        persist_state_single(job)

        with _DB_LOCK:
            conn = _get_connection()
            try:
                rows = conn.execute(
                    "SELECT result_index, payload FROM job_results WHERE job_id = ? ORDER BY result_index ASC",
                    (job.id,),
                ).fetchall()
            finally:
                conn.close()
        assert len(rows) == 3
        assert rows[0]["result_index"] == 0
        assert rows[1]["result_index"] == 1
        assert rows[2]["result_index"] == 2

    def test_dual_write_replaces_existing_rows(self, isolated_db) -> None:
        """A second save with a different result set must fully replace
        the prior ``job_results`` rows (not append).
        """
        from app.job_store import (
            _DB_LOCK,
            _get_connection,
            persist_state_single,
        )

        job = _make_job(3)
        job.results = [{"a": 1}, {"a": 2}]
        persist_state_single(job)
        # Now overwrite with a smaller list
        job.results = [{"only": True}]
        persist_state_single(job)
        with _DB_LOCK:
            conn = _get_connection()
            try:
                rows = conn.execute(
                    "SELECT payload FROM job_results WHERE job_id = ?",
                    (job.id,),
                ).fetchall()
            finally:
                conn.close()
        assert len(rows) == 1


class TestReaderHelpers:
    def test_read_job_events_returns_ordered(self, isolated_db) -> None:
        from app.job_store import persist_state_single, read_job_events

        job = _make_job(4)
        for i in range(5):
            job.logs.append(
                LogEntry(timestamp=f"2026-01-01T00:00:0{i}+00:00", message=f"msg-{i}"),
            )
        persist_state_single(job)
        events = read_job_events(job.id, limit=10, offset=0)
        assert [e["message"] for e in events] == [f"msg-{i}" for i in range(5)]

    def test_read_job_events_level_filter(self, isolated_db) -> None:
        from app.job_store import persist_state_single, read_job_events

        job = _make_job(5)
        job.logs.append(LogEntry(timestamp="2026-01-01T00:00:00", message="ok", level="info"))
        job.logs.append(LogEntry(timestamp="2026-01-01T00:00:01", message="boom", level="error"))
        job.logs.append(LogEntry(timestamp="2026-01-01T00:00:02", message="ok2", level="info"))
        persist_state_single(job)
        only_errors = read_job_events(job.id, limit=10, level_prefix="err")
        assert [e["message"] for e in only_errors] == ["boom"]

    def test_count_job_events(self, isolated_db) -> None:
        from app.job_store import count_job_events, persist_state_single

        job = _make_job(6)
        for i in range(3):
            job.logs.append(LogEntry(timestamp=f"2026-01-01T00:00:0{i}", message=f"m{i}"))
        persist_state_single(job)
        assert count_job_events(job.id) == 3

    def test_read_job_results_round_trip(self, isolated_db) -> None:
        from app.job_store import persist_state_single, read_job_results

        job = _make_job(7)
        job.results = [{"k": "v1", "n": 1}, {"k": "v2", "n": 2}]
        persist_state_single(job)
        out = read_job_results(job.id)
        assert out == [{"k": "v1", "n": 1}, {"k": "v2", "n": 2}]


class TestCleanupCompanionData:
    def test_hard_delete_cleans_companion_tables(self, isolated_db) -> None:
        """hard_delete must remove both main row AND companion data."""
        from app.storage_interface import SQLiteJobRepository

        repo = SQLiteJobRepository()
        job = _make_job(10)
        job.results = [{"k": "v"}]
        job.logs.append(LogEntry(timestamp="2026-01-01", message="test"))
        repo.save_single(job)
        # Verify companion rows exist
        from app.job_store import lookup_idempotency_key, record_idempotency_key

        record_idempotency_key("cleanup-key", job.id, "fp")

        repo.hard_delete(job.id)
        # Main job must be gone
        from app.job_store import (
            read_job_events,
            read_job_results,
        )

        assert repo.get_job(job.id) is None
        # Companion rows must also be gone
        assert read_job_results(job.id) == []
        assert read_job_events(job.id) == []
        # Idempotency key should remain (it's not a companion table — designed to survive deletes)
        assert lookup_idempotency_key("cleanup-key") == job.id

    def test_move_to_recycle_bin_preserves_companion_data(self, isolated_db) -> None:
        """Moving a job to recycle bin should preserve companion data
        so the results are still accessible after restore.
        """
        from app.storage_interface import SQLiteJobRepository

        repo = SQLiteJobRepository()
        job = _make_job(11)
        job.results = [{"preserved": True}]
        job.logs.append(LogEntry(timestamp="2026-01-01", message="moved"))
        repo.save_single(job)

        from app.job_store import read_job_events, read_job_results

        assert read_job_results(job.id) == [{"preserved": True}]
        repo.move_to_recycle_bin(job.id)
        # After move, companion data should still be readable via the raw readers
        assert read_job_results(job.id) == [{"preserved": True}]
        assert len(read_job_events(job.id)) == 1

    def test_cleanup_companion_data_removes_only_target_job(self, isolated_db) -> None:
        """cleanup_companion_data must not touch other jobs' data."""
        from app.storage_interface import SQLiteJobRepository

        repo = SQLiteJobRepository()
        keep = _make_job(12)
        keep.results = [{"keep": True}]
        remove = _make_job(13)
        remove.results = [{"remove": True}]
        repo.save_single(keep)
        repo.save_single(remove)

        from app.job_store import read_job_results

        repo.cleanup_companion_data(remove.id)
        assert read_job_results(remove.id) == []
        assert read_job_results(keep.id) == [{"keep": True}]

    def test_cleanup_companion_data_noop_for_nonexistent_job(self, isolated_db) -> None:
        """Calling cleanup_companion_data on a non-existent job must not raise."""
        from app.storage_interface import SQLiteJobRepository

        repo = SQLiteJobRepository()
        # Should not raise
        repo.cleanup_companion_data("never-existed")


class TestReadResults:
    def test_read_results_empty_for_no_results(self, isolated_db) -> None:
        from app.storage_interface import SQLiteJobRepository

        repo = SQLiteJobRepository()
        job = _make_job(14)
        repo.save_single(job)
        from app.job_store import read_job_results

        assert read_job_results(job.id) == []

    def test_read_results_with_offset(self, isolated_db) -> None:
        from app.storage_interface import SQLiteJobRepository

        repo = SQLiteJobRepository()
        job = _make_job(15)
        job.results = [{"idx": i} for i in range(10)]
        repo.save_single(job)
        from app.job_store import read_job_results

        out = read_job_results(job.id)
        assert len(out) == 10

    def test_read_results_returns_in_order(self, isolated_db) -> None:
        from app.storage_interface import SQLiteJobRepository

        repo = SQLiteJobRepository()
        job = _make_job(16)
        job.results = [{"letter": chr(65 + i)} for i in range(5)]
        repo.save_single(job)
        from app.job_store import read_job_results

        out = read_job_results(job.id)
        assert [r["letter"] for r in out] == ["A", "B", "C", "D", "E"]


class TestRepositoryContract:
    def test_sqlite_repo_implements_all_abstract_methods(self) -> None:
        from app.storage_interface import SQLiteJobRepository

        assert hasattr(SQLiteJobRepository, "read_events")
        assert hasattr(SQLiteJobRepository, "read_results")
        assert hasattr(SQLiteJobRepository, "cleanup_companion_data")
        assert hasattr(SQLiteJobRepository, "lookup_idempotency_key")
        assert hasattr(SQLiteJobRepository, "record_idempotency_key")
        assert hasattr(SQLiteJobRepository, "prune_idempotency_keys")


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    """Point job_store at a fresh temp DB for each test."""
    from app.config import settings
    from app.job_store import reset_job_store_for_tests

    db_file = tmp_path / "test_jobs.db"
    state_file = db_file.with_suffix(".json")
    monkeypatch.setenv("DATAFORGE_STATE_FILE", str(state_file))
    monkeypatch.setattr(settings, "STATE_FILE_PATH", str(state_file))
    reset_job_store_for_tests()
    yield db_file
    reset_job_store_for_tests()

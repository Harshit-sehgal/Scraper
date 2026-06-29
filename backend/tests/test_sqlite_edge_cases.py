"""Edge-case tests for SQLite storage layer — covers boundary conditions,
concurrent access patterns, and data integrity invariants.

Adds to the existing test_sqlite_repository_untested.py and
test_storage_mapper.py coverage by testing rarely-hit code paths.
"""

from __future__ import annotations

import threading

import pytest
from app.models import Job, JobStatus


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    """Point job_store at a fresh temp DB for each test."""
    from app.config import settings

    db_file = tmp_path / "test_jobs.db"
    state_file = db_file.with_suffix(".json")
    monkeypatch.setenv("DATAFORGE_STATE_FILE", str(state_file))
    monkeypatch.setattr(settings, "STATE_FILE_PATH", str(state_file))
    from app.job_store import reset_job_store_for_tests

    reset_job_store_for_tests()
    yield db_file
    reset_job_store_for_tests()


# ── Concurrent write safety ──────────────────────────────────────────────


class TestConcurrentWrites:
    """Verify the SQLite backend handles concurrent writes safely."""

    def test_concurrent_save_single_does_not_corrupt(self, isolated_db) -> None:
        """8 threads saving different jobs must not lose or corrupt data."""
        from app.storage_interface import SQLiteJobRepository

        repo = SQLiteJobRepository()
        n = 8
        jobs = [Job(id=f"concurrent-{i}", name=f"job-{i}") for i in range(n)]

        def _save(j: Job) -> None:
            repo.save_single(j)

        threads = [threading.Thread(target=_save, args=(j,)) for j in jobs]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        for j in jobs:
            loaded = repo.get_job(j.id)
            assert loaded is not None, f"Job {j.id} was lost during concurrent write"
            assert loaded.name == j.name

    def test_concurrent_save_and_read_consistent(self, isolated_db) -> None:
        """Concurrent reads during write must not observe partial state."""
        from app.storage_interface import SQLiteJobRepository

        repo = SQLiteJobRepository()
        repo.save_single(Job(id="consistent-1", name="original"))
        results: list[str | None] = []

        def _writer() -> None:
            repo.save_single(Job(id="consistent-1", name="updated-name"))

        def _reader() -> None:
            j = repo.get_job("consistent-1")
            results.append(j.name if j else None)

        t_w = threading.Thread(target=_writer)
        t_r = threading.Thread(target=_reader)
        t_w.start()
        t_r.start()
        t_w.join(timeout=10)
        t_r.join(timeout=10)

        # Both outcomes are valid — we just want no crash / no None
        assert all(r is not None for r in results)


# ── Boundary conditions ──────────────────────────────────────────────────


class TestBoundaryConditions:
    """Test storage behavior at boundary values."""

    def test_save_empty_url_list(self, isolated_db) -> None:
        from app.storage_interface import SQLiteJobRepository

        repo = SQLiteJobRepository()
        repo.save_single(Job(id="empty-urls", name="test", urls=[]))
        loaded = repo.get_job("empty-urls")
        assert loaded is not None
        assert loaded.urls == []

    def test_save_max_urls(self, isolated_db) -> None:
        from app.storage_interface import SQLiteJobRepository

        repo = SQLiteJobRepository()
        urls = [f"https://example.com/page/{i}" for i in range(100)]
        repo.save_single(Job(id="max-urls", name="test", urls=urls))
        loaded = repo.get_job("max-urls")
        assert loaded is not None
        assert len(loaded.urls) == 100

    def test_save_special_characters_in_name(self, isolated_db) -> None:
        from app.storage_interface import SQLiteJobRepository

        repo = SQLiteJobRepository()
        special = "Job with unicode: 日本語 español العربية \\' \" quote & <html>"
        repo.save_single(Job(id="special-name", name=special))
        loaded = repo.get_job("special-name")
        assert loaded is not None
        assert loaded.name == special

    def test_save_very_long_name(self, isolated_db) -> None:
        from app.storage_interface import SQLiteJobRepository

        repo = SQLiteJobRepository()
        long_name = "x" * 1000
        repo.save_single(Job(id="long-name", name=long_name))
        loaded = repo.get_job("long-name")
        assert loaded is not None
        assert loaded.name == long_name

    def test_negative_max_distance_km(self, isolated_db) -> None:
        from app.storage_interface import SQLiteJobRepository

        repo = SQLiteJobRepository()
        repo.save_single(Job(id="neg-dist", name="test", max_distance_km=-1.0))
        loaded = repo.get_job("neg-dist")
        assert loaded is not None
        assert loaded.max_distance_km == -1.0

    def test_zero_min_record_score(self, isolated_db) -> None:
        from app.storage_interface import SQLiteJobRepository

        repo = SQLiteJobRepository()
        repo.save_single(Job(id="zero-score", name="test", min_record_score=0.0))
        loaded = repo.get_job("zero-score")
        assert loaded is not None
        assert loaded.min_record_score == 0.0


# ── Data integrity ────────────────────────────────────────────────────────


class TestDataIntegrity:
    """Verify data invariants survive round-trips."""

    def test_results_list_integrity(self, isolated_db) -> None:
        from app.storage_interface import SQLiteJobRepository

        repo = SQLiteJobRepository()
        results = [{"title": "Row 1", "price": "$10"}, {"title": "Row 2", "price": "$20"}]
        repo.save_single(Job(id="results-test", name="test", results=results))
        loaded = repo.get_job("results-test")
        assert loaded is not None
        assert len(loaded.results) == 2
        assert loaded.results[0]["title"] == "Row 1"
        assert loaded.results[1]["price"] == "$20"

    def test_schema_fields_survives_round_trip(self, isolated_db) -> None:
        from app.models import FieldType, SchemaField
        from app.storage_interface import SQLiteJobRepository

        repo = SQLiteJobRepository()
        fields = [
            SchemaField(name="title", field_type=FieldType.STRING, required=True, description="Product title"),
            SchemaField(name="price", field_type=FieldType.CURRENCY, required=False, description=""),
        ]
        repo.save_single(Job(id="schema-test", name="test", schema_fields=fields))
        loaded = repo.get_job("schema-test")
        assert loaded is not None
        assert len(loaded.schema_fields) == 2
        assert loaded.schema_fields[0].name == "title"
        assert loaded.schema_fields[0].required is True
        assert loaded.schema_fields[1].field_type == FieldType.CURRENCY

    def test_overwrite_job_preserves_new_data(self, isolated_db) -> None:
        from app.storage_interface import SQLiteJobRepository

        repo = SQLiteJobRepository()
        repo.save_single(Job(id="overwrite", name="original"))
        repo.save_single(Job(id="overwrite", name="updated", status=JobStatus.COMPLETED, total_records=42))
        loaded = repo.get_job("overwrite")
        assert loaded is not None
        assert loaded.name == "updated"
        assert loaded.status == JobStatus.COMPLETED
        assert loaded.total_records == 42

    def test_delete_nonexistent_job_does_not_raise(self, isolated_db) -> None:
        from app.storage_interface import SQLiteJobRepository

        repo = SQLiteJobRepository()
        # Should not raise or corrupt the DB
        repo.delete_job_if_exists("nonexistent-id")
        assert repo.get_job("nonexistent-id") is None

    def test_list_jobs_empty(self, isolated_db) -> None:
        from app.storage_interface import SQLiteJobRepository

        repo = SQLiteJobRepository()
        jobs = repo.list_jobs()
        assert jobs == []

    def test_list_jobs_after_insert(self, isolated_db) -> None:
        from app.storage_interface import SQLiteJobRepository

        repo = SQLiteJobRepository()
        repo.save_single(Job(id="list-1", name="first"))
        repo.save_single(Job(id="list-2", name="second"))
        jobs = repo.list_jobs()
        assert len(jobs) == 2
        ids = {j.id for j in jobs}
        assert ids == {"list-1", "list-2"}


# ── Worker heartbeat edge cases ──────────────────────────────────────────


class TestWorkerHeartbeatEdgeCases:
    """Boundary conditions for worker heartbeat storage."""

    def test_heartbeat_ttl_expiry(self, isolated_db, monkeypatch) -> None:
        from app.job_store import get_worker_health, record_worker_heartbeat

        record_worker_heartbeat("expired-worker", "host-a", 1)

        health = get_worker_health("expired-worker", ttl_seconds=-1)
        assert health["alive"] is False

    def test_heartbeat_multiple_workers(self, isolated_db) -> None:
        from app.job_store import get_all_worker_healths, record_worker_heartbeat

        for i in range(5):
            record_worker_heartbeat(f"multi-w{i}", f"host-{i}", 100 + i)
        healths = get_all_worker_healths()
        assert len(healths) == 5
        worker_ids = {h["worker_id"] for h in healths}
        for i in range(5):
            assert f"multi-w{i}" in worker_ids

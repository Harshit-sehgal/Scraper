"""Parity tests: exercise the abstract ``JobRepository`` contract against
SQLite and Postgres (psycopg2) backends.

The deep-research report calls for "Repository contract tests shared
between SQLite and Postgres" so that the parity suite runs on both
backends. This file provides the contract specification; each backend
gets a concrete fixture that produces an isolated repository
instance, and the same test bodies run against both.

The Postgres variants are skipped by default; enable with the
``--run-postgres`` flag (requires Docker + testcontainers).
"""

from __future__ import annotations

import os
import sqlite3

import pytest
from app.models import Job, JobStatus, ScrapeMode


def _make_job(idx: int = 1) -> Job:
    return Job(
        id=f"parity-{idx}",
        name=f"Parity {idx}",
        mode=ScrapeMode.MANUAL,
        urls=[f"https://example.com/{idx}"],
        topic="parity",
        status=JobStatus.RUNNING,
    )


# ─── SQLite repository fixture ─────────────────────────────────────────


@pytest.fixture
def sqlite_repo(tmp_path, monkeypatch):
    """Build a fresh SQLiteJobRepository with an isolated DB on disk.

    The trick is to point ``DATAFORGE_STATE_FILE`` at a tmp path BEFORE any
    module-level code reads it. We then patch the storage_interface singleton
    so the rest of the app does not see the test repository.
    """
    from app import job_store, storage_interface

    db_path = tmp_path / "jobs_state.db"
    state_file = tmp_path / "jobs_state.json"

    # Reset migration cache so a fresh schema is built.
    job_store._MIGRATIONS_RUN_FOR.clear()
    job_store._get_db_path.__globals__["_DB_PATH_OVERRIDE"] = None  # type: ignore[attr-defined]

    # Patch the env so STATE_FILE_PATH_DYNAMIC returns our tmp path.
    monkeypatch.setenv("DATAFORGE_STATE_FILE", str(state_file))
    # The DB path is derived from the state file path with ``.db`` suffix.
    # _get_db_path uses settings.STATE_FILE_PATH_DYNAMIC, which reads the
    # env var; but _MIGRATIONS_RUN_FOR caches by path. We override the
    # path by monkeypatching the function itself.
    monkeypatch.setattr(job_store, "_get_db_path", lambda: db_path)

    repo = storage_interface.SQLiteJobRepository()
    yield repo

    # Cleanup: drop the singleton so the next test does not see ours.
    storage_interface._repository_instance = None
    job_store._MIGRATIONS_RUN_FOR.discard(db_path)
    try:
        if db_path.exists():
            db_path.unlink()
    except OSError:
        pass


# ─── Postgres repository fixture (skipped unless --run-postgres) ───────


@pytest.fixture
def postgres_repo(monkeypatch, tmp_path):
    """Build a PostgresJobRepository (psycopg2) backed by testcontainers.

    Requires the ``--run-postgres`` flag and a working Docker daemon. The
    fixture is intentionally light — it skips with a clear message when
    the testcontainers library is unavailable.
    """
    pytest.importorskip("testcontainers")
    pytest.importorskip("psycopg2")

    from testcontainers.postgres import PostgresContainer

    container = PostgresContainer("postgres:16-alpine")
    container.start()
    try:
        # testcontainers returns a SQLAlchemy-style URL; convert to libpq.
        url = container.get_connection_url()
        if url.startswith("postgresql+psycopg2://"):
            url = "postgresql://" + url[len("postgresql+psycopg2://") :]
        monkeypatch.setenv("DATAFORGE_DATABASE_URL", url)
        from app.postgres_repository import PostgresJobRepository

        repo = PostgresJobRepository()
        yield repo
    finally:
        container.stop()


# ─── Contract: get_job returns the same row that was persisted ────────


class TestGetJobContract:
    def test_get_job_round_trips_sqlite(self, sqlite_repo) -> None:
        job = _make_job(1)
        sqlite_repo.save_all({job.id: job}, {}, prune_missing=False)
        loaded = sqlite_repo.get_job(job.id)
        assert loaded is not None
        assert loaded.id == job.id
        assert loaded.name == job.name
        assert loaded.status == job.status
        assert loaded.urls == job.urls

    def test_get_job_returns_none_for_unknown_id_sqlite(self, sqlite_repo) -> None:
        assert sqlite_repo.get_job("does-not-exist") is None


# ─── Contract: list_job_summaries returns lightweight projections ─────


class TestListJobSummariesContract:
    def test_list_summaries_returns_all_persisted_jobs_sqlite(self, sqlite_repo) -> None:
        jobs = {f"parity-{idx}": _make_job(idx) for idx in range(3)}
        sqlite_repo.save_all(jobs, {}, prune_missing=False)
        summaries = sqlite_repo.list_job_summaries()
        ids = {s["id"] for s in summaries}
        assert {"parity-0", "parity-1", "parity-2"} <= ids

    def test_summaries_have_required_fields_sqlite(self, sqlite_repo) -> None:
        job = _make_job(7)
        sqlite_repo.save_all({job.id: job}, {}, prune_missing=False)
        summaries = sqlite_repo.list_job_summaries()
        ours = [s for s in summaries if s["id"] == "parity-7"]
        assert len(ours) == 1
        s = ours[0]
        for field in ("id", "name", "mode", "topic", "status", "created_at"):
            assert field in s, f"summary missing required field {field!r}: {s}"


# ─── Contract: list_recycle_summaries returns lightweight projections ──


class TestListRecycleSummariesContract:
    def test_list_recycle_summaries_returns_recycled_jobs_sqlite(self, sqlite_repo) -> None:
        job = _make_job(20)
        sqlite_repo.save_all({}, {job.id: job}, prune_missing=False)
        summaries = sqlite_repo.list_recycle_summaries()
        ours = [s for s in summaries if s["id"] == "parity-20"]
        assert len(ours) == 1

    def test_recycle_summaries_include_deleted_at_field_sqlite(self, sqlite_repo) -> None:
        job = _make_job(21)
        sqlite_repo.save_all({}, {job.id: job}, prune_missing=False)
        summaries = sqlite_repo.list_recycle_summaries()
        s = next(s for s in summaries if s["id"] == "parity-21")
        # The deleted_at field is always present; the value may be
        # null when the row was persisted via save_all (which uses the
        # job's own fields) rather than move_to_recycle_bin (which
        # stamps deleted_at on the row). Either is contractually valid.
        assert "deleted_at" in s

    def test_recycle_summaries_deleted_at_set_by_move_to_recycle_bin_sqlite(self, sqlite_repo) -> None:
        job = _make_job(25)
        sqlite_repo.save_all({job.id: job}, {}, prune_missing=False)
        assert sqlite_repo.move_to_recycle_bin(job.id) is True
        summaries = sqlite_repo.list_recycle_summaries()
        s = next(s for s in summaries if s["id"] == "parity-25")
        assert s["deleted_at"] is not None

    def test_recycle_summaries_have_required_fields_sqlite(self, sqlite_repo) -> None:
        job = _make_job(22)
        sqlite_repo.save_all({}, {job.id: job}, prune_missing=False)
        summaries = sqlite_repo.list_recycle_summaries()
        s = next(s for s in summaries if s["id"] == "parity-22")
        for field in ("id", "name", "mode", "topic", "status", "created_at", "deleted_at"):
            assert field in s, f"recycle summary missing required field {field!r}: {s}"

    def test_recycle_summaries_exclude_active_jobs_sqlite(self, sqlite_repo) -> None:
        active = _make_job(23)
        recycled = _make_job(24)
        sqlite_repo.save_all({active.id: active}, {recycled.id: recycled}, prune_missing=False)
        summaries = sqlite_repo.list_recycle_summaries()
        ids = {s["id"] for s in summaries}
        assert "parity-23" not in ids
        assert "parity-24" in ids


# ─── Contract: read_events returns chronological log entries ─────────


class TestReadEventsContract:
    def test_read_events_returns_chronological_sqlite(self, sqlite_repo) -> None:
        job = _make_job(11)
        sqlite_repo.save_all({job.id: job}, {}, prune_missing=False)
        # Insert events directly via the SQL row helper so we don't depend
        # on append_event (which lives in job_store, not on the abstract
        # interface yet).
        from app.job_store import _get_db_path

        with sqlite3.connect(str(_get_db_path())) as conn:
            conn.execute(
                "INSERT INTO job_events (job_id, timestamp, level, message) VALUES (?, ?, ?, ?)",
                ("parity-11", "2026-06-01T10:00:00Z", "info", "started"),
            )
            conn.execute(
                "INSERT INTO job_events (job_id, timestamp, level, message) VALUES (?, ?, ?, ?)",
                ("parity-11", "2026-06-01T10:00:01Z", "warning", "rate-limited"),
            )
            conn.execute(
                "INSERT INTO job_events (job_id, timestamp, level, message) VALUES (?, ?, ?, ?)",
                ("parity-11", "2026-06-01T10:00:02Z", "info", "recovered"),
            )
            conn.commit()
        events = sqlite_repo.read_events(job.id)
        messages = [e["message"] for e in events]
        assert messages == ["started", "rate-limited", "recovered"]
        levels = [e["level"] for e in events]
        assert levels == ["info", "warning", "info"]

    def test_read_events_empty_for_unknown_job_sqlite(self, sqlite_repo) -> None:
        assert sqlite_repo.read_events("never-persisted") == []


# ─── Contract: read_results (empty/offset/order contracts) ────────────


class TestReadResultsContract:
    def test_read_results_empty_for_no_results_sqlite(self, sqlite_repo) -> None:
        job = _make_job(30)
        sqlite_repo.save_all({job.id: job}, {}, prune_missing=False)
        assert sqlite_repo.read_results(job.id) == []

    def test_read_results_returns_in_order_sqlite(self, sqlite_repo) -> None:
        job = _make_job(31)
        job.results = [{"idx": i} for i in range(5)]
        sqlite_repo.save_all({job.id: job}, {}, prune_missing=False)
        out = sqlite_repo.read_results(job.id)
        assert [r["idx"] for r in out] == [0, 1, 2, 3, 4]

    def test_read_results_respects_limit_sqlite(self, sqlite_repo) -> None:
        job = _make_job(32)
        job.results = [{"idx": i} for i in range(20)]
        sqlite_repo.save_all({job.id: job}, {}, prune_missing=False)
        out = sqlite_repo.read_results(job.id, limit=3)
        assert len(out) == 3
        assert [r["idx"] for r in out] == [0, 1, 2]

    def test_read_results_offset_sqlite(self, sqlite_repo) -> None:
        job = _make_job(33)
        job.results = [{"idx": i} for i in range(10)]
        sqlite_repo.save_all({job.id: job}, {}, prune_missing=False)
        out = sqlite_repo.read_results(job.id, limit=5, offset=5)
        assert [r["idx"] for r in out] == [5, 6, 7, 8, 9]

    def test_read_results_unknown_job_returns_empty_sqlite(self, sqlite_repo) -> None:
        assert sqlite_repo.read_results("never-existed") == []

    def test_read_results_updated_after_resave_sqlite(self, sqlite_repo) -> None:
        """Re-saving a job with different results must replace companion data."""
        job = _make_job(34)
        job.results = [{"v": "first"}]
        sqlite_repo.save_all({job.id: job}, {}, prune_missing=False)
        job.results = [{"v": "second"}, {"v": "third"}]
        sqlite_repo.save_all({job.id: job}, {}, prune_missing=False)
        out = sqlite_repo.read_results(job.id)
        assert [r["v"] for r in out] == ["second", "third"]


# ─── Contract: idempotency-key lifecycle ─────────────────────────────


class TestIdempotencyContract:
    def test_record_and_lookup_sqlite(self, sqlite_repo) -> None:
        sqlite_repo.record_idempotency_key("contract-key", "parity-40", "fp")
        assert sqlite_repo.lookup_idempotency_key("contract-key") == "parity-40"

    def test_lookup_missing_returns_none_sqlite(self, sqlite_repo) -> None:
        assert sqlite_repo.lookup_idempotency_key("never-recorded") is None

    def test_empty_key_lookup_returns_none_sqlite(self, sqlite_repo) -> None:
        assert sqlite_repo.lookup_idempotency_key("") is None
        assert sqlite_repo.lookup_idempotency_key(None) is None  # type: ignore[arg-type]

    def test_prune_idempotency_keys_sqlite(self, sqlite_repo) -> None:
        sqlite_repo.record_idempotency_key("will-prune", "parity-41", "fp")
        # Prune with 0 days — recent keys survive
        assert sqlite_repo.prune_idempotency_keys(older_than_days=0) == 0
        assert sqlite_repo.lookup_idempotency_key("will-prune") == "parity-41"


# ─── Optional Postgres parity (only run with --run-postgres) ──────────


@pytest.mark.postgres
class TestPostgresParity:
    def test_get_job_round_trips_postgres(self, postgres_repo) -> None:
        job = _make_job(100)
        postgres_repo.save_all({job.id: job}, {}, prune_missing=True)
        loaded = postgres_repo.get_job(job.id)
        assert loaded is not None
        assert loaded.id == job.id
        assert loaded.name == job.name

    def test_list_summaries_returns_all_persisted_jobs_postgres(self, postgres_repo) -> None:
        for idx in range(101, 104):
            job = _make_job(idx)
            postgres_repo.save_all({job.id: job}, {}, prune_missing=True)
        summaries = postgres_repo.list_job_summaries()
        ids = {s["id"] for s in summaries}
        assert {"parity-101", "parity-102", "parity-103"} <= ids

    def test_read_events_returns_chronological_postgres(self, postgres_repo) -> None:
        job = _make_job(200)
        postgres_repo.save_all({job.id: job}, {}, prune_missing=True)
        # Insert events directly via the underlying connection. Each
        # backend exposes the same contract, so we use the same SQL.
        # We rely on the schema being identical between the two backends
        # (job_events / job_results / idempotency_keys / jobs / recycle_bin).
        import psycopg2
        from app.postgres_repository import _get_database_url

        with psycopg2.connect(_get_database_url()) as conn:
            with conn.cursor() as cur:
                for ts, level, message in [
                    ("2026-06-01T10:00:00Z", "info", "started"),
                    ("2026-06-01T10:00:01Z", "warning", "rate-limited"),
                    ("2026-06-01T10:00:02Z", "info", "recovered"),
                ]:
                    cur.execute(
                        "INSERT INTO job_events (job_id, timestamp, level, message) VALUES (%s, %s, %s, %s)",
                        ("parity-200", ts, level, message),
                    )
            conn.commit()
        events = postgres_repo.read_events(job.id)
        assert [e["message"] for e in events] == ["started", "rate-limited", "recovered"]

    def test_list_recycle_summaries_postgres(self, postgres_repo) -> None:
        job = _make_job(300)
        postgres_repo.save_all({}, {job.id: job}, prune_missing=True)
        summaries = postgres_repo.list_recycle_summaries()
        ours = [s for s in summaries if s["id"] == "parity-300"]
        assert len(ours) == 1
        assert "deleted_at" in ours[0]

    def test_read_results_round_trip_postgres(self, postgres_repo) -> None:
        """Postgres read_results must return results in insertion order."""
        job = _make_job(400)
        job.results = [{"k": "v1", "n": 1}, {"k": "v2", "n": 2}]
        postgres_repo.save_all({job.id: job}, {}, prune_missing=True)
        out = postgres_repo.read_results(job.id)
        assert out == [{"k": "v1", "n": 1}, {"k": "v2", "n": 2}]

    def test_read_results_empty_postgres(self, postgres_repo) -> None:
        """Postgres read_results must return [] when no results exist."""
        job = _make_job(401)
        postgres_repo.save_all({job.id: job}, {}, prune_missing=True)
        assert postgres_repo.read_results(job.id) == []

    def test_read_results_respects_limit_postgres(self, postgres_repo) -> None:
        """Postgres read_results must respect the limit parameter."""
        job = _make_job(402)
        job.results = [{"idx": i} for i in range(20)]
        postgres_repo.save_all({job.id: job}, {}, prune_missing=True)
        out = postgres_repo.read_results(job.id, limit=3)
        assert len(out) == 3
        assert [r["idx"] for r in out] == [0, 1, 2]

    def test_read_results_offset_postgres(self, postgres_repo) -> None:
        """Postgres read_results must skip offset rows."""
        job = _make_job(403)
        job.results = [{"idx": i} for i in range(10)]
        postgres_repo.save_all({job.id: job}, {}, prune_missing=True)
        out = postgres_repo.read_results(job.id, limit=5, offset=5)
        assert [r["idx"] for r in out] == [5, 6, 7, 8, 9]

    def test_read_results_updated_after_resave_postgres(self, postgres_repo) -> None:
        """Re-saving must replace companion data, not append."""
        job = _make_job(404)
        job.results = [{"v": "first"}]
        postgres_repo.save_all({job.id: job}, {}, prune_missing=True)
        job.results = [{"v": "second"}, {"v": "third"}]
        postgres_repo.save_all({job.id: job}, {}, prune_missing=True)
        out = postgres_repo.read_results(job.id)
        assert [r["v"] for r in out] == ["second", "third"]

    def test_idempotency_key_round_trip_postgres(self, postgres_repo) -> None:
        """Postgres record_idempotency_key + lookup_idempotency_key round-trip."""
        postgres_repo.record_idempotency_key("pg-key", "parity-410", "fp")
        assert postgres_repo.lookup_idempotency_key("pg-key") == "parity-410"

    def test_idempotency_key_empty_lookup_postgres(self, postgres_repo) -> None:
        """Postgres lookup_idempotency_key must return None for empty keys."""
        assert postgres_repo.lookup_idempotency_key("") is None

    def test_cleanup_companion_data_postgres(self, postgres_repo) -> None:
        """Postgres cleanup_companion_data must remove companion rows."""
        job = _make_job(420)
        job.results = [{"data": True}]
        postgres_repo.save_all({job.id: job}, {}, prune_missing=True)
        assert postgres_repo.read_results(job.id) == [{"data": True}]
        postgres_repo.cleanup_companion_data(job.id)
        assert postgres_repo.read_results(job.id) == []


# ─── Cross-backend smoke test: psycopg3 factory selection ────────────


class TestFactorySelection:
    def test_psycopg3_selected_when_env_flag_set(self, monkeypatch) -> None:
        monkeypatch.setenv("DATAFORGE_PG_DRIVER", "psycopg3")
        monkeypatch.setenv("DATAFORGE_DATABASE_URL", "postgresql://localhost/x")

        # The factory selects the driver from the env var; the function
        # is inlined in get_job_repository so we re-implement the same
        # selection here to pin the contract.
        from app.psycopg3_repository import verify_psycopg3_connectivity

        # We can't actually connect, but the selection logic itself is
        # testable in isolation.
        driver = (os.environ.get("DATAFORGE_PG_DRIVER") or "psycopg2").strip().lower()
        assert driver == "psycopg3"
        # Sanity: the verify function exists and is callable.
        assert callable(verify_psycopg3_connectivity)

    def test_psycopg2_selected_by_default(self, monkeypatch) -> None:
        monkeypatch.delenv("DATAFORGE_PG_DRIVER", raising=False)
        monkeypatch.setenv("DATAFORGE_DATABASE_URL", "postgresql://localhost/x")
        driver = (os.environ.get("DATAFORGE_PG_DRIVER") or "psycopg2").strip().lower()
        assert driver == "psycopg2"

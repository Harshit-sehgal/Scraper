"""Unit tests for app.storage_interface — ABC contract, resolver factory, and
default method behaviour.

These tests exercise the abstract interface without requiring SQLite or
Postgres connections, using a minimal concrete stub so we can verify:
- Abstract methods are enforced
- Default implementations raise NotImplementedError
- get_job_repository() resolves to SQLite when postgres is unavailable
- reset_repository() clears the cached singleton
- prune_idempotency_keys() returns 0 by default
- health_check() returns the expected shape
- is_cancel_requested() returns False by default
- load_world_state()/save_world_state() defaults are safe no-ops
"""

from __future__ import annotations

import pytest
from app.models import Job
from app.storage_interface import JobRepository


class _StubRepo(JobRepository):
    """Minimal concrete subclass of JobRepository for contract testing.

    Implements only the @abstractmethod definitions so we can test the
    non-abstract defaults in isolation.
    """

    def __init__(self):
        super().__init__()
        self._jobs: dict = {}
        self._recycle: dict = {}
        self._world: dict | None = None

    # ── Abstract method implementations ────────────────────────────────

    def load_jobs(self) -> dict[str, Job]:
        return dict(self._jobs)

    def load_recycle_bin(self) -> dict[str, Job]:
        return dict(self._recycle)

    def get_job(self, job_id: str):
        return self._jobs.get(job_id)

    def list_job_summaries(self, limit=100, cursor=None):
        return []

    def list_recycle_summaries(self, limit=100, cursor=None):
        return []

    def load_all(self, recover_in_progress=True):
        return dict(self._jobs), dict(self._recycle), self._world

    def save_all(self, jobs, recycle_bin, prune_missing=False):
        self._jobs = dict(jobs)
        self._recycle = dict(recycle_bin)

    def read_events(self, job_id, limit=200, offset=0, level_prefix=None):
        return []

    def read_results(self, job_id, limit=100, offset=0):
        return []

    def save_single(self, job):
        pass

    def lookup_idempotency_key(self, idem_key):
        return None

    def lookup_idempotency_fingerprint(self, idem_key):
        return None

    def record_idempotency_key(self, idem_key, job_id, request_fingerprint):
        pass

    def get_storage_status(self):
        return {"backend": "stub", "ok": True}


# ─── ABC enforcement ───────────────────────────────────────────────────


class TestJobRepositoryABCEnforcement:
    def test_cannot_instantiate_abstract_class(self) -> None:
        with pytest.raises(TypeError, match="abstract"):
            JobRepository()  # type: ignore[abstract]

    def test_stub_is_subclass(self) -> None:
        assert issubclass(_StubRepo, JobRepository)


# ─── Default method behaviour ─────────────────────────────────────────


class TestDefaultMethodBehaviour:
    def test_count_jobs_by_status_raises(self) -> None:
        repo = _StubRepo()
        with pytest.raises(NotImplementedError, match="count_jobs_by_status"):
            repo.count_jobs_by_status()

    def test_count_results_raises(self) -> None:
        repo = _StubRepo()
        with pytest.raises(NotImplementedError, match="count_results"):
            repo.count_results("job-id")

    def test_record_worker_heartbeat_raises(self) -> None:
        repo = _StubRepo()
        with pytest.raises(NotImplementedError, match="record_worker_heartbeat"):
            repo.record_worker_heartbeat("worker-1", "host", 1234)

    def test_get_worker_health_raises(self) -> None:
        repo = _StubRepo()
        with pytest.raises(NotImplementedError, match="get_worker_health"):
            repo.get_worker_health("worker-1")

    def test_get_all_worker_healths_raises(self) -> None:
        repo = _StubRepo()
        with pytest.raises(NotImplementedError, match="get_all_worker_healths"):
            repo.get_all_worker_healths()

    def test_prune_idempotency_keys_returns_zero(self) -> None:
        repo = _StubRepo()
        assert repo.prune_idempotency_keys(older_than_days=1) == 0

    def test_health_check_returns_ok(self) -> None:
        repo = _StubRepo()
        result = repo.health_check()
        assert result["ok"] is True
        assert result["backend"] == "_StubRepo"

    def test_is_cancel_requested_defaults_false(self) -> None:
        repo = _StubRepo()
        assert repo.is_cancel_requested("any-id") is False

    def test_move_to_recycle_bin_raises(self) -> None:
        repo = _StubRepo()
        with pytest.raises(NotImplementedError, match="move_to_recycle_bin"):
            repo.move_to_recycle_bin("job-id")

    def test_restore_from_recycle_bin_raises(self) -> None:
        repo = _StubRepo()
        with pytest.raises(NotImplementedError, match="restore_from_recycle_bin"):
            repo.restore_from_recycle_bin("job-id")

    def test_hard_delete_raises(self) -> None:
        repo = _StubRepo()
        with pytest.raises(NotImplementedError, match="hard_delete"):
            repo.hard_delete("job-id")

    def test_clear_terminal_jobs_raises(self) -> None:
        repo = _StubRepo()
        with pytest.raises(NotImplementedError, match="clear_terminal_jobs"):
            repo.clear_terminal_jobs()

    def test_cleanup_companion_data_is_noop(self) -> None:
        repo = _StubRepo()
        # Should not raise — default is a no-op
        repo.cleanup_companion_data("job-id")

    def test_load_world_state_returns_none(self) -> None:
        repo = _StubRepo()
        assert repo.load_world_state() is None

    def test_save_world_state_is_noop(self) -> None:
        repo = _StubRepo()
        # Should not raise — default is a no-op
        repo.save_world_state({"key": "value"})


# ─── Repository resolver factory ───────────────────────────────────────


class TestGetJobRepository:
    def test_resolves_sqlite_by_default(self, monkeypatch, tmp_path) -> None:
        from app.storage_interface import get_job_repository, reset_repository

        # Ensure clean state
        reset_repository()
        monkeypatch.setenv("DATAFORGE_STORAGE_BACKEND", "sqlite")
        monkeypatch.setenv("DATAFORGE_STATE_FILE_PATH_DYNAMIC", str(tmp_path / "test.db"))

        repo = get_job_repository()
        try:
            from app.storage_interface import SQLiteJobRepository

            assert isinstance(repo, SQLiteJobRepository)
        finally:
            reset_repository()
            monkeypatch.delenv("DATAFORGE_STORAGE_BACKEND", raising=False)

    def test_postgres_without_url_raises(self, monkeypatch) -> None:
        from app.storage_interface import get_job_repository, reset_repository

        reset_repository()
        monkeypatch.setenv("DATAFORGE_STORAGE_BACKEND", "postgres")
        monkeypatch.delenv("DATAFORGE_DATABASE_URL", raising=False)

        with pytest.raises(RuntimeError, match="DATAFORGE_DATABASE_URL"):
            get_job_repository()

        reset_repository()
        monkeypatch.delenv("DATAFORGE_STORAGE_BACKEND", raising=False)

    def test_cached_singleton_returned(self, monkeypatch, tmp_path) -> None:
        from app.storage_interface import get_job_repository, reset_repository

        reset_repository()
        monkeypatch.setenv("DATAFORGE_STORAGE_BACKEND", "sqlite")
        monkeypatch.setenv("DATAFORGE_STATE_FILE_PATH_DYNAMIC", str(tmp_path / "test2.db"))

        repo1 = get_job_repository()
        repo2 = get_job_repository()
        assert repo1 is repo2

        reset_repository()
        monkeypatch.delenv("DATAFORGE_STORAGE_BACKEND", raising=False)

    def test_reset_clears_singleton(self, monkeypatch, tmp_path) -> None:
        from app.storage_interface import get_job_repository, reset_repository

        reset_repository()
        monkeypatch.setenv("DATAFORGE_STORAGE_BACKEND", "sqlite")
        monkeypatch.setenv("DATAFORGE_STATE_FILE_PATH_DYNAMIC", str(tmp_path / "test3.db"))

        repo1 = get_job_repository()
        reset_repository()
        monkeypatch.setenv("DATAFORGE_STATE_FILE_PATH_DYNAMIC", str(tmp_path / "test4.db"))
        repo2 = get_job_repository()
        # After reset, a new instance is created
        assert repo1 is not repo2

        reset_repository()
        monkeypatch.delenv("DATAFORGE_STORAGE_BACKEND", raising=False)


# ─── _JOBS_COLUMNS_SQL ─────────────────────────────────────────────────


class TestJobsColumnsSQL:
    def test_column_list_is_not_empty(self) -> None:
        from app.storage_interface import _JOBS_COLUMNS_SQL

        assert len(_JOBS_COLUMNS_SQL) > 0

    def test_every_column_has_type(self) -> None:
        """Each entry should look like 'name TYPE ...'."""
        from app.storage_interface import _JOBS_COLUMNS_SQL

        for col in _JOBS_COLUMNS_SQL:
            parts = col.split()
            assert len(parts) >= 2, f"Column def too short: {col!r}"
            # First token is the column name, second is the SQL type
            assert parts[1].upper() in {
                "TEXT",
                "INTEGER",
                "REAL",
                "BOOLEAN",
                "BLOB",
            }, f"Unexpected type in: {col!r}"

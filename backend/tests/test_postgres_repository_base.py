"""Structural unit tests for PostgresRepositoryBase.

Tests module-level helpers, driver-function wiring, validation,
companion-table sync, and base-class CRUD methods using mocked
connections — no Postgres server required.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from app.models import Job, JobStatus
from app.postgres_repository_base import PostgresRepositoryBase

# ─── Helpers ───────────────────────────────────────────────────────────


def _fake_job(id_: str = "j1", status: JobStatus = JobStatus.COMPLETED, **overrides) -> Job:
    """Build a minimal Job for testing."""
    defaults: dict[str, Any] = {
        "id": id_,
        "name": f"job-{id_}",
        "status": status,
        "urls": ["https://test.invalid"],
        "completed_at": "2026-01-01T00:00:00+00:00",
        "results": [{"title": "result-1"}],
    }
    defaults.update(overrides)
    return Job(**defaults)


def _row_from_job(job: Job) -> dict[str, Any]:
    """Use canonical mapper to get a row dict from a Job."""
    from app.storage_mapper import job_to_row

    return job_to_row(job)


class _StubRepo(PostgresRepositoryBase):
    """Minimal concrete subclass of PostgresRepositoryBase.

    Provides mock implementations of the four abstract methods so we can
    test the shared logic without a real database.
    """

    def __init__(self, *, auto_ensure: bool = True) -> None:
        super().__init__(auto_ensure_schema=auto_ensure)
        self._schema_ensured = True  # skip real schema migration

        # Configurable mock connection + cursor
        self._mock_cursor = MagicMock()
        self._mock_cursor.rowcount = 0
        self._mock_conn = MagicMock()
        self._mock_conn.cursor.return_value = self._mock_cursor

        # Recorded SQL/params for assertions
        self.executed: list[tuple[str, Any]] = []
        self._fetch_all_impl: MagicMock = MagicMock(return_value=[])
        self._fetch_one_impl: MagicMock = MagicMock(return_value=None)
        self._execute_impl: MagicMock = MagicMock(side_effect=self._record_execute)

    @contextmanager
    def _conn(self):
        yield self._mock_conn

    def _record_execute(self, conn: Any, sql: str, params: Any = None) -> MagicMock:
        self.executed.append((sql, params))
        return self._mock_cursor

    # Override abstract methods to delegate to our impls
    def _fetch_all(self, conn: Any, sql: str, params: Any = None) -> list[dict[str, Any]]:
        return self._fetch_all_impl(conn, sql, params)

    def _fetch_one(self, conn: Any, sql: str, params: Any = None) -> dict[str, Any] | None:
        return self._fetch_one_impl(conn, sql, params)

    def _execute(self, conn: Any, sql: str, params: Any = None) -> Any:
        return self._execute_impl(conn, sql, params)


# ─── Module-level helpers ───────────────────────────────────────────────


class TestValidateCols:
    """``_validate_cols`` validates column names against known schema."""

    def test_valid_columns_joined(self) -> None:
        from app.postgres_repository_base import _validate_cols

        result = _validate_cols(["id", "name", "status"])
        assert result == "id, name, status"

    def test_unknown_column_raises_value_error(self) -> None:
        from app.postgres_repository_base import _validate_cols

        with pytest.raises(ValueError, match="Unknown column"):
            _validate_cols(["id", "nonexistent_col"])

    def test_empty_list_returns_empty_string(self) -> None:
        from app.postgres_repository_base import _validate_cols

        result = _validate_cols([])
        assert result == ""


class TestJobColumns:
    """``_JOB_COLUMNS`` frozenset contains expected keys."""

    def test_required_columns_present(self) -> None:
        from app.postgres_repository_base import _JOB_COLUMNS

        for col in ("id", "name", "status", "created_by", "org_id", "project_id", "deleted_at"):
            assert col in _JOB_COLUMNS, f"{col!r} missing from _JOB_COLUMNS"

    def test_frozenset_type(self) -> None:
        from app.postgres_repository_base import _JOB_COLUMNS

        assert isinstance(_JOB_COLUMNS, frozenset)


class TestDriverFunctions:
    """Module-level ``_fetch_all``, ``_fetch_one``, ``execute`` require driver init."""

    def test_fetch_all_raises_before_init(self) -> None:
        from app.postgres_repository_base import _set_driver_functions

        _set_driver_functions(None, None, None)
        try:
            from app.postgres_repository_base import _fetch_all

            with pytest.raises(RuntimeError, match="driver not initialised"):
                _fetch_all(MagicMock(), "SELECT 1")
        finally:
            _set_driver_functions(lambda *a: [], lambda *a: None, lambda *a: None)

    def test_fetch_one_raises_before_init(self) -> None:
        from app.postgres_repository_base import _set_driver_functions

        _set_driver_functions(None, None, None)
        try:
            from app.postgres_repository_base import _fetch_one

            with pytest.raises(RuntimeError, match="driver not initialised"):
                _fetch_one(MagicMock(), "SELECT 1")
        finally:
            _set_driver_functions(lambda *a: [], lambda *a: None, lambda *a: None)

    def test_execute_raises_before_init(self) -> None:
        from app.postgres_repository_base import _set_driver_functions

        _set_driver_functions(None, None, None)
        try:
            from app.postgres_repository_base import execute

            with pytest.raises(RuntimeError, match="driver not initialised"):
                execute(MagicMock(), "SELECT 1")
        finally:
            _set_driver_functions(lambda *a: [], lambda *a: None, lambda *a: None)

    def test_set_driver_functions_wires_correctly(self) -> None:
        from app.postgres_repository_base import _set_driver_functions

        mock_fa = MagicMock(return_value=[{"id": 1}])
        mock_fo = MagicMock(return_value={"id": 1})
        mock_ex = MagicMock()
        _set_driver_functions(mock_fa, mock_fo, mock_ex)

        from app.postgres_repository_base import _fetch_all, _fetch_one
        from app.postgres_repository_base import execute as mod_execute

        conn = MagicMock()
        _fetch_all(conn, "SELECT 1", None)
        mock_fa.assert_called_once_with(conn, "SELECT 1", None)

        _fetch_one(conn, "SELECT 2", None)
        mock_fo.assert_called_once_with(conn, "SELECT 2", None)

        mod_execute(conn, "INSERT 1", None)
        mock_ex.assert_called_once_with(conn, "INSERT 1", None)


class TestRegisterDbErrorClass:
    """``register_db_error_class`` adds valid exception types."""

    def test_valid_class_is_registered(self) -> None:
        import app.postgres_repository_base as mod
        from app.postgres_repository_base import register_db_error_class

        original = mod._DB_OPS_ERRORS

        class CustomDBError(Exception):
            pass

        register_db_error_class(CustomDBError)
        try:
            assert CustomDBError in mod._DB_OPS_ERRORS
        finally:
            mod._DB_OPS_ERRORS = original

    def test_non_exception_class_is_ignored(self) -> None:
        import app.postgres_repository_base as mod
        from app.postgres_repository_base import register_db_error_class

        register_db_error_class(str)  # type: ignore[arg-type]  # intentional invalid class
        assert str not in mod._DB_OPS_ERRORS


class TestGetDatabaseUrl:
    """``get_database_url`` resolves DSN from settings or raises RuntimeError."""

    def test_returns_settings_url(self) -> None:
        from app.postgres_repository_base import get_database_url

        mock_settings = MagicMock()
        mock_settings.DATABASE_URL = "postgresql://u:p@h:5432/db"
        with patch("app.config.settings", mock_settings):
            result = get_database_url()
        assert result == "postgresql://u:p@h:5432/db"

    def test_raises_when_url_missing(self) -> None:
        from app.postgres_repository_base import get_database_url

        mock_settings = MagicMock()
        mock_settings.DATABASE_URL = ""
        with patch("app.config.settings", mock_settings):
            with pytest.raises(RuntimeError, match="DATAFORGE_DATABASE_URL"):
                get_database_url()


# ─── Schema SQL builders ────────────────────────────────────────────────


class TestSchemaSQLBuilders:
    """Schema SQL builders produce valid CREATE TABLE statements."""

    def test_build_create_jobs_sql(self) -> None:
        from app.postgres_repository_base import build_create_jobs_sql

        sql = build_create_jobs_sql()
        assert "CREATE TABLE IF NOT EXISTS jobs" in sql
        assert "id TEXT PRIMARY KEY" in sql

    def test_build_create_recycle_bin_sql(self) -> None:
        from app.postgres_repository_base import build_create_recycle_bin_sql

        sql = build_create_recycle_bin_sql()
        assert "CREATE TABLE IF NOT EXISTS recycle_bin" in sql
        assert "id TEXT PRIMARY KEY" in sql


# ─── Companion-table sync ───────────────────────────────────────────────


class TestSyncJobResults:
    """``sync_job_results`` deletes then inserts result rows."""

    def test_deletes_existing_and_inserts_new(self) -> None:
        from app.postgres_repository_base import _set_driver_functions, sync_job_results

        executed_sql: list[str] = []
        mock_execute = lambda conn, sql, params=None: executed_sql.append(sql)  # noqa: E731
        _set_driver_functions(lambda *a: [], lambda *a: None, mock_execute)

        conn = MagicMock()
        sync_job_results(conn, "j1", [{"a": 1}, {"b": 2}])

        assert any("DELETE FROM job_results" in s for s in executed_sql)
        insert_calls = [s for s in executed_sql if "INSERT INTO job_results" in s]
        assert len(insert_calls) == 2

    def test_empty_results_only_deletes(self) -> None:
        from app.postgres_repository_base import _set_driver_functions, sync_job_results

        executed_sql: list[str] = []
        mock_execute = lambda conn, sql, params=None: executed_sql.append(sql)  # noqa: E731
        _set_driver_functions(lambda *a: [], lambda *a: None, mock_execute)

        conn = MagicMock()
        sync_job_results(conn, "j1", [])
        delete_calls = [s for s in executed_sql if "DELETE FROM job_results" in s]
        insert_calls = [s for s in executed_sql if "INSERT INTO job_results" in s]
        assert len(delete_calls) >= 1
        assert len(insert_calls) == 0


class TestSyncJobEvents:
    """``sync_job_events`` handles dict, model_dump, and raw objects."""

    def test_dict_logs_are_inserted(self) -> None:
        from app.postgres_repository_base import _set_driver_functions, sync_job_events

        executed: list[tuple] = []
        mock_execute = lambda conn, sql, params=None: executed.append((sql, params))  # noqa: E731
        _set_driver_functions(lambda *a: [], lambda *a: None, mock_execute)

        conn = MagicMock()
        logs = [{"timestamp": "2026-01-01T00:00:00Z", "level": "info", "message": "test"}]
        sync_job_events(conn, "j1", logs)

        insert_calls = [(s, p) for s, p in executed if "INSERT INTO job_events" in s]
        assert len(insert_calls) == 1

    def test_model_dump_objects(self) -> None:
        from app.postgres_repository_base import _set_driver_functions, sync_job_events

        executed: list[tuple] = []
        mock_execute = lambda conn, sql, params=None: executed.append((sql, params))  # noqa: E731
        _set_driver_functions(lambda *a: [], lambda *a: None, mock_execute)

        conn = MagicMock()
        mock_entry = MagicMock()
        mock_entry.model_dump.return_value = {"timestamp": "2026-01-01", "level": "warn", "message": "oops"}
        sync_job_events(conn, "j1", [mock_entry])

        insert_calls = [(s, p) for s, p in executed if "INSERT INTO job_events" in s]
        assert len(insert_calls) == 1

    def test_raw_string_fallback(self) -> None:
        from app.postgres_repository_base import _set_driver_functions, sync_job_events

        executed: list[tuple] = []
        mock_execute = lambda conn, sql, params=None: executed.append((sql, params))  # noqa: E731
        _set_driver_functions(lambda *a: [], lambda *a: None, mock_execute)

        conn = MagicMock()
        sync_job_events(conn, "j1", ["plain text message"])

        insert_calls = [(s, p) for s, p in executed if "INSERT INTO job_events" in s]
        assert len(insert_calls) == 1

    def test_none_logs_no_inserts(self) -> None:
        from app.postgres_repository_base import _set_driver_functions, sync_job_events

        executed: list[tuple] = []
        mock_execute = lambda conn, sql, params=None: executed.append((sql, params))  # noqa: E731
        _set_driver_functions(lambda *a: [], lambda *a: None, mock_execute)

        conn = MagicMock()
        sync_job_events(conn, "j1", None)

        insert_calls = [(s, p) for s, p in executed if "INSERT INTO job_events" in s]
        delete_calls = [(s, p) for s, p in executed if "DELETE FROM job_events" in s]
        assert len(insert_calls) == 0
        assert len(delete_calls) >= 1  # delete always runs


# ─── Base class CRUD with mock connections ───────────────────────────────


class TestLoadJobs:
    """``load_jobs`` deserialises rows from the jobs table."""

    def test_returns_dict_of_jobs(self) -> None:
        job = _fake_job("j1")
        row = _row_from_job(job)

        repo = _StubRepo()
        repo._fetch_all_impl = MagicMock(return_value=[row])

        result = repo.load_jobs()
        assert "j1" in result
        assert result["j1"].id == "j1"

    def test_skips_unparseable_rows(self) -> None:
        repo = _StubRepo()
        repo._fetch_all_impl = MagicMock(return_value=[{"nonsense": True}])

        result = repo.load_jobs()
        assert result == {}


class TestGetJob:
    """``get_job`` returns a single Job or None."""

    def test_returns_job_when_found(self) -> None:
        job = _fake_job("j1")
        row = _row_from_job(job)

        repo = _StubRepo()
        repo._fetch_one_impl = MagicMock(return_value=row)

        result = repo.get_job("j1")
        assert result is not None
        assert result.id == "j1"

    def test_returns_none_when_not_found(self) -> None:
        repo = _StubRepo()
        repo._fetch_one_impl = MagicMock(return_value=None)

        assert repo.get_job("missing") is None


class TestListJobSummaries:
    """``list_job_summaries`` clamps limit and maps fields."""

    def test_limit_clamped_to_500(self) -> None:
        repo = _StubRepo()
        repo._fetch_all_impl = MagicMock(return_value=[])

        repo.list_job_summaries(limit=9999)
        # The limit is passed as a %s parameter, not inline
        call_args = repo._fetch_all_impl.call_args
        params = call_args[0][2]
        assert params[-1] == 500

    def test_limit_floored_to_1(self) -> None:
        repo = _StubRepo()
        repo._fetch_all_impl = MagicMock(return_value=[])

        repo.list_job_summaries(limit=0)
        call_args = repo._fetch_all_impl.call_args
        params = call_args[0][2]
        assert params[-1] == 1

    def test_summary_fields_mapped(self) -> None:
        job = _fake_job("j1", topic="test-topic")
        row = _row_from_job(job)
        repo = _StubRepo()
        repo._fetch_all_impl = MagicMock(return_value=[row])

        summaries = repo.list_job_summaries()
        assert len(summaries) == 1
        s = summaries[0]
        assert s["id"] == "j1"
        assert s["status"] == "completed"

    def test_urls_json_parsed_from_string(self) -> None:
        job = _fake_job("j1")
        row = _row_from_job(job)
        row["urls"] = '["https://a.com", "https://b.com"]'
        repo = _StubRepo()
        repo._fetch_all_impl = MagicMock(return_value=[row])

        summaries = repo.list_job_summaries()
        assert summaries[0]["urls"] == ["https://a.com", "https://b.com"]


class TestCountJobsByStatus:
    """``count_jobs_by_status`` returns a ``{status: count}`` mapping."""

    def test_groups_by_status(self) -> None:
        repo = _StubRepo()
        repo._fetch_all_impl = MagicMock(
            return_value=[
                {"status": "completed", "cnt": 5},
                {"status": "failed", "cnt": 2},
            ]
        )

        result = repo.count_jobs_by_status()
        assert result == {"completed": 5, "failed": 2}

    def test_include_deleted_removes_where_clause(self) -> None:
        repo = _StubRepo()
        repo._fetch_all_impl = MagicMock(return_value=[])

        repo.count_jobs_by_status(include_deleted=True)
        sql = repo._fetch_all_impl.call_args[0][1]
        assert "WHERE" not in sql

    def test_exclude_deleted_adds_where_clause(self) -> None:
        repo = _StubRepo()
        repo._fetch_all_impl = MagicMock(return_value=[])

        repo.count_jobs_by_status(include_deleted=False)
        sql = repo._fetch_all_impl.call_args[0][1]
        assert "WHERE" in sql
        assert "deleted_at IS NULL" in sql

    def test_db_error_returns_empty_dict(self) -> None:
        repo = _StubRepo()
        repo._fetch_all_impl = MagicMock(side_effect=RuntimeError("db down"))

        result = repo.count_jobs_by_status()
        assert result == {}


class TestSaveSingle:
    """``save_single`` upserts a job + syncs companions."""

    def test_upsert_uses_on_conflict(self) -> None:
        job = _fake_job("j1")
        repo = _StubRepo()

        repo.save_single(job)
        sqls = [s for s, _ in repo.executed]
        assert any("ON CONFLICT" in s for s in sqls)


class TestSaveAll:
    """``save_all`` upserts all jobs and handles prune_missing."""

    def test_upserts_all_jobs(self) -> None:
        j1 = _fake_job("j1")
        j2 = _fake_job("j2")
        repo = _StubRepo()

        repo.save_all({"j1": j1, "j2": j2}, {})
        assert len(repo.executed) >= 2

    def test_prune_missing_deletes_orphans(self) -> None:
        j1 = _fake_job("j1")
        repo = _StubRepo()

        repo.save_all({"j1": j1}, {}, prune_missing=True)
        sqls = [s for s, _ in repo.executed]
        assert any("DELETE FROM jobs" in s for s in sqls)

    def test_recycle_bin_rows_get_deleted_at(self) -> None:
        j1 = _fake_job("j1")
        repo = _StubRepo()
        repo.save_all({}, {"j1": j1})
        sqls = [s for s, _ in repo.executed]
        assert any("INSERT INTO recycle_bin" in s for s in sqls)


class TestMoveToRecycleBin:
    """``move_to_recycle_bin`` soft-deletes a job and copies to recycle_bin."""

    def test_returns_false_when_job_not_found(self) -> None:
        repo = _StubRepo()
        repo._fetch_one_impl = MagicMock(return_value=None)
        assert repo.move_to_recycle_bin("missing") is False

    def test_returns_true_and_stamps_deleted_at(self) -> None:
        job = _fake_job("j1")
        row = _row_from_job(job)

        repo = _StubRepo()
        repo._fetch_one_impl = MagicMock(return_value=row)

        result = repo.move_to_recycle_bin("j1")
        assert result is True
        sqls = [s for s, _ in repo.executed]
        assert any("UPDATE jobs SET deleted_at" in s for s in sqls)
        assert any("INSERT INTO recycle_bin" in s for s in sqls)


class TestRestoreFromRecycleBin:
    """``restore_from_recycle_bin`` un-deletes a job."""

    def test_returns_false_when_not_in_bin(self) -> None:
        repo = _StubRepo()
        repo._fetch_one_impl = MagicMock(return_value=None)
        assert repo.restore_from_recycle_bin("missing") is False

    def test_returns_true_and_restores(self) -> None:
        job = _fake_job("j1")
        row = _row_from_job(job)

        repo = _StubRepo()
        repo._fetch_one_impl = MagicMock(return_value=row)

        result = repo.restore_from_recycle_bin("j1")
        assert result is True
        sqls = [s for s, _ in repo.executed]
        assert any("DELETE FROM recycle_bin" in s for s in sqls)
        assert any("INSERT INTO jobs" in s for s in sqls)


class TestHardDelete:
    """``hard_delete`` removes job from all tables."""

    def test_returns_true_when_deleted(self) -> None:
        repo = _StubRepo()
        repo._mock_cursor.rowcount = 1

        result = repo.hard_delete("j1")
        assert result is True

    def test_returns_false_when_not_found(self) -> None:
        repo = _StubRepo()
        repo._mock_cursor.rowcount = 0

        result = repo.hard_delete("j1")
        assert result is False

    def test_deletes_from_all_tables(self) -> None:
        repo = _StubRepo()
        repo._mock_cursor.rowcount = 1
        repo.hard_delete("j1")

        sqls = [s for s, _ in repo.executed]
        assert any("DELETE FROM jobs" in s for s in sqls)
        assert any("DELETE FROM recycle_bin" in s for s in sqls)
        assert any("DELETE FROM job_results" in s for s in sqls)
        assert any("DELETE FROM job_events" in s for s in sqls)


class TestClearTerminalJobs:
    """``clear_terminal_jobs`` soft-deletes terminal-status jobs."""

    def test_moves_terminal_jobs_to_recycle(self) -> None:
        job = _fake_job("j1", status=JobStatus.COMPLETED)
        row = _row_from_job(job)

        repo = _StubRepo()
        repo._fetch_all_impl = MagicMock(return_value=[row])

        count = repo.clear_terminal_jobs()
        assert count == 1
        sqls = [s for s, _ in repo.executed]
        assert any("UPDATE jobs SET deleted_at" in s for s in sqls)
        assert any("INSERT INTO recycle_bin" in s for s in sqls)

    def test_with_older_than_filter(self) -> None:
        repo = _StubRepo()
        repo._fetch_all_impl = MagicMock(return_value=[])

        repo.clear_terminal_jobs(older_than="2025-01-01")
        sql = repo._fetch_all_impl.call_args[0][1]
        assert "completed_at" in sql


class TestReadResults:
    """``read_results`` reads and JSON-parses result payloads."""

    def test_parses_json_payloads(self) -> None:
        repo = _StubRepo()
        repo._fetch_all_impl = MagicMock(
            return_value=[
                {"payload": json.dumps({"title": "r1"})},
                {"payload": json.dumps({"title": "r2"})},
            ]
        )

        results = repo.read_results("j1")
        assert len(results) == 2
        assert results[0]["title"] == "r1"

    def test_unparseable_payload_returns_fallback(self) -> None:
        repo = _StubRepo()
        repo._fetch_all_impl = MagicMock(
            return_value=[
                {"payload": "not-json"},
            ]
        )

        results = repo.read_results("j1")
        assert len(results) == 1
        assert "_unparseable" in results[0]

    def test_db_error_returns_empty_list(self) -> None:
        repo = _StubRepo()
        repo._fetch_all_impl = MagicMock(side_effect=RuntimeError("down"))

        assert repo.read_results("j1") == []

    def test_limit_clamped(self) -> None:
        repo = _StubRepo()
        repo._fetch_all_impl = MagicMock(return_value=[])

        repo.read_results("j1", limit=9999, offset=-5)
        call_args = repo._fetch_all_impl.call_args
        params = call_args[0][2]
        assert params[1] == 1000
        assert params[2] == 0


class TestCountResults:
    """``count_results`` returns count or 0 on error."""

    def test_returns_count(self) -> None:
        repo = _StubRepo()
        repo._fetch_one_impl = MagicMock(return_value={"cnt": 42})

        assert repo.count_results("j1") == 42

    def test_returns_zero_on_error(self) -> None:
        repo = _StubRepo()
        repo._fetch_one_impl = MagicMock(side_effect=RuntimeError("down"))

        assert repo.count_results("j1") == 0


class TestReadEvents:
    """``read_events`` with optional level_prefix filter."""

    def test_reads_events(self) -> None:
        repo = _StubRepo()
        repo._fetch_all_impl = MagicMock(
            return_value=[
                {"timestamp": "2026-01-01", "level": "info", "message": "ok"},
            ]
        )

        events = repo.read_events("j1")
        assert len(events) == 1
        assert events[0]["message"] == "ok"

    def test_level_prefix_filter(self) -> None:
        repo = _StubRepo()
        repo._fetch_all_impl = MagicMock(return_value=[])

        repo.read_events("j1", level_prefix="err")
        sql = repo._fetch_all_impl.call_args[0][1]
        assert "LOWER(level) LIKE" in sql

    def test_db_error_returns_empty(self) -> None:
        repo = _StubRepo()
        repo._fetch_all_impl = MagicMock(side_effect=OSError("conn lost"))

        assert repo.read_events("j1") == []


class TestIdempotency:
    """``lookup_idempotency_key``, ``record_idempotency_key``, ``prune_idempotency_keys``."""

    def test_lookup_returns_job_id_on_hit(self) -> None:
        repo = _StubRepo()
        repo._fetch_one_impl = MagicMock(return_value={"job_id": "j1"})

        assert repo.lookup_idempotency_key("key1") == "j1"

    def test_lookup_returns_none_on_miss(self) -> None:
        repo = _StubRepo()
        repo._fetch_one_impl = MagicMock(return_value=None)

        assert repo.lookup_idempotency_key("key1") is None

    def test_lookup_empty_key_returns_none(self) -> None:
        repo = _StubRepo()
        assert repo.lookup_idempotency_key("") is None

    def test_lookup_fingerprint_hit(self) -> None:
        repo = _StubRepo()
        repo._fetch_one_impl = MagicMock(return_value={"request_fingerprint": "abc"})

        assert repo.lookup_idempotency_fingerprint("key1") == "abc"

    def test_lookup_fingerprint_empty_key(self) -> None:
        repo = _StubRepo()
        assert repo.lookup_idempotency_fingerprint("") is None

    def test_record_empty_key_is_noop(self) -> None:
        repo = _StubRepo()
        repo.record_idempotency_key("", "j1", "fp")
        assert len(repo.executed) == 0

    def test_record_executes_upsert(self) -> None:
        repo = _StubRepo()
        repo.record_idempotency_key("key1", "j1", "fp")
        sqls = [s for s, _ in repo.executed]
        assert any("idempotency_keys" in s for s in sqls)

    def test_prune_returns_count(self) -> None:
        repo = _StubRepo()
        repo._mock_cursor.rowcount = 3

        result = repo.prune_idempotency_keys(7)
        assert result == 3

    def test_prune_zero_days_returns_zero(self) -> None:
        repo = _StubRepo()
        assert repo.prune_idempotency_keys(0) == 0

    def test_prune_negative_days_returns_zero(self) -> None:
        repo = _StubRepo()
        assert repo.prune_idempotency_keys(-1) == 0


class TestCleanupCompanionData:
    """``cleanup_companion_data`` deletes results + events for a job."""

    def test_deletes_results_and_events(self) -> None:
        repo = _StubRepo()
        repo.cleanup_companion_data("j1")

        sqls = [s for s, _ in repo.executed]
        assert any("DELETE FROM job_results" in s for s in sqls)
        assert any("DELETE FROM job_events" in s for s in sqls)

    def test_swallows_db_errors(self) -> None:
        repo = _StubRepo()
        repo._execute_impl = MagicMock(side_effect=RuntimeError("down"))

        # Should not raise
        repo.cleanup_companion_data("j1")


class TestIsCancelRequested:
    """``is_cancel_requested`` returns bool from DB row."""

    def test_returns_true(self) -> None:
        repo = _StubRepo()
        repo._fetch_one_impl = MagicMock(return_value={"cancel_requested": True})

        assert repo.is_cancel_requested("j1") is True

    def test_returns_false_on_missing(self) -> None:
        repo = _StubRepo()
        repo._fetch_one_impl = MagicMock(return_value=None)

        assert repo.is_cancel_requested("j1") is False


class TestWorldState:
    """``load_world_state`` and ``save_world_state`` round-trip."""

    def test_load_returns_parsed_json(self) -> None:
        repo = _StubRepo()
        repo._fetch_one_impl = MagicMock(return_value={"payload": json.dumps({"k": "v"})})

        result = repo.load_world_state()
        assert result == {"k": "v"}

    def test_load_returns_none_on_missing(self) -> None:
        repo = _StubRepo()
        repo._fetch_one_impl = MagicMock(return_value=None)

        assert repo.load_world_state() is None

    def test_load_handles_malformed_json(self) -> None:
        repo = _StubRepo()
        repo._fetch_one_impl = MagicMock(return_value={"payload": "not-json"})

        assert repo.load_world_state() is None

    def test_save_upserts(self) -> None:
        repo = _StubRepo()
        repo.save_world_state({"k": "v"})
        sqls = [s for s, _ in repo.executed]
        assert any("world_state" in s for s in sqls)


class TestWorkerHeartbeat:
    """``record_worker_heartbeat`` and ``get_worker_health``."""

    def test_record_heartbeat_upserts(self) -> None:
        repo = _StubRepo()
        repo.record_worker_heartbeat("w1", "host1", 1234)
        sqls = [s for s, _ in repo.executed]
        assert any("worker_heartbeats" in s for s in sqls)

    def test_get_health_alive(self) -> None:
        import datetime

        recent = datetime.datetime.now(datetime.UTC).isoformat()
        repo = _StubRepo()
        repo._fetch_one_impl = MagicMock(
            return_value={
                "last_heartbeat": recent,
                "hostname": "host1",
                "pid": 1234,
                "started_at": recent,
            }
        )

        health = repo.get_worker_health("w1")
        assert health["alive"] is True
        assert health["hostname"] == "host1"

    def test_get_health_dead(self) -> None:
        repo = _StubRepo()
        repo._fetch_one_impl = MagicMock(return_value=None)

        health = repo.get_worker_health("w1")
        assert health["alive"] is False

    def test_get_health_stale_heartbeat(self) -> None:
        repo = _StubRepo()
        repo._fetch_one_impl = MagicMock(
            return_value={
                "last_heartbeat": "2020-01-01T00:00:00+00:00",
                "hostname": "host1",
                "pid": 1234,
                "started_at": "2020-01-01T00:00:00+00:00",
            }
        )

        health = repo.get_worker_health("w1", ttl_seconds=60)
        assert health["alive"] is False

    def test_get_all_worker_healths(self) -> None:
        import datetime

        recent = datetime.datetime.now(datetime.UTC).isoformat()
        repo = _StubRepo()
        repo._fetch_all_impl = MagicMock(
            return_value=[
                {"worker_id": "w1", "last_heartbeat": recent, "hostname": "h1", "pid": 1},
            ]
        )

        results = repo.get_all_worker_healths()
        assert len(results) == 1
        assert results[0]["alive"] is True


class TestHealthCheck:
    """``health_check`` returns structured result."""

    def test_returns_dict_with_ok_key(self) -> None:
        repo = _StubRepo()
        with patch(
            "app.storage_health.check_postgres_health", return_value={"ok": True, "backend": "postgres", "schema_version": 8}
        ):
            result = repo.health_check()

        assert "ok" in result

    def test_db_error_returns_error_dict(self) -> None:
        repo = _StubRepo()
        with patch.object(repo, "_ensure", side_effect=RuntimeError("no db")):
            result = repo.health_check()
        assert result["ok"] is False


class TestGetStorageStatus:
    """``get_storage_status`` returns detailed status."""

    def test_error_path_returns_minus_one_counts(self) -> None:
        repo = _StubRepo()
        with patch.object(repo, "_ensure", side_effect=RuntimeError("no db")):
            result = repo.get_storage_status()
        assert result["job_count"] == -1
        assert result["recycle_bin_count"] == -1
        assert result["wal_mode"] == "unknown"


class TestEnsure:
    """``_ensure`` only runs schema setup once."""

    def test_schema_ensured_flag_prevents_repeat(self) -> None:
        repo = _StubRepo(auto_ensure=True)
        repo._schema_ensured = True

        # _ensure should be a no-op since schema is already ensured
        repo._ensure()

    def test_auto_ensure_false_skips(self) -> None:
        repo = _StubRepo(auto_ensure=False)
        repo._schema_ensured = False

        repo._ensure()

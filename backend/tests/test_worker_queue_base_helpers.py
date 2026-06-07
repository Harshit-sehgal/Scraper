"""Tests for the driver-agnostic base helpers in
``app.worker_queue_postgres_base``.

These verify the schema helpers using a fake connection (in-memory dict)
to confirm the SQL flow without depending on a real Postgres server.
"""

from __future__ import annotations

from typing import Any

import pytest
from app.worker_queue_postgres_base import (
    _CURRENT_QUEUE_SCHEMA_VERSION,
    _add_column_if_missing,
    _ensure_schema_via,
)


class FakeCursor:
    """Minimal psycopg2-like cursor that records SQL and parameters."""

    def __init__(self, conn: "FakeConn") -> None:
        self._conn = conn
        self._result: list[tuple] | None = None

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, *exc: Any) -> None:
        return None

    def execute(self, sql: str, params: Any = None) -> None:
        self._conn.executed.append((sql.strip(), params))
        # Simulate table creation side effect for the in-memory store.
        if sql.strip().upper().startswith("CREATE TABLE"):
            pass  # tables "exist" virtually
        # ``SAVEPOINT`` / ``RELEASE`` / ``ROLLBACK`` are recorded but not modeled.

    def fetchone(self) -> tuple | None:
        return self._conn.next_fetchone


class FakeConn:
    """Minimal psycopg2-like connection for unit testing."""

    def __init__(self) -> None:
        self.executed: list[tuple[str, Any]] = []
        self.next_fetchone: tuple | None = None
        self.committed = False
        self.rolled_back = False

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True


@pytest.fixture
def fake_conn() -> FakeConn:
    return FakeConn()


def test_schema_version_is_three() -> None:
    """Schema version is currently 3 (queue_tasks, queue_task_history + result + exec_time_ms)."""
    assert _CURRENT_QUEUE_SCHEMA_VERSION == 3


def test_add_column_if_missing_runs_alter(fake_conn: FakeConn) -> None:
    """A missing column triggers ALTER TABLE ADD COLUMN inside a SAVEPOINT."""
    _add_column_if_missing(fake_conn, "queue_task_history", "result", "TEXT")
    sqls = [s for s, _ in fake_conn.executed]
    assert any(s.startswith("SAVEPOINT add_col_sp") for s in sqls)
    assert any("ALTER TABLE queue_task_history ADD COLUMN result" in s for s in sqls)
    assert any(s.startswith("RELEASE SAVEPOINT add_col_sp") for s in sqls)


def test_ensure_schema_via_runs_create_table_when_no_schema_version(
    fake_conn: FakeConn,
) -> None:
    """When the schema_version row is missing, _ensure_schema_via creates the tables."""
    calls: list[tuple[str, Any]] = []

    def fetch_one(_conn: Any, sql: str, params: Any = None) -> dict | None:
        calls.append((sql, params))
        return None  # no version row exists

    def execute(_conn: Any, sql: str, params: Any = None) -> None:
        calls.append((sql, params))
        fake_conn.executed.append((sql.strip(), params))

    _ensure_schema_via(fake_conn, fetch_one, execute)
    sqls = [s for s, _ in calls]
    assert any("CREATE TABLE IF NOT EXISTS queue_tasks" in s for s in sqls)
    assert any("CREATE TABLE IF NOT EXISTS queue_task_history" in s for s in sqls)
    assert any("CREATE INDEX IF NOT EXISTS idx_queue_tasks_status_priority" in s for s in sqls)
    assert any("CREATE INDEX IF NOT EXISTS idx_queue_tasks_scheduled" in s for s in sqls)
    # Final version write
    assert any("INSERT INTO queue_schema_version" in s for s in sqls)


def test_ensure_schema_via_skips_when_already_at_current_version(
    fake_conn: FakeConn,
) -> None:
    """If schema_version already reports the current version, no migrations run."""
    calls: list[tuple[str, Any]] = []

    def fetch_one(_conn: Any, sql: str, params: Any = None) -> dict | None:
        calls.append((sql, params))
        return {"version": _CURRENT_QUEUE_SCHEMA_VERSION}

    def execute(_conn: Any, sql: str, params: Any = None) -> None:
        calls.append((sql, params))

    _ensure_schema_via(fake_conn, fetch_one, execute)
    sqls = [s for s, _ in calls]
    # No CREATE TABLE statements should be executed
    assert not any("CREATE TABLE IF NOT EXISTS queue_tasks" in s for s in sqls)
    assert not any("CREATE TABLE IF NOT EXISTS queue_task_history" in s for s in sqls)


def test_ensure_schema_via_handles_null_version_row(fake_conn: FakeConn) -> None:
    """A row with NULL version triggers a DROP and full re-migration."""
    calls: list[tuple[str, Any]] = []

    def fetch_one(_conn: Any, sql: str, params: Any = None) -> dict | None:
        calls.append((sql, params))
        # First call: table exists. Second: row exists with NULL version.
        if "DROP TABLE" in (calls[0][0] if calls else ""):
            return {"version": _CURRENT_QUEUE_SCHEMA_VERSION}
        # Simulate a NULL version row.
        return {"version": None}

    def execute(_conn: Any, sql: str, params: Any = None) -> None:
        calls.append((sql, params))

    # First call returns row with NULL version, triggering DROP and recreate.
    _ensure_schema_via(fake_conn, fetch_one, execute)
    sqls = [s for s, _ in calls]
    # Either path: the migration is invoked, ending with INSERT version row.
    assert any("INSERT INTO queue_schema_version" in s for s in sqls)

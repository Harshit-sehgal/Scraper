"""Unit tests for the psycopg 3 driver hooks in
``app.worker_queue_postgres_psycopg3``.

These tests exercise the driver helpers (``_conn``, ``_fetch_one``,
``_fetch_all``, ``_execute``, ``_close_pool``, ``_get_pool``) with a
mock connection that mimics psycopg 3's API, so we cover the
psycopg 3-specific code paths without needing a running Postgres server.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


class FakeColumn:
    """psycopg 3 column descriptor — has a ``.name`` attribute."""

    def __init__(self, name: str) -> None:
        self.name = name


class FakePsycopg3Cursor:
    """Minimal psycopg 3 cursor that records SQL and parameters."""

    def __init__(self, conn: "FakePsycopg3Conn", description: list | None = None) -> None:
        self._conn = conn
        self._description = description
        self._rows: list[tuple] = []

    def __enter__(self) -> "FakePsycopg3Cursor":
        return self

    def __exit__(self, *exc: Any) -> None:
        return None

    @property
    def description(self) -> list | None:
        return self._description

    def execute(self, sql: str, params: Any = None) -> None:
        self._conn.executed.append((sql, params))
        if self._conn.next_rows is not None:
            self._rows = self._conn.next_rows

    def fetchone(self) -> tuple | None:
        return self._rows[0] if self._rows else None

    def fetchall(self) -> list[tuple]:
        return list(self._rows)


class FakePsycopg3Conn:
    """Minimal psycopg 3 connection."""

    def __init__(self, description: list | None = None) -> None:
        self.executed: list[tuple[str, Any]] = []
        self.next_rows: list[tuple] = []
        self.committed = False
        self.rolled_back = False
        self._description = description

    def cursor(self) -> FakePsycopg3Cursor:
        return FakePsycopg3Cursor(self, self._description)

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True


class FakePool:
    """Minimal psycopg 3 pool that yields a fake connection."""

    def __init__(self, conn: FakePsycopg3Conn) -> None:
        self._conn = conn
        self.closed = False

    @contextmanager
    def connection(self):
        yield self._conn

    def open(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def fresh_module() -> Any:
    """Reload the psycopg3 module to reset the global pool."""
    import importlib
    import sys

    mod_name = "app.worker_queue_postgres_psycopg3"
    if mod_name not in sys.modules:
        importlib.import_module(mod_name)
    else:
        importlib.reload(sys.modules[mod_name])
    return sys.modules[mod_name]


def test_psycopg3_module_exposes_factory_and_shutdown(fresh_module: Any) -> None:
    """The module exports the public factory and shutdown helpers."""
    assert callable(fresh_module.get_postgres_worker_queue_psycopg3)
    assert callable(fresh_module.shutdown_psycopg3_worker_queue)
    assert fresh_module.PostgresWorkerQueuePsycopg3 is not None


def test_get_pool_min_max_uses_settings(fresh_module: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """_get_pool_min_max returns the configured min/max with max >= min."""
    monkeypatch.setenv("DATAFORGE_PG_MIN_CONN", "2")
    monkeypatch.setenv("DATAFORGE_PG_MAX_CONN", "8")
    minconn, maxconn = fresh_module._get_pool_min_max()
    assert minconn == 2
    assert maxconn == 8


def test_get_pool_min_max_clamps_max_below_min(
    fresh_module: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If max < min, max is raised to min (avoids invalid pool config)."""
    monkeypatch.setenv("DATAFORGE_PG_MIN_CONN", "5")
    monkeypatch.setenv("DATAFORGE_PG_MAX_CONN", "1")
    minconn, maxconn = fresh_module._get_pool_min_max()
    assert minconn == 5
    assert maxconn == 5


def test_fetch_all_returns_dicts(fresh_module: Any) -> None:
    """_fetch_all converts cursor rows to list of dicts using description."""
    fake = FakePsycopg3Conn(description=[FakeColumn("id"), FakeColumn("val")])
    fake.next_rows = [("a", 1), ("b", 2)]
    result = fresh_module._fetch_all(fake, "SELECT id, val FROM t")
    assert result == [{"id": "a", "val": 1}, {"id": "b", "val": 2}]


def test_fetch_all_handles_no_description(fresh_module: Any) -> None:
    """_fetch_all returns [] when the cursor has no description (no rows)."""
    fake = FakePsycopg3Conn(description=None)
    fake.next_rows = []
    result = fresh_module._fetch_all(fake, "SELECT 1")
    assert result == []


def test_fetch_one_returns_dict(fresh_module: Any) -> None:
    """_fetch_one returns the first row as a dict."""
    fake = FakePsycopg3Conn(description=[FakeColumn("id"), FakeColumn("val")])
    fake.next_rows = [("a", 1)]
    result = fresh_module._fetch_one(fake, "SELECT id, val FROM t WHERE id=%s", ("a",))
    assert result == {"id": "a", "val": 1}


def test_fetch_one_returns_none_when_no_rows(fresh_module: Any) -> None:
    """_fetch_one returns None when the cursor has no rows."""
    fake = FakePsycopg3Conn(description=[FakeColumn("id")])
    fake.next_rows = []
    result = fresh_module._fetch_one(fake, "SELECT id FROM t")
    assert result is None


def test_fetch_one_handles_no_description(fresh_module: Any) -> None:
    """_fetch_one returns None for a query with no description and no row."""
    fake = FakePsycopg3Conn(description=None)
    fake.next_rows = []
    result = fresh_module._fetch_one(fake, "SELECT 1")
    assert result is None


def test_execute_runs_and_returns_cursor(fresh_module: Any) -> None:
    """_execute runs the SQL and returns the cursor."""
    fake = FakePsycopg3Conn()
    cur = fresh_module._execute(fake, "INSERT INTO t (x) VALUES (%s)", (1,))
    assert cur is not None
    assert len(fake.executed) == 1
    assert fake.executed[0] == ("INSERT INTO t (x) VALUES (%s)", (1,))


def test_execute_handles_none_params(fresh_module: Any) -> None:
    """_execute treats None params as an empty tuple."""
    fake = FakePsycopg3Conn()
    fresh_module._execute(fake, "DELETE FROM t")
    assert fake.executed[0] == ("DELETE FROM t", ())


def test_conn_context_commits_on_success(fresh_module: Any) -> None:
    """The _conn context manager commits on a clean exit."""
    fake = FakePsycopg3Conn()
    pool = FakePool(fake)
    fresh_module._pool = pool
    with fresh_module._conn() as conn:
        assert conn is fake
    assert fake.committed is True
    assert fake.rolled_back is False


def test_conn_context_rolls_back_on_exception(
    fresh_module: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An exception inside the _conn context triggers rollback + record_error."""
    fake = FakePsycopg3Conn()
    pool = FakePool(fake)
    fresh_module._pool = pool
    # Stub metrics so we don't depend on the global collector.
    monkeypatch.setattr("app.metrics_collector.record_error", lambda *_a, **_k: None)
    with pytest.raises(RuntimeError, match="boom"):
        with fresh_module._conn():
            raise RuntimeError("boom")
    assert fake.committed is False
    assert fake.rolled_back is True


def test_conn_context_swallows_metrics_failure(
    fresh_module: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the metrics collector fails, the original DB error is still raised."""
    fake = FakePsycopg3Conn()
    pool = FakePool(fake)
    fresh_module._pool = pool

    def boom(*_a: Any, **_k: Any) -> None:
        raise RuntimeError("metrics broken")

    monkeypatch.setattr("app.metrics_collector.record_error", boom)
    with pytest.raises(RuntimeError, match="original"):
        with fresh_module._conn():
            raise RuntimeError("original")


def test_close_pool_is_idempotent(fresh_module: Any) -> None:
    """Closing an already-closed pool is a safe no-op."""
    fresh_module._pool = None
    fresh_module._close_pool()  # should not raise


def test_close_pool_handles_close_failure(fresh_module: Any) -> None:
    """A pool that raises on close is silently logged and ignored."""
    bad_pool = MagicMock()
    bad_pool.close.side_effect = RuntimeError("close failed")
    fresh_module._pool = bad_pool
    fresh_module._close_pool()  # should not raise
    assert fresh_module._pool is None


def test_get_postgres_worker_queue_psycopg3_returns_instance(fresh_module: Any) -> None:
    """The public factory returns a PostgresWorkerQueuePsycopg3 instance."""
    with patch.object(fresh_module, "_get_pool") as get_pool:
        fake = FakePsycopg3Conn()
        pool = FakePool(fake)
        get_pool.return_value = pool
        fresh_module._pool = pool
        q = fresh_module.get_postgres_worker_queue_psycopg3()
        assert isinstance(q, fresh_module.PostgresWorkerQueuePsycopg3)


def test_shutdown_helper_calls_close(fresh_module: Any) -> None:
    """shutdown_psycopg3_worker_queue calls _close_pool."""
    with patch.object(fresh_module, "_close_pool") as close_pool:
        fresh_module.shutdown_psycopg3_worker_queue()
        close_pool.assert_called_once_with()


def test_queue_class_driver_hooks_dispatch_to_module(
    fresh_module: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The PostgresWorkerQueuePsycopg3 driver hooks delegate to the module helpers."""
    fake = FakePsycopg3Conn()
    pool = FakePool(fake)
    fresh_module._pool = pool
    q = fresh_module.get_postgres_worker_queue_psycopg3()
    # Each hook should work without raising.
    list(q._fetch_all(fake, "SELECT 1"))
    assert q._fetch_one(fake, "SELECT 2") is None or q._fetch_one(fake, "SELECT 2") is not None
    q._execute(fake, "SELECT 3")

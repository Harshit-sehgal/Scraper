"""Tests for ``Settings.PG_MIN_CONN`` / ``Settings.PG_MAX_CONN`` (DATAFORGE_PG_MIN_CONN / DATAFORGE_PG_MAX_CONN).

These are the unified pool-sizing knobs for the psycopg2 and psycopg3
Postgres backends. The tests assert:

1. The default values (1, 10) match the prior hard-coded behaviour.
2. The env vars override the defaults.
3. The values are clamped to ``[1, 1000]`` to prevent a malformed
   env var from producing a degenerate pool.
4. A non-integer env var falls back to the default, not a crash.
5. ``maxconn`` is always ``>=`` ``minconn`` at the consumer level
   (the pool factories do the floor).
"""

from __future__ import annotations

import pytest
from app.config import Settings


@pytest.fixture
def fresh_settings(monkeypatch):
    """A fresh ``Settings`` instance with all PG env vars cleared."""
    monkeypatch.delenv("DATAFORGE_PG_MIN_CONN", raising=False)
    monkeypatch.delenv("DATAFORGE_PG_MAX_CONN", raising=False)
    return Settings()


def test_pg_min_conn_default_is_one(fresh_settings: Settings) -> None:
    assert fresh_settings.PG_MIN_CONN == 1


def test_pg_max_conn_default_is_ten(fresh_settings: Settings) -> None:
    assert fresh_settings.PG_MAX_CONN == 10


def test_pg_min_conn_reads_env_var(fresh_settings: Settings, monkeypatch) -> None:
    monkeypatch.setenv("DATAFORGE_PG_MIN_CONN", "4")
    assert fresh_settings.PG_MIN_CONN == 4


def test_pg_max_conn_reads_env_var(fresh_settings: Settings, monkeypatch) -> None:
    monkeypatch.setenv("DATAFORGE_PG_MAX_CONN", "20")
    assert fresh_settings.PG_MAX_CONN == 20


def test_pg_min_conn_clamps_to_upper_bound(fresh_settings: Settings, monkeypatch) -> None:
    monkeypatch.setenv("DATAFORGE_PG_MIN_CONN", "99999")
    assert fresh_settings.PG_MIN_CONN == 1000


def test_pg_min_conn_floors_to_one(fresh_settings: Settings, monkeypatch) -> None:
    monkeypatch.setenv("DATAFORGE_PG_MIN_CONN", "0")
    assert fresh_settings.PG_MIN_CONN == 1


def test_pg_max_conn_clamps_to_upper_bound(fresh_settings: Settings, monkeypatch) -> None:
    monkeypatch.setenv("DATAFORGE_PG_MAX_CONN", "99999")
    assert fresh_settings.PG_MAX_CONN == 1000


def test_pg_min_conn_falls_back_on_garbage(fresh_settings: Settings, monkeypatch) -> None:
    monkeypatch.setenv("DATAFORGE_PG_MIN_CONN", "not-a-number")
    assert fresh_settings.PG_MIN_CONN == 1


def test_pg_max_conn_falls_back_on_garbage(fresh_settings: Settings, monkeypatch) -> None:
    monkeypatch.setenv("DATAFORGE_PG_MAX_CONN", "definitely-not-a-number")
    assert fresh_settings.PG_MAX_CONN == 10


def test_psycopg3_pool_min_max_uses_settings(fresh_settings: Settings, monkeypatch) -> None:
    """The psycopg3 ``_get_pool_min_max`` helper must delegate to settings."""
    from app.psycopg3_repository import _get_pool_min_max

    monkeypatch.setenv("DATAFORGE_PG_MIN_CONN", "3")
    monkeypatch.setenv("DATAFORGE_PG_MAX_CONN", "15")
    minconn, maxconn = _get_pool_min_max()
    assert minconn == 3
    assert maxconn == 15


def test_psycopg3_pool_min_max_enforces_floor(fresh_settings: Settings, monkeypatch) -> None:
    """``maxconn`` is always ``>=`` ``minconn`` even if the env is weird."""
    from app.psycopg3_repository import _get_pool_min_max

    monkeypatch.setenv("DATAFORGE_PG_MIN_CONN", "20")
    monkeypatch.setenv("DATAFORGE_PG_MAX_CONN", "5")
    minconn, maxconn = _get_pool_min_max()
    assert minconn == 20
    assert maxconn >= minconn

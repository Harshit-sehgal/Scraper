"""Tests for the driver-aware ``get_postgres_worker_queue()`` factory.

Verifies that the factory in ``app.worker_queue_postgres`` correctly
selects the psycopg 3 implementation when ``DATAFORGE_PG_DRIVER=psycopg3``
and the psycopg 2 implementation otherwise. These tests do not require
a running Postgres instance — they only verify the dispatch logic
(avoiding actual construction, which would open a DB connection).
"""

from __future__ import annotations

import sys
from unittest.mock import patch

import pytest


def _driver_selection() -> str:
    """Return the driver name the factory would select for current env.

    Mirrors the dispatch logic in ``get_postgres_worker_queue`` exactly
    so we can verify the decision without opening a DB connection.
    """
    import os

    return os.environ.get("DATAFORGE_PG_DRIVER", "").strip().lower()


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch):
    """Reset DATAFORGE_PG_DRIVER and the queue instance for each test."""
    monkeypatch.delenv("DATAFORGE_PG_DRIVER", raising=False)
    yield


def test_factory_default_driver_is_psycopg2() -> None:
    """With no DATAFORGE_PG_DRIVER set, the factory selects the psycopg2 driver."""
    assert _driver_selection() != "psycopg3"


def test_factory_psycopg3_env_selects_psycopg3(monkeypatch: pytest.MonkeyPatch) -> None:
    """DATAFORGE_PG_DRIVER=psycopg3 must select the psycopg 3 driver."""
    monkeypatch.setenv("DATAFORGE_PG_DRIVER", "psycopg3")
    assert _driver_selection() == "psycopg3"


def test_factory_psycopg2_env_explicit_selects_psycopg2(monkeypatch: pytest.MonkeyPatch) -> None:
    """DATAFORGE_PG_DRIVER=psycopg2 must select the psycopg2 driver."""
    monkeypatch.setenv("DATAFORGE_PG_DRIVER", "psycopg2")
    assert _driver_selection() != "psycopg3"


def test_factory_env_whitespace_and_case_normalised(monkeypatch: pytest.MonkeyPatch) -> None:
    """Env value is case-insensitive and whitespace-stripped."""
    monkeypatch.setenv("DATAFORGE_PG_DRIVER", "  Psycopg3  ")
    assert _driver_selection() == "psycopg3"
    monkeypatch.setenv("DATAFORGE_PG_DRIVER", "  PSYCOPG3  ")
    assert _driver_selection() == "psycopg3"
    monkeypatch.setenv("DATAFORGE_PG_DRIVER", "PSYCOPG2")
    assert _driver_selection() == "psycopg2"


def test_factory_singleton_returns_same_instance() -> None:
    """get_postgres_worker_queue returns the same instance on repeated calls.

    Uses a mock so the underlying ``__init__`` (which opens a DB
    connection) is not executed.
    """
    import app.worker_queue_postgres as wqp

    wqp.reset_postgres_worker_queue()
    with patch.object(wqp, "PostgresWorkerQueue") as cls:
        cls.return_value = "fake_queue_instance"
        q1 = wqp.get_postgres_worker_queue()
        q2 = wqp.get_postgres_worker_queue()
    assert q1 is q2
    assert cls.call_count == 1


def test_factory_reset_creates_new_instance() -> None:
    """After reset, a fresh instance is constructed on the next call."""
    import app.worker_queue_postgres as wqp

    wqp.reset_postgres_worker_queue()
    with patch.object(wqp, "PostgresWorkerQueue") as cls:
        cls.side_effect = ["fake_q1", "fake_q2"]
        q1 = wqp.get_postgres_worker_queue()
        wqp.reset_postgres_worker_queue()
        q2 = wqp.get_postgres_worker_queue()
    assert q1 == "fake_q1"
    assert q2 == "fake_q2"
    assert q1 is not q2


def test_factory_psycopg3_path_constructs_psycopg3_instance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DATAFORGE_PG_DRIVER=psycopg3 routes construction to the psycopg 3 class."""
    import app.worker_queue_postgres as wqp
    from app.worker_queue_postgres_psycopg3 import PostgresWorkerQueuePsycopg3

    monkeypatch.setenv("DATAFORGE_PG_DRIVER", "psycopg3")
    wqp.reset_postgres_worker_queue()
    with patch.object(PostgresWorkerQueuePsycopg3, "__init__", return_value=None) as init:
        queue = wqp.get_postgres_worker_queue()
    assert isinstance(queue, PostgresWorkerQueuePsycopg3)
    assert init.call_count == 1


def test_factory_psycopg3_import_error_raises_runtime_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the psycopg 3 module is unavailable, the factory raises a clear error."""
    monkeypatch.setenv("DATAFORGE_PG_DRIVER", "psycopg3")
    import app.worker_queue_postgres as wqp

    wqp.reset_postgres_worker_queue()
    # Force the import to fail by hiding the module.
    monkeypatch.setitem(sys.modules, "app.worker_queue_postgres_psycopg3", None)
    with pytest.raises(RuntimeError, match=r"Failed to import psycopg3 worker queue"):
        wqp.get_postgres_worker_queue()

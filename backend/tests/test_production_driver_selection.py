"""Tests for the production Postgres driver selection logic.

These tests ensure the repository path used in production cannot silently
default to psycopg2, which would crash the production image that ships
only psycopg3.
"""

from __future__ import annotations

import pytest


def test_production_without_pg_driver_fails_fast(monkeypatch) -> None:
    """In production with STORAGE_BACKEND=postgres, missing DATAFORGE_PG_DRIVER
    must raise RuntimeError rather than silently defaulting to psycopg2."""
    monkeypatch.setenv("DATAFORGE_STORAGE_BACKEND", "postgres")
    monkeypatch.setenv("DATAFORGE_ENV", "production")
    monkeypatch.setenv(
        "DATAFORGE_DATABASE_URL",
        "postgresql://user:pass@localhost:5432/db",
    )
    monkeypatch.delenv("DATAFORGE_PG_DRIVER", raising=False)

    import app.storage_interface as si

    si.reset_repository()

    with pytest.raises(RuntimeError) as excinfo:
        si.get_job_repository()
    assert "DATAFORGE_PG_DRIVER" in str(excinfo.value)
    assert "psycopg3" in str(excinfo.value)

    si.reset_repository()


def test_production_with_pg_driver_psycopg3_does_not_fail_on_driver(monkeypatch) -> None:
    """With DATAFORGE_PG_DRIVER=psycopg3, the production check should NOT
    raise a driver selection RuntimeError. (It may still raise a
    connection error if Postgres is unreachable, which is acceptable.)"""
    monkeypatch.setenv("DATAFORGE_STORAGE_BACKEND", "postgres")
    monkeypatch.setenv("DATAFORGE_ENV", "production")
    monkeypatch.setenv(
        "DATAFORGE_DATABASE_URL",
        "postgresql://user:pass@localhost:5432/db",
    )
    monkeypatch.setenv("DATAFORGE_PG_DRIVER", "psycopg3")

    import app.storage_interface as si

    si.reset_repository()

    try:
        si.get_job_repository()
    except RuntimeError as exc:
        # If the error is about driver selection, that's a fail. Otherwise
        # (e.g. connection error), the driver-selection path succeeded.
        assert "DATAFORGE_PG_DRIVER" not in str(exc), f"Driver-selection must not raise when DATAFORGE_PG_DRIVER=psycopg3: {exc}"
    except Exception:
        # Connectivity errors, module-not-found for psycopg3 driver, etc. are
        # all acceptable — the point is the production gate passed.
        pass

    si.reset_repository()


def test_development_without_pg_driver_uses_sqlite(monkeypatch) -> None:
    """In development without DATAFORGE_STORAGE_BACKEND=postgres, the
    SQLite path should work and the production gate must NOT trigger."""
    monkeypatch.setenv("DATAFORGE_STORAGE_BACKEND", "sqlite")
    monkeypatch.setenv("DATAFORGE_ENV", "development")
    monkeypatch.delenv("DATAFORGE_PG_DRIVER", raising=False)

    import app.storage_interface as si

    si.reset_repository()

    # SQLite path should work without a Postgres driver at all.
    repo = si.get_job_repository()
    assert repo is not None
    si.reset_repository()

"""Tests for storage schema parity between SQLite and Postgres backends.

Verifies that:
- The Postgres ``_JOB_COLUMNS`` set covers at least the columns in SQLite's
  ``_JOBS_COLUMNS_SQL`` list — column drift would mean writes from one
  backend silently drop in another.
- The ``_columns_sql()`` helper (used to generate Postgres CREATE TABLE)
  matches SQLite's columns list exactly.

Catches regressions of the kind reported in the audit:

    Postgres has no `updated_at` column; SQLite does. Writes succeed on
    SQLite then silently drop on Postgres (or error out if strict mode).

This file deliberately does NOT require a Postgres connection — it tests
the schema definition surface only.  Integration tests that exercise the
actual DB engine live in the ``test_postgres_*.py`` modules and require
``--run-postgres``.
"""
from __future__ import annotations

import re

# ─── Surface-level imports ──────────────────────────────────────────────


def test_storage_interface_columns_sql_exists():
    """SQLite's SQLite-only column list must exist on storage_interface."""
    from app.storage_interface import _JOBS_COLUMNS_SQL

    assert isinstance(_JOBS_COLUMNS_SQL, list)
    assert len(_JOBS_COLUMNS_SQL) > 0
    for entry in _JOBS_COLUMNS_SQL:
        assert " " in entry, f"each entry must be a column spec, got: {entry!r}"


def test_postgres_job_columns_frozenset_exists():
    """Postgres's _JOB_COLUMNS must be a frozenset (immutable)."""
    from app.postgres_repository_base import _JOB_COLUMNS

    assert isinstance(_JOB_COLUMNS, frozenset)
    assert len(_JOB_COLUMNS) > 0


def test_postgres_columns_sql_returns_storage_interface_list():
    """The shared _columns_sql() helper must delegate to storage_interface
    so both backends can never drift unknowingly.
    """
    from app.postgres_repository_base import _columns_sql
    from app.storage_interface import _JOBS_COLUMNS_SQL

    assert _columns_sql() == list(_JOBS_COLUMNS_SQL)


# ─── Parity: every SQLite column has Postgres validator entry ──────────


def _sqlite_columns() -> set[str]:
    """Extract column names from SQLite's SQL-DDL list (e.g. 'mode TEXT'
    becomes 'mode')."""
    from app.storage_interface import _JOBS_COLUMNS_SQL

    out: set[str] = set()
    for entry in _JOBS_COLUMNS_SQL:
        first_word = entry.strip().split(" ", 1)[0]
        out.add(first_word)
    return out


def _postgres_columns() -> set[str]:
    from app.postgres_repository_base import _JOB_COLUMNS

    return set(_JOB_COLUMNS)


def test_sqlite_columns_present_in_postgres_columns():
    """Every column the SQLite backend writes must be in the Postgres
    validator set.  Otherwise a SQLite-backed job written via
    ``job_to_row`` survives a Postgres round-trip but the Postgres
    backend rejects the value with ``Unknown column``.

    Special-case: ``id``, ``name``, ``status`` are added by
    ``build_create_jobs_sql`` (``id`` is the primary key, ``name`` and
    ``status`` are prepended explicitly) so they're not in
    ``_JOBS_COLUMNS_SQL``.  Those are tested separately below.
    """
    sqlite_cols = _sqlite_columns()
    postgres_cols = _postgres_columns()

    missing = sqlite_cols - postgres_cols - _POSTGRES_PREPENDED_COLUMNS
    assert not missing, (
        f"SQLite columns not in Postgres _JOB_COLUMNS: {sorted(missing)}. "
        f"This means a SQLite-written row would have Postgres-unknown columns."
    )


def test_postgres_columns_match_sqlite_for_overlap_set():
    """Symmetry check: Postgres-known columns must include all SQLite
    data fields (excluding the prepended id/name/status).
    """
    sqlite_cols = _sqlite_columns()
    postgres_cols = _postgres_columns()

    extra = postgres_cols - sqlite_cols - _POSTGRES_PREPENDED_COLUMNS
    assert not extra, (
        f"Postgres has columns SQLite does not: {sorted(extra)}. "
        f"These would be silently dropped on SQLite round-trip."
    )


def test_updated_at_present_in_postgres():
    """Regression: ``updated_at`` was previously missing from Postgres
    ``_JOB_COLUMNS`` even though SQLite stores it.  This test exists to
    catch the next regression — losing track of when a row was last
    touched is observability bleeds.
    """
    from app.postgres_repository_base import _JOB_COLUMNS

    assert "updated_at" in _JOB_COLUMNS


def test_id_name_status_prepended_to_create_sql():
    """Postgres CREATE TABLE prepends id/name/status.  Empty-string
    defaults for those via SQLite are NOT in ``_JOBS_COLUMNS_SQL`` so
    we enumerate them here as the expected difference.
    """
    from app.postgres_repository_base import build_create_jobs_sql

    sql = build_create_jobs_sql()
    assert "id TEXT PRIMARY KEY" in sql
    assert "name TEXT NOT NULL" in sql
    assert "status TEXT NOT NULL DEFAULT 'pending'" in sql


# ─── Build CREATE TABLE statements and round-trip-detect drift ──────────


def test_create_jobs_sql_contains_updated_at_column():
    """The built Postgres CREATE TABLE statement must include a column
    for ``updated_at`` (otherwise Postgres rows have no last-modified
    timestamp at all — the SQLite side does).
    """
    from app.postgres_repository_base import build_create_jobs_sql

    sql = build_create_jobs_sql()
    # Column definitions look like: "updated_at TEXT DEFAULT ''",
    assert re.search(r"\bupdated_at\s+TEXT\b", sql), (
        f"'updated_at' column missing from Postgres CREATE TABLE: {sql!r}"
    )


def test_create_recycle_bin_sql_contains_updated_at_column():
    from app.postgres_repository_base import build_create_recycle_bin_sql

    sql = build_create_recycle_bin_sql()
    assert re.search(r"\bupdated_at\s+TEXT\b", sql), (
        f"'updated_at' column missing from Postgres CREATE TABLE for recycle_bin: {sql!r}"
    )


def test_create_jobs_sql_symmetric_for_recycle_bin():
    """The jobs and recycle_bin tables must declare identical columns
    (modulo the prepended id/name/status which both add).  Otherwise
    rows preserved by a recycle move are stored against a different
    schema and read back with missing fields."""
    from app.postgres_repository_base import (
        build_create_jobs_sql,
        build_create_recycle_bin_sql,
    )

    jobs_sql = build_create_jobs_sql()
    recycle_sql = build_create_recycle_bin_sql()
    # Strip the table name; the rest must match.
    jobs_body = jobs_sql.replace("CREATE TABLE IF NOT EXISTS jobs", "CREATE TABLE IF NOT EXISTS t")
    recycle_body = recycle_sql.replace(
        "CREATE TABLE IF NOT EXISTS recycle_bin",
        "CREATE TABLE IF NOT EXISTS t",
    )
    assert jobs_body == recycle_body, (
        "jobs and recycle_bin schemas diverge:\n"
        f"JOBS:\n{jobs_sql}\nRECYCLE:\n{recycle_sql}"
    )


# Columns Postgres adds by prepending them in build_create_jobs_sql.
# These don't live in SQLite's _JOBS_COLUMNS_SQL so they're the only
# legitimate asymmetry for the parity checks above.
_POSTGRES_PREPENDED_COLUMNS = frozenset({"id", "name", "status"})

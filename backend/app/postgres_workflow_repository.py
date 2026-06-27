"""Postgres-backed workflow repository.

CAND-P1-WORKFLOW-STORAGE-001: the Postgres workflows table DDL is in
``storage_migrations.py`` v8. This module provides the repository
implementation that round-trips workflow records through it.

Uses the same driver-selection pattern as
:class:`~app.postgres_repository_base.PostgresRepositoryBase`:
the ``_conn()``, ``_fetch_all()``, ``_fetch_one()``, and ``_execute()``
hooks delegate to whichever psycopg driver is active.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from app.workflow_repository import (
    _WORKFLOW_COLUMNS,
    WorkflowRepository,
    _record_to_row,
    _row_to_record,
)

logger = logging.getLogger(__name__)

_DB_OPS_ERRORS: tuple[type[BaseException], ...] = (OSError, RuntimeError, ValueError, TypeError, ImportError)


def register_wf_db_error_class(error_class: type[BaseException]) -> None:
    """Register a driver error type for catch-all blocks."""
    global _DB_OPS_ERRORS
    if error_class not in _DB_OPS_ERRORS:
        _DB_OPS_ERRORS = (*_DB_OPS_ERRORS, error_class)  # type: ignore[misc]


def _try_register_driver_errors() -> None:
    """Attempt to import and register psycopg2/3 error classes."""
    for mod_name in ("psycopg2", "psycopg"):
        try:
            mod = __import__(mod_name)
            err_cls = getattr(mod, "Error", None) or getattr(mod, "DatabaseError", None)
            if err_cls and issubclass(err_cls, BaseException):
                register_wf_db_error_class(err_cls)
        except ImportError as exc:
            logger.debug("Postgres driver %s not available: %s", mod_name, exc)
            pass


_try_register_driver_errors()


class _PostgresWorkflowRepositoryBase(WorkflowRepository, ABC):
    """Abstract base with all shared Postgres workflow CRUD logic.

    Subclasses must implement:
    - ``_conn()`` — context manager yielding a database connection
    - ``_fetch_all(conn, sql, params)`` — execute query, return list[dict]
    - ``_fetch_one(conn, sql, params)`` — execute query, return dict | None
    - ``_execute(conn, sql, params)`` — execute statement, return cursor
    """

    backend = "postgres"

    def __init__(self) -> None:
        self._schema_ensured = False

    @abstractmethod
    @contextmanager
    def _conn(self) -> Iterator:
        """Acquire a connection."""

    @abstractmethod
    def _fetch_all(self, conn, sql: str, params=None) -> list[dict]:
        """Execute query, return all rows as dicts."""

    @abstractmethod
    def _fetch_one(self, conn, sql: str, params=None) -> dict | None:
        """Execute query, return one row or None."""

    @abstractmethod
    def _execute(self, conn, sql: str, params=None):
        """Execute a statement."""

    def _ensure_schema(self) -> None:
        """Ensure the workflows table exists (idempotent)."""
        if self._schema_ensured:
            return
        with self._conn() as conn:
            self._execute(
                conn,
                """
                CREATE TABLE IF NOT EXISTS workflows (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL DEFAULT '',
                    description TEXT DEFAULT '',
                    user_id TEXT DEFAULT '',
                    org_id TEXT DEFAULT '',
                    project_id TEXT DEFAULT '',
                    mode TEXT DEFAULT 'workflow_replay',
                    domain TEXT DEFAULT '',
                    start_url TEXT DEFAULT '',
                    original_url TEXT DEFAULT '',
                    search_params TEXT DEFAULT '{}',
                    steps TEXT DEFAULT '[]',
                    extraction_schema TEXT DEFAULT '[]',
                    pagination_config TEXT DEFAULT '{}',
                    auth_profile_id TEXT DEFAULT NULL,
                    status TEXT DEFAULT 'draft',
                    version INTEGER DEFAULT 1,
                    created_at TEXT DEFAULT '',
                    updated_at TEXT DEFAULT '',
                    last_run_at TEXT DEFAULT '',
                    last_success_at TEXT DEFAULT '',
                    last_failure_reason TEXT DEFAULT '',
                    last_run_job_id TEXT DEFAULT '',
                    total_runs INTEGER DEFAULT 0
                )
                """,
            )
            for idx_sql in [
                "CREATE INDEX IF NOT EXISTS idx_workflows_user_id ON workflows(user_id)",
                "CREATE INDEX IF NOT EXISTS idx_workflows_org_id ON workflows(org_id)",
                "CREATE INDEX IF NOT EXISTS idx_workflows_status ON workflows(status)",
                "CREATE INDEX IF NOT EXISTS idx_workflows_project_id ON workflows(project_id)",
            ]:
                try:
                    self._execute(conn, idx_sql)
                except _DB_OPS_ERRORS:
                    logger.debug("CREATE INDEX failed (ignored): %s", idx_sql)
        self._schema_ensured = True

    # ── Repository interface ───────────────────────────────────────────

    def get(self, workflow_id: str) -> dict[str, Any] | None:
        self._ensure_schema()
        with self._conn() as conn:
            row = self._fetch_one(
                conn,
                "SELECT * FROM workflows WHERE id = %s",
                (workflow_id,),
            )
            if row is None:
                return None
            return _row_to_record(row)

    def list_workflows(
        self,
        *,
        status: str | None = None,
        domain: str | None = None,
        user_id: str | None = None,
        org_id: str | None = None,
        project_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        self._ensure_schema()
        safe_limit = max(1, min(limit, 500))
        safe_offset = max(0, offset)
        clauses: list[str] = []
        params: list[object] = []
        if status:
            clauses.append("status = %s")
            params.append(status)
        if domain:
            clauses.append("LOWER(domain) LIKE %s")
            params.append(f"%{domain.lower()}%")
        if user_id:
            clauses.append("user_id = %s")
            params.append(user_id)
        if org_id:
            clauses.append("org_id = %s")
            params.append(org_id)
        if project_id:
            clauses.append("project_id = %s")
            params.append(project_id)
        where = " AND ".join(clauses) if clauses else "1=1"
        sql = f"SELECT * FROM workflows WHERE {where} ORDER BY created_at DESC LIMIT %s OFFSET %s"  # nosec B608 — column names from _WORKFLOW_COLUMNS constant; params parameterized
        params.extend([safe_limit, safe_offset])
        with self._conn() as conn:
            rows = self._fetch_all(conn, sql, tuple(params))
        return [_row_to_record(r) for r in rows]

    def upsert(self, workflow_id: str, record: dict[str, Any]) -> None:
        self._ensure_schema()
        row = _record_to_row(record)
        cols = ", ".join(_WORKFLOW_COLUMNS)
        placeholders = ", ".join("%s" for _ in _WORKFLOW_COLUMNS)
        update_cols = ", ".join(f"{c} = EXCLUDED.{c}" for c in _WORKFLOW_COLUMNS if c != "id")
        sql = (
            f"INSERT INTO workflows ({cols}) VALUES ({placeholders}) "  # nosec B608 — column names from constant; values param-bound
            f"ON CONFLICT (id) DO UPDATE SET {update_cols}"
        )
        values = [row.get(c) for c in _WORKFLOW_COLUMNS]
        with self._conn() as conn:
            self._execute(conn, sql, values)

    def delete(self, workflow_id: str) -> bool:
        self._ensure_schema()
        with self._conn() as conn:
            cur = self._execute(conn, "DELETE FROM workflows WHERE id = %s", (workflow_id,))
            return (cur.rowcount or 0) > 0

    def count_workflows(self) -> int:
        self._ensure_schema()
        try:
            with self._conn() as conn:
                row = self._fetch_one(conn, "SELECT COUNT(*) AS cnt FROM workflows")
                return int(row["cnt"]) if row else 0
        except _DB_OPS_ERRORS:
            logger.exception("count_workflows failed")
            return 0

    def health_check(self) -> dict[str, Any]:
        try:
            count = self.count_workflows()
            return {"ok": True, "backend": self.backend, "workflow_count": count}
        except _DB_OPS_ERRORS as e:
            return {"ok": False, "backend": self.backend, "error": str(e)}


class PostgresWorkflowRepository(_PostgresWorkflowRepositoryBase):
    """psycopg2-backed workflow repository.

    Reuses the shared connection pool from
    :mod:`app.postgres_repository`.
    """

    backend = "postgres"

    def __init__(self) -> None:
        super().__init__()
        from app.postgres_repository import _get_pool

        self._get_pool = _get_pool

    @contextmanager
    def _conn(self) -> Iterator:
        pool = self._get_pool()
        conn = pool.getconn()
        try:
            yield conn
        finally:
            pool.putconn(conn)

    def _fetch_all(self, conn, sql: str, params=None) -> list[dict]:
        import psycopg2.extras

        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]

    def _fetch_one(self, conn, sql: str, params=None) -> dict | None:
        import psycopg2.extras

        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
            return dict(row) if row else None

    def _execute(self, conn, sql: str, params=None):
        with conn.cursor() as cur:
            cur.execute(sql, params)
            conn.commit()
            return cur


class Psycopg3WorkflowRepository(_PostgresWorkflowRepositoryBase):
    """psycopg3-backed workflow repository.

    Reuses the shared connection pool from
    :mod:`app.psycopg3_repository`.
    """

    backend = "postgres-psycopg3"

    def __init__(self) -> None:
        super().__init__()
        from app.psycopg3_repository import _get_pool

        self._get_pool = _get_pool

    @contextmanager
    def _conn(self) -> Iterator:
        pool = self._get_pool()
        with pool.connection() as conn:
            yield conn

    def _fetch_all(self, conn, sql: str, params=None) -> list[dict]:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            cols = [desc[0] for desc in cur.description or []]
            return [dict(zip(cols, row, strict=False)) for row in cur.fetchall()]

    def _fetch_one(self, conn, sql: str, params=None) -> dict | None:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
            if row is None:
                return None
            cols = [desc[0] for desc in cur.description or []]
            return dict(zip(cols, row, strict=False))

    def _execute(self, conn, sql: str, params=None):
        with conn.cursor() as cur:
            cur.execute(sql, params)
            conn.commit()
            return cur

"""Workflow repository — ABC, backends, and factory.

CAND-P1-WORKFLOW-STORAGE-001: adds repository-backed workflow storage
with SQLite and Postgres parity so workflow definitions survive
container lifecycle events and tenant-scoped queries use indexed
database lookups rather than O(N) full-scan reads of a flat JSON file.

The default backend is ``"json"`` which wraps the existing
:class:`~app.utils.json_file_store.JSONFileStore` — zero behaviour
change for existing deployments. Operators opt in to database-backed
storage by setting ``DATAFORGE_WORKFLOW_BACKEND=sqlite`` (or
``postgres``).

The ``workflows`` table DDL already exists in both SQLite (migration
v9) and Postgres (migration v8) — this module wires the router to it.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_WORKFLOW_REPO_LOCK = threading.Lock()
_workflow_repo_instance: WorkflowRepository | None = None

# JSON columns stored as text in the DB, deserialised on read.
_LIST_JSON_COLS: frozenset[str] = frozenset({"steps", "extraction_schema"})
_DICT_JSON_COLS: frozenset[str] = frozenset({"search_params", "pagination_config"})
_ALL_JSON_COLS: frozenset[str] = _LIST_JSON_COLS | _DICT_JSON_COLS

# Canonical column order matching storage_migrations.py v9/v8 DDL.
_WORKFLOW_COLUMNS: tuple[str, ...] = (
    "id",
    "name",
    "description",
    "user_id",
    "org_id",
    "project_id",
    "mode",
    "domain",
    "start_url",
    "original_url",
    "search_params",
    "steps",
    "extraction_schema",
    "pagination_config",
    "auth_profile_id",
    "status",
    "version",
    "created_at",
    "updated_at",
    "last_run_at",
    "last_success_at",
    "last_failure_reason",
    "last_run_job_id",
    "total_runs",
)


# ── Helpers ─────────────────────────────────────────────────────────────


def _record_to_row(record: dict[str, Any]) -> dict[str, Any]:
    """Serialize a workflow dict for DB storage.

    JSON-valued columns (steps, extraction_schema, search_params,
    pagination_config) are serialised to text; all others are
    passed through unchanged.
    """
    row: dict[str, Any] = {}
    for col in _WORKFLOW_COLUMNS:
        val = record.get(col)
        if col in _ALL_JSON_COLS and val is not None and not isinstance(val, str):
            val = json.dumps(val, default=str)
        row[col] = val
    return row


def _row_to_record(row: dict[str, Any]) -> dict[str, Any]:
    """Deserialize a DB row dict back into a workflow record.

    JSON-valued columns are parsed back to Python objects.
    """
    record: dict[str, Any] = {}
    for col in _WORKFLOW_COLUMNS:
        val = row.get(col)
        if col in _ALL_JSON_COLS and isinstance(val, str):
            try:
                val = json.loads(val)
            except (json.JSONDecodeError, TypeError):
                val = [] if col in _LIST_JSON_COLS else {}
        record[col] = val
    # Carry forward any extra keys that exist in the row (e.g. from
    # schema evolution) so round-trips are lossless for unknown cols.
    for k, v in row.items():
        if k not in record:
            record[k] = v
    return record


# ── Abstract base ────────────────────────────────────────────────────────


class WorkflowRepository(ABC):
    """Abstract repository for workflow definitions.

    CAND-P1-WORKFLOW-STORAGE-001: each backend must preserve owner/
    org/project fields and survive process restarts.
    """

    @abstractmethod
    def get(self, workflow_id: str) -> dict[str, Any] | None:
        """Return a single workflow by id, or None."""

    @abstractmethod
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
        """Return workflows matching the given filters."""

    @abstractmethod
    def upsert(self, workflow_id: str, record: dict[str, Any]) -> None:
        """Insert or replace a workflow record."""

    @abstractmethod
    def delete(self, workflow_id: str) -> bool:
        """Delete a workflow. Return True if a row was removed."""

    @abstractmethod
    def delete_by_user(self, user_id: str) -> int:
        """Atomically delete every workflow owned by *user_id*.

        Performs the ownership check and the delete inside the same
        transaction / file-lock so a concurrent ``upsert`` cannot
        leak a row whose ``user_id`` was reassigned. Returns the
        number of records removed.

        Used by the GDPR / delete-my-data pipeline.
        """

    @abstractmethod
    def count_workflows(self) -> int:
        """Return the total number of workflow rows."""

    @abstractmethod
    def health_check(self) -> dict[str, Any]:
        """Return a health dict with at least ``backend`` and ``ok`` keys."""

    def transform(
        self,
        workflow_id: str,
        fn: Callable[[dict[str, Any]], dict[str, Any] | None],
    ) -> dict[str, Any] | None:
        """Atomically transform a workflow inside the store's lock.

        Default implementation: ``get`` + callback + ``upsert``.
        Backends with native atomic read-modify-write SHOULD override
        this to hold the store lock across the full read-transform-
        write span, so concurrent counter bumps on the same workflow
        id do not race.

        Returns the post-transform record, or ``None`` if *fn* returned
        ``None`` / the record does not exist.
        """
        existing = self.get(workflow_id)
        if existing is None:
            return None
        transformed = fn(dict(existing))
        if transformed is not None:
            self.upsert(workflow_id, transformed)
        return transformed


# ── JSON adapter (default, backward-compatible) ──────────────────────────


class JsonWorkflowRepository(WorkflowRepository):
    """Thin adapter over :class:`~app.utils.json_file_store.JSONFileStore`.

    This is the default backend so existing deployments get zero
    behaviour change. The adapter satisfies the
    :class:`WorkflowRepository` contract using the file-backed store
    under the hood.
    """

    backend = "json"

    def __init__(self, store: Any | None = None) -> None:
        # Lazy import to avoid circulars at module level.
        if store is not None:
            self._store = store
        else:
            from app.utils.json_file_store import JSONFileStore

            default_path = Path(__file__).resolve().parents[1] / "data" / "workflows.json"
            self._store = JSONFileStore(default_path)

    def get(self, workflow_id: str) -> dict[str, Any] | None:
        return self._store.get(workflow_id)

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
        items = list(self._store.values())
        if status:
            items = [w for w in items if w.get("status") == status]
        if domain:
            d_lower = domain.lower()
            items = [w for w in items if d_lower in (w.get("domain") or "").lower()]
        if user_id:
            items = [w for w in items if w.get("user_id") == user_id]
        if org_id:
            items = [w for w in items if w.get("org_id") == org_id]
        if project_id:
            items = [w for w in items if w.get("project_id") == project_id]
        return items[offset : offset + limit]

    def upsert(self, workflow_id: str, record: dict[str, Any]) -> None:
        self._store.upsert(workflow_id, record)

    def transform(
        self,
        workflow_id: str,
        fn: Callable[[dict[str, Any]], dict[str, Any] | None],
    ) -> dict[str, Any] | None:
        """Atomic read-transform-write under the JSONFileStore lock."""
        return self._store.transform(workflow_id, fn)

    def delete(self, workflow_id: str) -> bool:
        return self._store.delete(workflow_id)

    def delete_by_user(self, user_id: str) -> int:
        """Atomic delete of *user_id*'s workflows inside one flocked RMW.

        Pushes the ownership predicate into the store so the read,
        filter, and delete all happen inside the same
        ``_read_modify_write`` lock. Eliminates the TOCTOU window
        previously created by ``_store.values()`` + ``delete_many``.
        """
        predicate = lambda rec, _uid=user_id: rec.get("user_id") == _uid  # noqa: E731
        return self._store.delete_where(predicate)

    def count_workflows(self) -> int:
        return len(self._store)

    def health_check(self) -> dict[str, Any]:
        return {"ok": True, "backend": self.backend}


# ── SQLite backend ──────────────────────────────────────────────────────


class SQLiteWorkflowRepository(WorkflowRepository):
    """SQLite-backed workflow repository using the v9 ``workflows`` table.

    Reuses the :func:`app.job_store._get_connection` /
    :data:`app.job_store._DB_LOCK` pattern so workflows land in the
    same database as jobs — same journal-mode, same migration
    pipeline.

    On first construction, if the ``workflows`` table is empty and
    ``workflows.json`` exists with data, performs a one-shot backfill
    (idempotent — re-constructing the repo does not re-import).
    """

    backend = "sqlite"

    def __init__(self) -> None:
        self._backfill_done = False
        # Round-9 fix: guard the backfill flag so concurrent first-callers
        # (e.g. get() and list_workflows() racing on a fresh process)
        # don't both pass the check-then-set, both set the flag, and
        # both run the full upsert loop. The upserts are idempotent
        # (ON CONFLICT) so no data corruption — only wasted duplicate
        # work, which we now avoid.
        self._backfill_lock = threading.Lock()

    def _maybe_backfill_from_json(self) -> None:
        """One-shot import from workflows.json to SQLite.

        Reuses the deserialization logic from the
        JSON-to-SQLite migration but runs
        in-process so the router can switch backends without a
        separate migration step.

        Safe to call multiple times — the ``_backfill_done`` flag
        and the non-empty table check make it a no-op.
        """
        if self._backfill_done:
            return
        with self._backfill_lock:
            if self._backfill_done:
                return
            self._backfill_done = True
            try:
                count = self.count_workflows()
                if count > 0:
                    return  # table already populated — nothing to import
            except (RuntimeError, OSError, ValueError, TypeError, KeyError, IndexError, AttributeError):
                return  # table may not exist yet — migrations will create it

        json_path = Path(__file__).resolve().parents[1] / "data" / "workflows.json"
        if not json_path.exists():
            return

        try:
            with json_path.open("r", encoding="utf-8") as f:
                raw = json.load(f)
        except (OSError, ValueError, TypeError):
            logger.warning("workflows.json unreadable; skipping backfill")
            return
        if not isinstance(raw, dict) or not raw:
            return

        logger.info("Backfilling workflows from %s (%d records)", json_path, len(raw))
        for wf_id, record in raw.items():
            if isinstance(record, dict) and wf_id:
                self.upsert(wf_id, record)
        logger.info("Backfill complete: %d workflows imported", len(raw))

    def _db_connection(self) -> sqlite3.Connection:
        from app.job_store import _get_connection

        return _get_connection()

    def get(self, workflow_id: str) -> dict[str, Any] | None:
        from app.job_store import _DB_LOCK

        self._maybe_backfill_from_json()
        with _DB_LOCK:
            conn = self._db_connection()
            try:
                cursor = conn.execute(
                    "SELECT * FROM workflows WHERE id = ?",
                    (workflow_id,),
                )
                row = cursor.fetchone()
                if row is None:
                    return None
                keys = [desc[0] for desc in cursor.description]
                return _row_to_record(dict(zip(keys, row, strict=False)))
            finally:
                conn.close()

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
        from app.job_store import _DB_LOCK

        self._maybe_backfill_from_json()
        safe_limit = max(1, min(limit, 500))
        safe_offset = max(0, offset)
        clauses: list[str] = []
        params: list[object] = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if domain:
            clauses.append("LOWER(domain) LIKE ?")
            params.append(f"%{domain.lower()}%")
        if user_id:
            clauses.append("user_id = ?")
            params.append(user_id)
        if org_id:
            clauses.append("org_id = ?")
            params.append(org_id)
        if project_id:
            clauses.append("project_id = ?")
            params.append(project_id)
        where = " AND ".join(clauses) if clauses else "1=1"
        sql = f"SELECT * FROM workflows WHERE {where} ORDER BY created_at DESC LIMIT ? OFFSET ?"  # nosec B608 — column names from _WORKFLOW_COLUMNS constant; params parameterized
        params.extend([safe_limit, safe_offset])

        with _DB_LOCK:
            conn = self._db_connection()
            try:
                rows = conn.execute(sql, params).fetchall()
                keys = [desc[0] for desc in conn.execute("SELECT * FROM workflows LIMIT 0").description]  # type: ignore[union-attr]
                return [_row_to_record(dict(zip(keys, r, strict=False))) for r in rows]
            finally:
                conn.close()

    def upsert(self, workflow_id: str, record: dict[str, Any]) -> None:
        from app.job_store import _DB_LOCK

        self._maybe_backfill_from_json()
        row = _record_to_row(record)
        cols = ", ".join(_WORKFLOW_COLUMNS)
        placeholders = ", ".join("?" for _ in _WORKFLOW_COLUMNS)
        update_cols = ", ".join(f"{c} = EXCLUDED.{c}" for c in _WORKFLOW_COLUMNS if c != "id")
        sql = (
            f"INSERT INTO workflows ({cols}) VALUES ({placeholders}) "  # nosec B608 — column names from constant; values param-bound
            f"ON CONFLICT (id) DO UPDATE SET {update_cols}"
        )
        values = [row.get(c) for c in _WORKFLOW_COLUMNS]

        with _DB_LOCK:
            conn = self._db_connection()
            try:
                conn.execute(sql, values)
                conn.commit()
            except (RuntimeError, OSError, ValueError, TypeError, KeyError, IndexError, AttributeError):
                conn.rollback()
                raise
            finally:
                conn.close()

    def delete(self, workflow_id: str) -> bool:
        from app.job_store import _DB_LOCK

        with _DB_LOCK:
            conn = self._db_connection()
            try:
                cur = conn.execute("DELETE FROM workflows WHERE id = ?", (workflow_id,))
                conn.commit()
                return cur.rowcount > 0
            except (RuntimeError, OSError, ValueError, TypeError, KeyError, IndexError, AttributeError):
                conn.rollback()
                raise
            finally:
                conn.close()

    def delete_by_user(self, user_id: str) -> int:
        """Atomic delete of *user_id*'s workflows in a single SQL statement.

        ``DELETE FROM workflows WHERE user_id = ?`` evaluates the
        ownership predicate on the rows visible at delete time under
        the existing ``_DB_LOCK``. This is materially safer than the
        previous ``list_workflows(user_id=...)`` + ``repo.delete(id)``
        loop, where a concurrent ``upsert`` could reassign a row's
        ``user_id`` between the snapshot and the per-row delete (or
        insert a new row after the snapshot that would never be
        inspected and so could leak the user's data without being
        deleted).
        """
        from app.job_store import _DB_LOCK

        with _DB_LOCK:
            conn = self._db_connection()
            try:
                cur = conn.execute(
                    "DELETE FROM workflows WHERE user_id = ?",
                    (user_id,),
                )
                conn.commit()
                return cur.rowcount
            except (RuntimeError, OSError, ValueError, TypeError, KeyError, IndexError, AttributeError):
                conn.rollback()
                raise
            finally:
                conn.close()

    def count_workflows(self) -> int:
        from app.job_store import _DB_LOCK

        self._maybe_backfill_from_json()
        with _DB_LOCK:
            conn = self._db_connection()
            try:
                row = conn.execute("SELECT COUNT(*) FROM workflows").fetchone()
                return int(row[0]) if row else 0
            finally:
                conn.close()

    def health_check(self) -> dict[str, Any]:
        try:
            count = self.count_workflows()
            return {"ok": True, "backend": self.backend, "workflow_count": count}
        except (RuntimeError, OSError, ValueError, TypeError, KeyError, IndexError, AttributeError, ImportError) as exc:
            return {"ok": False, "backend": self.backend, "error": str(exc)}


# ── Factory ─────────────────────────────────────────────────────────────


def get_workflow_repository() -> WorkflowRepository:
    """Resolve the appropriate WorkflowRepository based on configuration.

    Priority:
    1. ``DATAFORGE_WORKFLOW_BACKEND`` env var (``json``, ``sqlite``, ``postgres``)
    2. ``settings.WORKFLOW_BACKEND`` (defaults to ``"json"``)

    The repository is cached as a module-level singleton so all callers
    share the same instance.
    """
    global _workflow_repo_instance
    if _workflow_repo_instance is not None:
        return _workflow_repo_instance

    with _WORKFLOW_REPO_LOCK:
        if _workflow_repo_instance is not None:
            return _workflow_repo_instance

        backend = os.environ.get("DATAFORGE_WORKFLOW_BACKEND", "").strip().lower()
        if not backend:
            try:
                from app.config import settings

                backend = (getattr(settings, "WORKFLOW_BACKEND", "") or "").strip().lower()
            except ImportError as exc:
                logger.debug("Could not import settings for workflow backend detection: %s", exc)
        if not backend:
            backend = "json"

        if backend == "json":
            repo: WorkflowRepository = JsonWorkflowRepository()
            _workflow_repo_instance = repo
            logger.info("Using JsonWorkflowRepository (WORKFLOW_BACKEND=json)")
            return repo

        if backend == "sqlite":
            repo = SQLiteWorkflowRepository()
            _workflow_repo_instance = repo
            logger.info("Using SQLiteWorkflowRepository (WORKFLOW_BACKEND=sqlite)")
            return repo

        if backend == "postgres":
            try:
                from app.postgres_workflow_repository import PostgresWorkflowRepository

                repo = PostgresWorkflowRepository()
                _workflow_repo_instance = repo
                logger.info("Using PostgresWorkflowRepository (WORKFLOW_BACKEND=postgres)")
                return repo
            except (ImportError, RuntimeError) as e:
                msg = f"Failed to create PostgresWorkflowRepository: {e}. Set DATAFORGE_DATABASE_URL."
                raise RuntimeError(msg) from e

        msg = f"Unknown DATAFORGE_WORKFLOW_BACKEND={backend!r}. Use 'json', 'sqlite', or 'postgres'."
        raise ValueError(msg)


def reset_workflow_repository() -> None:
    """Reset the cached workflow repository instance (for testing)."""
    global _workflow_repo_instance
    _workflow_repo_instance = None

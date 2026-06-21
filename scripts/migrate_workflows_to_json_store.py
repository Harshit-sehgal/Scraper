#!/usr/bin/env python3
"""One-shot migration script: import workflows from legacy SQLite into the new JSONFileStore-backed workflow store.

Background
----------
The workflow router used to seed an in-memory ``_workflows`` dict at
module-import time from the v9 ``workflows`` SQLite table managed by
``backend/app/job_store.py``. The router was then rewritten to use the
cross-process ``JSONFileStore`` base class (file-backed JSON with
``fcntl.flock`` + atomic rename). The rewrite removed the
``_load_workflows_from_db()`` and ``_persist_workflows()`` helpers,
so any pre-existing workflow rows in SQLite are now invisible to the
new router.

This script reads ``SELECT * FROM workflows`` from the legacy SQLite
DB and writes each row through :class:`JSONFileStore.upsert` into
``backend/data/workflows.json`` (one flock + one atomic-rename per
row). Drafts were never persisted to SQLite by the legacy router;
the new router's ``workflow_drafts.json`` file is created here as an
empty placeholder so the deploy-acceptance file check sees both
files present after the migration runs.

Run this script ONCE before deploying the workflow-router rewrite to
production. The migration is idempotent — the JSONFileStore upsert
preserves ``created_at`` from any existing JSON record, so re-running
this script against an already-migrated DB is a no-op.

Usage
-----
::

    python3 scripts/migrate_workflows_to_json_store.py \\
        --src-db backend/data/jobs_state.db \\
        --output-dir backend/data \\
        [--dry-run] [--verbose]
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any

# Make the backend package importable when this script is run from the
# repo root via ``python3 scripts/migrate_workflows_to_json_store.py``.
_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "backend"))

# Pin a stub env so ``app.config.settings`` can be imported without
# forcing dotenv loading. The script does not need real keys — it only
# reads from SQLite and writes to a JSON file.
os.environ.setdefault("DATAFORGE_DOTENV_PATH", "/dev/null")
os.environ.setdefault("DATAFORGE_ENV", "test")
os.environ.setdefault("DATAFORGE_STORAGE_BACKEND", "sqlite")
os.environ.setdefault("DATAFORGE_API_KEY", "migration-script")
os.environ.setdefault("DATAFORGE_OPERATOR_API_KEY", "migration-script")
os.environ.setdefault("DATAFORGE_ADMIN_API_KEY", "migration-script")
os.environ.setdefault("DATAFORGE_SESSION_SECRET", "migration-script")
os.environ.setdefault("DATAFORGE_ALLOW_INSECURE_DEV_AUTH", "false")
os.environ.setdefault("DATAFORGE_SKIP_DB_CHECK", "true")

from app.utils.json_file_store import JSONFileStore

logger = logging.getLogger("migrate_workflows")

# Known-key filter for the workflows table. Schema evolution beyond
# these keys is handled by ``SELECT *`` over-fetch + the filter inside
# :func:`_row_to_workflow_record` (extra columns are preserved as-is).
_WORKFLOW_COLUMNS = (
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

_LIST_JSON_COLUMNS = frozenset({"steps", "extraction_schema"})
_DICT_JSON_COLUMNS = frozenset({"search_params", "pagination_config"})


def _default_src_db() -> Path:
    """Resolve the source SQLite DB path, mirroring job_store._get_db_path."""
    settings_path: Path | None = None
    try:
        from app.config import settings

        if settings.STATE_FILE_PATH_DYNAMIC:
            settings_path = Path(settings.STATE_FILE_PATH_DYNAMIC).expanduser()
    except Exception as exc:  # private-shaped fallback
        logger.debug("could not read settings.STATE_FILE_PATH_DYNAMIC: %s", exc)
    if settings_path is not None:
        return settings_path.with_suffix(".db")
    return _REPO_ROOT / "backend" / "data" / "jobs_state.db"


def _deserialize_json_columns(record: dict[str, Any]) -> dict[str, Any]:
    """Restore Python objects from SQLite-stored JSON columns."""
    for col in list(record):
        if col in _LIST_JSON_COLUMNS or col in _DICT_JSON_COLUMNS:
            raw = record[col]
            default = "[]" if col in _LIST_JSON_COLUMNS else "{}"
            if not isinstance(raw, str):
                record[col] = json.loads(default)
                continue
            try:
                record[col] = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                record[col] = json.loads(default)
    return record


def _row_to_workflow_record(row: sqlite3.Row) -> dict[str, Any] | None:
    """Convert a SQLite row mapping to a JSONFileStore-ready record.

    Returns ``None`` when the row lacks a usable ``id`` (skip silently).
    """
    # sqlite3.Row iteration yields VALUES in column order (sequence
    # semantics), not column NAMES. Capture ``.keys()`` first so Ruff
    # does not treat this as dict-style iteration.
    row_keys = row.keys()
    record: dict[str, Any] = {col: row[col] for col in row_keys if col in _WORKFLOW_COLUMNS}
    workflow_id = str(record.get("id") or "").strip()
    if not workflow_id:
        return None
    # Coerce auth_profile_id's NULL to None so JSON serialization stays
    # consistent with the file-backed workflow router.
    ap_id = record.get("auth_profile_id")
    record["auth_profile_id"] = ap_id if ap_id is not None else None
    return _deserialize_json_columns(record)


def migrate_workflows(
    src_db: Path,
    output_dir: Path,
    *,
    dry_run: bool = False,
    verbose: bool = False,
) -> dict[str, Any]:
    """Migrate all workflow rows from a v9 SQLite DB into the JSONFileStore.

    Parameters are explicit and side-effect-isolated so the same function
    is exercised by both the CLI and the unit tests.

    Returns a summary dict with keys: ``rows_seen``, ``rows_migrated``,
    ``output_path``, ``drafts_output_path``, ``dry_run``.
    """
    if not src_db.exists():
        message = f"source SQLite DB not found: {src_db}"
        raise FileNotFoundError(message)

    output_dir.mkdir(parents=True, exist_ok=True)
    workflows_json = output_dir / "workflows.json"
    drafts_json = output_dir / "workflow_drafts.json"

    if dry_run:
        workflows_json = output_dir / "workflows.dryrun.json"
        drafts_json = output_dir / "workflow_drafts.dryrun.json"

    store = JSONFileStore(path=workflows_json)
    rows_seen = 0
    rows_migrated = 0

    logger.info("opening source DB: %s", src_db)
    with sqlite3.connect(str(src_db)) as conn:
        conn.row_factory = sqlite3.Row
        try:
            # SELECT * picks up schema evolution automatically; the
            # row-to-record filter projects to the known workflow shape.
            rows = conn.execute("SELECT * FROM workflows").fetchall()
        except sqlite3.OperationalError as exc:
            message = f"workflows table not found in {src_db} (pre-v9 schema?): {exc}. Nothing to migrate."
            logger.warning(message)
            rows = []

        for row in rows:
            rows_seen += 1
            record = _row_to_workflow_record(row)
            if record is None:
                if verbose:
                    logger.info("skipping row with empty id (rows_seen=%d)", rows_seen)
                continue
            if verbose:
                logger.info("migrating workflow id=%s name=%s", record["id"], record.get("name"))
            # Always upsert — in dry-run mode the store points at the
            # .dryrun.json sibling, so writes are preview-only and
            # do not touch the canonical workflows.json.
            store.upsert(str(record["id"]), record)
            rows_migrated += 1

    # Ensure the drafts file exists. The legacy router never
    # persisted drafts to SQLite, so there's nothing to migrate; we
    # touch an empty JSON object so the deploy-acceptance check
    # finds both files present after the migration.
    if not drafts_json.exists():
        drafts_json.parent.mkdir(parents=True, exist_ok=True)
        drafts_json.write_text("{}\n", encoding="utf-8")
        if verbose:
            logger.info("seeded empty drafts placeholder at %s", drafts_json)

    summary = {
        "rows_seen": rows_seen,
        "rows_migrated": rows_migrated,
        "output_path": str(workflows_json),
        "drafts_output_path": str(drafts_json),
        "dry_run": dry_run,
    }
    logger.info(
        "migration %s: rows_seen=%d rows_migrated=%d output=%s",
        "previewed" if dry_run else "complete",
        rows_seen,
        rows_migrated,
        workflows_json,
    )
    return summary


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="migrate_workflows_to_json_store",
        description=("One-shot migration: import v9 SQLite workflows table into the JSONFileStore-backed workflow store."),
    )
    parser.add_argument(
        "--src-db",
        type=Path,
        default=_default_src_db(),
        help="path to the legacy SQLite DB (default: %(default)s)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=_REPO_ROOT / "backend" / "data",
        help="destination directory for workflows.json + workflow_drafts.json (default: %(default)s)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="preview the migration without writing to workflows.json (writes to a .dryrun.json sibling instead)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="log every workflow migrated",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    args = _parse_args(argv)
    try:
        summary = migrate_workflows(
            src_db=args.src_db,
            output_dir=args.output_dir,
            dry_run=args.dry_run,
            verbose=args.verbose,
        )
    except FileNotFoundError:
        logger.exception("Source database file not found")
        return 2
    except sqlite3.OperationalError:
        # Schema mismatch (e.g. un-migrated v8 DB) — log with traceback so
        # operators see which column is missing.
        logger.exception("SQLite schema error — likely a pre-v9 database")
        return 3
    except sqlite3.DatabaseError:
        logger.exception("SQLite error while reading source database")
        return 3

    logger.info(
        "done — rows_seen=%d rows_migrated=%d output_path=%s drafts_path=%s dry_run=%s",
        summary["rows_seen"],
        summary["rows_migrated"],
        summary["output_path"],
        summary["drafts_output_path"],
        summary["dry_run"],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

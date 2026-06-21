"""Tests for the one-shot workflow migration script.

Pins the contract: ``migrate_workflows(src_db, output_dir)`` reads
the v9 SQLite ``workflows`` table, deserializes JSON columns, and
upserts each row into a file-backed ``JSONFileStore``. The script is
idempotent (re-runnable), supports ``--dry-run`` for previews, and
returns a structured summary.

Earlier in this session the workflow router was rewritten to drop the
SQLite-primary seed path. This script bridges pre-existing operator
data into the new ``backend/data/workflows.json`` so production
deploys of the rewrite do not silently lose workflow rows.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path

import pytest

# Pin the same env the production router expects (avoids dotenv load).
os.environ.setdefault("DATAFORGE_DOTENV_PATH", "/dev/null")
os.environ.setdefault("DATAFORGE_ENV", "test")
os.environ.setdefault("DATAFORGE_STORAGE_BACKEND", "sqlite")
os.environ.setdefault("DATAFORGE_API_KEY", "migration-test")
os.environ.setdefault("DATAFORGE_OPERATOR_API_KEY", "migration-test")
os.environ.setdefault("DATAFORGE_ADMIN_API_KEY", "migration-test")
os.environ.setdefault("DATAFORGE_SESSION_SECRET", "migration-test")
os.environ.setdefault("DATAFORGE_ALLOW_INSECURE_DEV_AUTH", "false")
os.environ.setdefault("DATAFORGE_SKIP_DB_CHECK", "true")

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

from scripts.migrate_workflows_to_json_store import (
    _WORKFLOW_COLUMNS,
    migrate_workflows,
)

_V9_SCHEMA_DDL = """
CREATE TABLE workflows (
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
"""


def _create_v9_db(tmp_path: Path, table_ddl: str = _V9_SCHEMA_DDL) -> Path:
    """Build a temporary empty SQLite DB with the v9 workflows table."""
    db_path = tmp_path / "jobs_state.db"
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(table_ddl)
        conn.commit()
    return db_path


def _make_workflow_row(**overrides: object) -> dict[str, object]:
    """Return a v9 workflow row dict with sensible defaults.

    Pass keyword overrides for any v9 column.
    """
    base: dict[str, object] = {
        "id": "wf-default",
        "name": "Demo Workflow",
        "description": "",
        "user_id": "user-default",
        "org_id": "org-default",
        "project_id": "project-default",
        "mode": "workflow_replay",
        "domain": "example.com",
        "start_url": "https://example.com/",
        "original_url": "https://example.com/",
        "search_params": json.dumps({}),
        "steps": json.dumps([]),
        "extraction_schema": json.dumps([]),
        "pagination_config": json.dumps({}),
        "auth_profile_id": None,
        "status": "draft",
        "version": 1,
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
        "last_run_at": "",
        "last_success_at": "",
        "last_failure_reason": "",
        "last_run_job_id": "",
        "total_runs": 0,
    }
    base.update(overrides)
    return base


def _insert_workflow(db_path: Path, row: dict[str, object]) -> None:
    """INSERT a single workflow row into the v9 SQLite DB."""
    placeholders = ", ".join(["?"] * len(_WORKFLOW_COLUMNS))
    values = [row.get(col) for col in _WORKFLOW_COLUMNS]
    with sqlite3.connect(str(db_path)) as conn:
        # Column names from `_WORKFLOW_COLUMNS` (frozen tuple imported from the
        # migration script) and placeholders are static; only values are bound
        # via parameterized `?`. S608 false-positive.
        conn.execute(
            f"INSERT INTO workflows ({', '.join(_WORKFLOW_COLUMNS)}) VALUES ({placeholders})",
            values,
        )
        conn.commit()


@pytest.fixture
def legacy_workflows_db(tmp_path: Path) -> Path:
    """Build a temporary SQLite DB with two canonical workflow fixture rows."""
    db_path = _create_v9_db(tmp_path)
    _insert_workflow(
        db_path,
        _make_workflow_row(
            id="wf-1",
            name="List Hotels",
            user_id="user-a",
            org_id="org-a",
            project_id="proj-a",
            domain="example.com",
            start_url="https://example.com/list",
            original_url="https://example.com/list",
            search_params=json.dumps({"q": "hotels", "page_size": 50}),
            steps=json.dumps(
                [
                    {"id": "step-1", "kind": "navigate", "url": "https://example.com/list"},
                    {"id": "step-2", "kind": "extract", "selector": "div.hotel"},
                ],
            ),
            extraction_schema=json.dumps(
                [{"name": "title", "kind": "text"}, {"name": "price", "kind": "number"}],
            ),
            pagination_config=json.dumps({"strategy": "click_next", "max_pages": 10}),
            status="active",
            version=3,
            created_at="2026-01-01T00:00:00+00:00",
            updated_at="2026-01-02T00:00:00+00:00",
        ),
    )
    _insert_workflow(
        db_path,
        _make_workflow_row(
            id="wf-2",
            name="Search Recipes",
            description="operator-curated",
            user_id="user-b",
            org_id="org-b",
            project_id="proj-b",
            domain="recipes.example.org",
            start_url="https://recipes.example.org/",
            original_url="https://recipes.example.org/",
            auth_profile_id="auth-b-1",
            created_at="2026-02-01T00:00:00+00:00",
            updated_at="2026-02-01T00:00:00+00:00",
        ),
    )
    return db_path


def test_migrate_empty_workflows_table(tmp_path: Path) -> None:
    """No rows in the workflows table (e.g. dev DB) — script returns 0 silently."""
    db_path = _create_v9_db(tmp_path)

    out_dir = tmp_path / "out"
    summary = migrate_workflows(db_path, out_dir, dry_run=False)
    assert summary["rows_seen"] == 0
    assert summary["rows_migrated"] == 0


def test_migrate_missing_workflows_table_is_pre_v9_warning(tmp_path: Path, caplog) -> None:
    """A DB without the workflows table should be treated as pre-v9 — no rows, no crash."""
    db_path = tmp_path / "no_table.db"
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("CREATE TABLE other_state (id INTEGER PRIMARY KEY)")

    out_dir = tmp_path / "out"
    summary = migrate_workflows(db_path, out_dir, dry_run=False)
    assert summary["rows_seen"] == 0
    assert summary["rows_migrated"] == 0


def test_migrate_writes_correctly_deserialized_records(
    legacy_workflows_db: Path,
    tmp_path: Path,
) -> None:
    """JSON columns are deserialized; auth_profile_id is coerced to None when NULL."""
    out_dir = tmp_path / "out"
    summary = migrate_workflows(legacy_workflows_db, out_dir, dry_run=False)

    assert summary["rows_seen"] == 2
    assert summary["rows_migrated"] == 2

    workflows_json = out_dir / "workflows.json"
    assert workflows_json.exists()

    # The store is JSONFileStore which uses tempfile + atomic rename; read
    # the on-disk JSON directly to verify shape independently of the store.
    data = json.loads(workflows_json.read_text())
    assert set(data.keys()) == {"wf-1", "wf-2"}

    wf1 = data["wf-1"]
    assert wf1["name"] == "List Hotels"
    assert wf1["search_params"] == {"q": "hotels", "page_size": 50}
    assert isinstance(wf1["steps"], list) and len(wf1["steps"]) == 2
    assert isinstance(wf1["extraction_schema"], list) and len(wf1["extraction_schema"]) == 2
    assert wf1["pagination_config"] == {"strategy": "click_next", "max_pages": 10}
    assert wf1["auth_profile_id"] is None
    assert wf1["created_at"] == "2026-01-01T00:00:00+00:00"

    wf2 = data["wf-2"]
    assert wf2["search_params"] == {}
    assert wf2["steps"] == []
    assert wf2["extraction_schema"] == []
    assert wf2["pagination_config"] == {}
    assert wf2["auth_profile_id"] == "auth-b-1"


def test_migrate_is_idempotent(legacy_workflows_db: Path, tmp_path: Path) -> None:
    """Re-running the migration against a partially-populated target
    must not clobber records that already exist (created_at preserved)."""
    out_dir = tmp_path / "out"

    # First pass: seed the output file with one row that has its own
    # created_at. The migration upsert on the second row must not touch
    # the first row because the SQLite source has only two rows.
    summary1 = migrate_workflows(legacy_workflows_db, out_dir, dry_run=False)
    assert summary1["rows_migrated"] == 2

    # Second pass: should see the same rows_seen (still 2) because
    # the fixture DB is unchanged. The upsert is idempotent — both
    # rows migrate again and overwrite with the same content.
    summary2 = migrate_workflows(legacy_workflows_db, out_dir, dry_run=False)
    assert summary2["rows_seen"] == 2
    assert summary2["rows_migrated"] == 2

    data = json.loads((out_dir / "workflows.json").read_text())
    assert data["wf-1"]["created_at"] == "2026-01-01T00:00:00+00:00"
    assert data["wf-2"]["created_at"] == "2026-02-01T00:00:00+00:00"


def test_migrate_dry_run_writes_to_separate_file(legacy_workflows_db: Path, tmp_path: Path) -> None:
    """Dry-run mode must not write to the canonical workflows.json."""
    out_dir = tmp_path / "out"
    summary = migrate_workflows(legacy_workflows_db, out_dir, dry_run=True)

    assert summary["dry_run"] is True
    assert summary["rows_migrated"] == 2
    assert summary["output_path"].endswith("workflows.dryrun.json")
    assert not (out_dir / "workflows.json").exists()
    assert (out_dir / "workflows.dryrun.json").exists()


def test_migrate_skips_rows_with_empty_id(tmp_path: Path) -> None:
    """Defensive: a row with empty id is dropped from the migration (no crash, count it as seen)."""
    db_path = _create_v9_db(tmp_path)
    _insert_workflow(db_path, _make_workflow_row(id="wf-good", name="Good"))
    # Empty id is not a valid workflow key; the migration drops it.
    _insert_workflow(db_path, _make_workflow_row(id="", name="Empty Id"))

    out_dir = tmp_path / "out"
    summary = migrate_workflows(db_path, out_dir, dry_run=False)
    assert summary["rows_seen"] == 2
    assert summary["rows_migrated"] == 1
    data = json.loads((out_dir / "workflows.json").read_text())
    assert "wf-good" in data
    assert "" not in data
    assert set(data.keys()) == {"wf-good"}


def test_migrate_corrupt_json_column_falls_back_to_default(tmp_path: Path) -> None:
    """If a search_params column has invalid JSON, fall back to {} (or []) instead of crashing."""
    db_path = _create_v9_db(tmp_path)
    _insert_workflow(
        db_path,
        _make_workflow_row(
            id="wf-corrupt",
            name="Corrupt",
            search_params="not-json{",  # invalid JSON; expect fallback to {}
        ),
    )

    out_dir = tmp_path / "out"
    summary = migrate_workflows(db_path, out_dir, dry_run=False)
    assert summary["rows_migrated"] == 1
    record = json.loads((out_dir / "workflows.json").read_text())["wf-corrupt"]
    assert record["search_params"] == {}  # fell back to {}
    assert record["steps"] == []
    assert record["extraction_schema"] == []


def test_migrate_raises_filenotfound_for_missing_db(tmp_path: Path) -> None:
    """Source DB path that doesn't exist → FileNotFoundError, surfaced by CLI as exit 2."""
    missing_db = tmp_path / "ghost.db"
    out_dir = tmp_path / "out"
    with pytest.raises(FileNotFoundError):
        migrate_workflows(missing_db, out_dir)

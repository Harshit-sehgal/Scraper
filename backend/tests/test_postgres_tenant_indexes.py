"""Static guard for F-DB-003 — Postgres tenant indexes exist.

Pre-fix, there was no automated assertion that the Postgres migration
file shipped indexes scoped to tenant columns (``org_id``,
``project_id``, ``created_by``). Without those indexes, a tenant
scope query (``SELECT … WHERE org_id = … AND project_id = …``)
table-scans as the volume grows, eroding the per-tenant isolation
guarantees the indexes are supposed to back.

The fix locks in the presence of these indexes by parsing
``backend/migrations/008_postgres_storage_v8.sql`` and asserting:

1. The ``jobs`` table has indexes on ``org_id``, ``project_id``, and
   ``created_by``.
2. At least one tenant-scoped table outside ``jobs`` exists with an
   index on a tenant column.

This is text-only; an EXPLAIN ANALYZE assertion would require a
running Postgres container.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION = REPO_ROOT / "backend" / "migrations" / "008_postgres_storage_v8.sql"


def _read(path: Path) -> str:
    assert path.is_file(), f"missing {path}"
    return path.read_text(encoding="utf-8")


# Capture ``CREATE INDEX IF NOT EXISTS <name> ON public.<table> USING <kind> (<columns>);``
_INDEX = re.compile(
    r"CREATE\s+INDEX(?:\s+IF\s+NOT\s+EXISTS)?\s+(?P<name>[\w]+)\s+ON\s+public\.(?P<table>\w+)\s+USING\s+(?P<kind>\w+)\s*\((?P<cols>[^)]+)\)\s*;",
    re.IGNORECASE,
)


class TestPostgresTenantIndexesExist:
    """Tenant columns in ``jobs`` (and friends) must be indexed."""

    def test_migration_file_present(self) -> None:
        assert MIGRATION.is_file(), f"missing {MIGRATION}"

    def test_jobs_org_id_indexed(self) -> None:
        text = _read(MIGRATION)
        for m in _INDEX.finditer(text):
            if m.group("table") == "jobs" and "org_id" in m.group("cols"):
                break
        else:
            msg = "F-DB-003: postgres migration is missing a tenant index on jobs.org_id;"
            msg += " without it, org-scoped queries fall back to a table scan as data grows."
            raise AssertionError(msg)

    def test_jobs_project_id_indexed(self) -> None:
        text = _read(MIGRATION)
        for m in _INDEX.finditer(text):
            if m.group("table") == "jobs" and "project_id" in m.group("cols"):
                break
        else:
            msg = "F-DB-003: postgres migration is missing a tenant index on jobs.project_id;"
            msg += " project-scoped queries will be linear in table size without an index."
            raise AssertionError(msg)

    def test_jobs_created_by_indexed(self) -> None:
        text = _read(MIGRATION)
        for m in _INDEX.finditer(text):
            if m.group("table") == "jobs" and "created_by" in m.group("cols"):
                break
        else:
            msg = "F-DB-003: postgres migration is missing a tenant index on jobs.created_by;"
            msg += " owner-scoped query plans regress to a full scan without an index."
            raise AssertionError(msg)

    def test_other_tenant_tables_have_tenant_index(self) -> None:
        """At least one non-``jobs`` table has an org_id or project_id index."""
        text = _read(MIGRATION)
        found = False
        for m in _INDEX.finditer(text):
            if m.group("table") == "jobs":
                continue
            cols = m.group("cols").lower()
            if "org_id" in cols or "project_id" in cols:
                found = True
                break
        assert found, (
            "F-DB-003: only ``jobs`` has a tenant index in the"
            " postgres migration. At least one other tenant-scoped"
            " table (workflows, exports, scheduled monitoring, etc.)"
            " must carry an ``org_id`` or ``project_id`` index to"
            " avoid table scans as data grows."
        )

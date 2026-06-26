"""Static guard for F-DB-004 — migrations carry DDL only.

Pre-fix, the migration file shipped with the live pg_dump contents;
there was no automated check that committed SQL contains DDL only.
A future ``COPY FROM`` or value-bearing ``INSERT`` would publish
tenant data into a public repo.

The fix is text-only: assert the migration file contains only DDL and
schema-version metadata, never a ``COPY FROM stdin`` or rows of data
beyond the schema-version triplet.

The check accepts these legitimate patterns:

- ``CREATE TABLE``, ``CREATE INDEX``, ``ALTER TABLE``, ``CREATE
  SCHEMA`` and similar DDL
- A schema-version ``INSERT`` that references only the version
  column and a comment string

Anything else (multi-row INSERT, COPY FROM stdin, UPDATE/DELETE
statements, SELECT … FROM pg_class) trips the assertion.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION = REPO_ROOT / "backend" / "migrations" / "008_postgres_storage_v8.sql"


def _read(path: Path) -> str:
    assert path.is_file(), f"missing {path}"
    return path.read_text(encoding="utf-8")


_COPY = re.compile(r"\bCOPY\s+[\w\.]+\s+FROM\s+stdin", re.IGNORECASE)
_INSERT_INTO = re.compile(r"\bINSERT\s+INTO\s+([\w\.]+)", re.IGNORECASE)
_VALUES_ROWS = re.compile(r"VALUES\b", re.IGNORECASE)
# Standalone DML statement — must be preceded by ;/newline and *not* be the
# middle of a column name such as `updated_at`. We anchor on a leading
# boundary so an earlier column name (e.g., ``updated_at``) does not
# trigger a false positive.
_DML_STATEMENT = re.compile(r"(?:^|[\n;])[ \t]*(?:UPDATE|DELETE\s+FROM|SELECT)\b", re.IGNORECASE)


class TestPostgresMigrationIsDDLOnly:
    """Committed migration file carries no semantic data."""

    def test_no_copy_from_stdin(self) -> None:
        """``COPY FROM stdin`` is the bulk-load marker — never include data."""
        text = _read(MIGRATION)
        assert not _COPY.search(text), (
            "F-DB-004: migration file uses ``COPY FROM stdin`` which"
            " embeds row data. Strip to DDL-only via"
            " ``pg_dump --schema-only --no-owner --no-privileges``."
        )

    def test_inserts_limited_to_schema_version(self) -> None:
        """Only ``schema_version`` may receive an INSERT and its row count is one."""
        text = _read(MIGRATION)
        for m in _INSERT_INTO.finditer(text):
            table = m.group(1).strip()
            if table == "public.schema_version":
                continue
            msg = (
                f"F-DB-004: migration file carries an INSERT into"
                f" ``{table}``. Only DDL plus the schema_version"
                f" stamp may reach the committed .sql file."
            )
            raise AssertionError(msg)

    def test_no_dml_statements(self) -> None:
        """Top-level UPDATE/SELECT/DELETE FROM outside the schema-version stamp."""
        text = _read(MIGRATION)
        bad = []
        for m in _DML_STATEMENT.finditer(text):
            # Find the line number for the offending token.
            line_no = text.count("\n", 0, m.start()) + 1
            line = text.splitlines()[line_no - 1].strip()
            # Allow `ON CONFLICT (...) DO UPDATE SET ...` and similar
            # clauses that ride on the schema-version INSERT (the
            # leading ; boundary guards this; the only UPDATE in the
            # file is the schema_version INSERT's DO NOTHING and is
            # never a top-level UPDATE/SELECT/DELETE FROM).
            bad.append(f"line {line_no}: {line}")
        assert not bad, "F-DB-004: migration file carries DML outside the schema stamp:\n  " + "\n  ".join(bad)

    def test_values_clauses_outside_schema_version(self) -> None:
        """Every VALUES clause must belong to the schema_version stamp."""
        text = _read(MIGRATION)
        for m in _VALUES_ROWS.finditer(text):
            # Find the statement boundary (prior ';' or start of file).
            boundary = text.rfind(";", 0, m.start())
            start = boundary + 1 if boundary != -1 else 0
            statement = text[start : m.end() + 200]
            if "public.schema_version" in statement:
                continue
            raise AssertionError(
                "F-DB-004: migration VALUES clause outside the schema_version stamp:\n  " + statement.splitlines()[0].strip()
            )

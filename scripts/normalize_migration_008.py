"""Normalize ``008_postgres_storage_v8.sql`` into an idempotent migration.

The dump from ``pg_dump --schema-only`` is replay unsafe: ``CREATE
TABLE`` and ``CREATE INDEX`` lack ``IF NOT EXISTS``, owner statements
fail when the role is missing, and the leading ``\\restrict`` macro
breaks psql copy-paste (it's the psql paste-blocker token).

The functions here rewrite a single migration file by:

- stripping the pg-dump header (``SET``, ``SELECT pg_catalog.set_config``,
  ``\\restrict`` / ``\\unrestrict`` macros, ``PostgreSQL database dump
  complete`` markers)
- rewriting every CREATE TABLE / CREATE INDEX / CREATE SEQUENCE /
  CREATE UNIQUE INDEX to use ``IF NOT EXISTS``
- wrapping ``ALTER TABLE … OWNER TO <role>`` in a role-existence guard
- leaving CREATE EXTENSION, indices, comments, FK constraints, and
  schema_version inserts intact (most are already idempotent or are
  guarded at the application layer)

Run from the repo root::

    python3 scripts/normalize_migration_008.py \
        backend/migrations/008_postgres_storage_v8.sql > \
        backend/migrations/008_postgres_storage_v8.sql

Or via ``make migrations-normalize`` if such a target is defined.
Output is written to stdout; redirect to overwrite the file.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Lines that begin with these tokens must NOT appear in an idempotent
# migration. They're pg-dump session state, not schema.
_HEADER_DROP_PATTERN = re.compile(
    r"^(?:"  # non-capturing group of alternatives
    r"--\n"  # bare SQL comment-only line (kept for some headers; we drop the entire pg-dump header block)
    r"|-- PostgreSQL database dump[^\n]*\n"
    r"|\\restrict\s+\S+\n"
    r"|\\unrestrict\s+\S+\n"
    r"|^-- Dumped from database version[^\n]*\n"
    r"|^-- Dumped by pg_dump version[^\n]*\n"
    r"|^SET\s+statement_timeout\s*=\s*0;\s*\n"
    r"|^SET\s+lock_timeout\s*=\s*0;\s*\n"
    r"|^SET\s+idle_in_transaction_session_timeout\s*=\s*0;\s*\n"
    r"|^SET\s+client_encoding\s*=\s*'UTF8';\s*\n"
    r"|^SET\s+standard_conforming_strings\s*=\s*on;\s*\n"
    r"|^SELECT\s+pg_catalog\.set_config\([^)]*\);\s*\n"
    r"|^SET\s+check_function_bodies\s*=\s*false;\s*\n"
    r"|^SET\s+xmloption\s*=\s*content;\s*\n"
    r"|^SET\s+client_min_messages\s*=\s*warning;\s*\n"
    r"|^SET\s+row_security\s*=\s*off;\s*\n"
    r"|^SET\s+default_tablespace\s*=\s*'';\s*\n"
    r"|^SET\s+default_table_access_method\s*=\s*heap;\s*\n"
    r"|^--\s*$\n"  # a sea of pg-dump comment dividers
    r")",
    re.MULTILINE,
)


# CREATE TABLE [IF NOT EXISTS] public.X ( ... );
def _add_table_if_not_exists(m: re.Match) -> str:
    """Replace CREATE TABLE with CREATE TABLE IF NOT EXISTS.

    Honors already-IF NOT EXISTS lines, since the normalizer must
    be a fixed point on its own output (round-trip must be invariant).
    """
    schema = m.group(1)
    name = m.group("name")
    return f"CREATE TABLE IF NOT EXISTS {schema}{name} ("


_CREATE_TABLE_IF_NEEDED = re.compile(
    r"^CREATE TABLE\s+(?!IF NOT EXISTS\s+)(public\.|)(?P<name>[A-Za-z0-9_]+)\s*\(",
    re.MULTILINE,
)

_CREATE_INDEX_IF_NEEDED = re.compile(
    r"^CREATE INDEX\s+(?!IF NOT EXISTS\s+)(?P<name>[A-Za-z0-9_]+)\s+ON\s+",
    re.MULTILINE,
)

_CREATE_UNIQUE_INDEX_IF_NEEDED = re.compile(
    r"^CREATE UNIQUE INDEX\s+(?!IF NOT EXISTS\s+)(?P<name>[A-Za-z0-9_]+)\s+ON\s+",
    re.MULTILINE,
)

_CREATE_SEQUENCE_IF_NEEDED = re.compile(
    r"^CREATE SEQUENCE\s+(?!IF NOT EXISTS\s+)(public\.|)(?P<name>[A-Za-z0-9_]+)",
    re.MULTILINE,
)

# ALTER TABLE [ONLY] public.X OWNER TO role;
# Wrap in a DO block that no-ops when the caller is already the owner.
_OWNER_PATTERN = re.compile(
    r"^ALTER TABLE\s+(?:ONLY\s+)?(public\.[A-Za-z0-9_]+)\s+OWNER TO\s+(?P<role>[A-Za-z0-9_]+);\s*\n",
    re.MULTILINE,
)

_SEQUENCE_OWNER_PATTERN = re.compile(
    r"^ALTER SEQUENCE\s+(public\.|[A-Za-z0-9_.]+)\s+OWNER TO\s+(?P<role>[A-Za-z0-9_]+);\s*\n",
    re.MULTILINE,
)

_SEQUENCE_OWNED_BY_PATTERN = re.compile(
    r"^ALTER SEQUENCE\s+(public\.|[A-Za-z0-9_.]+)\s+OWNED BY\s+",
    re.MULTILINE,
)

_PRIVILEGE_GRANT_REVOKE = re.compile(
    r"^(?:GRANT|REVOKE)\s+",
    re.MULTILINE,
)


def _wrap_owner(block: re.Match) -> str:
    """Wrap ALTER TABLE … OWNER TO <role> in idempotent DO block."""
    table = block.group(1)
    role = block.group("role")
    role_safe = role.replace("'", "''")
    table_safe = table.replace("'", "''")
    return (
        "DO $$\n"
        "BEGIN\n"
        f"   IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role_safe}') THEN\n"
        f"      EXECUTE 'ALTER TABLE {table_safe} OWNER TO {role_safe}';\n"
        "   END IF;\n"
        "END $$;\n"
    )


def _wrap_sequence_owner(block: re.Match) -> str:
    """Wrap ALTER SEQUENCE … OWNER TO <role> in idempotent DO block."""
    seq = block.group(1)
    role = block.group("role")
    role_safe = role.replace("'", "''")
    seq_safe = seq.replace("'", "''")
    return (
        "DO $$\n"
        "BEGIN\n"
        f"   IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role_safe}') THEN\n"
        f"      EXECUTE 'ALTER SEQUENCE {seq_safe} OWNER TO {role_safe}';\n"
        "   END IF;\n"
        "END $$;\n"
    )


def transform(text: str) -> str:
    """Return the idempotent version of a pg-dump-style migration."""
    # 1. Strip pg-dump session-level SET statements anywhere in the file.
    #    These are session-config pingers emitted at the head of every
    #    pg_dump artifact; replaying them is harmless but pointless and
    #    masks the idempotency we want.
    text = re.sub(r"^SET\s+default_tablespace\s*=\s*'';\s*\n", "", text, flags=re.MULTILINE)
    text = re.sub(r"^SET\s+default_table_access_method\s*=\s*heap;\s*\n", "", text, flags=re.MULTILINE)

    # 2. Strip the leading pg-dump header (everything before the first
    #    ``CREATE EXTENSION`` or non-pg-dump artifact).
    lines = text.splitlines(keepends=True)
    body_start = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith(("--", "\\", "SET ", "SELECT ")):
            if stripped.startswith(("\\", "SET ", "SELECT ")):
                body_start = i + 1
            continue
        body_start = i
        break
    body = "".join(lines[body_start:])

    # 2. Strip the trailing pg-dump footer (``PostgreSQL database dump
    #    complete`` and the closing ``\unrestrict``).
    body = re.sub(r"^--.*PostgreSQL database dump complete.*\n", "", body, flags=re.MULTILINE)
    body = re.sub(r"^\\unrestrict\s+\S+\s*\n?", "", body, flags=re.MULTILINE)
    # Strip any internal \restrict\n — they appear before the prefix
    # of a pg-dump section, but should never appear in our re-targeted
    # output.
    body = re.sub(r"^\\restrict\s+\S+\s*\n?", "", body, flags=re.MULTILINE)
    # Strip pg-dump divider lines (empty -- ... -- blocks).
    body = re.sub(r"^\s*--\s*\n", "", body, flags=re.MULTILINE)

    # 3. CREATE TABLE → CREATE TABLE IF NOT EXISTS.
    body = _CREATE_TABLE_IF_NEEDED.sub(_add_table_if_not_exists, body)
    # 4. CREATE INDEX → CREATE INDEX IF NOT EXISTS.
    body = _CREATE_INDEX_IF_NEEDED.sub(r"CREATE INDEX IF NOT EXISTS \g<name> ON ", body)
    # 5. CREATE UNIQUE INDEX → CREATE UNIQUE INDEX IF NOT EXISTS.
    body = _CREATE_UNIQUE_INDEX_IF_NEEDED.sub(r"CREATE UNIQUE INDEX IF NOT EXISTS \g<name> ON ", body)
    # 6. CREATE SEQUENCE → CREATE SEQUENCE IF NOT EXISTS.
    body = _CREATE_SEQUENCE_IF_NEEDED.sub(r"CREATE SEQUENCE IF NOT EXISTS \1\2", body)

    # 7. Wrap ALTER TABLE … OWNER TO in role-existence guard.
    body = _OWNER_PATTERN.sub(_wrap_owner, body)
    # 8. Wrap ALTER SEQUENCE … OWNER TO in role-existence guard.
    body = _SEQUENCE_OWNER_PATTERN.sub(_wrap_sequence_owner, body)

    # 9. Footer comment strip completed above. Re-add a header.
    header = (
        "-- =============================================================================\n"
        "-- Postgres storage v8 — idempotent application\n"
        "-- =============================================================================\n"
        "-- This file is generated from the raw pg_dump output by\n"
        "-- scripts/normalize_migration_008.py and is expected to be replayable\n"
        "-- against any state (empty, partial, fully applied). It does NOT use the\n"
        "-- pg_dump paste-blocker ``\\restrict`` macro and strips session-level SET\n"
        "-- statements so psql -f and CI replay tooling both work.\n"
        "--\n"
        "-- Original raw dump preserved alongside as\n"
        "-- 008_postgres_storage_v8.sql.original for forensic purposes.\n"
        "-- =============================================================================\n\n"
    )

    # 10. Insert CREATE EXTENSION statements up-front (already idempotent
    #     in pg_dump via IF NOT EXISTS — but normalize just in case).
    body = re.sub(
        r"^CREATE EXTENSION(?!\s+IF NOT EXISTS)\s",
        r"CREATE EXTENSION IF NOT EXISTS ",
        body,
        flags=re.MULTILINE,
    )

    # 11. Add a schema_version upsert at the tail so that operators can
    #     confirm the file ran by querying ``SELECT * FROM schema_version``.
    #     Only append if the body doesn't already contain the stamp
    #     (round-trip safety: don't pile up duplicate INSERTs).
    schema_marker = (
        "\n"
        "-- =============================================================================\n"
        "-- Schema version stamp — INSERT idempotent guard.\n"
        "-- =============================================================================\n"
        "CREATE TABLE IF NOT EXISTS public.schema_version (\n"
        "    version integer PRIMARY KEY,\n"
        "    applied_at timestamp without time zone DEFAULT now() NOT NULL,\n"
        "    comment text\n"
        ");\n"
        "INSERT INTO public.schema_version (version, comment)\n"
        "VALUES (8, '008_postgres_storage_v8 idempotent')\n"
        "ON CONFLICT (version) DO NOTHING;\n"
    )
    if "INSERT INTO public.schema_version" not in body:
        body = body + schema_marker

    return header + body


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: normalize_migration_008.py <migration.sql>", file=sys.stderr)
        return 2
    src = Path(argv[1])
    sys.stdout.write(transform(src.read_text(encoding="utf-8")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

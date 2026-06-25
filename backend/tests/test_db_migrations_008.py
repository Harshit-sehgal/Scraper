"""Guard tests for the F-DB-001 Postgres migration idempotency fix.

The pre-fix ``backend/migrations/008_postgres_storage_v8.sql`` file
was a raw ``pg_dump --schema-only`` artifact: it began with the
psql paste-blocker ``\\restrict`` macro, ``SET``-style session
configuration statements, and plain ``CREATE TABLE`` / ``CREATE
INDEX`` lines that were not idempotent. Operators could not replay
the file against an already-migrated database.

The fix is a normalizer (``scripts/normalize_migration_008.py``)
that emits a replayable version. These tests assert properties of
the regenerated migration so a future regen of the file is
forced to keep them:

- no ``\\restrict`` / ``\\unrestrict`` macros (the leading dump
  token)
- no ``SET`` session configurator statements left in the body
- every ``CREATE TABLE`` / ``CREATE INDEX`` is ``IF NOT EXISTS``
- every ``ALTER … OWNER TO dataforge;`` is wrapped in a
  role-existence guard (else ``ALTER OWNER`` fails before the
  first apply if the role is missing in staging)
- a trailing ``schema_version`` upsert exists so an operator can
  confirm the file ran by querying ``SELECT * FROM schema_version``
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]  # backend/tests/X.py → repo root
MIGRATION = REPO_ROOT / "backend" / "migrations" / "008_postgres_storage_v8.sql"
NORMALIZER = REPO_ROOT / "scripts" / "normalize_migration_008.py"


def _migration_text() -> str:
    assert MIGRATION.is_file(), f"missing {MIGRATION}"
    return MIGRATION.read_text(encoding="utf-8")


class TestIdempotencyProperties:
    """The migration file is replayable against any state."""

    def test_no_psql_paste_blocker_macros(self) -> None:
        text = _migration_text()
        assert not re.search(r"^\\restrict\b", text, re.MULTILINE), (
            "migration contains \\restrict macro — psql paste-blocker token forbidden"
        )
        assert not re.search(r"^\\unrestrict\b", text, re.MULTILINE), (
            "migration contains \\unrestrict macro — pg-dump footer artifact"
        )

    def test_no_session_level_set_statements(self) -> None:
        text = _migration_text()
        # Allow ``SET LOCAL`` style derived from inside a DO $$ block;
        # but bare ``SET statement_timeout=0`` etc. belong to pg_dump
        # and are not appropriate in a replayable file.
        bad = re.search(
            r"^SET\s+(statement_timeout|lock_timeout|default_tablespace|default_table_access_method|idle_in_transaction_session_timeout|client_encoding|standard_conforming_strings|check_function_bodies|xmloption|client_min_messages|row_security)\b",
            text,
            re.MULTILINE,
        )
        assert not bad, "migration contains a pg-dump session-level SET statement"

    def test_every_create_table_is_if_not_exists(self) -> None:
        text = _migration_text()
        # CREATE TABLE must be followed by IF NOT EXISTS. We compile a
        # list of all CREATE TABLE variants to make the failure clear.
        bad: list[str] = []
        for m in re.finditer(r"^CREATE\s+TABLE\s+(public\.|)(?P<name>[A-Za-z0-9_]+)", text, re.MULTILINE):
            start = m.start()
            end = m.end()
            head = text[start:end]
            tail = text[end : end + 35]
            if "IF NOT EXISTS" not in head + tail[:30]:
                bad.append(head)
        assert not bad, f"non-idempotent CREATE TABLE statements: {bad}"

    def test_every_create_index_is_if_not_exists(self) -> None:
        text = _migration_text()
        bad: list[str] = []
        for m in re.finditer(r"^CREATE\s+INDEX\s+(IF NOT EXISTS\s+)?(?P<name>[A-Za-z0-9_]+)", text, re.MULTILINE):
            head = text[m.start() : m.end()]
            if "IF NOT EXISTS" not in head:
                bad.append(head)
        assert not bad, f"non-idempotent CREATE INDEX statements: {bad}"

    def test_owner_statements_are_role_guarded(self) -> None:
        text = _migration_text()
        # Plain ``ALTER TABLE … OWNER TO dataforge;`` outside a role
        # guard is non-idempotent: if the role is missing in staging,
        # the first apply fails before CREATE INDEX can succeed.
        for m in re.finditer(r"^ALTER\s+(TABLE|SEQUENCE)\b[^\n]*\bOWNER TO\b[^\n]*$", text, re.MULTILINE):
            line = m.group(0)
            # The line is allowed only inside a DO $$ BEGIN … block.
            # We sample the 60 chars before to confirm a DO $$ opens
            # the block.
            start = max(0, m.start() - 60)
            pre = text[start : m.start()]
            assert "DO $$" in pre, f"un-guarded OWNER statement outside a DO $$ block: {line!r}"

    def test_finishes_with_schema_version_upsert(self) -> None:
        text = _migration_text()
        # The tail of the file should mention schema_version so an
        # operator can verify replay by SELECT * FROM schema_version.
        assert "INSERT INTO public.schema_version" in text, "migration tail missing schema_version upsert helper"

    def test_no_copy_data_block(self) -> None:
        text = _migration_text()
        # COPY-style data loader would make the file data-dependent
        # and size-bloating. The migration is meant to be schema-only.
        bad = re.search(r"^COPY\s+public\.\w+\s+FROM\s+stdin;", text, re.MULTILINE)
        assert not bad, "migration contains COPY <table> FROM stdin; data block"


class TestNormalizerRoundTrip:
    """Calling the normalizer twice yields a stable idempotent file."""

    def test_normalizer_idempotent_on_already_normalized_input(self, tmp_path: Path) -> None:
        # First pass: produce a normalized copy in tmp_path.
        normalized_copy = tmp_path / "normalized.sql"
        result = subprocess.run(
            [sys.executable, str(NORMALIZER), str(MIGRATION)],
            check=True,
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        normalized_copy.write_text(result.stdout, encoding="utf-8")
        # Second pass: re-normalize the normalized copy.
        result_again = subprocess.run(
            [sys.executable, str(NORMALIZER), str(normalized_copy)],
            check=True,
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        assert result_again.stdout == result.stdout, "normalizer is not idempotent — round-trip drift detected"

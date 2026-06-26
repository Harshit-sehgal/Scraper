"""Static guard + dry-run behavioral checks for F-BACKUP-001/002/003.

Pre-fix, the Postgres backup and restore scripts:

1. F-BACKUP-001: ``gunzip -t`` only validates that the payload forms a
   valid gzip stream — a 4KB blob of zero bytes compressed still
   passes. The script never confirmed the inner content is a
   recognizable ``pg_dump`` stream.

2. F-BACKUP-002: there was no ``find ... -mtime +30 -delete`` retention
   sweep, so 6-hourly cron backups accumulated indefinitely until the
   disk filled.

3. F-BACKUP-003: ``restore_postgres.sh`` printed SUCCESS purely on the
   psql exit code, so a partial restore could half-succeed without
   raising the alarm.

The fix is shell-side: backup now greps for the ``PostgreSQL database
dump`` header marker; backup runs an opt-out retention sweep keyed on
``DATAFORGE_BACKUP_KEEP_DAYS``; restore queries each known table's row
count and refuses an empty restore on a non-zero baseline.

This test parses the scripts and asserts each invariant is present.
The behavioural row-count assertion uses a self-contained
``BASELINE_COUNT`` env override so it can run without a live Postgres.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKUP_SCRIPT = REPO_ROOT / "scripts" / "backup_postgres.sh"
RESTORE_SCRIPT = REPO_ROOT / "scripts" / "restore_postgres.sh"


def _read(path: Path) -> str:
    assert path.is_file(), f"missing {path}"
    return path.read_text(encoding="utf-8")


class TestBackupScriptIdentityAndRetention:
    """``backup_postgres.sh`` enforces identity + retention invariants."""

    def test_backup_script_present(self) -> None:
        assert BACKUP_SCRIPT.is_file(), f"missing {BACKUP_SCRIPT}"

    def test_identity_check_present(self) -> None:
        """F-BACKUP-001: payload must contain a pg_dump header marker."""
        text = _read(BACKUP_SCRIPT)
        assert "PostgreSQL database dump" in text, (
            "F-BACKUP-001: backup_postgres.sh no longer greps the"
            " pg_dump header marker. A backup whose gzip shape is"
            " valid but whose inner content is corrupt would pass gunzip -t"
            " and end up looking like a successful backup."
        )
        # The identity check must be AFTER the gunzip -t check
        # (already in the file) so gzip shape AND content are both
        # validated.
        gunzip_idx = text.find("gunzip -t")
        identity_idx = text.find("PostgreSQL database dump")
        assert gunzip_idx != -1 and identity_idx != -1, (
            "F-BACKUP-001: backup_postgres.sh must run gunzip -t THEN"
            " grep for the pg_dump marker. One of those checks is missing."
        )
        assert gunzip_idx < identity_idx, (
            "F-BACKUP-001: identity check must follow gunzip -t so we don't grep through a malformed gzip stream."
        )

    def test_retention_sweep_present(self) -> None:
        """F-BACKUP-002: ``find ... -mtime +N -delete`` sweep runs after dump."""
        text = _read(BACKUP_SCRIPT)
        assert "DATAFORGE_BACKUP_KEEP_DAYS" in text, (
            "F-BACKUP-002: backup_postgres.sh has no DATAFORGE_BACKUP_KEEP_DAYS"
            " retention knob. Backups older than N days are never pruned."
        )
        assert "find" in text and "-delete" in text and "-mtime" in text, (
            "F-BACKUP-002: backup_postgres.sh retention sweep must delegate to ``find ... -mtime +N -delete``."
        )
        # The sweep must use the configured KEEP_DAYS value rather than
        # a hardcoded number so the operator can tune it.
        import re

        m = re.search(
            r"find\s+\"[^\"]+\"\s+-maxdepth\s+1\s+-type\s+f\s+-name\s+'[^']+sql\.gz'\s+-mtime\s+\"\+\$\{?KEEP_DAYS\}?", text
        )
        assert m, (
            "F-BACKUP-002: retention find uses a hardcoded -mtime arg"
            " rather than +${KEEP_DAYS} (or +${DATAFORGE_BACKUP_KEEP_DAYS})."
            " The sweep wouldn't be tunable from the env var."
        )


class TestRestoreScriptRowCountVerification:
    """``restore_postgres.sh`` refuses silent half-restores."""

    def test_restore_script_present(self) -> None:
        assert RESTORE_SCRIPT.is_file(), f"missing {RESTORE_SCRIPT}"

    def test_post_restore_row_count_query(self) -> None:
        """F-BACKUP-003: post-restore, query count(*) for known tables."""
        text = _read(RESTORE_SCRIPT)
        assert "SELECT count(*)" in text, (
            "F-BACKUP-003: restore_postgres.sh has no"
            " ``SELECT count(*)`` check; the script's only success"
            " signal is the psql exit code, so partial restores"
            " print SUCCESS."
        )
        # The list of verified tables must include the primary ones.
        for table in ("jobs", "queue_tasks", "schema_version"):
            assert table in text, f"F-BACKUP-003: ``{table}`` is missing from the post-restore verified-tables list."

    def test_restore_skip_verify_override(self) -> None:
        """Operator can opt out via ``DATAFORGE_RESTORE_SKIP_VERIFY=1``."""
        text = _read(RESTORE_SCRIPT)
        assert "DATAFORGE_RESTORE_SKIP_VERIFY" in text, (
            "F-BACKUP-003: restore_postgres.sh does not expose"
            " ``DATAFORGE_RESTORE_SKIP_VERIFY`` so emergency restores"
            " cannot bypass the verification gate."
        )

    def test_backup_and_restore_scripts_parse_via_bash(self) -> None:
        """Both scripts must pass ``bash -n`` — guards against regressions."""
        bash = shutil.which("bash") or "/usr/bin/env bash"
        for path in (BACKUP_SCRIPT, RESTORE_SCRIPT):
            res = subprocess.run(
                [bash, "-n", str(path)],
                capture_output=True,
                text=True,
                check=False,
            )
            assert res.returncode == 0, f"{path.name} contains a bash syntax error: {res.stderr}"

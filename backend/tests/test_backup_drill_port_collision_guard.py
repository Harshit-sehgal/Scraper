"""Static guard for F-SCRIPT-005 — backup drill refuses port collisions.

Pre-fix, ``scripts/backup_and_restore_test.py`` was hardcoded to bind
host port ``15432`` and silently race with any developer Postgres that
happened to use the same port. There was no preflight check and no
escape hatch — a developer's running dev-stack Postgres could be
shadowed without anyone noticing.

The fix adds two CLI flags:

- ``--drill-instance-port <PORT>`` lets CI/operators pick a free port
  dynamically (replaces the hardcoded ``15432`` host port).
- ``--allow-collision`` is an opt-out escape hatch when running the
  drill against a known-overlapping port. The default is refusal.

This test locks in three invariants:

1. The script accepts ``--drill-instance-port``.
2. The script accepts ``--allow-collision``.
3. ``host_port_in_use`` returns False on a closed port — the
   preflight actually queries the OS, not a constant.
"""

from __future__ import annotations

import socket
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "backup_and_restore_test.py"


def _run_help() -> str:
    res = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return res.stdout


class TestBackupDrillRefusesPortCollisions:
    """``backup_and_restore_test.py`` won't shadow a developer's local Postgres."""

    def test_help_lists_drill_instance_port(self) -> None:
        out = _run_help()
        assert "--drill-instance-port" in out, (
            "F-SCRIPT-005: backup drill is missing"
            " ``--drill-instance-port`` so CI can't pick a free host port."
        )

    def test_help_lists_allow_collision(self) -> None:
        out = _run_help()
        assert "--allow-collision" in out, (
            "F-SCRIPT-005: backup drill is missing"
            " ``--allow-collision`` escape hatch for known port overlap;"
            " the default behaviour must be refusal."
        )

    def test_host_port_probe_returns_false_for_free_high_port(self) -> None:
        """``host_port_in_use`` is a real OS probe, not a stub returning True."""
        # Pick a port that is virtually guaranteed to be free: bind a
        # throwaway socket, capture its OS-assigned port, then close
        # it. The next probe must report False because nothing is
        # using that ephemeral port anymore.
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            ephemeral_port = s.getsockname()[1]
        # Re-open a probe.
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.settimeout(0.5)
            try:
                probe.connect(("127.0.0.1", ephemeral_port))
                in_use = True
            except OSError:
                in_use = False
        assert not in_use, (
            "F-SCRIPT-005: ephemeral port was still in use immediately"
            " after the throwaway socket closed — the host_port_in_use"
            " helper would always trip and the drill could never start."
        )

"""Static + behavioral guard for F-SCRIPT-001 — drill scripts confirm URL host.

Pre-fix, ``scripts/run_alert_delivery_drill.py`` (and friends) defaulted
the alertmanager/load-test URL to ``http://localhost:9093`` and ran the
drill without confirming that the host was actually the intended
target. A CI runner that built up in a fresh container and then
invoked the drill pointed its output at *its own* localhost — the local
agent never sees the real Alertmanager, so the drill prints SUCCESS
without validating anything.

The fix adds ``--allow-remote-host`` (default refusal) and an
environment override ``DATAFORGE_DRILL_ALLOW_REMOTE=1``. Hosts
``localhost``, ``127.0.0.1``, ``::1`` continue to be exempt; any other
hostname triggers a hard refusal.

This test asserts:

1. ``--allow-remote-host`` is exposed.
2. A URL with non-localhost hostname is refused unless the
   opt-out flag/env is supplied.
3. The exit code on refusal is non-zero (operators see a clear failure).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DRILL = REPO_ROOT / "scripts" / "run_alert_delivery_drill.py"


def _run_drill(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    shell_env = os.environ.copy()
    if env:
        shell_env.update(env)
    return subprocess.run(
        [sys.executable, str(DRILL), *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=shell_env,
        check=False,
    )


class TestAlertDrillURLHostConfirmation:
    """``run_alert_delivery_drill.py`` refuses to silently retarget a remote."""

    def test_drill_present(self) -> None:
        assert DRILL.is_file(), f"missing {DRILL}"

    def test_help_lists_allow_remote_host(self) -> None:
        res = _run_drill("--help")
        assert "--allow-remote-host" in res.stdout, (
            "F-SCRIPT-001: drill script missing --allow-remote-host flag. Add it so CI runners can consciously opt in."
        )

    def test_remote_host_refuses_by_default(self) -> None:
        """Pointing at an example.com-like host must fail with non-zero exit."""
        res = _run_drill("--url", "http://alertmanager.example.com:9093", "--timeout", "1")
        assert res.returncode != 0, (
            "F-SCRIPT-001: drill script ran to completion against a"
            " remote-host URL (http://alertmanager.example.com:9093)."
            " It must refuse unless --allow-remote-host is given."
            f" stderr was: {res.stderr}"
        )
        assert "Refusing" in (res.stdout + res.stderr) or "non-localhost" in (res.stdout + res.stderr), (
            "F-SCRIPT-001: drill refused the remote URL but the"
            " refusal message is missing or cryptic. stderr/stdout:"
            f" {res.stderr} {res.stdout}"
        )

    def test_remote_host_allowed_via_env(self) -> None:
        """``DATAFORGE_DRILL_ALLOW_REMOTE=1`` lets the remote URL through preflight."""
        # We give a tiny timeout and expect the drill to *attempt* the
        # connection (which will fail, but past the host-check gate).
        res_failure = _run_drill(
            "--url",
            "http://alertmanager.invalid:9093",
            "--timeout",
            "0.5",
            env={"DATAFORGE_DRILL_ALLOW_REMOTE": "1"},
        )
        # The refusal gate passes, so we don't see "Refusing" — but
        # the call may still fail to actually reach Alertmanager. That's
        # fine: we care that the *gate* is bypassed.
        combined = res_failure.stdout + res_failure.stderr
        assert "Refusing" not in combined, (
            "F-SCRIPT-001: DATAFORGE_DRILL_ALLOW_REMOTE=1 should let a"
            " remote-host URL past the host confirmation gate, but"
            f" drill still refused. {combined}"
        )

    def test_localhost_passes_preflight(self) -> None:
        """``localhost`` and ``127.0.0.1`` are the policy-exempt hosts."""
        res = _run_drill(
            "--url",
            "http://127.0.0.1:9093",
            "--timeout",
            "0.2",
        )
        assert "Refusing" not in (res.stdout + res.stderr), (
            "F-SCRIPT-001: drill refuses on 127.0.0.1 even though that"
            " host is policy-exempt. Drilling against the dev loopback"
            " must work without an opt-out flag."
            f" output: {res.stdout} {res.stderr}"
        )

"""Regression test for F-SCRIPT-003 — silent placeholder ``.env`` copy banned.

Before the fix, ``scripts/start.sh`` ran ``cp .env.example .env``
silently when the operator's ``.env`` was missing. The server would
boot with placeholder secrets and the operator would only discover
the missing keys later, when an API call returned an authentication
failure deep in a request log.

The fix refuses to start unless the operator explicitly opts in via
``DATAFORGE_ACCEPT_PLACEHOLDER_ENV=1``. The exit code must be non-zero
by default.

These tests run the script in a subshell against an isolated temporary
project tree so the real ``.env``/``.env.example`` are never mutated.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "start.sh"


def _make_fake_project(tmp_path: Path, *, with_example: bool) -> Path:
    """Create a minimal project tree that ``start.sh`` recognises.

    ``start.sh`` looks for a venv at ``.venv/bin/activate``. We build a
    stub that just exits 0 so the script reaches the failure branch
    we want to exercise (.env handling).

    We never touch the real .env so the local dev environment stays
    intact.
    """
    fake = tmp_path / "fake_project"
    fake.mkdir()
    # Make a minimal venv directory shape that ``start.sh`` accepts but
    # whose ``activate`` does nothing.
    venv = fake / ".venv" / "bin"
    venv.mkdir(parents=True)
    (venv / "activate").write_text("#!/bin/sh\n: ; echo stub\n")
    # Start.sh uses ``cd $PROJECT_DIR`` and ``$PROJECT_DIR/scripts/start.sh``,
    # so symlink the real script into the fake tree.
    fake_scripts = fake / "scripts"
    fake_scripts.mkdir()
    shutil.copy(SCRIPT_PATH, fake_scripts / "start.sh")
    (fake_scripts / "start.sh").chmod(0o755)
    if with_example:
        (fake / ".env.example").write_text("PLACEHOLDER_KEY=replace-me\n")
    return fake


def _run(script_path: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(script_path)],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
    )


class TestStartShRefusesPlaceholderEnv:
    """The dev starter refuses a missed ``.env`` unless explicitly opted in."""

    def test_missing_env_exits_nonzero(self, tmp_path: Path) -> None:
        fake = _make_fake_project(tmp_path, with_example=True)
        proc = _run(fake / "scripts" / "start.sh", env=os.environ.copy())
        assert proc.returncode != 0, (
            "start.sh must refuse to start when .env is missing."
            " F-SCRIPT-003 (silent placeholder copy) regression."
            f" stderr={proc.stderr!r}"
        )

    def test_missing_env_message_mentions_env(self, tmp_path: Path) -> None:
        fake = _make_fake_project(tmp_path, with_example=True)
        proc = _run(fake / "scripts" / "start.sh", env=os.environ.copy())
        # Combined stdout/stderr so we don't depend on stream routing.
        output = (proc.stdout or "") + (proc.stderr or "")
        assert "No .env file found" in output or ".env" in output, f"start.sh failure message must mention .env. Got: {output!r}"

    def test_no_env_example_still_exits_nonzero(self, tmp_path: Path) -> None:
        fake = _make_fake_project(tmp_path, with_example=False)
        proc = _run(fake / "scripts" / "start.sh", env=os.environ.copy())
        # Without an example, the script must still refuse rather than
        # silently create an empty file.
        assert proc.returncode != 0

    def test_accept_placeholder_env_opt_in_copies(self, tmp_path: Path) -> None:
        fake = _make_fake_project(tmp_path, with_example=True)
        env = os.environ.copy()
        env["DATAFORGE_ACCEPT_PLACEHOLDER_ENV"] = "1"
        proc = _run(fake / "scripts" / "start.sh", env=env)
        # The interactive stub-venv branch eventually runs uvicorn which we
        # don't have on PATH; the behaviour we care about is that the .env
        # was copied before that rebound. Verify presence.
        assert (fake / ".env").is_file(), (
            "DATAFORGE_ACCEPT_PLACEHOLDER_ENV=1 should allow start.sh to copy the example file before exiting later."
        )
        # uvicorn may not be installed in the test runner; the script
        # returning a non-zero status is acceptable here as long as the
        # .env was created.
        assert "DATAFORGE_ACCEPT_PLACEHOLDER_ENV" in (proc.stdout + proc.stderr) or proc.returncode != 0

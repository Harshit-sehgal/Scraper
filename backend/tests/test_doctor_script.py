"""Characterization tests for the ``scripts/doctor.py`` bootstrap gate.

These tests assert the public CLI contract of the doctor script. They do not
exhaustively check every check (that's the script's own job), but they do
guarantee the script is executable, exits 0 in a healthy repo, and emits the
documented JSON shape when asked. If the doctor script breaks, these tests
will catch the regression before a CI run does.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCTOR = REPO_ROOT / "scripts" / "doctor.py"


def _run(args: list[str], timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(DOCTOR), *args],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def test_doctor_script_exists_and_is_executable() -> None:
    assert DOCTOR.exists(), f"doctor script missing at {DOCTOR}"
    # The file should have a shebang (we set +x in the repo, but don't depend on filesystem mode).
    first_line = DOCTOR.read_text(encoding="utf-8").splitlines()[0]
    assert first_line.startswith("#!"), "doctor.py should start with a shebang"


def test_doctor_human_report_passes_in_healthy_repo() -> None:
    proc = _run([])
    assert proc.returncode == 0, f"doctor failed (exit={proc.returncode}):\n{proc.stdout}\n{proc.stderr}"
    assert "DataForge doctor" in proc.stdout
    assert "[OK" in proc.stdout
    assert "required:" in proc.stdout


def test_doctor_json_shape() -> None:
    proc = _run(["--json"])
    assert proc.returncode == 0, f"doctor --json failed: {proc.stderr}"
    payload = json.loads(proc.stdout)
    # Top-level shape
    for key in ("ok", "required_pass", "required_fail", "optional_fail", "checks"):
        assert key in payload, f"missing key {key!r} in doctor JSON"
    assert isinstance(payload["checks"], list)
    assert payload["checks"], "doctor must report at least one check"
    # Per-check shape
    sample = payload["checks"][0]
    for key in ("name", "required", "ok", "detail"):
        assert key in sample, f"missing key {key!r} in check {sample!r}"

#!/usr/bin/env python3
"""Run a local-only benchmark smoke suite and write evidence artifacts.

This script intentionally avoids live websites. It wraps fixture/config
benchmark tests that are safe for local validation and CI smoke checks.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_DIR = REPO_ROOT / "artifacts" / "benchmarks"
JSON_PATH = ARTIFACT_DIR / "latest_smoke.json"
MD_PATH = ARTIFACT_DIR / "latest_smoke.md"

COMMAND = [
    sys.executable,
    "-m",
    "pytest",
    "backend/tests/test_benchmark_fixtures.py",
    "backend/benchmarks/test_benchmark_smoke.py",
    "-q",
    "-m",
    "not live_benchmark and not browser and not golden_dataset",
    "-o",
    "addopts=",
]


def _redact(text: str) -> str:
    for key in (
        "DATAFORGE_API_KEY",
        "DATAFORGE_OPERATOR_API_KEY",
        "DATAFORGE_ADMIN_API_KEY",
        "DATAFORGE_SESSION_SECRET",
        "DATAFORGE_METRICS_TOKEN",
    ):
        value = os.environ.get(key, "")
        if value:
            text = text.replace(value, "<redacted>")
    return text


def main() -> int:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.setdefault("PYTHONPATH", "backend")
    env.setdefault("DATAFORGE_DOTENV_PATH", "/dev/null")
    env.setdefault("DATAFORGE_STORAGE_BACKEND", "sqlite")
    env.setdefault("DATAFORGE_ENV", "test")

    started = datetime.now(UTC)
    start = time.monotonic()
    timed_out = False
    try:
        completed = subprocess.run(
            COMMAND,
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        exit_code = completed.returncode
        stdout = _redact(completed.stdout)
        stderr = _redact(completed.stderr)
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        exit_code = 124
        stdout = _redact(exc.stdout or "")
        stderr = _redact(exc.stderr or "benchmark smoke timed out after 120 seconds")

    ended = datetime.now(UTC)
    duration = round(time.monotonic() - start, 3)
    status = "timeout" if timed_out else ("passed" if exit_code == 0 else "failed")

    payload = {
        "generated_at": ended.isoformat(),
        "started_at": started.isoformat(),
        "ended_at": ended.isoformat(),
        "duration_seconds": duration,
        "status": status,
        "exit_code": exit_code,
        "live_sites_used": False,
        "command": COMMAND,
        "stdout": stdout,
        "stderr": stderr,
        "artifacts": {
            "json": str(JSON_PATH.relative_to(REPO_ROOT)),
            "markdown": str(MD_PATH.relative_to(REPO_ROOT)),
        },
    }
    JSON_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    MD_PATH.write_text(
        "\n".join(
            [
                "# Benchmark Smoke Result",
                "",
                f"- generated_at: {payload['generated_at']}",
                f"- status: {status}",
                f"- exit_code: {exit_code}",
                f"- duration_seconds: {duration}",
                "- live_sites_used: false",
                f"- command: `{' '.join(COMMAND)}`",
                "",
                "## Stdout",
                "",
                "```text",
                stdout.strip(),
                "```",
                "",
                "## Stderr",
                "",
                "```text",
                stderr.strip(),
                "```",
                "",
            ],
        ),
        encoding="utf-8",
    )

    print(f"Benchmark smoke status: {status}")
    print(f"Wrote {JSON_PATH.relative_to(REPO_ROOT)}")
    print(f"Wrote {MD_PATH.relative_to(REPO_ROOT)}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

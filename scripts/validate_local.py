#!/usr/bin/env python3
"""Run reproducible local validation with bounded, redacted logs."""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
VALIDATION_DIR = ROOT / "artifacts" / "validation"
COMMANDS_DIR = VALIDATION_DIR / "commands"
RUNS_DIR = VALIDATION_DIR / "runs"
SUMMARY_MD = VALIDATION_DIR / "latest_summary.md"
SUMMARY_JSON = VALIDATION_DIR / "latest_summary.json"

SECRET_PATTERNS = [
    re.compile(r"(?i)(authorization\s*:\s*)(bearer\s+)?[^\s\r\n]+"),
    re.compile(r"(?i)(cookie\s*:\s*)[^\r\n]+"),
    re.compile(r"(?i)(dataforge_session=)[^;\s\r\n]+"),
    re.compile(r"(?i)((?:api[_-]?key|token|password|secret|session)[A-Za-z0-9_.-]*\s*[=:]\s*)[^\s\r\n]+"),
    re.compile(r"(?i)(DATAFORGE_[A-Z0-9_]*(?:KEY|SECRET|TOKEN|PASSWORD|SESSION)[A-Z0-9_]*=)[^\s\r\n]+"),
]

SAFE_ENV_DEFAULTS = {
    "DATAFORGE_DOTENV_PATH": "/dev/null",
    "DATAFORGE_ENV": "test",
    "DATAFORGE_STORAGE_BACKEND": "sqlite",
    "DATAFORGE_API_KEY": "user-key",
    "DATAFORGE_OPERATOR_API_KEY": "operator-key",
    "DATAFORGE_ADMIN_API_KEY": "admin-key",
    "DATAFORGE_SESSION_SECRET": "test-session-secret-change-me",
    "DATAFORGE_ALLOW_INSECURE_DEV_AUTH": "false",
    "DATAFORGE_SKIP_DB_CHECK": "true",
    "PYTHONPATH": "backend",
}


@dataclass(frozen=True)
class Check:
    name: str
    command: list[str]
    timeout: int
    required: bool = True
    cwd: Path = ROOT
    needs_executable: str | None = None
    expected: int | str = 0
    env_overrides: dict[str, str] = field(default_factory=dict)
    note: str = ""


def redact(text: str) -> tuple[str, bool]:
    redacted = text
    changed = False
    for pattern in SECRET_PATTERNS:
        redacted, count = pattern.subn(lambda match: "".join(group or "" for group in match.groups()) + "[REDACTED]", redacted)
        changed = changed or count > 0
    return redacted, changed


def slugify(value: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip().lower())
    return clean.strip("_") or "check"


def command_text(command: list[str]) -> str:
    return " ".join(command)


def safe_env(overrides: dict[str, str] | None = None) -> dict[str, str]:
    env = os.environ.copy()
    env.update(SAFE_ENV_DEFAULTS)
    if overrides:
        env.update(overrides)
    return env


def write_command_log(index: int, result: dict[str, Any], commands_dir: Path) -> Path:
    commands_dir.mkdir(parents=True, exist_ok=True)
    path = commands_dir / f"{index:02d}_{slugify(result['name'])}.md"
    lines = [
        f"# {result['name']}",
        "",
        f"- status: {result['status']}",
        f"- command: `{result['command']}`",
        f"- working_directory: `{result['working_directory']}`",
        f"- start_time: {result['start_time']}",
        f"- end_time: {result['end_time']}",
        f"- duration_seconds: {result['duration_seconds']:.2f}",
        f"- exit_code: {result['exit_code']}",
        f"- timeout_seconds: {result['timeout_seconds']}",
        f"- required: {str(result['required']).lower()}",
        f"- redaction_applied: {str(result['redaction_applied']).lower()}",
    ]
    if result.get("note"):
        lines.append(f"- note: {result['note']}")
    if result.get("skip_reason"):
        lines.append(f"- skip_reason: {result['skip_reason']}")
    lines.extend(
        [
            "",
            "## stdout",
            "",
            "```text",
            result.get("stdout", ""),
            "```",
            "",
            "## stderr",
            "",
            "```text",
            result.get("stderr", ""),
            "```",
            "",
        ],
    )
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def internal_result(name: str, status: str, stdout: str, *, required: bool = True, note: str = "") -> dict[str, Any]:
    now = datetime.now(UTC).isoformat()
    redacted_stdout, changed_out = redact(stdout)
    redacted_note, changed_note = redact(note)
    return {
        "name": name,
        "command": "internal check",
        "working_directory": str(ROOT),
        "start_time": now,
        "end_time": now,
        "duration_seconds": 0.0,
        "exit_code": 0 if status in {"passed", "skipped"} else 1,
        "timeout_seconds": 0,
        "required": required,
        "status": status,
        "stdout": redacted_stdout,
        "stderr": "",
        "redaction_applied": changed_out or changed_note,
        "note": redacted_note,
    }


def run_check(check: Check) -> dict[str, Any]:
    start = datetime.now(UTC)
    start_monotonic = time.monotonic()
    raw_command = command_text(check.command)

    if check.needs_executable and shutil.which(check.needs_executable) is None:
        end = datetime.now(UTC)
        return {
            "name": check.name,
            "command": raw_command,
            "working_directory": str(check.cwd),
            "start_time": start.isoformat(),
            "end_time": end.isoformat(),
            "duration_seconds": time.monotonic() - start_monotonic,
            "exit_code": None,
            "timeout_seconds": check.timeout,
            "required": check.required,
            "status": "not_installed",
            "stdout": "",
            "stderr": f"Required executable not found: {check.needs_executable}",
            "redaction_applied": False,
            "note": check.note,
        }

    try:
        completed = subprocess.run(
            check.command,
            cwd=check.cwd,
            env=safe_env(check.env_overrides),
            text=True,
            capture_output=True,
            timeout=check.timeout,
            check=False,
        )
        end = datetime.now(UTC)
        stdout, changed_out = redact(completed.stdout or "")
        stderr, changed_err = redact(completed.stderr or "")
        note, changed_note = redact(check.note)
        if "No module named" in stderr:
            status = "not_installed"
        elif check.expected == "nonzero":
            status = "passed" if completed.returncode != 0 else "failed"
        else:
            status = "passed" if completed.returncode == check.expected else "failed"
        return {
            "name": check.name,
            "command": raw_command,
            "working_directory": str(check.cwd),
            "start_time": start.isoformat(),
            "end_time": end.isoformat(),
            "duration_seconds": time.monotonic() - start_monotonic,
            "exit_code": completed.returncode,
            "timeout_seconds": check.timeout,
            "required": check.required,
            "status": status,
            "stdout": stdout,
            "stderr": stderr,
            "redaction_applied": changed_out or changed_err or changed_note,
            "note": note,
        }
    except subprocess.TimeoutExpired as exc:
        end = datetime.now(UTC)
        stdout = exc.stdout.decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        stdout, changed_out = redact(stdout)
        stderr, changed_err = redact(stderr)
        note, changed_note = redact(check.note)
        return {
            "name": check.name,
            "command": raw_command,
            "working_directory": str(check.cwd),
            "start_time": start.isoformat(),
            "end_time": end.isoformat(),
            "duration_seconds": time.monotonic() - start_monotonic,
            "exit_code": None,
            "timeout_seconds": check.timeout,
            "required": check.required,
            "status": "timeout",
            "stdout": stdout,
            "stderr": stderr,
            "redaction_applied": changed_out or changed_err or changed_note,
            "note": note,
        }


def build_common_checks(py: str, frontend_exists: bool) -> list[Check]:
    checks = [
        Check("python_version", [py, "--version"], 30),
        Check("git_commit", ["git", "rev-parse", "--short", "HEAD"], 30, required=False, needs_executable="git"),
        Check("git_status_short", ["git", "status", "--short"], 30, required=False, needs_executable="git"),
    ]
    if frontend_exists:
        checks.extend(
            [
                Check("node_version", ["node", "--version"], 30, required=False, needs_executable="node"),
                Check("npm_version", ["npm", "--version"], 30, required=False, needs_executable="npm"),
            ],
        )
    return checks


def backend_quick_checks(py: str) -> list[Check]:
    return [
        Check("compileall", [py, "-m", "compileall", "-q", "backend", "scripts", "architecture_validator.py"], 60),
        Check("architecture_validator", [py, "architecture_validator.py"], 60),
        Check("research_boundary", [py, "scripts/check_research_boundary.py"], 60),
        Check("dependency_bounds", [py, "scripts/validate_dependency_bounds.py"], 60),
        Check(
            "url_and_research_smoke_tests",
            [py, "-m", "pytest", "backend/tests/test_url_safety.py", "backend/tests/test_research_boundary.py", "-q"],
            120,
        ),
        Check(
            "p0_regression_tests",
            [
                py,
                "-m",
                "pytest",
                "backend/tests/test_p0_auth_tenant.py",
                "backend/tests/test_p0_billing_usage.py",
                "backend/tests/test_route_auth_matrix_generator.py",
                "-q",
            ],
            180,
        ),
    ]


def backend_full_checks(py: str) -> list[Check]:
    return [
        Check("backend_full_tests", [py, "-m", "pytest", "backend/tests", "-q"], 600),
    ]


def static_checks(py: str) -> list[Check]:
    return [
        Check("ruff_check", [py, "-m", "ruff", "check", "backend", "scripts"], 300),
        Check("pyflakes", [py, "-m", "pyflakes", "backend/app", "backend/tests", "scripts"], 300),
        Check("mypy", [py, "-m", "mypy", "backend"], 300),
    ]


def security_checks(py: str) -> list[Check]:
    prod_env_path = ROOT / ".env.production.example"
    checks = [
        Check("bandit_backend", [py, "-m", "bandit", "-r", "backend", "-q"], 300),
        Check("pip_audit", [py, "-m", "pip_audit"], 300),
    ]
    if prod_env_path.exists():
        checks.append(
            Check(
                "prod_env_example_placeholder_check",
                [py, "scripts/check_prod_env.py", "--env-file", str(prod_env_path)],
                120,
                expected="nonzero",
                env_overrides={"DATAFORGE_ENV": "production", "DATAFORGE_SKIP_DB_CHECK": "true"},
                note="Expected fail for placeholder example env; this is not production readiness evidence.",
            ),
        )
    return checks


def frontend_checks() -> list[Check]:
    if not (ROOT / "package.json").exists():
        return []
    return [
        Check("npm_ci", ["npm", "ci"], 600, needs_executable="npm"),
        Check("frontend_tests", ["npm", "run", "test"], 300, needs_executable="npm"),
        Check("frontend_lint_js", ["npm", "run", "lint:js"], 300, needs_executable="npm"),
    ]


def required_path_result() -> dict[str, Any]:
    required_paths = [
        "backend",
        "scripts",
        "architecture_validator.py",
        "artifacts/audit",
        "docs",
    ]
    missing = [path for path in required_paths if not (ROOT / path).exists()]
    status = "failed" if missing else "passed"
    stdout = "Required paths present." if not missing else "Missing required paths:\n" + "\n".join(missing)
    return internal_result("required_paths", status, stdout)


def checks_for_mode(mode: str, py: str) -> list[Check]:
    frontend_exists = (ROOT / "package.json").exists()
    common = build_common_checks(py, frontend_exists)
    if mode == "quick":
        return common + backend_quick_checks(py)
    if mode == "backend":
        return common + backend_quick_checks(py) + backend_full_checks(py)
    if mode == "frontend":
        return common + frontend_checks()
    if mode == "security":
        return common + security_checks(py)
    if mode == "full":
        return (
            common
            + backend_quick_checks(py)
            + backend_full_checks(py)
            + static_checks(py)
            + security_checks(py)
            + frontend_checks()
        )
    message = f"Unsupported mode: {mode}"
    raise ValueError(message)


def summarize(mode: str, run_id: str, archive_dir: Path, results: list[dict[str, Any]]) -> dict[str, Any]:
    counts = dict.fromkeys(["passed", "failed", "skipped", "timeout", "not_installed"], 0)
    for result in results:
        counts[result["status"]] = counts.get(result["status"], 0) + 1
    failing_required = [
        result for result in results if result["required"] and result["status"] in {"failed", "timeout", "not_installed"}
    ]
    overall_status = "passed" if not failing_required else "failed"
    if overall_status == "passed":
        next_action = "Proceed with the requested change after reviewing logs for warnings."
    else:
        next_action = "Inspect failed command logs under artifacts/validation/commands/ and fix or document the failures."
    return {
        "mode": mode,
        "run_id": run_id,
        "archive_dir": str(archive_dir),
        "generated_at": datetime.now(UTC).isoformat(),
        "overall_status": overall_status,
        "counts": counts,
        "failing_required": [result["name"] for result in failing_required],
        "next_recommended_action": next_action,
        "results": results,
    }


def write_summary(summary: dict[str, Any], archive_dir: Path) -> None:
    VALIDATION_DIR.mkdir(parents=True, exist_ok=True)
    SUMMARY_JSON.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        "# Latest Validation Summary",
        "",
        f"- generated_at: {summary['generated_at']}",
        f"- mode: {summary['mode']}",
        f"- run_id: {summary['run_id']}",
        f"- archive_dir: `{Path(summary['archive_dir']).relative_to(ROOT)}`",
        f"- overall_status: {summary['overall_status']}",
        f"- passed: {summary['counts'].get('passed', 0)}",
        f"- failed: {summary['counts'].get('failed', 0)}",
        f"- skipped: {summary['counts'].get('skipped', 0)}",
        f"- timed_out: {summary['counts'].get('timeout', 0)}",
        f"- not_installed: {summary['counts'].get('not_installed', 0)}",
        f"- next_recommended_action: {summary['next_recommended_action']}",
        "",
        "## Commands",
        "",
        "| Status | Required | Name | Exit | Log |",
        "| --- | --- | --- | --- | --- |",
    ]
    for result in summary["results"]:
        log_path = Path(result["log_path"]).relative_to(ROOT) if result.get("log_path") else ""
        lines.append(
            f"| {result['status']} | {str(result['required']).lower()} | {result['name']} | {result['exit_code']} | `{log_path}` |",
        )
    lines.append("")
    SUMMARY_MD.write_text("\n".join(lines), encoding="utf-8")

    archive_summary = copy.deepcopy(summary)
    for result in archive_summary["results"]:
        if result.get("archive_log_path"):
            result["log_path"] = result["archive_log_path"]
    archive_dir.mkdir(parents=True, exist_ok=True)
    (archive_dir / "summary.json").write_text(json.dumps(archive_summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    archive_lines = lines.copy()
    for index, line in enumerate(archive_lines):
        if line.startswith("- archive_dir:"):
            archive_lines[index] = f"- archive_dir: `{archive_dir.relative_to(ROOT)}`"
        elif line.startswith("| ") and "`artifacts/validation/commands/" in line:
            archive_lines[index] = line.replace("artifacts/validation/commands/", f"{archive_dir.relative_to(ROOT)}/commands/")
    (archive_dir / "summary.md").write_text("\n".join(archive_lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run DataForge local validation.")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--quick", action="store_true", help="Run quick stable validation checks.")
    modes.add_argument("--full", action="store_true", help="Run quick, backend, static, security, and frontend checks.")
    modes.add_argument("--backend", action="store_true", help="Run backend quick checks and full backend tests.")
    modes.add_argument("--frontend", action="store_true", help="Run frontend install, test, and lint checks.")
    modes.add_argument("--security", action="store_true", help="Run security-oriented checks.")
    parser.add_argument("--json", action="store_true", help="Print the JSON summary to stdout.")
    return parser.parse_args()


def selected_mode(args: argparse.Namespace) -> str:
    for mode in ["full", "backend", "frontend", "security", "quick"]:
        if getattr(args, mode):
            return mode
    return "quick"


def main() -> int:
    args = parse_args()
    mode = selected_mode(args)
    py = sys.executable
    progress_stream = sys.stderr if args.json else sys.stdout
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + f"_{mode}"
    archive_dir = RUNS_DIR / run_id
    archive_commands_dir = archive_dir / "commands"

    VALIDATION_DIR.mkdir(parents=True, exist_ok=True)
    COMMANDS_DIR.mkdir(parents=True, exist_ok=True)
    for old_log in COMMANDS_DIR.glob("*.md"):
        old_log.unlink()

    results = [required_path_result()]
    results[0]["log_path"] = str(write_command_log(0, results[0], COMMANDS_DIR))
    results[0]["archive_log_path"] = str(write_command_log(0, results[0], archive_commands_dir))

    checks = checks_for_mode(mode, py)
    for index, check in enumerate(checks, start=1):
        print(f"[{index}/{len(checks)}] {check.name}...", file=progress_stream, flush=True)
        result = run_check(check)
        result["log_path"] = str(write_command_log(index, result, COMMANDS_DIR))
        result["archive_log_path"] = str(write_command_log(index, result, archive_commands_dir))
        results.append(result)
        print(f"  {result['status']} ({result['duration_seconds']:.2f}s)", file=progress_stream, flush=True)

    summary = summarize(mode, run_id, archive_dir, results)
    write_summary(summary, archive_dir)

    print(f"Validation summary: {SUMMARY_MD.relative_to(ROOT)}", file=progress_stream)
    print(f"Overall status: {summary['overall_status']}", file=progress_stream)
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["overall_status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

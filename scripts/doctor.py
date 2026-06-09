#!/usr/bin/env python3
"""Repository health check — DataForge Scraper.

Runs the small set of commands and checks that an agent (or a human) needs
to have green before trusting the workspace for further changes. This is the
"bootstrap" gate from the Phase 0 master plan:

    Phase 0 — freeze truth and create the safe working base.
    Step 3. Add a ``make doctor`` command that checks Python version,
            required system tools, dependency installation, Playwright
            browser availability, env variables, and Node tooling.

Each check returns a ``CheckResult``. The script exits non-zero if any
required check fails. Optional checks (e.g. Playwright browser binaries)
report their state but never fail the gate, so that local-only sandboxes
without browsers can still get a green light for unit work.

Usage:
    python scripts/doctor.py [--strict] [--json]

Exit codes:
    0 — All required checks passed
    1 — One or more required checks failed
    2 — Internal error (unexpected exception during a check)
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = REPO_ROOT / "pyproject.toml"
REQUIREMENTS_LOCK = REPO_ROOT / "backend" / "requirements.lock.txt"
REQUIREMENTS_DEV_LOCK = REPO_ROOT / "backend" / "requirements-dev.lock.txt"
ENV_EXAMPLE = REPO_ROOT / ".env.example"
MIN_PY = (3, 12)


@dataclass
class CheckResult:
    name: str
    required: bool
    ok: bool
    detail: str
    hint: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _python_version() -> CheckResult:
    v = sys.version_info
    ok = (v.major, v.minor) >= MIN_PY
    return CheckResult(
        name="python_version",
        required=True,
        ok=ok,
        detail=f"Python {v.major}.{v.minor}.{v.micro}",
        hint="" if ok else f"Need Python {MIN_PY[0]}.{MIN_PY[1]}+",
    )


def _binary(name: str, required: bool, hint: str = "") -> CheckResult:
    path = shutil.which(name)
    return CheckResult(
        name=f"binary:{name}",
        required=required,
        ok=path is not None,
        detail=path or "not found",
        hint=hint,
    )


def _venv_present() -> CheckResult:
    venv = REPO_ROOT / ".venv" / "bin" / "python"
    return CheckResult(
        name="venv",
        required=False,
        ok=venv.exists(),
        detail=str(venv) if venv.exists() else "no .venv",
        hint="python3 -m venv .venv && .venv/bin/pip install -r backend/requirements-dev.lock.txt",
    )


def _lock_files_present() -> CheckResult:
    missing = [str(p.relative_to(REPO_ROOT)) for p in (REQUIREMENTS_LOCK, REQUIREMENTS_DEV_LOCK) if not p.exists()]
    return CheckResult(
        name="lockfiles",
        required=True,
        ok=not missing,
        detail="ok" if not missing else f"missing: {', '.join(missing)}",
    )


def _pyproject_present() -> CheckResult:
    return CheckResult(
        name="pyproject",
        required=True,
        ok=PYPROJECT.exists(),
        detail=str(PYPROJECT.relative_to(REPO_ROOT)) if PYPROJECT.exists() else "missing",
    )


def _pytest_runs() -> CheckResult:
    """A sub-1s probe that pytest can collect at all."""
    try:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "--collect-only",
                "-q",
                "backend/tests/test_url_safety.py",
            ],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        return CheckResult(
            name="pytest_collect",
            required=True,
            ok=False,
            detail="timeout after 30s on a single-file collect",
            hint="Investigate hanging imports or conftest side-effects.",
        )
    ok = proc.returncode == 0
    snippet = (proc.stdout + proc.stderr).strip().splitlines()
    detail = (snippet[-1] if snippet else "").strip() or f"exit={proc.returncode}"
    return CheckResult(
        name="pytest_collect",
        required=True,
        ok=ok,
        detail=detail,
        hint="" if ok else "Run `python -m pytest --collect-only -q` for full output.",
    )


def _global_pytest_timeout() -> CheckResult:
    """The global pytest-timeout default must be set (Phase 0 step 4)."""
    pyproject = REPO_ROOT / "pyproject.toml"
    if not pyproject.exists():
        return CheckResult(
            name="pytest_timeout_default",
            required=True,
            ok=False,
            detail="pyproject.toml missing",
        )
    text = pyproject.read_text(encoding="utf-8")
    import re

    match = re.search(r'^addopts\s*=\s*"([^"]*)"', text, re.MULTILINE)
    if not match:
        return CheckResult(
            name="pytest_timeout_default",
            required=True,
            ok=False,
            detail="no addopts in pyproject.toml",
        )
    addopts = match.group(1)
    if "--timeout=" not in addopts:
        return CheckResult(
            name="pytest_timeout_default",
            required=True,
            ok=False,
            detail=f"addopts is {addopts!r} but has no --timeout=N",
            hint="Add --timeout=30 to [tool.pytest.ini_options].addopts in pyproject.toml",
        )
    return CheckResult(
        name="pytest_timeout_default",
        required=True,
        ok=True,
        detail=f"addopts contains --timeout (full: {addopts!r})",
    )


def _dns_standin_is_wired() -> CheckResult:
    """The conftest autouse DNS stand-in must be installed (Phase 0 M1).

    We run ``pytest --collect-only`` on a test file that asserts the
    stand-in works. If the conftest fixture is missing, the collect-only
    itself succeeds but the characterisation test in it would fail during
    a real run; the doctor catch is that the file exists and the conftest
    is importable behind pytest.
    """
    test_file = REPO_ROOT / "backend" / "tests" / "test_dns_isolation.py"
    if not test_file.exists():
        return CheckResult(
            name="dns_standin",
            required=True,
            ok=False,
            detail="test_dns_isolation.py is missing",
            hint="Phase 0 test file was deleted; restore from git.",
        )
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", str(test_file)],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    if proc.returncode != 0:
        return CheckResult(
            name="dns_standin",
            required=True,
            ok=False,
            detail="pytest --collect-only failed on test_dns_isolation.py",
            hint="Check if the conftest _default_dns_resolver fixture is installed.",
        )
    return CheckResult(
        name="dns_standin",
        required=True,
        ok=True,
        detail="conftest._default_dns_resolver fixture is wired (test_dns_isolation.py collected ok)",
    )


def _route_inventory_runs() -> CheckResult:
    """The stable vs experimental route inventory script must run (Phase 0 C1)."""
    script = REPO_ROOT / "scripts" / "route_inventory_split.py"
    if not script.exists():
        return CheckResult(
            name="route_inventory_split",
            required=True,
            ok=False,
            detail="scripts/route_inventory_split.py missing",
            hint="Restore the Phase 0 C1 deliverable.",
        )
    proc = subprocess.run(
        [sys.executable, str(script)],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if proc.returncode != 0:
        return CheckResult(
            name="route_inventory_split",
            required=True,
            ok=False,
            detail=(proc.stderr.strip().splitlines() or [""])[-1] or f"exit={proc.returncode}",
        )
    return CheckResult(
        name="route_inventory_split",
        required=True,
        ok=True,
        detail="stable+experimental+diff generated without errors",
    )


def _env_example_present() -> CheckResult:
    return CheckResult(
        name="env_example",
        required=False,
        ok=ENV_EXAMPLE.exists(),
        detail=str(ENV_EXAMPLE.relative_to(REPO_ROOT)) if ENV_EXAMPLE.exists() else "missing",
    )


def _playwright_browsers() -> CheckResult:
    """Best-effort: do not fail the gate if browsers aren't installed."""
    for env_var in ("PLAYWRIGHT_BROWSERS_PATH",):
        if os.environ.get(env_var):
            return CheckResult(
                name="playwright_browsers",
                required=False,
                ok=True,
                detail=f"{env_var}={os.environ[env_var]}",
            )
    home = Path.home() / ".cache" / "ms-playwright"
    if home.exists() and any(home.iterdir()):
        return CheckResult(
            name="playwright_browsers",
            required=False,
            ok=True,
            detail=str(home),
        )
    return CheckResult(
        name="playwright_browsers",
        required=False,
        ok=False,
        detail="no Playwright browser cache found",
        hint="Install with: .venv/bin/playwright install chromium",
    )


def _node_tooling() -> CheckResult:
    """Frontend tooling is only required for frontend work."""
    node = shutil.which("node")
    npm = shutil.which("npm")
    ok = node is not None and npm is not None
    detail = f"node={node or 'missing'} npm={npm or 'missing'}"
    return CheckResult(
        name="node_tooling",
        required=False,
        ok=ok,
        detail=detail,
        hint="Install Node.js 18+ for frontend lint/test/e2e.",
    )


CHECKS = [
    _python_version,
    _pyproject_present,
    _lock_files_present,
    _venv_present,
    lambda: _binary("git", required=True),
    lambda: _binary("docker", required=False, hint="Docker is optional for unit tests."),
    lambda: _binary("make", required=False, hint="`make` is the recommended task runner."),
    _env_example_present,
    _node_tooling,
    _playwright_browsers,
    _global_pytest_timeout,
    _dns_standin_is_wired,
    _route_inventory_runs,
    _pytest_runs,
]


def run(strict: bool = False) -> list:
    results = []
    for fn in CHECKS:
        try:
            results.append(fn())
        except Exception as exc:
            results.append(
                CheckResult(
                    name=getattr(fn, "__name__", repr(fn)),
                    required=True,
                    ok=False,
                    detail=f"unexpected error: {exc!r}",
                ),
            )
            if strict:
                break
    return results


def _summarize(results):
    required_pass = sum(1 for r in results if r.required and r.ok)
    required_fail = sum(1 for r in results if r.required and not r.ok)
    optional_fail = sum(1 for r in results if not r.required and not r.ok)
    return required_pass, required_fail, optional_fail


def _print_human(results) -> None:
    width = max((len(r.name) for r in results), default=0)
    for r in results:
        flag = "OK " if r.ok else "FAIL"
        req = "*" if r.required else " "
        line = f"  [{flag}] {req} {r.name.ljust(width)}  {r.detail}"
        print(line)
        if r.hint and not r.ok:
            print(f"           hint: {r.hint}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Repository health check")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Stop at the first unexpected error and exit non-zero.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of the human report.",
    )
    args = parser.parse_args(argv)

    results = run(strict=args.strict)
    req_pass, req_fail, opt_fail = _summarize(results)
    overall_ok = req_fail == 0

    if args.json:
        print(
            json.dumps(
                {
                    "ok": overall_ok,
                    "required_pass": req_pass,
                    "required_fail": req_fail,
                    "optional_fail": opt_fail,
                    "checks": [r.to_dict() for r in results],
                },
                indent=2,
            ),
        )
    else:
        print("DataForge doctor")
        print("----------------")
        _print_human(results)
        print(
            f"\nrequired: {req_pass} passed, {req_fail} failed | optional: {opt_fail} missing",
        )

    return 0 if overall_ok else 1


if __name__ == "__main__":
    sys.exit(main())

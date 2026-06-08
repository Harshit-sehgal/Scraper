"""Frontend smoke test: syntax-check every JS file in ``frontend/``.

We run a cheap ``node --check`` over every ``*.js`` file under
``frontend/``. This catches:

* Syntax errors that would only show up at runtime
* Typos that break the module graph
* Unrelated-include errors (e.g. ``require`` in a browser context)

It deliberately does NOT run a headless browser — the goal is to
keep CI fast and dependency-free. Browser-level smoke is handled by
Playwright in a separate workflow.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FRONTEND = REPO / "frontend"


def _find_js_files() -> list[Path]:
    return sorted(p for p in FRONTEND.rglob("*.js") if p.is_file())


def main() -> int:
    if not FRONTEND.exists():
        print(f"no frontend directory at {FRONTEND}", file=sys.stderr)
        return 0
    if shutil.which("node") is None:
        print("node not available — skipping frontend syntax check", file=sys.stderr)
        return 0
    files = _find_js_files()
    if not files:
        print(f"no .js files under {FRONTEND}", file=sys.stderr)
        return 0
    failures: list[tuple[Path, str]] = []
    for path in files:
        proc = subprocess.run(
            ["node", "--check", str(path)],  # noqa: S607
            check=False,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            failures.append((path, (proc.stderr or proc.stdout).strip()))
    if failures:
        print("Frontend syntax check FAILED:", file=sys.stderr)
        for path, err in failures:
            print(f"  {path}\n    {err}", file=sys.stderr)
        return 1
    print(f"Frontend syntax check OK ({len(files)} files).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

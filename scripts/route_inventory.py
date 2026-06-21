#!/usr/bin/env python3
"""Auto-generate the route inventory from the live FastAPI app.

The deep-research report's **Medium-2 — docs drift** finding says
that "this script is not yet linted" for the rest of the route
families. This script is the inverse direction: produce a Markdown
inventory that can be diffed against ``docs/API.md`` in CI.

Usage::

    python3 scripts/route_inventory.py > /tmp/routes.md
    diff -u docs/API.md /tmp/routes.md
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _live_routes() -> set[tuple[str, str]]:
    code = (
        "import sys, json;"
        "sys.path.insert(0, 'scripts');"
        "from fastapi_route_iter import iter_app_routes;"
        "from app.main import create_app;"
        "app=create_app();"
        "out=set();"
        "[out.add((m.upper(), r.path)) for r in iter_app_routes(app) "
        "if hasattr(r, 'methods') and r.path.startswith('/api/') "
        "for m in r.methods if m.upper() in {'GET','POST','PUT','PATCH','DELETE','OPTIONS','HEAD'}];"
        "print(json.dumps(sorted(out)))"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(REPO),
        env={
            **os.environ,
            "PYTHONPATH": "backend",
            "DATAFORGE_DOTENV_PATH": "/dev/null",
            "DATAFORGE_STORAGE_BACKEND": "sqlite",
        },
    )
    if proc.returncode != 0:
        print("Failed to import app.main:", file=sys.stderr)
        print(proc.stderr, file=sys.stderr)
        sys.exit(2)
    return {tuple(x) for x in json.loads(proc.stdout)}


_PREFIX_TO_SECTION: list[tuple[str, str]] = [
    ("/api/jobs", "Job and Result Routes"),
    ("/api/recycle_bin", "Recycle Bin Routes"),
    ("/api/discover", "Discovery and URL Analysis"),
    ("/api/schema", "Discovery and URL Analysis"),
    ("/api/url", "Discovery and URL Analysis"),
    ("/api/scraper", "Scraper/Telemetry Routes"),
    ("/api/operator", "Operator and System Routes"),
    ("/api/system", "Operator and System Routes"),
]


def main() -> int:
    routes = sorted(_live_routes())
    by_section: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for method, path in routes:
        placed = False
        for prefix, section in _PREFIX_TO_SECTION:
            if path == prefix or path.startswith(prefix + "/"):
                by_section[section].append((method, path))
                placed = True
                break
        if not placed:
            by_section["Other"].append((method, path))
    print("# Auto-generated Route Inventory\n")
    print(f"Total /api routes: {len(routes)}\n")
    for section in dict.fromkeys(s for _, s in _PREFIX_TO_SECTION):
        rows = by_section.pop(section, [])
        if not rows:
            continue
        print(f"\n## {section}\n")
        print("| Method | Path |")
        print("| --- | --- |")
        for method, path in rows:
            print(f"| {method} | `{path}` |")
    if by_section.get("Other"):
        print("\n## Other\n")
        print("| Method | Path |")
        print("| --- | --- |")
        for method, path in by_section["Other"]:
            print(f"| {method} | `{path}` |")
    return 0


if __name__ == "__main__":
    sys.exit(main())

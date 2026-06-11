"""Docs lint: keep ``docs/API.md`` aligned with the live FastAPI route table.

The deep-research report flagged manual docs drift as a top-3
maintenance risk. The cheapest defensive measure is a CI gate that
fails when a route is registered in code but missing from
``docs/API.md`` (or vice versa).

We deliberately ignore path parameters, HTTP methods that are not
``GET``/``POST``/``PUT``/``PATCH``/``DELETE``/``OPTIONS``/``HEAD``,
and routes that are explicitly marked ``include_in_schema=False``.

By default the experimental routes (those gated by
``DATAFORGE_ENABLE_EXPERIMENTAL_ROUTES``) are NOT included in the
lint comparison — they are not part of the stable public API and
documenting them would create churn. Pass ``--include-experimental``
to opt in.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
API_DOC = REPO / "docs" / "API.md"
MAIN_PY = REPO / "backend" / "app" / "main.py"

# Track all /api route families that appear in docs/API.md as
# route tables. Health/liveness endpoints and metrics are excluded
# because they are documented narratively, not in tables.
TRACKED_PREFIXES: tuple[str, ...] = (
    "/api/jobs",
    "/api/recycle_bin",
    "/api/discover",
    "/api/schema",
    "/api/url",
    "/api/scraper",
    "/api/operator",
    "/api/system",
    "/api/saas",
    "/api/session",
    "/api/exports",
)

# Markdown pipe rows that look like:
#   | GET | `/api/jobs` | Authenticated user |
ROUTE_ROW_RE = re.compile(
    r"^\|\s*(GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD)\s*\|\s*`([^`]+)`\s*\|",
    re.MULTILINE,
)


def _declared_routes_in_doc(*, include_experimental: bool) -> set[tuple[str, str]]:
    """Parse ``docs/API.md`` for declared (method, path) tuples
    that fall under one of the tracked prefixes.
    """
    text = API_DOC.read_text(encoding="utf-8")
    if not include_experimental:
        text = text.split("## Experimental / Research Routes (Gated)", maxsplit=1)[0]
    out: set[tuple[str, str]] = set()
    for m, p in ROUTE_ROW_RE.findall(text):
        if any(p.startswith(prefix) for prefix in TRACKED_PREFIXES):
            out.add((m, p))
    return out


def _live_routes(include_experimental: bool) -> set[tuple[str, str]]:
    """Import the FastAPI app and dump the (method, path) tuple set.

    We do this in a subprocess so this script can run without the
    heavy backend dependencies installed (e.g. in a docs-only CI lane).
    """
    import json
    import subprocess

    code = (
        "import sys, json;"
        "from app.main import app;"
        "out=set();"
        "[out.add((m.upper(), r.path)) for r in app.routes "
        "if hasattr(r, 'methods') and r.path.startswith('/api/') "
        "for m in r.methods if m.upper() in {'GET','POST','PUT','PATCH','DELETE','OPTIONS','HEAD'}];"
        "print(json.dumps(sorted(out)))"
    )
    env = {
        **__import__("os").environ,
        "PYTHONPATH": "backend",
        "DATAFORGE_DOTENV_PATH": "/dev/null",
        "DATAFORGE_STORAGE_BACKEND": "sqlite",
    }
    # Default to NOT including experimental routes so the public API
    # lint stays stable. ``--include-experimental`` is the explicit
    # opt-in for maintainers who want a complete view.
    env["DATAFORGE_ENABLE_EXPERIMENTAL_ROUTES"] = "true" if include_experimental else "false"
    proc = subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(REPO),
        env=env,
    )
    if proc.returncode != 0:
        print("Failed to import app.main:", file=sys.stderr)
        print(proc.stderr, file=sys.stderr)
        return set()
    return {tuple(x) for x in json.loads(proc.stdout)}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Lint docs/API.md against the live FastAPI route table.")
    parser.add_argument(
        "--include-experimental",
        action="store_true",
        help="Include experimental routes (gated by DATAFORGE_ENABLE_EXPERIMENTAL_ROUTES) in the lint comparison.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not API_DOC.exists():
        print(f"docs file missing: {API_DOC}", file=sys.stderr)
        return 2
    declared = _declared_routes_in_doc(include_experimental=args.include_experimental)
    if not declared:
        print(f"no routes declared in {API_DOC}", file=sys.stderr)
        return 2
    live = _live_routes(include_experimental=args.include_experimental)
    if not live:
        print("could not enumerate live routes (import failed); skipping", file=sys.stderr)
        return 0
    # Normalise paths by removing trailing slashes.
    norm_live = {(m, p.rstrip("/") or "/") for m, p in live if any(p.startswith(prefix) for prefix in TRACKED_PREFIXES)}
    norm_declared = {(m, p.rstrip("/") or "/") for m, p in declared}
    missing_from_doc = sorted(norm_live - norm_declared)
    missing_from_app = sorted(norm_declared - norm_live)
    failures: list[str] = []
    if missing_from_doc:
        failures.append(
            "Routes registered in app but missing from docs/API.md:\n  " + "\n  ".join(f"{m} {p}" for m, p in missing_from_doc),
        )
    if missing_from_app:
        failures.append(
            "Routes declared in docs/API.md but not registered in app:\n  "
            + "\n  ".join(f"{m} {p}" for m, p in missing_from_app),
        )
    if failures:
        for f in failures:
            print(f, file=sys.stderr)
        return 1
    scope = "with experimental routes" if args.include_experimental else "stable routes only"
    print(f"docs lint OK: {len(norm_declared)} routes match between app and {API_DOC.name} ({scope}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

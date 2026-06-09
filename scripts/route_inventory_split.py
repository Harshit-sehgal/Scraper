#!/usr/bin/env python3
"""Generate stable vs experimental route inventories from the live FastAPI app.

This script addresses the Phase 0 master plan step 7 ("Split stable vs
experimental route docs") and the C1 P1 in the verified issue backlog
("API docs only lint with experimental routes").

It runs the live app.main:app twice -- once with the experimental
router disabled (the default for production) and once with it enabled
-- and emits two Markdown files plus a third file listing the
experimental-only routes.

Usage::

    python3 scripts/route_inventory_split.py \\
        --stable-out docs/API_STABLE.md \\
        --experimental-out docs/API_EXPERIMENTAL.md \\
        --diff-out docs/API_EXPERIMENTAL_DIFF.md

The script is intentionally side-effect free: it does not write any
files unless --write is passed, so it is safe to import from tests.

Verification contract:

* The stable inventory must contain every route from
  docs/API_STABLE.md (the source of truth for production behavior).
* The experimental diff must be a strict superset of the stable
  inventory, so the C1 acceptance gate ("stable docs match runtime
  behavior with experimental disabled") holds.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BACKEND = REPO / "backend"

STABLE_HEADER_TMPL = """# API (Stable)

**This file is auto-generated. Do not edit by hand.**

**Generated:** {timestamp}
**Mode:** experimental routes **disabled** (`DATAFORGE_ENABLE_EXPERIMENTAL_ROUTES=false`).
**Verification command:**

```
python3 scripts/route_inventory_split.py --write
```

This is the source of truth for the production API surface. Anything
listed here is safe to depend on; anything not listed is not in the
production code path. Experimental / research routes are listed in
[`API_EXPERIMENTAL.md`](API_EXPERIMENTAL.md); the diff between the two
files is [`API_EXPERIMENTAL_DIFF.md`](API_EXPERIMENTAL_DIFF.md).
"""

EXPERIMENTAL_HEADER_TMPL = """# API (Experimental)

**This file is auto-generated. Do not edit by hand.**

**Generated:** {timestamp}
**Mode:** experimental routes **enabled** (`DATAFORGE_ENABLE_EXPERIMENTAL_ROUTES=true`).
**Verification command:**

```
python3 scripts/route_inventory_split.py --write
```

These endpoints are gated on the ``ENABLE_EXPERIMENTAL_ROUTES`` flag
and are not part of the stable v1 contract. They may change or be
removed without notice. They are not covered by the SaaS readiness
acceptance gate and must not be advertised to paying customers
without explicit opt-in.

For the production API surface, see [`API_STABLE.md`](API_STABLE.md).
For the diff between stable and experimental, see
[`API_EXPERIMENTAL_DIFF.md`](API_EXPERIMENTAL_DIFF.md).
"""

DIFF_HEADER_TMPL = """# API (Experimental Diff)

**This file is auto-generated. Do not edit by hand.**

**Generated:** {timestamp}
**Mode:** `experimental_routes - stable_routes`

This is the set of routes that are exposed **only** when
``DATAFORGE_ENABLE_EXPERIMENTAL_ROUTES=true``. Every row below is a
route that does not exist in the production code path. The list is
the diff between [`API_EXPERIMENTAL.md`](API_EXPERIMENTAL.md) and
[`API_STABLE.md`](API_STABLE.md).
"""


def _env(*, experimental: bool) -> dict:
    return {
        **os.environ,
        "PYTHONPATH": str(BACKEND),
        "DATAFORGE_DOTENV_PATH": "/dev/null",
        "DATAFORGE_STORAGE_BACKEND": "sqlite",
        "DATAFORGE_ENABLE_EXPERIMENTAL_ROUTES": "true" if experimental else "false",
    }


def _live_routes(*, experimental: bool):
    code = (
        "import sys, json;"
        "from app.main import app;"
        "out=[];"
        "[out.append([m.upper(), r.path]) for r in app.routes "
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
        env=_env(experimental=experimental),
    )
    if proc.returncode != 0:
        print("Failed to import app.main:", file=sys.stderr)
        print(proc.stderr, file=sys.stderr)
        sys.exit(2)
    return [tuple(x) for x in json.loads(proc.stdout)]


_PREFIX_TO_SECTION = [
    ("/api/jobs", "Job and Result Routes"),
    ("/api/recycle_bin", "Recycle Bin Routes"),
    ("/api/discover", "Discovery and URL Analysis"),
    ("/api/schema", "Discovery and URL Analysis"),
    ("/api/url", "Discovery and URL Analysis"),
    ("/api/scraper", "Scraper/Telemetry Routes"),
    ("/api/operator", "Operator and System Routes"),
    ("/api/system", "Operator and System Routes"),
    ("/api/exports", "Export Routes"),
    ("/api/diagnostics", "Diagnostics Routes"),
]


def _section_for(path: str) -> str:
    for prefix, section in _PREFIX_TO_SECTION:
        if path == prefix or path.startswith(prefix + "/"):
            return section
    return "Other"


def _format_inventory(routes, header: str) -> str:
    by_section = {}
    for method, path in routes:
        section = _section_for(path)
        by_section.setdefault(section, []).append((method, path))
    out = [header.rstrip(), ""]
    section_order = list(dict.fromkeys(s for _, s in _PREFIX_TO_SECTION))
    for section in section_order:
        rows = by_section.pop(section, [])
        if not rows:
            continue
        out.append("## " + section)
        out.append("")
        out.append("| Method | Path |")
        out.append("| --- | --- |")
        for method, path in rows:
            out.append("| " + method + " | `" + path + "` |")
        out.append("")
    if by_section.get("Other"):
        out.append("## Other")
        out.append("")
        out.append("| Method | Path |")
        out.append("| --- | --- |")
        for method, path in by_section["Other"]:
            out.append("| " + method + " | `" + path + "` |")
        out.append("")
    out.append("**Total routes:** " + str(len(routes)))
    out.append("")
    return "\n".join(out)


def _format_diff(diff, header: str) -> str:
    if not diff:
        out = [header.rstrip(), "", "_No experimental routes are currently mounted._", ""]
    else:
        out = [header.rstrip(), "", "| Method | Path |", "| --- | --- |"]
        for method, path in diff:
            out.append("| " + method + " | `" + path + "` |")
        out.append("")
        out.append("**Experimental-only routes:** " + str(len(diff)))
        out.append("")
    return "\n".join(out)


def generate():
    timestamp = datetime.datetime.now(tz=datetime.UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    stable = _live_routes(experimental=False)
    full = _live_routes(experimental=True)
    diff = sorted(set(full) - set(stable))
    stable_md = _format_inventory(stable, STABLE_HEADER_TMPL.format(timestamp=timestamp))
    exp_md = _format_inventory(full, EXPERIMENTAL_HEADER_TMPL.format(timestamp=timestamp))
    diff_md = _format_diff(diff, DIFF_HEADER_TMPL.format(timestamp=timestamp))
    return stable_md, exp_md, diff_md, len(stable), len(full), len(diff)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate stable vs experimental route inventories")
    parser.add_argument("--stable-out", type=Path, default=REPO / "docs" / "API_STABLE.md")
    parser.add_argument("--experimental-out", type=Path, default=REPO / "docs" / "API_EXPERIMENTAL.md")
    parser.add_argument("--diff-out", type=Path, default=REPO / "docs" / "API_EXPERIMENTAL_DIFF.md")
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write the generated files to disk. Without this flag the script is side-effect free.",
    )
    args = parser.parse_args()

    stable_md, exp_md, diff_md, n_stable, n_full, n_diff = generate()

    if args.write:
        args.stable_out.write_text(stable_md, encoding="utf-8")
        args.experimental_out.write_text(exp_md, encoding="utf-8")
        args.diff_out.write_text(diff_md, encoding="utf-8")
        print("wrote " + str(args.stable_out.relative_to(REPO)))
        print("wrote " + str(args.experimental_out.relative_to(REPO)))
        print("wrote " + str(args.diff_out.relative_to(REPO)))
    else:
        sys.stdout.write(stable_md)
        sys.stdout.write("\n")
        sys.stdout.write(exp_md)
        sys.stdout.write("\n")
        sys.stdout.write(diff_md)
    print(
        f"stable={n_stable} experimental={n_full} diff={n_diff}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

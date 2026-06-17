#!/usr/bin/env python3
"""Generate the OpenAPI spec from the live FastAPI app.

The route inventory (``scripts/generate_route_inventory.py``) gives a
flat table of (method, path, module, handler) tuples. The OpenAPI
spec is the richer document that powers SDK generation, contract
testing, and inter-service type-safety. This script runs the app in
a subprocess (so the auth/router import side effects don't leak into
the parent test session) and writes the spec to:

* ``artifacts/audit/openapi.json``  — machine-readable, one spec
  per ``DATAFORGE_ENABLE_EXPERIMENTAL_ROUTES`` value.
* ``docs/openapi.json``  — for serving from the docs site.

Usage:
    python3 scripts/generate_openapi.py [--output PATH] [--experimental]

Notes
-----
* The spec is generated with ``DATAFORGE_ENV=development`` so /docs
  and /openapi.json are exposed by the app config.
* When ``--experimental`` is set, the spec also includes routes
  guarded by ``DATAFORGE_ENABLE_EXPERIMENTAL_ROUTES=true``.
* Two specs are produced so SDK consumers can pin against the
  stable contract while operators can audit the experimental
  surface separately.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
BACKEND = REPO / "backend"
DEFAULT_OUT_DIR = REPO / "artifacts" / "audit"
DOCS_OUT_DIR = REPO / "docs"


def _run_subprocess(enable_experimental: bool) -> dict[str, Any]:
    """Bootstrap the app in a clean interpreter and dump its OpenAPI schema."""
    env_value = "true" if enable_experimental else "false"
    script = (
        "import json,sys;"
        "os=__import__('os');"
        "os.environ['DATAFORGE_DOTENV_PATH']='/dev/null';"
        "os.environ['DATAFORGE_ENV']='development';"
        "os.environ['DATAFORGE_STORAGE_BACKEND']='sqlite';"
        f"os.environ['DATAFORGE_ENABLE_EXPERIMENTAL_ROUTES']='{env_value}';"
        "from app.main import app;"
        "sys.stdout.write(json.dumps(app.openapi(), indent=2, sort_keys=True));"
    )
    env = os.environ.copy()
    env["DATAFORGE_DOTENV_PATH"] = "/dev/null"
    env["DATAFORGE_ENV"] = "development"
    env["DATAFORGE_STORAGE_BACKEND"] = "sqlite"
    env["DATAFORGE_ENABLE_EXPERIMENTAL_ROUTES"] = env_value
    env["DATAFORGE_API_KEY"] = ""
    env["DATAFORGE_OPERATOR_API_KEY"] = ""
    env["DATAFORGE_ADMIN_API_KEY"] = ""
    # Test-only session secret; not a real credential.
    env["DATAFORGE_SESSION_SECRET"] = "openapi-gen-test-secret"  # noqa: S105
    env["DATAFORGE_ALLOW_INSECURE_DEV_AUTH"] = "true"
    env["DATAFORGE_SKIP_DB_CHECK"] = "true"
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(BACKEND),
        timeout=60,
    )
    if result.returncode != 0:
        msg = (
            f"openapi generation failed (rc={result.returncode}):\n"
            f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
        )
        raise RuntimeError(
            msg,
        )
    return json.loads(result.stdout)


def _summarize(spec: dict[str, Any]) -> dict[str, int]:
    paths = spec.get("paths") or {}
    by_method: dict[str, int] = {}
    for ops in paths.values():
        for method in ops:
            if method.lower() in {"get", "post", "put", "patch", "delete", "head", "options"}:
                by_method[method.upper()] = by_method.get(method.upper(), 0) + 1
    return {
        "path_count": len(paths),
        "operation_count": sum(by_method.values()),
        **by_method,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate OpenAPI spec from the live FastAPI app.")
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUT_DIR,
        help="Directory to write the spec into (default: artifacts/audit)",
    )
    parser.add_argument(
        "--experimental",
        action="store_true",
        help="Also generate a spec with experimental routes enabled.",
    )
    parser.add_argument(
        "--no-docs-copy",
        action="store_true",
        help="Skip copying the stable spec to docs/openapi.json.",
    )
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)

    stable = _run_subprocess(enable_experimental=False)
    stable_path = args.output / "openapi.json"
    stable_path.write_text(json.dumps(stable, indent=2, sort_keys=True))
    if not args.no_docs_copy:
        DOCS_OUT_DIR.mkdir(parents=True, exist_ok=True)
        (DOCS_OUT_DIR / "openapi.json").write_text(json.dumps(stable, indent=2, sort_keys=True))

    summary = _summarize(stable)
    print(f"Wrote {stable_path}")
    print(f"  path_count={summary['path_count']}  operation_count={summary['operation_count']}")
    for method in ("GET", "POST", "PUT", "PATCH", "DELETE"):
        if method in summary:
            print(f"  {method}={summary[method]}")
    if not args.no_docs_copy:
        print(f"Also wrote {DOCS_OUT_DIR / 'openapi.json'}")

    if args.experimental:
        experimental = _run_subprocess(enable_experimental=True)
        experimental_path = args.output / "openapi.experimental.json"
        experimental_path.write_text(json.dumps(experimental, indent=2, sort_keys=True))
        es = _summarize(experimental)
        diff_ops = es["operation_count"] - summary["operation_count"]
        print(f"Wrote {experimental_path}")
        print(
            f"  path_count={es['path_count']}  operation_count={es['operation_count']}  (+{diff_ops} vs stable)",
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

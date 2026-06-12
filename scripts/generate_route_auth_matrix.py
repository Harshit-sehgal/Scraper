#!/usr/bin/env python3
"""Generate route auth, middleware, tenant-scope, and test-coverage matrix."""

from __future__ import annotations

import json
import re

from generate_route_inventory import REPO, collect_route_rows

DOC_OUT = REPO / "docs" / "ROUTE_AUTH_MATRIX.md"
JSON_OUT = REPO / "artifacts" / "audit" / "ROUTE_AUTH_MATRIX.json"
TEST_ROOT = REPO / "backend" / "tests"


def _test_corpus() -> str:
    parts: list[str] = []
    for path in sorted(TEST_ROOT.rglob("test_*.py")):
        try:
            parts.append(path.read_text(encoding="utf-8"))
        except UnicodeDecodeError:
            continue
    return "\n".join(parts)


def _coverage_for(path: str, corpus: str) -> str:
    if not path.startswith("/api/"):
        return "unknown"
    if path in corpus:
        return "yes"
    literal_prefix = re.sub(r"/\\{[^}]+\\}.*", "", path)
    if literal_prefix and literal_prefix != path and literal_prefix in corpus:
        return "yes"
    family = "/" + "/".join(path.strip("/").split("/")[:2])
    if family and family in corpus:
        return "yes"
    return "unknown"


def _auth_status(row: dict[str, str]) -> str:
    access = row["public_or_protected"]
    if access.startswith("public"):
        return "public"
    if access == "protected":
        return "protected"
    return "unknown"


def build_matrix() -> list[dict[str, str]]:
    corpus = _test_corpus()
    rows: list[dict[str, str]] = []
    for row in collect_route_rows():
        if not row["path"].startswith("/api/"):
            continue
        coverage = _coverage_for(row["path"], corpus)
        notes = row["notes"]
        if row["tenant_scoped"] == "unknown":
            notes = (notes + " " if notes else "") + "Tenant scope unknown; candidate follow-up required."
        rows.append(
            {
                "method": row["method"],
                "path": row["path"],
                "public_protected_unknown": _auth_status(row),
                "required_role": row["required_role_if_known"] or "none",
                "route_dependency": row["auth_dependency_if_known"] or "none",
                "middleware_protected": row["middleware_protected"],
                "tenant_scoped": row["tenant_scoped"],
                "test_coverage": coverage,
                "stable_or_experimental": row["stable_or_experimental"],
                "notes": notes,
            },
        )
    return sorted(rows, key=lambda item: (item["path"], item["method"]))


def render_markdown(rows: list[dict[str, str]]) -> str:
    unknown_auth = [row for row in rows if row["public_protected_unknown"] == "unknown"]
    unknown_tenant = [row for row in rows if row["tenant_scoped"] == "unknown"]
    lines = [
        "# Route Auth Matrix",
        "",
        "**Generated from the registered FastAPI app. Do not edit generated rows by hand.**",
        "",
        "**Command:** `python3 scripts/generate_route_auth_matrix.py`",
        "",
        f"**API route rows:** {len(rows)}",
        f"**Unknown auth rows:** {len(unknown_auth)}",
        f"**Unknown tenant-scope rows:** {len(unknown_tenant)}",
        "",
        "Unknown auth or tenant-scope rows must be tracked as candidate issues.",
        "",
        "| Method | Path | Public/Protected | Required Role | Route Dependency | Middleware Protected | Tenant Scoped | Test Coverage | Boundary | Notes |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            "| `{method}` | `{path}` | {public_protected_unknown} | {required_role} | {route_dependency} | "
            "{middleware_protected} | {tenant_scoped} | {test_coverage} | {stable_or_experimental} | {notes} |".format(**row),
        )
    lines.append("")
    return "\n".join(lines)


def write_outputs(rows: list[dict[str, str]]) -> None:
    unknown_auth = [row for row in rows if row["public_protected_unknown"] == "unknown"]
    unknown_tenant = [row for row in rows if row["tenant_scoped"] == "unknown"]
    DOC_OUT.write_text(render_markdown(rows), encoding="utf-8")
    JSON_OUT.parent.mkdir(parents=True, exist_ok=True)
    JSON_OUT.write_text(
        json.dumps(
            {
                "route_count": len(rows),
                "unknown_auth_count": len(unknown_auth),
                "unknown_tenant_scope_count": len(unknown_tenant),
                "unknown_auth_routes": unknown_auth,
                "unknown_tenant_scope_routes": unknown_tenant,
                "routes": rows,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> int:
    rows = build_matrix()
    write_outputs(rows)
    unknown_auth = sum(1 for row in rows if row["public_protected_unknown"] == "unknown")
    unknown_tenant = sum(1 for row in rows if row["tenant_scoped"] == "unknown")
    print(f"wrote {DOC_OUT.relative_to(REPO)}")
    print(f"wrote {JSON_OUT.relative_to(REPO)}")
    print(f"routes={len(rows)} unknown_auth={unknown_auth} unknown_tenant={unknown_tenant}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

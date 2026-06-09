#!/usr/bin/env python3
"""Generate the DataForge FastAPI route authorization matrix.

The matrix is derived from the registered FastAPI app, not from docs.
It classifies route-level `require_role(...)` dependencies where present and
falls back to the global `/api/*` API-key middleware behavior for unguarded API
routes.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


@dataclass(frozen=True)
class RouteAuthRow:
    method: str
    path: str
    access: str
    enforcement: str
    notes: str


def _route_methods(route: Any) -> list[str]:
    methods = sorted(getattr(route, "methods", []) or [])
    return [method for method in methods if method not in {"HEAD", "OPTIONS"}]


def _dependency_roles(route: Any) -> list[str]:
    roles: list[str] = []
    dependencies = getattr(getattr(route, "dependant", None), "dependencies", []) or []
    for dependency in dependencies:
        call = getattr(dependency, "call", None)
        closure = getattr(call, "__closure__", None) or []
        for cell in closure:
            try:
                value = cell.cell_contents
            except ValueError:
                continue
            if isinstance(value, list) and value:
                role_values = []
                for role in value:
                    role_value = getattr(role, "value", None)
                    if role_value in {"admin", "operator", "viewer"}:
                        role_values.append(role_value)
                if role_values:
                    roles.extend(role_values)
    return sorted(set(roles))


def _classify_route(path: str, method: str, roles: list[str]) -> tuple[str, str, str]:
    from app.config import settings as _cfg

    is_prod = _cfg.ENV.lower() == "production"

    if path == "/metrics":
        has_token = bool(_cfg.METRICS_TOKEN)
        if is_prod and has_token:
            notes = "Protected by DATAFORGE_METRICS_TOKEN in production."
        elif is_prod and not has_token:
            notes = "WARNING: public in production! Set DATAFORGE_METRICS_TOKEN."
        else:
            notes = "Metrics token check active in production only."
        return ("metrics-token-if-configured", "settings.METRICS_TOKEN check in endpoint", notes)

    if path in {"/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"}:
        if is_prod:
            notes = "DANGER: should be disabled or blocked via reverse proxy in production."
        else:
            notes = "Development-only route; must be disabled in production."
        return ("development-docs", "FastAPI docs route plus production settings/proxy", notes)

    if roles == ["admin"]:
        notes = ""
        if path == "/api/system/merge/knowledge":
            notes = "Also calls legacy X-Admin-Key check when ADMIN_API_KEY is configured."
        return ("admin", "require_role([admin])", notes)

    if "admin" in roles and "operator" in roles:
        return ("operator-or-admin", "require_role([admin, operator])", "")

    if "operator" in roles:
        return ("operator", "require_role([operator])", "")

    # Endpoints explicitly exempt from API-key middleware (browsers or
    # self-service auth cannot carry API keys).
    if path == "/api/system/csp-violations":
        return ("public", "exempt from API-key middleware", "Browser-generated CSP report; no API key possible.")

    if path in {"/api/session", "/api/session/me"}:
        return ("public", "exempt from API-key middleware", "Session self-service auth; separate cookie-based flow.")

    if path.startswith("/api/"):
        mutation_note = "Mutation route lacks explicit require_role guard." if method != "GET" else ""
        return ("authenticated-user", "global /api/* API-key middleware", mutation_note)

    return ("public", "no API route auth", "Dashboard/static/probe route; review before public exposure.")


def build_matrix() -> list[RouteAuthRow]:
    from app.main import app

    rows: list[RouteAuthRow] = []
    for route in app.routes:
        path = getattr(route, "path", "")
        roles = _dependency_roles(route)
        for method in _route_methods(route):
            access, enforcement, notes = _classify_route(path, method, roles)
            rows.append(
                RouteAuthRow(
                    method=method,
                    path=path,
                    access=access,
                    enforcement=enforcement,
                    notes=notes,
                ),
            )
    return sorted(rows, key=lambda row: (row.path, row.method))


def render_markdown(rows: list[RouteAuthRow]) -> str:
    lines = [
        "# Route Authorization Matrix",
        "",
        "Generated from the registered FastAPI app. This is route-registration evidence, not a penetration test.",
        "",
        "| Method | Path | Access | Enforcement | Notes |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(f"| `{row.method}` | `{row.path}` | {row.access} | {row.enforcement} | {row.notes} |")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate DataForge route authorization matrix.")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    args = parser.parse_args()

    rows = build_matrix()
    if args.format == "json":
        print(json.dumps([asdict(row) for row in rows], indent=2))
    else:
        print(render_markdown(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

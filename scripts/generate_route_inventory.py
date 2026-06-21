#!/usr/bin/env python3
"""Generate a rich route inventory from the live FastAPI app."""

from __future__ import annotations

import argparse
import datetime
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
BACKEND = REPO / "backend"
SCRIPTS = REPO / "scripts"
DOC_OUT = REPO / "docs" / "ROUTE_INVENTORY.md"
JSON_OUT = REPO / "artifacts" / "audit" / "ROUTE_INVENTORY.json"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from fastapi_route_iter import iter_app_routes

PUBLIC_API_EXEMPT = {
    "/api/session",
    "/api/session/me",
    "/api/system/csp-violations",
    "/api/saas/signup",
}
TENANT_SCOPED_PREFIXES = (
    "/api/jobs",
    "/api/recycle_bin",
    "/api/exports",
    "/api/workflows",
    "/api/workflow-drafts",
    "/api/auth-profiles",
    "/api/scheduled",
    "/api/user",
    "/api/saas/aup",
    "/api/saas/me",
    "/api/saas/orgs",
    "/api/saas/projects",
    "/api/saas/memberships",
    "/api/saas/email-verification",
    "/api/saas/invitations",
)
GLOBAL_OR_NOT_TENANT_PREFIXES = (
    "/api/session",
    "/api/system",
    "/api/operator",
    "/api/scraper",
    "/api/discover",
    "/api/schema",
    "/api/url",
    "/api/intelligence",
    "/api/saas/plan",
    "/api/saas/usage",
    "/api/saas/password-reset",
    "/api/billing/subscriptions",
    "/api/billing/webhook",
    "/api/billing/checkout",
    "/api/billing/stub-return",
)


def _env(*, experimental: bool) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "PYTHONPATH": str(BACKEND),
            "DATAFORGE_DOTENV_PATH": "/dev/null",
            "DATAFORGE_ENV": "test",
            "DATAFORGE_STORAGE_BACKEND": "sqlite",
            "DATAFORGE_API_KEY": "user-key",
            "DATAFORGE_OPERATOR_API_KEY": "operator-key",
            "DATAFORGE_ADMIN_API_KEY": "admin-key",
            "DATAFORGE_SESSION_SECRET": "test-session-secret-change-me",
            "DATAFORGE_ALLOW_INSECURE_DEV_AUTH": "false",
            "DATAFORGE_SKIP_DB_CHECK": "true",
            "DATAFORGE_ENABLE_EXPERIMENTAL_ROUTES": "true" if experimental else "false",
        },
    )
    return env


def _type_name(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    name = getattr(value, "__name__", None)
    if name:
        return str(name)
    return str(value).replace("|", "\\|")


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
            if isinstance(value, list):
                for role in value:
                    role_value = getattr(role, "value", None)
                    if role_value in {"admin", "operator", "user", "viewer"}:
                        roles.append(role_value)
    return sorted(set(roles))


def _dependency_summary(route: Any) -> str:
    labels: list[str] = []
    dependencies = getattr(getattr(route, "dependant", None), "dependencies", []) or []
    for dependency in dependencies:
        call = getattr(dependency, "call", None)
        if call is None:
            continue
        qualname = getattr(call, "__qualname__", getattr(call, "__name__", "dependency"))
        if "require_principal" in qualname:
            labels.append("require_principal")
        elif "require_role_with_user" in qualname:
            labels.append("require_role_with_user")
        elif "require_role" in qualname:
            labels.append("require_role")
        else:
            labels.append(qualname)
    return ", ".join(sorted(set(labels)))


def _access_for(path: str, method: str, roles: list[str]) -> tuple[str, str, str]:
    if path == "/metrics":
        return ("protected", "metrics-token-if-configured", "settings.METRICS_TOKEN check in endpoint")
    if path in {"/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"}:
        return ("public-dev-only", "development-docs", "FastAPI docs disabled by app config in production")
    if path in {"/", "/health", "/ready"} or path.startswith("/app"):
        return ("public", "", "non-API probe/static route")
    if path in PUBLIC_API_EXEMPT:
        return ("public", "", "explicit API middleware exemption")
    if roles == ["admin"]:
        return ("protected", "admin", "require_role/admin-only dependency")
    if "admin" in roles and "operator" in roles and "user" in roles:
        return ("protected", "authenticated-user", "route dependency accepts admin/operator/user")
    if "admin" in roles and "operator" in roles:
        return ("protected", "operator-or-admin", "route dependency accepts admin/operator")
    if "operator" in roles:
        return ("protected", "operator", "route dependency accepts operator")
    if path.startswith("/api/"):
        note = "protected by global /api middleware; no route-level role dependency"
        if method != "GET":
            note += "; mutation role should be reviewed"
        return ("protected", "authenticated-user", note)
    return ("public", "", "non-API route")


def _middleware_protected(path: str) -> str:
    if not path.startswith("/api/"):
        return "no"
    return "no" if path in PUBLIC_API_EXEMPT else "yes"


def tenant_scope_for(path: str) -> str:
    if not path.startswith("/api/"):
        return "no"
    if path == "/api/saas/signup":
        return "no"
    if path.startswith(TENANT_SCOPED_PREFIXES):
        return "yes"
    if path.startswith(GLOBAL_OR_NOT_TENANT_PREFIXES):
        return "no"
    return "unknown"


def _category(path: str, stable_or_experimental: str) -> str:
    if stable_or_experimental == "experimental":
        return "experimental API routes"
    if path in {"/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"}:
        return "docs/openapi/static/dev routes"
    if path in {"/", "/health", "/ready", "/metrics"} or path.startswith("/app"):
        return "health/readiness routes"
    if path.startswith(("/api/session", "/api/saas/signup")):
        return "session/auth routes"
    if path.startswith("/api/"):
        return "stable API routes"
    return "docs/openapi/static/dev routes"


def _request_model(route: Any) -> str:
    body_field = getattr(route, "body_field", None)
    if body_field is None:
        return ""
    return _type_name(getattr(body_field, "type_", None) or getattr(body_field, "annotation", None))


def _response_model(route: Any) -> str:
    response_model = getattr(route, "response_model", None)
    if response_model is not None:
        return _type_name(response_model)
    response_field = getattr(route, "response_field", None)
    return _type_name(getattr(response_field, "type_", None)) if response_field is not None else ""


def _collect_current_app_rows(
    *,
    stable_paths: set[tuple[str, str]],
    experimental_paths: set[tuple[str, str]],
) -> list[dict[str, str]]:
    from app.main import create_app

    app = create_app()

    rows: list[dict[str, str]] = []
    for route in iter_app_routes(app):
        path = getattr(route, "path", "")
        methods = sorted(getattr(route, "methods", []) or [])
        endpoint = getattr(route, "endpoint", None)
        endpoint_module = getattr(endpoint, "__module__", route.__class__.__module__)
        endpoint_name = getattr(endpoint, "__name__", route.__class__.__name__)
        if not methods:
            rows.append(
                {
                    "method": "MOUNT",
                    "path": path,
                    "router_module": endpoint_module,
                    "handler_function": endpoint_name,
                    "stable_or_experimental": "stable",
                    "category": _category(path, "stable"),
                    "public_or_protected": "public",
                    "required_role_if_known": "",
                    "auth_dependency_if_known": "",
                    "middleware_protected": "no",
                    "tenant_scoped": "no",
                    "request_model_if_known": "",
                    "response_model_if_known": "",
                    "notes": "mounted ASGI/static route",
                },
            )
            continue
        for method in methods:
            if method in {"HEAD", "OPTIONS"}:
                continue
            key = (method, path)
            stable_or_experimental = (
                "stable" if key in stable_paths else "experimental" if key in experimental_paths else "unknown"
            )
            roles = _dependency_roles(route)
            access, required_role, note = _access_for(path, method, roles)
            rows.append(
                {
                    "method": method,
                    "path": path,
                    "router_module": endpoint_module,
                    "handler_function": endpoint_name,
                    "stable_or_experimental": stable_or_experimental,
                    "category": _category(path, stable_or_experimental),
                    "public_or_protected": access,
                    "required_role_if_known": required_role,
                    "auth_dependency_if_known": _dependency_summary(route),
                    "middleware_protected": _middleware_protected(path),
                    "tenant_scoped": tenant_scope_for(path),
                    "request_model_if_known": _request_model(route),
                    "response_model_if_known": _response_model(route),
                    "notes": note,
                },
            )
    return sorted(rows, key=lambda row: (row["path"], row["method"]))


def _current_rows_json() -> int:
    # In dump mode the caller passes the stable/full sets in environment.
    stable_paths = {tuple(item) for item in json.loads(os.environ["DATAFORGE_ROUTE_STABLE_SET"])}
    experimental_paths = {tuple(item) for item in json.loads(os.environ["DATAFORGE_ROUTE_EXPERIMENTAL_SET"])}
    print(json.dumps(_collect_current_app_rows(stable_paths=stable_paths, experimental_paths=experimental_paths), indent=2))
    return 0


def _raw_method_paths(*, experimental: bool) -> list[tuple[str, str]]:
    code = (
        "import sys, json;"
        "sys.path.insert(0, 'scripts');"
        "from fastapi_route_iter import iter_app_routes;"
        "from app.main import create_app;"
        "app=create_app();"
        "out=[];"
        "[out.append([m.upper(), r.path]) for r in iter_app_routes(app) "
        "if hasattr(r, 'methods') for m in (r.methods or []) "
        "if m.upper() not in {'HEAD','OPTIONS'}];"
        "print(json.dumps(sorted(out)))"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(REPO),
        env=_env(experimental=experimental),
        text=True,
        capture_output=True,
        check=False,
        timeout=60,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr)
    return [tuple(item) for item in json.loads(proc.stdout)]


def collect_route_rows() -> list[dict[str, str]]:
    stable = _raw_method_paths(experimental=False)
    full = _raw_method_paths(experimental=True)
    env = _env(experimental=True)
    env["DATAFORGE_ROUTE_STABLE_SET"] = json.dumps(stable)
    env["DATAFORGE_ROUTE_EXPERIMENTAL_SET"] = json.dumps(full)
    proc = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--dump-json"],
        cwd=str(REPO),
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=60,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr)
    return json.loads(proc.stdout)


def render_markdown(rows: list[dict[str, str]]) -> str:
    timestamp = datetime.datetime.now(tz=datetime.UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines = [
        "# Route Inventory",
        "",
        "**Generated from the registered FastAPI app. Do not edit generated rows by hand.**",
        "",
        f"**Generated:** {timestamp}",
        "**Command:** `python3 scripts/generate_route_inventory.py`",
        "",
        "This inventory distinguishes stable API routes, experimental API routes,",
        "development docs/static routes, health/readiness routes, and session/auth routes.",
        "",
        f"**Total route rows:** {len(rows)}",
        "",
    ]
    categories = [
        "stable API routes",
        "experimental API routes",
        "session/auth routes",
        "health/readiness routes",
        "docs/openapi/static/dev routes",
    ]
    for category in categories:
        category_rows = [row for row in rows if row["category"] == category]
        if not category_rows:
            continue
        lines.extend(
            [
                f"## {category.title()}",
                "",
                "| Method | Path | Module | Handler | Boundary | Access | Role | Dependency | Request Model | Response Model | Notes |",
                "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
            ],
        )
        for row in category_rows:
            lines.append(
                "| `{method}` | `{path}` | `{router_module}` | `{handler_function}` | {stable_or_experimental} | "
                "{public_or_protected} | {required_role_if_known} | {auth_dependency_if_known} | "
                "{request_model_if_known} | {response_model_if_known} | {notes} |".format(**row),
            )
        lines.append("")
    return "\n".join(lines)


def write_outputs(rows: list[dict[str, str]]) -> None:
    DOC_OUT.write_text(render_markdown(rows), encoding="utf-8")
    JSON_OUT.parent.mkdir(parents=True, exist_ok=True)
    JSON_OUT.write_text(json.dumps({"route_count": len(rows), "routes": rows}, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate DataForge route inventory docs and JSON.")
    parser.add_argument("--dump-json", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.dump_json:
        return _current_rows_json()
    rows = collect_route_rows()
    write_outputs(rows)
    stable = sum(1 for row in rows if row["stable_or_experimental"] == "stable")
    experimental = sum(1 for row in rows if row["stable_or_experimental"] == "experimental")
    print(f"wrote {DOC_OUT.relative_to(REPO)}")
    print(f"wrote {JSON_OUT.relative_to(REPO)}")
    print(f"routes={len(rows)} stable={stable} experimental={experimental}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

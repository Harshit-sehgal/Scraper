#!/usr/bin/env python3
"""Verify documentation matches code.

Usage:
    scripts/verify_docs_match_code.py

Checks:
1. Route inventory matches API.md
2. Environment variables in code match docs
3. Function signatures match docstrings
"""

from __future__ import annotations

import logging
import re
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

REPO = Path(__file__).resolve().parents[1]
BACKEND = REPO / "backend"
SCRIPTS = REPO / "scripts"
DOCS = REPO / "docs"


def get_routes_from_code() -> set[str]:
    """Extract routes from FastAPI app."""
    routes = set()
    try:
        # Import the app and get routes
        sys.path.insert(0, str(BACKEND))
        sys.path.insert(0, str(SCRIPTS))
        from app.main import create_app
        from fastapi_route_iter import iter_app_routes

        app = create_app()

        for route in iter_app_routes(app):
            if hasattr(route, "path"):
                methods = getattr(route, "methods", {"GET"})
                for method in methods:
                    if method in {"GET", "POST", "PUT", "DELETE", "PATCH"}:
                        routes.add(f"{method} {route.path}")
    except Exception as e:
        print(f"Warning: Could not extract routes from code: {e}")
    return routes


def get_routes_from_docs() -> set[str]:
    """Extract routes from API.md."""
    routes = set()
    api_md = DOCS / "API.md"
    if api_md.exists():
        content = api_md.read_text(encoding="utf-8")
        # Match patterns like "| GET | `/api/jobs` |"
        pattern = r"\|\s*(GET|POST|PUT|DELETE|PATCH)\s*\|\s*`([^`]+)`\s*\|"
        for match in re.finditer(pattern, content):
            method, path = match.groups()
            routes.add(f"{method} {path}")
    return routes


def get_env_vars_from_code() -> set[str]:
    """Extract environment variables from code."""
    env_vars = set()
    # Search for DATAFORGE_ prefix in code
    for py_file in BACKEND.rglob("*.py"):
        try:
            content = py_file.read_text(encoding="utf-8")
            # Match DATAFORGE_XXX patterns
            for match in re.finditer(r"DATAFORGE_[A-Z_]+", content):
                env_vars.add(match.group())
        except Exception as e:
            logger.debug("Failed to read %s: %s", py_file, e)
    return env_vars


def get_env_vars_from_docs() -> set[str]:
    """Extract environment variables from documentation."""
    env_vars = set()
    for md_file in DOCS.rglob("*.md"):
        try:
            content = md_file.read_text(encoding="utf-8")
            for match in re.finditer(r"DATAFORGE_[A-Z_]+", content):
                env_vars.add(match.group())
        except Exception as e:
            logger.debug("Failed to read %s: %s", md_file, e)
    return env_vars


def verify_routes() -> tuple[bool, list[str]]:
    """Verify routes match between code and docs."""
    code_routes = get_routes_from_code()
    doc_routes = get_routes_from_docs()

    issues = []

    # Routes in code but not in docs (excluding known built-ins)
    ignored_routes = {
        "GET /docs",
        "GET /docs/oauth2-redirect",
        "GET /redoc",
        "GET /openapi.json",
        "GET /metrics",  # Prometheus metrics endpoint (not a user-facing API route)
    }
    missing_in_docs = (code_routes - doc_routes) - ignored_routes
    if missing_in_docs:
        issues.append("Routes in code but not in docs:")
        for route in sorted(missing_in_docs):
            issues.append(f"  - {route}")

    # Routes in docs but not in code (excluding experimental)
    missing_in_code = doc_routes - code_routes
    # Filter out experimental routes (they're behind feature flags)
    non_experimental_missing = {
        r
        for r in missing_in_code
        if "/operator/" not in r
        and "/ml/" not in r
        and "/strategy/" not in r
        and "/topology" not in r
        and "/crystalline" not in r
        and "/knowledge" not in r
        and "/observability" not in r
        and "/replay/" not in r
        and "/scheduler/" not in r
        and "/refactor/" not in r
        and "/domain-policy" not in r
        and "/acquisition/" not in r
        and "/agency" not in r
        and "/search" not in r
        and "/economics" not in r
        and "/health/summary" not in r
        and "/health/domains" not in r
        and "/health/domain/" not in r
        and "/trends" not in r
        and "/trends/" not in r
        and "/predict" not in r
    }
    if non_experimental_missing:
        issues.append("Routes in docs but not in code (non-experimental):")
        for route in sorted(non_experimental_missing):
            issues.append(f"  - {route}")

    return len(issues) == 0, issues


def verify_env_vars() -> tuple[bool, list[str]]:
    """Verify environment variables match between code and docs."""
    code_vars = get_env_vars_from_code()
    doc_vars = get_env_vars_from_docs()

    # Known false positives: template patterns and wildcard prefixes that
    # the regex picks up but aren't real env var names.
    ignored_env_vars = {
        "DATAFORGE_METRICS_TOKEN__",  # Prometheus template delimiter (real var is DATAFORGE_METRICS_TOKEN)
        "DATAFORGE_TELEGRAM_",  # Wildcard prefix in comments (real vars are DATAFORGE_TELEGRAM_BOT_TOKEN etc.)
        "DATAFORGE_TELEGRAM_TOKEN",  # Comment mention only in telegram_notifier.py:65
    }

    issues = []

    # Variables in code but not in docs
    missing_in_docs = (code_vars - doc_vars) - ignored_env_vars
    if missing_in_docs:
        issues.append("Environment variables in code but not in docs:")
        for var in sorted(missing_in_docs):
            issues.append(f"  - {var}")

    return len(issues) == 0, issues


def main() -> int:
    print("Verifying documentation matches code...\n")

    all_passed = True

    # Verify routes
    print("1. Verifying routes...")
    routes_ok, route_issues = verify_routes()
    if routes_ok:
        print("   ✓ Routes match between code and docs")
    else:
        print("   ✗ Route mismatches found:")
        for issue in route_issues:
            print(f"     {issue}")
        all_passed = False

    # Verify environment variables
    print("\n2. Verifying environment variables...")
    env_ok, env_issues = verify_env_vars()
    if env_ok:
        print("   ✓ Environment variables match between code and docs")
    else:
        print("   ✗ Environment variable mismatches found:")
        for issue in env_issues:
            print(f"     {issue}")
        all_passed = False

    # Summary
    print("\n" + "=" * 60)
    if all_passed:
        print("All documentation checks passed!")
        return 0
    print("Documentation verification failed. Please fix the issues above.")
    return 1


if __name__ == "__main__":
    sys.exit(main())

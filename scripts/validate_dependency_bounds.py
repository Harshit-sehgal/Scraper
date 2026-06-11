#!/usr/bin/env python3
"""Validate that ``pyproject.toml`` dependency bounds are sane.

Since the Option B migration, ``pyproject.toml`` is the single source of
truth for both production and dev dependencies (the legacy
``backend/requirements*.in`` / ``*.lock.txt`` files are gone).

Rules enforced:

1. Every dependency MUST have an upper bound (``<X.Y.Z`` or ``~=X.Y.Z``).
   Unbounded pins are a supply-chain risk.
2. Dev-only packages (pytest, ruff, mypy, bandit, etc.) MUST live in
   ``[project.optional-dependencies].dev`` and MUST NOT appear in
   ``[project].dependencies``.
3. ``psycopg2-binary`` / ``psycopg[binary,pool]`` MUST both be present
   (the codebase supports both Postgres drivers).

Exit code:
    0 - all rules pass
    1 - one or more rules failed
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = REPO_ROOT / "pyproject.toml"

# Packages that are never acceptable in a production image.
DEV_ONLY_PACKAGES: set[str] = {
    "pytest",
    "pytest-cov",
    "pytest-asyncio",
    "pytest-timeout",
    "pytest-mock",
    "pytest-xdist",
    "pytest-rerunfailures",
    "testcontainers",
    "coverage",
    "pyflakes",
    "ruff",
    "mypy",
    "bandit",
    "pip-audit",
    "pip-tools",
}

# Patterns that indicate a pinned/unbounded dep (no upper bound is a risk).
_BOUND_REQUIRED = re.compile(r"[<>=~!]=?")


def _normalise_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name.lower())


def _parse_pyproject_deps(text: str, section: str) -> dict[str, str]:
    """Extract ``[section] = ["pkg>=..."]`` into a dict.

    The section may be ``project.dependencies`` (dotted) or just the
    single segment that the caller passed.
    """
    # Find the section header. ``tomllib`` is 3.11+, but the project is
    # 3.12+, so we can use it without a fallback.
    import tomllib

    data = tomllib.loads(text)
    if section == "project.dependencies":
        items = data.get("project", {}).get("dependencies", [])
    elif section == "project.optional-dependencies.dev":
        items = data.get("project", {}).get("optional-dependencies", {}).get("dev", [])
    else:
        items = []
    out: dict[str, str] = {}
    for raw in items:
        # Strip extras like ``uvicorn[standard]`` and ``coverage[toml]``
        stripped = re.sub(r"\[[^\]]*\]", "", raw).strip()
        if not stripped:
            continue
        # Take the first whitespace-separated token (the name + spec).
        first = stripped.split()[0]
        # Normalise: drop any leading version operators that snuck in.
        name = re.split(r"[\s<>=~!]", first, maxsplit=1)[0]
        if not name:
            continue
        spec = stripped[len(name) :].strip()
        out[_normalise_name(name)] = spec
    return out


def main() -> int:
    if not PYPROJECT.exists():
        print(f"pyproject.toml not found at {PYPROJECT}")
        return 1

    text = PYPROJECT.read_text(encoding="utf-8")
    prod = _parse_pyproject_deps(text, "project.dependencies")
    dev = _parse_pyproject_deps(text, "project.optional-dependencies.dev")

    failures: list[str] = []

    # Rule 1: every prod dep must have an upper bound.
    unbounded: list[str] = []
    for name, spec in prod.items():
        if not _BOUND_REQUIRED.search(spec):
            unbounded.append(f"{name} ({spec or 'no spec'})")
    if unbounded:
        failures.append(
            "Production deps without an upper bound (supply-chain risk): " + ", ".join(unbounded),
        )

    # Rule 2: dev-only packages must not appear in prod deps.
    leaked = sorted(DEV_ONLY_PACKAGES & set(prod))
    if leaked:
        failures.append(
            "Production deps contain dev-only packages: "
            + ", ".join(leaked)
            + ". Move them to [project.optional-dependencies].dev.",
        )

    # Rule 3: both Postgres drivers must be present.
    has_psycopg2 = any("psycopg2" in n for n in prod)
    has_psycopg3 = any("psycopg" in n for n in prod)
    if not (has_psycopg2 and has_psycopg3):
        failures.append(
            "Both psycopg2-binary and psycopg[binary,pool] must be in prod deps "
            f"(found psycopg2={has_psycopg2}, psycopg3={has_psycopg3}).",
        )

    if failures:
        print("Dependency validation FAILED:")
        for f in failures:
            print(f"  - {f}")
        print()
        print("Fix pyproject.toml and re-run.")
        return 1

    print(
        f"Dependency validation OK: {len(prod)} prod packages, {len(dev)} dev packages.",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

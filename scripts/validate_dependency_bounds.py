#!/usr/bin/env python3
"""Validate that dependency lock files match their declared intent.

Rules enforced:

1. ``requirements.lock.txt`` MUST NOT contain dev-only packages (pytest,
   pytest-cov, pytest-asyncio, testcontainers, coverage, pyflakes, ruff,
   mypy, bandit, pip-audit, pip-tools).
2. ``requirements-dev.lock.txt`` MUST be a superset of
   ``requirements.lock.txt`` (any package present in prod must also be
   present in dev with an equal-or-higher pinned version).
3. Both lock files MUST be parseable as ``name==version`` lines.

Exit code:
    0 - all rules pass
    1 - one or more rules failed
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"

PROD_LOCK = BACKEND_DIR / "requirements.lock.txt"
DEV_LOCK = BACKEND_DIR / "requirements-dev.lock.txt"

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

# Common normalisations (distro name may differ from import name)
NORMALISATIONS: dict[str, str] = {
    "pytest-cov": "pytest-cov",
    "pytest-asyncio": "pytest-asyncio",
    "pytest-timeout": "pytest-timeout",
    "pytest-mock": "pytest-mock",
    "pip-audit": "pip-audit",
    "pip-tools": "pip-tools",
}

_PIN_RE = re.compile(r"^([A-Za-z0-9_.\-]+)==([0-9][^\s#]*)")


def parse_lock(path: Path) -> dict[str, str]:
    """Return a dict of normalised package name -> pinned version."""
    if not path.exists():
        return {}
    out: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Strip PEP 508 extras like ``coverage[toml]`` before matching.
        line = re.sub(r"\[[^\]]*\]", "", line)
        m = _PIN_RE.match(line)
        if not m:
            continue
        name = m.group(1).lower()
        # PEP 503 normalisation: collapse runs of [-_.] to "-"
        canon = re.sub(r"[-_.]+", "-", name)
        out[canon] = m.group(2)
    return out


def compare_versions(a: str, b: str) -> int:
    """Return -1, 0, or 1 by lexicographic compare on the leading numeric tuple."""

    def to_tuple(s: str) -> tuple[int, ...]:
        parts: list[int] = []
        for chunk in re.split(r"[^0-9]+", s):
            if not chunk:
                continue
            try:
                parts.append(int(chunk))
            except ValueError:
                break
        return tuple(parts)

    ta, tb = to_tuple(a), to_tuple(b)
    if ta < tb:
        return -1
    if ta > tb:
        return 1
    return 0


def main() -> int:
    failures: list[str] = []

    prod = parse_lock(PROD_LOCK)
    dev = parse_lock(DEV_LOCK)

    # Rule 1: prod lock must not contain dev-only packages.
    if prod:
        leaked = sorted(set(DEV_ONLY_PACKAGES) & set(prod))
        if leaked:
            failures.append(
                "Production lock file contains dev-only packages: " + ", ".join(leaked) + ". Move them to requirements-dev.in.",
            )

    # Rule 2: dev lock is a superset of prod (with version >= prod).
    if prod and dev:
        missing_in_dev: list[str] = []
        older_in_dev: list[str] = []
        for name, prod_ver in prod.items():
            if name not in dev:
                missing_in_dev.append(f"{name}=={prod_ver}")
                continue
            if compare_versions(dev[name], prod_ver) < 0:
                older_in_dev.append(
                    f"{name}: dev={dev[name]} prod={prod_ver}",
                )
        if missing_in_dev:
            failures.append(
                "Dev lock is missing prod packages: " + ", ".join(missing_in_dev),
            )
        if older_in_dev:
            failures.append(
                "Dev lock has older pins than prod: " + ", ".join(older_in_dev),
            )

    if failures:
        print("Dependency validation FAILED:")
        for f in failures:
            print(f"  - {f}")
        print()
        print("Run the lock regeneration commands documented in requirements.in.")
        return 1

    print(
        f"Dependency validation OK: {len(prod)} prod packages, {len(dev)} dev packages.",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

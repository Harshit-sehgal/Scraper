"""Sanity test for the dependency-file architecture.

The project's dependency intent is split across four files:

* ``backend/requirements.in``          — production intent (bounded ranges)
* ``backend/requirements.lock.txt``    — production lock (pinned)
* ``backend/requirements-dev.in``      — dev tooling intent (bounded ranges)
* ``backend/requirements-dev.lock.txt`` — dev lock (pinned)

The two legacy wrappers (``requirements.txt`` and ``requirements-dev.txt``)
MUST just be ``-r`` shims pointing at the lock files. The lock files MUST
not contain known dev-only packages. The dev lock MUST be a superset of
the prod lock. ``scripts/validate_dependency_bounds.py`` enforces this in
CI; this test pins the contract so a future refactor cannot silently
break it.
"""

from __future__ import annotations

import re
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROD_IN = BACKEND_DIR / "requirements.in"
PROD_LOCK = BACKEND_DIR / "requirements.lock.txt"
PROD_LEGACY = BACKEND_DIR / "requirements.txt"
DEV_IN = BACKEND_DIR / "requirements-dev.in"
DEV_LOCK = BACKEND_DIR / "requirements-dev.lock.txt"
DEV_LEGACY = BACKEND_DIR / "requirements-dev.txt"

DEV_ONLY_PACKAGES = {
    "pytest",
    "pytest-cov",
    "pytest-asyncio",
    "pytest-timeout",
    "pytest-mock",
    "testcontainers",
    "coverage",
    "pyflakes",
    "ruff",
    "mypy",
    "bandit",
    "pip-audit",
    "pip-tools",
}


def _is_wrapper(content: str) -> bool:
    """A wrapper file should be only comments and a single ``-r`` line."""
    meaningful = [line.strip() for line in content.splitlines() if line.strip() and not line.strip().startswith("#")]
    return len(meaningful) == 1 and meaningful[0].startswith("-r ")


def _parse_lock(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()  # noqa: PLW2901, RUF100
        # Strip PEP 508 extras like ``coverage[toml]`` before matching.
        normalised = re.sub(r"\[[^\]]*\]", "", line)
        m = re.match(r"^([A-Za-z0-9_.\-]+)==([0-9][^\s#]*)", normalised)
        if m:
            out[m.group(1).lower()] = m.group(2)
    return out


class TestIntentFiles:
    def test_prod_in_declares_pinned_ranges(self) -> None:
        content = PROD_IN.read_text()
        for pkg in ("fastapi", "uvicorn[standard]", "playwright", "httpx"):
            assert pkg in content, f"requirements.in missing {pkg}"

    def test_dev_in_extends_prod_in(self) -> None:
        content = DEV_IN.read_text()
        assert "-r requirements.in" in content, "requirements-dev.in must include prod intent"


class TestLockFiles:
    def test_prod_lock_no_dev_only_packages(self) -> None:
        prod = set(_parse_lock(PROD_LOCK))
        leaked = sorted(DEV_ONLY_PACKAGES & prod)
        assert not leaked, f"Prod lock leaked dev-only packages: {leaked}"

    def test_dev_lock_superset_of_prod(self) -> None:
        prod = _parse_lock(PROD_LOCK)
        dev = _parse_lock(DEV_LOCK)
        missing = sorted(set(prod) - set(dev))
        assert not missing, f"Dev lock missing prod packages: {missing}"

    def test_dev_lock_has_pins(self) -> None:
        dev = _parse_lock(DEV_LOCK)
        assert "pytest" in dev, "Dev lock must pin pytest"
        assert "pyflakes" in dev, "Dev lock must pin pyflakes"
        assert "coverage" in dev, "Dev lock must pin coverage"


class TestLegacyWrappers:
    def test_requirements_txt_is_wrapper(self) -> None:
        assert _is_wrapper(PROD_LEGACY.read_text()), "requirements.txt must be a -r wrapper pointing at requirements.lock.txt"
        assert "requirements.lock.txt" in PROD_LEGACY.read_text()

    def test_requirements_dev_txt_is_wrapper(self) -> None:
        assert _is_wrapper(DEV_LEGACY.read_text()), (
            "requirements-dev.txt must be a -r wrapper pointing at requirements-dev.lock.txt"
        )
        assert "requirements-dev.lock.txt" in DEV_LEGACY.read_text()

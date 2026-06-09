"""Characterization tests for the global pytest-timeout configuration.

The Phase 0 master plan requires:

    Step 4. Add global pytest timeout configuration and separate test
            markers.

The pytest-timeout package is already declared in ``pyproject.toml``'s
``[project.optional-dependencies].dev``. The characterization tests below
prove that pytest-timeout is *active* in the configured run (i.e. that
there is a global default) by reading the source of truth (``pyproject.toml``)
and by checking the plugin is loaded at pytest startup.

If these tests start failing after a config change, that change has
regressed Phase 0 step 4.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = REPO_ROOT / "pyproject.toml"


def _read_pyproject() -> str:
    return PYPROJECT.read_text(encoding="utf-8")


def test_pytest_timeout_is_a_dev_dependency() -> None:
    """``pytest-timeout`` must be declared in the dev extras."""
    text = _read_pyproject()
    match = re.search(r"pytest-timeout", text)
    assert match, "pytest-timeout is not declared in pyproject.toml dev deps"


def test_pytest_timeout_addopts_is_set() -> None:
    """``addopts`` must include ``--timeout=N``."""
    text = _read_pyproject()
    addopts_match = re.search(
        r'addopts\s*=\s*"([^"]*)"',
        text,
    )
    assert addopts_match, "no addopts entry in pyproject.toml [tool.pytest.ini_options]"
    addopts = addopts_match.group(1)
    assert "--timeout=" in addopts, (
        f"addopts is {addopts!r} but does not include --timeout=N; add a global pytest-timeout default to satisfy Phase 0 step 4"
    )


def test_pytest_timeout_plugin_is_loaded() -> None:
    """pytest-timeout's plugin is registered at pytest startup."""
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "--markers"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, f"pytest --markers failed: {proc.stderr}"
    assert "@pytest.mark.timeout" in proc.stdout, "pytest-timeout marker is not registered; plugin failed to load"


@pytest.mark.timeout(1)
def test_per_test_timeout_override_is_accepted() -> None:
    """The ``@pytest.mark.timeout(N)`` decorator must not crash collection."""
    assert True

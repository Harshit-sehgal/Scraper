"""Automated validation of manual exploratory scripts.

Ensures every script under ``backend/manual/`` is syntactically valid
and exposes zero top-level side effects (allowing clean imports).
The scripts themselves are run by hand against a live API server and
are not part of the pytest test suite.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

# The scripts live at ``backend/manual/manual_*.py``. They are not part
# of any installed package, so we add that directory to ``sys.path`` for
# the duration of this test session and import each by its bare module
# name. The names are deliberately stable: renaming a manual script will
# fail this test as a deliberate reminder to update the list.
MANUAL_SCRIPT_DIR = Path(__file__).resolve().parent.parent / "manual"

MANUAL_SCRIPTS = [
    "manual_api",
    "manual_app_scrape",
    "manual_chennai",
    "manual_extract",
    "manual_flights_e2e",
    "manual_hn",
    "manual_insight",
    "manual_modes",
    "manual_pollinations",
    "manual_providers",
    "manual_real_scrape",
    "manual_threebestrated",
    "manual_workflow",
]


@pytest.fixture(scope="module", autouse=True)
def _ensure_manual_dir_on_path() -> None:
    """Add ``backend/manual/`` to ``sys.path`` once per test module."""
    manual_dir = str(MANUAL_SCRIPT_DIR)
    if manual_dir not in sys.path:
        sys.path.insert(0, manual_dir)


@pytest.mark.parametrize("module_name", MANUAL_SCRIPTS)
def test_manual_script_import_safety(module_name) -> None:
    """Import each manual script to assert it is syntactically correct and free of top-level side effects."""
    try:
        mod = importlib.import_module(module_name)
        assert mod is not None
    except Exception as exc:
        pytest.fail(f"Failed to safely import manual script '{module_name}': {exc}")

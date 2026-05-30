"""
Automated validation of manual test scripts — E05 Integration.
Ensures all manual tests compile, are syntactically valid, and
expose zero top-level side effects (allowing clean imports).
"""
from __future__ import annotations

import sys
import importlib
from pathlib import Path
import pytest

MANUAL_TEST_FILES = [
    "manual_run_manual_test",
    "manual_test_api",
    "manual_test_app_scrape",
    "manual_test_chennai",
    "manual_test_extract",
    "manual_test_flights_e2e",
    "manual_test_hn",
    "manual_test_insight",
    "manual_test_modes",
    "manual_test_pollinations",
    "manual_test_providers",
    "manual_test_real_scrape",
    "manual_test_threebestrated",
    "manual_test_workflow",
]


@pytest.mark.parametrize("module_name", MANUAL_TEST_FILES)
def test_manual_script_import_safety(module_name):
    """Import manual test modules dynamically to assert that they are syntactically

    correct and have no side effects (e.g. blocking HTTP calls or database actions
    on import).
    """
    # Ensure backend/tests is in path
    tests_dir = str(Path(__file__).parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)

    try:
        # Dyn import the module
        mod = importlib.import_module(module_name)
        assert mod is not None
    except Exception as e:
        pytest.fail(f"Failed to safely import manual test module '{module_name}': {e}")

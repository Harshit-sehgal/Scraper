import os
import sys

# Inherit pytest options and hooks from backend/tests/conftest.py to ensure unified execution
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "tests")))

# The re-export below intentionally makes the parent ``conftest.py`` hooks
# visible to the benchmarks test tree. Some of those names are only
# referenced by pytest's plugin discovery, so ruff cannot see their use.
from conftest import (  # noqa: F401, RUF100
    pytest_addoption,
    pytest_collection_modifyitems,
    pytest_configure,
    pytest_runtest_logreport,
    pytest_sessionfinish,
    pytest_sessionstart,
    reset_failure_injection,
    reset_semantic_world_state,
)

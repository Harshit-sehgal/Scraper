import importlib
import os
import sys

# Inherit pytest options and hooks from backend/tests/conftest.py to ensure unified execution
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "tests")))

# Re-export the parent ``conftest.py`` hooks into the benchmark tree.
_parent_conftest = importlib.import_module("conftest")
pytest_addoption = _parent_conftest.pytest_addoption
pytest_collection_modifyitems = _parent_conftest.pytest_collection_modifyitems
pytest_configure = _parent_conftest.pytest_configure
pytest_runtest_logreport = _parent_conftest.pytest_runtest_logreport
pytest_sessionfinish = _parent_conftest.pytest_sessionfinish
pytest_sessionstart = _parent_conftest.pytest_sessionstart
reset_failure_injection = _parent_conftest.reset_failure_injection
reset_semantic_world_state = _parent_conftest.reset_semantic_world_state

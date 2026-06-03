"""
Tests for the research-shell quarantine in app/routers/scraper.py
and app/routers/operator.py.

These two routers historically top-level imported 5 research modules
between them:
  - app.trend_analyzer (both)
  - app.degradation_predictor (operator)
  - app.domain_health_alerts (operator)
  - app.visualization (operator)

All four are now imported lazily inside the endpoint functions that
use them. This file pins the contract.
"""

from __future__ import annotations

import importlib
import sys

import pytest

# Modules that must NOT be loaded after a clean import of the routers.
RESEARCH_MODULES_USED_BY_ROUTERS = (
    "app.trend_analyzer",
    "app.degradation_predictor",
    "app.domain_health_alerts",
    "app.visualization",
)


@pytest.fixture
def clean_router_imports():
    """Drop the routers and their transitive research deps from sys.modules.

    This is necessary because pytest, conftest.py, and earlier test
    files may have already imported these modules.
    """
    modules_to_drop = (
        "app.routers.scraper",
        "app.routers.operator",
        *RESEARCH_MODULES_USED_BY_ROUTERS,
    )
    for name in modules_to_drop:
        sys.modules.pop(name, None)
    yield
    for name in modules_to_drop:
        sys.modules.pop(name, None)


def test_scraper_router_does_not_load_research_modules(clean_router_imports):
    """Importing app.routers.scraper must not pull in any research module."""
    importlib.import_module("app.routers.scraper")

    loaded = [m for m in RESEARCH_MODULES_USED_BY_ROUTERS if m in sys.modules]
    assert loaded == [], (
        f"app.routers.scraper eagerly imported research modules: {loaded}. "
        f"All research imports must be lazy in endpoint function bodies."
    )


def test_operator_router_does_not_load_research_modules(clean_router_imports):
    """Importing app.routers.operator must not pull in any research module."""
    importlib.import_module("app.routers.operator")

    loaded = [m for m in RESEARCH_MODULES_USED_BY_ROUTERS if m in sys.modules]
    assert loaded == [], (
        f"app.routers.operator eagerly imported research modules: {loaded}. "
        f"All research imports must be lazy in endpoint function bodies."
    )


def test_both_routers_clean_together(clean_router_imports):
    """Importing both routers in sequence must keep research modules absent."""
    importlib.import_module("app.routers.operator")
    importlib.import_module("app.routers.scraper")

    loaded = [m for m in RESEARCH_MODULES_USED_BY_ROUTERS if m in sys.modules]
    assert loaded == [], f"Either or both router modules eagerly imported: {loaded}."


@pytest.mark.parametrize("research_module", RESEARCH_MODULES_USED_BY_ROUTERS)
def test_router_endpoint_imports_trigger_lazy_load(research_module, clean_router_imports):
    """Sanity check: the research modules themselves can be imported.

    This isn't a functional test of the endpoints (which need much
    more setup) — it just confirms that the research modules are
    importable in isolation and that the lazy-import contract doesn't
    break the underlying capability.
    """
    __import__(research_module)
    assert research_module in sys.modules

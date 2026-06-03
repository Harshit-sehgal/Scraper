"""Tests that importing app.html_utils does not pull in research modules."""

from __future__ import annotations

import importlib
import sys

import pytest

RESEARCH_MODULES = ("app.semantic_segmentation", "app.strategy_evolution")


@pytest.fixture(autouse=True)
def _clean():
    for m in RESEARCH_MODULES + ("app.html_utils",):
        sys.modules.pop(m, None)
    yield
    for m in RESEARCH_MODULES + ("app.html_utils",):
        sys.modules.pop(m, None)


def test_html_utils_import_does_not_load_research_modules() -> None:
    importlib.import_module("app.html_utils")

    loaded = [m for m in RESEARCH_MODULES if m in sys.modules]
    assert loaded == [], f"html_utils eagerly loaded: {loaded}"


def test_html_utils_import_after_main_still_clean() -> None:
    """Even when app.main is already loaded, html_utils import stays clean."""
    import os

    os.environ["DATAFORGE_ENABLE_EXPERIMENTAL_ROUTES"] = "false"
    from app.config import settings

    settings.ENABLE_EXPERIMENTAL_ROUTES = False

    for m in ("app.main", "app.html_utils"):
        sys.modules.pop(m, None)

    importlib.import_module("app.html_utils")
    importlib.import_module("app.main")

    loaded = [m for m in RESEARCH_MODULES if m in sys.modules]
    assert loaded == [], f"html_utils eagerly loaded after main: {loaded}"

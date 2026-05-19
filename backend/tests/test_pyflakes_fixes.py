"""
Verify there are no unresolved pyflakes warnings across the codebase.

This is a placeholder — actual pyflakes integration can be added later.
"""

import pytest


def test_all_modules_import_cleanly():
    """Test that all app modules can be imported without errors."""
    modules = [
        "app.config",
        "app.models",
        "app.scraper",
        "app.html_utils",
        "app.filters",
        "app.selector_engine",
        "app.cleaning_engine",
        "app.state_store",
        "app.anti_bot_engine",
        "app.proxy_manager",
        "app.strategy_evolution",
        "app.selector_ml_optimizer",
        "app.recovery_strategies",
        "app.scraper_recovery_integration",
        "app.extraction_provenance",
        "app.regression_capture",
    ]
    for module_name in modules:
        try:
            __import__(module_name)
        except ImportError as e:
            pytest.fail(f"{module_name} failed to import: {e}")

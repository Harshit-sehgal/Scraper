"""Tests for the experimental router mount gate in app/main.py.

The gate at configure_routes() must:
1. NOT include the experimental router when ENABLE_EXPERIMENTAL_ROUTES is False.
2. Include the experimental router when ENABLE_EXPERIMENTAL_ROUTES is True.
3. Log a warning when enabled in production environment.
4. Never import app.routers.experimental at module load time of app.main.

We test these by inspecting the routes attached to a freshly-created
FastAPI app, not by booting the full lifespan (which would require
Postgres, Playwright, etc).
"""

from __future__ import annotations

import sys


def _experimental_route_paths(app) -> set[str]:
    """Return the set of path patterns exposed by the experimental router."""
    paths: set[str] = set()
    for route in app.routes:
        # Each FastAPI route has a `.path` attribute. The experimental
        # router is mounted with the default prefix (no prefix), so
        # its paths are like "/api/system/topology".
        if hasattr(route, "path"):
            paths.add(route.path)
    return paths


def test_main_does_not_eagerly_import_experimental_router() -> None:
    """app.main must NOT have the experimental router in its import graph
    when ENABLE_EXPERIMENTAL_ROUTES is False. This keeps the default-mode
    startup free of research-module imports.
    """
    # Force the flag to False, then (re)import app.main.
    from app.config import settings

    settings.ENABLE_EXPERIMENTAL_ROUTES = False

    # Drop any cached import of the experimental router so we can detect
    # whether the new app.main import brought it in.
    sys.modules.pop("app.routers.experimental", None)

    # Now import app.main fresh.
    if "app.main" in sys.modules:
        # Reload via importlib so we re-execute module-level code.
        import importlib

        importlib.reload(sys.modules["app.main"])

    # The experimental router should not have been pulled in.
    assert "app.routers.experimental" not in sys.modules, (
        "app.main eagerly imported app.routers.experimental at module "
        "load time. This violates the import-time gate — the experimental "
        "router should only be imported inside configure_routes()."
    )


def test_experimental_routes_not_mounted_when_gate_off(monkeypatch) -> None:
    """With ENABLE_EXPERIMENTAL_ROUTES=False, no /api/system/* research
    paths should appear in the route table.
    """
    from app.config import settings

    monkeypatch.setattr(settings, "ENABLE_EXPERIMENTAL_ROUTES", False, raising=False)
    monkeypatch.setattr(settings, "ENV", "development", raising=False)

    from app.main import configure_routes
    from fastapi import FastAPI

    test_app = FastAPI()
    configure_routes(test_app)

    paths = _experimental_route_paths(test_app)
    # Pick a few well-known experimental paths.
    for experimental_path in (
        "/api/system/topology",
        "/api/system/crystalline",
        "/api/system/merge/knowledge",
    ):
        assert (
            experimental_path not in paths
        ), f"Experimental route {experimental_path} was mounted despite ENABLE_EXPERIMENTAL_ROUTES=False."


def test_experimental_routes_mounted_when_gate_on(monkeypatch) -> None:
    """With ENABLE_EXPERIMENTAL_ROUTES=True, the research paths MUST appear."""
    from app.config import settings

    monkeypatch.setattr(settings, "ENABLE_EXPERIMENTAL_ROUTES", True, raising=False)
    monkeypatch.setattr(settings, "ENV", "development", raising=False)

    from app.main import configure_routes
    from fastapi import FastAPI

    test_app = FastAPI()
    configure_routes(test_app)

    paths = _experimental_route_paths(test_app)
    # When enabled, at least one of the well-known paths should be present.
    assert "/api/system/topology" in paths, (
        "Experimental routes were not mounted despite "
        "ENABLE_EXPERIMENTAL_ROUTES=True. configure_routes() failed to "
        "include the experimental router."
    )


def test_production_warning_when_experimental_enabled_in_prod(monkeypatch, caplog) -> None:
    """When the gate is open AND env=production, a WARNING must be logged."""
    from app.config import settings

    monkeypatch.setattr(settings, "ENABLE_EXPERIMENTAL_ROUTES", True, raising=False)
    monkeypatch.setattr(settings, "ENV", "production", raising=False)

    from app.main import configure_routes
    from fastapi import FastAPI

    test_app = FastAPI()
    import logging

    with caplog.at_level(logging.WARNING, logger="app.main"):
        configure_routes(test_app)

    assert (
        "EXPERIMENTAL ROUTES ENABLED IN PRODUCTION" in caplog.text
    ), "Production-mode warning was not logged when experimental routes were enabled. This is a required safety signal."

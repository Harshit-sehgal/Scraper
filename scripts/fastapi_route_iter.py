"""Compatibility helpers for iterating FastAPI routes.

FastAPI 0.137 represents included routers as internal ``_IncludedRouter``
objects in ``app.routes``. Those wrappers do not expose ``path``/``methods``
directly; the real routes live under ``route.original_router.routes``.

Keep this helper tiny and dependency-free so route inventory scripts can use
it both in-process and from ``python -c`` subprocess dumps.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Any


def iter_fastapi_routes(routes: Iterable[Any]) -> Iterator[Any]:
    """Yield concrete route objects, flattening included-router wrappers."""

    for route in routes:
        original_router = getattr(route, "original_router", None)
        if original_router is not None:
            yield from iter_fastapi_routes(getattr(original_router, "routes", []) or [])
            continue
        yield route


def iter_app_routes(app: Any) -> Iterator[Any]:
    """Yield concrete route objects from a FastAPI application."""

    yield from iter_fastapi_routes(getattr(app, "routes", []) or [])

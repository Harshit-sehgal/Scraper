"""Compatibility helpers for iterating FastAPI routes.

FastAPI >= 0.137 represents included routers as internal ``_IncludedRouter``
objects in ``app.routes``. Those wrappers expose only ``original_router`` and do
not carry a flattened ``path``; the concrete routes live under
``original_router.routes``. Routes declared directly on a prefixed router keep
the prefix baked into ``path``, but routes pulled in through a nested
``include_router`` stay relative to the parent prefix. Older FastAPI versions
flatten everything into ``app.routes`` directly.

This helper walks both shapes and yields concrete routes whose ``path`` is the
fully qualified path (accumulated router prefixes applied exactly once).

Keep this helper tiny and dependency-free so route inventory scripts can use
it both in-process and from ``python -c`` subprocess dumps.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Any


def _concat(prefix: str, path: str) -> str:
    """Join a router prefix and a route path with a single separator."""
    if not prefix:
        return path
    if not path:
        return prefix
    return f"{prefix.rstrip('/')}/{path.lstrip('/')}"


def _qualify(prefix: str, path: str) -> str:
    """Apply ``prefix`` to ``path`` unless it is already present."""
    if not prefix:
        return path
    base = prefix.rstrip("/")
    if path == base or path.startswith(f"{base}/"):
        return path
    return _concat(prefix, path)


class _PrefixedRoute:
    """A concrete route whose ``path`` has accumulated router prefixes applied.

    Every other attribute is delegated to the wrapped route, so callers still
    see the real ``methods``, ``name``, ``dependencies``, ``endpoint``, etc.
    """

    __slots__ = ("_route", "path")

    def __init__(self, route: Any, path: str) -> None:
        self._route = route
        self.path = path

    def __getattr__(self, name: str) -> Any:
        return getattr(self._route, name)


def iter_fastapi_routes(routes: Iterable[Any], prefix: str = "") -> Iterator[Any]:
    """Yield concrete route objects, flattening included-router wrappers.

    Router prefixes (including nested includes) are applied to each yielded
    route's ``path``.
    """

    for route in routes:
        original_router = getattr(route, "original_router", None)
        if original_router is not None:
            wrapper_prefix = getattr(route, "prefix", "") or ""
            router_prefix = getattr(original_router, "prefix", "") or ""
            child_prefix = _concat(_concat(prefix, wrapper_prefix), router_prefix)
            yield from iter_fastapi_routes(getattr(original_router, "routes", []) or [], child_prefix)
            continue

        path = getattr(route, "path", None)
        if prefix and isinstance(path, str):
            yield _PrefixedRoute(route, _qualify(prefix, path))
        else:
            yield route


def iter_app_routes(app: Any) -> Iterator[Any]:
    """Yield concrete route objects from a FastAPI application."""

    yield from iter_fastapi_routes(getattr(app, "routes", []) or [])

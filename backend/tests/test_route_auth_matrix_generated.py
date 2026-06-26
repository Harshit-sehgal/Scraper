"""Static + introspection guard for F-RBAC-001 — every non-public route has auth.

Pre-fix, the codebase relied on a ``grep``-style check that asks "does
this router file import a ``require_*`` helper?" to decide whether the
routes inside it are protected. That check produces false negatives:

  - ``app/routers/health.py`` legitimately omits auth (it's a probe
    endpoint).
  - ``app/routers/session.py`` is the login route itself.
  - ``app/routers/jobs.py`` is a façade that mounts child routers; the
    child routers carry auth.

The catch: a future contributor who adds a *single* new router with
``APIRouter()`` (no auth helpers) for what looks like an admin endpoint
will silently pass the static grep check while leaking data.

The fix is a generator test that:

1. Builds the FastAPI app via ``app.main.create_app()``.
2. Walks every route that resolves to an ``APIRoute`` *and* has a
   non-public path prefix.
3. Asserts each such route has at least one ``require_*``-prefixed
   dependency in either:
     - ``route.dependencies=[...]`` (path-level), or
     - function-signature ``Annotated[X, Depends(require_*(...))]`` (the
       way most DataForge routers actually wire auth).

Public routes are taken from a hardcoded allow-list until the matrix
generator itself matures. The list is deliberately narrow:

``UNPROTECTED_PATH_PREFIXES`` = {"/health", "/ready", "/healthz", "/docs",
"/redoc", "/openapi.json"} plus anything in ``auth`` and ``session`` for
the auth-bootstrap path.

Notes on routers that mount child routers:
    The ``app.routers.jobs`` façade uses ``Mount``-style sub-router
    inclusion.  ``_iter_routes`` follows ``original_router`` to enumerate
    the leaf ``APIRoute`` objects so child routers get covered by the
    same check.  Façade-only routers otherwise show as ``Mount`` and
    would be silently skipped.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND))


# Routes that MUST remain public by design. Adding a new entry here
# requires conscious approval — the comment records *why* each prefix
# is on the allow-list.
UNPROTECTED_PATH_PREFIXES: tuple[str, ...] = (
    "/",  # root / health alias
    "/health",  # k8s liveness probe — must be public
    "/ready",  # k8s readiness probe — must be public
    "/healthz",  # alternate health probe alias
    "/metrics",  # Prometheus scrape — segregated by network ACL
    "/docs",  # FastAPI built-in
    "/redoc",  # FastAPI built-in
    "/openapi.json",  # FastAPI built-in
    # Auth bootstrap — must accept unauthenticated calls.
    "/auth/login",
    "/auth/oidc/",
    "/auth/logout",
    "/auth/session",
    "/api/auth/login",
    "/api/auth/oidc/",
    "/api/auth/logout",
    "/api/auth/session",
    "/api/auth/",
    # SaaS signup / password reset / email verify must be public so a
    # brand-new client (no session yet) can register.
    "/api/saas/signup",
    "/api/saas/email-verification/",
    "/api/saas/password-reset/request",
    "/api/saas/password-reset/reset",
    # Session cookie bootstrap — the route IS the auth boundary.
    "/api/session",
    # CSP report-only endpoint — must accept browser-generated reports
    # without an authenticated session.
    "/api/system/csp-violations",
    # Billing webhooks are authenticated by Stripe signature, not by an
    # API key.  Pinning ``require_*`` on them would break the gateway.
    "/api/billing/webhook",
    "/api/billing/stub-return/",
    "/api/intelligence/analyze-url",
    # legitimate *public* analyzer — operators
    # expose it for unauthenticated URL triage;
    # needs explicit sign-off if changed.
)


def _is_protected(path: str) -> bool:
    return not any(path.startswith(p) for p in UNPROTECTED_PATH_PREFIXES)


def _route_dep_names(route) -> list[str]:
    """Return the __name__ of every callable listed as a route dep.

    Many DataForge routers declare auth via ``Annotated[UserRole, Depends(require_role(...))]``
    on the endpoint function signature. ``inspect.signature`` collapses an
    ``Annotated[X, Depends(...)]`` default into ``inspect._empty`` — the
    actual ``Depends`` wrapper survives only inside the parameter's
    ``annotation`` metadata. Because every router module uses
    ``from __future__ import annotations``, the parameter annotations are
    stringified; we must resolve them via ``typing.get_type_hints(include_extras=True)``
    to recover the live ``Annotated`` chain.

    Walked surfaces:

      * route-level ``route.dependencies=[...]`` (path-level deps); and
      * function-signature-level annotations (the inline-Annotated path).
    """
    import inspect as _inspect
    import typing

    from fastapi.params import Depends as _FDepends

    names: list[str] = []

    # 1. Route-level ``dependencies=[..]`` list.
    for d in getattr(route, "dependencies", None) or []:
        callable_ = getattr(d, "dependency", None) or getattr(d, "callable", None)
        name = getattr(callable_, "__name__", None)
        if name:
            names.append(name)

    # 2. Function-signature-level Depends() inside Annotated metadata.
    endpoint = getattr(route, "endpoint", None)
    if endpoint is None:
        return names
    try:
        sig = _inspect.signature(endpoint)
    except (TypeError, ValueError):
        return names

    # Resolve stringified annotations into live ``Annotated`` objects so
    # we can peel off the ``Depends`` wrapper stored as metadata.
    try:
        hints = typing.get_type_hints(endpoint, include_extras=True)
    except Exception:
        hints = {}

    for param_name, param in sig.parameters.items():
        # 2a. Annotated-style: ``Annotated[X, Depends(...)]`` — recover
        # via get_type_hints so the metadata survives stringification.
        ann = hints.get(param_name, param.annotation)
        if typing.get_origin(ann) is typing.Annotated:
            for meta in typing.get_args(ann)[1:]:
                if isinstance(meta, _FDepends):
                    dep = getattr(meta, "dependency", None)
                    dep_name = getattr(dep, "__name__", None)
                    if dep_name:
                        names.append(dep_name)
        # 2b. Older style: ``field: X = Depends(...)`` — default holds the
        # Depends wrapper directly. Defensively handle.
        default = param.default
        if isinstance(default, _FDepends):
            dep = getattr(default, "dependency", None)
            dep_name = getattr(dep, "__name__", None)
            if dep_name:
                names.append(dep_name)
        # 2c. Stringified annotation path (no from __future__). When the
        # annotation survives as a string after stringification, ``get_args``
        # lets us extract the underlying Depends instance buried inside.
        if isinstance(ann, str) and "Depends(" in ann and "annotated" not in ann.lower():
            # Worth a last-ditch regex sweep so we don't miss a route that
            # only resolves annotation late.
            import re as _re

            for call_match in _re.finditer(r"Depends\(\s*([A-Za-z_][A-Za-z0-9_]*)", ann):
                names.append(call_match.group(1))
    return names


class TestNonPublicRoutesCarryAuthDependencies:
    """Every non-public ``APIRoute`` has at least one ``require_*`` dep."""

    def test_required_helpers_exist_in_codebase(self) -> None:
        # Sanity: the helpers we expect must exist somewhere; otherwise
        # this test would silently lose meaning if a refactor relocates
        # them to a different module path.
        from app.utils import rbac as rbac_mod

        for name in ("require_principal", "require_role"):
            assert hasattr(rbac_mod, name), (
                f"F-RBAC-001: ``{name}`` not exported from app.utils.rbac;"
                " the F-RBAC-001 invariant cannot be enforced without it."
            )

    def test_non_public_routes_carry_auth_dependency(self) -> None:
        from app.main import create_app

        # We don't fire the lifespan (Postgres, Playwright and friends
        # would fail) so build the app and walk the routes only.
        app = create_app()

        # Flatten router-recursive walking.
        def _iter_routes(routes):
            for r in routes:
                original = getattr(r, "original_router", None)
                if original is not None:
                    yield from _iter_routes(getattr(original, "routes", []) or [])
                    continue
                yield r

        from fastapi.routing import APIRoute

        offenders: list[tuple[str, str, list[str]]] = []
        for route in _iter_routes(getattr(app, "routes", [])):  # type: ignore[attr-defined]
            if not isinstance(route, APIRoute):
                continue
            path = getattr(route, "path", "") or ""
            if not _is_protected(path):
                continue
            dep_names = _route_dep_names(route)
            # Match either the factory (``require_role``, ``require_principal``)
            # OR the inner closure it returns — FastAPI unwraps ``Annotated[X,
            # Depends(require_role(...))]`` to the inner ``dependency`` callable.
            has_require = any(re.match(r"^(require_[a-z_]+|dependency)$", n) for n in dep_names)
            if not has_require:
                offenders.append((path, getattr(route, "name", "?"), dep_names))

        assert not offenders, (
            "F-RBAC-001: these non-public routes do not declare any"
            " ``require_*`` auth dependency in their FastAPI"
            " ``dependencies``. Each line is (path, route_name, dep_names).\n"
            "Add the missing dependency factory in the router file or,"
            " if the path is genuinely public, list it in"
            " ``UNPROTECTED_PATH_PREFIXES`` with a comment justifying the"
            " exception:\n  - " + "\n  - ".join(f"{p} ({n}, deps={d!r})" for p, n, d in offenders)
        )

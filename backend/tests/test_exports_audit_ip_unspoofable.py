"""Regression test: ``_get_client_ip_for_audit`` must not trust ``X-Forwarded-For``.

Bug: ``backend/app/routers/exports.py::_get_client_ip_for_audit`` read
``X-Forwarded-For`` unconditionally, so an unauthenticated caller
could forge the client IP recorded in the audit log by sending a
spoofed header. This bypasses the central trusted-proxy check in
``app.middlewares._get_client_ip``.

Fix: delegate to ``app.middlewares._get_client_ip`` so audit logs
trust XFF only when the direct client is a configured trusted proxy.

These tests pin the new behavior by patching
``app.rate_limiter._is_trusted_proxy`` (the upstream gate) and
verifying the returned IP matches the expected behavior.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from starlette.requests import Request as StarletteRequest


def _build_request(client_host: str, xff: str | None = None) -> StarletteRequest:
    """Build a minimal Starlette Request with a controllable client + XFF."""
    headers: list[tuple[bytes, bytes]] = []
    if xff is not None:
        headers.append((b"x-forwarded-for", xff.encode("ascii")))
    raw_headers = headers
    scope: dict[str, Any] = {
        "type": "http",
        "method": "GET",
        "scheme": "https",
        "path": "/api/jobs/test/export/csv",
        "raw_path": b"/api/jobs/test/export/csv",
        "query_string": b"",
        "headers": raw_headers,
        "client": (client_host, 12345),
        "server": ("test", 443),
    }
    return StarletteRequest(scope)


def test_audit_ip_ignores_xff_when_direct_client_is_untrusted() -> None:
    """When the direct client is NOT a trusted proxy, XFF is ignored."""
    from app.routers.exports import _get_client_ip_for_audit

    request = _build_request(client_host="203.0.113.5", xff="8.8.8.8, 1.1.1.1")
    with patch("app.rate_limiter._is_trusted_proxy", return_value=False):
        assert _get_client_ip_for_audit(request) == "203.0.113.5"


def test_audit_ip_uses_xff_first_hop_when_direct_client_is_trusted() -> None:
    """When the direct client IS a trusted proxy, the first XFF hop is used."""
    from app.routers.exports import _get_client_ip_for_audit

    request = _build_request(client_host="127.0.0.1", xff="8.8.8.8, 1.1.1.1")
    with patch("app.rate_limiter._is_trusted_proxy", return_value=True):
        assert _get_client_ip_for_audit(request) == "8.8.8.8"


def test_audit_ip_returns_unknown_when_no_trusted_proxy_and_no_client() -> None:
    """Pin upstream behaviour: client=None + no XFF falls back to ``"unknown"``.

    Note: this test passes if the helper returns ``"unknown"`` for
    any reason (helper's ``except`` clause OR upstream's internal
    fallback). It does NOT specifically exercise the helper's
    narrower ``except (ImportError, AttributeError, TypeError)`` —
    that branch is pinned by
    ``test_audit_ip_returns_unknown_when_ip_helper_raises`` below.
    Green result here only confirms the helper surfaces ``"unknown"``
    when the upstream correctly reports no client identity.

    Caveat: if you remove the inline ``from app.middlewares import
    _get_client_ip`` and its try/except fallback entirely, THIS test
    still passes — but the helper would no longer satisfy the audit
    contract for non-/api/ requests. Always rely on test #4 for the
    real fail-closed invariant.
    """
    from app.routers.exports import _get_client_ip_for_audit

    # Direct client marked as not-trusted AND no XFF -> falls back
    # to client.host, but if client is None the upstream returns "unknown".
    headers: list[tuple[bytes, bytes]] = []
    scope: dict[str, Any] = {
        "type": "http",
        "method": "GET",
        "scheme": "https",
        "path": "/api/jobs/test/export/csv",
        "raw_path": b"/api/jobs/test/export/csv",
        "query_string": b"",
        "headers": headers,
        "client": None,
        "server": ("test", 443),
    }
    request = StarletteRequest(scope)
    with patch("app.rate_limiter._is_trusted_proxy", return_value=False):
        assert _get_client_ip_for_audit(request) == "unknown"


def test_audit_ip_returns_unknown_when_ip_helper_raises() -> None:
    """Pin the except-fallback to ``"unknown"`` when the IP helper raises.

    Without this pin the narrower ``except (ImportError,
    AttributeError, TypeError)`` clause could silently regress to
    catching nothing, because no production path actually triggers it.
    A regression in ``app.middlewares._get_client_ip`` (wrong
    signature, missing dep, bug in the trusted-proxy check) must
    NOT propagate to the export route as a 5xx — audit must still
    record ``"unknown"`` rather than nothing.

    Implementation note: the patch targets ``app.middlewares._get_client_ip``
    directly. This works because the helper imports it with
    ``from app.middlewares import _get_client_ip`` INSIDE its
    function body in
    ``backend/app/routers/exports.py::_get_client_ip_for_audit``,
    so Python rebinds the name from the module namespace on each
    call. If that import is ever refactored to a module-level
    import, this test will silently stop exercising the except
    clause — also update the patch target in that case.
    """
    from app.routers.exports import _get_client_ip_for_audit

    request = _build_request(client_host="203.0.113.5")
    with patch("app.middlewares._get_client_ip", side_effect=AttributeError("simulated")):
        assert _get_client_ip_for_audit(request) == "unknown"

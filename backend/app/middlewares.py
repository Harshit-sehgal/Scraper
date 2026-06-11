from __future__ import annotations

import logging
import secrets
import time
from contextlib import suppress
from typing import TYPE_CHECKING

from fastapi.responses import JSONResponse

from app.audit_logger import log_auth_event
from app.config import settings
from app.rate_limiter import RateLimiterMiddleware

if TYPE_CHECKING:
    from fastapi import Request


def _get_client_ip(request: Request) -> str:
    """Extract the originating client IP, honoring reverse-proxy headers.

    Trusted proxy: nginx. The deployment runs nginx as the single
    ingress proxy in front of the API, and nginx is configured to
    forward the original client IP via ``X-Forwarded-For`` and
    ``X-Real-IP``. We read those headers here so audit logs reflect
    the real caller, not the proxy's loopback address.

    XFF/X-Real-IP headers are only trusted when the direct client
    is a known trusted proxy (e.g. nginx on localhost).

    Precedence:
    1. ``X-Forwarded-For`` first hop (the leftmost entry is the
       original client when the header is appended at each hop).
    2. ``X-Real-IP`` (single-IP variant nginx sometimes sets).
    3. ``request.client.host`` as a last-resort fallback for direct
       connections (no proxy) or unusual deployment topologies.

    Returns ``"unknown"`` if none of the above yield a usable value.
    """
    from app.rate_limiter import _is_trusted_proxy

    client_host = request.client.host if request.client else ""
    if client_host and _is_trusted_proxy(client_host):
        xff = request.headers.get("X-Forwarded-For")
        if xff:
            first = xff.split(",", 1)[0].strip()
            if first:
                return first
        xri = request.headers.get("X-Real-IP")
        if xri:
            return xri.strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _is_match(provided: str, expected: str) -> bool:
    """Constant-time API-key comparison.

    Hoisted to module scope so we don't allocate a new function object
    on every request. The empty-string short-circuit keeps the constant
    time characteristic for unequal-length inputs (one branch returns
    immediately; the other compares two known-non-empty strings).
    """
    if not expected or not provided:
        return False
    return secrets.compare_digest(provided, expected)


logger = logging.getLogger(__name__)

MAX_BODY_SIZE = 5 * 1024 * 1024  # 5MB


async def body_size_middleware(request: Request, call_next):
    """Limit request body size to prevent abuse.

    Always streams and counts the body, regardless of ``Content-Length``.
    A client cannot bypass the cap by lying about the Content-Length
    and then streaming many gigabytes of chunked-encoded data.
    """
    if request.method not in ("POST", "PUT", "PATCH") or not request.url.path.startswith("/api/"):
        return await call_next(request)

    # Fast path: trust Content-Length as an early reject, but still
    # stream-verify on the way in. The actual byte-counting happens
    # in the loop below, so a lying Content-Length cannot bypass.
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_BODY_SIZE:
                return JSONResponse(
                    status_code=413,
                    content={"detail": "Request body too large (max 5MB)"},
                )
        except (ValueError, TypeError):
            pass

    chunks: list[bytes] = []
    bytes_received = 0
    async for chunk in request.stream():
        bytes_received += len(chunk)
        if bytes_received > MAX_BODY_SIZE:
            return JSONResponse(
                status_code=413,
                content={"detail": "Request body too large (max 5MB)"},
            )
        chunks.append(chunk)

    body = b"".join(chunks)
    replayed = False

    async def replay_body():
        nonlocal replayed
        if replayed:
            return {"type": "http.request", "body": b"", "more_body": False}
        replayed = True
        return {"type": "http.request", "body": body, "more_body": False}

    request._receive = replay_body
    # Pre-populate the cached body so downstream Request.body() / .stream()
    # calls short-circuit on ``_body`` and never re-read ``_receive``.
    # This is the canonical Starlette pattern for re-readable body streams.
    request._body = body
    return await call_next(request)


async def api_key_middleware(request: Request, call_next):
    if (settings.API_KEY or settings.ADMIN_API_KEY or getattr(settings, "OPERATOR_API_KEY", "")) and request.url.path.startswith(
        "/api/",
    ):
        if request.method == "OPTIONS" and request.headers.get("Origin") and request.headers.get("Access-Control-Request-Method"):
            return await call_next(request)
        # CSP violation reports are sent by browsers, which cannot carry API keys.
        # This endpoint must remain unauthenticated but is still rate-limited
        # and body-size-capped by the other middlewares.
        if request.url.path == "/api/system/csp-violations":
            return await call_next(request)
        # Session management endpoints are exempt from API key middleware.
        # They use their own auth logic (exchanging key for cookie, or
        # returning session state from the cookie itself).
        if request.url.path in ("/api/session", "/api/session/me"):
            return await call_next(request)
        # Use exact-match / prefix-match on the docs / openapi paths.
        # Substring matching (e.g. ``"/docs" in path``) would falsely
        # exempt any path containing those letters, including a
        # future ``/api/dossier`` or ``/api/some-openapi-redirect``.
        docs_paths = ("/docs", "/openapi.json")
        is_docs_path = request.url.path in docs_paths or request.url.path.startswith(("/docs/", "/redoc", "/openapi"))
        if not is_docs_path or settings.ENV.lower() == "production":
            api_key = request.headers.get("X-API-Key", "")
            admin_key_header = request.headers.get("X-Admin-Key", "")
            auth_header = request.headers.get("Authorization", "")
            auth_scheme, _, auth_token = auth_header.partition(" ")
            bearer_token = auth_token.strip() if auth_scheme.lower() == "bearer" else ""

            matched_role: str | None = None
            # Match the HIGHEST privilege first so a request that
            # successfully authenticates against the admin key is
            # attributed to the admin role, even if it also carries a
            # user or operator key. A *wrong* admin key falls through
            # to the operator/user checks (no early 403).
            if settings.ADMIN_API_KEY and (
                _is_match(api_key, settings.ADMIN_API_KEY)
                or _is_match(bearer_token, settings.ADMIN_API_KEY)
                or _is_match(admin_key_header, settings.ADMIN_API_KEY)
            ):
                matched_role = "admin"
            elif getattr(settings, "OPERATOR_API_KEY", "") and (
                _is_match(api_key, settings.OPERATOR_API_KEY) or _is_match(bearer_token, settings.OPERATOR_API_KEY)
            ):
                matched_role = "operator"
            elif settings.API_KEY and (_is_match(api_key, settings.API_KEY) or _is_match(bearer_token, settings.API_KEY)):
                matched_role = "user"

            # Fall back to session cookie check if no API key matched.
            # This allows browser clients to authenticate via HTTP-only
            # session cookie after the initial key exchange (G2).
            if not matched_role:
                from app.auth.session import get_session_role

                session_role = get_session_role(request)
                if session_role:
                    matched_role = session_role

            if not matched_role:
                log_auth_event(
                    actor=_get_client_ip(request),
                    action="api_key_auth",
                    resource=request.url.path,
                    outcome="failure",
                    details={"method": request.method, "has_bearer": bool(bearer_token)},
                )
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Invalid or missing API key. Provide X-API-Key or Authorization Bearer token."},
                )
            if request.method != "GET":
                log_auth_event(
                    actor=f"{matched_role}:{_get_client_ip(request)}",
                    action="api_key_auth",
                    resource=request.url.path,
                    outcome="success",
                    details={"role": matched_role, "method": request.method},
                )
    return await call_next(request)


async def latency_tracking_middleware(request: Request, call_next):
    """Track API and metrics endpoint request durations for Prometheus export."""
    path = request.url.path
    if path.startswith("/api/") or path == "/metrics" or path in ("/health", "/ready"):
        start = time.time()
        try:
            return await call_next(request)
        finally:
            duration = time.time() - start
            from app.metrics_collector import record_request_latency

            record_request_latency(duration)
    else:
        return await call_next(request)


# ─── CSP (Content-Security-Policy) Report-Only ────────────────────────────
# A conservative report-only CSP is sent with every response. The policy is
# deliberately loose (it must not break the dashboard or scraper UI) but it
# surfaces a violation report endpoint so the operator can tighten the policy
# iteratively. Enable via DATAFORGE_CSP_REPORT_ONLY=true (default true in
# development, false in production until the operator confirms the policy).
DEFAULT_CSP_REPORT_ONLY_POLICY = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: https:; "
    "font-src 'self' data:; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "report-uri /api/system/csp-violations"
)


async def csp_report_only_middleware(request: Request, call_next):
    """Attach a report-only Content-Security-Policy header to every response.

    The header is *report-only* — it never blocks anything — but the browser
    will POST a violation report to ``/api/system/csp-violations`` when a
    directive is violated. The endpoint logs the violation and increments
    ``dataforge_csp_violations_total{directive=...}``.
    """
    if not getattr(settings, "CSP_REPORT_ONLY", True):
        return await call_next(request)

    response = await call_next(request)
    with suppress(AttributeError, TypeError, ValueError):
        response.headers.setdefault(
            "Content-Security-Policy-Report-Only",
            DEFAULT_CSP_REPORT_ONLY_POLICY,
        )
    return response


rate_limiter = RateLimiterMiddleware(
    global_limit=settings.RATE_LIMIT_GLOBAL,
    per_ip=settings.RATE_LIMIT_PER_IP_ENABLED,
    per_ip_limit=settings.RATE_LIMIT_PER_IP,
)

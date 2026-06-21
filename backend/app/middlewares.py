from __future__ import annotations

import logging
import time
from contextlib import suppress
from typing import TYPE_CHECKING

from fastapi import HTTPException
from fastapi.responses import JSONResponse

from app.audit_logger import log_auth_event, log_rbac_event
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


logger = logging.getLogger(__name__)

MAX_BODY_SIZE = 5 * 1024 * 1024  # 5MB


def _extract_principal_attr(request: Request, attr: str) -> str:
    """Best-effort extraction of a P0-SAAS-001 principal attribute for audit logs.

    Reads from ``request.state.auth_context`` (set by
    ``rbac.resolve_auth_context``) when present. Returns ``""`` if the
    request has no resolved auth context (e.g. failed-auth events that
    never got far enough to populate it).
    """
    cached = getattr(getattr(request, "state", None), "auth_context", None)
    return str(getattr(cached, attr, "") or "")


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
            return {"type": "http.disconnect"}
        replayed = True
        return {"type": "http.request", "body": body, "more_body": False}

    request._receive = replay_body
    # Pre-populate the cached body so downstream Request.body() / .stream()
    # calls short-circuit on ``_body`` and never re-read ``_receive``.
    # This is the canonical Starlette pattern for re-readable body streams.
    request._body = body
    return await call_next(request)


async def api_key_middleware(request: Request, call_next):
    if request.url.path.startswith("/api/"):
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
        # Self-service account signup is intentionally public. It remains
        # covered by body-size limits and the global rate limiter.
        if request.url.path == "/api/saas/signup":
            return await call_next(request)
        # Billing webhooks are called by Autumn/Stripe, which do not carry
        # DataForge API keys. The endpoint is rate-limited and body-size
        # capped by other middlewares.
        if request.url.path == "/api/billing/webhook":
            return await call_next(request)
        # Stub-return page is rendered in a browser after the operator
        # clicks the stub approval URL (PayPal credentials not configured).
        # Browsers do not carry API keys to this redirect URL, but the page
        # is dev-only — it shows a confirmation message and never commits
        # state — so it is allowed through unauthenticated.
        if request.url.path.startswith("/api/billing/stub-return/"):
            return await call_next(request)
        bearer_token = None
        auth_header = request.headers.get("Authorization", "")
        auth_scheme, _, auth_token = auth_header.partition(" ")
        if auth_scheme.lower() == "bearer":
            bearer_token = auth_token.strip()
        has_api_key_header = bool(request.headers.get("X-API-Key") or request.headers.get("X-Admin-Key"))

        try:
            from app.utils.rbac import resolve_auth_context

            auth_context = resolve_auth_context(request)
        except HTTPException as exc:
            log_auth_event(
                actor=_get_client_ip(request),
                action="api_key_auth" if has_api_key_header else "api_auth",
                resource=request.url.path,
                outcome="failure",
                details={"method": request.method, "has_bearer": bool(bearer_token)},
                org_id=_extract_principal_attr(request, "org_id"),
                project_id=_extract_principal_attr(request, "project_id"),
            )
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.detail},
            )

        try:
            from app.utils.usage_ledger import UsageType, get_usage_ledger

            get_usage_ledger().record_usage(
                auth_context.user_id,
                UsageType.API_REQUEST,
                quantity=1,
                metadata={
                    "path": request.url.path,
                    "method": request.method,
                    "role": auth_context.role.value,
                    "source": auth_context.source,
                },
                org_id=auth_context.org_id,
                project_id=auth_context.project_id,
            )
        except ValueError as exc:
            log_rbac_event(
                actor=auth_context.user_id,
                action="quota_exceeded:api_request",
                resource="usage:api_request",
                role=auth_context.role.value,
                outcome="denied",
                details={"path": request.url.path, "method": request.method, "error": str(exc)},
            )
            return JSONResponse(
                status_code=429,
                content={"detail": str(exc)},
            )

        if request.method != "GET":
            log_auth_event(
                actor=f"{auth_context.role.value}:{auth_context.user_id}:{_get_client_ip(request)}",
                action="api_auth",
                resource=request.url.path,
                outcome="success",
                details={"role": auth_context.role.value, "method": request.method, "source": auth_context.source},
                org_id=auth_context.org_id,
                project_id=auth_context.project_id,
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


async def security_headers_middleware(request: Request, call_next):
    """Add security headers to every response."""
    response = await call_next(request)

    # Prevent MIME type sniffing (XSS protection)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")

    # Prevent clickjacking
    response.headers.setdefault("X-Frame-Options", "DENY")

    # Enable XSS filter in browsers
    response.headers.setdefault("X-XSS-Protection", "1; mode=block")

    # Referrer policy
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")

    # Permissions policy (formerly Feature-Policy)
    response.headers.setdefault(
        "Permissions-Policy",
        "geolocation=(), microphone=(), camera=(), payment=(), usb=(), magnetometer=(), gyroscope=()",
    )

    # Apply Strict-Transport-Security (HSTS) only in production
    if settings.ENV.lower() == "production":
        response.headers.setdefault(
            "Strict-Transport-Security",
            "max-age=63072000; includeSubDomains; preload",
        )

    return response


rate_limiter = RateLimiterMiddleware(
    global_limit=settings.RATE_LIMIT_GLOBAL,
    per_ip=settings.RATE_LIMIT_PER_IP_ENABLED,
    per_ip_limit=settings.RATE_LIMIT_PER_IP,
)

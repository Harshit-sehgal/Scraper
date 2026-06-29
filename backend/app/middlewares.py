from __future__ import annotations

import logging
import time
import uuid
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

# API paths that are intentionally public and do not require authentication.
# Each entry includes the rationale inline so the exemption list is auditable.
# These endpoints are still covered by body-size caps, rate limiting, and
# other security middlewares.
_PUBLIC_API_PATHS: frozenset[str] = frozenset(
    {
        # CSP violation reports are sent by browsers, which cannot carry API keys.
        "/api/system/csp-violations",
        # Session management endpoints use their own auth (exchanging key for cookie).
        "/api/session",
        "/api/session/me",
        # Password reset endpoints are called by unauthenticated users in reset flows.
        "/api/saas/password-reset/request",
        "/api/saas/password-reset/reset",
        # Self-service signup is intentionally public.
        "/api/saas/signup",
        # Billing webhooks are called by PayPal/Stripe, which do not carry DataForge keys.
        "/api/billing/webhook",
    }
)

_PUBLIC_API_PREFIXES: tuple[str, ...] = (
    # Stub-return page is a browser redirect URL (dev-only, displays confirmation only).
    "/api/billing/stub-return/",
)


def _is_public_api_path(path: str) -> bool:
    """Return True if *path* is a public API endpoint (no API key required)."""
    if path in _PUBLIC_API_PATHS:
        return True
    return any(path.startswith(p) for p in _PUBLIC_API_PREFIXES)


def _is_cors_preflight(request: Request) -> bool:
    """Return True if this is a CORS preflight OPTIONS request."""
    return bool(
        request.method == "OPTIONS" and request.headers.get("Origin") and request.headers.get("Access-Control-Request-Method")
    )


async def _enforce_api_auth_and_quota(request: Request) -> None:
    """Authenticate the request and enforce usage quota.

    Raises HTTPException (caught by the caller) if authentication fails or
    the quota is exceeded. This extracted function keeps the middleware
    dispatch logic focused on routing decisions while the security/audit
    logic lives in one place.
    """
    auth_header = request.headers.get("Authorization", "")
    _auth_scheme, _, _auth_token = auth_header.partition(" ")

    from app.utils.rbac import resolve_auth_context

    auth_context = resolve_auth_context(request)

    from app.plan_enforcer import check_usage_limit
    from app.utils.usage_ledger import UsageType, get_usage_ledger

    quota_owner = auth_context.org_id or auth_context.project_id or auth_context.user_id
    allowed, details = check_usage_limit(
        quota_owner,
        UsageType.API_REQUEST,
        1,
        org_id=auth_context.org_id,
        project_id=auth_context.project_id,
    )
    if not allowed:
        _quota_msg = f"quota exceeded for api_requests: {details['current_usage'] + 1}/{details['limit']}"
        raise ValueError(_quota_msg)

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
        except (ValueError, TypeError) as exc:
            logger.debug("Ignoring invalid Content-Length header: %s", exc)

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
        if _is_cors_preflight(request):
            return await call_next(request)
        # Public-API exemptions (CSP reports, session, password-reset,
        # signup, billing webhooks, stub-return) are tracked centrally
        # in ``_PUBLIC_API_PATHS`` / ``_PUBLIC_API_PREFIXES`` so that the
        # two middleware layers (this one and api_auth_dependency) cannot
        # drift apart.  Adding a new public endpoint is one edit there.
        if _is_public_api_path(request.url.path):
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
            from app.plan_enforcer import check_usage_limit
            from app.utils.usage_ledger import UsageType, get_usage_ledger

            quota_owner = auth_context.org_id or auth_context.project_id or auth_context.user_id
            allowed, details = check_usage_limit(
                quota_owner,
                UsageType.API_REQUEST,
                1,
                org_id=auth_context.org_id,
                project_id=auth_context.project_id,
            )
            if not allowed:
                _quota_msg = f"quota exceeded for api_requests: {details['current_usage'] + 1}/{details['limit']}"
                raise ValueError(_quota_msg)

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


async def csp_middleware(request: Request, call_next):
    """Attach a Content-Security-Policy header to every response.

    When ``CSP_REPORT_ONLY`` is True (the default), the header is
    ``Content-Security-Policy-Report-Only`` — violations are logged but
    never blocked. When False, the header is ``Content-Security-Policy``
    and the browser enforces the policy. Set to False in production only
    after confirming your application works with the policy in report-only
    mode. Set ``CSP_REPORT_ONLY=false`` in ``.env.production`` to enforce.
    """
    csp_mode = getattr(settings, "CSP_REPORT_ONLY", True)
    response = await call_next(request)
    with suppress(AttributeError, TypeError, ValueError):
        response.headers.setdefault(
            "Content-Security-Policy" if not csp_mode else "Content-Security-Policy-Report-Only",
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


# ─── Request ID Propagation ─────────────────────────────────────────────


async def request_id_middleware(request: Request, call_next):
    """Propagate or generate a per-request correlation ID.

    If the inbound request carries an ``X-Request-ID`` header, its value is
    normalised and reused (allows upstream services like nginx or an API
    gateway to set the ID).  Otherwise a random UUID4 is generated.

    The ID is stored on ``request.state.request_id`` and attached as an
    ``X-Request-ID`` response header so callers can correlate logs with
    HTTP responses.  Downstream code (workers, storage, webhooks) can
    access the ID via ``getattr(request.state, "request_id", "")``.

    MEDIUM (#138): The inbound header value is sanitised before use.
    Without validation, an attacker could supply
    ``X-Request-ID: abc\\r\\nSet-Cookie: pwn=1`` to inject CRLF into the
    response header (HTTP header injection / response splitting on
    lenient parsers) or to break log lines. Constrain the value to a
    safe charset and length; if the inbound value is rejected, fall
    back to a freshly-generated UUID so the request still has an ID
    and downstream correlation continues to work.
    """
    request_id = request.headers.get("X-Request-ID", "").strip()
    if not _is_safe_request_id(request_id):
        request_id = uuid.uuid4().hex
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers.setdefault("X-Request-ID", request_id)
    return response


# Allowed charset for inbound X-Request-ID values: ASCII letters/digits,
# hyphen, underscore, dot. Length cap mirrors common correlation IDs and
# limits log-line growth. Anything outside this set (including CRLF,
# unicode, and other control chars) is rejected.
_REQUEST_ID_MAX_LEN = 128
_REQUEST_ID_SAFE_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.",
)


def _is_safe_request_id(value: str) -> bool:
    """Return True iff ``value`` is a safe inbound X-Request-ID.

    Rejects empty strings (handled separately), values containing
    whitespace or control characters (CRLF injection risk), values
    exceeding the length cap (log pollution), and values carrying any
    character outside the safe charset.
    """
    if not value or not isinstance(value, str):
        return False
    if len(value) > _REQUEST_ID_MAX_LEN:
        return False
    return all(c in _REQUEST_ID_SAFE_CHARS for c in value)


# ─── Access Log ────────────────────────────────────────────────────────


async def access_log_middleware(request: Request, call_next):
    """Structured JSON access logging for every API request.

    Emits one log line per request with method, path, status code,
    latency, and client IP. Uses the standard ``logging`` module so
    output goes to stdout (container-friendly). The log record is
    structured as a JSON object for easy parsing by log aggregators
    (ELK, Loki, CloudWatch Logs, etc.).

    Only logs API requests (``/api/`` prefix) and health endpoints
    to avoid noise from static assets and favicon hits.

    Integration with ``metrics_collector``: the latency histogram is
    already recorded by ``latency_tracking_middleware``; this middleware
    adds the human-readable log line for incident response.
    """
    path = request.url.path
    if not (path.startswith("/api/") or path in ("/health", "/ready")):
        return await call_next(request)

    start = time.time()
    response = await call_next(request)
    duration_ms = (time.time() - start) * 1000

    access_logger.info(
        "",
        extra={
            "access_log": True,
            "method": request.method,
            "path": path,
            "status": response.status_code,
            "latency_ms": round(duration_ms, 1),
            "client_ip": _get_client_ip(request),
            "request_id": getattr(request.state, "request_id", ""),
        },
    )
    return response


access_logger = logging.getLogger("dataforge.access")

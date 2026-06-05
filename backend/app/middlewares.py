from __future__ import annotations

import logging
import secrets
import time
from typing import TYPE_CHECKING

from fastapi.responses import JSONResponse

from app.audit_logger import log_auth_event
from app.config import settings
from app.rate_limiter import RateLimiterMiddleware

if TYPE_CHECKING:
    from fastapi import Request

logger = logging.getLogger(__name__)

MAX_BODY_SIZE = 5 * 1024 * 1024  # 5MB


async def body_size_middleware(request: Request, call_next):
    """Limit request body size to prevent abuse."""
    if request.method not in ("POST", "PUT", "PATCH") or not request.url.path.startswith("/api/"):
        return await call_next(request)

    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_BODY_SIZE:
                return JSONResponse(
                    status_code=413,
                    content={"detail": "Request body too large (max 5MB)"},
                )
            return await call_next(request)
        except (ValueError, TypeError):
            pass  # nosec B110

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
    return await call_next(request)


async def api_key_middleware(request: Request, call_next):
    if (settings.API_KEY or settings.ADMIN_API_KEY or getattr(settings, "OPERATOR_API_KEY", "")) and request.url.path.startswith(
        "/api/",
    ):
        if request.method == "OPTIONS" and request.headers.get("Origin") and request.headers.get("Access-Control-Request-Method"):
            return await call_next(request)
        is_docs_path = "/docs" in request.url.path or "/openapi" in request.url.path
        if not is_docs_path or settings.ENV.lower() == "production":
            api_key = request.headers.get("X-API-Key", "")
            admin_key_header = request.headers.get("X-Admin-Key", "")
            auth_header = request.headers.get("Authorization", "")
            auth_scheme, _, auth_token = auth_header.partition(" ")
            bearer_token = auth_token.strip() if auth_scheme.lower() == "bearer" else ""

            def is_match(provided, expected):
                if not expected or not provided:
                    return False
                return secrets.compare_digest(provided, expected)

            matched_role: str | None = None
            if settings.API_KEY and (is_match(api_key, settings.API_KEY) or is_match(bearer_token, settings.API_KEY)):
                matched_role = "user"
            elif getattr(settings, "OPERATOR_API_KEY", "") and (
                is_match(api_key, settings.OPERATOR_API_KEY) or is_match(bearer_token, settings.OPERATOR_API_KEY)
            ):
                matched_role = "operator"
            elif settings.ADMIN_API_KEY and (
                is_match(api_key, settings.ADMIN_API_KEY)
                or is_match(bearer_token, settings.ADMIN_API_KEY)
                or is_match(admin_key_header, settings.ADMIN_API_KEY)
            ):
                matched_role = "admin"

            if not matched_role:
                log_auth_event(
                    actor=request.client.host if request.client else "unknown",
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
                    actor=f"{matched_role}:{request.client.host if request.client else 'unknown'}",
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
    try:
        response.headers.setdefault(
            "Content-Security-Policy-Report-Only",
            DEFAULT_CSP_REPORT_ONLY_POLICY,
        )
    except (AttributeError, TypeError, ValueError):
        # Some response types (StreamingResponse, Response without headers
        # mutation) may reject setdefault; never let CSP break the response.
        pass
    return response


rate_limiter = RateLimiterMiddleware(
    global_limit=settings.RATE_LIMIT_GLOBAL,
    per_ip=settings.RATE_LIMIT_PER_IP_ENABLED,
    per_ip_limit=settings.RATE_LIMIT_PER_IP,
)

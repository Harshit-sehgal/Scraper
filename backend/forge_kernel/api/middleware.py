"""Middleware — CORS, body size, API key authentication, and latency tracking.

Ported from existing app.middlewares into the kernel.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from forge_kernel.config import settings
from forge_kernel.security.rbac import _resolve_role

if TYPE_CHECKING:
    from collections.abc import Callable

    from fastapi import FastAPI, Request, Response

logger = logging.getLogger(__name__)


MAX_BODY_SIZE = 10 * 1024 * 1024  # 10 MB


class BodySizeMiddleware(BaseHTTPMiddleware):
    """Reject requests with body larger than MAX_BODY_SIZE."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > MAX_BODY_SIZE:
                    from fastapi.responses import JSONResponse

                    return JSONResponse(
                        status_code=413,
                        content={"detail": f"Request body exceeds maximum allowed size of {MAX_BODY_SIZE} bytes"},
                    )
            except ValueError:
                from fastapi.responses import JSONResponse

                return JSONResponse(
                    status_code=400,
                    content={"detail": "Invalid Content-Length header"},
                )
        return await call_next(request)


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Check API key for /api/* endpoints unless authentication is disabled."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Only protect /api/* routes
        if not request.url.path.startswith("/api/"):
            return await call_next(request)

        # Allow health/ready without auth
        if request.url.path in ("/api/health", "/api/ready"):
            return await call_next(request)

        sec = settings.security

        # If no API keys are configured, allow all
        if not sec.API_KEY and not sec.OPERATOR_API_KEY and not sec.ADMIN_API_KEY:  # nosec B105 — string-equality against empty string, no credential present
            return await call_next(request)

        # Check auth
        api_key = request.headers.get("X-API-Key", "")
        auth_header = request.headers.get("Authorization", "")
        bearer_token = ""  # nosec B105 — initialized empty; populated below only on valid Bearer prefix
        if auth_header.startswith("Bearer "):
            bearer_token = auth_header[7:]

        key_to_check = api_key or bearer_token
        role = _resolve_role(key_to_check) if key_to_check else None

        if role is None:
            from fastapi.responses import JSONResponse

            return JSONResponse(
                status_code=401,
                content={"detail": "Valid API key required. Provide X-API-Key or Authorization: Bearer header."},
            )

        return await call_next(request)


class LatencyTrackingMiddleware(BaseHTTPMiddleware):
    """Track request latency in kernel metrics."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start = time.monotonic()
        response = await call_next(request)
        duration = (time.monotonic() - start) * 1000
        try:
            from forge_kernel.observability import get_kernel_metrics

            get_kernel_metrics().record("request_duration_ms", duration)
        except Exception as e:
            logger.debug("Failed to record request duration metric: %s", e)
        return response


def configure_middleware(app: FastAPI) -> None:
    """Configure all middleware for the kernel FastAPI app."""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.security.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(BodySizeMiddleware)
    app.add_middleware(APIKeyMiddleware)
    app.add_middleware(LatencyTrackingMiddleware)

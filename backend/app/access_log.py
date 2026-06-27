"""Structured access log middleware.

Emits one JSON-shaped log line per HTTP request with:

* HTTP method, URL path, query string, response status, latency
* Client IP (honouring trusted-proxy XFF extraction)
* User-Agent fingerprint
* Request ID (X-Request-ID header or generated UUID)

Records duration to :func:`app.metrics_collector.record_request_latency`.

Disabled with ``DATAFORGE_ACCESS_LOG_ENABLED=false``.  Defaults to ``True``.

Best-effort: a logging failure must never turn a successful request
into a 500 — errors are swallowed with debug-level diagnostics.
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from typing import TYPE_CHECKING, Final

from starlette.middleware.base import BaseHTTPMiddleware

if TYPE_CHECKING:
    from starlette.requests import Request

logger = logging.getLogger(__name__)

ENV_VAR: Final[str] = "DATAFORGE_ACCESS_LOG_ENABLED"
DEFAULT_ENABLED: Final[bool] = True

# Paths excluded from the access log to avoid noise from health-probes
# and other high-frequency endpoints that operators don't audit.
_DEFAULT_NOISE_PATHS: Final[frozenset[str]] = frozenset(
    {
        "/health",
        "/ready",
        "/metrics",
    },
)

_NOISE_PATH_PREFIXES: Final[tuple[str, ...]] = (
    "/static/",
    "/assets/",
)


def access_log_enabled() -> bool:
    """Return whether the access-log middleware is active."""
    raw = os.environ.get(ENV_VAR, "").strip().lower()
    if not raw:
        return DEFAULT_ENABLED
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    return DEFAULT_ENABLED


def _should_log(path: str) -> bool:
    """Return False for high-noise paths (health probes, metrics)."""
    if path in _DEFAULT_NOISE_PATHS:
        return False
    return all(not path.startswith(prefix) for prefix in _NOISE_PATH_PREFIXES)


def _client_ip(request: Request) -> str:
    """Best-effort client-IP extraction for log purposes.

    Delegates to :func:`app.middlewares._get_client_ip` when
    available so XFF is honored only when the direct client is a
    trusted proxy — same posture as the audit-log writer.
    """
    try:
        from app.middlewares import _get_client_ip

        return _get_client_ip(request)
    except (ImportError, AttributeError):
        if request.client:
            return str(request.client.host)
    return "unknown"


class StructuredAccessLogMiddleware(BaseHTTPMiddleware):
    """Emit one structured log line per HTTP request."""

    def __init__(self, app, *, enabled: bool | None = None) -> None:  # type: ignore[no-untyped-def]
        super().__init__(app)
        self._enabled = enabled if enabled is not None else access_log_enabled()

    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        if not self._enabled:
            return await call_next(request)

        start = time.perf_counter()
        # Establish a request id so downstream logs/responses carry it.
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex

        try:
            response = await call_next(request)
            elapsed = time.perf_counter() - start
            self._emit_log(request, response.status_code, elapsed, request_id)
            response.headers["X-Request-ID"] = request_id
            return response
        except Exception as exc:
            elapsed = time.perf_counter() - start
            self._emit_log(
                request,
                500,
                elapsed,
                request_id,
                error_repr=repr(exc),
            )
            raise

    def _emit_log(
        self,
        request: Request,
        status_code: int,
        elapsed: float,
        request_id: str,
        *,
        error_repr: str | None = None,
    ) -> None:
        path = request.url.path
        if not _should_log(path):
            return
        try:
            client_ip = _client_ip(request)
            ua = request.headers.get("user-agent", "-")
            method = request.method
            extra: dict[str, object] = {
                "request_id": request_id,
                "method": method,
                "path": path,
                "status": int(status_code),
                "latency_seconds": round(elapsed, 6),
                "client_ip": client_ip,
                "user_agent": ua,
            }
            if error_repr is not None:
                extra["error"] = error_repr
            else:
                extra["event"] = "http_access"
            log_level = logging.ERROR if status_code >= 500 else logging.INFO
            logger.log(log_level, "%s %s -> %s (%.6fs)", method, path, status_code, elapsed, extra=extra)
            try:
                from app.metrics_collector import record_request_latency

                record_request_latency(elapsed)
            except (ImportError, AttributeError, RuntimeError):
                logger.debug("Failed to record request latency metric", exc_info=True)
        except (ValueError, TypeError, RuntimeError, ImportError):
            # Never let logging failure turn a successful request into a 5xx.
            logger.debug("Access log emission failed (non-blocking)", exc_info=True)

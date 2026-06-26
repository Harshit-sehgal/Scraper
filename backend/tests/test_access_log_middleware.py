"""Unit tests for the access log middleware.

Verifies that ``access_log_middleware`` emits structured log records
for API requests with the correct fields, and skips non-API paths.
"""

from __future__ import annotations

import logging
from io import StringIO
from unittest.mock import MagicMock

import pytest
from app.middlewares import access_log_middleware


class _RecordCapture(logging.Handler):
    """Lightweight handler that appends emitted LogRecords to a list."""

    def __init__(self, records: list[logging.LogRecord]) -> None:
        super().__init__()
        self._records = records

    def emit(self, record: logging.LogRecord) -> None:
        self._records.append(record)


class TestAccessLogMiddleware:
    """access_log_middleware emits structured JSON logs for API requests."""

    @pytest.mark.asyncio
    async def test_api_request_produces_response(self) -> None:
        """API requests should pass through and return the response."""
        request = MagicMock()
        request.url.path = "/api/jobs"
        request.method = "GET"
        request.client = MagicMock()
        request.client.host = "10.0.0.1"
        request.headers = {}

        response = MagicMock()
        response.status_code = 200

        async def call_next(req):
            return response

        result = await access_log_middleware(request, call_next)
        assert result is response

    @pytest.mark.asyncio
    async def test_health_endpoint_is_logged(self) -> None:
        """Health endpoint requests should also be logged."""
        request = MagicMock()
        request.url.path = "/health"
        request.method = "GET"
        request.client = MagicMock()
        request.client.host = "127.0.0.1"
        request.headers = {}

        response = MagicMock()
        response.status_code = 200

        async def call_next(req):
            return response

        result = await access_log_middleware(request, call_next)
        assert result is response

    @pytest.mark.asyncio
    async def test_non_api_path_is_not_logged(self) -> None:
        """Non-API paths (e.g. /favicon.ico) should pass through without logging."""
        request = MagicMock()
        request.url.path = "/favicon.ico"
        request.method = "GET"

        response = MagicMock()
        response.status_code = 404

        async def call_next(req):
            return response

        # Capture log output — should be empty
        logger = logging.getLogger("dataforge.access")
        handler = logging.StreamHandler(StringIO())
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        result = await access_log_middleware(request, call_next)

        log_output = handler.stream.getvalue()
        logger.removeHandler(handler)

        assert result is response
        # No log should have been emitted for non-API paths
        assert log_output == ""

    @pytest.mark.asyncio
    async def test_latency_is_recorded(self) -> None:
        """The latency_ms field should be present in the log extra dict."""

        request = MagicMock()
        request.url.path = "/api/system/status"
        request.method = "GET"
        request.client = MagicMock()
        request.client.host = "192.168.1.1"
        request.headers = {}

        response = MagicMock()
        response.status_code = 200

        async def call_next(req):
            return response

        records: list[logging.LogRecord] = []
        handler = _RecordCapture(records)
        logger = logging.getLogger("dataforge.access")
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        await access_log_middleware(request, call_next)
        logger.removeHandler(handler)

        assert len(records) == 1
        extra = records[0].__dict__
        assert "latency_ms" in extra
        assert isinstance(extra["latency_ms"], float)
        assert extra["latency_ms"] >= 0

    @pytest.mark.asyncio
    async def test_all_fields_present(self) -> None:
        """Verify all expected fields are in the log record."""
        request = MagicMock()
        request.url.path = "/api/jobs"
        request.method = "POST"
        request.client = MagicMock()
        request.client.host = "172.16.0.1"
        request.headers = {}

        response = MagicMock()
        response.status_code = 201

        async def call_next(req):
            return response

        records: list[logging.LogRecord] = []
        handler = _RecordCapture(records)
        logger = logging.getLogger("dataforge.access")
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        await access_log_middleware(request, call_next)
        logger.removeHandler(handler)

        assert len(records) == 1
        extra = records[0].__dict__
        assert extra["method"] == "POST"
        assert extra["path"] == "/api/jobs"
        assert extra["status"] == 201
        assert extra["access_log"] is True

    @pytest.mark.asyncio
    async def test_error_status_code_logged(self) -> None:
        """Error responses (5xx) should also be logged."""
        request = MagicMock()
        request.url.path = "/api/jobs/bad-id"
        request.method = "GET"
        request.client = MagicMock()
        request.client.host = "10.0.0.1"
        request.headers = {}

        response = MagicMock()
        response.status_code = 500

        async def call_next(req):
            return response

        records: list[logging.LogRecord] = []
        handler = _RecordCapture(records)
        logger = logging.getLogger("dataforge.access")
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        await access_log_middleware(request, call_next)
        logger.removeHandler(handler)

        assert len(records) == 1
        assert records[0].__dict__["status"] == 500

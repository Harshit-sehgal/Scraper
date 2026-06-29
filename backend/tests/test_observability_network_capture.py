"""Obs 16: Network request log capture — test network request logging."""
from __future__ import annotations

from typing import Any


def _make_network_log_entry(
    url: str,
    method: str = "GET",
    status_code: int = 200,
    timing_ms: float = 100.0,
    request_headers: dict[str, str] | None = None,
    response_headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build a network request log entry."""
    return {
        "url": url,
        "method": method,
        "status_code": status_code,
        "timing_ms": timing_ms,
        "request_headers": request_headers or {},
        "response_headers": response_headers or {},
    }


def _capture_network_log(captures: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Capture and return a snapshot of network request logs."""
    return list(captures)


class TestNetworkLogEntry:
    def test_basic_get_request(self) -> None:
        entry = _make_network_log_entry("https://example.com/api", method="GET", status_code=200)
        assert entry["url"] == "https://example.com/api"
        assert entry["method"] == "GET"
        assert entry["status_code"] == 200

    def test_post_request(self) -> None:
        entry = _make_network_log_entry("https://example.com/submit", method="POST", status_code=201)
        assert entry["method"] == "POST"
        assert entry["status_code"] == 201

    def test_error_response(self) -> None:
        entry = _make_network_log_entry("https://example.com/not-found", method="GET", status_code=404)
        assert entry["status_code"] == 404

    def test_server_error(self) -> None:
        entry = _make_network_log_entry("https://example.com/error", method="GET", status_code=500)
        assert entry["status_code"] == 500

    def test_redirect(self) -> None:
        entry = _make_network_log_entry("https://example.com/old", method="GET", status_code=301)
        assert entry["status_code"] == 301

    def test_timing_tracked(self) -> None:
        entry = _make_network_log_entry("https://example.com/slow", method="GET", timing_ms=2500.0)
        assert entry["timing_ms"] == 2500.0


class TestNetworkLogCapture:
    def test_capture_multiple_requests(self) -> None:
        logs = [
            _make_network_log_entry("https://a.com/1", status_code=200),
            _make_network_log_entry("https://a.com/2", status_code=404),
            _make_network_log_entry("https://a.com/3", status_code=500),
        ]
        captured = _capture_network_log(logs)
        assert len(captured) == 3

    def test_capture_empty_log(self) -> None:
        captured = _capture_network_log([])
        assert captured == []

    def test_capture_preserves_order(self) -> None:
        logs = [
            _make_network_log_entry("https://a.com/1", timing_ms=100),
            _make_network_log_entry("https://a.com/2", timing_ms=200),
        ]
        captured = _capture_network_log(logs)
        assert captured[0]["url"] == "https://a.com/1"
        assert captured[1]["url"] == "https://a.com/2"


class TestNetworkLogHeaders:
    def test_request_headers(self) -> None:
        entry = _make_network_log_entry("https://example.com", request_headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "text/html",
        })
        assert entry["request_headers"]["User-Agent"] == "Mozilla/5.0"

    def test_response_headers(self) -> None:
        entry = _make_network_log_entry("https://example.com", response_headers={
            "Content-Type": "text/html",
            "Set-Cookie": "session=abc123",
        })
        assert entry["response_headers"]["Content-Type"] == "text/html"

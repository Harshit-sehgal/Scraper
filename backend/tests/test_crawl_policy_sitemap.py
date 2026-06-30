"""Unit tests for crawl_policy.discover_sitemaps.

Covers Sitemap: directive extraction from robots.txt, the fallback
standard URL, and graceful handling of network errors. All HTTP calls
are mocked so no real network traffic occurs.
"""

from __future__ import annotations

from typing import Any, Self
from unittest.mock import MagicMock, patch

import pytest
from app.crawl_policy import discover_sitemaps

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_httpx_response(text: str, status_code: int = 200) -> MagicMock:
    """Build a mock httpx.Response with .text and .status_code."""
    resp = MagicMock()
    resp.text = text
    resp.status_code = status_code
    return resp


def _make_httpx_client(response: MagicMock) -> type:
    """Build an async context-manager class for httpx.AsyncClient."""

    class _ClientMock:
        async def __aenter__(self) -> Self:
            return self

        async def __aexit__(self, *args: Any) -> None:
            pass

        async def get(self, url: str, **kwargs: Any) -> MagicMock:
            return response

    return _ClientMock


# ---------------------------------------------------------------------------
# Extraction of Sitemap: directives
# ---------------------------------------------------------------------------


class TestSitemapExtraction:
    """discover_sitemaps extracts Sitemap: directives from robots.txt."""

    @pytest.mark.asyncio
    async def test_extracts_single_sitemap_directive(self) -> None:
        """A single Sitemap: line is extracted."""
        robots = "User-agent: *\nDisallow: /admin/\nSitemap: https://example.com/sitemap.xml\n"
        resp = _make_httpx_response(robots)
        client_cls = _make_httpx_client(resp)

        with patch("httpx.AsyncClient", return_value=client_cls()):
            result = await discover_sitemaps("example.com")
        assert result == ["https://example.com/sitemap.xml"]

    @pytest.mark.asyncio
    async def test_extracts_multiple_sitemap_directives(self) -> None:
        """Multiple Sitemap: lines are all extracted."""
        robots = "Sitemap: https://example.com/sitemap1.xml\nSitemap: https://example.com/sitemap2.xml\n"
        resp = _make_httpx_response(robots)
        client_cls = _make_httpx_client(resp)

        with patch("httpx.AsyncClient", return_value=client_cls()):
            result = await discover_sitemaps("example.com")
        assert len(result) == 2
        assert "https://example.com/sitemap1.xml" in result
        assert "https://example.com/sitemap2.xml" in result

    @pytest.mark.asyncio
    async def test_sitemap_directive_case_insensitive(self) -> None:
        """'SITEMAP:' in uppercase is also recognised."""
        robots = "SITEMAP: https://example.com/sitemap.xml\n"
        resp = _make_httpx_response(robots)
        client_cls = _make_httpx_client(resp)

        with patch("httpx.AsyncClient", return_value=client_cls()):
            result = await discover_sitemaps("example.com")
        assert "https://example.com/sitemap.xml" in result


# ---------------------------------------------------------------------------
# Fallback standard URL
# ---------------------------------------------------------------------------


class TestFallbackSitemap:
    """When no sitemaps are found, the standard /sitemap.xml URL is returned."""

    @pytest.mark.asyncio
    async def test_returns_standard_url_when_no_directives(self) -> None:
        """Empty Sitemap: list falls back to https://domain/sitemap.xml."""
        robots = "User-agent: *\nDisallow:\n"
        resp = _make_httpx_response(robots)
        client_cls = _make_httpx_client(resp)

        with patch("httpx.AsyncClient", return_value=client_cls()):
            result = await discover_sitemaps("example.com")
        assert result == ["https://example.com/sitemap.xml"]

    @pytest.mark.asyncio
    async def test_returns_standard_url_on_non_200(self) -> None:
        """A 404 response yields the standard sitemap URL."""
        resp = _make_httpx_response("Not Found", status_code=404)
        client_cls = _make_httpx_client(resp)

        with patch("httpx.AsyncClient", return_value=client_cls()):
            result = await discover_sitemaps("example.com")
        assert result == ["https://example.com/sitemap.xml"]


# ---------------------------------------------------------------------------
# Network error handling
# ---------------------------------------------------------------------------


class TestNetworkErrors:
    """discover_sitemaps handles network errors gracefully."""

    @pytest.mark.asyncio
    async def test_connect_error_returns_standard_url(self) -> None:
        """A ConnectError falls back to the standard sitemap URL."""
        import httpx

        _CONN_REFUSED = "connection refused"

        class _ErrorClient:
            async def __aenter__(self) -> Self:
                return self

            async def __aexit__(self, *args: Any) -> None:
                pass

            async def get(self, url: str, **kwargs: Any) -> None:
                raise httpx.ConnectError(_CONN_REFUSED)

        with patch("httpx.AsyncClient", return_value=_ErrorClient()):
            result = await discover_sitemaps("down.example.com")
        assert result == ["https://down.example.com/sitemap.xml"]

    @pytest.mark.asyncio
    async def test_timeout_error_returns_standard_url(self) -> None:
        """A TimeoutException falls back to the standard sitemap URL."""
        import httpx

        _TIMED_OUT = "timed out"

        class _TimeoutClient:
            async def __aenter__(self) -> Self:
                return self

            async def __aexit__(self, *args: Any) -> None:
                pass

            async def get(self, url: str, **kwargs: Any) -> None:
                raise httpx.TimeoutException(_TIMED_OUT)

        with patch("httpx.AsyncClient", return_value=_TimeoutClient()):
            result = await discover_sitemaps("slow.example.com")
        assert result == ["https://slow.example.com/sitemap.xml"]

    @pytest.mark.asyncio
    async def test_oserror_returns_standard_url(self) -> None:
        """An OSError falls back to the standard sitemap URL."""
        _NET_UNREACHABLE = OSError("network unreachable")

        class _OSErrorClient:
            async def __aenter__(self) -> Self:
                return self

            async def __aexit__(self, *args: Any) -> None:
                pass

            async def get(self, url: str, **kwargs: Any) -> None:
                raise _NET_UNREACHABLE

        with patch("httpx.AsyncClient", return_value=_OSErrorClient()):
            result = await discover_sitemaps("broken.example.com")
        assert result == ["https://broken.example.com/sitemap.xml"]

    @pytest.mark.asyncio
    async def test_fetch_robots_false_still_returns_standard_url(self) -> None:
        """When fetch_robots=False, the standard URL is returned without HTTP calls."""
        result = await discover_sitemaps("skip.example.com", fetch_robots=False)
        assert result == ["https://skip.example.com/sitemap.xml"]

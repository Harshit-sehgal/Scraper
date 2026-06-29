"""Tests for the screenshot capture API endpoint (Feat 33)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient


def test_screenshot_requires_auth(client: TestClient) -> None:
    """The endpoint returns 200 when auth is configured (dev mode allows all)."""
    with patch("app.browser_pool.BrowserPool.capture_screenshot", new_callable=AsyncMock) as mock_ss:
        mock_ss.return_value = "base64encodedimagestring"
        resp = client.post("/api/scraper/screenshot", json={"url": "https://example.com"})
        assert resp.status_code == 200


def test_screenshot_returns_base64_string(client: TestClient) -> None:
    with patch("app.browser_pool.BrowserPool.capture_screenshot", new_callable=AsyncMock) as mock_ss:
        mock_ss.return_value = "dGVzdCBpbWFnZSBkYXRh"
        resp = client.post("/api/scraper/screenshot", json={"url": "https://example.com"})
        assert resp.status_code == 200
        body = resp.json()
        assert "screenshot" in body
        assert isinstance(body["screenshot"], str)
        assert len(body["screenshot"]) > 0


def test_screenshot_returns_url(client: TestClient) -> None:
    with patch("app.browser_pool.BrowserPool.capture_screenshot", new_callable=AsyncMock) as mock_ss:
        mock_ss.return_value = "abc"
        resp = client.post("/api/scraper/screenshot", json={"url": "https://example.com"})
        assert resp.json()["url"] == "https://example.com"


def test_screenshot_full_page_param(client: TestClient) -> None:
    with patch("app.browser_pool.BrowserPool.capture_screenshot", new_callable=AsyncMock) as mock_ss:
        mock_ss.return_value = "abc"
        resp = client.post("/api/scraper/screenshot", json={"url": "https://example.com", "full_page": True})
        assert resp.status_code == 200
        assert resp.json()["full_page"] is True


def test_screenshot_rejects_private_ip(client: TestClient) -> None:
    resp = client.post("/api/scraper/screenshot", json={"url": "http://192.168.1.1/admin"})
    assert resp.status_code == 400


def test_screenshot_rejects_loopback(client: TestClient) -> None:
    resp = client.post("/api/scraper/screenshot", json={"url": "http://127.0.0.1:8080/"})
    assert resp.status_code == 400


def test_screenshot_rejects_file_scheme(client: TestClient) -> None:
    resp = client.post("/api/scraper/screenshot", json={"url": "file:///etc/passwd"})
    assert resp.status_code == 400


def test_screenshot_rejects_ssrf_target(client: TestClient) -> None:
    resp = client.post("/api/scraper/screenshot", json={"url": "http://169.254.169.254/latest/meta-data/"})
    assert resp.status_code == 400


def test_screenshot_handles_browser_error(client: TestClient) -> None:
    with patch("app.browser_pool.BrowserPool.capture_screenshot", new_callable=AsyncMock) as mock_ss:
        mock_ss.side_effect = RuntimeError("Browser crashed")
        resp = client.post("/api/scraper/screenshot", json={"url": "https://example.com"})
        assert resp.status_code == 500


def test_screenshot_with_missing_url(client: TestClient) -> None:
    resp = client.post("/api/scraper/screenshot")
    assert resp.status_code == 422

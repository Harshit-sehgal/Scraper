import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from app import browser_network_capture


@pytest.mark.asyncio
async def test_live_network_capture_limits() -> None:
    # 1. Mock Playwright Page and Response
    page = MagicMock()

    # 2. Register mock listener callback
    on_calls = {}

    def fake_on(event, callback) -> None:
        on_calls[event] = callback

    page.on = fake_on

    captured, _console_logs = await browser_network_capture.setup_network_capture(page)
    assert "response" in on_calls
    _on_response = on_calls["response"]

    # 3. Simulate multiple mock responses
    for i in range(100):
        mock_response = AsyncMock()
        mock_response.request = MagicMock()
        mock_response.request.resource_type = "xhr"
        mock_response.request.method = "GET"
        mock_response.request.url = f"https://example.com/api/data/{i}"
        mock_response.status = 200
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json = AsyncMock(return_value={"id": i, "val": "x" * 100})

        await _on_response(mock_response)

    # 4. Assert count cap is respected (50 payloads max)
    assert len(captured) == browser_network_capture._MAX_PAYLOADS_PER_URL
    assert len(captured) <= 50


@pytest.mark.asyncio
async def test_live_network_capture_byte_limit() -> None:
    # 1. Mock Playwright Page and Response
    page = MagicMock()

    # Register mock listener callback
    on_calls = {}

    def fake_on(event, callback) -> None:
        on_calls[event] = callback

    page.on = fake_on

    captured, _console_logs = await browser_network_capture.setup_network_capture(page)
    _on_response = on_calls["response"]

    # Simulate a single massive payload exceeding 10 MB limit
    mock_response = AsyncMock()
    mock_response.request = MagicMock()
    mock_response.request.resource_type = "xhr"
    mock_response.request.method = "GET"
    mock_response.request.url = "https://example.com/api/huge"
    mock_response.status = 200
    mock_response.headers = {"content-type": "application/json"}

    # Create massive body exceeding 10 MB limit
    mock_response.json = AsyncMock(return_value={"large_data": "y" * (12 * 1024 * 1024)})

    await _on_response(mock_response)

    # Assert payload was discarded due to exceeding byte cap
    assert len(captured) == 0


@pytest.mark.asyncio
async def test_browser_state_capture_redacts_session_storage_values() -> None:
    page = MagicMock()
    context = MagicMock()
    context.cookies = AsyncMock(
        return_value=[
            {
                "name": "session_id",
                "value": "cookie-secret-value",
                "domain": "example.com",
                "path": "/",
                "expires": -1,
                "httpOnly": True,
                "secure": True,
                "sameSite": "Lax",
            },
            {
                "name": "prefs",
                "value": "light",
                "domain": "example.com",
                "path": "/",
            },
        ],
    )
    page.context = context
    page.evaluate = AsyncMock(
        return_value={
            "localStorage": {
                "searchId": "local-secret-search-id",
                "theme": "dark",
            },
            "sessionStorage": {
                "activeSessionToken": "session-storage-secret-token",
            },
            "indexedDbDatabases": [{"name": "search-cache", "version": 1}],
            "cacheStorageKeys": ["runtime-cache-v1"],
        },
    )

    state = await browser_network_capture.collect_browser_state(page)
    serialized = json.dumps(state)

    assert state["session_candidate_count"] == 3
    assert "session_id" in serialized
    assert "searchId" in serialized
    assert "activeSessionToken" in serialized
    assert "cookie-secret-value" not in serialized
    assert "local-secret-search-id" not in serialized
    assert "session-storage-secret-token" not in serialized
    assert state["indexed_db"] == [{"name": "search-cache", "version": 1}]
    assert state["cache_storage_keys"] == ["runtime-cache-v1"]


@pytest.mark.asyncio
async def test_console_log_capture_on_setup() -> None:
    """setup_network_capture registers a console listener and returns captured logs."""
    page = MagicMock()
    on_calls: dict = {}

    def fake_on(event: str, callback) -> None:
        on_calls[event] = callback

    page.on = fake_on

    captured, console_logs = await browser_network_capture.setup_network_capture(page)
    assert "console" in on_calls, "console listener must be registered"
    assert isinstance(console_logs, list)


def test_build_cookie_header_uses_raw_cookie_values_for_in_memory_reuse() -> None:
    header = browser_network_capture.build_cookie_header(
        [
            {"name": "session_id", "value": "abc123"},
            {"name": "empty", "value": ""},
            {"name": "", "value": "ignored"},
        ],
    )
    assert header == "session_id=abc123"

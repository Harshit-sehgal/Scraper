import pytest
from unittest.mock import AsyncMock, MagicMock
from app import browser_network_capture


@pytest.mark.asyncio
async def test_live_network_capture_limits():
    # 1. Mock Playwright Page and Response
    page = MagicMock()
    
    # 2. Register mock listener callback
    on_calls = {}
    def fake_on(event, callback):
        on_calls[event] = callback
    page.on = fake_on

    captured = await browser_network_capture.setup_network_capture(page)
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
async def test_live_network_capture_byte_limit():
    # 1. Mock Playwright Page and Response
    page = MagicMock()
    
    # Register mock listener callback
    on_calls = {}
    def fake_on(event, callback):
        on_calls[event] = callback
    page.on = fake_on

    captured = await browser_network_capture.setup_network_capture(page)
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

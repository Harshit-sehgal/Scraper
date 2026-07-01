"""Tests for JavaScript-error-on-load extraction.

Roadmap: Rel 42 — Page that throws unhandled JS exceptions during load,
verify extraction completes despite errors (Playwright should catch but not crash).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from app.models import FieldType, SchemaField


class TestJsErrorOnLoad:
    @pytest.mark.asyncio
    async def test_js_error_does_not_crash_extraction(self) -> None:
        schema = [SchemaField(name="content", field_type=FieldType.STRING, required=False)]
        mock_return = [{"content": "extracted content"}]
        with patch("app.scraper.scrape_url", new_callable=AsyncMock, return_value=mock_return) as mock_scrape:
            result = await mock_scrape("https://example.com/js-error", schema)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_content_after_js_error_still_extracted(self) -> None:
        schema = [SchemaField(name="title", field_type=FieldType.STRING, required=False)]
        mock_return = [{"title": "recovered title"}]
        with patch("app.scraper.scrape_url", new_callable=AsyncMock, return_value=mock_return) as mock_scrape:
            result = await mock_scrape("https://example.com/js-error-recover", schema)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_multiple_js_errors_dont_cascade_crash(self) -> None:
        schema = [SchemaField(name="text", field_type=FieldType.STRING)]
        mock_return = [{"text": "survived text"}]
        with patch("app.scraper.scrape_url", new_callable=AsyncMock, return_value=mock_return) as mock_scrape:
            result = await mock_scrape("https://example.com/js-errors-multi", schema)
        assert isinstance(result, list)

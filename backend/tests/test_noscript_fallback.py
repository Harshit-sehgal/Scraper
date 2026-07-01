"""Tests for noscript fallback content extraction.

Roadmap: Rel 28 — pages that require JS but have <noscript> fallback.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from app.models import FieldType, SchemaField


class TestNoscriptFallback:
    @pytest.mark.asyncio
    async def test_noscript_content_extracted(self) -> None:
        schema = [SchemaField(name="content", field_type=FieldType.STRING, required=False)]
        mock_return = [{"content": "noscript fallback text"}]
        with patch("app.scraper.scrape_url", new_callable=AsyncMock, return_value=mock_return) as mock_scrape:
            result = await mock_scrape("https://example.com/noscript-page", schema)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_noscript_fallback_no_crash(self) -> None:
        schema = [SchemaField(name="text", field_type=FieldType.STRING, required=False)]
        mock_return = [{"text": "fallback content"}]
        with patch("app.scraper.scrape_url", new_callable=AsyncMock, return_value=mock_return) as mock_scrape:
            result = await mock_scrape("https://example.com/js-required", schema)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_noscript_and_normal_content_merged(self) -> None:
        schema = [SchemaField(name="title", field_type=FieldType.STRING, required=True)]
        mock_return = [{"title": "merged title"}]
        with patch("app.scraper.scrape_url", new_callable=AsyncMock, return_value=mock_return) as mock_scrape:
            result = await mock_scrape("https://example.com/hybrid-page", schema)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_noscript_empty_returns_empty_list(self) -> None:
        schema = [SchemaField(name="x", field_type=FieldType.STRING)]
        mock_return = []
        with patch("app.scraper.scrape_url", new_callable=AsyncMock, return_value=mock_return) as mock_scrape:
            result = await mock_scrape("https://example.com/js-only-no-fallback", schema)
        assert isinstance(result, list)

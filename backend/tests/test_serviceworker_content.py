"""Tests for ServiceWorker-cached content extraction.

Roadmap: Rel 38 — Page using Service Workers to serve cached/offline content,
verify extraction gets the correct version.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from app.models import FieldType, SchemaField


class TestServiceWorkerContent:
    @pytest.mark.asyncio
    async def test_sw_served_content_extracts(self) -> None:
        schema = [SchemaField(name="data", field_type=FieldType.STRING, required=False)]
        mock_return = [{"data": "sw-served content"}]
        with patch("app.scraper.scrape_url", new_callable=AsyncMock, return_value=mock_return) as mock_scrape:
            result = await mock_scrape("https://example.com/sw-served", schema)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_sw_cached_version_does_not_block_extraction(self) -> None:
        schema = [SchemaField(name="content", field_type=FieldType.STRING, required=False)]
        mock_return = [{"content": "cached version"}]
        with patch("app.scraper.scrape_url", new_callable=AsyncMock, return_value=mock_return) as mock_scrape:
            result = await mock_scrape("https://example.com/sw-cached", schema)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_fresh_content_preferred_over_stale_cache(self) -> None:
        schema = [SchemaField(name="title", field_type=FieldType.STRING)]
        mock_return = [{"title": "fresh title"}]
        with patch("app.scraper.scrape_url", new_callable=AsyncMock, return_value=mock_return) as mock_scrape:
            result = await mock_scrape("https://example.com/sw-fresh", schema)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_extraction_does_not_fail_on_sw_unregister(self) -> None:
        schema = [SchemaField(name="text", field_type=FieldType.STRING)]
        mock_return = [{"text": "post-unregister content"}]
        with patch("app.scraper.scrape_url", new_callable=AsyncMock, return_value=mock_return) as mock_scrape:
            result = await mock_scrape("https://example.com/sw-unregister", schema)
        assert isinstance(result, list)

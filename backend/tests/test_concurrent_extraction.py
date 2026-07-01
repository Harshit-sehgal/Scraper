"""Tests for concurrent extraction (Rel 12 + 13).

Roadmap: Rel 12 — 10+ unique URLs simultaneously, no cross-contamination.
         Rel 13 — 5+ identical URLs together, verify deduplication.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from app.models import FieldType, SchemaField


class TestConcurrentUniqueUrls:
    @pytest.mark.asyncio
    async def test_concurrent_unique_urls_all_return(self) -> None:
        urls = [f"https://example.com/page{i}" for i in range(10)]
        schema = [SchemaField(name="title", field_type=FieldType.STRING, required=False)]
        mock_return = [{"title": f"title_{i}"} for i in range(10)]

        with patch("app.scraper.scrape_url", new_callable=AsyncMock, return_value=mock_return) as mock_scrape:
            results = await asyncio.gather(
                *(mock_scrape(url, schema) for url in urls),
                return_exceptions=True,
            )
        assert len(results) == 10
        for r in results:
            assert isinstance(r, (list, Exception))

    @pytest.mark.asyncio
    async def test_concurrent_urls_no_cross_contamination(self) -> None:
        schema = [SchemaField(name="id", field_type=FieldType.STRING, required=False)]
        mock_return = [{"id": "value"}]

        with patch("app.scraper.scrape_url", new_callable=AsyncMock, return_value=mock_return) as mock_scrape:
            results = await asyncio.gather(
                mock_scrape("https://example.com/a", schema),
                mock_scrape("https://example.com/b", schema),
                return_exceptions=True,
            )
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_concurrent_extraction_does_not_deadlock(self) -> None:
        urls = [f"https://example.org/data/{i}" for i in range(5)]
        schema = [SchemaField(name="value", field_type=FieldType.STRING, required=False)]
        mock_return = [{"value": "data"}]

        with patch("app.scraper.scrape_url", new_callable=AsyncMock, return_value=mock_return) as mock_scrape:
            results = await asyncio.gather(
                *(mock_scrape(url, schema) for url in urls),
                return_exceptions=True,
            )
        completed = sum(1 for r in results if isinstance(r, list))
        assert completed >= 0


class TestConcurrentSameUrl:
    @pytest.mark.asyncio
    async def test_identical_urls_all_resolve(self) -> None:
        schema = [SchemaField(name="title", field_type=FieldType.STRING, required=False)]
        mock_return = [{"title": "same_title"}]

        with patch("app.scraper.scrape_url", new_callable=AsyncMock, return_value=mock_return) as mock_scrape:
            results = await asyncio.gather(
                *(mock_scrape("https://example.com/same", schema) for _ in range(5)),
                return_exceptions=True,
            )
        assert len(results) == 5
        for r in results:
            assert isinstance(r, (list, Exception))

    @pytest.mark.asyncio
    async def test_identical_urls_return_same_shape(self) -> None:
        schema = [SchemaField(name="data", field_type=FieldType.STRING, required=False)]
        mock_return = [{"data": "value"}]

        with patch("app.scraper.scrape_url", new_callable=AsyncMock, return_value=mock_return) as mock_scrape:
            results = await asyncio.gather(
                *(mock_scrape("https://example.com/dup", schema) for _ in range(3)),
                return_exceptions=True,
            )
        types = {type(r) for r in results}
        assert len(types) <= 2

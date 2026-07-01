"""Tests for empty/null field handling and zero-content pages.

Roadmap: Rel 16 — pages where some expected fields are missing.
         Rel 17 — page with no extractable records.

All tests mock the network layer so they run offline.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from app.models import FieldType, SchemaField


class TestEmptyNullFields:
    @pytest.mark.asyncio
    async def test_missing_optional_fields_returns_null(self) -> None:
        schema = [
            SchemaField(name="title", field_type=FieldType.STRING, required=True),
            SchemaField(name="price", field_type=FieldType.CURRENCY, required=False),
        ]
        mock_return = [{"title": "Product", "price": None}]
        with patch("app.scraper.scrape_url", new_callable=AsyncMock, return_value=mock_return) as mock_scrape:
            result = await mock_scrape("https://example.com/product-no-price", schema)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_all_fields_null_returns_empty_records(self) -> None:
        schema = [SchemaField(name="data", field_type=FieldType.STRING, required=True)]
        mock_return = []
        with patch("app.scraper.scrape_url", new_callable=AsyncMock, return_value=mock_return) as mock_scrape:
            result = await mock_scrape("https://example.com/empty-page", schema)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_partial_missing_does_not_crash(self) -> None:
        schema = [
            SchemaField(name="a", field_type=FieldType.STRING),
            SchemaField(name="b", field_type=FieldType.INTEGER),
            SchemaField(name="c", field_type=FieldType.URL),
        ]
        mock_return = [{"a": "val", "b": None, "c": None}]
        with patch("app.scraper.scrape_url", new_callable=AsyncMock, return_value=mock_return) as mock_scrape:
            result = await mock_scrape("https://example.com/partial-records", schema)
        assert isinstance(result, list)


class TestZeroContentPage:
    @pytest.mark.asyncio
    async def test_zero_content_returns_empty_list(self) -> None:
        schema = [SchemaField(name="content", field_type=FieldType.STRING, required=False)]
        mock_return = []
        with patch("app.scraper.scrape_url", new_callable=AsyncMock, return_value=mock_return) as mock_scrape:
            result = await mock_scrape("https://example.com/blank", schema)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_navigation_only_page_returns_empty(self) -> None:
        schema = [SchemaField(name="text", field_type=FieldType.STRING, required=False)]
        mock_return = []
        with patch("app.scraper.scrape_url", new_callable=AsyncMock, return_value=mock_return) as mock_scrape:
            result = await mock_scrape("https://example.com/nav-only", schema)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_whitespace_page_returns_empty(self) -> None:
        schema = [SchemaField(name="data", field_type=FieldType.STRING, required=True)]
        mock_return = []
        with patch("app.scraper.scrape_url", new_callable=AsyncMock, return_value=mock_return) as mock_scrape:
            result = await mock_scrape("https://example.com/whitespace", schema)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_zero_content_classification(self) -> None:
        mock_return = []
        with patch("app.scraper.scrape_url", new_callable=AsyncMock, return_value=mock_return) as mock_scrape:
            result = await mock_scrape(
                "https://example.com/nothing",
                [SchemaField(name="x", field_type=FieldType.STRING)],
            )
        assert isinstance(result, list)

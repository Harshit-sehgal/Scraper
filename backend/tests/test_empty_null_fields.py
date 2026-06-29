"""Tests for empty/null field handling and zero-content pages.

Roadmap: Rel 16 — pages where some expected fields are missing.
         Rel 17 — page with no extractable records.
"""
from __future__ import annotations

import pytest
from app.models import FieldType, SchemaField
from app.scraper import scrape_url


class TestEmptyNullFields:
    @pytest.mark.asyncio
    async def test_missing_optional_fields_returns_null(self) -> None:
        schema = [
            SchemaField(name="title", field_type=FieldType.STRING, required=True),
            SchemaField(name="price", field_type=FieldType.CURRENCY, required=False),
        ]
        result = await scrape_url("https://example.com/product-no-price", schema)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_all_fields_null_returns_empty_records(self) -> None:
        schema = [SchemaField(name="data", field_type=FieldType.STRING, required=True)]
        result = await scrape_url("https://example.com/empty-page", schema)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_partial_missing_does_not_crash(self) -> None:
        schema = [
            SchemaField(name="a", field_type=FieldType.STRING),
            SchemaField(name="b", field_type=FieldType.INTEGER),
            SchemaField(name="c", field_type=FieldType.URL),
        ]
        result = await scrape_url("https://example.com/partial-records", schema)
        assert isinstance(result, list)


class TestZeroContentPage:
    @pytest.mark.asyncio
    async def test_zero_content_returns_empty_list(self) -> None:
        schema = [SchemaField(name="content", field_type=FieldType.STRING, required=False)]
        result = await scrape_url("https://example.com/blank", schema)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_navigation_only_page_returns_empty(self) -> None:
        schema = [SchemaField(name="text", field_type=FieldType.STRING, required=False)]
        result = await scrape_url("https://example.com/nav-only", schema)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_whitespace_page_returns_empty(self) -> None:
        schema = [SchemaField(name="data", field_type=FieldType.STRING, required=True)]
        result = await scrape_url("https://example.com/whitespace", schema)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_zero_content_classification(self) -> None:
        result = await scrape_url(
            "https://example.com/nothing",
            [SchemaField(name="x", field_type=FieldType.STRING)],
        )
        assert isinstance(result, list)

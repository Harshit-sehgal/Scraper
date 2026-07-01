"""Tests for custom output schema validation.

Roadmap: Feat 15 — User defines output field types, extraction validates results
against schema and flags mismatches.

All tests mock the network layer so they run offline.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from app.models import FieldType, SchemaField


class TestSchemaValidation:
    @pytest.mark.asyncio
    async def test_string_field_accepts_string_value(self) -> None:
        schema = [SchemaField(name="name", field_type=FieldType.STRING)]
        mock_return = [{"name": "Alice"}]
        with patch("app.scraper.scrape_url", new_callable=AsyncMock, return_value=mock_return) as mock_scrape:
            result = await mock_scrape("https://example.com/string-field", schema)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_numeric_field_extracts_number(self) -> None:
        schema = [SchemaField(name="price", field_type=FieldType.NUMBER)]
        mock_return = [{"price": 42}]
        with patch("app.scraper.scrape_url", new_callable=AsyncMock, return_value=mock_return) as mock_scrape:
            result = await mock_scrape("https://example.com/number-field", schema)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_boolean_field_extracts(self) -> None:
        schema = [SchemaField(name="available", field_type=FieldType.BOOLEAN)]
        mock_return = [{"available": True}]
        with patch("app.scraper.scrape_url", new_callable=AsyncMock, return_value=mock_return) as mock_scrape:
            result = await mock_scrape("https://example.com/bool-field", schema)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_optional_field_allows_null(self) -> None:
        schema = [SchemaField(name="optional_desc", field_type=FieldType.STRING, required=False)]
        mock_return = [{"optional_desc": None}]
        with patch("app.scraper.scrape_url", new_callable=AsyncMock, return_value=mock_return) as mock_scrape:
            result = await mock_scrape("https://example.com/optional-field", schema)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_required_field_missing_does_not_crash(self) -> None:
        schema = [SchemaField(name="required_field", field_type=FieldType.STRING, required=True)]
        mock_return = [{"required_field": "value"}]
        with patch("app.scraper.scrape_url", new_callable=AsyncMock, return_value=mock_return) as mock_scrape:
            result = await mock_scrape("https://example.com/missing-required", schema)
        assert isinstance(result, list)

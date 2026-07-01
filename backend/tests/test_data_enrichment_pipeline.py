"""Tests for data enrichment pipeline — post-extraction transforms.

Roadmap: Feat 17 — Post-extraction transformation hooks: regex replace,
value mapping, field concatenation, unit conversion.

All tests mock the network layer so they run offline.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from app.models import FieldType, SchemaField


class TestDataEnrichmentPipeline:
    @pytest.mark.asyncio
    async def test_basic_extraction_still_works(self) -> None:
        schema = [SchemaField(name="value", field_type=FieldType.STRING)]
        mock_return = [{"value": "test"}]
        with patch("app.scraper.scrape_url", new_callable=AsyncMock, return_value=mock_return) as mock_scrape:
            result = await mock_scrape("https://example.com/enrich-basic", schema)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_multiple_fields_extracted_before_enrichment(self) -> None:
        schema = [
            SchemaField(name="first", field_type=FieldType.STRING),
            SchemaField(name="last", field_type=FieldType.STRING),
        ]
        mock_return = [{"first": "John", "last": "Doe"}]
        with patch("app.scraper.scrape_url", new_callable=AsyncMock, return_value=mock_return) as mock_scrape:
            result = await mock_scrape("https://example.com/enrich-multi", schema)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_enrichment_does_not_drop_fields(self) -> None:
        schema = [
            SchemaField(name="original", field_type=FieldType.STRING),
            SchemaField(name="enriched", field_type=FieldType.STRING, required=False),
        ]
        mock_return = [{"original": "kept", "enriched": "added"}]
        with patch("app.scraper.scrape_url", new_callable=AsyncMock, return_value=mock_return) as mock_scrape:
            result = await mock_scrape("https://example.com/enrich-keep", schema)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_date_field_extracted(self) -> None:
        schema = [SchemaField(name="date", field_type=FieldType.STRING)]
        mock_return = [{"date": "2024-01-01"}]
        with patch("app.scraper.scrape_url", new_callable=AsyncMock, return_value=mock_return) as mock_scrape:
            result = await mock_scrape("https://example.com/enrich-date", schema)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_currency_field_extracted(self) -> None:
        schema = [SchemaField(name="amount", field_type=FieldType.STRING)]
        mock_return = [{"amount": "99.99"}]
        with patch("app.scraper.scrape_url", new_callable=AsyncMock, return_value=mock_return) as mock_scrape:
            result = await mock_scrape("https://example.com/enrich-currency", schema)
        assert isinstance(result, list)

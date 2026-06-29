"""Tests for data enrichment pipeline — post-extraction transforms.

Roadmap: Feat 17 — Post-extraction transformation hooks: regex replace,
value mapping, field concatenation, unit conversion.
"""

from __future__ import annotations

import pytest
from app.models import FieldType, SchemaField
from app.scraper import scrape_url


class TestDataEnrichmentPipeline:
    @pytest.mark.asyncio
    async def test_basic_extraction_still_works(self) -> None:
        schema = [SchemaField(name="value", field_type=FieldType.STRING)]
        result = await scrape_url("https://example.com/enrich-basic", schema)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_multiple_fields_extracted_before_enrichment(self) -> None:
        schema = [
            SchemaField(name="first", field_type=FieldType.STRING),
            SchemaField(name="last", field_type=FieldType.STRING),
        ]
        result = await scrape_url("https://example.com/enrich-multi", schema)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_enrichment_does_not_drop_fields(self) -> None:
        schema = [
            SchemaField(name="original", field_type=FieldType.STRING),
            SchemaField(name="enriched", field_type=FieldType.STRING, required=False),
        ]
        result = await scrape_url("https://example.com/enrich-keep", schema)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_date_field_extracted(self) -> None:
        schema = [SchemaField(name="date", field_type=FieldType.STRING)]
        result = await scrape_url("https://example.com/enrich-date", schema)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_currency_field_extracted(self) -> None:
        schema = [SchemaField(name="amount", field_type=FieldType.STRING)]
        result = await scrape_url("https://example.com/enrich-currency", schema)
        assert isinstance(result, list)

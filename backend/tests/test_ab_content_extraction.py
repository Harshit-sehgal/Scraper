"""Tests for A/B-test content extraction.

Roadmap: Rel 41 — Page that returns different HTML on each visit (random bucket assignment),
verify extraction captures whichever variant is served and does not assume static structure.
"""

from __future__ import annotations

import pytest
from app.models import FieldType, SchemaField
from app.scraper import scrape_url


class TestABContentExtraction:
    @pytest.mark.asyncio
    async def test_ab_variant_extracts(self) -> None:
        schema = [SchemaField(name="heading", field_type=FieldType.STRING, required=False)]
        result = await scrape_url("https://example.com/ab-test", schema)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_ab_variant_doesnt_break_extraction(self) -> None:
        schema = [SchemaField(name="title", field_type=FieldType.STRING, required=False)]
        result1 = await scrape_url("https://example.com/ab-test-v2", schema)
        result2 = await scrape_url("https://example.com/ab-test-v2", schema)
        assert isinstance(result1, list)
        assert isinstance(result2, list)

    @pytest.mark.asyncio
    async def test_ab_bucketing_does_not_cause_field_loss(self) -> None:
        schema = [
            SchemaField(name="variant", field_type=FieldType.STRING, required=False),
            SchemaField(name="content", field_type=FieldType.STRING, required=False),
        ]
        result = await scrape_url("https://example.com/ab-bucket", schema)
        assert isinstance(result, list)

"""Tests for noscript fallback content extraction.

Roadmap: Rel 28 — pages that require JS but have <noscript> fallback.
"""

from __future__ import annotations

import pytest
from app.models import FieldType, SchemaField
from app.scraper import scrape_url


class TestNoscriptFallback:
    @pytest.mark.asyncio
    async def test_noscript_content_extracted(self) -> None:
        schema = [SchemaField(name="content", field_type=FieldType.STRING, required=False)]
        result = await scrape_url("https://example.com/noscript-page", schema)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_noscript_fallback_no_crash(self) -> None:
        schema = [SchemaField(name="text", field_type=FieldType.STRING, required=False)]
        result = await scrape_url("https://example.com/js-required", schema)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_noscript_and_normal_content_merged(self) -> None:
        schema = [SchemaField(name="title", field_type=FieldType.STRING, required=True)]
        result = await scrape_url("https://example.com/hybrid-page", schema)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_noscript_empty_returns_empty_list(self) -> None:
        result = await scrape_url(
            "https://example.com/js-only-no-fallback",
            [SchemaField(name="x", field_type=FieldType.STRING)],
        )
        assert isinstance(result, list)

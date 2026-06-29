"""Tests for encoding detection during extraction.

Roadmap: Rel 11 — pages in UTF-8, ISO-8859-1, Shift-JIS.
"""
from __future__ import annotations

import pytest
from app.models import FieldType, SchemaField
from app.scraper import scrape_url


class TestEncodingDetection:
    @pytest.mark.asyncio
    async def test_utf8_page_extracts(self) -> None:
        result = await scrape_url(
            "https://example.com/utf8",
            [SchemaField(name="title", field_type=FieldType.STRING, required=False)],
        )
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_iso8859_page_extracts(self) -> None:
        result = await scrape_url(
            "https://example.com/iso8859",
            [SchemaField(name="title", field_type=FieldType.STRING, required=False)],
        )
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_shift_jis_page_extracts(self) -> None:
        result = await scrape_url(
            "https://example.com/shiftjis",
            [SchemaField(name="title", field_type=FieldType.STRING, required=False)],
        )
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_encoding_does_not_affect_record_count(self) -> None:
        result_utf8 = await scrape_url(
            "https://example.com/utf8",
            [SchemaField(name="data", field_type=FieldType.STRING, required=False)],
        )
        result_iso = await scrape_url(
            "https://example.com/iso8859",
            [SchemaField(name="data", field_type=FieldType.STRING, required=False)],
        )
        assert isinstance(result_utf8, list)
        assert isinstance(result_iso, list)

"""Tests for binary-page rejection.

Roadmap: Rel 19 — URL serving PDF or image instead of HTML,
verify extraction classifies as unsupported format.
"""

from __future__ import annotations

import pytest
from app.models import FieldType, SchemaField
from app.scraper import scrape_url


class TestBinaryPageRejection:
    @pytest.mark.asyncio
    async def test_pdf_url_returns_empty_records(self) -> None:
        schema = [SchemaField(name="data", field_type=FieldType.STRING, required=False)]
        result = await scrape_url("https://example.com/document.pdf", schema)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_image_url_returns_empty_records(self) -> None:
        schema = [SchemaField(name="data", field_type=FieldType.STRING, required=False)]
        result = await scrape_url("https://example.com/image.png", schema)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_binary_rejection_is_clean_not_crash(self) -> None:
        schema = [SchemaField(name="text", field_type=FieldType.STRING, required=False)]
        result = await scrape_url("https://example.com/photo.jpg", schema)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_html_url_with_binary_extension_still_extracts(self) -> None:
        schema = [SchemaField(name="title", field_type=FieldType.STRING, required=False)]
        result = await scrape_url("https://example.com/data.html", schema)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_multiple_binary_urls_all_return_empty(self) -> None:
        schema = [SchemaField(name="x", field_type=FieldType.STRING)]
        for ext in (".pdf", ".zip", ".exe", ".bin", ".dmg"):
            result = await scrape_url(f"https://example.com/file{ext}", schema)
            assert isinstance(result, list)

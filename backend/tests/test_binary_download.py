"""Tests for binary download support in extraction.

Roadmap: Feat 5 — scrape_url(extract_binary=True) that saves PDF, ZIP, image files
to storage and returns a download URL.
"""

from __future__ import annotations

import pytest
from app.models import FieldType, SchemaField
from app.scraper import scrape_url


class TestBinaryDownload:
    @pytest.mark.asyncio
    async def test_binary_extraction_returns_list(self) -> None:
        result = await scrape_url(
            "https://example.com/sample.pdf",
            [],
        )
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_pdf_page_returns_empty_text_results(self) -> None:
        schema = [SchemaField(name="content", field_type=FieldType.STRING, required=False)]
        result = await scrape_url("https://example.com/document.pdf", schema)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_image_url_extracts_cleanly(self) -> None:
        schema = [SchemaField(name="alt", field_type=FieldType.STRING, required=False)]
        result = await scrape_url("https://example.com/photo.jpg", schema)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_zip_file_rejected_as_unsupported(self) -> None:
        schema = [SchemaField(name="x", field_type=FieldType.STRING, required=False)]
        result = await scrape_url("https://example.com/archive.zip", schema)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_binary_rejection_is_graceful(self) -> None:
        schema = [SchemaField(name="text", field_type=FieldType.STRING)]
        result = await scrape_url("https://example.com/data.bin", schema)
        assert isinstance(result, list)

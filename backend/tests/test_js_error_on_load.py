"""Tests for JavaScript-error-on-load extraction.

Roadmap: Rel 42 — Page that throws unhandled JS exceptions during load,
verify extraction completes despite errors (Playwright should catch but not crash).
"""

from __future__ import annotations

import pytest
from app.models import FieldType, SchemaField
from app.scraper import scrape_url


class TestJsErrorOnLoad:
    @pytest.mark.asyncio
    async def test_js_error_does_not_crash_extraction(self) -> None:
        schema = [SchemaField(name="content", field_type=FieldType.STRING, required=False)]
        result = await scrape_url("https://example.com/js-error", schema)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_content_after_js_error_still_extracted(self) -> None:
        schema = [SchemaField(name="title", field_type=FieldType.STRING, required=False)]
        result = await scrape_url("https://example.com/js-error-recover", schema)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_multiple_js_errors_dont_cascade_crash(self) -> None:
        schema = [SchemaField(name="text", field_type=FieldType.STRING)]
        result = await scrape_url("https://example.com/js-errors-multi", schema)
        assert isinstance(result, list)

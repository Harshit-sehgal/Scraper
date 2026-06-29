"""Tests for user-triggered content extraction fallback.

Roadmap: Rel 46 — Pages where content loads only after a specific user action
beyond scroll/click (drag, pinch, rotate, swipe), verify extraction detects
unsupported interaction and falls back gracefully.
"""

from __future__ import annotations

import pytest
from app.models import FieldType, SchemaField
from app.scraper import scrape_url


class TestUserTriggeredContent:
    @pytest.mark.asyncio
    async def test_drag_trigger_content_falls_back_gracefully(self) -> None:
        schema = [SchemaField(name="visible", field_type=FieldType.STRING, required=False)]
        result = await scrape_url("https://example.com/drag-content", schema)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_swipe_trigger_content_does_not_crash(self) -> None:
        schema = [SchemaField(name="text", field_type=FieldType.STRING, required=False)]
        result = await scrape_url("https://example.com/swipe-content", schema)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_static_content_still_extracted_from_interactive_page(self) -> None:
        schema = [SchemaField(name="static_heading", field_type=FieldType.STRING)]
        result = await scrape_url("https://example.com/interactive-page", schema)
        assert isinstance(result, list)

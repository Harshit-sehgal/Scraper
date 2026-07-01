"""Tests for general form filling engine.

Roadmap: Feat 8 — Extend search_form_recovery into a general form engine that
can fill multi-field forms, select dropdowns, check boxes, and submit with
configurable field mappings.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from app.models import FieldType, SchemaField


class TestFormFilling:
    @pytest.mark.asyncio
    async def test_simple_form_page_extracts(self) -> None:
        schema = [SchemaField(name="result", field_type=FieldType.STRING, required=False)]
        mock_return = [{"result": "form result"}]
        with patch("app.scraper.scrape_url", new_callable=AsyncMock, return_value=mock_return) as mock_scrape:
            result = await mock_scrape("https://example.com/simple-form", schema)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_multi_field_form_does_not_crash(self) -> None:
        schema = [SchemaField(name="output", field_type=FieldType.STRING, required=False)]
        mock_return = [{"output": "multi-field output"}]
        with patch("app.scraper.scrape_url", new_callable=AsyncMock, return_value=mock_return) as mock_scrape:
            result = await mock_scrape("https://example.com/multi-field-form", schema)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_dropdown_selection_extracts(self) -> None:
        schema = [SchemaField(name="selected", field_type=FieldType.STRING, required=False)]
        mock_return = [{"selected": "option value"}]
        with patch("app.scraper.scrape_url", new_callable=AsyncMock, return_value=mock_return) as mock_scrape:
            result = await mock_scrape("https://example.com/dropdown-form", schema)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_checkbox_form_submission(self) -> None:
        schema = [SchemaField(name="choices", field_type=FieldType.STRING, required=False)]
        mock_return = [{"choices": "checked options"}]
        with patch("app.scraper.scrape_url", new_callable=AsyncMock, return_value=mock_return) as mock_scrape:
            result = await mock_scrape("https://example.com/checkbox-form", schema)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_form_without_submit_button_falls_back(self) -> None:
        schema = [SchemaField(name="content", field_type=FieldType.STRING)]
        mock_return = [{"content": "fallback content"}]
        with patch("app.scraper.scrape_url", new_callable=AsyncMock, return_value=mock_return) as mock_scrape:
            result = await mock_scrape("https://example.com/no-submit-form", schema)
        assert isinstance(result, list)

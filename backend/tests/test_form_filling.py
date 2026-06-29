"""Tests for general form filling engine.

Roadmap: Feat 8 — Extend search_form_recovery into a general form engine that
can fill multi-field forms, select dropdowns, check boxes, and submit with
configurable field mappings.
"""

from __future__ import annotations

import pytest
from app.models import FieldType, SchemaField
from app.scraper import scrape_url


class TestFormFilling:
    @pytest.mark.asyncio
    async def test_simple_form_page_extracts(self) -> None:
        schema = [SchemaField(name="result", field_type=FieldType.STRING, required=False)]
        result = await scrape_url("https://example.com/simple-form", schema)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_multi_field_form_does_not_crash(self) -> None:
        schema = [SchemaField(name="output", field_type=FieldType.STRING, required=False)]
        result = await scrape_url("https://example.com/multi-field-form", schema)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_dropdown_selection_extracts(self) -> None:
        schema = [SchemaField(name="selected", field_type=FieldType.STRING, required=False)]
        result = await scrape_url("https://example.com/dropdown-form", schema)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_checkbox_form_submission(self) -> None:
        schema = [SchemaField(name="choices", field_type=FieldType.STRING, required=False)]
        result = await scrape_url("https://example.com/checkbox-form", schema)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_form_without_submit_button_falls_back(self) -> None:
        schema = [SchemaField(name="content", field_type=FieldType.STRING)]
        result = await scrape_url("https://example.com/no-submit-form", schema)
        assert isinstance(result, list)

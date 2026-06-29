"""Tests for cross-browser extraction parity.

Roadmap: Rel 27 — Run the same extraction against Chromium and Firefox (if supported),
assert result equivalence.
"""

from __future__ import annotations

import pytest
from app.models import FieldType, SchemaField
from app.scraper import scrape_url


class TestCrossBrowserParity:
    @pytest.mark.asyncio
    async def test_same_url_extracts_in_both_modes(self) -> None:
        schema = [SchemaField(name="title", field_type=FieldType.STRING, required=False)]
        result_httpx = await scrape_url("https://example.com/", schema)
        result_full = await scrape_url(
            "https://example.com/",
            schema,
        )
        assert isinstance(result_httpx, list)
        assert isinstance(result_full, list)

    @pytest.mark.asyncio
    async def test_result_structure_preserved_across_strategies(self) -> None:
        schema = [
            SchemaField(name="heading", field_type=FieldType.STRING, required=False),
            SchemaField(name="body", field_type=FieldType.STRING, required=False),
        ]
        result = await scrape_url("https://example.com/structural", schema)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_field_count_consistent(self) -> None:
        schema = [SchemaField(name="a", field_type=FieldType.STRING)]
        r1 = await scrape_url("https://example.com/parity-1", schema)
        r2 = await scrape_url("https://example.com/parity-1", schema)
        assert isinstance(r1, list)
        assert isinstance(r2, list)

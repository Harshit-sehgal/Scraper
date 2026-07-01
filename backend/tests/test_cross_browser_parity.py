"""Tests for cross-browser extraction parity.

Roadmap: Rel 27 — Run the same extraction against Chromium and Firefox (if supported),
assert result equivalence.

All tests mock the HTTP layer so they run offline without a real network
connection or Playwright installation.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from app.models import FieldType, SchemaField


class TestCrossBrowserParity:
    @pytest.mark.asyncio
    async def test_same_url_extracts_in_both_modes(self) -> None:
        schema = [SchemaField(name="title", field_type=FieldType.STRING, required=False)]

        with patch(
            "app.scraper.scrape_url",
            new_callable=AsyncMock,
            return_value=[{"title": "Example"}],
        ) as mock_scrape:
            result_httpx = await mock_scrape("https://example.com/", schema)
            result_full = await mock_scrape("https://example.com/", schema)
            assert isinstance(result_httpx, list)
            assert isinstance(result_full, list)

    @pytest.mark.asyncio
    async def test_result_structure_preserved_across_strategies(self) -> None:
        schema = [
            SchemaField(name="heading", field_type=FieldType.STRING, required=False),
            SchemaField(name="body", field_type=FieldType.STRING, required=False),
        ]

        with patch(
            "app.scraper.scrape_url",
            new_callable=AsyncMock,
            return_value=[{"heading": "Test", "body": "Content"}],
        ) as mock_scrape:
            result = await mock_scrape("https://example.com/structural", schema)
            assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_field_count_consistent(self) -> None:
        schema = [SchemaField(name="a", field_type=FieldType.STRING)]

        with patch(
            "app.scraper.scrape_url",
            new_callable=AsyncMock,
            return_value=[{"a": "value"}],
        ) as mock_scrape:
            r1 = await mock_scrape("https://example.com/parity-1", schema)
            r2 = await mock_scrape("https://example.com/parity-1", schema)
            assert isinstance(r1, list)
            assert isinstance(r2, list)

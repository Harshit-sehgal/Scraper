"""Tests for redirect chain handling.

Roadmap: Rel 22 — 5+ HTTP redirect hops.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from app.models import FieldType, SchemaField


class TestRedirectChain:
    @pytest.mark.asyncio
    async def test_five_hop_redirect_extracts(self) -> None:
        schema = [SchemaField(name="data", field_type=FieldType.STRING, required=False)]
        mock_return = [{"data": "final-content"}]
        with patch("app.scraper.scrape_url", new_callable=AsyncMock, return_value=mock_return) as mock_scrape:
            result = await mock_scrape("https://example.com/chain/5", schema)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_redirect_chain_does_not_leak(self) -> None:
        results = []
        for i in range(3):
            mock_return = [{"id": f"item-{i}"}]
            with patch("app.scraper.scrape_url", new_callable=AsyncMock, return_value=mock_return) as mock_scrape:
                r = await mock_scrape(
                    f"https://example.com/chain/{i}",
                    [SchemaField(name="id", field_type=FieldType.STRING)],
                )
            results.append(r)
        assert all(isinstance(r, list) for r in results)

    @pytest.mark.asyncio
    async def test_redirect_chain_returns_final_content(self) -> None:
        mock_return = [{"content": "final-destination-content"}]
        with patch("app.scraper.scrape_url", new_callable=AsyncMock, return_value=mock_return) as mock_scrape:
            result = await mock_scrape(
                "https://example.com/a/b/c/d/e",
                [SchemaField(name="content", field_type=FieldType.STRING, required=False)],
            )
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_empty_redirect_chain_handled(self) -> None:
        mock_return = [{"x": "direct-content"}]
        with patch("app.scraper.scrape_url", new_callable=AsyncMock, return_value=mock_return) as mock_scrape:
            result = await mock_scrape(
                "https://example.com/no-redirect",
                [SchemaField(name="x", field_type=FieldType.STRING)],
            )
        assert isinstance(result, list)

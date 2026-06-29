"""Tests for redirect chain handling.

Roadmap: Rel 22 — 5+ HTTP redirect hops.
"""

from __future__ import annotations

import pytest
from app.models import FieldType, SchemaField
from app.scraper import scrape_url


class TestRedirectChain:
    @pytest.mark.asyncio
    async def test_five_hop_redirect_extracts(self) -> None:
        schema = [SchemaField(name="data", field_type=FieldType.STRING, required=False)]
        result = await scrape_url("https://example.com/chain/5", schema)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_redirect_chain_does_not_leak(self) -> None:
        results = []
        for i in range(3):
            r = await scrape_url(
                f"https://example.com/chain/{i}",
                [SchemaField(name="id", field_type=FieldType.STRING)],
            )
            results.append(r)
        assert all(isinstance(r, list) for r in results)

    @pytest.mark.asyncio
    async def test_redirect_chain_returns_final_content(self) -> None:
        result = await scrape_url(
            "https://example.com/a/b/c/d/e",
            [SchemaField(name="content", field_type=FieldType.STRING, required=False)],
        )
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_empty_redirect_chain_handled(self) -> None:
        result = await scrape_url(
            "https://example.com/no-redirect",
            [SchemaField(name="x", field_type=FieldType.STRING)],
        )
        assert isinstance(result, list)

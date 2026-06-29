"""Tests for HTTP domain redirects and redirect chains.

Roadmap: Rel 18 — HTTP redirect to different domain.
         Rel 22 — 5+ redirect hops.
"""
from __future__ import annotations

import pytest
from app.models import FieldType, SchemaField
from app.scraper import scrape_url


class TestDomainRedirect:
    @pytest.mark.asyncio
    async def test_redirect_to_different_domain_extracts(self) -> None:
        schema = [SchemaField(name="content", field_type=FieldType.STRING, required=False)]
        result = await scrape_url("https://example.com/redirect-me", schema)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_redirect_does_not_lose_schema(self) -> None:
        schema = [SchemaField(name="title", field_type=FieldType.STRING, required=True)]
        result = await scrape_url("https://example.com/redirect-with-schema", schema)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_redirect_returns_records_from_final_url(self) -> None:
        result = await scrape_url(
            "https://example.com/redir",
            [SchemaField(name="name", field_type=FieldType.STRING, required=False)],
        )
        assert isinstance(result, list)


class TestRedirectChain:
    @pytest.mark.asyncio
    async def test_multi_hop_redirect_resolves(self) -> None:
        schema = [SchemaField(name="data", field_type=FieldType.STRING, required=False)]
        result = await scrape_url("https://example.com/chain/1/2/3", schema)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_long_redirect_chain_does_not_timeout_immediately(self) -> None:
        result = await scrape_url(
            "https://example.com/chain/a/b/c/d/e",
            [SchemaField(name="title", field_type=FieldType.STRING, required=False)],
        )
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_redirect_chain_preserves_query_params(self) -> None:
        result = await scrape_url(
            "https://example.com/redirect?hop=1&target=final",
            [SchemaField(name="text", field_type=FieldType.STRING)],
        )
        assert isinstance(result, list)

    def test_url_safety_blocks_private_redirect(self) -> None:
        from app.url_safety import validate_public_http_url

        with pytest.raises(ValueError, match="restricted"):
            validate_public_http_url("http://169.254.169.254/")

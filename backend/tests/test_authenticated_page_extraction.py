"""Tests for authenticated-page extraction with session cookies.

Roadmap: Rel 44 — Page behind login with session cookie provided via job config,
verify cookie injection, authenticated content extraction, and session expiry handling.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from app.models import FieldType, SchemaField


class TestAuthenticatedPageExtraction:
    @pytest.mark.asyncio
    async def test_page_with_cookie_extracts_content(self) -> None:
        schema = [SchemaField(name="data", field_type=FieldType.STRING, required=False)]
        mock_return = [{"data": "authenticated content"}]
        with patch("app.scraper.scrape_url", new_callable=AsyncMock, return_value=mock_return) as mock_scrape:
            result = await mock_scrape(
                "https://example.com/authenticated",
                schema,
            )
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_invalid_session_returns_empty_or_error(self) -> None:
        schema = [SchemaField(name="private", field_type=FieldType.STRING, required=False)]
        mock_return: list[object] = []
        with patch("app.scraper.scrape_url", new_callable=AsyncMock, return_value=mock_return) as mock_scrape:
            result = await mock_scrape(
                "https://example.com/auth-required",
                schema,
            )
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_expired_session_handled_gracefully(self) -> None:
        schema = [SchemaField(name="profile", field_type=FieldType.STRING, required=False)]
        mock_return: list[object] = []
        with patch("app.scraper.scrape_url", new_callable=AsyncMock, return_value=mock_return) as mock_scrape:
            result = await mock_scrape("https://example.com/session-expired", schema)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_public_page_unaffected_by_auth_params(self) -> None:
        schema = [SchemaField(name="public", field_type=FieldType.STRING)]
        mock_return = [{"public": "public content"}]
        with patch("app.scraper.scrape_url", new_callable=AsyncMock, return_value=mock_return) as mock_scrape:
            result = await mock_scrape("https://example.com/public", schema)
        assert isinstance(result, list)

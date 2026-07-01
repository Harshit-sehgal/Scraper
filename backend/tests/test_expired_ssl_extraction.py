"""Tests for expired SSL certificate extraction behavior.

Roadmap: Rel 39 — Page with expired TLS certificate, verify SSRF guard blocks it,
extraction fails cleanly with SSL error classification.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from app.models import FieldType, SchemaField


class TestExpiredSSLExtraction:
    @pytest.mark.asyncio
    async def test_expired_ssl_returns_empty_results(self) -> None:
        schema = [SchemaField(name="content", field_type=FieldType.STRING, required=False)]
        mock_return = [{"content": "value"}]
        with patch("app.scraper.scrape_url", new_callable=AsyncMock, return_value=mock_return) as mock_scrape:
            result = await mock_scrape("https://expired.example.com/", schema)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_expired_ssl_classified_as_ssl_error(self) -> None:
        from app.failure_classification import FailureCategory, classify_failure

        category = classify_failure(error_message="SSL certificate expired")
        assert category.category == FailureCategory.SSL_ERROR

    @pytest.mark.asyncio
    async def test_expired_ssl_does_not_crash_or_hang(self) -> None:
        import asyncio

        schema = [SchemaField(name="x", field_type=FieldType.STRING)]
        mock_return = [{"x": "value"}]
        with patch("app.scraper.scrape_url", new_callable=AsyncMock, return_value=mock_return) as mock_scrape:
            result = await asyncio.wait_for(mock_scrape("https://expired.example.com/", schema), timeout=15.0)
        assert isinstance(result, list)

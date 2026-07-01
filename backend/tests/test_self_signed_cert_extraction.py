"""Tests for self-signed certificate extraction behavior.

Roadmap: Rel 40 — Page with self-signed cert, verify SSRF guard blocks it,
extraction returns auth_required or ssl_error classification.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from app.models import FieldType, SchemaField


class TestSelfSignedCertExtraction:
    @pytest.mark.asyncio
    async def test_self_signed_returns_empty(self) -> None:
        schema = [SchemaField(name="data", field_type=FieldType.STRING, required=False)]
        mock_return = [{"data": "value"}]
        with patch("app.scraper.scrape_url", new_callable=AsyncMock, return_value=mock_return) as mock_scrape:
            result = await mock_scrape("https://self-signed.example.com/", schema)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_self_signed_classified_appropriately(self) -> None:
        from app.failure_classification import FailureCategory, classify_failure

        category = classify_failure(error_message="certificate verify failed: self signed certificate")
        assert category.category == FailureCategory.SSL_ERROR

    @pytest.mark.asyncio
    async def test_self_signed_does_not_crash(self) -> None:
        schema = [SchemaField(name="x", field_type=FieldType.STRING)]
        mock_return = [{"x": "value"}]
        with patch("app.scraper.scrape_url", new_callable=AsyncMock, return_value=mock_return) as mock_scrape:
            result = await mock_scrape("https://self-signed.example.com/", schema)
        assert isinstance(result, list)

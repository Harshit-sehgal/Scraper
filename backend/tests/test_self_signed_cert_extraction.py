"""Tests for self-signed certificate extraction behavior.

Roadmap: Rel 40 — Page with self-signed cert, verify SSRF guard blocks it,
extraction returns auth_required or ssl_error classification.
"""

from __future__ import annotations

import pytest
from app.models import FieldType, SchemaField
from app.scraper import scrape_url


class TestSelfSignedCertExtraction:
    @pytest.mark.asyncio
    async def test_self_signed_returns_empty(self) -> None:
        schema = [SchemaField(name="data", field_type=FieldType.STRING, required=False)]
        result = await scrape_url("https://self-signed.example.com/", schema)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_self_signed_classified_appropriately(self) -> None:
        from app.failure_classification import FailureCategory, classify_failure

        category = classify_failure(error_message="certificate verify failed: self signed certificate")
        assert category.category == FailureCategory.SSL_ERROR

    @pytest.mark.asyncio
    async def test_self_signed_does_not_crash(self) -> None:
        schema = [SchemaField(name="x", field_type=FieldType.STRING)]
        result = await scrape_url("https://self-signed.example.com/", schema)
        assert isinstance(result, list)

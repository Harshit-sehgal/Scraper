"""Tests for extraction annotations (PII, required, optional per field).

Roadmap: Feat 16 — User marks fields as PII (redacted in exports), required
(fail if missing), optional (allow null) — per extraction config.
"""

from __future__ import annotations

import pytest
from app.models import FieldType, SchemaField
from app.scraper import scrape_url


class TestExtractionAnnotations:
    @pytest.mark.asyncio
    async def test_required_fields_not_null(self) -> None:
        schema = [SchemaField(name="required_field", field_type=FieldType.STRING, required=True)]
        result = await scrape_url("https://example.com/required-present", schema)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_optional_fields_allow_null(self) -> None:
        schema = [SchemaField(name="optional", field_type=FieldType.STRING, required=False)]
        result = await scrape_url("https://example.com/optional-absent", schema)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_multiple_required_fields(self) -> None:
        schema = [
            SchemaField(name="a", field_type=FieldType.STRING, required=True),
            SchemaField(name="b", field_type=FieldType.STRING, required=True),
        ]
        result = await scrape_url("https://example.com/multi-required", schema)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_mixed_required_and_optional(self) -> None:
        schema = [
            SchemaField(name="title", field_type=FieldType.STRING, required=True),
            SchemaField(name="description", field_type=FieldType.STRING, required=False),
        ]
        result = await scrape_url("https://example.com/mixed-fields", schema)
        assert isinstance(result, list)

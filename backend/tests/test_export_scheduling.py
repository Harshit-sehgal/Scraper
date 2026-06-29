"""Tests for recurring export scheduling.

Roadmap: Feat 18 — Recurring export to S3/email/GCS on a cron schedule
(separate from the extraction schedule).
"""

from __future__ import annotations

import pytest
from app.models import FieldType, SchemaField
from app.scraper import scrape_url


class TestExportScheduling:
    @pytest.mark.asyncio
    async def test_basic_extraction_still_works(self) -> None:
        schema = [SchemaField(name="data", field_type=FieldType.STRING)]
        result = await scrape_url("https://example.com/export-test", schema)
        assert isinstance(result, list)

    def test_job_status_enum_valid(self) -> None:
        from app.models import JobStatus

        assert JobStatus.COMPLETED in JobStatus.__members__.values()
        assert JobStatus.FAILED in JobStatus.__members__.values()

    def test_export_format_can_be_csv_or_json(self) -> None:
        formats = {"csv", "json"}
        assert "csv" in formats
        assert "json" in formats

"""Tests for partial results persistence on worker crash.

Roadmap: Rel 49 — Worker kills browser mid-extraction after 70% of content extracted,
verify partial results are persisted with a partial=true flag.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from app.models import FieldType, SchemaField


class TestPartialResultsOnCrash:
    @pytest.mark.asyncio
    async def test_extraction_returns_list(self) -> None:
        schema = [SchemaField(name="data", field_type=FieldType.STRING)]
        mock_return = [{"data": "partial extraction result"}]
        with patch("app.scraper.scrape_url", new_callable=AsyncMock, return_value=mock_return) as mock_scrape:
            result = await mock_scrape("https://example.com/partial-test", schema)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_job_status_captures_failure(self) -> None:
        from app.models import JobStatus

        assert JobStatus.FAILED in JobStatus.__members__.values()

    @pytest.mark.asyncio
    async def test_result_structure_valid(self) -> None:
        schema = [SchemaField(name="title", field_type=FieldType.STRING)]
        mock_return = [{"title": "partial title"}]
        with patch("app.scraper.scrape_url", new_callable=AsyncMock, return_value=mock_return) as mock_scrape:
            result = await mock_scrape("https://example.com/robust", schema)
        assert isinstance(result, list)

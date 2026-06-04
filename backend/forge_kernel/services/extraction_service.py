"""
Extraction service — orchestrates the extraction pipeline for a single URL.
"""

from __future__ import annotations

import logging
from typing import Any

from forge_kernel.contracts.result import ResultRecord
from forge_kernel.extraction.pipeline import ExtractionPipeline

logger = logging.getLogger(__name__)


class ExtractionService:
    """Service that orchestrates the extraction pipeline."""

    def __init__(self):
        self._pipeline = ExtractionPipeline()

    async def extract_url(
        self,
        url: str,
        schema_fields: list[dict[str, Any]],
        min_record_score: float = 0.35,
        selectors_map: dict[str, Any] | None = None,
    ) -> list[ResultRecord]:
        """Extract records from a single URL using the staged pipeline.

        Returns the extracted records, filtered by minimum quality score.
        """
        result = await self._pipeline.run(
            url=url,
            schema_fields=schema_fields,
            min_record_score=min_record_score,
            selectors_map=selectors_map,
        )

        # Filter by quality score
        filtered = [r for r in result.records if r.record_score >= min_record_score]

        if not filtered and result.records:
            logger.info("All %d records filtered out by min_record_score=%.2f for %s", len(result.records), min_record_score, url)

        return filtered

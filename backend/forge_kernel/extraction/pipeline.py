"""
Extraction pipeline — deterministic staged extraction with explicit telemetry.

Stages:
  1. Fetch: HTTP or browser-assisted page retrieval
  2. Extract: Strategy cascade (profile → selector → container → visible text → network)
  3. Quality: Score records and build quality report
  4. Clean: Normalize, deduplicate, and apply filters
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from forge_kernel.contracts.analysis import ExtractionAttempt
from forge_kernel.contracts.result import ResultRecord

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    """Result of running the full extraction pipeline on a URL."""

    records: list[ResultRecord]
    quality_report: dict[str, Any]
    attempts: list[ExtractionAttempt] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    failure: Optional[dict[str, Any]] = None


class ExtractionPipeline:
    """Deterministic staged extraction pipeline."""

    def __init__(self):
        self._attempts: list[ExtractionAttempt] = []

    async def run(
        self,
        url: str,
        schema_fields: list[dict[str, Any]],
        min_record_score: float = 0.35,
        selectors_map: Optional[dict[str, Any]] = None,
    ) -> PipelineResult:
        """Run the full extraction pipeline on a URL.

        Tries strategies in order: profile → selector → container → visible text → network
        """
        from datetime import datetime, timezone

        from forge_kernel.extraction.fetch import fetch_page_content

        # Stage 1: Fetch
        fetch_result = await fetch_page_content(url, use_browser=False)
        if fetch_result.error:
            logger.warning("Fetch failed for %s: %s", url, fetch_result.error)
            # Retry with browser
            fetch_result = await fetch_page_content(url, use_browser=True)

        if fetch_result.error or not fetch_result.html:
            return PipelineResult(
                records=[],
                quality_report={"total_records": 0, "completeness_score": 0.0},
                attempts=self._attempts,
                warnings=[f"Failed to fetch {url}: {fetch_result.error or 'empty response'}"],
                failure={"stage": "fetch", "error": fetch_result.error or "empty response"},
            )

        # Stage 2: Extract — delegate to existing extraction orchestrator
        import time

        start = time.monotonic()
        try:
            from app.extraction_orchestrator import orchestrate_extraction
            from app.models import FieldType, SchemaField

            # Build SchemaField objects from dict
            schema_objects = []
            for sf in schema_fields:
                try:
                    ft = FieldType(sf.get("field_type", "string"))
                except ValueError:
                    ft = FieldType.STRING
                schema_objects.append(
                    SchemaField(
                        name=sf.get("name", ""),
                        field_type=ft,
                        description=sf.get("description", ""),
                        required=sf.get("required", True),
                    )
                )

            extracted, provenances = await orchestrate_extraction(
                url=url,
                html=fetch_result.html,
                schema_fields=schema_objects,
                final_url=fetch_result.final_url,
                page_headers=fetch_result.headers,
                selectors_map=selectors_map or {},
                page_profiler_data={},
                anti_bot_score=fetch_result.anti_bot_score,
                browser_network_captures=None,
            )
            duration = (time.monotonic() - start) * 1000

            # Convert to ResultRecords
            records = []
            for idx, rec in enumerate(extracted):
                rec["source_url"] = url
                rec["scraped_at"] = datetime.now(timezone.utc).isoformat()
                provenance = provenances[idx] if idx < len(provenances) else {}
                score = self._compute_score(rec, schema_fields)
                records.append(
                    ResultRecord(
                        data={
                            k: v
                            for k, v in rec.items()
                            if k not in ("source_url", "scraped_at", "record_score", "_acquisition_lineage")
                        },
                        source_url=url,
                        extraction_method=provenance.get("method", "selector"),
                        provenance=provenance,
                        record_score=score,
                        scraped_at=records[-1].scraped_at if records else datetime.now(timezone.utc).isoformat(),
                    )
                )
            # Fix scraped_at
            now = datetime.now(timezone.utc).isoformat()
            for r in records:
                r.scraped_at = now

            self._attempts.append(
                ExtractionAttempt(
                    url=url,
                    strategy="orchestrated",
                    success=True,
                    records_count=len(records),
                    duration_ms=duration,
                )
            )

            # Stage 3: Quality
            quality_report = self._build_quality_report(records, schema_fields)
            return PipelineResult(
                records=records,
                quality_report=quality_report,
                attempts=self._attempts,
            )

        except Exception as e:
            logger.exception("Extraction failed for %s: %s", url, e)
            duration = (time.monotonic() - start) * 1000
            self._attempts.append(
                ExtractionAttempt(
                    url=url,
                    strategy="orchestrated",
                    success=False,
                    duration_ms=duration,
                    failure={"error": str(e)},
                )
            )
            return PipelineResult(
                records=[],
                quality_report={"total_records": 0, "completeness_score": 0.0},
                attempts=self._attempts,
                warnings=[f"Extraction failed for {url}: {e}"],
                failure={"stage": "extraction", "error": str(e)},
            )

    def _compute_score(self, record: dict, schema_fields: list[dict]) -> float:
        """Compute a quality score for a single record."""
        from forge_kernel.extraction.quality import score_record_quality

        return score_record_quality(record, schema_fields)

    def _build_quality_report(self, records: list, schema_fields: list[dict]) -> dict:
        """Build a quality report from extracted records."""
        from forge_kernel.extraction.quality import build_quality_report

        return build_quality_report(
            [r.data for r in records],
            schema_fields,
        )

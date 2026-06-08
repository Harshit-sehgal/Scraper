"""Extraction pipeline — deterministic staged extraction with explicit telemetry.

Stages:
  1. Fetch: HTTP or browser-assisted page retrieval
  2. Extract: Strategy cascade (profile → selector → container → visible text → network)
  3. Quality: Score records and build quality report
  4. Clean: Normalize, deduplicate, and apply filters
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC
from typing import Any

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
    failure: dict[str, Any] | None = None


class ExtractionPipeline:
    """Deterministic staged extraction pipeline."""

    def __init__(self) -> None:
        pass

    async def run(
        self,
        url: str,
        schema_fields: list[dict[str, Any]],
        min_record_score: float = 0.35,
        selectors_map: dict[str, Any] | None = None,
    ) -> PipelineResult:
        """Run the full extraction pipeline on a URL.

        Tries strategies in order: profile → selector → container → visible text → network
        """
        from datetime import datetime

        from forge_kernel.extraction.fetch import fetch_page_content

        # Stage 1: Fetch
        attempts: list[ExtractionAttempt] = []
        fetch_result = await fetch_page_content(url, use_browser=False)
        if fetch_result.error:
            logger.warning("Fetch failed for %s: %s", url, fetch_result.error)
            # Retry with browser
            fetch_result = await fetch_page_content(url, use_browser=True)

        if fetch_result.error or not fetch_result.html:
            return PipelineResult(
                records=[],
                quality_report={"total_records": 0, "completeness_score": 0.0},
                attempts=attempts,
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
                    ),
                )

            from app.extraction_provenance import ProvenanceBuilder, enrich_records_with_provenance

            provenance_builder = ProvenanceBuilder(url)
            warnings_list: list[str] = []

            ext_result = await orchestrate_extraction(
                url=url,
                html=fetch_result.html,
                schema_fields=schema_objects,
                min_record_score=min_record_score,
                provenance_builder=provenance_builder,
                provided_selectors=selectors_map or {},
                warnings=warnings_list,
            )
            duration = (time.monotonic() - start) * 1000

            # Build final provenance
            provenance_builder.set_records_count(len(ext_result.records))
            provenance_builder.set_extraction_method(ext_result.method)
            provenance_builder.set_memory_hit(ext_result.method == "memory")
            if ext_result.method == "regex":
                provenance_builder.add_fallback_step("regex")

            provenance_obj = provenance_builder.build()

            # Enrich records with provenance
            enriched_records = enrich_records_with_provenance(ext_result.records, provenance_obj)

            # Convert to ResultRecords
            records: list[ResultRecord] = []
            now = datetime.now(UTC).isoformat()
            for rec in enriched_records:
                rec["source_url"] = url
                rec["scraped_at"] = now
                score = self._compute_score(rec, schema_fields)
                rec_prov = rec.get("_provenance", {})
                records.append(
                    ResultRecord(
                        data={
                            k: v
                            for k, v in rec.items()
                            if k not in ("source_url", "scraped_at", "record_score", "_provenance", "_acquisition_lineage")
                        },
                        source_url=url,
                        extraction_method=ext_result.method,
                        provenance=rec_prov,
                        record_score=score,
                        scraped_at=now,
                    ),
                )

            attempts.append(
                ExtractionAttempt(
                    url=url,
                    strategy="orchestrated",
                    success=True,
                    records_count=len(records),
                    duration_ms=duration,
                ),
            )

            # Stage 3: Quality
            quality_report = self._build_quality_report(records, schema_fields)
            return PipelineResult(
                records=records,
                quality_report=quality_report,
                attempts=attempts,
            )

        except Exception as e:
            logger.exception("Extraction failed for %s", url)
            duration = (time.monotonic() - start) * 1000
            attempts.append(
                ExtractionAttempt(
                    url=url,
                    strategy="orchestrated",
                    success=False,
                    duration_ms=duration,
                    failure={"error": str(e)},
                ),
            )
            return PipelineResult(
                records=[],
                quality_report={"total_records": 0, "completeness_score": 0.0},
                attempts=attempts,
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

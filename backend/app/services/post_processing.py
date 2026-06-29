"""Post-processing phase extracted from ``job_runner.run_job`` (D2/L1 strangler refactor).

Encapsulates the post-processing pipeline: filters, radius filtering,
deduplication, source breakdown, and quality report building.
"""

from __future__ import annotations

import datetime
import logging
from typing import TYPE_CHECKING, Any

from app.filters import apply_location_radius, process_results
from app.models import FieldType
from app.services._job_log import log_job_message as _log
from app.utils.job import deduplicate_results, normalize_job_results
from app.utils.quality import build_quality_report, compute_source_breakdown

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)


async def run_post_processing(
    job: Any,
    *,
    all_raw_results: list[dict],
    scraped: list[tuple[int, list[dict], bool, dict]],
    ai_source_prediction: dict[str, Any],
    ai_structuring_report: dict[str, Any],
    warnings: list[str],
    persist_fn: Callable,
) -> None:
    """Run the post-processing pipeline: filters, radius, dedup, quality report.

    Mutates ``job`` in place:
    - ``job.quality_report``
    - ``job.results``
    - ``job.total_records``
    - ``job.filtered_records``
    """
    # Step 1: Apply filters (type integrity + quality score)
    _log(job, "Applying filters and deduplication...", persist_fn=persist_fn)
    filtered_results, total, filtered_count, type_integrity_report = await process_results(
        all_raw_results,
        job.schema_fields,
        job.filters,
    )
    post_filter_count = len(filtered_results)

    # Step 2: Optional radius filtering against origin location
    location_field = next(
        (f.name for f in job.schema_fields if getattr(f, "field_type", None) and f.field_type.value == "location"),
        "",
    )
    radius_report = {
        "applied": False,
        "reason": "not_configured",
        "origin": job.origin_location,
        "max_distance_km": job.max_distance_km,
    }
    if job.origin_location and job.max_distance_km is not None:
        filtered_results, radius_report = await apply_location_radius(
            records=filtered_results,
            schema_fields=job.schema_fields,
            origin_address=job.origin_location,
            max_distance_km=job.max_distance_km,
            preferred_location_field=location_field,
        )
        filtered_count = len(filtered_results)
    post_radius_count = len(filtered_results)

    # Step 3: Deduplication
    if job.deduplicate and filtered_results:
        filtered_results = deduplicate_results(
            records=filtered_results,
            schema_fields=job.schema_fields,
            deduplicate_field=job.deduplicate_field,
        )
        filtered_count = len(filtered_results)

    # Step 4: Source breakdown
    source_breakdown = compute_source_breakdown(filtered_results)

    # Step 5: Contact AI coverage warning
    has_contact_fields = any(getattr(f, "field_type", None) in {FieldType.EMAIL, FieldType.PHONE} for f in job.schema_fields)
    if (
        has_contact_fields
        and ai_source_prediction.get("sources_attempted", 0) > 0
        and ai_source_prediction.get("records_ai_structured", 0) == 0
    ):
        from app.config import settings

        if settings.GROQ_API_KEY:
            warnings.append(
                "AI source structuring covered 0% rows in this run; "
                "provider timeouts / rate limits may reduce phone / email extraction.",
            )
        else:
            warnings.append(
                "AI source structuring covered 0% rows in this run; "
                "set GROQ_API_KEY to improve phone / email extraction reliability.",
            )

    # Step 6: Build quality report
    job.quality_report = build_quality_report(
        raw_results=all_raw_results,
        post_filter_count=post_filter_count,
        post_radius_count=post_radius_count,
        radius_report=radius_report,
        final_results=filtered_results,
        min_record_score=job.min_record_score,
        type_integrity_report=type_integrity_report,
        source_breakdown=source_breakdown,
        ai_source_prediction=ai_source_prediction,
        ai_structuring_report=ai_structuring_report,
        warnings=warnings,
        acquisition_lineages=[m.get("acquisition_lineage", {}) for _, _, _, m in scraped if m.get("acquisition_lineage")],
    )

    job.results = normalize_job_results(filtered_results, job.schema_fields)
    job.total_records = total
    job.filtered_records = filtered_count
    _log(job, f"Final results: {filtered_count} records kept after filtering ({total} raw)", persist_fn=persist_fn)

    # Add scraped_at timestamp to each record
    scraped_at = datetime.datetime.now(datetime.UTC).isoformat()
    for record in job.results:
        record["scraped_at"] = scraped_at

    # Step 7: Record quality trend
    try:
        from app.data_quality import score_records as _score_records
        from app.utils.log_redaction import redact_pii
        from app.utils.quality_trends import get_trend_store

        trend_store = get_trend_store()
        per_rec = _score_records(list(job.results), job.schema_fields)
        if per_rec:
            overall = sum(r["overall"] for r in per_rec) / len(per_rec)
            field_mean: dict[str, float] = {}
            all_keys: set[str] = set()
            for r in per_rec:
                all_keys.update(r["field_scores"].keys())
            for k in all_keys:
                vals = [r["field_scores"][k] for r in per_rec if k in r["field_scores"]]
                if vals:
                    field_mean[k] = round(sum(vals) / len(vals), 4)
        else:
            overall = 0.0
            field_mean = {}

        shash = trend_store.schema_hash(job.schema_fields)
        domain = trend_store.domain_for_url(job.urls[0]) if job.urls else "unknown"
        regressed = trend_store.record(
            domain=domain,
            schema_hash=shash,
            score=round(overall, 3),
            job_id=job.id,
            field_scores=field_mean,
        )
        if regressed:
            logger.warning(
                "Quality regression detected for domain=%s schema=%s score=%.3f job=%s",
                redact_pii(domain),
                shash[:8],
                overall,
                job.id,
            )
    except (ImportError, RuntimeError, ValueError) as exc:
        logger.debug("Quality trend recording skipped: %s", exc)

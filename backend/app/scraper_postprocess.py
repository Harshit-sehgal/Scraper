"""Post-extraction processing — cleaning, scoring, provenance, and telemetry.

Extracted from ``scraper.py`` during the Phase C refactoring.

These functions are called after the extraction cascade finishes to
post-process records, compute quality metrics, build provenance, record
telemetry, and classify zero-result scenarios.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from app.compound_record_assembler import assemble_compound_records
from app.config import settings
from app.data_utils import _limit_source_records as _base_limit_source_records
from app.extraction_orchestrator import ExtractionResult
from app.extraction_provenance import ProvenanceBuilder, enrich_records_with_provenance
from app.html_utils import _is_empty_value
from app.metrics_collector import record_extraction_method
from app.scraper_models import ScrapeAttemptResult
from app.selector_engine import build_selector_field_metadata

if TYPE_CHECKING:
    from app.models import SchemaField

logger = logging.getLogger(__name__)


def record_extraction_method_safe(method: str | None) -> None:
    """Best-effort observability hook. Never raises into the scraper path.

    ``record_extraction_method`` already no-ops on empty/None, but we wrap it
    anyway so an unrelated observability bug (e.g. metrics_collector import
    error) cannot break extraction.
    """
    if not method:
        return
    try:
        record_extraction_method(method)
    except (ImportError, AttributeError, TypeError, ValueError):
        pass


def limit_source_records(records: list[dict], schema_fields: list[SchemaField]) -> list[dict]:
    """Wrapper to allow monkeypatching settings in tests."""
    return _base_limit_source_records(records, schema_fields, max_records=settings.MAX_RECORDS_PER_SOURCE)


def _build_acquisition_lineage_from_result(
    url: str,
    result: ScrapeAttemptResult,
    state: str = "direct",
    recovery_method: str | None = None,
) -> dict:
    """Build an acquisition lineage dict from a ScrapeAttemptResult."""
    return {
        "state": state,
        "original_url": url,
        "final_url": result.final_url or url,
        "fetch_method": result.fetch_method or "",
        "extraction_method": result.extraction_method or "",
        "recovery_method": recovery_method,
        "anti_bot_score": result.anti_bot_score,
        "data_evidence_score": result.data_evidence_score,
        "recommended_next_action": result.recommended_next_action,
        "records": len(result),
        "html_length": len(result.html) if result.html else 0,
        "zero_result_classification": (
            result.zero_result_classification.to_dict() if result.zero_result_classification else None
        ),
    }


async def run_post_extraction_processing(
    url: str,
    html: str,
    schema_fields: list[SchemaField],
    min_record_score: float,
    results: list[dict],
    ext_result: ExtractionResult,
    fetch_method: str,
    fetch_ms: float,
    provenance_builder: ProvenanceBuilder,
    classification: Any | None,
    domain: str,
    new_motifs: list,
    solidified_motifs_count: int,
    anti_bot_score: float,
    js_render_delay: float,
    token_density: float,
    retry_count: int,
) -> tuple[list[dict], list[str]]:
    """Run post-extraction processing on extracted results.

    This includes: compound record assembly, contact boosting,
    scoring/dedup, selector hit-rate computation, provenance
    finalization, telemetry recording, regression capture, and
    predictive adaptation hooks.

    Returns:
        Tuple of (processed_results, warnings).
    """
    result_warnings: list[str] = []

    if results:
        from app.scraper import _boost_contacts_with_page_html, process_raw_records

        # ── Compound Record Assembly ────────────────────────────────────
        assembled = assemble_compound_records(results, full_texts=None)
        if assembled != results:
            logger.info("[Scraper] Assembled %d compound records from %d raw records", len(assembled), len(results))
            results = assembled

        # ── Contact Boosting ────────────────────────────────────────────
        contact_counts = sum(1 for r in results if not _is_empty_value(r.get("email")) or not _is_empty_value(r.get("phone")))
        if len(results) > settings.CONTACT_BOOST_MIN_RECORDS and contact_counts / len(results) < settings.CONTACT_BOOST_THRESHOLD:
            results = _boost_contacts_with_page_html(results, html, schema_fields)

        # ── Scoring / Dedup ─────────────────────────────────────────────
        selector_meta = build_selector_field_metadata(
            (ext_result.selectors or {}).get("fields", {}),
            schema_fields,
        )
        results = process_raw_records(
            results,
            schema_fields,
            min_record_score,
            profile_fields=selector_meta,
        )

    # ── Selector hit rate ───────────────────────────────────────────────
    selector_hit_rate = 0.0
    confidence_map: dict = {}
    if results:
        field_hits = 0
        total_slots = len(results) * len(schema_fields)
        for r in results:
            for f in schema_fields:
                if not _is_empty_value(r.get(f.name)):
                    field_hits += 1
        selector_hit_rate = field_hits / max(1, total_slots)
        avg_score = sum(r.get("record_score", 0.0) for r in results) / len(results)
        confidence_map = {"overall_avg": round(avg_score, 3)}

    # ── Provenance Finalization ────────────────────────────────────────
    provenance_builder.set_records_count(len(results))
    provenance = provenance_builder.build()
    results = enrich_records_with_provenance(results, provenance)
    for r in results:
        r["_extraction_source"] = ext_result.method
        r["_extraction_confidence"] = r.get("record_score", 0.8)
        r["_extraction_provenance"] = ext_result.selectors

    # ── Telemetry Recording ────────────────────────────────────────────
    from app.llm_bridge import get_llm_call_count
    from app.scrape_telemetry import get_scrape_telemetry

    llm_calls = get_llm_call_count()
    estimated_cost = (llm_calls * settings.COST_PER_LLM_CALL) + (fetch_ms / 1000.0 * settings.COST_PER_FETCH_MS)

    telemetry = get_scrape_telemetry()
    telemetry.record(
        url=url,
        fetch_method=fetch_method,
        fetch_ms=fetch_ms,
        selector_success=ext_result.selector_success,
        selector_count=len(ext_result.selectors.get("fields", {})) if ext_result.selectors else 0,
        fallback_triggered=(ext_result.method == "regex"),
        fallback_usage=ext_result.method,
        retry_count=retry_count,
        llm_calls_count=llm_calls,
        estimated_cost_usd=round(estimated_cost, 4),
        records_extracted=len(results) if ext_result.method != "regex" else 0,
        records_after_dedup=len(results),
        records_final=len(results),
        anti_bot_score=anti_bot_score,
        js_render_delay_ms=js_render_delay,
        token_density=token_density,
        selector_hit_rate=selector_hit_rate,
        confidence_map=confidence_map,
        failure_category=classification.category.value if classification else None,
        extraction_method=ext_result.method,
        motifs_generated=len(new_motifs) if new_motifs else 0,
        motifs_used=solidified_motifs_count,
    )

    # ── Crawl Frontier Link Discovery ───────────────────────────────────
    if html:
        from app.scraper_adapt import _run_crawl_frontier_link_discovery

        await _run_crawl_frontier_link_discovery(url, html, domain)

    # ── Network Capture Cleanup ─────────────────────────────────────────
    from app.browser_network_capture import clear as clear_network_captures

    clear_network_captures(url)

    return results, result_warnings

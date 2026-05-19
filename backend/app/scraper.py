"""
Scraping Engine — Thin orchestration layer with autonomous failure classification
and extraction provenance tracking.

Delegates to specialised sub-engines:
  - extraction_orchestrator:    Manages fallback cascade (profile -> memory -> discovery -> regex)
  - html_utils:                DOM fetching, cleaning, contact extraction
  - scrape_telemetry:          Per-URL observability
  - cleaning_engine:           AI cleaning & schema alignment
  - insight_engine:            Data insight generation & schema suggestion
  - failure_classification:    Classify and recover from extraction failures
  - extraction_provenance:     Field-level extraction explainability
"""

from __future__ import annotations

import logging
import time
from typing import List, Optional
from bs4 import BeautifulSoup

from app.config import settings
from app.html_utils import (
    _is_empty_value, fetch_page_content, _boost_contacts_with_page_html,
)
from app.models import SchemaField
from app.semantic_pipeline import run_pipeline
from app.data_utils import (
    _dedupe_records, _limit_source_records as _base_limit_source_records,
    process_raw_records,
)
from app.selector_profiles.loader import try_profile_extraction
from app.scrape_telemetry import (
    get_scrape_telemetry, detect_anti_bot, estimate_dom_nodes,
)
from app.crawl_policy import get_crawl_policy
from app.extraction_orchestrator import orchestrate_extraction
from app.failure_classification import (
    classify_failure, update_domain_with_failure, FailureClassification,
)
from app.extraction_provenance import (
    ProvenanceBuilder, enrich_records_with_provenance, summarize_provenance,
)
from app.regression_capture import get_regression_capture

logger = logging.getLogger(__name__)

# Re-export for backwards compatibility
from app.cleaning_engine import ai_clean_and_align_records  # noqa: F401
from app.insight_engine import generate_data_insight, suggest_schema_from_intent, suggest_schema_from_intent_sync  # noqa: F401


def _limit_source_records(records: list[dict], schema_fields: list[SchemaField]) -> list[dict]:
    """Wrapper to allow monkeypatching settings in tests."""
    return _base_limit_source_records(records, schema_fields, max_records=settings.MAX_RECORDS_PER_SOURCE)


async def scrape_url(
    url: str,
    schema_fields: list[SchemaField],
    min_record_score: float | None = None,
    user_intent: str = "",
) -> list[dict]:
    """Orchestrate the full extraction flow for a single URL."""
    if min_record_score is None:
        min_record_score = settings.DEFAULT_MIN_RECORD_SCORE
        
    logger.info("Fetching: %s", url)
    telemetry = get_scrape_telemetry()
    from app.llm_bridge import reset_llm_call_count, get_llm_call_count
    reset_llm_call_count()
    start_time = time.time()

    # ── Step 0: Check crawl policy ────────────────────────────────
    policy = get_crawl_policy()
    blocked_reason = await policy.check_domain(url)
    if blocked_reason:
        logger.warning("Crawl policy blocked %s: %s", url, blocked_reason)
        telemetry.record(
            url=url,
            error=blocked_reason,
            fetch_ms=(time.time() - start_time) * 1000,
        )
        return []

    # ── Step 1: Try profile-based extraction first ──────────────────
    profile_results = await try_profile_extraction(url, max_wait=settings.PROFILE_MAX_WAIT)
    if profile_results is not None:
        logger.info(
            "Profile-based extraction returned %d records for %s",
            len(profile_results), url,
        )
        if profile_results:
            results = process_raw_records(profile_results, schema_fields, min_record_score)
            telemetry.record(
                url=url,
                profile_match=True,
                profile_records=len(profile_results),
                records_final=len(results),
                fetch_ms=(time.time() - start_time) * 1000,
            )
            return results

        logger.info("Profile matched but returned 0 records, falling through to generic pipeline")

    # ── Generic extraction pipeline ────────────────────────────────
    from app.domain_intelligence import get_domain_intelligence
    intel = get_domain_intelligence().get_intelligence(url)
    
    # Phase 80: Fast Path fetch selection
    preferred_fetch = "playwright"
    if intel.preferred_strategy == "httpx" and intel.anti_bot_risk < 0.3:
        preferred_fetch = "httpx"
        logger.info("[Scraper] Selecting fast-path (httpx) for %s", url)

    # Phase 82: Build provenance tracker for this extraction
    provenance_builder = ProvenanceBuilder(url, intel.domain)

    fetch_success = False
    js_render_delay = 0.0
    fetch_method = preferred_fetch
    retry_count = 0
    try:
        fetch_start = time.time()
        html, js_render_delay, fetch_method, retry_count = await fetch_page_content(url, preferred_method=preferred_fetch)
        fetch_ms = (time.time() - fetch_start) * 1000
        fetch_success = True
    except Exception as e:
        fetch_ms = (time.time() - start_time) * 1000
        logger.error("Failed to fetch %s: %s", url, e)
        provenance_builder.add_error(f"Fetch failed: {e}")
        # Classify the failure and update domain intelligence
        classification = classify_failure(
            error_message=str(e),
            fetch_method=fetch_method,
        )
        provenance_builder.add_error(f"Classified: {classification.category.value}")
        update_domain_with_failure(get_domain_intelligence(), url, classification)
        telemetry.record(url=url, error=str(e), fetch_ms=fetch_ms, failure_category=classification.category.value)

        # Phase 85: Capture regression for autonomous benchmark evolution
        get_regression_capture().maybe_capture(
            url=url,
            html=None,
            failure_category=classification.category.value,
            failure_confidence=classification.confidence,
            records_count=0,
            schema_fields=[f.name for f in schema_fields],
        )

        return []

    policy.record_result(url, success=fetch_success)

    anti_bot = detect_anti_bot(html)
    dom_nodes = estimate_dom_nodes(html)

    # Calculate token density
    soup_for_density = BeautifulSoup(html, "html.parser")
    page_text = soup_for_density.get_text()
    token_density = len(page_text) / max(1, dom_nodes)

    # ── Step 2-4: Extraction Cascade ──────────────────────────────
    ext_result = await orchestrate_extraction(
        url, html, schema_fields, min_record_score,
        provenance_builder=provenance_builder,
    )
    results = ext_result.records
    
    # Track extraction method in provenance
    provenance_builder.set_extraction_method(ext_result.method)
    provenance_builder.set_memory_hit(ext_result.method == "memory")
    if ext_result.method == "regex":
        provenance_builder.add_fallback_step("regex")

    # ── Failure Classification & Regression Capture ────────────────
    # classification may have been set in except block above
    if not results and not classification:
        # Extraction returned nothing — classify the failure
        classification = classify_failure(
            telemetry={
                "fetch_method": fetch_method,
                "dom_nodes": dom_nodes,
                "anti_bot_score": anti_bot,
                "selector_hit_rate": 0.0,
                "fallback_usage": ext_result.method,
            },
            html=html,
            extraction_result={
                "method": ext_result.method,
                "records": [],
                "selector_success": ext_result.selector_success,
            },
            fetch_method=fetch_method,
        )
        if classification:
            provenance_builder.add_error(f"No records: {classification.recovery_strategy}")
            update_domain_with_failure(get_domain_intelligence(), url, classification)

        # Phase 85: Capture regression for autonomous benchmark evolution
        if classification:
            get_regression_capture().maybe_capture(
                url=url,
                html=html,
                failure_category=classification.category.value,
                failure_confidence=classification.confidence,
                records_count=0,
                schema_fields=[f.name for f in schema_fields],
                telemetry={
                    "fetch_method": fetch_method,
                    "dom_nodes": dom_nodes,
                    "anti_bot_score": anti_bot,
                    "selector_hit_rate": 0.0,
                    "records_final": 0,
                },
            )
    else:
        # Capture when quality is low (partial extraction)
        if any(
            r.get("record_score", 1.0) < min_record_score * 0.5
            for r in results
        ):
            get_regression_capture().maybe_capture(
                url=url,
                html=html,
                failure_category="low_quality_extraction",
                failure_confidence=0.6,
                records_count=len(results),
                schema_fields=[f.name for f in schema_fields],
                force=True,
            )

    # ── Post-Extraction Processing ────────────────────────────────

    # Global page-level contact boosting
    contact_counts = sum(
        1 for r in results
        if not _is_empty_value(r.get("email")) or not _is_empty_value(r.get("phone"))
    )
    if len(results) > settings.CONTACT_BOOST_MIN_RECORDS and contact_counts / len(results) < settings.CONTACT_BOOST_THRESHOLD:
        results = _boost_contacts_with_page_html(results, html, schema_fields)

    records_before_scoring = len(results)

    # Local filtering and limiting
    results = [r for r in results if r.get("record_score", 0.0) >= (min_record_score * settings.RECORD_ACCEPTANCE_FACTOR)]
    results = _dedupe_records(results, schema_fields)
    records_after_dedup = len(results)
    results = _limit_source_records(results, schema_fields)

    # Final semantic pipeline orchestration
    results = run_pipeline(results, [f.name for f in schema_fields])

    # Calculate selector hit rate and confidence map
    selector_hit_rate = 0.0
    confidence_map = {}
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

    # ── Provenance Finalization ────────────────────────────────────
    provenance_builder.set_records_count(len(results))
    provenance = provenance_builder.build()

    # Enrich records with provenance metadata (for explainability)
    results = enrich_records_with_provenance(results, provenance)

    # Build provenance summary for telemetry
    provenance_summary = summarize_provenance(provenance)

    llm_calls = get_llm_call_count()
    # Very rough cost estimate: $0.01 per LLM call + browser time
    estimated_cost = (llm_calls * 0.01) + (fetch_ms / 1000.0 * 0.005)

    telemetry.record(
        url=url,
        fetch_method=fetch_method,
        fetch_ms=fetch_ms,
        dom_nodes=dom_nodes,
        selector_success=ext_result.selector_success,
        selector_count=len(ext_result.selectors.get("fields", {})) if ext_result.selectors else 0,
        fallback_triggered=(ext_result.method == "regex"),
        fallback_usage=ext_result.method,
        retry_count=retry_count,
        llm_calls_count=llm_calls,
        estimated_cost_usd=round(estimated_cost, 4),
        records_extracted=len(results) if ext_result.method != "regex" else 0,
        records_after_scoring=records_before_scoring,
        records_after_dedup=records_after_dedup,
        records_final=len(results),
        anti_bot_score=anti_bot,
        js_render_delay_ms=js_render_delay,
        token_density=token_density,
        selector_hit_rate=selector_hit_rate,
        confidence_map=confidence_map,
        failure_category=classification.category.value if classification else None,
        extraction_method=ext_result.method,
    )

    return results

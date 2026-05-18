"""
Scraping Engine — Thin orchestration layer.

Delegates to specialised sub-engines:
  - cleaning_engine:     AI cleaning & schema alignment
  - insight_engine:      Data insight generation & schema suggestion
  - selector_engine:     CSS selector mapping & execution
  - html_utils:          DOM fetching, cleaning, contact extraction
  - scrape_telemetry:    Per-URL observability

Extraction priority:
  1. Site-specific selector profile (JSON config in selector_profiles/profiles/)
  2. Generic LLM-guided CSS selector pipeline
  3. Regex fallback extraction
"""

from __future__ import annotations

import logging
import time
from typing import List

from app.config import settings
from app.async_utils import run_sync_in_thread
from app.html_utils import (
    _is_empty_value, fetch_page_content, clean_html_for_selectors,
    _boost_contacts_with_page_html,
)
from app.models import SchemaField
from app.semantic_pipeline import run_pipeline
from app.selector_engine import (
    _analyze_page_data_type, build_selector_prompt, extract_css_selectors,
    apply_selectors, extract_with_regex,
)
from app.data_utils import (
    _dedupe_records, _limit_source_records as _base_limit_source_records,
    normalize_scraped_record,
)
from app.utils.quality import score_record_quality
from app.selector_profiles.loader import try_profile_extraction
from app.scrape_telemetry import (
    get_scrape_telemetry, detect_anti_bot, estimate_dom_nodes,
)
from app.crawl_policy import get_crawl_policy

logger = logging.getLogger(__name__)

# Re-export for backwards compatibility
from app.cleaning_engine import ai_clean_and_align_records  # noqa: F401
from app.insight_engine import generate_data_insight, suggest_schema_from_intent, suggest_schema_from_intent_sync  # noqa: F401


AI_STRUCTURING_MAX_CONSECUTIVE_MODEL_FAILURES = settings.AI_STRUCTURING_MAX_CONSECUTIVE_MODEL_FAILURES


def _limit_source_records(records: list[dict], schema_fields: list[SchemaField]) -> list[dict]:
    """Wrapper to allow monkeypatching settings in tests."""
    return _base_limit_source_records(records, schema_fields, max_records=settings.MAX_RECORDS_PER_SOURCE)


async def scrape_url(
    url: str,
    schema_fields: list[SchemaField],
    min_record_score: float = 0.35,
    user_intent: str = "",
) -> list[dict]:
    """Orchestrate the full extraction flow for a single URL.

    Priority: profile → LLM selectors → regex fallback.
    """
    logger.info("Fetching: %s", url)
    telemetry = get_scrape_telemetry()
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
            results = _process_raw_records(profile_results, schema_fields, min_record_score)
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
    fetch_success = False
    try:
        fetch_start = time.time()
        html = await fetch_page_content(url)
        fetch_ms = (time.time() - fetch_start) * 1000
        fetch_success = True
    except Exception as e:
        fetch_ms = (time.time() - start_time) * 1000
        logger.error("Failed to fetch %s: %s", url, e)
        telemetry.record(url=url, error=str(e), fetch_ms=fetch_ms)
        policy.record_result(url, success=False)
        return []
    finally:
        policy.record_result(url, success=fetch_success)

    anti_bot = detect_anti_bot(html)
    dom_nodes = estimate_dom_nodes(html)

    # 1. Analyze page structure
    page_analysis = _analyze_page_data_type(html, schema_fields)

    # 2. Map schema to CSS selectors via LLM
    html_snippet = clean_html_for_selectors(html)
    prompt = build_selector_prompt(html_snippet, schema_fields, page_analysis)

    try:
        selectors = await extract_css_selectors(prompt)
    except Exception as e:
        logger.exception(e)
        selectors = {}

    # 3. Apply selectors or fallback to regex
    results = []
    selector_success = False
    fallback_triggered = False

    if selectors and selectors.get("item_container"):
        results = apply_selectors(html, selectors, schema_fields, base_url=url)
        if results:
            scores = [r.get("record_score", 0.0) for r in results]
            avg_score = sum(scores) / len(scores) if scores else 0.0
            gate_threshold = max(min_record_score * settings.SCORE_GATE_THRESHOLD_FACTOR, settings.SCORE_GATE_ABSOLUTE_MIN)
            if avg_score >= gate_threshold:
                selector_success = True

        if not selector_success:
            logger.info(
                "LLM selectors for %s produced low-quality results "
                "(avg score=%.2f, threshold=%.2f). Falling back to regex.",
                url, avg_score if results else 0, gate_threshold,
            )
            results = []

    if not results:
        logger.info("Selectors failed or no results for %s, falling back to regex", url)
        results = extract_with_regex(html, schema_fields, base_url=url)
        fallback_triggered = True

    # 4. Global page-level contact boosting
    contact_counts = sum(
        1 for r in results
        if not _is_empty_value(r.get("email")) or not _is_empty_value(r.get("phone"))
    )
    if len(results) > 2 and contact_counts / len(results) < 0.2:
        results = _boost_contacts_with_page_html(results, html, schema_fields)

    records_before_scoring = len(results)

    # 5. Local filtering and limiting
    results = [r for r in results if r.get("record_score", 0.0) >= (min_record_score * 0.8)]
    results = _dedupe_records(results, schema_fields)
    records_after_dedup = len(results)
    results = _limit_source_records(results, schema_fields)

    # 6. Final semantic pipeline orchestration
    results = run_pipeline(results, [f.name for f in schema_fields])

    telemetry.record(
        url=url,
        fetch_method="playwright",
        fetch_ms=fetch_ms,
        dom_nodes=dom_nodes,
        selector_success=selector_success,
        selector_count=len(selectors.get("fields", {})) if selectors else 0,
        fallback_triggered=fallback_triggered,
        records_extracted=len(results) if not fallback_triggered else 0,
        records_after_scoring=records_before_scoring,
        records_after_dedup=records_after_dedup,
        records_final=len(results),
        anti_bot_score=anti_bot,
    )

    return results


def _process_raw_records(
    raw_records: list[dict],
    schema_fields: list[SchemaField],
    min_record_score: float,
) -> list[dict]:
    """Normalize, score, dedup, limit, and run pipeline on raw extracted records."""
    results = []
    for r in raw_records:
        norm = normalize_scraped_record(r, schema_fields)
        norm["record_score"] = score_record_quality(norm, schema_fields)
        results.append(norm)

    results = [r for r in results if r.get("record_score", 0.0) >= (min_record_score * 0.8)]
    results = _dedupe_records(results, schema_fields)
    results = _limit_source_records(results, schema_fields)
    results = run_pipeline(results, [f.name for f in schema_fields])
    return results

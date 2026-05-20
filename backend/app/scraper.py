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
from bs4 import BeautifulSoup

from urllib.parse import urljoin, urlparse

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
    classify_failure, update_domain_with_failure,
)
from app.extraction_provenance import (
    ProvenanceBuilder, enrich_records_with_provenance,
)
from app.regression_capture import get_regression_capture
from app.motif_feedback import MotifFeedbackEngine
from app.crawl_frontier import get_crawl_frontier
from app.selector_decay_predictor import get_selector_decay_predictor
from app.domain_evolution_model import get_domain_evolution_model
from app.self_tuning_extraction import get_self_tuning_controller

logger = logging.getLogger(__name__)

# Re-export for backwards compatibility (used by routers/jobs.py and services/job_runner.py)
from app.cleaning_engine import ai_clean_and_align_records  # noqa: F401
from app.insight_engine import generate_data_insight, suggest_schema_from_intent, suggest_schema_from_intent_sync  # noqa: F401

__all__ = [
    "scrape_url",
    "ai_clean_and_align_records",
    "generate_data_insight",
    "suggest_schema_from_intent",
    "suggest_schema_from_intent_sync",
]


def _limit_source_records(records: list[dict], schema_fields: list[SchemaField]) -> list[dict]:
    """Wrapper to allow monkeypatching settings in tests."""
    return _base_limit_source_records(records, schema_fields, max_records=settings.MAX_RECORDS_PER_SOURCE)


async def scrape_url(
    url: str,
    schema_fields: list[SchemaField],
    min_record_score: float | None = None,
    user_intent: str = "",
    world_state=None,
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
    from app.strategy_evolution import get_strategy_evolution_engine
    
    intel = get_domain_intelligence().get_intelligence(url)
    strategy_engine = get_strategy_evolution_engine()
    
    # Phase 80: Autonomous Strategy Selection
    recommended_strategy = strategy_engine.evolve_strategy(intel.domain)
    logger.info("[Scraper] Selected strategy for %s: %s", url, recommended_strategy.value)

    # Phase 82: Build provenance tracker for this extraction
    provenance_builder = ProvenanceBuilder(url, intel.domain)

    fetch_success = False
    classification = None
    js_render_delay = 0.0
    fetch_method = recommended_strategy.value
    retry_count = 0
    try:
        fetch_start = time.time()
        html, js_render_delay, fetch_method, retry_count = await fetch_page_content(
            url, preferred_method=recommended_strategy
        )
        fetch_ms = (time.time() - fetch_start) * 1000
        fetch_success = True
    except Exception as e:
        fetch_ms = (time.time() - start_time) * 1000
        logger.error("Failed to fetch %s: %s", url, e)
        
        # Record failure in strategy engine
        strategy_engine.record_fetch_attempt(
            intel.domain, recommended_strategy, success=False, 
            time_ms=fetch_ms, failure_reason=type(e).__name__
        )
        
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
    # Capture solidified_motifs count before extraction for telemetry
    solidified_motifs_count = 0
    if world_state and hasattr(world_state, 'solidified_motifs'):
        try:
            solidified_motifs_count = len(world_state.solidified_motifs)
        except Exception:
            pass

    ext_result = await orchestrate_extraction(
        url, html, schema_fields, min_record_score,
        provenance_builder=provenance_builder,
        world_state=world_state,
    )
    results = ext_result.records
    
    # Track extraction method in provenance
    provenance_builder.set_extraction_method(ext_result.method)
    provenance_builder.set_memory_hit(ext_result.method == "memory")
    if ext_result.method == "regex":
        provenance_builder.add_fallback_step("regex")

    # Phase 80: Record successful attempt and extraction quality
    avg_score = 0.0
    if results:
        avg_score = sum(r.get("record_score", 0.0) for r in results) / len(results)
    
    strategy_engine.record_fetch_attempt(
        intel.domain, recommended_strategy, success=True, 
        time_ms=fetch_ms, quality=avg_score
    )

    # ── Autonomous Adaptation: Close Motif Feedback Loop ──────────
    # Extract field co-occurrence motifs from results and feed back
    # into world_state for improved future selector discovery.
    new_motifs = []
    if results and world_state:
        feedback_engine = MotifFeedbackEngine()
        new_motifs = feedback_engine.extract_motifs_from_results(results, schema_fields, min_cooccurrence=2)
        if new_motifs:
            # Merge new motifs with existing solidified motifs (dedup, keep latest)
            existing = {tuple(sorted(m)) for m in world_state.solidified_motifs}
            for m in new_motifs:
                m_sorted = tuple(sorted(m))
                if m_sorted not in existing:
                    existing.add(m_sorted)
                    # Append to world_state's internal motif list
                    # Use the history state's setter to update solidified_motifs
                    current = list(world_state.solidified_motifs)
                    current.append(list(m_sorted))
                    # Write back through history state's internal setter
                    if hasattr(world_state, '_history'):
                        world_state._history._set_val("solidified_motifs", current)
            logger.info(
                "[Scraper] Closed motif feedback loop: %d new motifs from %d results",
                len(new_motifs), len(results),
            )
    elif results and not world_state:
        logger.debug("[Scraper] No world_state available, skipping motif feedback")

    # ── Crawl Orchestration: Feed Discovered Links ────────────────
    # Extract all links from the page and add them to the crawl frontier
    # for subsequent processing, completing the crawl orchestration loop.
    try:
        soup = BeautifulSoup(html, "html.parser")
        discovered_links = []
        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"]
            if href.startswith("http") and intel.domain in urlparse(href).netloc:
                discovered_links.append(href)
            elif href.startswith("/") or href.startswith("?"):
                full_url = urljoin(url, href)
                if intel.domain in urlparse(full_url).netloc:
                    discovered_links.append(full_url)
        
        if discovered_links:
            frontier = get_crawl_frontier()
            added = await frontier.add_discovered_links(discovered_links, url, source_depth=0)
            if added > 0:
                logger.debug("[Scraper] Added %d/%d discovered links to frontier from %s",
                            added, len(discovered_links), url)
    except Exception as e:
        logger.debug("[Scraper] Link discovery skipped for %s: %s", url, e)

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
    llm_calls = get_llm_call_count()
    # Very rough cost estimate: $0.01 per LLM call + browser time
    estimated_cost = (llm_calls * 0.01) + (fetch_ms / 1000.0 * 0.005)

    # ── Regression Intelligence: Compute severity from classification ──
    regression_severity = None
    if classification:
        from app.regression_capture import RegressionEntry
        # Build a temporary entry to classify severity
        temp_entry = RegressionEntry(
            id="", url=url, domain=intel.domain,
            failure_category=classification.category.value,
            failure_confidence=classification.confidence,
            captured_at=start_time,
        )
        regression_severity = get_regression_capture().classify_severity(temp_entry)

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
        regression_severity=regression_severity,
        extraction_method=ext_result.method,
        motifs_generated=len(new_motifs) if new_motifs else 0,
        motifs_used=solidified_motifs_count,
    )

    # ── Predictive Adaptation: Record observations ────────────────────
    # 1. Selector Decay Prediction: Track confidence trend
    try:
        decay_predictor = get_selector_decay_predictor()
        decay_predictor.record_observation(intel.domain, selector_hit_rate)
        
        # Log prediction if decay risk is elevated
        prediction = decay_predictor.predict_decay(intel.domain)
        if prediction.risk_level in ("decaying", "critical"):
            logger.info(
                "[PredictiveAdaptation] %s decay risk=%.2f level=%s days_until_failure=%.1f",
                intel.domain, prediction.decay_risk, prediction.risk_level,
                prediction.days_until_failure,
            )
    except Exception as e:
        logger.debug("[PredictiveAdaptation] Decay prediction failed: %s", e)
    
    # 2. Domain Evolution Model: Track mutations and anti-bot changes
    try:
        evolution_model = get_domain_evolution_model()
        if ext_result.method == "regex":
            # Regex fallback suggests selector drift → record mutation
            evolution_model.record_mutation(intel.domain)
        if anti_bot > 0.5:
            # Anti-bot escalation detected
            evolution_model.record_anti_bot_escalation(intel.domain, anti_bot)
    except Exception as e:
        logger.debug("[PredictiveAdaptation] Evolution modeling failed: %s", e)
    
    # 3. Self-Tuning Extraction: Feed telemetry for parameter adjustment
    try:
        tuning_controller = get_self_tuning_controller()
        tuning_controller.record_telemetry(intel.domain, {
            "fetch_ms": fetch_ms,
            "error": classification.category.value if classification else None,
            "failure_category": classification.category.value if classification else None,
            "anti_bot_score": anti_bot,
            "confidence_map": confidence_map,
        })
    except Exception as e:
        logger.debug("[PredictiveAdaptation] Self-tuning failed: %s", e)

    return results

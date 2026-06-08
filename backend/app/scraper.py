"""Scraping Engine — Thin orchestration layer with failure classification
and extraction provenance tracking.

Delegates to specialised sub-engines:
  - extraction_orchestrator:    Manages fallback cascade
  - html_utils:                DOM fetching, cleaning, contact extraction
  - scrape_telemetry:          Per-URL observability
  - cleaning_engine:           AI cleaning & schema alignment
  - insight_engine:            Data insight generation & schema suggestion
  - failure_classification:    Classify and recover from extraction failures
  - extraction_provenance:     Field-level extraction explainability

Refactored during Phase C: ``ScrapeAttemptResult`` moved to
``scraper_models``, adaptive hooks to ``scraper_adapt``, and
post-processing helpers to ``scraper_postprocess``.
"""

from __future__ import annotations

import contextlib
import logging
import time
from typing import TYPE_CHECKING, Any

from app.config import settings
from app.crawl_policy import get_crawl_policy
from app.extraction_orchestrator import orchestrate_extraction
from app.extraction_provenance import ProvenanceBuilder
from app.failure_classification import classify_failure, update_domain_with_failure
from app.html_utils import fetch_page_content
from app.metrics_collector import record_anti_bot_classification
from app.page_evidence_collector import collect_page_evidence
from app.regression_capture import get_regression_capture
from app.scrape_telemetry import (
    detect_anti_bot,
    detect_anti_bot_platform,
    estimate_dom_nodes,
    get_scrape_telemetry,
)
from app.scraper_adapt import run_all_adaptive_hooks
from app.scraper_models import ScrapeAttemptResult
from app.scraper_postprocess import (
    _build_acquisition_lineage_from_result,
    record_extraction_method_safe,
    run_post_extraction_processing,
)
from app.selector_profiles.loader import match_profile_for_url, try_profile_extraction
from app.zero_result_classifier import classify_zero_result

if TYPE_CHECKING:
    from app.models import SchemaField
    from app.recovery_strategies import AttemptContext

logger = logging.getLogger(__name__)

# ─── Re-exports for backward compatibility ────────────────────────────
# These symbols are imported by callers throughout the codebase.
from app.cleaning_engine import ai_clean_and_align_records
from app.crawl_frontier import get_crawl_frontier
from app.data_utils import _limit_source_records, process_raw_records
from app.html_utils import _boost_contacts_with_page_html

# Avoid pyflakes unused import errors for backward-compatibility re-exports
_ = (get_crawl_frontier, _boost_contacts_with_page_html, _limit_source_records)

__all__ = [
    "ScrapeAttemptResult",
    "ai_clean_and_align_records",
    "generate_data_insight",
    "scrape_url",
    "scrape_url_attempt",
    "suggest_schema_from_intent",
    "suggest_schema_from_intent_sync",
]


# ─── Re-export wrappers (insight_engine forwarding) ───────────────────


async def generate_data_insight(*args: Any, **kwargs: Any) -> Any:
    from app.insight_engine import generate_data_insight as impl

    return await impl(*args, **kwargs)


async def suggest_schema_from_intent(*args: Any, **kwargs: Any) -> Any:
    from app.insight_engine import suggest_schema_from_intent as impl

    return await impl(*args, **kwargs)


def suggest_schema_from_intent_sync(*args: Any, **kwargs: Any) -> Any:
    from app.insight_engine import suggest_schema_from_intent_sync as impl

    return impl(*args, **kwargs)


# ─── Internal helper: check crawl policy ─────────────────────────────


async def _check_crawl_policy(url: str) -> ScrapeAttemptResult | None:
    """Check if the crawl policy allows scraping this URL.

    Returns a ``ScrapeAttemptResult`` with empty records if blocked,
    or ``None`` if allowed.
    """
    policy = get_crawl_policy()
    blocked_reason = await policy.check_domain(url)
    if not blocked_reason:
        return None

    logger.warning("Crawl policy blocked %s: %s", url, blocked_reason)
    telemetry = get_scrape_telemetry()
    telemetry.record(url=url, error=blocked_reason)
    record_extraction_method_safe("blocked")
    return ScrapeAttemptResult(
        [],
        html=None,
        final_url=url,
        telemetry=telemetry,
        extraction_method=None,
        zero_result_classification=None,
        recommended_next_action="resolve_crawl_restrictions",
        warnings=[f"Crawl policy blocked: {blocked_reason}"],
    )


# ─── Internal helper: try profile-based extraction ───────────────────


async def _try_profile_extraction(
    url: str,
    schema_fields: list[SchemaField],
    min_record_score: float,
    user_intent: str,
    selectors_map: dict | None,  # noqa: ARG001, RUF100
    attempt_ctx: AttemptContext | None,  # noqa: ARG001, RUF100
    skip_profiles: bool = False,
) -> tuple[ScrapeAttemptResult | None, dict | None, str | None]:
    """Try profile-based extraction as the first extraction strategy.

    Returns a tuple of (result, matched_profile, fetch_method) where:
    - ``result`` is a ``ScrapeAttemptResult`` if successful, or ``None``
    - ``matched_profile`` is the profile name if matched, or ``None``
    - ``fetch_method`` is the fetch method string, or ``None``

    If profile extraction returns results with good field-name overlap,
    the results are processed and returned immediately. Otherwise the
    function falls through (returns ``None`` for the result).
    """
    matched_profile = None
    if skip_profiles:
        logger.info("[Recovery] force_llm_discovery set — skipping profile-based extraction")
        matched_profile = None
    else:
        matched_profile = match_profile_for_url(url)
        try:
            profile_results = await try_profile_extraction(url, max_wait=settings.PROFILE_MAX_WAIT)
        except Exception:
            get_crawl_policy().record_result(url, success=False)
            raise

    if matched_profile and matched_profile.get("fields") and profile_results is not None:
        logger.info(
            "Profile-based extraction returned %d records for %s",
            len(profile_results),
            url,
        )
        if profile_results:
            profile_keys = {k.lower() for r in profile_results for k in r if not k.startswith("_")}
            schema_keys = {f.name.lower() for f in schema_fields}
            schema_match = len(profile_keys & schema_keys) / max(len(schema_keys), 1)
            profile_match = len(profile_keys & schema_keys) / max(len(profile_keys), 1)
            if schema_match < 0.6 or profile_match < 0.5:
                logger.info(
                    "Profile field names don't match schema (s=%.0f%% p=%.0f%%) — falling through",
                    schema_match * 100,
                    profile_match * 100,
                )
            else:
                profile_field_defs = matched_profile.get("fields") if matched_profile else None
                results = process_raw_records(
                    profile_results,
                    schema_fields,
                    min_record_score,
                    profile_fields=profile_field_defs,
                    user_intent=user_intent,
                )
                telemetry = get_scrape_telemetry()
                telemetry.record(
                    url=url,
                    profile_match=True,
                    profile_records=len(profile_results),
                    records_final=len(results),
                )
                get_crawl_policy().record_result(url, success=True)
                record_extraction_method_safe("profile")
                return (
                    ScrapeAttemptResult(
                        results,
                        html=None,
                        final_url=url,
                        fetch_method="profile",
                        telemetry=telemetry,
                        extraction_method="profile",
                        zero_result_classification=None,
                        data_evidence_score=min(1.0, len(results) / 10.0),
                    ),
                    matched_profile,
                    "profile",
                )

        logger.info("Profile matched but returned 0 records, falling through to generic pipeline")
    return None, matched_profile, None


# ─── Internal helper: session-bound recovery ─────────────────────────


async def _try_session_recovery(html: str, url: str, search_params: dict | None) -> str | None:
    """Attempt session-bound search form recovery if the URL is session-bound.

    Returns recovered HTML if successful, or ``None`` if no recovery
    was needed or possible.
    """
    if search_params:
        try:
            from app.session_url_detector import detect_session_params

            session_detect = detect_session_params(url)
            if session_detect.get("is_session_bound"):
                logger.info("[SessionRecovery] URL %s is session-bound — checking for search form", url)
                from app.selector_discovery import _detect_search_form, _try_form_search_recovery

                form_info = _detect_search_form(html)
                if form_info.get("detected"):
                    logger.info("[SessionRecovery] Search form detected — attempting recovery")
                    recovery_result = await _try_form_search_recovery(
                        landing_page_html=html,
                        landing_page_url=url,
                        search_params=search_params,
                    )
                    if recovery_result.get("success") and recovery_result.get("fresh_html"):
                        return recovery_result["fresh_html"]
                    logger.warning("[SessionRecovery] Recovery failed: %s", recovery_result.get("error", "unknown"))
                else:
                    logger.info("[SessionRecovery] No search form detected on %s", url)
        except Exception as recovery_err:
            logger.warning("[SessionRecovery] Recovery attempt failed for %s: %s", url, recovery_err)
    elif not search_params:
        try:
            from app.session_url_detector import detect_session_params

            session_detect = detect_session_params(url)
            if session_detect.get("is_session_bound"):
                logger.warning(
                    "[SessionRecovery] URL %s is session-bound but no search_params provided",
                    url,
                )
        except Exception:  # nosec B110  # noqa: RUF100, S110
            pass  # nosec B110
    return None


# ─── Internal helper: zero-result classification ─────────────────────


async def _classify_and_capture_zero_result(
    url: str,
    html: str,
    fetch_method: str,
    anti_bot_score: float,
    schema_fields: list[SchemaField],
    ext_result: Any,
    is_failure_page: bool,
    classification: Any | None,
    start_time: float,  # noqa: ARG001, RUF100
) -> tuple[Any | None, str | None, list[str]]:
    """Classify zero-result scenarios and capture regression candidates.

    Returns (zero_classification, zero_result_failure_class, warnings).
    """
    from bs4 import BeautifulSoup

    from app.empty_response_detector import detect_empty_response
    from app.session_url_detector import detect_session_params

    session_detection = detect_session_params(url) if url else None
    empty_check = detect_empty_response(html) if html else None
    evidence = collect_page_evidence(html, url=url)
    soup_for_density = BeautifulSoup(html, "html.parser")
    visible_text = soup_for_density.get_text() if html else ""

    potential_zero_classification = classify_zero_result(
        acquisition_lineage={"state": fetch_method},
        session_detection=session_detection,
        empty_check=empty_check.to_dict() if empty_check is not None and hasattr(empty_check, "to_dict") else None,
        anti_bot_score=anti_bot_score,
        final_url=url,
        html=html,
        visible_text=visible_text,
        detected_forms=evidence.forms if evidence else None,
        detected_containers=len(evidence.candidate_containers) if evidence else 0,
        raw_candidate_count=len(evidence.candidate_containers) if evidence else 0,
        schema_fields=[f.name for f in schema_fields],
    )

    warnings: list[str] = []

    if not ext_result.records or is_failure_page:
        zero_classification = potential_zero_classification
        if not classification:
            classification = classify_failure(
                telemetry={
                    "fetch_method": fetch_method,
                    "anti_bot_score": anti_bot_score,
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
                from app.domain_intelligence import get_domain_intelligence

                update_domain_with_failure(get_domain_intelligence(), url, classification)

        if zero_classification:
            logger.info(
                "[ZeroResult] %s — %s (confidence=%.2f)",
                zero_classification.failure_class,
                zero_classification.user_message,
                zero_classification.confidence,
            )

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
                    "anti_bot_score": anti_bot_score,
                    "selector_hit_rate": 0.0,
                    "records_final": 0,
                },
            )

        return zero_classification, zero_classification.failure_class if zero_classification else None, warnings

    # Low-quality extraction
    if any(r.get("record_score", 1.0) < settings.DEFAULT_MIN_RECORD_SCORE * 0.5 for r in ext_result.records):
        get_regression_capture().maybe_capture(
            url=url,
            html=html,
            failure_category="low_quality_extraction",
            failure_confidence=0.6,
            records_count=len(ext_result.records),
            schema_fields=[f.name for f in schema_fields],
            force=True,
        )

    return None, None, warnings


# ─── Internal helper: build fetch response on failure ─────────────────


def _build_fetch_failure_result(
    url: str,
    fetch_method: str,
    classification: Any | None,
    e: Exception,
    start_time: float,
    telemetry: Any,
) -> ScrapeAttemptResult:
    """Build a ScrapeAttemptResult for a fetch failure, with classification and telemetry."""
    from app.recovery_strategies import RecoveryAction

    fetch_ms = (time.time() - start_time) * 1000
    logger.exception("Failed to fetch %s", url)

    provenance_builder = ProvenanceBuilder(url, "")
    provenance_builder.add_error(f"Fetch failed: {e}")
    if classification:
        provenance_builder.add_error(f"Classified: {classification.category.value}")

    telemetry.record(
        url=url, error=str(e), fetch_ms=fetch_ms, failure_category=classification.category.value if classification else None
    )

    get_crawl_policy().record_result(url, success=False)
    recommended_next_action = ""
    if classification:
        try:
            recommended_next_action = RecoveryAction(classification.recovery_strategy).value
        except (ValueError, AttributeError):
            recommended_next_action = classification.recovery_strategy

    record_extraction_method_safe("fetch_failed")
    return ScrapeAttemptResult(
        [],
        html=None,
        final_url=url,
        fetch_method=fetch_method,
        telemetry=telemetry,
        extraction_method=fetch_method,
        zero_result_classification=None,
        recommended_next_action=recommended_next_action,
        warnings=[f"Fetch failed: {e}"],
    )


# ─── Main entry points ────────────────────────────────────────────────


async def scrape_url_attempt(
    url: str,
    schema_fields: list[SchemaField],
    min_record_score: float | None = None,
    user_intent: str = "",
    world_state=None,
    selectors_map: dict | None = None,
    search_params: dict[str, str] | None = None,
    attempt_ctx: AttemptContext | None = None,
) -> ScrapeAttemptResult:
    """Scrape a single URL and return an enriched ScrapeAttemptResult
    with full metadata (HTML, telemetry, acquisition lineage, zero-result
    classification, and warnings).

    This is the preferred entry point for callers that need rich diagnostics.
    ``scrape_url()`` is a backward-compatible wrapper that also returns
    a ScrapeAttemptResult (a ``list`` subclass).
    """
    from app.recovery_strategies import AttemptContext as AttemptContextType

    if attempt_ctx is not None and not isinstance(attempt_ctx, AttemptContextType):
        attempt_ctx = None

    raw = await scrape_url(
        url,
        schema_fields,
        min_record_score=min_record_score,
        user_intent=user_intent,
        world_state=world_state,
        selectors_map=selectors_map,
        search_params=search_params,
        attempt_ctx=attempt_ctx,
    )

    records = list(raw)
    result_html: str | None = getattr(raw, "html", None)
    result_fetch_method: str | None = getattr(raw, "fetch_method", None)
    result_extraction_method: str | None = getattr(raw, "extraction_method", None)
    result_telemetry: Any = getattr(raw, "telemetry", None)
    result_zero_classification: Any = getattr(raw, "zero_result_classification", None)
    result_anti_bot_score: float = getattr(raw, "anti_bot_score", 0.0)
    result_data_evidence_score: float = getattr(raw, "data_evidence_score", 0.0)
    result_recommended_action: str = getattr(raw, "recommended_next_action", "")
    result_warnings: list[str] = getattr(raw, "warnings", [])

    state = "direct"
    if result_zero_classification:
        cls = result_zero_classification.failure_class
        if cls == "anti_bot_block":
            state = "anti_bot_blocked"
        elif cls == "empty_response":
            state = "empty_response"
        elif cls in ("session_bound_url", "search_replay_required"):
            state = "session_expired"
        elif cls == "js_render_required":
            state = "empty_response"
    elif not records and not result_zero_classification:
        state = "empty_response"

    result = ScrapeAttemptResult(
        records,
        html=result_html,
        final_url=url,
        fetch_method=result_fetch_method,
        extraction_method=result_extraction_method,
        telemetry=result_telemetry,
        zero_result_classification=result_zero_classification,
        anti_bot_score=result_anti_bot_score,
        data_evidence_score=result_data_evidence_score,
        recommended_next_action=result_recommended_action,
        warnings=result_warnings,
    )
    result.network_diagnostics = getattr(raw, "network_diagnostics", [])
    result.acquisition_lineage = _build_acquisition_lineage_from_result(url, result, state=state)

    return result


async def scrape_url(
    url: str,
    schema_fields: list[SchemaField],
    min_record_score: float | None = None,
    user_intent: str = "",
    world_state=None,
    selectors_map: dict | None = None,
    search_params: dict[str, str] | None = None,
    attempt_ctx: AttemptContext | None = None,
) -> list[dict]:
    """Orchestrate the full extraction flow for a single URL.

    Returns a ``ScrapeAttemptResult`` (a ``list`` subclass) that behaves as
    a plain ``list[dict]`` for backward compatibility while carrying
    metadata attributes (html, telemetry, acquisition_lineage, etc.).

    For callers that need the richest possible metadata, use
    ``scrape_url_attempt()`` instead.
    """
    from bs4 import BeautifulSoup

    from app.domain_intelligence import get_domain_intelligence
    from app.recovery_strategies import AttemptContext
    from app.strategy_evolution import FetchStrategy, get_strategy_evolution_engine  # research-shell, lazy

    if attempt_ctx is not None and not isinstance(attempt_ctx, AttemptContext):
        attempt_ctx = None
    if min_record_score is None:
        min_record_score = settings.DEFAULT_MIN_RECORD_SCORE
    if attempt_ctx and attempt_ctx.min_record_score_override is not None:
        min_record_score = attempt_ctx.min_record_score_override
        logger.info("[Recovery] Using min_record_score override: %.2f", min_record_score)

    logger.info("Fetching: %s", url)
    telemetry = get_scrape_telemetry()
    from app.llm_bridge import reset_llm_call_count

    reset_llm_call_count()
    start_time = time.time()

    # ── Step 0: Check crawl policy ────────────────────────────────
    blocked_result = await _check_crawl_policy(url)
    if blocked_result is not None:
        return blocked_result

    # ── Step 1: Clone selectors_map, transfer recovery flags ──────
    if selectors_map is not None:
        selectors_map = dict(selectors_map)
        if "fields" in selectors_map and isinstance(selectors_map["fields"], dict):
            selectors_map["fields"] = dict(selectors_map["fields"])
    if attempt_ctx:
        if selectors_map is None:
            selectors_map = {}
        if attempt_ctx.force_llm_discovery:
            selectors_map["force_llm_discovery"] = True
        if attempt_ctx.bypass_selector_memory:
            selectors_map["bypass_selector_memory"] = True
        if attempt_ctx.force_container_discovery:
            selectors_map["force_container_discovery"] = True

    # ── Step 2: Try profile-based extraction ──────────────────────
    skip_profiles = bool(attempt_ctx and attempt_ctx.force_llm_discovery)
    profile_result, matched_profile, profile_fetch_method = await _try_profile_extraction(
        url,
        schema_fields,
        min_record_score,
        user_intent,
        selectors_map,
        attempt_ctx,
        skip_profiles,
    )
    if profile_result is not None:
        return profile_result

    # ── Step 3: Generic extraction pipeline ───────────────────────
    intel = get_domain_intelligence().get_intelligence(url)
    strategy_engine = get_strategy_evolution_engine()

    recommended_strategy = strategy_engine.evolve_strategy(intel.domain)
    logger.info("[Scraper] Selected strategy for %s: %s", url, recommended_strategy.value)

    provenance_builder = ProvenanceBuilder(url, intel.domain)

    # ── Fetch ─────────────────────────────────────────────────────
    fetch_success = False
    classification = None
    js_render_delay = 0.0
    fetch_method = recommended_strategy.value
    retry_count = 0
    try:
        fetch_start = time.time()
        fetch_strategy = recommended_strategy
        if attempt_ctx and getattr(attempt_ctx, "fetch_strategy", None):
            with contextlib.suppress(ValueError):
                if attempt_ctx.fetch_strategy is not None:
                    fetch_strategy = FetchStrategy(attempt_ctx.fetch_strategy)
        html, js_render_delay, fetch_method, retry_count = await fetch_page_content(
            url,
            preferred_method=fetch_strategy,
            timeout_ms=attempt_ctx.timeout_ms if attempt_ctx else None,
            hydration_wait_ms=attempt_ctx.hydration_wait_ms if attempt_ctx else None,
            skip_networkidle=attempt_ctx.skip_networkidle if attempt_ctx else False,
            scroll_attempts=attempt_ctx.scroll_attempts if attempt_ctx else None,
            anti_bot_stealth=attempt_ctx.anti_bot_stealth if attempt_ctx else False,
            extra_headers=attempt_ctx.extra_headers if attempt_ctx else None,
        )
        fetch_ms = (time.time() - fetch_start) * 1000
        fetch_success = True
    except Exception as e:
        fetch_ms = (time.time() - start_time) * 1000
        strategy_engine.record_fetch_attempt(
            intel.domain, recommended_strategy, success=False, time_ms=fetch_ms, failure_reason=type(e).__name__
        )
        classification = classify_failure(error_message=str(e), fetch_method=fetch_method)
        get_regression_capture().maybe_capture(
            url=url,
            html=None,
            failure_category=classification.category.value if classification else "unknown",
            failure_confidence=classification.confidence if classification else 0.0,
            records_count=0,
            schema_fields=[f.name for f in schema_fields],
        )
        return _build_fetch_failure_result(url, fetch_method, classification, e, start_time, telemetry)

    get_crawl_policy().record_result(url, success=fetch_success)

    # ── Session-Bound Search Form Recovery ────────────────────────
    recovered_html = await _try_session_recovery(html, url, search_params)
    if recovered_html is not None:
        html = recovered_html

    # ── Anti-Bot Detection ────────────────────────────────────────
    anti_bot = detect_anti_bot(html)
    dom_nodes = estimate_dom_nodes(html)

    try:
        if anti_bot >= settings.ANTIBOT_HARD_BLOCK_THRESHOLD or anti_bot >= settings.CLASSIFY_ANTIBOT_SCORE_THRESHOLD:
            record_anti_bot_classification(detect_anti_bot_platform(html) or "anti_bot_block")
        else:
            record_anti_bot_classification("ok")
    except (ImportError, AttributeError, TypeError, ValueError, RuntimeError, OSError, KeyError):  # nosec B110
        pass

    soup_for_density = BeautifulSoup(html, "html.parser")
    token_density = len(soup_for_density.get_text()) / max(1, dom_nodes)

    # ── Solidified motifs count pre-extraction ────────────────────
    solidified_motifs_count = 0
    if world_state and hasattr(world_state, "solidified_motifs"):
        from contextlib import suppress

        with suppress(Exception):
            solidified_motifs_count = len(world_state.solidified_motifs)

    # ── Step 4: Extraction Cascade ─────────────────────────────────
    result_warnings: list[str] = []
    ext_result = await orchestrate_extraction(
        url,
        html,
        schema_fields,
        min_record_score,
        provenance_builder=provenance_builder,
        world_state=world_state,
        user_intent=user_intent,
        provided_selectors=selectors_map,
        warnings=result_warnings,
    )

    # ── Post-extraction semantic validation ───────────────────────
    from app.utils.quality import post_extract_validate_records

    results = post_extract_validate_records(ext_result.records, schema_fields, warnings=result_warnings)
    for r in results:
        r["_extraction_method"] = ext_result.method
        r["_extraction_source"] = ext_result.method
        r["_extraction_confidence"] = r.get("record_score", 0.8)
        r["_extraction_provenance"] = ext_result.selectors

    provenance_builder.set_extraction_method(ext_result.method)
    provenance_builder.set_memory_hit(ext_result.method == "memory")
    if ext_result.method == "regex":
        provenance_builder.add_fallback_step("regex")

    record_extraction_method_safe(ext_result.method)

    # ── Strategy Engine Feedback ──────────────────────────────────
    avg_score = 0.0
    if results:
        avg_score = sum(r.get("record_score", 0.0) for r in results) / len(results)
    strategy_engine.record_fetch_attempt(
        intel.domain,
        recommended_strategy,
        success=True,
        time_ms=fetch_ms,
        quality=avg_score,
    )

    # ── Step 5: Motif Feedback ────────────────────────────────────
    new_motifs = run_all_adaptive_hooks(
        url=url,
        html=html,
        domain=intel.domain,
        results=results,
        schema_fields=schema_fields,
        world_state=world_state,
        extraction_method=ext_result.method,
        fetch_ms=fetch_ms,
        selector_hit_rate=0.0,
        confidence_map=None,
        classification=classification,
        anti_bot_score=anti_bot,
    )

    # ── Step 6: Post-extraction processing ────────────────────────
    results, result_warnings = await run_post_extraction_processing(
        url=url,
        html=html,
        schema_fields=schema_fields,
        min_record_score=min_record_score,
        results=results,
        ext_result=ext_result,
        fetch_method=fetch_method,
        fetch_ms=fetch_ms,
        provenance_builder=provenance_builder,
        classification=classification,
        domain=intel.domain,
        new_motifs=new_motifs,
        solidified_motifs_count=solidified_motifs_count,
        anti_bot_score=anti_bot,
        js_render_delay=js_render_delay,
        token_density=token_density,
        retry_count=retry_count,
    )

    # ── Step 7: Zero-Result Classification ────────────────────────
    is_failure_page = False  # Always false here; zero-result detection handles this
    zero_classification, zero_result_failure_class, _ = await _classify_and_capture_zero_result(
        url=url,
        html=html,
        fetch_method=fetch_method,
        anti_bot_score=anti_bot,
        schema_fields=schema_fields,
        ext_result=ext_result,
        is_failure_page=is_failure_page,
        classification=classification,
        start_time=start_time,
    )

    res_warnings = list(result_warnings)
    if not results and zero_result_failure_class:
        logger.info(
            "[Scraper] Zero records for %s — failure_class=%s",
            url,
            zero_result_failure_class,
        )
        recommended_next_action = zero_classification.recommended_action if zero_classification else ""
        return ScrapeAttemptResult(
            [],
            html=html,
            final_url=url,
            fetch_method=fetch_method,
            telemetry=telemetry,
            extraction_method=ext_result.method if "ext_result" in locals() else None,
            zero_result_classification=zero_classification,
            anti_bot_score=anti_bot,
            recommended_next_action=recommended_next_action,
            warnings=res_warnings,
            network_diagnostics=getattr(ext_result, "network_diagnostics", []),
        )

    data_evidence_score = min(1.0, len(results) / 10.0) if results else 0.0
    return ScrapeAttemptResult(
        results,
        html=html,
        final_url=url,
        fetch_method=fetch_method,
        telemetry=telemetry,
        extraction_method=ext_result.method if "ext_result" in locals() else None,
        zero_result_classification=zero_classification,
        anti_bot_score=anti_bot,
        data_evidence_score=data_evidence_score,
        warnings=res_warnings,
        network_diagnostics=getattr(ext_result, "network_diagnostics", []),
    )


# Backward-compatible alias used by tests
_record_extraction_method_safe = record_extraction_method_safe

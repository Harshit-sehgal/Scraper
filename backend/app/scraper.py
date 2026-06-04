"""Scraping Engine — Thin orchestration layer with failure classification
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

import contextlib
import logging
import time
from typing import TYPE_CHECKING, Any
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from app.cleaning_engine import ai_clean_and_align_records
from app.compound_record_assembler import assemble_compound_records
from app.config import settings
from app.crawl_frontier import get_crawl_frontier
from app.crawl_policy import get_crawl_policy
from app.data_utils import (
    _limit_source_records as _base_limit_source_records,
)
from app.data_utils import (
    process_raw_records,
)
from app.extraction_orchestrator import orchestrate_extraction
from app.extraction_provenance import (
    ProvenanceBuilder,
    enrich_records_with_provenance,
)
from app.failure_classification import (
    classify_failure,
    update_domain_with_failure,
)
from app.html_utils import (
    _boost_contacts_with_page_html,
    _is_empty_value,
    fetch_page_content,
)
from app.page_evidence_collector import collect_page_evidence
from app.regression_capture import get_regression_capture
from app.scrape_telemetry import (
    detect_anti_bot,
    estimate_dom_nodes,
    get_scrape_telemetry,
)
from app.selector_profiles.loader import match_profile_for_url, try_profile_extraction
from app.zero_result_classifier import classify_zero_result

logger = logging.getLogger(__name__)


class ScrapeAttemptResult(list):
    """Subclass of list that holds rich metadata about a scrape attempt.

    Behaves as a plain list of records for backward compatibility while
    carrying context about how the page was fetched, extracted, and classified.
    """

    def __init__(
        self,
        records: list[dict],
        html: str | None = None,
        final_url: str | None = None,
        fetch_method: str | None = None,
        extraction_method: str | None = None,
        telemetry: Any = None,
        zero_result_classification: Any = None,
        acquisition_lineage: dict | None = None,
        anti_bot_score: float = 0.0,
        data_evidence_score: float = 0.0,
        recommended_next_action: str = "",
        warnings: list[str] | None = None,
        network_diagnostics: list[str] | None = None,
    ) -> None:
        super().__init__(records)
        self.html = html
        self.final_url = final_url
        self.fetch_method = fetch_method
        self.extraction_method = extraction_method
        self.telemetry = telemetry
        self.zero_result_classification = zero_result_classification
        self.acquisition_lineage = acquisition_lineage
        self.anti_bot_score = anti_bot_score
        self.data_evidence_score = data_evidence_score
        self.recommended_next_action = recommended_next_action
        self.warnings = warnings or []
        self.network_diagnostics = network_diagnostics or []

    def to_telemetry_dict(self) -> dict:
        """Return scrape metadata as a dict for diagnostics."""
        return {
            "records": len(self),
            "html_length": len(self.html) if self.html else 0,
            "final_url": self.final_url,
            "fetch_method": self.fetch_method,
            "extraction_method": self.extraction_method,
            "anti_bot_score": self.anti_bot_score,
            "data_evidence_score": self.data_evidence_score,
            "recommended_next_action": self.recommended_next_action,
            "zero_result_classification": (
                self.zero_result_classification.to_dict() if self.zero_result_classification else None
            ),
            "warnings": self.warnings,
        }


if TYPE_CHECKING:
    from app.models import SchemaField
    from app.recovery_strategies import AttemptContext

# Re-export for backwards compatibility (used by routers / jobs.py and
# services / job_runner.py)

__all__ = [
    "ScrapeAttemptResult",
    "ai_clean_and_align_records",
    "generate_data_insight",
    "scrape_url",
    "scrape_url_attempt",
    "suggest_schema_from_intent",
    "suggest_schema_from_intent_sync",
]


async def generate_data_insight(*args: Any, **kwargs: Any) -> Any:
    from app.insight_engine import generate_data_insight as impl

    return await impl(*args, **kwargs)


async def suggest_schema_from_intent(*args: Any, **kwargs: Any) -> Any:
    from app.insight_engine import suggest_schema_from_intent as impl

    return await impl(*args, **kwargs)


def suggest_schema_from_intent_sync(*args: Any, **kwargs: Any) -> Any:
    from app.insight_engine import suggest_schema_from_intent_sync as impl

    return impl(*args, **kwargs)


def _limit_source_records(records: list[dict], schema_fields: list[SchemaField]) -> list[dict]:
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

    # Safely extract records and metadata — handles both ScrapeAttemptResult
    # and plain list (e.g. when monkeypatched in tests).
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

    # Determine state for acquisition lineage
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

    # Build the enriched result with all metadata
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
    # Build acquisition lineage from the enriched result
    result.acquisition_lineage = _build_acquisition_lineage_from_result(
        url=url,
        result=result,
        state=state,
    )

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
    from app.recovery_strategies import AttemptContext

    if attempt_ctx is not None and not isinstance(attempt_ctx, AttemptContext):
        attempt_ctx = None  # Safety: only accept proper AttemptContext
    if min_record_score is None:
        min_record_score = settings.DEFAULT_MIN_RECORD_SCORE
    # Apply recovery min_record_score_override if set
    if attempt_ctx and attempt_ctx.min_record_score_override is not None:
        min_record_score = attempt_ctx.min_record_score_override
        logger.info("[Recovery] Using min_record_score override: %.2f", min_record_score)

    logger.info("Fetching: %s", url)
    telemetry = get_scrape_telemetry()
    from app.llm_bridge import get_llm_call_count, reset_llm_call_count

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

    # ── Step 1: Try profile-based extraction first ──────────────────
    # Clone selectors_map to prevent recovery flags from leaking across
    # concurrent URL extracts (job.selectors_map is shared across tasks).
    if selectors_map is not None:
        selectors_map = dict(selectors_map)
        if "fields" in selectors_map and isinstance(selectors_map["fields"], dict):
            selectors_map["fields"] = dict(selectors_map["fields"])
    # Transfer recovery flags to the cloned selectors_map so orchestrator can
    # consume them.
    if attempt_ctx:
        if selectors_map is None:
            selectors_map = {}
        if attempt_ctx.force_llm_discovery:
            selectors_map["force_llm_discovery"] = True
        if attempt_ctx.bypass_selector_memory:
            selectors_map["bypass_selector_memory"] = True
        if attempt_ctx.force_container_discovery:
            selectors_map["force_container_discovery"] = True

    # If recovery requested force_llm_discovery, skip profiles entirely.
    # A normal AttemptContext should not disable profile extraction.
    skip_profiles = bool(attempt_ctx and attempt_ctx.force_llm_discovery)
    if skip_profiles:
        logger.info("[Recovery] force_llm_discovery set — skipping profile-based extraction")
        matched_profile = None
        profile_results = None
    else:
        matched_profile = match_profile_for_url(url)
        try:
            profile_results = await try_profile_extraction(url, max_wait=settings.PROFILE_MAX_WAIT)
        except Exception:
            policy.record_result(url, success=False)
            raise
    if profile_results is not None:
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
                    "Profile field names don't match schema (s=%.0f%% p=%.0f%%) — falling through to generic pipeline",
                    schema_match * 100,
                    profile_match * 100,
                )
            else:
                profile_field_defs = (matched_profile or {}).get("fields") if matched_profile else None
                results = process_raw_records(
                    profile_results,
                    schema_fields,
                    min_record_score,
                    profile_fields=profile_field_defs,
                    user_intent=user_intent,
                )
                telemetry.record(
                    url=url,
                    profile_match=True,
                    profile_records=len(profile_results),
                    records_final=len(results),
                    fetch_ms=(time.time() - start_time) * 1000,
                )
                policy.record_result(url, success=True)
                return ScrapeAttemptResult(
                    results,
                    html=None,
                    final_url=url,
                    fetch_method="profile",
                    telemetry=telemetry,
                    extraction_method="profile",
                    zero_result_classification=None,
                    data_evidence_score=min(1.0, len(results) / 10.0),
                )

        logger.info("Profile matched but returned 0 records, falling through to generic pipeline")

    # ── Generic extraction pipeline ────────────────────────────────
    from app.domain_intelligence import get_domain_intelligence
    from app.strategy_evolution import FetchStrategy, get_strategy_evolution_engine  # research-shell, lazy

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
        logger.exception("Failed to fetch %s", url)

        # Record failure in strategy engine
        strategy_engine.record_fetch_attempt(
            intel.domain,
            recommended_strategy,
            success=False,
            time_ms=fetch_ms,
            failure_reason=type(e).__name__,
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

        # Capture regression candidates for future benchmark expansion
        get_regression_capture().maybe_capture(
            url=url,
            html=None,
            failure_category=classification.category.value,
            failure_confidence=classification.confidence,
            records_count=0,
            schema_fields=[f.name for f in schema_fields],
        )

        policy.record_result(url, success=False)
        recommended_next_action = ""
        if classification:
            from app.recovery_strategies import RecoveryAction

            try:
                recommended_next_action = RecoveryAction(classification.recovery_strategy).value
            except (ValueError, AttributeError):
                recommended_next_action = classification.recovery_strategy
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

    policy.record_result(url, success=fetch_success)

    # ── Session-Bound Search Form Recovery ───────────────────────────
    # If the URL is session-bound (detected from param analysis) AND
    # search_params are provided, attempt to replay the search form
    # to get a fresh results page instead of a stale / expired landing page.
    recovered_html = None
    if search_params:
        try:
            from app.session_url_detector import detect_session_params

            session_detect = detect_session_params(url)
            if session_detect.get("is_session_bound"):
                logger.info(
                    "[SessionRecovery] URL %s is session-bound — checking for search form",
                    url,
                )
                from app.selector_discovery import _detect_search_form, _try_form_search_recovery

                form_info = _detect_search_form(html)
                if form_info.get("detected"):
                    logger.info(
                        "[SessionRecovery] Search form detected at '%s' — attempting recovery",
                        form_info.get("action", ""),
                    )
                    recovery_result = await _try_form_search_recovery(
                        landing_page_html=html,
                        landing_page_url=url,
                        search_params=search_params,
                    )
                    if recovery_result.get("success") and recovery_result.get("fresh_html"):
                        recovered_html = recovery_result["fresh_html"]
                        html = recovered_html
                        logger.info(
                            "[SessionRecovery] Recovery succeeded — using fresh session page: %s",
                            recovery_result.get("fresh_url", url),
                        )
                    else:
                        logger.warning(
                            "[SessionRecovery] Recovery failed for %s: %s",
                            url,
                            recovery_result.get("error", "unknown"),
                        )
                else:
                    logger.info(
                        "[SessionRecovery] No search form detected on %s — proceeding with original HTML",
                        url,
                    )
        except Exception as recovery_err:
            logger.warning(
                "[SessionRecovery] Recovery attempt failed for %s: %s",
                url,
                recovery_err,
            )
    elif not search_params:
        try:
            from app.session_url_detector import detect_session_params

            session_detect = detect_session_params(url)
            if session_detect.get("is_session_bound"):
                logger.warning(
                    "[SessionRecovery] URL %s is session-bound but no search_params provided — page may be stale",
                    url,
                )
        except Exception:
            pass  # nosec B110

    anti_bot = detect_anti_bot(html)
    dom_nodes = estimate_dom_nodes(html)

    # Calculate token density
    soup_for_density = BeautifulSoup(html, "html.parser")
    page_text = soup_for_density.get_text()
    token_density = len(page_text) / max(1, dom_nodes)

    # ── Step 2 - 4: Extraction Cascade ──────────────────────────────
    # Capture solidified_motifs count before extraction for telemetry
    solidified_motifs_count = 0
    if world_state and hasattr(world_state, "solidified_motifs"):
        try:
            solidified_motifs_count = len(world_state.solidified_motifs)
        except Exception:
            pass  # nosec B110

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

    # Run post-extraction semantic validation
    from app.utils.quality import post_extract_validate_records

    results = post_extract_validate_records(ext_result.records, schema_fields, warnings=result_warnings)

    for r in results:
        r["_extraction_method"] = ext_result.method
        r["_extraction_source"] = ext_result.method
        r["_extraction_confidence"] = r.get("record_score", 0.8)
        r["_extraction_provenance"] = ext_result.selectors

    # Track extraction method in provenance
    provenance_builder.set_extraction_method(ext_result.method)
    provenance_builder.set_memory_hit(ext_result.method == "memory")
    if ext_result.method == "regex":
        provenance_builder.add_fallback_step("regex")

    # Phase 80: Record successful attempt and extraction quality
    avg_score = 0.0
    if results:
        avg_score = sum(r.get("record_score", 0.0) for r in results) / len(results)

    strategy_engine.record_fetch_attempt(intel.domain, recommended_strategy, success=True, time_ms=fetch_ms, quality=avg_score)

    # ── Autonomous Adaptation: Close Motif Feedback Loop ──────────
    # Extract field co-occurrence motifs from results and feed back
    # into world_state for improved future selector discovery.
    new_motifs = []
    if results and world_state:
        from app.motif_feedback import MotifFeedbackEngine  # research-shell, lazy

        feedback_engine = MotifFeedbackEngine()
        new_motifs = feedback_engine.extract_motifs_from_results(
            results,
            schema_fields,
            min_cooccurrence=settings.MOTIF_MIN_COOCCURRENCE,
        )
        if new_motifs:
            # Merge into world_state atomically. The public method takes
            # the substrate lock so concurrent extractions don't lose
            # updates via read-modify-write races.
            if hasattr(world_state, "add_solidified_motifs"):
                added = world_state.add_solidified_motifs(new_motifs)
            else:
                # Older world_state implementations: fall back to a
                # best-effort, non-atomic merge through history.
                added = 0
                if hasattr(world_state, "_history") and hasattr(world_state._history, "add_solidified_motifs"):
                    added = world_state._history.add_solidified_motifs(new_motifs)
            logger.info(
                "[Scraper] Closed motif feedback loop: %d new motifs (of %d candidates) from %d results",
                added,
                len(new_motifs),
                len(results),
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
            href_val = a_tag.get("href")
            href = href_val[0] if isinstance(href_val, list) else str(href_val) if href_val else ""
            if not href:
                continue
            if href.startswith("http") and intel.domain in urlparse(href).netloc:
                discovered_links.append(href)
            elif href.startswith(("/", "?")):
                full_url = urljoin(url, href)
                if intel.domain in urlparse(full_url).netloc:
                    discovered_links.append(full_url)

        if discovered_links:
            frontier = get_crawl_frontier()
            added = await frontier.add_discovered_links(discovered_links, url, source_depth=0)
            if added > 0:
                logger.debug("[Scraper] Added %d/%d discovered links to frontier from %s", added, len(discovered_links), url)
    except Exception as e:
        logger.debug("[Scraper] Link discovery skipped for %s: %s", url, e)

    # ── Zero-Result Classification & Failure Classification ────────────
    zero_classification = None
    zero_result_failure_class = None
    # Check for session-bound URL signals and empty response indicators
    from app.session_url_detector import detect_session_params

    session_detection = detect_session_params(url) if url else None
    from app.empty_response_detector import detect_empty_response

    empty_check = detect_empty_response(html) if html else None

    # Collect page evidence for zero-result classification
    evidence = collect_page_evidence(html, url=url)
    visible_text = page_text

    # Classify the zero-result/failure state using the dedicated classifier
    potential_zero_classification = classify_zero_result(
        acquisition_lineage={"state": fetch_method},
        session_detection=session_detection,
        empty_check=empty_check.to_dict() if empty_check is not None and hasattr(empty_check, "to_dict") else None,
        anti_bot_score=anti_bot,
        final_url=url,
        html=html,
        visible_text=visible_text,
        detected_forms=evidence.forms if evidence else None,
        detected_containers=len(evidence.candidate_containers) if evidence else 0,
        raw_candidate_count=len(evidence.candidate_containers) if evidence else 0,
        schema_fields=[f.name for f in schema_fields],
    )

    is_failure_page = (
        potential_zero_classification.failure_class in ("anti_bot_block", "auth_required", "empty_response")
        if potential_zero_classification is not None
        else False
    )

    if not results or is_failure_page:
        if is_failure_page:
            results = []
        zero_classification = potential_zero_classification

        # Classification may have been set in except block above, only classify
        # if not
        if not classification:
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

        # Log zero-result classification for diagnostics
        if zero_classification:
            zero_result_failure_class = zero_classification.failure_class
            logger.info(
                "[ZeroResult] %s — %s (confidence=%.2f)",
                zero_classification.failure_class,
                zero_classification.user_message,
                zero_classification.confidence,
            )
            provenance_builder.add_error(
                f"Zero-result: {zero_classification.failure_class} ({zero_classification.recommended_action})",
            )

        # Capture regression candidates for future benchmark expansion
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
    # Capture when quality is low (partial extraction)
    elif any(r.get("record_score", 1.0) < min_record_score * 0.5 for r in results):
        get_regression_capture().maybe_capture(
            url=url,
            html=html,
            failure_category="low_quality_extraction",
            failure_confidence=0.6,
            records_count=len(results),
            schema_fields=[f.name for f in schema_fields],
            force=True,
        )

    # ── Compound Record Assembly ────────────────────────────────────
    # Detect and assemble compound records if results contain internal segments.
    # Uses _element_text (preserved by container discovery and visible-text extraction)
    # as the primary text source, falling back to concatenated record values.
    if results:
        assembled = assemble_compound_records(results, full_texts=None)
        if assembled != results:
            logger.info("[Scraper] Assembled %d compound records from %d raw records", len(assembled), len(results))
            results = assembled

    # ── Post-Extraction Processing ────────────────────────────────

    # Global page-level contact boosting
    contact_counts = sum(1 for r in results if not _is_empty_value(r.get("email")) or not _is_empty_value(r.get("phone")))
    if len(results) > settings.CONTACT_BOOST_MIN_RECORDS and contact_counts / len(results) < settings.CONTACT_BOOST_THRESHOLD:
        results = _boost_contacts_with_page_html(results, html, schema_fields)

    records_before_scoring = len(results)

    if results:
        from app.selector_engine import build_selector_field_metadata

        selector_meta = build_selector_field_metadata(
            (ext_result.selectors or {}).get("fields", {}),
            schema_fields,
        )
        results = process_raw_records(
            results,
            schema_fields,
            min_record_score,
            profile_fields=selector_meta,
            user_intent=user_intent,
        )
    records_after_dedup = len(results)

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
    for r in results:
        r["_extraction_source"] = ext_result.method
        r["_extraction_confidence"] = r.get("record_score", 0.8)
        r["_extraction_provenance"] = ext_result.selectors

    # Build provenance summary for telemetry
    llm_calls = get_llm_call_count()
    # Very rough cost estimate: $0.01 per LLM call + browser time
    estimated_cost = (llm_calls * settings.COST_PER_LLM_CALL) + (fetch_ms / 1000.0 * settings.COST_PER_FETCH_MS)

    # ── Regression Intelligence: Compute severity from classification ──
    regression_severity = None
    if classification:
        from app.regression_capture import RegressionEntry

        # Build a temporary entry to classify severity
        temp_entry = RegressionEntry(
            id="",
            url=url,
            domain=intel.domain,
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
        from app.selector_decay_predictor import get_selector_decay_predictor  # research-shell, lazy

        decay_predictor = get_selector_decay_predictor()
        decay_predictor.record_observation(intel.domain, selector_hit_rate)

        # Log prediction if decay risk is elevated
        prediction = decay_predictor.predict_decay(intel.domain)
        if prediction.risk_level in ("decaying", "critical"):
            logger.info(
                "[PredictiveAdaptation] %s decay risk=%.2f level=%s days_until_failure=%.1f",
                intel.domain,
                prediction.decay_risk,
                prediction.risk_level,
                prediction.days_until_failure,
            )
    except Exception as e:
        logger.debug("[PredictiveAdaptation] Decay prediction failed: %s", e)

    # 2. Domain Evolution Model: Track mutations and anti-bot changes
    try:
        from app.domain_evolution_model import get_domain_evolution_model  # research-shell, lazy

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
        from app.self_tuning_extraction import get_self_tuning_controller  # research-shell, lazy

        tuning_controller = get_self_tuning_controller()
        tuning_controller.record_telemetry(
            intel.domain,
            {
                "fetch_ms": fetch_ms,
                "error": classification.category.value if classification else None,
                "failure_category": classification.category.value if classification else None,
                "anti_bot_score": anti_bot,
                "confidence_map": confidence_map,
            },
        )
    except Exception as e:
        logger.debug("[PredictiveAdaptation] Self-tuning failed: %s", e)

    # Cleanup: Release browser network capture buffer for this URL
    from app.browser_network_capture import clear as clear_network_captures

    clear_network_captures(url)

    # ── Return with zero-result diagnostic logging ─────────────────
    # Log the failure class for diagnostics. The empty results signal
    # the caller that extraction ran to completion but found nothing.
    res_warnings = list(result_warnings)
    if not results and zero_result_failure_class:
        logger.info(
            "[Scraper] Zero records for %s — failure_class=%s (not returning marker record)",
            url,
            zero_result_failure_class,
        )
        recommended_next_action = ""
        if zero_classification:
            recommended_next_action = zero_classification.recommended_action

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

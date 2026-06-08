"""Scraper Recovery Integration — Wraps scrape_url with intelligent recovery.

Provides a recovery-aware wrapper around scrape_url that:
  1. Executes the initial scrape_url call
  2. If it fails, classifies the failure
  3. Generates a recovery plan
  4. Attempts recovery with escalation
  5. Logs all recovery attempts

This integrates with:
  - FailureClassification for failure identification
  - RecoveryStrategies for recovery planning and execution
  - SelectorMemory for cleanup on detector failures
  - DomainIntelligence for parameter tuning
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

from app.config import settings
from app.domain_intelligence import get_domain_intelligence
from app.failure_classification import FailureCategory, classify_failure
from app.selector_memory import get_selector_memory

if TYPE_CHECKING:
    from app.acquisition_state import AcquisitionLineage, AcquisitionState
    from app.models import SchemaField
    from app.recovery_strategies import AttemptContext, get_recovery_executor, get_recovery_strategist
else:
    # --- Dynamic delegation to research-shell modules to keep imports lazy but mockable ---
    class LazyEnumMeta(type):
        def __getattr__(cls, name):
            from app.acquisition_state import AcquisitionState as impl  # noqa: N813

            return getattr(impl, name)

    class AcquisitionState(metaclass=LazyEnumMeta):
        pass

    class AcquisitionLineage:
        def __new__(cls, *args, **kwargs):
            from app.acquisition_state import AcquisitionLineage as impl  # noqa: N813

            return impl(*args, **kwargs)

    class AttemptContext:
        def __new__(cls, *args, **kwargs):
            from app.recovery_strategies import AttemptContext as impl  # noqa: N813

            return impl(*args, **kwargs)

    def get_recovery_executor(*args, **kwargs):
        from app.recovery_strategies import get_recovery_executor as impl

        return impl(*args, **kwargs)

    def get_recovery_strategist(*args, **kwargs):
        from app.recovery_strategies import get_recovery_strategist as impl

        return impl(*args, **kwargs)


logger = logging.getLogger(__name__)


def _recommended_action_for_state(state: AcquisitionState) -> str:
    # Local imports removed for module-level wrappers

    if state == AcquisitionState.SESSION_EXPIRED:
        return "provide_search_params"
    if state == AcquisitionState.ANTI_BOT_BLOCKED:
        return "use_authorized_access_or_retry_later"
    if state == AcquisitionState.EMPTY_RESPONSE:
        return "check_login_js_or_cookie_wall"
    return "inspect_failure_telemetry"


def _acquisition_state_for_failure(failure_category: str | None) -> AcquisitionState:
    # Local imports removed for module-level wrappers

    category = (failure_category or "").lower()
    if any(key in category for key in ("anti_bot", "captcha", "banned", "rate_limited")):
        return AcquisitionState.ANTI_BOT_BLOCKED
    if "session" in category:
        return AcquisitionState.SESSION_EXPIRED
    if any(key in category for key in ("empty", "no_records", "zero_records", "selector", "low_quality")):
        return AcquisitionState.EMPTY_RESPONSE
    if "timeout" in category:
        return AcquisitionState.EMPTY_RESPONSE
    return AcquisitionState.EMPTY_RESPONSE


async def scrape_url_with_recovery(  # noqa: C901, PLR0912, PLR0913, PLR0915
    url: str,
    schema_fields: list[SchemaField],
    min_record_score: float | None = None,
    user_intent: str = "",
    world_state=None,
    max_recovery_attempts: int = settings.MAX_RECOVERY_ATTEMPTS,
    selectors_map: dict | None = None,
    search_params: dict[str, str] | None = None,
) -> tuple[list[dict], dict]:
    """Scrape a URL with intelligent failure recovery.

    Args:
        url: The URL to scrape
        schema_fields: Fields to extract
        min_record_score: Minimum quality score for records
        user_intent: User intent for extraction
        world_state: Semantic world state for tracking
        max_recovery_attempts: Maximum recovery attempts before giving up
        selectors_map: Pre-discovered CSS selectors map from URL analysis
        search_params: Optional search parameters for session-bound URL recovery

    Returns:
        Tuple of (results, recovery_stats) where:
            - results: Extracted records (empty list if all attempts failed)
            - recovery_stats: Dictionary with recovery information

    """
    from app.scraper import scrape_url_attempt

    strategist = get_recovery_strategist()
    executor = get_recovery_executor()
    selector_memory = get_selector_memory()
    get_domain_intelligence()

    recovery_stats: dict[str, Any] = {
        "url": url,
        "attempts": 0,
        "recovery_attempts": 0,
        "success": False,
        "final_failure_category": None,
        "recovery_actions_taken": [],
        "failure_classifications": [],
        "total_time_ms": 0.0,
    }

    start_time = time.time()
    attempt = 0
    last_error: Exception | None = None
    attempt_ctx = AttemptContext()
    result: Any = None

    while attempt < max_recovery_attempts:
        if attempt_ctx.skip_url:
            recovery_stats["final_failure_category"] = "skipped_url"
            break
        if attempt_ctx.abort_domain or attempt_ctx.skip_domain:
            recovery_stats["final_failure_category"] = "skipped_domain"
            break

        attempt += 1
        recovery_stats["attempts"] += 1

        try:
            # Chaos failure injection check
            from app.chaos_simulator import FailureMode, get_chaos_simulator

            chaos = get_chaos_simulator()

            if chaos.is_failure_active(FailureMode.NETWORK_TIMEOUT):
                logger.warning("[Chaos Simulation] Injecting NETWORK_TIMEOUT")
                msg = "Timed out waiting for response"
                raise TimeoutError(msg)

            if chaos.is_failure_active(FailureMode.BROWSER_CRASH):
                logger.warning("[Chaos Simulation] Injecting BROWSER_CRASH")
                msg = "Browser target closed unexpectedly"
                raise ConnectionError(msg)

            if chaos.is_failure_active(FailureMode.ANTI_BOT_ESCALATION):
                logger.warning("[Chaos Simulation] Injecting ANTI_BOT_ESCALATION")
                msg = "403 Forbidden - WAF Challenge"
                raise PermissionError(msg)

            if chaos.is_failure_active(FailureMode.SELECTOR_POISONING):
                logger.warning("[Chaos Simulation] Injecting SELECTOR_POISONING (zero records)")
                results: Any = []
            else:
                # Use scrape_url_attempt for richer result metadata
                result = await scrape_url_attempt(
                    url,
                    schema_fields,
                    min_record_score=min_record_score,
                    user_intent=user_intent,
                    world_state=world_state,
                    selectors_map=selectors_map,
                    search_params=search_params,
                    attempt_ctx=attempt_ctx,
                )
                results = list(result)  # Extract records as a plain list

            # Check telemetry for fetch-level errors
            from app.scrape_telemetry import get_scrape_telemetry

            telemetry = get_scrape_telemetry()
            last_event = telemetry.get_last_for_url(url)

            if last_event and last_event.error:
                logger.warning("Scrape attempt %d failed: %s", attempt, last_event.error)
                raise RuntimeError(last_event.error)

            if not results and attempt < max_recovery_attempts:
                logger.warning("Scrape attempt %d returned 0 records, triggering recovery", attempt)
                msg = "zero_records_extracted"
                raise ValueError(msg)

            recovery_stats["success"] = True
            if hasattr(result, "network_diagnostics"):
                recovery_stats["network_diagnostics"] = result.network_diagnostics
            if hasattr(result, "warnings"):
                recovery_stats["warnings"] = result.warnings
            recovery_stats["total_time_ms"] = (time.time() - start_time) * 1000

            # Build acquisition lineage from enriched result metadata
            anti_bot_score = result.anti_bot_score
            fetch_method = result.fetch_method or "playwright_full"
            recommend = result.recommended_next_action

            if attempt > 1:
                state = AcquisitionState.RECOVERED
                user_message = "Scrape succeeded after recovery actions."
            elif anti_bot_score > 0.5:
                state = AcquisitionState.ANTI_BOT_BLOCKED
                user_message = "Page may have anti-bot protections."
                try:
                    from app.metrics_collector import record_anti_bot_classification

                    record_anti_bot_classification("anti_bot_block")
                except (ImportError, AttributeError, TypeError, ValueError):  # nosec B110
                    pass
            else:
                state = AcquisitionState.DIRECT
                user_message = "Page loaded successfully."

            lineage = AcquisitionLineage(
                original_url=url,
                final_url=result.final_url or url,
                state=state,
                fetch_method=fetch_method,
                anti_bot_score=anti_bot_score,
                data_evidence_score=result.data_evidence_score,
                user_message=user_message,
                recommended_next_action=recommend or _recommended_action_for_state(state),
                recovery_method=(
                    ", ".join(recovery_stats["recovery_actions_taken"]) if recovery_stats["recovery_actions_taken"] else None
                ),
            )
            recovery_stats["acquisition_lineage"] = lineage.to_dict()

            logger.info(
                "Scrape succeeded on attempt %d for %s (got %d records, state=%s, anti_bot=%.2f)",
                attempt,
                url,
                len(results),
                state.value if hasattr(state, "value") else str(state),
                anti_bot_score,
            )
            return results, recovery_stats

        except Exception as e:  # nosec B110
            last_error = e
            error_msg = str(e)

            # Get telemetry if available for richer classification
            from app.scrape_telemetry import get_scrape_telemetry

            last_event = get_scrape_telemetry().get_last_for_url(url)
            event_dict = last_event.to_dict() if last_event else {}

            # Use scrape result HTML for evidence-based classification if
            # available
            result_html = None
            if "result" in locals():
                result_html = getattr(result, "html", None)

            classification = classify_failure(
                error_message=error_msg,
                telemetry=event_dict,
                html=result_html,
            )
            recovery_stats["failure_classifications"].append(classification.to_dict())
            recovery_stats["final_failure_category"] = classification.category.value

            if classification.category == FailureCategory.SELECTOR_DECAY:
                logger.info("Selector decay detected, cleaning up selector memory for %s", url)
                selector_memory.force_cleanup()

            if attempt >= max_recovery_attempts:
                break

            domain_info = get_domain_intelligence().get_intelligence(url).to_dict()
            plan = strategist.generate_recovery_plan(classification, attempt, domain_info=domain_info)
            logger.info("Generated recovery plan for %s: %s (attempt %d)", url, plan.primary_action.value, attempt)

            if attempt > plan.max_retry_attempts:
                logger.warning(
                    "Max retry attempts (%d) reached for %s, giving up",
                    plan.max_retry_attempts,
                    url,
                )
                break

            recovery_stats["recovery_attempts"] += 1
            recovery_stats["recovery_actions_taken"].append(plan.primary_action.value)

            success = await executor.execute(
                plan,
                context={
                    "url": url,
                    "attempt": attempt,
                    "world_state": world_state,
                    "min_record_score": min_record_score or settings.DEFAULT_MIN_RECORD_SCORE,
                },
                attempt_ctx=attempt_ctx,
            )

            if not success:
                logger.warning("Recovery action %s failed for %s", plan.primary_action.value, url)

            if attempt_ctx.skip_url:
                recovery_stats["final_failure_category"] = "skipped_url"
                break
            if attempt_ctx.abort_domain or attempt_ctx.skip_domain:
                recovery_stats["final_failure_category"] = "skipped_domain"
                break

            if attempt_ctx.bypass_selector_memory:
                selector_memory.force_cleanup()
            if attempt_ctx.force_llm_discovery and selectors_map:
                selectors_map = None

    recovery_stats["total_time_ms"] = (time.time() - start_time) * 1000

    failure_category = recovery_stats.get("final_failure_category", "unknown")
    state = _acquisition_state_for_failure(failure_category)

    from app.scrape_telemetry import get_scrape_telemetry

    last_event = get_scrape_telemetry().get_last_for_url(url)
    event_dict = last_event.to_dict() if last_event else {}

    lineage = AcquisitionLineage(
        original_url=url,
        final_url=url,
        state=state,
        message=f"Final failure category: {failure_category}",
        fetch_method=event_dict.get("fetch_method", "unknown") or "unknown",
        session_bound=(state == AcquisitionState.SESSION_EXPIRED),
        anti_bot_score=float(event_dict.get("anti_bot_score", 0.0) or 0.0),
        data_evidence_score=0.0,
        user_message="",
        recommended_next_action=_recommended_action_for_state(state),
    )
    lineage.user_message = lineage.get_user_message()
    recovery_stats["acquisition_lineage"] = lineage.to_dict()

    logger.error("All %d scrape attempts failed for %s. Last error: %s", max_recovery_attempts, url, last_error)
    return [], recovery_stats

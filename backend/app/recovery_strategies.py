"""Advanced Recovery Strategies — Intelligent failure recovery per failure type.

Provides tailored recovery actions beyond simple retries:
  - Per-failure-type strategies (e.g., SELECTOR_DECAY triggers forced rediscovery)
  - Escalation paths (retry → backoff → proxy → LLM → skip)
  - Parameter tuning based on failure patterns and domain intelligence
  - State tracking to prevent retry loops
  - Integration with anti_bot_engine, proxy_manager, and selector_memory

LAW: Recovery is not a boolean (retry / skip). It's a multi-stage escalation
with per-failure-type knowledge encoded in the recovery strategy.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any, ClassVar

from app.failure_classification import FailureCategory, FailureClassification

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)


class RecoveryAction(StrEnum):
    """Concrete recovery actions the executor can take."""

    # Fetch / Transport recovery
    INCREASE_HYDRATION_WAIT = "increase_hydration_wait"
    RETRY_WITH_DNS_FLUSH = "retry_with_dns_flush"
    INCREASE_TIMEOUT = "increase_timeout"
    REDUCE_CONCURRENCY = "reduce_concurrency"

    # Anti-Bot recovery
    ROTATE_PROXY = "rotate_proxy"
    BACKOFF_AND_SLOW = "backoff_and_slow"
    ABORT_DOMAIN = "abort_domain"
    SOLVE_CAPTCHA = "solve_captcha"
    HARVEST_CF_CLEARANCE = "harvest_cf_clearance"

    # Extraction recovery
    FORCE_REDISCOVERY = "force_rediscovery"
    FORCE_REDISCOVERY_WITH_SWAP_DETECTION = "force_rediscovery_with_swap_detection"
    LOWER_SCORE_THRESHOLD = "lower_score_threshold"
    RETRY_WITH_FIELD_FOCUS = "retry_with_field_focus"

    # Escalation
    ESCALATE_TO_LLM = "escalate_to_llm"
    USE_HTTPX_FALLBACK = "use_httpx_fallback"

    # Terminal
    SKIP_DOMAIN = "skip_domain"
    SKIP_URL = "skip_url"


@dataclass
class RecoveryPlan:
    """Plan for recovering from a specific failure."""

    failure_category: FailureCategory
    primary_action: RecoveryAction
    secondary_actions: list[RecoveryAction] = field(default_factory=list)
    parameters: dict[str, Any] = field(default_factory=dict)
    max_retry_attempts: int = 1
    backoff_seconds: float = 1.0
    should_escalate: bool = False
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["failure_category"] = self.failure_category.value
        result["primary_action"] = self.primary_action.value
        result["secondary_actions"] = [a.value for a in self.secondary_actions]
        return result


@dataclass
class AttemptContext:
    """Mutable context mutated by recovery handlers and consumed by the next scrape attempt."""

    timeout_ms: int | None = None
    hydration_wait_ms: int | None = None
    fetch_strategy: str | None = None
    bypass_selector_memory: bool = False
    force_llm_discovery: bool = False
    prefer_httpx: bool = False
    reduce_concurrency: bool = False
    proxy_profile: str | None = None
    search_params: dict[str, str] | None = None
    extra_headers: dict[str, str] = field(default_factory=dict)
    cookies: dict[str, str] = field(default_factory=dict)
    skip_networkidle: bool = False
    scroll_attempts: int | None = None
    anti_bot_stealth: bool = False
    # Roadmap Wave 5 Item 3: per-job JS wait condition overrides
    wait_for_selector: str | None = None
    wait_for_function: str | None = None
    wait_for_timeout: int | None = None
    wait_for_navigation: bool | None = None

    # Recovery-only flags
    skip_url: bool = False
    """If True, the URL should be skipped entirely (set by handle_skip_url)."""
    skip_domain: str | None = None
    """If set, the domain should be skipped (set by handle_skip_domain)."""
    min_record_score_override: float | None = None
    """Override the minimum record score (set by handle_lower_score_threshold)."""
    force_container_discovery: bool = False
    """If True, bypass memory and LLM discovery and go straight to container discovery."""
    abort_domain: bool = False
    """If True, mark domain cooldown instead of retrying with a different strategy."""


class RecoveryStrategist:
    """Generates tailored recovery plans for failures."""

    # Per-failure-type recovery escalation paths
    RECOVERY_PATHS: ClassVar[dict[FailureCategory, dict]] = {
        # ── Fetch / Transport failures ────────────────────────────────
        FailureCategory.HYDRATION_FAILURE: {
            "primary": RecoveryAction.INCREASE_HYDRATION_WAIT,
            "escalation": [
                RecoveryAction.RETRY_WITH_DNS_FLUSH,
                RecoveryAction.REDUCE_CONCURRENCY,
                RecoveryAction.ROTATE_PROXY,
            ],
            "max_retries": 3,
            "backoff_seconds": 2.0,
            "params": {"extra_delay_ms": 5000, "max_hydration_wait": 30000},
        },
        FailureCategory.LAZY_LOAD_TIMEOUT: {
            "primary": RecoveryAction.INCREASE_TIMEOUT,
            "escalation": [
                RecoveryAction.INCREASE_HYDRATION_WAIT,
                RecoveryAction.REDUCE_CONCURRENCY,
                RecoveryAction.SKIP_URL,
            ],
            "max_retries": 2,
            "backoff_seconds": 3.0,
            "params": {"timeout_ms": 40000},
        },
        FailureCategory.RENDER_STARVATION: {
            "primary": RecoveryAction.REDUCE_CONCURRENCY,
            "escalation": [
                RecoveryAction.BACKOFF_AND_SLOW,
                RecoveryAction.SKIP_DOMAIN,
            ],
            "max_retries": 1,
            "backoff_seconds": 5.0,
            "params": {"max_contexts": 2, "slow_factor": 0.5},
        },
        FailureCategory.DNS_RESOLUTION_FAILURE: {
            "primary": RecoveryAction.RETRY_WITH_DNS_FLUSH,
            "escalation": [
                RecoveryAction.BACKOFF_AND_SLOW,
                RecoveryAction.SKIP_DOMAIN,
            ],
            "max_retries": 2,
            "backoff_seconds": 4.0,
            "params": {"delay_ms": 3000},
        },
        FailureCategory.CONNECTION_TIMEOUT: {
            "primary": RecoveryAction.INCREASE_TIMEOUT,
            "escalation": [
                RecoveryAction.RETRY_WITH_DNS_FLUSH,
                RecoveryAction.ROTATE_PROXY,
                RecoveryAction.SKIP_DOMAIN,
            ],
            "max_retries": 2,
            "backoff_seconds": 2.0,
            "params": {"timeout_ms": 25000},
        },
        FailureCategory.HTTP_ERROR: {
            "primary": RecoveryAction.BACKOFF_AND_SLOW,
            "escalation": [
                RecoveryAction.ROTATE_PROXY,
                RecoveryAction.SKIP_DOMAIN,
            ],
            "max_retries": 1,
            "backoff_seconds": 5.0,
            "params": {"delay_ms": 10000, "slow_factor": 0.5},
        },
        FailureCategory.SSL_ERROR: {
            "primary": RecoveryAction.SKIP_URL,
            "escalation": [],
            "max_retries": 1,
            "backoff_seconds": 0.0,
            "params": {"reason": "tls_certificate_validation_failed"},
        },
        FailureCategory.NETWORK_ERROR: {
            "primary": RecoveryAction.RETRY_WITH_DNS_FLUSH,
            "escalation": [
                RecoveryAction.BACKOFF_AND_SLOW,
                RecoveryAction.SKIP_DOMAIN,
            ],
            "max_retries": 2,
            "backoff_seconds": 3.0,
            "params": {"delay_ms": 3000},
        },
        FailureCategory.AUTH_REQUIRED: {
            "primary": RecoveryAction.SKIP_URL,
            "escalation": [],
            "max_retries": 1,
            "backoff_seconds": 0.0,
            "params": {"reason": "authorized_auth_profile_required"},
        },
        # ── Anti-Bot failures ────────────────────────────────────────
        FailureCategory.ANTI_BOT_BLOCK: {
            "primary": RecoveryAction.ROTATE_PROXY,
            "escalation": [
                RecoveryAction.HARVEST_CF_CLEARANCE,
                RecoveryAction.BACKOFF_AND_SLOW,
                RecoveryAction.ABORT_DOMAIN,
            ],
            "max_retries": 3,
            "backoff_seconds": 10.0,
            "params": {"rotate_proxy": True, "delay_ms": 15000},
        },
        FailureCategory.CAPTCHA: {
            "primary": RecoveryAction.SOLVE_CAPTCHA,
            "escalation": [
                RecoveryAction.ROTATE_PROXY,
                RecoveryAction.BACKOFF_AND_SLOW,
                RecoveryAction.ABORT_DOMAIN,
            ],
            "max_retries": 2,
            "backoff_seconds": 20.0,
            "params": {"delay_ms": 30000},
        },
        FailureCategory.IP_BANNED: {
            "primary": RecoveryAction.ROTATE_PROXY,
            "escalation": [
                RecoveryAction.BACKOFF_AND_SLOW,
                RecoveryAction.ABORT_DOMAIN,
            ],
            "max_retries": 2,
            "backoff_seconds": 30.0,
            "params": {"delay_ms": 60000},
        },
        FailureCategory.RATE_LIMITED: {
            "primary": RecoveryAction.BACKOFF_AND_SLOW,
            "escalation": [
                RecoveryAction.ROTATE_PROXY,
                RecoveryAction.SKIP_DOMAIN,
            ],
            "max_retries": 2,
            "backoff_seconds": 10.0,
            "params": {"delay_ms": 15000, "slow_factor": 0.3},
        },
        # ── Extraction failures ──────────────────────────────────────
        FailureCategory.SELECTOR_DECAY: {
            "primary": RecoveryAction.FORCE_REDISCOVERY,
            "escalation": [
                RecoveryAction.ESCALATE_TO_LLM,
                RecoveryAction.LOWER_SCORE_THRESHOLD,
            ],
            "max_retries": 2,
            "backoff_seconds": 0.0,
            "params": {"bypass_memory": True},
        },
        FailureCategory.SELECTOR_MISMATCH: {
            "primary": RecoveryAction.FORCE_REDISCOVERY_WITH_SWAP_DETECTION,
            "escalation": [
                RecoveryAction.LOWER_SCORE_THRESHOLD,
                RecoveryAction.ESCALATE_TO_LLM,
            ],
            "max_retries": 2,
            "backoff_seconds": 0.0,
            "params": {"enable_swap_detection": True, "bypass_memory": True},
        },
        FailureCategory.FIELD_SWAP: {
            "primary": RecoveryAction.FORCE_REDISCOVERY_WITH_SWAP_DETECTION,
            "escalation": [
                RecoveryAction.RETRY_WITH_FIELD_FOCUS,
                RecoveryAction.ESCALATE_TO_LLM,
            ],
            "max_retries": 1,
            "backoff_seconds": 0.0,
            "params": {"detect_swaps": True, "bypass_memory": True},
        },
        FailureCategory.LOW_QUALITY_EXTRACTION: {
            "primary": RecoveryAction.LOWER_SCORE_THRESHOLD,
            "escalation": [
                RecoveryAction.FORCE_REDISCOVERY,
                RecoveryAction.ESCALATE_TO_LLM,
            ],
            "max_retries": 1,
            "backoff_seconds": 0.0,
            "params": {"score_multiplier": 0.8},
        },
        FailureCategory.EMPTY_PAGE: {
            "primary": RecoveryAction.INCREASE_HYDRATION_WAIT,
            "escalation": [
                RecoveryAction.FORCE_REDISCOVERY,
                RecoveryAction.SKIP_URL,
            ],
            "max_retries": 1,
            "backoff_seconds": 2.0,
            "params": {"extra_delay_ms": 5000},
        },
        FailureCategory.MALFORMED_DOM: {
            "primary": RecoveryAction.USE_HTTPX_FALLBACK,
            "escalation": [
                RecoveryAction.ESCALATE_TO_LLM,
                RecoveryAction.SKIP_URL,
            ],
            "max_retries": 1,
            "backoff_seconds": 1.0,
            "params": {"prefer_httpx": True},
        },
        FailureCategory.SEMANTIC_MISMATCH: {
            "primary": RecoveryAction.ESCALATE_TO_LLM,
            "escalation": [
                RecoveryAction.LOWER_SCORE_THRESHOLD,
            ],
            "max_retries": 1,
            "backoff_seconds": 0.0,
            "params": {"force_llm_discovery": True},
        },
        FailureCategory.NO_RECORDS_EXTRACTED: {
            "primary": RecoveryAction.FORCE_REDISCOVERY,
            "escalation": [
                RecoveryAction.LOWER_SCORE_THRESHOLD,
                RecoveryAction.ESCALATE_TO_LLM,
                RecoveryAction.SKIP_URL,
            ],
            "max_retries": 2,
            "backoff_seconds": 0.0,
            "params": {"bypass_memory": True},
        },
        FailureCategory.PARTIAL_EXTRACTION: {
            "primary": RecoveryAction.LOWER_SCORE_THRESHOLD,
            "escalation": [
                RecoveryAction.FORCE_REDISCOVERY,
                RecoveryAction.RETRY_WITH_FIELD_FOCUS,
            ],
            "max_retries": 1,
            "backoff_seconds": 0.0,
            "params": {"score_multiplier": 0.85},
        },
        FailureCategory.HALLUCINATION: {
            "primary": RecoveryAction.LOWER_SCORE_THRESHOLD,
            "escalation": [
                RecoveryAction.ESCALATE_TO_LLM,
            ],
            "max_retries": 1,
            "backoff_seconds": 0.0,
            "params": {"apply_schema_validation": True},
        },
        # ── Infrastructure failures ──────────────────────────────────
        FailureCategory.BROWSER_CRASH: {
            "primary": RecoveryAction.ROTATE_PROXY,
            "escalation": [
                RecoveryAction.REDUCE_CONCURRENCY,
                RecoveryAction.SKIP_DOMAIN,
            ],
            "max_retries": 2,
            "backoff_seconds": 3.0,
            "params": {},
        },
        FailureCategory.TIMEOUT: {
            "primary": RecoveryAction.INCREASE_TIMEOUT,
            "escalation": [
                RecoveryAction.REDUCE_CONCURRENCY,
                RecoveryAction.SKIP_DOMAIN,
            ],
            "max_retries": 1,
            "backoff_seconds": 2.0,
            "params": {"timeout_ms": 30000},
        },
        FailureCategory.UNKNOWN: {
            "primary": RecoveryAction.BACKOFF_AND_SLOW,
            "escalation": [
                RecoveryAction.ROTATE_PROXY,
                RecoveryAction.SKIP_DOMAIN,
            ],
            "max_retries": 1,
            "backoff_seconds": 3.0,
            "params": {},
        },
    }

    def __init__(self) -> None:
        """Initialize recovery strategist."""

    def generate_recovery_plan(
        self,
        failure_classification: FailureClassification,
        attempt_number: int = 1,
        domain_info: dict | None = None,
    ) -> RecoveryPlan:
        """Generate a recovery plan for a classified failure.

        Args:
            failure_classification: The classified failure
            attempt_number: Which recovery attempt this is (1-based)
            domain_info: Optional domain intelligence context

        Returns:
            RecoveryPlan with primary and escalation actions

        """
        category = failure_classification.category
        path = self.RECOVERY_PATHS.get(category, self.RECOVERY_PATHS[FailureCategory.UNKNOWN])

        # Escalate if we've already attempted the primary action
        if attempt_number > 1 and attempt_number <= len(path["escalation"]) + 1:
            primary_action = path["escalation"][attempt_number - 2]
            secondary_actions = path["escalation"][attempt_number - 1 :]
        else:
            primary_action = path["primary"]
            secondary_actions = path["escalation"][: min(2, len(path["escalation"]))]

        # Adjust parameters based on domain intelligence if available
        params = dict(path["params"])
        if domain_info:
            params = self._tune_parameters(params, domain_info, category)

        reason = (
            f"Failure: {category.value} (confidence={failure_classification.confidence:.2f}), "
            f"attempt={attempt_number}/{path['max_retries']}"
        )

        return RecoveryPlan(
            failure_category=category,
            primary_action=primary_action,
            secondary_actions=list(secondary_actions),
            parameters=params,
            max_retry_attempts=path["max_retries"],
            backoff_seconds=path["backoff_seconds"],
            should_escalate=attempt_number < path["max_retries"],
            reason=reason,
        )

    def _tune_parameters(self, params: dict[str, Any], domain_info: dict[str, Any], category: FailureCategory) -> dict[str, Any]:
        """Tune recovery parameters based on domain intelligence.

        Example:
          - If domain has high anti-bot risk, increase backoff times
          - If domain has high fail rate, reduce max retries
          - If domain is fresh, increase timeout

        """
        tuned = dict(params)

        anti_bot_risk = domain_info.get("anti_bot_risk", 0.5)
        fail_rate = domain_info.get("failure_rate", 0.1)

        # Anti-bot categories: increase delays if risk is high
        if (
            category
            in [
                FailureCategory.ANTI_BOT_BLOCK,
                FailureCategory.CAPTCHA,
                FailureCategory.IP_BANNED,
                FailureCategory.RATE_LIMITED,
            ]
            and anti_bot_risk > 0.7
        ):
            if "delay_ms" in tuned:
                tuned["delay_ms"] = int(tuned["delay_ms"] * 1.5)
            if "slow_factor" in tuned:
                tuned["slow_factor"] = tuned["slow_factor"] * 0.7

        # If domain has high failure rate, increase delay to back off
        if fail_rate > 0.5 and "delay_ms" in tuned:
            tuned["delay_ms"] = int(tuned["delay_ms"] * 1.3)

        return tuned


class RecoveryExecutor:
    """Executes recovery actions with hooks for system integration."""

    def __init__(self) -> None:
        """Initialize executor with action handlers."""
        self.action_handlers: dict[RecoveryAction, Callable] = {}

    def register_handler(self, action: RecoveryAction, handler: Callable) -> None:
        """Register a handler for a specific recovery action.

        Args:
            action: The RecoveryAction to handle
            handler: Async callable that executes the action

        """
        self.action_handlers[action] = handler

    async def execute(
        self,
        plan: RecoveryPlan,
        context: dict[str, Any],
        attempt_ctx: AttemptContext | None = None,
    ) -> bool:
        """Execute a recovery plan, mutating attempt_ctx for the next scrape.

        Args:
            plan: The recovery plan to execute
            context: Execution context (url, html, schema_fields, etc.)
            attempt_ctx: Mutable context that handlers modify for the next attempt.
                         Changes here are consumed by the scraper before retry.

        """
        if attempt_ctx is None:
            attempt_ctx = AttemptContext()
        # Apply backoff if specified.  The BACKOFF_AND_SLOW handler owns
        # its own delay (delay_ms → seconds) and would otherwise stack
        # back-to-back, giving double the planned latency.
        if plan.backoff_seconds > 0 and plan.primary_action is not RecoveryAction.BACKOFF_AND_SLOW:
            logger.info("Backoff %.1f seconds before %s recovery", plan.backoff_seconds, plan.primary_action.value)
            await asyncio.sleep(plan.backoff_seconds)

        # Execute primary action
        logger.info(
            "Executing recovery: %s for %s (reason: %s)",
            plan.primary_action.value,
            plan.failure_category.value,
            plan.reason,
        )

        handler = self.action_handlers.get(plan.primary_action)
        if handler:
            try:
                result = await handler(plan.parameters, context, attempt_ctx)
                if result:
                    logger.info("Recovery successful: %s", plan.primary_action.value)
                    return True
            except (OSError, RuntimeError, ValueError, TypeError, ConnectionError, TimeoutError):
                logger.exception("Recovery action failed: %s", plan.primary_action.value)
        else:
            logger.warning("No handler registered for action: %s", plan.primary_action.value)

        # If primary failed and we should escalate, try secondary actions
        if plan.should_escalate and plan.secondary_actions:
            logger.info("Primary recovery failed, escalating to secondary actions")
            for secondary_action in plan.secondary_actions:
                handler = self.action_handlers.get(secondary_action)
                if handler:
                    try:
                        result = await handler(plan.parameters, context, attempt_ctx)
                        if result:
                            logger.info("Recovery successful via escalation: %s", secondary_action.value)
                            return True
                    except (OSError, RuntimeError, ValueError, TypeError, ConnectionError, TimeoutError):
                        logger.exception("Escalated recovery action failed: %s", secondary_action.value)

        logger.warning("All recovery actions failed for %s", plan.failure_category.value)
        return False


# ── Built-in recovery handlers ──────────────────────────────────────────
# Each handler receives (params, context, attempt_ctx) and mutates
# ``attempt_ctx`` so the next scrape attempt picks up the change.
# Handlers return True to signal "recovery action applied successfully"
# (meaning the context mutation was applied, not that the scrape will
# succeed — the caller still needs to retry).


async def handle_increase_hydration_wait(
    params: dict[str, Any],
    context: dict[str, Any],
    attempt_ctx: AttemptContext,
) -> bool:
    """Increase hydration wait milliseconds for the next attempt."""
    extra_ms = params.get("extra_delay_ms", 5000)
    attempt_ctx.hydration_wait_ms = (attempt_ctx.hydration_wait_ms or 0) + int(extra_ms)
    logger.info("Recovery: increased hydration_wait_ms to %d", attempt_ctx.hydration_wait_ms)
    return True


async def handle_retry_with_dns_flush(
    params: dict[str, Any],
    context: dict[str, Any],
    attempt_ctx: AttemptContext,
) -> bool:
    """Retry after a DNS cache flush delay."""
    delay_ms = params.get("delay_ms", 3000)
    await asyncio.sleep(delay_ms / 1000)
    logger.info("Recovery: DNS flush wait of %dms complete", delay_ms)
    return True


async def handle_increase_timeout(
    params: dict[str, Any],
    context: dict[str, Any],
    attempt_ctx: AttemptContext,
) -> bool:
    """Increase the page/network timeout for the next attempt."""
    timeout_ms = params.get("timeout_ms", 25000)
    attempt_ctx.timeout_ms = int(timeout_ms)
    logger.info("Recovery: increased timeout_ms to %d", attempt_ctx.timeout_ms)
    return True


async def handle_reduce_concurrency(
    _params: dict[str, Any],
    _context: dict[str, Any],
    attempt_ctx: AttemptContext,
) -> bool:
    """Reduce concurrency for the next attempt."""
    attempt_ctx.reduce_concurrency = True
    logger.info("Recovery: reduce_concurrency enabled")
    return True


async def handle_rotate_proxy(
    _params: dict[str, Any],
    _context: dict[str, Any],
    attempt_ctx: AttemptContext,
) -> bool:
    """Rotate the proxy for the next attempt."""
    attempt_ctx.proxy_profile = "rotated"
    logger.info("Recovery: proxy rotation requested")
    return True


async def handle_backoff_and_slow(
    params: dict[str, Any],
    context: dict[str, Any],
    attempt_ctx: AttemptContext,
) -> bool:
    """Backoff before retry with reduced speed."""
    delay_ms = params.get("delay_ms", 5000)
    await asyncio.sleep(delay_ms / 1000)
    attempt_ctx.reduce_concurrency = True
    slow_factor = params.get("slow_factor", 0.5)
    logger.info("Recovery: backed off %dms, slow_factor=%.2f", delay_ms, slow_factor)
    return True


async def handle_abort_domain(
    params: dict[str, Any],
    context: dict[str, Any],
    attempt_ctx: AttemptContext,
) -> bool:
    """Mark domain for cooldown instead of retrying.

    Mirrors ``app.recovery_handlers.handle_abort_domain`` so that calling
    ``get_recovery_executor()`` without experimental_startularity wired in
    (the only path that registers the better copy via
    ``register_all_recovery_handlers``) still persists a persistent
    cooldown via :meth:`DomainRuntimePolicy.set_abort_domain`. The
    ``attempt_ctx.abort_domain`` flag is also set so the orchestrator
    can short-circuit the URL before persisting a transient placeholder.
    """
    url = context.get("url", "")
    skip_minutes = params.get("skip_domain_minutes", 60)
    logger.warning("Recovery: aborting domain for %s for %d minutes", url, skip_minutes)
    attempt_ctx.abort_domain = True
    if url:
        try:
            from app.domain_runtime_policy import get_domain_runtime_policy

            get_domain_runtime_policy().set_abort_domain(url)
        except (ImportError, RuntimeError, ValueError) as exc:
            logger.debug("Could not record abort_domain cooldown: %s", exc)
        try:
            from urllib.parse import urlparse

            parsed = urlparse(url)
            domain = parsed.netloc.lower() if parsed.hostname else ""
            if domain:
                attempt_ctx.skip_domain = domain
        except ValueError as exc:
            logger.debug("Could not derive domain for skip_domain: %s", exc)
    return True


async def handle_force_rediscovery(
    _params: dict[str, Any],
    _context: dict[str, Any],
    attempt_ctx: AttemptContext,
) -> bool:
    """Force selector rediscovery, bypassing memory."""
    attempt_ctx.bypass_selector_memory = True
    attempt_ctx.force_llm_discovery = True
    logger.info("Recovery: forced selector rediscovery")
    return True


async def handle_force_rediscovery_with_swap_detection(
    _params: dict[str, Any],
    _context: dict[str, Any],
    attempt_ctx: AttemptContext,
) -> bool:
    """Force rediscovery with swap detection enabled."""
    attempt_ctx.bypass_selector_memory = True
    attempt_ctx.force_llm_discovery = True
    attempt_ctx.force_container_discovery = True
    logger.info("Recovery: forced rediscovery with swap detection")
    return True


async def handle_lower_score_threshold(
    params: dict[str, Any],
    context: dict[str, Any],
    attempt_ctx: AttemptContext,
) -> bool:
    """Lower the minimum record score threshold for the next attempt."""
    score_multiplier = params.get("score_multiplier", 0.8)
    current = context.get("min_record_score", 50.0)
    attempt_ctx.min_record_score_override = current * score_multiplier
    logger.info(
        "Recovery: lowered min_record_score to %.1f (x%.2f)",
        attempt_ctx.min_record_score_override,
        score_multiplier,
    )
    return True


async def handle_retry_with_field_focus(
    _params: dict[str, Any],
    _context: dict[str, Any],
    attempt_ctx: AttemptContext,
) -> bool:
    """Retry with field-focused extraction."""
    attempt_ctx.force_llm_discovery = True
    logger.info("Recovery: retrying with field focus")
    return True


async def handle_escalate_to_llm(
    _params: dict[str, Any],
    _context: dict[str, Any],
    attempt_ctx: AttemptContext,
) -> bool:
    """Escalate to LLM-based discovery."""
    attempt_ctx.force_llm_discovery = True
    logger.info("Recovery: escalated to LLM discovery")
    return True


async def handle_use_httpx_fallback(
    _params: dict[str, Any],
    _context: dict[str, Any],
    attempt_ctx: AttemptContext,
) -> bool:
    """Fall back to HTTPX for the next attempt."""
    attempt_ctx.prefer_httpx = True
    logger.info("Recovery: switching to HTTPX fallback")
    return True


async def handle_skip_domain(
    _params: dict[str, Any],
    context: dict[str, Any],
    attempt_ctx: AttemptContext,
) -> bool:
    """Skip the entire domain."""
    url = context.get("url", "")
    domain = ""
    if url:
        from urllib.parse import urlparse

        parsed = urlparse(url)
        domain = parsed.netloc.lower() if parsed.hostname else ""
    if domain:
        attempt_ctx.skip_domain = domain
        logger.warning("Recovery: skipping domain %s", domain)
    else:
        # Fall back to the URL if it can't be parsed (best-effort signal;
        # consumers treat this as truthy → will trigger the skip path).
        attempt_ctx.skip_domain = url
        logger.warning("Recovery: skipping url (no netloc) %s", url)
    return True


async def handle_skip_url(
    _params: dict[str, Any],
    _context: dict[str, Any],
    attempt_ctx: AttemptContext,
) -> bool:
    """Skip this URL."""
    attempt_ctx.skip_url = True
    logger.warning("Recovery: skipping URL")
    return True


async def handle_solve_captcha(
    _params: dict[str, Any],
    context: dict[str, Any],
    attempt_ctx: AttemptContext,
) -> bool:
    """Attempt to solve a detected CAPTCHA via the configured solver.

    When ``settings.CAPTCHA_SOLVER_ENABLED=False`` (the default) the
    factory returns :class:`_NoOpSolver` and ``solve()`` returns ``None``
    — this handler then returns ``False`` so the executor escalates to
    the next action in the recovery path (typically ROTATE_PROXY).

    When a real solver is configured, the token returned by ``solve()``
    is stuffed into ``attempt_ctx.cookies`` so the headless client which
    receives it on the next attempt has a Cookie header set.  The
    scraper downstream translates ``attempt_ctx.cookies`` into
    Playwright's ``context.add_cookies()`` via the engine.
    """
    try:
        from app.captcha_solver import _NoOpSolver, get_captcha_solver
    except ImportError:
        logger.debug("captcha_solver module unavailable; cannot solve CAPTCHA")
        return False

    try:
        solver = get_captcha_solver()
    except (RuntimeError, ValueError, TypeError) as exc:
        logger.warning("CAPTCHA solver factory failed: %s", exc)
        return False

    if isinstance(solver, _NoOpSolver):
        logger.debug("CAPTCHA solver disabled (NoOp); escalating")
        return False

    url = context.get("url", "")
    if not url:
        logger.debug("CAPTCHA handler called without URL; cannot solve")
        return False

    page_url = url
    captcha_type = str(context.get("captcha_type", "recaptcha"))
    site_key = str(context.get("site_key", ""))
    if not site_key:
        logger.debug("CAPTCHA handler missing site_key; cannot solve")
        return False

    try:
        token = await solver.solve(site_key=site_key, page_url=page_url, captcha_type=captcha_type)
    except (TimeoutError, RuntimeError, ValueError, TypeError, OSError) as exc:
        logger.warning("CAPTCHA solve() raised: %s", exc)
        return False

    if not token:
        logger.debug("CAPTCHA solver returned no token")
        return False

    attempt_ctx.cookies = {**attempt_ctx.cookies, "captcha_token": str(token)}
    logger.info("Recovery: CAPTCHA solved (%s), token injected", captcha_type)
    return True


async def handle_harvest_cf_clearance(
    _params: dict[str, Any],
    context: dict[str, Any],
    attempt_ctx: AttemptContext,
) -> bool:
    """Harvest a ``cf_clearance`` cookie via the CF harvester.

    Default-off (``settings.CF_HARVESTER_ENABLED=False``).  When disabled
    the harvester short-circuits and we return ``False`` so the executor
    escalates to ``BACKOFF_AND_SLOW`` instead.

    On success the harvester persists the cookie via
    ``AntiBotEngine.update_cookies(domain, header)``; the result here is
    a boolean indicating whether the harvest completed within its
    timeout.  We also pass it through to ``attempt_ctx.cookies`` so the
    next attempt can replay it directly without a second round-trip.
    """
    url = context.get("url", "")
    if not url:
        logger.debug("CF harvest handler called without URL; cannot run")
        return False

    domain = context.get("domain", "")
    if not domain:
        try:
            from urllib.parse import urlparse

            domain = urlparse(url).netloc
        except (ValueError, TypeError):
            domain = ""

    if not domain:
        logger.debug("CF harvest handler missing domain; cannot run")
        return False

    try:
        from app.cf_harvester import harvest_cf_clearance
    except ImportError:
        logger.debug("cf_harvester module unavailable; cannot harvest")
        return False

    cookie_header = await harvest_cf_clearance(url, domain)
    if not cookie_header:
        logger.info("CF clearance harvest unsuccessful for %s; escalating", domain)
        return False

    try:
        from urllib.parse import unquote

        for piece in cookie_header.split(";"):
            piece = piece.strip()
            if "=" not in piece:
                continue
            name, _, value = piece.partition("=")
            attempt_ctx.cookies = {
                **attempt_ctx.cookies,
                unquote(name.strip()): unquote(value.strip()),
            }
    except (ValueError, TypeError, AttributeError) as exc:
        logger.warning("CF harvest cookie parsing failed: %s", exc)

    logger.info("Recovery: cf_clearance harvested for %s", domain)
    return True


# ── Handler registry — maps RecoveryAction to its implementation ────

_BUILTIN_HANDLERS: dict[RecoveryAction, Callable] = {
    RecoveryAction.INCREASE_HYDRATION_WAIT: handle_increase_hydration_wait,
    RecoveryAction.RETRY_WITH_DNS_FLUSH: handle_retry_with_dns_flush,
    RecoveryAction.INCREASE_TIMEOUT: handle_increase_timeout,
    RecoveryAction.REDUCE_CONCURRENCY: handle_reduce_concurrency,
    RecoveryAction.ROTATE_PROXY: handle_rotate_proxy,
    RecoveryAction.BACKOFF_AND_SLOW: handle_backoff_and_slow,
    RecoveryAction.ABORT_DOMAIN: handle_abort_domain,
    RecoveryAction.FORCE_REDISCOVERY: handle_force_rediscovery,
    RecoveryAction.FORCE_REDISCOVERY_WITH_SWAP_DETECTION: handle_force_rediscovery_with_swap_detection,
    RecoveryAction.LOWER_SCORE_THRESHOLD: handle_lower_score_threshold,
    RecoveryAction.RETRY_WITH_FIELD_FOCUS: handle_retry_with_field_focus,
    RecoveryAction.ESCALATE_TO_LLM: handle_escalate_to_llm,
    RecoveryAction.USE_HTTPX_FALLBACK: handle_use_httpx_fallback,
    RecoveryAction.SKIP_DOMAIN: handle_skip_domain,
    RecoveryAction.SKIP_URL: handle_skip_url,
    RecoveryAction.SOLVE_CAPTCHA: handle_solve_captcha,
    RecoveryAction.HARVEST_CF_CLEARANCE: handle_harvest_cf_clearance,
}


# Global singleton executor
_executor: RecoveryExecutor | None = None
_strategist: RecoveryStrategist | None = None
_executor_lock = threading.Lock()
_strategist_lock = threading.Lock()


def get_recovery_executor() -> RecoveryExecutor:
    """Get the global recovery executor with built-in handlers registered."""
    global _executor
    if _executor is not None:
        return _executor
    with _executor_lock:
        if _executor is None:
            _executor = RecoveryExecutor()
            _register_builtin_handlers(_executor)
    return _executor


def _register_builtin_handlers(executor: RecoveryExecutor) -> None:
    """Register the built-in recovery action handlers on the executor."""
    for action, handler in _BUILTIN_HANDLERS.items():
        executor.register_handler(action, handler)


def get_recovery_strategist() -> RecoveryStrategist:
    """Get the global recovery strategist."""
    global _strategist
    if _strategist is not None:
        return _strategist
    with _strategist_lock:
        if _strategist is None:
            _strategist = RecoveryStrategist()
    return _strategist

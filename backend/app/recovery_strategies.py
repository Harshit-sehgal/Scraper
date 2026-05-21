"""
Advanced Recovery Strategies — Intelligent failure recovery per failure type.

Provides tailored recovery actions beyond simple retries:
  - Per-failure-type strategies (e.g., SELECTOR_DECAY triggers forced rediscovery)
  - Escalation paths (retry → backoff → proxy → LLM → skip)
  - Parameter tuning based on failure patterns and domain intelligence
  - State tracking to prevent retry loops
  - Integration with anti_bot_engine, proxy_manager, and selector_memory

LAW: Recovery is not a boolean (retry/skip). It's a multi-stage escalation
with per-failure-type knowledge encoded in the recovery strategy.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, asdict
from enum import Enum
from typing import Callable, Any, Optional

from app.failure_classification import FailureCategory, FailureClassification

logger = logging.getLogger(__name__)


class RecoveryAction(str, Enum):
    """Concrete recovery actions the executor can take."""
    
    # Fetch/Transport recovery
    INCREASE_HYDRATION_WAIT = "increase_hydration_wait"
    RETRY_WITH_DNS_FLUSH = "retry_with_dns_flush"
    INCREASE_TIMEOUT = "increase_timeout"
    REDUCE_CONCURRENCY = "reduce_concurrency"
    
    # Anti-Bot recovery
    ROTATE_PROXY = "rotate_proxy"
    BACKOFF_AND_SLOW = "backoff_and_slow"
    ABORT_DOMAIN = "abort_domain"
    
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
    secondary_actions: list[RecoveryAction]  # Escalation path
    parameters: dict[str, Any]  # Action-specific params
    max_retry_attempts: int  # Total retries for this action
    backoff_seconds: float  # Time to wait before retry
    should_escalate: bool  # Whether to try secondary actions if primary fails
    reason: str  # Why this recovery plan was chosen
    
    def to_dict(self) -> dict:
        result = asdict(self)
        result["failure_category"] = self.failure_category.value
        result["primary_action"] = self.primary_action.value
        result["secondary_actions"] = [a.value for a in self.secondary_actions]
        return result


class RecoveryStrategist:
    """Generates tailored recovery plans for failures."""
    
    # Per-failure-type recovery escalation paths
    RECOVERY_PATHS: dict[FailureCategory, dict] = {
        # ── Fetch/Transport failures ────────────────────────────────
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
        
        # ── Anti-Bot failures ────────────────────────────────────────
        FailureCategory.ANTI_BOT_BLOCK: {
            "primary": RecoveryAction.ROTATE_PROXY,
            "escalation": [
                RecoveryAction.BACKOFF_AND_SLOW,
                RecoveryAction.ABORT_DOMAIN,
            ],
            "max_retries": 3,
            "backoff_seconds": 10.0,
            "params": {"rotate_proxy": True, "delay_ms": 15000},
        },
        
        FailureCategory.CAPTCHA: {
            "primary": RecoveryAction.ROTATE_PROXY,
            "escalation": [
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
    
    def __init__(self):
        """Initialize recovery strategist."""
    
    def generate_recovery_plan(
        self,
        failure_classification: FailureClassification,
        attempt_number: int = 1,
        domain_info: Optional[dict] = None,
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
            secondary_actions = path["escalation"][attempt_number - 1:]
        else:
            primary_action = path["primary"]
            secondary_actions = path["escalation"][:min(2, len(path["escalation"]))]
        
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
    
    def _tune_parameters(self, params: dict, domain_info: dict, category: FailureCategory) -> dict:
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
        if category in [
            FailureCategory.ANTI_BOT_BLOCK,
            FailureCategory.CAPTCHA,
            FailureCategory.IP_BANNED,
            FailureCategory.RATE_LIMITED,
        ] and anti_bot_risk > 0.7:
            if "delay_ms" in tuned:
                tuned["delay_ms"] = int(tuned["delay_ms"] * 1.5)
            if "slow_factor" in tuned:
                tuned["slow_factor"] = tuned["slow_factor"] * 0.7
        
        # If domain has high failure rate, be more aggressive
        if fail_rate > 0.5:
            if "delay_ms" in tuned:
                tuned["delay_ms"] = int(tuned["delay_ms"] * 0.8)
        
        return tuned


class RecoveryExecutor:
    """Executes recovery actions with hooks for system integration."""
    
    def __init__(self):
        """Initialize executor with action handlers."""
        self.action_handlers: dict[RecoveryAction, Callable] = {}
    
    def register_handler(self, action: RecoveryAction, handler: Callable):
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
    ) -> bool:
        """Execute a recovery plan.
        
        Args:
            plan: The recovery plan to execute
            context: Execution context (url, html, schema_fields, etc.)
            
        Returns:
            True if recovery succeeded, False otherwise
        """
        # Apply backoff if specified
        if plan.backoff_seconds > 0:
            logger.info(
                "Backoff %.1f seconds before %s recovery",
                plan.backoff_seconds, plan.primary_action.value
            )
            await asyncio.sleep(plan.backoff_seconds)
        
        # Execute primary action
        logger.info(
            "Executing recovery: %s for %s (reason: %s)",
            plan.primary_action.value, plan.failure_category.value, plan.reason
        )
        
        handler = self.action_handlers.get(plan.primary_action)
        if handler:
            try:
                result = await handler(plan.parameters, context)
                if result:
                    logger.info("Recovery successful: %s", plan.primary_action.value)
                    return True
            except Exception as e:
                logger.error("Recovery action failed: %s: %s", plan.primary_action.value, e)
        else:
            logger.warning("No handler registered for action: %s", plan.primary_action.value)
        
        # If primary failed and we should escalate, try secondary actions
        if plan.should_escalate and plan.secondary_actions:
            logger.info("Primary recovery failed, escalating to secondary actions")
            for secondary_action in plan.secondary_actions:
                handler = self.action_handlers.get(secondary_action)
                if handler:
                    try:
                        result = await handler(plan.parameters, context)
                        if result:
                            logger.info("Recovery successful via escalation: %s", secondary_action.value)
                            return True
                    except Exception as e:
                        logger.error("Escalated recovery action failed: %s: %s", secondary_action.value, e)
        
        logger.warning("All recovery actions failed for %s", plan.failure_category.value)
        return False


# Global singleton executor
_executor: RecoveryExecutor | None = None
_strategist: RecoveryStrategist | None = None


def get_recovery_executor() -> RecoveryExecutor:
    """Get the global recovery executor."""
    global _executor
    if _executor is None:
        _executor = RecoveryExecutor()
    return _executor


def get_recovery_strategist() -> RecoveryStrategist:
    """Get the global recovery strategist."""
    global _strategist
    if _strategist is None:
        _strategist = RecoveryStrategist()
    return _strategist

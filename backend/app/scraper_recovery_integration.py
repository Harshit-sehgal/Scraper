"""
Scraper Recovery Integration — Wraps scrape_url with intelligent recovery.

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

import asyncio
import logging
import time
from typing import Optional

from app.failure_classification import classify_failure, FailureCategory
from app.recovery_strategies import get_recovery_strategist, get_recovery_executor, RecoveryPlan
from app.selector_memory import get_selector_memory
from app.domain_intelligence import get_domain_intelligence
from app.models import SchemaField

logger = logging.getLogger(__name__)


async def scrape_url_with_recovery(
    url: str,
    schema_fields: list[SchemaField],
    min_record_score: float | None = None,
    user_intent: str = "",
    world_state=None,
    max_recovery_attempts: int = 3,
) -> tuple[list[dict], dict]:
    """Scrape a URL with intelligent failure recovery.
    
    Args:
        url: The URL to scrape
        schema_fields: Fields to extract
        min_record_score: Minimum quality score for records
        user_intent: User intent for extraction
        world_state: Semantic world state for tracking
        max_recovery_attempts: Maximum recovery attempts before giving up
        
    Returns:
        Tuple of (results, recovery_stats) where:
            - results: Extracted records (empty list if all attempts failed)
            - recovery_stats: Dictionary with recovery information
    """
    from app.scraper import scrape_url
    
    strategist = get_recovery_strategist()
    executor = get_recovery_executor()
    selector_memory = get_selector_memory()
    domain_intel = get_domain_intelligence()
    
    recovery_stats = {
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
    last_error: Optional[Exception] = None
    
    while attempt < max_recovery_attempts:
        attempt += 1
        recovery_stats["attempts"] += 1
        
        try:
            logger.info("Scrape attempt %d/%d for %s", attempt, max_recovery_attempts, url)
            results = await scrape_url(
                url,
                schema_fields,
                min_record_score=min_record_score,
                user_intent=user_intent,
                world_state=world_state,
            )
            
            recovery_stats["success"] = True
            recovery_stats["total_time_ms"] = (time.time() - start_time) * 1000
            logger.info("Scrape succeeded on attempt %d for %s (got %d records)", 
                       attempt, url, len(results))
            return results, recovery_stats
            
        except Exception as e:
            last_error = e
            logger.warning("Scrape attempt %d failed for %s: %s", attempt, url, type(e).__name__)
            
            # Try recovery if we haven't exceeded max attempts
            if attempt < max_recovery_attempts:
                try:
                    # Classify the failure
                    classification = classify_failure(
                        error_message=str(e),
                        fetch_method="playwright",
                    )
                    recovery_stats["failure_classifications"].append({
                        "attempt": attempt,
                        "category": classification.category.value,
                        "confidence": classification.confidence,
                    })
                    
                    # Get domain intelligence for parameter tuning
                    intel = domain_intel.get_intelligence(url)
                    domain_info = {
                        "anti_bot_risk": intel.anti_bot_risk,
                        "failure_rate": intel.failure_rate,
                        "failure_pattern": intel.primary_failure_pattern,
                    }
                    
                    # Generate recovery plan
                    plan = strategist.generate_recovery_plan(
                        classification,
                        attempt_number=attempt,
                        domain_info=domain_info,
                    )
                    
                    logger.info(
                        "Generated recovery plan for %s: %s (reason: %s)",
                        url, plan.primary_action.value, plan.reason
                    )
                    
                    # Attempt recovery
                    recovery_stats["recovery_attempts"] += 1
                    recovery_stats["recovery_actions_taken"].append(plan.primary_action.value)
                    
                    # For now, we'll just wait and retry (basic recovery)
                    # In a full implementation, each action would be registered with handlers
                    if plan.backoff_seconds > 0:
                        logger.info("Backoff %.1f seconds before retry", plan.backoff_seconds)
                        await asyncio.sleep(plan.backoff_seconds)
                    
                    # Special case: if SELECTOR_DECAY, clean up selector memory
                    if classification.category == FailureCategory.SELECTOR_DECAY:
                        logger.info("Selector decay detected, cleaning up selector memory for %s", url)
                        selector_memory.force_cleanup()
                    
                    # Continue to next attempt
                    continue
                    
                except Exception as recovery_error:
                    logger.error("Recovery generation failed: %s", recovery_error)
                    # Fall through to next attempt
                    continue
            else:
                logger.warning("Max recovery attempts (%d) reached for %s", max_recovery_attempts, url)
    
    # All attempts failed
    recovery_stats["total_time_ms"] = (time.time() - start_time) * 1000
    if last_error:
        try:
            classification = classify_failure(str(last_error), "playwright")
            recovery_stats["final_failure_category"] = classification.category.value
        except Exception:
            recovery_stats["final_failure_category"] = "unknown"
    
    logger.error(
        "All %d scrape attempts failed for %s (final error: %s)",
        max_recovery_attempts, url, type(last_error).__name__ if last_error else "unknown"
    )
    
    return [], recovery_stats


# Hook for executor to register handlers
def register_recovery_handlers():
    """Register recovery action handlers with the executor.
    
    This should be called on application startup to wire up all recovery actions
    to their corresponding implementations.
    """
    from app.recovery_strategies import (
        get_recovery_executor,
        RecoveryAction,
    )
    from app.browser_pool import get_browser_pool
    from app.proxy_manager import get_proxy_manager
    from app.selector_memory import get_selector_memory
    from app.rate_limiter import get_rate_limiter
    
    executor = get_recovery_executor()
    
    # Register placeholder handlers (in production, these would do real work)
    async def noop_handler(params: dict, context: dict) -> bool:
        return True
    
    # Register all actions with noop handlers for now
    # In a full implementation, these would be wired to real recovery logic
    for action in RecoveryAction:
        executor.register_handler(action, noop_handler)

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
from typing import Any, Dict, Optional

from app.failure_classification import classify_failure, FailureCategory
from app.config import settings
from app.recovery_strategies import get_recovery_strategist, get_recovery_executor, AttemptContext
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
    from app.scraper import scrape_url
    
    strategist = get_recovery_strategist()
    executor = get_recovery_executor()
    selector_memory = get_selector_memory()
    get_domain_intelligence()
    
    recovery_stats: Dict[str, Any] = {
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
    attempt_ctx = AttemptContext()
    
    while attempt < max_recovery_attempts:
        attempt += 1
        recovery_stats["attempts"] += 1
        
        try:
            # Chaos failure injection check
            from app.chaos_simulator import get_chaos_simulator, FailureMode
            chaos = get_chaos_simulator()
            
            if chaos.is_failure_active(FailureMode.NETWORK_TIMEOUT):
                logger.warning("[Chaos Simulation] Injecting NETWORK_TIMEOUT")
                raise Exception("Timed out waiting for response")
                
            if chaos.is_failure_active(FailureMode.BROWSER_CRASH):
                logger.warning("[Chaos Simulation] Injecting BROWSER_CRASH")
                raise Exception("Browser target closed unexpectedly")
                
            if chaos.is_failure_active(FailureMode.ANTI_BOT_ESCALATION):
                logger.warning("[Chaos Simulation] Injecting ANTI_BOT_ESCALATION")
                raise Exception("403 Forbidden - WAF Challenge")
                
            if chaos.is_failure_active(FailureMode.SELECTOR_POISONING):
                logger.warning("[Chaos Simulation] Injecting SELECTOR_POISONING (zero records)")
                results = []
            else:
                results = await scrape_url(
                    url,
                    schema_fields,
                    min_record_score=min_record_score,
                    user_intent=user_intent,
                    world_state=world_state,
                    selectors_map=selectors_map,
                    search_params=search_params,
                )
            
            # Since scrape_url catches exceptions and returns [], 
            # we must check telemetry to see if it actually failed.
            from app.scrape_telemetry import get_scrape_telemetry
            telemetry = get_scrape_telemetry()
            last_event = telemetry.get_last_for_url(url)
            
            if last_event and last_event.error:
                # It was a fetch or structural failure
                logger.warning("Scrape attempt %d failed: %s", attempt, last_event.error)
                raise Exception(last_event.error)
            
            if not results and attempt < max_recovery_attempts:
                # Extraction returned nothing - treat as failure to trigger recovery
                logger.warning("Scrape attempt %d returned 0 records, triggering recovery", attempt)
                raise Exception("zero_records_extracted")
            
            recovery_stats["success"] = True
            recovery_stats["total_time_ms"] = (time.time() - start_time) * 1000
            logger.info("Scrape succeeded on attempt %d for %s (got %d records)", 
                       attempt, url, len(results))
            return results, recovery_stats
            
        except Exception as e:
            last_error = e
            error_msg = str(e)
            
            # Get telemetry if available for richer classification
            from app.scrape_telemetry import get_scrape_telemetry
            last_event = get_scrape_telemetry().get_last_for_url(url)
            event_dict = last_event.to_dict() if last_event else {}
            
            # 1. Classify the failure
            classification = classify_failure(
                error_message=error_msg,
                telemetry=event_dict,
                html=None, # We don't have HTML here, scrape_url doesn't return it
            )
            recovery_stats["failure_classifications"].append(classification.to_dict())
            recovery_stats["final_failure_category"] = classification.category.value
            
            # Special case: if SELECTOR_DECAY, clean up selector memory
            if classification.category == FailureCategory.SELECTOR_DECAY:
                logger.info("Selector decay detected, cleaning up selector memory for %s", url)
                selector_memory.force_cleanup()

            if attempt >= max_recovery_attempts:
                break
                
            # 2. Generate recovery plan
            plan = strategist.generate_recovery_plan(classification, attempt)
            logger.info("Generated recovery plan for %s: %s (attempt %d)", 
                       url, plan.primary_action.value, attempt)
            
            # 3. Execute recovery
            recovery_stats["recovery_attempts"] += 1
            recovery_stats["recovery_actions_taken"].append(plan.primary_action.value)
            
            success = await executor.execute(plan, context={
                "url": url,
                "attempt": attempt,
                "world_state": world_state,
            }, attempt_ctx=attempt_ctx)
            
            if not success:
                logger.warning("Recovery action %s failed for %s", plan.primary_action.value, url)
            
            # Apply attempt context changes for next scrape
            if attempt_ctx.bypass_selector_memory:
                selector_memory.force_cleanup()
            if attempt_ctx.force_llm_discovery and selectors_map:
                selectors_map = None  # Force fresh discovery on retry
            
            # Exponential backoff
            await asyncio.sleep(plan.backoff_seconds)
            
    recovery_stats["total_time_ms"] = (time.time() - start_time) * 1000
    logger.error("All %d scrape attempts failed for %s. Last error: %s", 
                max_recovery_attempts, url, last_error)
    return [], recovery_stats

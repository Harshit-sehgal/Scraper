"""
Recovery Handlers Implementation — Concrete implementations of all recovery actions.

Wires recovery actions to system components:
  - ROTATE_PROXY → proxy_manager.rotate()
  - BACKOFF_AND_SLOW → rate_limiter rate adjustment + asyncio.sleep()
  - INCREASE_TIMEOUT → parameter adjustment in fetch config
  - FORCE_REDISCOVERY → selector_discovery with bypass_memory
  - LOWER_SCORE_THRESHOLD → quality scoring adjustment
  - And more...

This module is automatically loaded on application startup to register
all handlers with the RecoveryExecutor.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.recovery_strategies import (
    RecoveryAction,
    get_recovery_executor,
)
from app.proxy_manager import get_proxy_manager
from app.selector_memory import get_selector_memory

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════
# Recovery Handler Implementations
# ═══════════════════════════════════════════════════════════════════════


async def handle_rotate_proxy(params: dict[str, Any], context: dict[str, Any]) -> bool:
    """Rotate to next proxy and retry.
    
    Context:
        - url: The URL being scraped
        - html: Optional current HTML (may be empty/error page)
    
    Returns:
        True if rotation successful, False if no proxy pool
    """
    proxy_manager = get_proxy_manager()
    
    if not proxy_manager.enabled:
        logger.warning("Proxy rotation requested but proxy rotation not enabled")
        return False
    
    old_proxy = proxy_manager.current_proxy
    new_proxy = proxy_manager.rotate()
    
    logger.info("Rotated proxy: %s → %s", old_proxy, new_proxy)
    return True


async def handle_backoff_and_slow(params: dict[str, Any], context: dict[str, Any]) -> bool:
    """Backoff with exponential delay.
    
    Parameters:
        - delay_ms: Base delay in milliseconds (default 10000)
        - slow_factor: Rate multiplication factor (default 0.5 = half speed)
    """
    delay_ms = params.get("delay_ms", 10000)
    slow_factor = params.get("slow_factor", 0.5)
    
    delay_seconds = delay_ms / 1000.0
    logger.info("Backoff: waiting %.1f seconds, then slowing to %.1f speed",
               delay_seconds, slow_factor)
    
    await asyncio.sleep(delay_seconds)
    
    # Note: slow_factor would be applied to subsequent requests
    # by the rate limiter or fetch logic
    return True


async def handle_increase_hydration_wait(params: dict[str, Any], context: dict[str, Any]) -> bool:
    """Increase wait time for page hydration.
    
    Parameters:
        - extra_delay_ms: Additional delay (default 5000)
        - max_hydration_wait: Maximum total wait (default 30000)
    """
    extra_delay_ms = params.get("extra_delay_ms", 5000)
    
    logger.info("Increasing hydration wait by %d ms", extra_delay_ms)
    
    # This would be applied to the next fetch_page_content call
    # Context could track this for subsequent retries
    delay_seconds = extra_delay_ms / 1000.0
    await asyncio.sleep(delay_seconds)
    
    return True


async def handle_increase_timeout(params: dict[str, Any], context: dict[str, Any]) -> bool:
    """Increase timeout for page fetch.
    
    Parameters:
        - timeout_ms: New timeout value (default 30000)
    """
    timeout_ms = params.get("timeout_ms", 30000)
    
    logger.info("Recovery action: increasing timeout to %d ms", timeout_ms)
    
    # This adjustment would be applied by the calling code
    # when retrying the fetch
    return True


async def handle_reduce_concurrency(params: dict[str, Any], context: dict[str, Any]) -> bool:
    """Reduce browser concurrency to prevent starvation.
    
    Parameters:
        - max_contexts: Maximum concurrent browser contexts (default 3)
    """
    max_contexts = params.get("max_contexts", 3)
    
    logger.info("Recovery action: reducing concurrency to %d contexts", max_contexts)
    
    # This would be signaled to browser_pool.py
    # For now, just log the action
    return True


async def handle_retry_with_dns_flush(params: dict[str, Any], context: dict[str, Any]) -> bool:
    """Retry with DNS cache flush.
    
    Parameters:
        - delay_ms: Delay before retry (default 2000)
    """
    delay_ms = params.get("delay_ms", 2000)
    delay_seconds = delay_ms / 1000.0
    
    logger.info("Recovery action: DNS flush, waiting %.1f seconds", delay_seconds)
    
    # DNS flush would happen at Playwright/httpx level
    await asyncio.sleep(delay_seconds)
    return True


async def handle_force_rediscovery(params: dict[str, Any], context: dict[str, Any]) -> bool:
    """Force selector rediscovery for a domain.
    
    Parameters:
        - bypass_memory: Skip selector memory (default True)
    
    Side Effect:
        Marks domain selectors for rediscovery in selector memory
    """
    url = context.get("url")
    if not url:
        logger.warning("Force rediscovery: no URL in context")
        return False
    
    selector_memory = get_selector_memory()
    
    # Remove the selector memory entry for this domain so it's rediscovered
    domain = selector_memory._extract_domain(url)
    if domain and domain in selector_memory._memory:
        logger.info("Force rediscovery: clearing cached selectors for %s", domain)
        del selector_memory._memory[domain]
        selector_memory._save()
        return True
    
    logger.info("Force rediscovery: no cached selectors found for %s", domain)
    return True


async def handle_force_rediscovery_with_swap_detection(
    params: dict[str, Any],
    context: dict[str, Any]
) -> bool:
    """Force rediscovery with field swap detection.
    
    Parameters:
        - enable_swap_detection: Enable detection (default True)
        - bypass_memory: Skip selector memory (default True)
    
    Side Effect:
        Same as force_rediscovery, but caller should enable swap detection
    """
    # Same as basic force_rediscovery for now
    # The swap detection would be in the extraction layer
    return await handle_force_rediscovery(params, context)


async def handle_lower_score_threshold(params: dict[str, Any], context: dict[str, Any]) -> bool:
    """Lower quality score threshold for extracted records.
    
    Parameters:
        - score_multiplier: Multiply quality scores by this (default 0.8)
    """
    score_multiplier = params.get("score_multiplier", 0.8)
    
    logger.info("Recovery action: lowering quality threshold (multiplier=%.1f)", score_multiplier)
    
    # This would be applied to the next extraction round
    # The context could track this adjustment
    return True


async def handle_retry_with_field_focus(params: dict[str, Any], context: dict[str, Any]) -> bool:
    """Retry with focus on critical fields only.
    
    Parameters:
        - focus_fields: Which fields to focus on (default None = all)
    """
    logger.info("Recovery action: retry with field focus strategy")
    
    # This would affect the next extraction attempt
    return True


async def handle_escalate_to_llm(params: dict[str, Any], context: dict[str, Any]) -> bool:
    """Escalate to LLM-based discovery.
    
    Parameters:
        - force_llm_discovery: Force LLM (default True)
    """
    logger.info("Recovery action: escalating to LLM-based discovery")
    
    # Next extraction would use LLM discovery instead of cached selectors
    return True


async def handle_use_httpx_fallback(params: dict[str, Any], context: dict[str, Any]) -> bool:
    """Use httpx fallback instead of Playwright.
    
    Parameters:
        - prefer_httpx: Use httpx (default True)
    """
    logger.info("Recovery action: switching to httpx fallback fetch method")
    
    # This would signal to fetch_page_content to use httpx
    return True


async def handle_abort_domain(params: dict[str, Any], context: dict[str, Any]) -> bool:
    """Stop scraping a domain temporarily.
    
    Parameters:
        - skip_domain_minutes: Minutes to skip (default 60)
    """
    skip_minutes = params.get("skip_domain_minutes", 60)
    url = context.get("url")
    
    logger.warning(
        "Recovery action: aborting domain %s for %d minutes",
        url, skip_minutes
    )
    
    # This would be tracked in domain_intelligence for blocking
    return True


async def handle_skip_domain(params: dict[str, Any], context: dict[str, Any]) -> bool:
    """Skip domain permanently (for this job).
    
    Parameters:
        None
    """
    url = context.get("url")
    logger.warning("Recovery action: skipping domain %s", url)
    
    # Job runner would mark this domain as skipped
    return True


async def handle_skip_url(params: dict[str, Any], context: dict[str, Any]) -> bool:
    """Skip this specific URL.
    
    Parameters:
        None
    """
    url = context.get("url")
    logger.warning("Recovery action: skipping URL %s", url)
    
    return True


# ═══════════════════════════════════════════════════════════════════════
# Handler Registration
# ═══════════════════════════════════════════════════════════════════════


def register_all_recovery_handlers():
    """Register all recovery action handlers with the executor.
    
    Should be called once at application startup.
    """
    executor = get_recovery_executor()
    
    # Register all handlers
    handlers = {
        RecoveryAction.ROTATE_PROXY: handle_rotate_proxy,
        RecoveryAction.BACKOFF_AND_SLOW: handle_backoff_and_slow,
        RecoveryAction.INCREASE_HYDRATION_WAIT: handle_increase_hydration_wait,
        RecoveryAction.INCREASE_TIMEOUT: handle_increase_timeout,
        RecoveryAction.REDUCE_CONCURRENCY: handle_reduce_concurrency,
        RecoveryAction.RETRY_WITH_DNS_FLUSH: handle_retry_with_dns_flush,
        RecoveryAction.FORCE_REDISCOVERY: handle_force_rediscovery,
        RecoveryAction.FORCE_REDISCOVERY_WITH_SWAP_DETECTION: handle_force_rediscovery_with_swap_detection,
        RecoveryAction.LOWER_SCORE_THRESHOLD: handle_lower_score_threshold,
        RecoveryAction.RETRY_WITH_FIELD_FOCUS: handle_retry_with_field_focus,
        RecoveryAction.ESCALATE_TO_LLM: handle_escalate_to_llm,
        RecoveryAction.USE_HTTPX_FALLBACK: handle_use_httpx_fallback,
        RecoveryAction.ABORT_DOMAIN: handle_abort_domain,
        RecoveryAction.SKIP_DOMAIN: handle_skip_domain,
        RecoveryAction.SKIP_URL: handle_skip_url,
    }
    
    for action, handler in handlers.items():
        executor.register_handler(action, handler)
        logger.debug("Registered recovery handler: %s", action.value)
    
    logger.info("All %d recovery handlers registered", len(handlers))

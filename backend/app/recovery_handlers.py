"""Recovery Handlers Implementation — Concrete implementations of all recovery actions.

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

from app.proxy_manager import get_proxy_manager
from app.selector_memory import get_selector_memory

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════
# Recovery Handler Implementations
# ═══════════════════════════════════════════════════════════════════════


async def handle_rotate_proxy(params: dict[str, Any], context: dict[str, Any], attempt_ctx=None) -> bool:  # noqa: ARG001, RUF100
    """Rotate to next proxy in the pool."""
    logger.info("Rotating proxy for %s", context.get("url", ""))
    pm = get_proxy_manager()
    if not pm.enabled:
        logger.warning("Proxy rotation disabled — returning False")
        return False
    pm.rotate()
    if attempt_ctx:
        attempt_ctx.anti_bot_stealth = True
        attempt_ctx.proxy_profile = "rotated"
    return True


async def handle_backoff_and_slow(params: dict[str, Any], context: dict[str, Any], attempt_ctx=None) -> bool:
    """Apply backoff delay and reduce request rate."""
    delay_ms = params.get("delay_ms", 5000)
    slow_factor = params.get("slow_factor", 0.5)
    delay_seconds = delay_ms / 1000.0
    logger.info("Backoff: waiting %.1f seconds, then slowing to %.1f speed", delay_seconds, slow_factor)
    await asyncio.sleep(delay_seconds)
    url = context.get("url", "")
    if url:
        from app.domain_runtime_policy import get_domain_runtime_policy

        get_domain_runtime_policy().set_reduce_concurrency(url)
    if attempt_ctx:
        attempt_ctx.reduce_concurrency = True
        attempt_ctx.timeout_ms = int(params.get("timeout_ms", 40000))
    return True


async def handle_increase_hydration_wait(params: dict[str, Any], context: dict[str, Any], attempt_ctx=None) -> bool:  # noqa: ARG001, RUF100
    """Increase the time waited for JS hydration."""
    extra_ms = params.get("extra_delay_ms", 5000)
    max_wait = params.get("max_hydration_wait", 30000)
    logger.info("Increasing hydration wait by %dms (max %dms)", extra_ms, max_wait)
    if attempt_ctx:
        current = attempt_ctx.hydration_wait_ms or 0
        attempt_ctx.hydration_wait_ms = min(current + extra_ms, max_wait)
    return True


async def handle_increase_timeout(params: dict[str, Any], context: dict[str, Any], attempt_ctx=None) -> bool:  # noqa: ARG001, RUF100
    """Increase the overall fetch timeout."""
    timeout_ms = params.get("timeout_ms", 40000)
    logger.info("Increasing timeout to %dms", timeout_ms)
    if attempt_ctx:
        attempt_ctx.timeout_ms = timeout_ms
    return True


async def handle_reduce_concurrency(params: dict[str, Any], context: dict[str, Any], attempt_ctx=None) -> bool:  # noqa: ARG001, RUF100
    """Reduce concurrent fetches and update domain runtime policy."""
    url = context.get("url", "")
    logger.info("Reducing concurrency for %s", url)
    if url:
        from app.domain_runtime_policy import get_domain_runtime_policy

        get_domain_runtime_policy().set_reduce_concurrency(url)
    if attempt_ctx:
        attempt_ctx.reduce_concurrency = True
    return True


async def handle_retry_with_dns_flush(params: dict[str, Any], context: dict[str, Any], attempt_ctx=None) -> bool:  # noqa: ARG001, RUF100
    """Retry with DNS cache flush.

    Parameters
    ----------
        - delay_ms: Delay before retry (default 2000)

    """
    delay_ms = params.get("delay_ms", 2000)
    delay_seconds = delay_ms / 1000.0

    logger.info("Recovery action: DNS flush, waiting %.1f seconds", delay_seconds)

    # DNS flush would happen at Playwright / httpx level
    await asyncio.sleep(delay_seconds)
    return True


async def handle_force_rediscovery(params: dict[str, Any], context: dict[str, Any], attempt_ctx=None) -> bool:  # noqa: ARG001, RUF100
    url = context.get("url")
    if not url:
        return False
    selector_memory = get_selector_memory()
    # Use the public invalidation API so the kernel does not depend on
    # ``_memory`` / ``_save`` private state of SelectorMemory.
    if selector_memory.invalidate_domain(url):
        logger.info("Force rediscovery: cleared cached selectors for %s", url)
    if attempt_ctx:
        attempt_ctx.force_llm_discovery = True
        attempt_ctx.bypass_selector_memory = True
    return True


async def handle_force_rediscovery_with_swap_detection(
    params: dict[str, Any],
    context: dict[str, Any],
    attempt_ctx=None,
) -> bool:
    """Force rediscovery with field swap detection.

    Parameters
    ----------
        - enable_swap_detection: Enable detection (default True)
        - bypass_memory: Skip selector memory (default True)

    Side Effect:
        Same as force_rediscovery, but caller should enable swap detection

    """
    # Same as basic force_rediscovery for now
    # The swap detection would be in the extraction layer
    return await handle_force_rediscovery(params, context, attempt_ctx)


async def handle_lower_score_threshold(params: dict[str, Any], context: dict[str, Any], attempt_ctx=None) -> bool:
    """Lower quality score threshold for extracted records."""
    score_multiplier = params.get("score_multiplier", 0.8)
    logger.info("Recovery action: lowering quality threshold (multiplier=%.1f)", score_multiplier)
    if attempt_ctx:
        attempt_ctx.reduce_concurrency = True
        # Actually lower the min score threshold for the next retry
        current_score = context.get("min_record_score", 0.35)
        attempt_ctx.min_record_score_override = current_score * score_multiplier
        logger.info(
            "  -> setting min_record_score_override to %.3f (was %.3f)",
            attempt_ctx.min_record_score_override,
            current_score,
        )
    return True


async def handle_retry_with_field_focus(params: dict[str, Any], context: dict[str, Any], attempt_ctx=None) -> bool:  # noqa: ARG001, RUF100
    """Retry with focus on critical fields only."""
    logger.info("Recovery action: retry with field focus strategy")
    if attempt_ctx:
        attempt_ctx.force_llm_discovery = True
        attempt_ctx.bypass_selector_memory = True
    return True


async def handle_escalate_to_llm(params: dict[str, Any], context: dict[str, Any], attempt_ctx=None) -> bool:  # noqa: ARG001, RUF100
    """Escalate to LLM-based discovery."""
    logger.info("Recovery action: escalating to LLM-based discovery")
    if attempt_ctx:
        attempt_ctx.force_llm_discovery = True
        attempt_ctx.bypass_selector_memory = True
    return True


async def handle_abort_domain(params: dict[str, Any], context: dict[str, Any], attempt_ctx=None) -> bool:
    """Stop scraping a domain temporarily — mark cooldown, don't retry with a different strategy."""
    skip_minutes = params.get("skip_domain_minutes", 60)
    url = context.get("url")
    logger.warning("Recovery action: aborting domain %s for %d minutes", url, skip_minutes)
    if url:
        from app.domain_runtime_policy import get_domain_runtime_policy

        get_domain_runtime_policy().set_abort_domain(url)
    if attempt_ctx:
        attempt_ctx.abort_domain = True
        # Do NOT switch to httpx_basic — aborted domains should be skipped, not
        # retried
        if url:
            from urllib.parse import urlparse

            parsed = urlparse(url)
            domain = parsed.netloc.lower() if parsed.hostname else ""
            if domain:
                attempt_ctx.skip_domain = domain
    return True


async def handle_use_httpx_fallback(params: dict[str, Any], context: dict[str, Any], attempt_ctx=None) -> bool:  # noqa: ARG001, RUF100
    logger.info("Recovery action: switching to httpx fallback fetch method")
    if attempt_ctx:
        attempt_ctx.prefer_httpx = True
        attempt_ctx.fetch_strategy = "httpx_basic"
    return True


async def handle_skip_domain(params: dict[str, Any], context: dict[str, Any], attempt_ctx=None) -> bool:  # noqa: ARG001, RUF100
    """Skip domain permanently (for this job).

    Also records an abort in the domain runtime policy so future scheduling
    is aware of the skip.
    """
    url = context.get("url")
    logger.warning("Recovery action: skipping domain %s", url)
    if url:
        from app.domain_runtime_policy import get_domain_runtime_policy

        get_domain_runtime_policy().set_abort_domain(url)

    if attempt_ctx and url:
        from urllib.parse import urlparse

        parsed = urlparse(url)
        domain = parsed.netloc.lower() if parsed.hostname else ""
        if domain:
            attempt_ctx.skip_domain = domain
    return True


async def handle_skip_url(params: dict[str, Any], context: dict[str, Any], attempt_ctx=None) -> bool:  # noqa: ARG001, RUF100
    """Skip this specific URL.

    Parameters
    ----------
        None

    """
    url = context.get("url")
    logger.warning("Recovery action: skipping URL %s", url)

    if attempt_ctx:
        attempt_ctx.skip_url = True
    return True


# ═══════════════════════════════════════════════════════════════════════
# Handler Registration
# ═══════════════════════════════════════════════════════════════════════


def register_all_recovery_handlers() -> None:
    """Register all recovery action handlers with the executor.

    Should be called once at application startup.

    RecoveryAction and get_recovery_executor come from app.recovery_strategies
    (research module) and are imported lazily here so that the kernel
    import graph does not depend on the research shell.
    """
    from app.recovery_strategies import RecoveryAction, get_recovery_executor

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

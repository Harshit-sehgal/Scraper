"""
Scraper Router — endpoints for scraper observability, memory, and configuration.
"""

from __future__ import annotations

import logging
from typing import List

from fastapi import APIRouter, HTTPException

from app.config import settings
from app.scrape_telemetry import get_scrape_telemetry
from app.selector_memory import get_selector_memory
from app.scraper_diagnostics import run_diagnostics
from app.models import SchemaField
from app.browser_pool import get_browser_pool

router = APIRouter(prefix="/api/scraper", tags=["scraper"])
logger = logging.getLogger(__name__)


@router.get("/config")
async def get_scraper_config():
    """Return current scraper-related settings."""
    return {
        "playwright_timeout": settings.PLAYWRIGHT_TIMEOUT,
        "page_settle_delay": settings.PAGE_SETTLE_DELAY,
        "request_timeout": settings.REQUEST_TIMEOUT,
        "max_retries": settings.MAX_RETRIES,
        "max_records_per_source": settings.MAX_RECORDS_PER_SOURCE,
        "selector_snippet_max_chars": settings.SELECTOR_SNIPPET_MAX_CHARS,
        "regex_max_containers": settings.REGEX_MAX_CONTAINERS,
    }


@router.get("/telemetry")
async def get_recent_telemetry(n: int = 20):
    """Return the N most recent scrape telemetry events."""
    return get_scrape_telemetry().get_recent(n)


@router.get("/memory")
async def get_selector_memory_stats():
    """Return statistics on remembered selectors."""
    memory = get_selector_memory()
    return {
        "domain_count": len(memory._memory),
        "total_successes": sum(e.get("success_count", 0) for e in memory._memory.values()),
        "total_failures": sum(e.get("failure_count", 0) for e in memory._memory.values()),
        "top_domains": sorted(
            [{"domain": d, "success": e.get("success_count", 0)} for d, e in memory._memory.items()],
            key=lambda x: x["success"],
            reverse=True
        )[:10]
    }


@router.get("/browser")
async def get_browser_stats():
    """Return browser pool operational metrics."""
    return get_browser_pool().get_metrics()


@router.get("/health")
async def get_all_domains_health():
    """Return health scores for all tracked domains."""
    from app.crawl_policy import get_crawl_policy
    policy = get_crawl_policy()
    states = policy.get_all_domain_states()
    
    health = {}
    for domain in states:
        if domain.startswith("_"): continue
        health[domain] = policy.get_domain_health_score(domain)
        
    return health


@router.get("/stats")
async def get_scraper_stats():
    """Return aggregated scraper performance statistics."""
    telemetry = get_scrape_telemetry()
    return {
        "confidence_histogram": telemetry.get_confidence_histogram(),
        "recent_latency_avg": sum(t["fetch_ms"] for t in telemetry.get_recent(10)) / 10 if telemetry._history else 0,
        "recent_success_rate": sum(1 for t in telemetry.get_recent(20) if not t["fallback_triggered"]) / 20 if telemetry._history else 1.0,
    }


@router.delete("/telemetry")
async def clear_telemetry():
    """Clear all scrape telemetry history."""
    get_scrape_telemetry().clear()
    return {"status": "ok"}


@router.post("/diagnostics")
async def get_scraper_diagnostics(
    url: str,
    fields: list[SchemaField],
    min_score: float = 0.3
):
    """Run a deep diagnostic scrape for a URL."""
    report = await run_diagnostics(url, fields, min_record_score=min_score)
    return report.to_dict()

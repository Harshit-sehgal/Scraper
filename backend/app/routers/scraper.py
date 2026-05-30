"""
Scraper Router — endpoints for scraper observability, memory, configuration,
trend analysis, and economic tracking.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Depends

from app.config import settings
from app.utils.rbac import UserRole, require_role
from app.scrape_telemetry import get_scrape_telemetry
from app.selector_memory import get_selector_memory
from app.scraper_diagnostics import run_diagnostics
from app.models import SchemaField
from app.browser_pool import get_browser_pool
from app.trend_analyzer import TrendAnalyzer, EconomicTracker
from app.regression_capture import get_regression_capture

router = APIRouter(prefix="/api / scraper", tags=["scraper"])
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


@router.get("/memory / stats")
async def get_selector_memory_brief():
    """Return brief statistics on remembered selectors."""
    memory = get_selector_memory()
    return {
        "domain_count": len(memory._memory),
        "total_successes": sum(e.get("success_count", 0) for e in memory._memory.values()),
        "total_failures": sum(e.get("failure_count", 0) for e in memory._memory.values()),
        "top_domains": sorted(
            [{"domain": d, "success": e.get("success_count", 0)} for d, e in memory._memory.items()],
            key=lambda x: x["success"],
            reverse=True,
        )[:10],
    }


@router.get("/browser")
async def get_browser_stats():
    """Return browser pool operational metrics."""
    return get_browser_pool().get_metrics()


@router.get("/health / legacy")
async def get_legacy_domain_health():
    """Return health scores for all tracked domains (legacy crawl policy)."""
    from app.crawl_policy import get_crawl_policy

    policy = get_crawl_policy()
    states = policy.get_all_domain_states()

    health = {}
    for domain in states:
        if domain.startswith("_"):
            continue
        health[domain] = policy.get_domain_health_score(domain)

    return health


@router.get("/stats")
async def get_scraper_stats():
    """Return aggregated scraper performance statistics."""
    telemetry = get_scrape_telemetry()
    recent_latency = telemetry.get_recent(10)
    recent_success = telemetry.get_recent(20)
    return {
        "confidence_histogram": telemetry.get_confidence_histogram(),
        "recent_latency_avg": (
            sum(float(t.get("fetch_ms", 0) or 0) for t in recent_latency) / len(recent_latency) if recent_latency else 0
        ),
        "recent_success_rate": (
            sum(1 for t in recent_success if not t.get("fallback_triggered", False)) / len(recent_success)
            if recent_success
            else 1.0
        ),
    }


@router.delete("/telemetry")
async def clear_telemetry(_role: UserRole = Depends(require_role([UserRole.ADMIN]))):
    """Clear all scrape telemetry history."""
    get_scrape_telemetry().clear()
    return {"status": "ok"}


@router.post("/diagnostics")
async def get_scraper_diagnostics(
    url: str,
    fields: list[SchemaField],
    min_score: float = 0.3,
    _role: UserRole = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
):
    """Run a deep diagnostic scrape for a URL.

    Requires operator or admin role — triggers browser / network work.
    """
    report = await run_diagnostics(url, fields, min_record_score=min_score)
    return report.to_dict()


# ═══════════════════════════════════════════════════════════════════════
# Trend Analysis & Telemetry Intelligence
# ═══════════════════════════════════════════════════════════════════════


@router.get("/trends")
async def get_extraction_trends(window: int = Query(100, ge=10, le=500)):
    """Analyze scrape telemetry for degradation patterns, domain health trends,
    and actionable alerts.

    Args:
        window: Number of recent telemetry events to analyze (10 - 500).

    Returns:
        A TrendReport with domain-level trends, global metrics, and alerts.
    """
    telemetry_history = get_scrape_telemetry().get_recent(window)
    analyzer = TrendAnalyzer(history_window=window)
    report = analyzer.analyze(telemetry_history)
    return {
        "generated_at": report.generated_at,
        "domain_count": report.domain_count,
        "degrading_domains": report.degrading_domains,
        "improving_domains": report.improving_domains,
        "stable_domains": report.stable_domains,
        "unseen_domains": report.unseen_domains,
        "global_failure_rate": round(report.global_failure_rate, 3),
        "global_avg_latency_ms": round(report.global_avg_latency_ms, 1),
        "total_scrapes": report.total_scrapes,
        "alerts": report.alerts,
        "domain_trends": {
            d: {
                "health_score": t.health_score,
                "failure_rate": round(t.failure_rate, 3),
                "avg_fetch_ms": round(t.avg_fetch_ms, 1),
                "avg_quality_score": round(t.avg_quality_score, 3),
                "quality_trend": t.quality_trend,
                "anti_bot_trend": t.anti_bot_trend,
                "fetch_latency_trend": t.fetch_latency_trend,
                "selector_decay_accelerating": t.selector_decay_accelerating,
                "top_failure_categories": t.top_failure_categories,
                "sample_count": t.sample_count,
            }
            for d, t in report.domain_trends.items()
        },
    }


@router.get("/trends/{domain}")
async def get_domain_trend(
    domain: str,
    window: int = Query(100, ge=10, le=500),
):
    """Get detailed trend analysis for a specific domain."""
    telemetry_history = get_scrape_telemetry().get_recent(window)

    # Filter to only this domain's events
    from app.trend_analyzer import TrendAnalyzer as TA

    domain_events = [e for e in telemetry_history if TA.extract_domain(e.get("url", "")) == domain.lower()]

    if not domain_events:
        raise HTTPException(
            status_code=404,
            detail=f"No telemetry data found for domain: {domain}",
        )

    analyzer = TrendAnalyzer(history_window=window)
    trend = analyzer.analyze_domain(domain, domain_events)

    return {
        "domain": trend.domain,
        "health_score": trend.health_score,
        "total_scrapes": trend.total_scrapes,
        "total_failures": trend.total_failures,
        "failure_rate": round(trend.failure_rate, 3),
        "avg_fetch_ms": round(trend.avg_fetch_ms, 1),
        "avg_quality_score": round(trend.avg_quality_score, 3),
        "fetch_latency_trend": trend.fetch_latency_trend,
        "quality_trend": trend.quality_trend,
        "anti_bot_trend": trend.anti_bot_trend,
        "selector_decay_accelerating": trend.selector_decay_accelerating,
        "avg_cost_usd": round(trend.avg_cost_usd, 4),
        "top_failure_categories": trend.top_failure_categories,
        "sample_count": trend.sample_count,
    }


# ═══════════════════════════════════════════════════════════════════════
# Regression Capture & Autonomous Benchmark Evolution
# ═══════════════════════════════════════════════════════════════════════


@router.get("/regressions")
async def get_regression_archive(limit: int = Query(20, ge=1, le=100)):
    """Return the regression capture archive — statistics and recent captures.

    The regression capture system automatically archives extraction failures
    as named fixtures in fixtures / pages/, building an organic benchmark suite
    from real operational failures.

    Args:
        limit: Maximum number of recent captures to return (1 - 100).

    Returns:
        Archive statistics and the most recent capture entries.
    """
    capture = get_regression_capture()
    stats = capture.get_statistics()
    # Trim recent captures to the requested limit
    stats["recent_captures"] = stats.get("recent_captures", [])[:limit]
    return stats


@router.get("/regressions/{entry_id}")
async def get_regression_detail(entry_id: str):
    """Return detailed information about a specific regression capture."""
    capture = get_regression_capture()
    registry = capture.get_registry()
    for e in registry.entries:
        if e.id == entry_id:
            return {
                "id": e.id,
                "url": e.url,
                "domain": e.domain,
                "failure_category": e.failure_category,
                "failure_confidence": e.failure_confidence,
                "html_preview": e.html_preview[:500],
                "html_size": e.html_size,
                "captured_at": e.captured_at,
                "schema_fields": e.schema_fields,
                "fixture_filename": e.fixture_filename,
                "has_replay_test": e.replay_test_generated,
                "telemetry_snapshot": e.telemetry_snapshot,
            }
    raise HTTPException(status_code=404, detail=f"Regression entry not found: {entry_id}")


@router.post("/regressions/{entry_id}/generate-test")
async def generate_regression_replay_test(entry_id: str):
    """Generate a pytest replay test for a captured regression."""
    capture = get_regression_capture()
    test_code = capture.generate_replay_test(entry_id)
    if test_code is None:
        raise HTTPException(
            status_code=404,
            detail=f"Regression entry not found or fixture missing: {entry_id}",
        )
    return {"entry_id": entry_id, "test_code": test_code}


@router.post("/regressions / generate-all-tests")
async def generate_all_replay_tests():
    """Generate replay tests for all captured regressions that lack one."""
    capture = get_regression_capture()
    all_tests = capture.generate_all_replay_tests()
    return {
        "total_tests_generated": all_tests.count("TEST SEPARATOR") + 1 if all_tests else 0,
        "test_code": all_tests,
    }


# ═══════════════════════════════════════════════════════════════════════
# Economic Tracking & Cost Analysis
# ═══════════════════════════════════════════════════════════════════════


@router.get("/economics")
async def get_extraction_economics(window: int = Query(200, ge=10, le=1000)):
    """Return extraction cost and efficiency analysis.

    Provides cost breakdowns by domain and category (LLM, browser, network),
    with efficiency ratings.
    """
    telemetry_history = get_scrape_telemetry().get_recent(window)
    tracker = EconomicTracker()
    report = tracker.analyze(telemetry_history)

    return {
        "generated_at": report.generated_at,
        "total_cost_usd": report.total_cost_usd,
        "total_scrapes": report.total_scrapes,
        "total_records": report.total_records,
        "avg_cost_per_scrape": report.avg_cost_per_scrape,
        "avg_cost_per_record": report.avg_cost_per_record,
        "efficiency_rating": report.efficiency_rating,
        "cost_by_category": report.cost_by_category,
        "most_expensive_domains": report.most_expensive_domains,
        "least_expensive_domains": report.least_expensive_domains,
        "cost_by_domain": {
            d: {
                "total_cost_usd": s.total_cost_usd,
                "avg_cost_per_scrape": s.avg_cost_per_scrape,
                "avg_cost_per_record": s.avg_cost_per_record,
                "total_records": s.total_records,
                "total_scrapes": s.total_scrapes,
                "cost_breakdown": s.cost_breakdown,
                "efficiency_rating": s.efficiency_rating,
            }
            for d, s in report.cost_by_domain.items()
        },
    }


# ─── Domain Health Monitoring Endpoints ──────────────────────────────────


@router.get("/health / domains")
async def get_all_domains_health():
    """Get health status for all monitored domains.

    Returns a sorted list of domains with health scores and alerts.
    Useful for dashboards and automated alerting systems.
    """
    from app.domain_health_alerts import get_domain_health_monitor

    monitor = get_domain_health_monitor()
    domains_health = monitor.get_all_domains_health()

    return {
        "total_domains_monitored": len(domains_health),
        "domains": domains_health,
        "summary": {
            "healthy": sum(1 for d in domains_health if d["health_level"] == "healthy"),
            "degrading": sum(1 for d in domains_health if d["health_level"] == "degrading"),
            "unhealthy": sum(1 for d in domains_health if d["health_level"] == "unhealthy"),
            "critical": sum(1 for d in domains_health if d["health_level"] == "critical"),
            "blacklisted": sum(1 for d in domains_health if d["health_level"] == "blacklisted"),
        },
    }


@router.get("/health / domain/{domain}")
async def get_domain_health(domain: str):
    """Get detailed health status for a specific domain.

    Returns comprehensive health metrics including:
    - Health level (healthy / degrading / unhealthy / critical / blacklisted)
    - Health score (0.0 to 1.0)
    - Success rate
    - Consistency score (how uniform failures are)
    - Degradation trend (positive = worsening)
    - Total attempts
    - Recent failure category
    """
    from app.domain_health_alerts import get_domain_health_monitor

    monitor = get_domain_health_monitor()

    # Create a fake URL to extract domain
    url = f"https://{domain}/"
    health = monitor.get_domain_health(url)

    if health is None:
        raise HTTPException(status_code=404, detail=f"No health data for domain: {domain}")

    return health


@router.get("/health / summary")
async def get_system_health_summary():
    """Get system-wide health summary.

    Provides a quick overview of system health across all domains.
    Useful for dashboards and status pages.
    """
    from app.domain_health_alerts import get_domain_health_monitor

    monitor = get_domain_health_monitor()
    domains_health = monitor.get_all_domains_health()

    if not domains_health:
        return {
            "status": "no_data",
            "domains_monitored": 0,
            "overall_health_score": 0.0,
        }

    # Calculate overall health score
    overall_score = sum(d["health_score"] for d in domains_health) / len(domains_health)

    # Determine overall status
    if overall_score >= 0.8:
        overall_status = "healthy"
    elif overall_score >= 0.7:
        overall_status = "degrading"
    elif overall_score >= 0.5:
        overall_status = "unhealthy"
    else:
        overall_status = "critical"

    return {
        "status": overall_status,
        "overall_health_score": round(overall_score, 3),
        "domains_monitored": len(domains_health),
        "critical_count": sum(1 for d in domains_health if d["health_level"] in ["critical", "blacklisted"]),
        "unhealthy_count": sum(1 for d in domains_health if d["health_level"] in ["unhealthy", "critical"]),
    }


# ─── Selector Memory Stats Endpoints ──────────────────────────────────────


@router.get("/selectors / stats")
async def get_selector_memory_stats():
    """Get selector memory pool statistics.

    Returns aggregate statistics about cached selectors:
    - Total domains with cached selectors
    - Average confidence across all selectors
    - Distribution by confidence level
    - High / medium / low confidence counts
    """
    selector_memory = get_selector_memory()
    stats = selector_memory.get_memory_stats()

    return {
        "total_domains": stats["total_domains"],
        "total_selectors": stats["total_selectors"],
        "avg_confidence": round(stats["avg_confidence"], 3),
        "high_confidence": stats["high_confidence"],  # >= 0.75
        "medium_confidence": stats["medium_confidence"],  # 0.5 - 0.74
        "low_confidence": stats["low_confidence"],  # < 0.5
        "confidence_distribution": stats["by_confidence"],
    }


@router.get("/selectors / domain/{domain}")
async def get_domain_selector_confidence(domain: str):
    """Get selector confidence for a specific domain.

    Returns detailed confidence metrics:
    - Raw confidence (success rate)
    - Age factor (degradation over time)
    - Freshness factor (penalty for non-use)
    - Final confidence score
    - Reason (detailed explanation)
    """
    selector_memory = get_selector_memory()

    # Create a fake URL to extract domain
    url = f"https://{domain}/"
    confidence = selector_memory.get_selector_confidence(url)

    if confidence is None:
        raise HTTPException(status_code=404, detail=f"No cached selectors for domain: {domain}")

    return {
        "domain": domain,
        "raw_confidence": round(confidence.raw_confidence, 3),
        "age_factor": round(confidence.age_factor, 3),
        "freshness_factor": round(confidence.freshness_factor, 3),
        "final_score": round(confidence.final_score, 3),
        "reason": confidence.reason,
    }


@router.post("/selectors / cleanup")
async def trigger_selector_cleanup(_role: UserRole = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR]))):
    """Manually trigger selector memory cleanup.

    Forces deletion of all selectors below the confidence threshold,
    regardless of the normal cleanup interval.

    Returns cleanup statistics.
    """
    selector_memory = get_selector_memory()
    stats = selector_memory.force_cleanup()

    if not stats:
        return {
            "message": "Cleanup not performed (too soon after last cleanup)",
            "next_cleanup_available_in_seconds": 86400,
        }

    return {
        "domains_checked": stats["domains_checked"],
        "selectors_deleted": stats["selectors_deleted"],
        "deleted_domains": stats["deleted_domains"],
        "low_confidence_selectors": stats["low_confidence_selectors"],
    }


@router.get("/selectors / low-confidence")
async def get_low_confidence_selectors(threshold: float = Query(0.5, ge=0, le=1)):
    """Get all selectors scoring below the specified threshold.

    Useful for identifying domains at risk of extraction failure.
    """
    selector_memory = get_selector_memory()
    low_confidence = []

    for domain, entry in selector_memory._memory.items():
        confidence = selector_memory._compute_confidence(entry)
        if confidence.final_score < threshold:
            low_confidence.append(
                {
                    "domain": domain,
                    "score": round(confidence.final_score, 3),
                    "raw_confidence": round(confidence.raw_confidence, 3),
                    "age_factor": round(confidence.age_factor, 3),
                    "freshness_factor": round(confidence.freshness_factor, 3),
                    "success_count": entry.get("success_count", 0),
                    "failure_count": entry.get("failure_count", 0),
                    "reason": confidence.reason,
                }
            )

    # Sort by score (worst first)
    low_confidence.sort(key=lambda x: x["score"])

    return {
        "threshold": threshold,
        "count": len(low_confidence),
        "selectors": low_confidence,
    }


# ─── ML Selector Optimization Endpoints ──────────────────────────────────


@router.post("/ml / optimize / domain/{domain}")
async def optimize_domain_selectors(
    domain: str,
    selectors: Optional[dict] = None,
    _role: UserRole = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
):
    """Optimize selectors for a domain using ML predictions.

    Analyzes CSS selector patterns and predicts quality.
    Returns recommendations for improving selectors.

    Parameters:
        - domain: Domain name
        - selectors: Optional dict of {field: css_selector} to analyze

    If no selectors provided, uses cached selectors from memory.
    Requires operator or admin role — triggers ML computation.
    """
    from app.selector_ml_optimizer import get_selector_optimizer

    optimizer = get_selector_optimizer()

    # Get selectors to optimize
    if selectors is None:
        selector_memory = get_selector_memory()
        url = f"https://{domain}/"
        cached = selector_memory.get_selectors(url)

        if not cached:
            raise HTTPException(status_code=404, detail=f"No selectors found for domain: {domain}")

        selectors = cached

    # Run optimization
    report = optimizer.optimize_selectors(domain, selectors)

    return {
        "domain": domain,
        "timestamp": report["timestamp"],
        "original_count": report["original_count"],
        "avg_quality": round(report["summary"]["total_quality"], 3),
        "recommendations": {
            "keep": report["summary"]["keep"],
            "improve": report["summary"]["improve"],
            "replace": report["summary"]["replace"],
        },
        "optimizations": report["optimizations"],
    }


@router.get("/ml / optimize / domain/{domain}/history")
async def get_optimization_history(domain: str, limit: int = Query(10, ge=1, le=100)):
    """Get historical optimization reports for a domain.

    Shows how selector quality has evolved over time.
    """
    from app.selector_ml_optimizer import get_selector_optimizer

    optimizer = get_selector_optimizer()
    history = optimizer.get_optimization_history(domain, limit)

    return {
        "domain": domain,
        "count": len(history),
        "history": history,
    }


@router.post("/ml / learn")
async def record_selector_learning(
    domain: str,
    selector: str,
    quality: float = Query(0.0, ge=0, le=1),
    _role: UserRole = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
):
    """Record actual selector performance for ML model improvement.

    This feedback helps the ML model learn which selectors work best.

    Parameters:
        - domain: Domain name
        - selector: CSS selector that was used
        - quality: Actual quality score achieved [0, 1]
    """
    from app.selector_ml_optimizer import get_selector_optimizer

    optimizer = get_selector_optimizer()
    optimizer.learn_from_results(domain, selector, quality)

    return {
        "status": "learned",
        "domain": domain,
        "quality": quality,
    }


# ─── Strategy Evolution Endpoints ────────────────────────────────────────


@router.get("/strategy / recommend/{domain}")
async def recommend_fetch_strategy(domain: str):
    """Get recommended fetch strategy for a domain.

    Returns the best strategy based on historical performance.
    """
    from app.strategy_evolution import get_strategy_evolution_engine

    engine = get_strategy_evolution_engine()
    recommendation = engine.recommend_strategy(domain)

    return {
        "domain": domain,
        "recommended_strategy": recommendation.recommended_strategy.value,
        "alternatives": [s.value for s in recommendation.alternatives],
        "reason": recommendation.reason,
        "confidence": round(recommendation.confidence, 3),
        "estimated_success_rate": round(recommendation.estimated_success_rate, 3),
    }


@router.post("/strategy / record")
async def record_strategy_attempt(
    domain: str,
    strategy: str,
    success: bool,
    time_ms: float = Query(0, ge=0),
    quality: float = Query(0.5, ge=0, le=1),
    failure_reason: Optional[str] = None,
    _role: UserRole = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
):
    """Record a strategy attempt for learning.

    Parameters:
        - domain: Domain being fetched
        - strategy: Fetch strategy used (e.g., "playwright_full", "httpx_basic")
        - success: Whether attempt succeeded
        - time_ms: Time taken in milliseconds
        - quality: Quality of extracted data [0, 1]
        - failure_reason: Optional failure category
    """
    from app.strategy_evolution import get_strategy_evolution_engine, FetchStrategy

    engine = get_strategy_evolution_engine()

    try:
        strategy_enum = FetchStrategy(strategy)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown strategy: {strategy}")

    engine.record_fetch_attempt(domain, strategy_enum, success, time_ms, quality, failure_reason)

    return {
        "status": "recorded",
        "domain": domain,
        "strategy": strategy,
        "success": success,
    }


@router.get("/strategy / domain/{domain}")
async def get_domain_strategy_analysis(domain: str):
    """Get detailed strategy analysis for a domain.

    Shows performance of all strategies and evolution history.
    """
    from app.strategy_evolution import get_strategy_evolution_engine

    engine = get_strategy_evolution_engine()
    report = engine.get_domain_strategy_report(domain)

    return report


@router.get("/strategy / report")
async def get_all_strategies_report():
    """Get strategy performance report for all domains.

    High-level overview of which strategies work best across the system.
    """
    from app.strategy_evolution import get_strategy_evolution_engine

    engine = get_strategy_evolution_engine()
    report = engine.get_all_domains_strategy_report()

    return report


@router.post("/strategy / evolve/{domain}")
async def evolve_domain_strategy(
    domain: str, _role: UserRole = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR]))
):
    """Manually trigger strategy evolution for a domain.

    Useful when current strategy is degraded.
    Returns the new strategy recommended.
    """
    from app.strategy_evolution import get_strategy_evolution_engine

    engine = get_strategy_evolution_engine()
    new_strategy = engine.evolve_strategy(domain)

    state = engine.domain_states.get(domain)
    if state:
        current_perf = state.strategies[new_strategy]
        return {
            "domain": domain,
            "new_strategy": new_strategy.value,
            "success_rate": round(current_perf.success_rate, 3),
            "switches": state.strategy_switch_count,
        }

    return {
        "domain": domain,
        "new_strategy": new_strategy.value,
        "status": "evolved",
    }

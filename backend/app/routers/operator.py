"""
Operator Router — operational intelligence dashboard, mode switching, and degradation predictions.

Provides:
  - System governance dashboard (health summary, domain stats, resource usage)
  - Operator mode switching (production / benchmark / forensic / stealth / low_cost)
  - Degradation predictions (what's about to fail)
  - System health overview endpoint
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from app.scrape_telemetry import get_scrape_telemetry

from app.visualization import (
    OperatorMode,
    get_governance_dashboard,
)
from app.degradation_predictor import get_degradation_predictor
from app.domain_health_alerts import get_domain_health_monitor
from app.browser_pool import get_browser_pool
from app.trend_analyzer import TrendAnalyzer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/operator", tags=["operator"])


class ModeBody(BaseModel):
    """Request body for switching operator modes."""
    mode: str


# ═══════════════════════════════════════════════════════════════════════
# Operator Mode Endpoints
# ═══════════════════════════════════════════════════════════════════════


@router.get("/mode")
async def get_current_mode():
    """Get the current operator mode and its configuration.

    Returns the active operator profile and the corresponding
    runtime settings that are currently applied.
    """
    dashboard = get_governance_dashboard()
    governance_summary = dashboard.get_governance_summary()
    return {
        "active_mode": dashboard.active_mode.value,
        "available_modes": [m.value for m in OperatorMode],
        "settings": governance_summary,
    }


@router.post("/mode")
async def set_operator_mode(request: Request, body: ModeBody):
    """Switch the system to a different operator mode.

    Dynamically adjusts runtime settings (timeout, settle delay,
    stealth mode, etc.) for the selected operational profile.

    Requires admin-level privileges — this operation is powerful and can
    switch the runtime into stealth/forensic/benchmark modes that bypass
    normal timing and anti-bot limits.

    Modes:
      - production: High-yield throughput, stable data capture
      - benchmark: Hostile validation, full telemetry
      - forensic: Deep diagnostics, verbose logging
      - stealth: Maximum anti-bot camouflage
      - low_cost: Resource conservation mode

    Args:
        body.mode: One of 'production', 'benchmark', 'forensic', 'stealth', 'low_cost'.
    """
    from app.config import settings
    import secrets
    if settings.ADMIN_API_KEY:
        provided = request.headers.get("X-Admin-Key", "")
        if not secrets.compare_digest(provided, settings.ADMIN_API_KEY):
            raise HTTPException(
                status_code=403,
                detail="Admin API key required (X-Admin-Key header). This endpoint is powerful and can "
                       "switch the runtime into stealth/forensic/benchmark modes.",
            )

    mode = body.mode
    try:
        target_mode = OperatorMode(mode.lower())
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid mode: '{mode}'. Valid modes: {[m.value for m in OperatorMode]}",
        )

    dashboard = get_governance_dashboard()
    adjustments = dashboard.set_operator_mode(target_mode)
    logger.info(
        "[Operator] Mode switched to '%s': %s",
        target_mode.value,
        adjustments,
    )

    return {
        "active_mode": target_mode.value,
        "adjustments": adjustments,
        "message": f"Switched to {target_mode.value} mode",
    }


# ═══════════════════════════════════════════════════════════════════════
# System Governance Dashboard
# ═══════════════════════════════════════════════════════════════════════


@router.get("/dashboard")
async def get_system_dashboard():
    """Get the complete system governance dashboard.

    Returns a consolidated view of:
    - Operator mode and resource usage
    - Domain health summary (from domain_health_alerts)
    - Browser pool metrics
    - Telemetry stats (recent scrape success/failure counts)
    - Resource governor report (memory, queue, token spend)
    """
    dashboard = get_governance_dashboard()
    governance = dashboard.get_governance_summary()

    # Domain health summary
    monitor = get_domain_health_monitor()
    domains_health = monitor.get_all_domains_health()

    # Browser pool metrics
    browser_metrics = get_browser_pool().get_metrics()

    # Telemetry stats
    telemetry = get_scrape_telemetry()
    recent = telemetry.get_recent(100)
    recent_successes = sum(1 for t in recent if not t.get("fallback_triggered", False))
    recent_failures = len(recent) - recent_successes if recent else 0

    return {
        "active_mode": dashboard.active_mode.value,
        "resources": governance.get("resources", {}),
        "domains": {
            "total_monitored": len(domains_health),
            "healthy": sum(1 for d in domains_health if d.get("health_level") == "healthy"),
            "degrading": sum(1 for d in domains_health if d.get("health_level") == "degrading"),
            "unhealthy": sum(1 for d in domains_health if d.get("health_level") == "unhealthy"),
            "critical": sum(1 for d in domains_health if d.get("health_level") in ("critical", "blacklisted")),
        },
        "browser": {
            "active_contexts": browser_metrics.get("active_contexts", 0),
            "total_contexts": browser_metrics.get("total_contexts", 0),
        },
        "telemetry": {
            "recent_scrapes": len(recent),
            "recent_successes": recent_successes,
            "recent_failures": recent_failures,
            "success_rate": round(recent_successes / max(len(recent), 1), 3),
        },
        "governor": {
            "token_spend_dollars": governance.get("resources", {}).get("token_spend_dollars", 0),
            "browser_prunes": governance.get("resources", {}).get("metrics", {}).get("browser_prunes", 0),
            "queue_sheds": governance.get("resources", {}).get("metrics", {}).get("queue_sheds", 0),
        },
    }


# ═══════════════════════════════════════════════════════════════════════
# Degradation Prediction Endpoints
# ═══════════════════════════════════════════════════════════════════════


@router.get("/predictions")
async def get_degradation_predictions(
    window: int = Query(100, ge=10, le=500),
    min_confidence: float = Query(0.0, ge=0.0, le=1.0),
):
    """Get degradation predictions for all domains.

    Analyzes recent telemetry and domain trends to predict what's
    about to fail. Returns predictions sorted by severity.

    Args:
        window: Number of recent telemetry events to analyze (10-500).
        min_confidence: Minimum confidence threshold (0.0 to 1.0).

    Returns:
        A prediction report with per-domain predictions and system risk.
    """
    telemetry_history = get_scrape_telemetry().get_recent(window)

    if not telemetry_history:
        return {
            "generated_at": None,
            "domains_analyzed": 0,
            "predictions": [],
            "summary": {
                "critical": 0,
                "high": 0,
                "medium": 0,
                "low": 0,
                "cascade_risks": 0,
            },
            "systemic_risk_level": "low",
            "top_risks": [],
            "message": "No telemetry data available for predictions",
        }

    # Get domain trends first
    analyzer = TrendAnalyzer(history_window=window)
    report = analyzer.analyze(telemetry_history)

    # Run degradation predictor
    predictor = get_degradation_predictor()
    prediction_report = predictor.predict(telemetry_history, report.domain_trends)

    result = prediction_report.to_dict()

    # Filter by minimum confidence if requested
    if min_confidence > 0:
        result["predictions"] = [
            p for p in result["predictions"]
            if p.get("confidence", 0) >= min_confidence
        ]
        result["top_risks"] = [
            r for r in result["top_risks"]
            if r.get("confidence", 0) >= min_confidence
        ]
        result["summary"]["total_filtered"] = len(result["predictions"])

    return result


@router.get("/predictions/{domain}")
async def get_domain_prediction(
    domain: str,
    window: int = Query(100, ge=10, le=500),
):
    """Get degradation predictions for a specific domain.

    Args:
        domain: Domain name to predict for (e.g., 'justdial.com').
        window: Number of recent telemetry events to analyze (10-500).

    Returns:
        Predictions for the specified domain.
    """
    telemetry_history = get_scrape_telemetry().get_recent(window)

    # Filter to only this domain's events
    domain_events = [
        e for e in telemetry_history
        if TrendAnalyzer.extract_domain(e.get("url", "")) == domain.lower()
    ]

    if not domain_events:
        raise HTTPException(
            status_code=404,
            detail=f"No telemetry data found for domain: {domain}",
        )

    # Analyze domain trend
    analyzer = TrendAnalyzer(history_window=window)
    trend = analyzer.analyze_domain(domain, domain_events)

    # Predict for this domain
    predictor = get_degradation_predictor()
    report = predictor.predict(domain_events, {domain: trend})

    domain_predictions = [p.to_dict() for p in report.predictions]

    return {
        "domain": domain,
        "health_score": trend.health_score,
        "failure_rate": round(trend.failure_rate, 3),
        "sample_count": trend.sample_count,
        "quality_trend": trend.quality_trend,
        "predictions": domain_predictions,
        "systemic_risk_level": report.systemic_risk_level,
    }


# ═══════════════════════════════════════════════════════════════════════
# System Health Overview (lightweight, fast)
# ═══════════════════════════════════════════════════════════════════════


@router.get("/health")
async def get_operator_health_summary():
    """Get a lightweight system health overview for the dashboard.

    Returns essential health indicators at a glance.
    Optimized for frequent polling by the frontend dashboard.
    """
    # Telemetry quick stats
    telemetry = get_scrape_telemetry()
    recent = telemetry.get_recent(20)
    successes = sum(1 for t in recent if not t.get("fallback_triggered", False))
    total = len(recent)

    success_rate = successes / max(total, 1) if total > 0 else 0.0
    if success_rate >= 0.6:
        status = "healthy"
    elif success_rate > 0:
        status = "degraded"
    else:
        status = "critical"

    # Browser pool
    browser = get_browser_pool().get_metrics()

    # Domain health quick stats
    try:
        monitor = get_domain_health_monitor()
        domains = monitor.get_all_domains_health()
        degraded = sum(1 for d in domains if d.get("health_level") in ("degrading", "unhealthy", "critical"))
    except Exception:
        domains = []
        degraded = 0

    return {
        "status": status,
        "mode": get_governance_dashboard().active_mode.value,
        "success_rate": round(successes / max(total, 1), 3),
        "active_browsers": browser.get("active_contexts", 0),
        "domains_degraded": degraded,
        "domains_monitored": len(domains),
        "recent_scrapes": total,
    }

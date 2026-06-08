"""Experimental / Research Router — semantic, topology, replay, adaptive,
scraper research, and operator research endpoints.

EXPERIMENTAL / RESEARCH ONLY — These endpoints expose experimental semantic,
topology, replay, and adaptive modules, plus research-backed scraper and
operator capabilities. They are NOT production-validated capabilities.
Enable/use at your own risk. Behavior may change or be removed.

All imports from experimental modules are lazy (inside function bodies) so
they do not cause startup failures if those modules are unavailable.
"""

from __future__ import annotations

import logging
import re
import secrets
import time
from typing import Annotated, ClassVar

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.scrape_telemetry import get_scrape_telemetry
from app.utils.rbac import UserRole, require_role

logger = logging.getLogger(__name__)


def verify_experimental_enabled() -> None:
    if not settings.ENABLE_EXPERIMENTAL_ROUTES:
        # Use 403 (not 404) so callers can distinguish "feature is
        # disabled by configuration" from "path does not exist". A 404
        # would make monitoring and operator probes think the
        # deployment is broken rather than that a feature flag is off.
        raise HTTPException(
            status_code=403,
            detail=(
                "Experimental / research routes are disabled in this environment. "
                "Set DATAFORGE_ENABLE_EXPERIMENTAL_ROUTES=true to enable them."
            ),
        )


router = APIRouter(dependencies=[Depends(verify_experimental_enabled)])


# ─── Request Models ────────────────────────────────────────────────────────


class KnowledgeMergeRequest(BaseModel):
    """Validated request body for merge / knowledge endpoint."""

    model_config = ConfigDict(extra="forbid")

    # Cap the number of roles / exclusions that can be merged in a single
    # request; otherwise a malicious caller could OOM the persistent
    # world-state manifold.
    MAX_ROLES: ClassVar[int] = 500
    MAX_EXCLUSIONS: ClassVar[int] = 500

    role_manifold: dict[str, list[float]] = Field(
        default_factory=dict,
        description="Role vectors to merge into the field manifold",
    )
    learned_exclusions: dict[str, float] = Field(
        default_factory=dict,
        description="Learned exclusions to merge (key format: 'role1|role2')",
    )

    @classmethod
    def validate_payload(cls, data: dict) -> KnowledgeMergeRequest:
        """Validate and cap payload size.

        Operates on a shallow copy so the caller's dict is never mutated
        (a failed ``cls(**data)`` after a partial clamp previously left
        the request dict in an inconsistent state).
        """
        # Fast-path: pydantic does the type validation; we just enforce
        # the size caps.
        payload = dict(data) if isinstance(data, dict) else data  # pragma: no cover -- FastAPI guarantees a dict
        if isinstance(payload.get("role_manifold"), dict) and len(payload["role_manifold"]) > cls.MAX_ROLES:
            payload["role_manifold"] = dict(list(payload["role_manifold"].items())[: cls.MAX_ROLES])
        if isinstance(payload.get("learned_exclusions"), dict) and len(payload["learned_exclusions"]) > cls.MAX_EXCLUSIONS:
            payload["learned_exclusions"] = dict(list(payload["learned_exclusions"].items())[: cls.MAX_EXCLUSIONS])
        return cls(**payload)


class ModeBody(BaseModel):
    """Request body for switching operator modes."""

    mode: str


def _require_admin_key(request: Request) -> None:
    """Check admin API key for powerful system routes.

    When ``settings.ADMIN_API_KEY`` is empty we emit a loud warning and
    fall back to the regular API key check. The end-to-end fail-closed
    guard (refusing to start at all without an admin key) lives in
    ``scripts/verify_production_deployment.py`` and in the startup
    sequence — see ``app.lifespan``. Do not silence the warning: an
    unset ``ADMIN_API_KEY`` in production is a misconfiguration that
    must be flagged, not hidden.
    """
    if not settings.ADMIN_API_KEY:
        logger.warning(
            "ADMIN_API_KEY is unset; admin-key-guarded endpoints are "
            "falling back to the regular API key check. This is a "
            "configuration error in production.",
        )
        return
    provided = request.headers.get("X-Admin-Key", "")
    if not secrets.compare_digest(provided, settings.ADMIN_API_KEY):
        raise HTTPException(
            status_code=403,
            detail="Admin API key required. Provide X-Admin-Key header.",
        )


# ═══════════════════════════════════════════════════════════════════════
# Semantic World State & Topology Endpoints (EXPERIMENTAL / RESEARCH ONLY)
# ═══════════════════════════════════════════════════════════════════════


@router.get("/api/system/topology")
async def system_topology(
    _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN]))],
):
    """Exposes the raw state of the experimental semantic world model."""
    from app.semantic_world_state import get_world_state

    ws = get_world_state()
    view = ws.get_topology_view()
    return {
        "metrics": {
            "field_pressure": round(ws.metrics.field_pressure, 3),
            "global_energy": round(ws.metrics.global_energy, 3),
            "energy_balance": round(ws.metrics.energy_balance, 4),
            "semantic_temperature": round(ws.metrics.semantic_temperature, 3),
            "global_entropy": round(ws.metrics.global_entropy, 3),
            "exclusion_count": len(ws.learned_exclusions),
            "learning_count": ws.learning_count,
            "region_count": view.region_count(),
            "integrity_score": round(ws.metrics.integrity_score, 3),
            "crystalline_count": len(ws.crystalline_records),
        },
        "global_communities": [list(c) for c in ws.global_communities],
        "schema_patterns": [{"roles": list(k), "count": v} for k, v in ws.schema_patterns.items()],
        "learned_exclusions": [{"roles": list(k), "strength": round(v, 3)} for k, v in ws.learned_exclusions.items()],
        "field_regions": view.all_region_dicts(),
        "topology_edges": view.get_topology_edges(),
        "edge_fields": [edge.__dict__ for edge in view.get_edge_fields()],
        "role_compatibility": [{"role": k[0], "type": k[1], "score": round(v, 3)} for k, v in ws.role_compatibility.items()],
        "drift_logs": {role: ws._observability.get_role_drift(role) for role in ws.get_manifold_roles()},
        "meso_clusters": ws.meso_clusters,
        "macro_continents": ws.macro_continents,
    }


@router.get("/api/system/crystalline")
async def system_crystalline(
    _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN]))],
):
    """Returns the synthesized high-integrity knowledge units."""
    from app.semantic_world_state import get_world_state

    ws = get_world_state()
    return {
        "records": ws.crystalline_records,
        "count": len(ws.crystalline_records),
    }


@router.get("/api/system/export/knowledge")
async def export_knowledge(
    _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN]))],
):
    """Export the synthesized knowledge manifold as a portable schema."""
    from app.semantic_world_state import get_world_state

    ws = get_world_state()
    return {
        "version": "3.1-crystalline",
        "timestamp": time.time(),
        "manifold_size": len(ws.role_manifold),
        "role_manifold": ws.role_manifold,
        "crystalline_records": ws.crystalline_records,
        "communities": [list(c) for c in ws.global_communities],
        "schema_patterns": [{"roles": list(k), "count": v} for k, v in ws.schema_patterns.items()],
        "learned_exclusions": {"|".join(k): v for k, v in ws.learned_exclusions.items()},
    }


@router.post("/api/system/merge/knowledge")
async def merge_knowledge(
    request: Request,
    req: KnowledgeMergeRequest,
    _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN]))],  # noqa: B008, RUF100
):
    """Merge an external knowledge manifold into the current field.

    Validated with size caps: max 500 roles, max 500 exclusions.
    Requires admin API key if DATAFORGE_ADMIN_API_KEY is configured.

    The body is declared as ``KnowledgeMergeRequest`` so Pydantic
    validates the shape of ``role_manifold`` (``dict[str, list[float]]``)
    and ``learned_exclusions`` (``dict[str, float]``) before any code
    runs, preventing type-coercion bugs (``list("foo")`` ->
    ``['f','o','o']``) from corrupting the persistent world state.
    """
    _require_admin_key(request)

    from app.semantic_world_state import get_world_state

    ws = get_world_state()

    # 1. Merge Manifold (Geometric Beliefs)
    remote_manifold = req.role_manifold
    merged_roles = 0
    for role, vec in remote_manifold.items():
        # ``vec`` is already validated as ``list[float]`` by the
        # Pydantic model — defensive cast to list is harmless if a
        # future refactor weakens the model.
        if ws.has_manifold_role(role):
            ws.blend_manifold_vector(role, list(vec), alpha=0.7, beta=0.3)
        else:
            ws.set_manifold_vector(role, list(vec))
        merged_roles += 1

    # 2. Merge Exclusions (Topological Constraints)
    remote_exc = req.learned_exclusions
    for k_str, val in remote_exc.items():
        parts = k_str.split("|")
        if len(parts) == 2:
            key = tuple(sorted(parts))
            from app.instability_api import InstabilityAPI

            inst_api = InstabilityAPI(ws=ws)
            current = inst_api.get_learned_exclusion(key[0], key[1])
            inst_api.set_exclusion(key[0], key[1], max(current, val))

    return {"status": "merged", "roles_merged": merged_roles, "total_manifold": len(ws.role_manifold)}


@router.get("/api/system/search")
async def system_search(
    _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN]))],
    query: str,
    limit: int = 5,
):
    """Perform topological search on crystalline records."""
    from app.semantic_world_state import get_world_state

    ws = get_world_state()
    results = ws.topological_search(query)[:limit]
    return {"results": results, "query": query}


@router.get("/api/system/observability")
async def system_observability(
    _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN]))],
):
    """Exposes real-time telemetry and activity heatmaps."""
    from app.semantic_world_state import get_world_state

    ws = get_world_state()
    return {
        "telemetry": ws.observability_telemetry[-50:],
        "heatmap": ws.observability_heatmap,
        "causal_trace": ws.get_causal_telemetry()[-20:],
        "health_index": ws._observability.get_semantic_health_index(ws.capture_governance_snapshot()),
        "hierarchy": {
            "envelopes": list(ws.abstraction_envelopes.keys()),
            "levels": {r: ws.get_role_level(r) for r in ws.role_manifold},
        },
    }


# ═══════════════════════════════════════════════════════════════════════
# Domain Policy & Acquisition Telemetry (EXPERIMENTAL / RESEARCH ONLY)
# ═══════════════════════════════════════════════════════════════════════


@router.get("/api/system/domain-policy")
async def system_domain_policy(
    _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN]))],
):
    """Return the current domain runtime policy summaries."""
    from app.domain_runtime_policy import get_domain_runtime_policy

    policy = get_domain_runtime_policy()
    summary = policy.get_summary()
    # Add recommended_action for each domain
    result = {}
    for domain_key, entry_data in summary.items():
        # Build a representative URL for the recommended_action query
        sample_url = f"https://{domain_key}/"
        result[domain_key] = {
            **entry_data,
            "recommended_action": policy.recommended_action(sample_url),
        }
    return result


@router.get("/api/system/acquisition/telemetry")
async def acquisition_telemetry(
    _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN]))],
):
    """Exposes acquisition telemetry: state distribution, recovery rates, recent events."""
    from app.acquisition_telemetry import get_acquisition_telemetry

    return get_acquisition_telemetry().get_summary()


# ═══════════════════════════════════════════════════════════════════════
# Topology History & Event Journal (EXPERIMENTAL / RESEARCH ONLY)
# ═══════════════════════════════════════════════════════════════════════


@router.get("/api/system/history/topology")
async def system_topology_history(
    _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN]))],
    limit: int = 20,
):
    """Returns a timeline of historical topology states for replay."""
    from app.event_journal import get_journal

    journal = get_journal()

    history = []
    structural_entries = [e for e in journal._entries if e["type"] in ["restructure_topology", "merge_state", "add", "remove"]]
    target_entries = structural_entries[-limit:]

    for entry in target_entries:
        idx = entry["idx"]
        snapshot = journal.get_snapshot_at(idx)
        if snapshot and "topology" in snapshot:
            history.append(
                {
                    "idx": idx,
                    "timestamp": entry["timestamp"],
                    "type": entry["type"],
                    "topology": snapshot["topology"],
                },
            )

    return {"history": history}


# ═══════════════════════════════════════════════════════════════════════
# Cognitive Processing & Agency (EXPERIMENTAL / RESEARCH ONLY)
# ═══════════════════════════════════════════════════════════════════════


@router.post("/api/system/scheduler/step")
async def process_cognitive_tasks(_role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN]))], budget_ms: float = 100.0):  # noqa: B008, RUF100
    """Manually trigger processing of the cognitive task queue."""
    from app.semantic_world_state import get_world_state

    ws = get_world_state()
    completed = ws.process_cognitive_queue(budget_ms=budget_ms)
    return {"status": "success", "tasks_completed": completed}


@router.get("/api/system/agency")
async def system_agency(
    _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN]))],
):
    """Returns the state of automated agency and tools."""
    from app.llm_bridge import get_plugin_manager
    from app.semantic_world_state import get_world_state

    ws = get_world_state()
    plugins = get_plugin_manager(ws=ws)
    return {
        "active_actions": ws.active_actions,
        "available_tools": plugins.get_available_tools(),
        "action_history": ws.action_history[-30:],
        "active_intents": ws.active_intents,
    }


# ═══════════════════════════════════════════════════════════════════════
# Replay Buffer Endpoints (EXPERIMENTAL / RESEARCH ONLY)
# ═══════════════════════════════════════════════════════════════════════


@router.get("/api/system/replay/status")
async def system_replay_status(
    _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN]))],
):
    """Returns the status of the large-scale persistent replay buffer."""
    from app.replay_buffer import get_replay_buffer

    rb = get_replay_buffer()
    segment_info = await run_in_threadpool(rb.get_segment_info)
    return {
        "buffer": rb.status(),
        "segments": segment_info,
        "checkpoints": len(rb._checkpoints.entries) if hasattr(rb, "_checkpoints") else 0,
    }


@router.get("/api/system/replay/chain")
async def system_replay_chains(
    _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN]))],
    limit: int = 20,
):
    """Returns causal chains reconstructed from the persistent replay buffer."""
    from app.replay_buffer import get_replay_buffer

    rb = get_replay_buffer()
    chains = await run_in_threadpool(rb.get_causal_chains, limit=limit)
    return {
        "chains": chains,
        "count": len(chains),
        "total_buffer_entries": rb.status().get("total_entries", 0),
    }


@router.get("/api/system/replay/events")
async def system_replay_events(
    _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN]))],
    start_idx: int = 0,
    end_idx: int = -1,
):
    """Returns a range of events from the persistent replay buffer."""
    from app.replay_buffer import get_replay_buffer

    rb = get_replay_buffer()
    status = rb.status()
    if end_idx == -1:
        end_idx = status.get("total_entries", 0) - 1
    events = await run_in_threadpool(rb.get_event_range, start_idx, end_idx)
    return {
        "events": events,
        "count": len(events),
        "range": {"start": start_idx, "end": end_idx},
        "total_entries": status.get("total_entries", 0),
    }


# ═══════════════════════════════════════════════════════════════════════
# Manifold Compression (EXPERIMENTAL / RESEARCH ONLY)
# ═══════════════════════════════════════════════════════════════════════


@router.post("/api/system/refactor/compress")
async def trigger_manifold_compression(_role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN]))]):  # noqa: B008, RUF100
    """Trigger a manifold compression cycle."""
    from app.llm_bridge import get_plugin_manager
    from app.semantic_world_state import get_world_state

    plugins = get_plugin_manager(ws=get_world_state())
    result = plugins.call_tool("manifold_compressor")
    return {"result": result}


# ═══════════════════════════════════════════════════════════════════════
# Scraper Research Routes (quarantined from routers/scraper.py)
# ═══════════════════════════════════════════════════════════════════════

# ─── Trend Analysis & Telemetry Intelligence ─────────────────────────


@router.get("/api/scraper/trends")
async def get_extraction_trends(
    _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN]))],
    window: Annotated[int, Query(ge=10, le=500)] = 100,
):
    """Analyze scrape telemetry for degradation patterns, domain health trends,
    and actionable alerts.

    EXPERIMENTAL / RESEARCH ONLY — backed by ``app.trend_analyzer``.
    """
    try:
        from app.trend_analyzer import TrendAnalyzer  # research-shell, lazy

        telemetry_history = get_scrape_telemetry().get_recent(window)
        analyzer = TrendAnalyzer(history_window=window)
        report = await run_in_threadpool(analyzer.analyze, telemetry_history)
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
    except Exception as e:
        logger.exception("Failed to get extraction trends")
        raise HTTPException(status_code=500, detail="Failed to analyze extraction trends") from e


@router.get("/api/scraper/trends/{domain}")
async def get_domain_trend(
    domain: str,
    window: Annotated[int, Query(ge=10, le=500)] = 100,
):
    """Get detailed trend analysis for a specific domain.

    EXPERIMENTAL / RESEARCH ONLY — backed by ``app.trend_analyzer``.
    """
    try:
        telemetry_history = get_scrape_telemetry().get_recent(window)

        from app.trend_analyzer import TrendAnalyzer as TA

        domain_events = [e for e in telemetry_history if TA.extract_domain(e.get("url", "")) == domain.lower()]

        if not domain_events:
            raise HTTPException(
                status_code=404,
                detail=f"No telemetry data found for domain: {domain}",
            )

        from app.trend_analyzer import TrendAnalyzer  # research-shell, lazy

        analyzer = TrendAnalyzer(history_window=window)
        trend = await run_in_threadpool(analyzer.analyze_domain, domain, domain_events)

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
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to get trend for domain %s", domain)
        raise HTTPException(status_code=500, detail="Failed to get domain trend") from e


# ─── Economic Tracking & Cost Analysis ────────────────────────────────


@router.get("/api/scraper/economics")
async def get_extraction_economics(
    _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN]))],
    window: Annotated[int, Query(ge=10, le=1000)] = 200,
):
    """Return extraction cost and efficiency analysis.

    EXPERIMENTAL / RESEARCH ONLY — backed by ``app.trend_analyzer.EconomicTracker``.
    """
    from app.trend_analyzer import EconomicTracker  # research-shell, lazy

    telemetry_history = get_scrape_telemetry().get_recent(window)
    tracker = EconomicTracker()
    report = await run_in_threadpool(tracker.analyze, telemetry_history)

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


# ─── Domain Health Monitoring (quarantined from routers/scraper.py) ────


@router.get("/api/scraper/health/domains")
async def get_all_domains_health(
    _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN]))],
):
    """Get health status for all monitored domains.

    EXPERIMENTAL / RESEARCH ONLY — backed by ``app.domain_health_alerts``.
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


@router.get("/api/scraper/health/domain/{domain}")
async def get_domain_health(
    _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN]))],
    domain: str,
):
    """Get detailed health status for a specific domain.

    EXPERIMENTAL / RESEARCH ONLY — backed by ``app.domain_health_alerts``.
    """
    if not re.fullmatch(r"[a-z0-9.\-]{1,253}", domain):
        raise HTTPException(
            status_code=400,
            detail=("Invalid domain. Allowed characters: lowercase letters, digits, dot, hyphen. Max length: 253."),
        )
    from app.domain_health_alerts import get_domain_health_monitor

    monitor = get_domain_health_monitor()

    url = f"https://{domain}/"
    health = monitor.get_domain_health(url)

    if health is None:
        raise HTTPException(status_code=404, detail=f"No health data for domain: {domain}")

    return health


@router.get("/api/scraper/health/summary")
async def get_system_health_summary(
    _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN]))],
):
    """Get system-wide health summary.

    EXPERIMENTAL / RESEARCH ONLY — backed by ``app.domain_health_alerts``.
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

    overall_score = sum(d["health_score"] for d in domains_health) / len(domains_health)

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


# ═══════════════════════════════════════════════════════════════════════
# Operator Research Routes (quarantined from routers/operator.py)
# ═══════════════════════════════════════════════════════════════════════

# ─── Operator Mode Endpoints ──────────────────────────────────────────


@router.get("/api/operator/mode")
async def get_current_mode(
    _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN]))],
):
    """Get the current operator mode and its configuration.

    EXPERIMENTAL / RESEARCH ONLY — backed by ``app.visualization``.
    """
    try:
        from app.visualization import OperatorMode, get_governance_dashboard

        dashboard = get_governance_dashboard()
        governance_summary = await run_in_threadpool(dashboard.get_governance_summary)
        return {
            "active_mode": dashboard.active_mode.value,
            "available_modes": [m.value for m in OperatorMode],
            "settings": governance_summary,
        }
    except Exception as e:
        logger.exception("Failed to get operator mode")
        raise HTTPException(status_code=500, detail="Failed to get operator mode") from e


@router.post("/api/operator/mode")
async def set_operator_mode(
    body: ModeBody,
    _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN]))],
):
    """Switch the system to a different operator mode.

    EXPERIMENTAL / RESEARCH ONLY — backed by ``app.visualization``.
    """
    try:
        from app.visualization import OperatorMode, get_governance_dashboard

        mode = body.mode
        try:
            target_mode = OperatorMode(mode.lower())
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid mode: '{mode}'. Valid modes: {[m.value for m in OperatorMode]}",
            ) from None

        dashboard = get_governance_dashboard()
        adjustments = await run_in_threadpool(dashboard.set_operator_mode, target_mode)
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
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to set operator mode")
        raise HTTPException(status_code=500, detail="Failed to switch operator mode") from e


# ─── System Governance Dashboard ──────────────────────────────────────


@router.get("/api/operator/dashboard")
async def get_system_dashboard(
    _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN]))],
):
    """Get the complete system governance dashboard.

    EXPERIMENTAL / RESEARCH ONLY — backed by ``app.visualization`` and
    ``app.domain_health_alerts``.
    """
    try:
        from app.browser_pool import get_browser_pool
        from app.domain_health_alerts import get_domain_health_monitor
        from app.visualization import get_governance_dashboard

        dashboard = get_governance_dashboard()
        governance = await run_in_threadpool(dashboard.get_governance_summary)

        monitor = get_domain_health_monitor()
        domains_health = await run_in_threadpool(monitor.get_all_domains_health)

        browser_metrics = get_browser_pool().get_metrics()

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
    except Exception as e:
        logger.exception("Failed to get operator system dashboard")
        raise HTTPException(status_code=500, detail="Failed to load dashboard") from e


# ─── Degradation Prediction Endpoints ─────────────────────────────────


@router.get("/api/operator/predictions")
async def get_degradation_predictions(
    window: Annotated[int, Query(ge=10, le=500)] = 100,
    min_confidence: Annotated[float, Query(ge=0.0, le=1.0)] = 0.0,
):
    """Get degradation predictions for all domains.

    EXPERIMENTAL / RESEARCH ONLY — backed by ``app.trend_analyzer`` and
    ``app.degradation_predictor``.
    """
    try:
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

        from app.trend_analyzer import TrendAnalyzer

        analyzer = TrendAnalyzer(history_window=window)
        report = await run_in_threadpool(analyzer.analyze, telemetry_history)

        from app.degradation_predictor import get_degradation_predictor

        predictor = get_degradation_predictor()
        prediction_report = await run_in_threadpool(predictor.predict, telemetry_history, report.domain_trends)

        result = prediction_report.to_dict()

        if min_confidence > 0:
            result["predictions"] = [p for p in result["predictions"] if p.get("confidence", 0) >= min_confidence]
            result["top_risks"] = [r for r in result["top_risks"] if r.get("confidence", 0) >= min_confidence]
            result["summary"]["total_filtered"] = len(result["predictions"])

        return result
    except Exception as e:
        logger.exception("Failed to get degradation predictions")
        raise HTTPException(status_code=500, detail="Failed to get degradation predictions") from e


@router.get("/api/operator/predictions/{domain}")
async def get_domain_prediction(
    domain: str,
    window: Annotated[int, Query(ge=10, le=500)] = 100,
):
    """Get degradation predictions for a specific domain.

    EXPERIMENTAL / RESEARCH ONLY — backed by ``app.trend_analyzer`` and
    ``app.degradation_predictor``.
    """
    try:
        telemetry_history = get_scrape_telemetry().get_recent(window)

        from app.trend_analyzer import TrendAnalyzer

        domain_events = [e for e in telemetry_history if TrendAnalyzer.extract_domain(e.get("url", "")) == domain.lower()]

        if not domain_events:
            raise HTTPException(
                status_code=404,
                detail=f"No telemetry data found for domain: {domain}",
            )

        analyzer = TrendAnalyzer(history_window=window)
        trend = await run_in_threadpool(analyzer.analyze_domain, domain, domain_events)

        from app.degradation_predictor import get_degradation_predictor

        predictor = get_degradation_predictor()
        report = await run_in_threadpool(predictor.predict, domain_events, {domain: trend})

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
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to get prediction for domain %s", domain)
        raise HTTPException(status_code=500, detail="Failed to predict for domain") from e


# ─── Operator Health Overview (research-backed) ───────────────────────


@router.get("/api/operator/health")
async def get_operator_health_summary(
    _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN]))],
):
    """Get a lightweight system health overview for the dashboard.

    EXPERIMENTAL / RESEARCH ONLY — backed by ``app.domain_health_alerts``
    and ``app.visualization``.
    """
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

    from app.browser_pool import get_browser_pool

    browser = get_browser_pool().get_metrics()

    # Domain health quick stats
    try:
        from app.domain_health_alerts import get_domain_health_monitor

        monitor = get_domain_health_monitor()
        domains = monitor.get_all_domains_health()
        degraded = sum(1 for d in domains if d.get("health_level") in ("degrading", "unhealthy", "critical"))
    except Exception:
        logger.debug("Failed to get domain health monitor stats", exc_info=True)
        domains = []
        degraded = 0

    from app.visualization import get_governance_dashboard

    return {
        "status": status,
        "mode": get_governance_dashboard().active_mode.value,
        "success_rate": round(successes / max(total, 1), 3),
        "active_browsers": browser.get("active_contexts", 0),
        "domains_degraded": degraded,
        "domains_monitored": len(domains),
        "recent_scrapes": total,
    }


# ═══════════════════════════════════════════════════════════════════════
# Scraper ML & Strategy Routes (quarantined from routers/scraper.py)
# ═══════════════════════════════════════════════════════════════════════

# ─── ML Selector Optimization Endpoints ───────────────────────────────


@router.post("/api/scraper/ml/optimize/domain/{domain}")
async def optimize_domain_selectors(
    domain: str,
    _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR]))],  # noqa: B008, RUF100
    selectors: dict | None = None,
):
    """Optimize selectors for a domain using ML predictions.

    EXPERIMENTAL / RESEARCH ONLY — backed by ``app.selector_ml_optimizer``.
    """
    if not re.fullmatch(r"[a-z0-9.\-]{1,253}", domain):
        raise HTTPException(
            status_code=400,
            detail=("Invalid domain. Allowed characters: lowercase letters, digits, dot, hyphen. Max length: 253."),
        )
    try:
        from app.selector_memory import get_selector_memory
        from app.selector_ml_optimizer import get_selector_optimizer

        optimizer = get_selector_optimizer()

        if selectors is None:
            selector_memory = get_selector_memory()
            url = f"https://{domain}/"
            cached = selector_memory.get_selectors(url)

            if not cached:
                raise HTTPException(status_code=404, detail=f"No selectors found for domain: {domain}")

            selectors = cached

        report = await run_in_threadpool(optimizer.optimize_selectors, domain, selectors)

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
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to optimize selectors for domain %s", domain)
        raise HTTPException(status_code=500, detail="Selector optimization failed") from e


@router.get("/api/scraper/ml/optimize/domain/{domain}/history")
async def get_optimization_history(
    _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN]))],
    domain: str,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
):
    """Get historical optimization reports for a domain.

    EXPERIMENTAL / RESEARCH ONLY — backed by ``app.selector_ml_optimizer``.
    """
    try:
        from app.selector_ml_optimizer import get_selector_optimizer

        optimizer = get_selector_optimizer()
        history = await run_in_threadpool(optimizer.get_optimization_history, domain, limit)

        return {
            "domain": domain,
            "count": len(history),
            "history": history,
        }
    except Exception as e:
        logger.exception("Failed to get optimization history for domain %s", domain)
        raise HTTPException(status_code=500, detail="Failed to get optimization history") from e


@router.post("/api/scraper/ml/learn")
async def record_selector_learning(
    domain: str,
    selector: str,
    _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR]))],  # noqa: B008, RUF100
    quality: Annotated[float, Query(ge=0, le=1)] = 0.0,
):
    """Record actual selector performance for ML model improvement.

    EXPERIMENTAL / RESEARCH ONLY — backed by ``app.selector_ml_optimizer``.
    """
    try:
        from app.selector_ml_optimizer import get_selector_optimizer

        optimizer = get_selector_optimizer()
        await run_in_threadpool(optimizer.learn_from_results, domain, selector, quality)

        return {
            "status": "learned",
            "domain": domain,
            "quality": quality,
        }
    except Exception as e:
        logger.exception("Failed selector learning for domain %s", domain)
        raise HTTPException(status_code=500, detail="Selector learning failed") from e


# ─── Strategy Evolution Endpoints ─────────────────────────────────────


@router.get("/api/scraper/strategy/recommend/{domain}")
async def recommend_fetch_strategy(
    _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN]))],
    domain: str,
):
    """Get recommended fetch strategy for a domain.

    EXPERIMENTAL / RESEARCH ONLY — backed by ``app.strategy_evolution``.
    """
    try:
        from app.strategy_evolution import get_strategy_evolution_engine

        engine = get_strategy_evolution_engine()
        recommendation = await run_in_threadpool(engine.recommend_strategy, domain)

        return {
            "domain": domain,
            "recommended_strategy": recommendation.recommended_strategy.value,
            "alternatives": [s.value for s in recommendation.alternatives],
            "reason": recommendation.reason,
            "confidence": round(recommendation.confidence, 3),
            "estimated_success_rate": round(recommendation.estimated_success_rate, 3),
        }
    except Exception as e:
        logger.exception("Failed to recommend strategy for domain %s", domain)
        raise HTTPException(status_code=500, detail="Failed to recommend strategy") from e


@router.post("/api/scraper/strategy/record")
async def record_strategy_attempt(
    domain: str,
    strategy: str,
    success: bool,
    _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR]))],  # noqa: B008, RUF100
    time_ms: Annotated[float, Query(ge=0)] = 0,
    quality: Annotated[float, Query(ge=0, le=1)] = 0.5,
    failure_reason: str | None = None,
):
    """Record a strategy attempt for learning.

    EXPERIMENTAL / RESEARCH ONLY — backed by ``app.strategy_evolution``.
    """
    try:
        from app.strategy_evolution import FetchStrategy, get_strategy_evolution_engine

        engine = get_strategy_evolution_engine()

        try:
            strategy_enum = FetchStrategy(strategy)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Unknown strategy: {strategy}") from None

        await run_in_threadpool(engine.record_fetch_attempt, domain, strategy_enum, success, time_ms, quality, failure_reason)

        return {
            "status": "recorded",
            "domain": domain,
            "strategy": strategy,
            "success": success,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to record strategy attempt for domain %s", domain)
        raise HTTPException(status_code=500, detail="Failed to record strategy attempt") from e


@router.get("/api/scraper/strategy/domain/{domain}")
async def get_domain_strategy_analysis(
    _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN]))],  # noqa: B008, RUF100
    domain: str,
):
    """Get detailed strategy analysis for a domain.

    EXPERIMENTAL / RESEARCH ONLY — backed by ``app.strategy_evolution``.
    """
    try:
        from app.strategy_evolution import get_strategy_evolution_engine

        engine = get_strategy_evolution_engine()
        return await run_in_threadpool(engine.get_domain_strategy_report, domain)
    except Exception as e:
        logger.exception("Failed to get strategy analysis for domain %s", domain)
        raise HTTPException(status_code=500, detail="Failed to get domain strategy report") from e


@router.get("/api/scraper/strategy/report")
async def get_all_strategies_report(
    _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN]))],  # noqa: B008, RUF100
):
    """Get strategy performance report for all domains.

    EXPERIMENTAL / RESEARCH ONLY — backed by ``app.strategy_evolution``.
    """
    try:
        from app.strategy_evolution import get_strategy_evolution_engine

        engine = get_strategy_evolution_engine()
        return await run_in_threadpool(engine.get_all_domains_strategy_report)
    except Exception as e:
        logger.exception("Failed to get all strategies report")
        raise HTTPException(status_code=500, detail="Failed to get all strategy reports") from e


@router.post("/api/scraper/strategy/evolve/{domain}")
async def evolve_domain_strategy(
    domain: str,
    _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR]))],  # noqa: B008, RUF100
):
    """Manually trigger strategy evolution for a domain.

    EXPERIMENTAL / RESEARCH ONLY — backed by ``app.strategy_evolution``.
    """
    try:
        from app.strategy_evolution import get_strategy_evolution_engine

        engine = get_strategy_evolution_engine()
        new_strategy = await run_in_threadpool(engine.evolve_strategy, domain)

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
    except Exception as e:
        logger.exception("Failed manual strategy evolution for domain %s", domain)
        raise HTTPException(status_code=500, detail="Strategy evolution failed") from e

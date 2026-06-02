"""
Experimental / Research Router — semantic, topology, replay, and adaptive endpoints.

EXPERIMENTAL / RESEARCH ONLY — These endpoints expose experimental semantic,
topology, replay, and adaptive modules. They are NOT production-validated
capabilities. Enable/use at your own risk. Behavior may change or be removed.

All imports from experimental modules are lazy (inside function bodies) so
they do not cause startup failures if those modules are unavailable.
"""

from __future__ import annotations

import secrets
import time

from app.config import settings
from app.utils.rbac import UserRole, require_role
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field


def verify_experimental_enabled():
    if not settings.ENABLE_EXPERIMENTAL_ROUTES:
        raise HTTPException(
            status_code=404,
            detail="Experimental / research routes are disabled in this environment. Set DATAFORGE_ENABLE_EXPERIMENTAL_ROUTES=true to enable them."
        )

router = APIRouter(dependencies=[Depends(verify_experimental_enabled)])


# ─── Request Models ────────────────────────────────────────────────────────


class KnowledgeMergeRequest(BaseModel):
    """Validated request body for merge / knowledge endpoint."""

    role_manifold: dict[str, list[float]] = Field(
        default_factory=dict,
        description="Role vectors to merge into the field manifold",
    )
    learned_exclusions: dict[str, float] = Field(
        default_factory=dict,
        description="Learned exclusions to merge (key format: 'role1|role2')",
    )

    @classmethod
    def validate_payload(cls, data: dict) -> "KnowledgeMergeRequest":
        """Validate and cap payload size."""
        max_roles = 500
        max_exclusions = 500
        # Clamp to max sizes
        if "role_manifold" in data and len(data["role_manifold"]) > max_roles:
            data["role_manifold"] = dict(list(data["role_manifold"].items())[:max_roles])
        if "learned_exclusions" in data and len(data["learned_exclusions"]) > max_exclusions:
            data["learned_exclusions"] = dict(list(data["learned_exclusions"].items())[:max_exclusions])
        return cls(**data)


def _require_admin_key(request: Request):
    """Check admin API key for powerful system routes."""
    if not settings.ADMIN_API_KEY:
        return  # No admin key configured — fall back to regular API key
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
async def system_topology():
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
        "role_compatibility": [
            {"role": k[0], "type": k[1], "score": round(v, 3)} for k, v in ws.role_compatibility.items()
        ],
        "drift_logs": {role: ws._observability.get_role_drift(role) for role in ws.get_manifold_roles()},
        "meso_clusters": ws.meso_clusters,
        "macro_continents": ws.macro_continents,
    }


@router.get("/api/system/crystalline")
async def system_crystalline():
    """Returns the synthesized high-integrity knowledge units."""
    from app.semantic_world_state import get_world_state

    ws = get_world_state()
    return {
        "records": ws.crystalline_records,
        "count": len(ws.crystalline_records),
    }


@router.get("/api/system/export/knowledge")
async def export_knowledge():
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
async def merge_knowledge(request: Request, data: dict, _role=Depends(require_role([UserRole.ADMIN]))):
    """Merge an external knowledge manifold into the current field.

    Validated with size caps: max 500 roles, max 500 exclusions.
    Requires admin API key if DATAFORGE_ADMIN_API_KEY is configured.
    """
    _require_admin_key(request)
    # Validate payload with size caps
    try:
        req = KnowledgeMergeRequest.validate_payload(data)
    except Exception as e:
        return JSONResponse(
            status_code=422,
            content={"detail": f"Invalid merge payload: {e}"},
        )

    from app.semantic_world_state import get_world_state

    ws = get_world_state()

    # 1. Merge Manifold (Geometric Beliefs)
    remote_manifold = req.role_manifold
    merged_roles = 0
    for role, vec in remote_manifold.items():
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
async def system_search(query: str, limit: int = 5):
    """Perform topological search on crystalline records."""
    from app.semantic_world_state import get_world_state

    ws = get_world_state()
    results = ws.topological_search(query)[:limit]
    return {"results": results, "query": query}


@router.get("/api/system/observability")
async def system_observability():
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
async def system_domain_policy():
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
async def acquisition_telemetry():
    """Exposes acquisition telemetry: state distribution, recovery rates, recent events."""
    from app.acquisition_telemetry import get_acquisition_telemetry

    return get_acquisition_telemetry().get_summary()


# ═══════════════════════════════════════════════════════════════════════
# Topology History & Event Journal (EXPERIMENTAL / RESEARCH ONLY)
# ═══════════════════════════════════════════════════════════════════════


@router.get("/api/system/history/topology")
async def system_topology_history(limit: int = 20):
    """Returns a timeline of historical topology states for replay."""
    from app.event_journal import get_journal

    journal = get_journal()

    history = []
    structural_entries = [
        e for e in journal._entries if e["type"] in ["restructure_topology", "merge_state", "add", "remove"]
    ]
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
                }
            )

    return {"history": history}


# ═══════════════════════════════════════════════════════════════════════
# Cognitive Processing & Agency (EXPERIMENTAL / RESEARCH ONLY)
# ═══════════════════════════════════════════════════════════════════════


@router.post("/api/system/scheduler/step")
async def process_cognitive_tasks(budget_ms: float = 100.0, _role=Depends(require_role([UserRole.ADMIN]))):
    """Manually trigger processing of the cognitive task queue."""
    from app.semantic_world_state import get_world_state

    ws = get_world_state()
    completed = ws.process_cognitive_queue(budget_ms=budget_ms)
    return {"status": "success", "tasks_completed": completed}


@router.get("/api/system/agency")
async def system_agency():
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
async def system_replay_status():
    """Returns the status of the large-scale persistent replay buffer."""
    from app.replay_buffer import get_replay_buffer

    rb = get_replay_buffer()
    return {
        "buffer": rb.status(),
        "segments": rb.get_segment_info(),
        "checkpoints": len(rb._checkpoints.entries) if hasattr(rb, "_checkpoints") else 0,
    }


@router.get("/api/system/replay/chain")
async def system_replay_chains(limit: int = 20):
    """Returns causal chains reconstructed from the persistent replay buffer."""
    from app.replay_buffer import get_replay_buffer

    rb = get_replay_buffer()
    chains = rb.get_causal_chains(limit=limit)
    return {
        "chains": chains,
        "count": len(chains),
        "total_buffer_entries": rb.status().get("total_entries", 0),
    }


@router.get("/api/system/replay/events")
async def system_replay_events(start_idx: int = 0, end_idx: int = -1):
    """Returns a range of events from the persistent replay buffer."""
    from app.replay_buffer import get_replay_buffer

    rb = get_replay_buffer()
    status = rb.status()
    if end_idx == -1:
        end_idx = status.get("total_entries", 0) - 1
    events = rb.get_event_range(start_idx, end_idx)
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
async def trigger_manifold_compression(_role=Depends(require_role([UserRole.ADMIN]))):
    """Trigger a manifold compression cycle."""
    from app.llm_bridge import get_plugin_manager
    from app.semantic_world_state import get_world_state

    plugins = get_plugin_manager(ws=get_world_state())
    result = plugins.call_tool("manifold_compressor")
    return {"result": result}

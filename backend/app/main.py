
"""
FastAPI Main Server — DataForge General-Purpose Web Scraper API.
"""

import asyncio
from pathlib import Path

# Load .env before any app imports that read env vars at module level
from dotenv import load_dotenv
load_dotenv()

# ruff: noqa: E402
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.routers.jobs import create_jobs_router
from app.routers.exports import create_exports_router
from app.services.job_runner import run_job
from app.services.state import persist_state
from app.state_store import load_state
from app.utils.env import env_int
# Initialize event cascade (safe: scheduler is lazy-created, no circular import)
from app.graph_update_scheduler import get_scheduler
get_scheduler()

app = FastAPI(
    title="DataForge — General-Purpose Web Scraper",
    description="AI-powered scraper that extracts structured data from any website",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Runtime safety rails
CONFIG = {
    "max_discovery_urls": env_int("DATAFORGE_MAX_DISCOVERY_URLS", 20, minimum=1, maximum=100),
    "per_url_timeout_seconds": env_int("DATAFORGE_PER_URL_TIMEOUT_SECONDS", 120, minimum=10, maximum=900),
    "max_job_runtime_seconds": env_int("DATAFORGE_MAX_JOB_RUNTIME_SECONDS", 1800, minimum=60, maximum=14400),
    "ai_structuring_timeout_seconds": env_int("DATAFORGE_AI_STRUCTURING_TIMEOUT_SECONDS", 240, minimum=15, maximum=1800),
    "insight_timeout_seconds": env_int("DATAFORGE_INSIGHT_TIMEOUT_SECONDS", 25, minimum=5, maximum=300),
    "max_job_history": env_int("DATAFORGE_MAX_JOB_HISTORY", 300, minimum=25, maximum=5000),
    "max_recycle_bin_history": env_int("DATAFORGE_MAX_RECYCLE_BIN_HISTORY", 300, minimum=25, maximum=5000),
}

# Durable job store
jobs_store, recycle_bin_store = load_state()

def _persist_state_wrapper():
    persist_state(
        jobs_store=jobs_store,
        recycle_bin_store=recycle_bin_store,
        max_job_history=CONFIG["max_job_history"],
        max_recycle_bin_history=CONFIG["max_recycle_bin_history"]
    )

def _schedule_background_task(coro):
    return asyncio.create_task(coro)

async def _run_job_wrapper(job_id: str):
    await run_job(
        job_id=job_id,
        jobs_store=jobs_store,
        persist_state_fn=_persist_state_wrapper,
        max_discovery_urls=CONFIG["max_discovery_urls"],
        max_job_runtime_seconds=CONFIG["max_job_runtime_seconds"],
        per_url_scrape_timeout_seconds=CONFIG["per_url_timeout_seconds"],
        ai_structuring_timeout_seconds=CONFIG["ai_structuring_timeout_seconds"],
        insight_timeout_seconds=CONFIG["insight_timeout_seconds"],
    )

# Include Routers
app.include_router(
    create_jobs_router(
        jobs_store=jobs_store,
        recycle_bin_store=recycle_bin_store,
        persist_state_fn=_persist_state_wrapper,
        schedule_task_fn=_schedule_background_task,
        run_job_coro_fn=_run_job_wrapper,
        config=CONFIG
    )
)

app.include_router(
    create_exports_router(jobs_store=jobs_store)
)

# Serve Frontend
FRONTEND_DIR = Path(__file__).parent.parent.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/app", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")

@app.get("/")
async def root():
    return {"message": "DataForge API v2", "docs": "/docs", "dashboard": "/app"}

@app.get("/api/system/status")
async def system_status():
    from app.models import JobStatus
    counts = {s.value: 0 for s in JobStatus}
    for job in jobs_store.values():
        status_key = str(job.status.value if isinstance(job.status, JobStatus) else job.status)
        if status_key not in counts:
            counts[status_key] = 0
        counts[status_key] += 1

    active = counts.get(JobStatus.PENDING.value, 0) + counts.get(JobStatus.DISCOVERING.value, 0) + counts.get(JobStatus.RUNNING.value, 0)

    from app.state_store import get_state_file_path
    return {
        "status": "online",
        "jobs": {
            "total": len(jobs_store),
            "active": active,
            "completed": counts.get(JobStatus.COMPLETED.value, 0),
            "failed": counts.get(JobStatus.FAILED.value, 0),
            "canceled": counts.get(JobStatus.CANCELED.value, 0),
        },
        "runtime_limits": CONFIG,
        "state_file": str(get_state_file_path()),
    }

@app.get("/api/system/topology")
async def system_topology():
    """Exposes the raw state of the semantic cognition substrate."""
    from app.semantic_world_state import get_world_state
    ws = get_world_state()
    view = ws._topology.get_view()
    return {
        "metrics": {
            "field_pressure": round(ws.metrics.field_pressure, 3),
            "global_energy": round(ws.metrics.global_energy, 3),
            "semantic_temperature": round(ws.metrics.semantic_temperature, 3),
            "global_entropy": round(ws.metrics.global_entropy, 3),
            "exclusion_count": len(ws.learned_exclusions),
            "learning_count": ws.learning_count,
            "integrity_score": round(ws.metrics.integrity_score, 3),
            "crystalline_count": len(ws.crystalline_records),
        },
        "global_communities": [list(c) for c in ws.global_communities],
        "schema_patterns": [{"roles": list(k), "count": v} for k, v in ws.schema_patterns.items()],
        "learned_exclusions": [{"roles": list(k), "strength": round(v, 3)} for k, v in ws.learned_exclusions.items()],
        "field_regions": view.all_region_dicts(),
        "role_compatibility": [{"role": k[0], "type": k[1], "score": round(v, 3)} for k, v in ws.role_compatibility.items()]
    }


@app.get("/api/system/crystalline")
async def system_crystalline():
    """Returns the synthesized high-integrity knowledge units."""
    from app.semantic_world_state import get_world_state
    ws = get_world_state()
    return {
        "records": ws.crystalline_records,
        "count": len(ws.crystalline_records)
    }

@app.get("/api/system/export/knowledge")
async def export_knowledge():
    """Export the synthesized knowledge manifold as a portable schema."""
    import time
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

@app.post("/api/system/merge/knowledge")
async def merge_knowledge(data: dict):
    """Merge an external knowledge manifold into the current field (Phase 23)."""
    from app.semantic_world_state import get_world_state
    ws = get_world_state()
    
    # 1. Merge Manifold (Geometric Beliefs)
    remote_manifold = data.get("role_manifold", {})
    merged_roles = 0
    for role, vec in remote_manifold.items():
        if ws._manifold.has_manifold_role(role):
            # Blend vectors (Physical Consensus) — controlled mutation through ManifoldState
            ws._manifold.blend_manifold_vector(role, list(vec), alpha=0.7, beta=0.3)
        else:
            ws._manifold.set_manifold_vector(role, list(vec))
        merged_roles += 1
            
    # 2. Merge Exclusions (Topological Constraints)
    remote_exc = data.get("learned_exclusions", {})
    for k_str, val in remote_exc.items():
        parts = k_str.split("|")
        if len(parts) == 2:
            key = tuple(sorted(parts))
            ws._instability.set_exclusion(key, max(ws._instability.get_exclusion_by_key(key), val))
            
    return {"status": "merged", "roles_merged": merged_roles, "total_manifold": len(ws.role_manifold)}

@app.get("/api/system/search")
async def system_search(query: str, limit: int = 5):
    """Perform topological search on crystalline records."""
    from app.semantic_world_state import get_world_state
    ws = get_world_state()
    results = ws.topological_search(query)[:limit]
    return {"results": results, "query": query}

@app.get("/api/system/observability")
async def system_observability():
    """Exposes real-time telemetry and activity heatmaps."""
    from app.semantic_world_state import get_world_state
    ws = get_world_state()
    return {
        "telemetry": ws._observability.telemetry[-50:],
        "heatmap": ws._observability.heatmap,
        "causal_trace": ws._observability.get_causal_telemetry()[-20:],
        "hierarchy": {
            "envelopes": list(ws._abstraction.envelopes.keys()),
            "levels": {r: ws._abstraction.get_role_level(r) for r in ws.role_manifold}
        }
    }

@app.post("/api/system/scheduler/step")
async def process_cognitive_tasks(budget_ms: float = 100.0):
    """Manually trigger processing of the cognitive task queue."""
    from app.semantic_world_state import get_world_state
    ws = get_world_state()
    completed = ws.process_cognitive_queue(budget_ms=budget_ms)
    return {"status": "success", "tasks_completed": completed}

@app.get("/api/system/agency")
async def system_agency():
    """Returns the state of autonomous agency and tools."""
    from app.semantic_world_state import get_world_state
    from app.llm_bridge import get_plugin_manager
    ws = get_world_state()
    plugins = get_plugin_manager(ws=ws)
    return {
        "active_actions": ws._action.active_actions,
        "available_tools": plugins.get_available_tools(),
        "action_history": ws._action.action_history[-30:],
        "active_intents": ws._intent.active_intents
    }

@app.post("/api/system/refactor/compress")
async def trigger_manifold_compression():
    """Trigger an autonomous manifold compression cycle."""
    from app.semantic_world_state import get_world_state
    from app.llm_bridge import get_plugin_manager
    plugins = get_plugin_manager(ws=get_world_state())
    result = plugins.call_tool("manifold_compressor")
    return {"result": result}

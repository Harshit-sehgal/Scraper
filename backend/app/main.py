"""
FastAPI Main Server — DataForge General-Purpose Web Scraper API.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict, Any

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from pydantic import BaseModel, Field

from app.config import settings
from app.routers.jobs import create_jobs_router
from app.routers.exports import create_exports_router
from app.routers.scraper import router as scraper_router
from app.services.job_runner import run_job
from app.state_store import get_state_file_path
from app.storage_interface import get_job_repository

# Repository is resolved lazily inside lifespan() so that env vars can be
# patched during tests before startup. The module-level variable is set
# during startup and referenced by route handlers.
job_repo = None
from app.rate_limiter import RateLimiterMiddleware


from enum import Enum


class AcquisitionMode(str, Enum):
    """Acquisition mode for URL preview/analysis.
    
    Determines how aggressively the system attempts to acquire the page:
    - standard: Basic fetch, single attempt
    - aggressive: Session recovery, search form submission
    - deep_scan: All recovery strategies, multiple retries
    """
    STANDARD = "standard"
    AGGRESSIVE = "aggressive"
    DEEP_SCAN = "deep_scan"


# ─── Request Models ────────────────────────────────────────────────────────


class URLPreviewRequest(BaseModel):
    """Request body for URL analysis."""
    url: str = Field(..., description="The URL to analyze for data extraction")
    search_params: dict[str, str] | None = Field(
        default=None,
        description=(
            "Optional search parameters to submit to the site's search form if "
            "the URL has expired (e.g. expired session token). Keys are semantic: "
            "origin, destination, departure_date, return_date, adults, children. "
            "Values are the search values (e.g. 'NYC', 'LHR', '05/15/2026')."
        ),
    )
    acquisition_mode: AcquisitionMode = Field(
        default=AcquisitionMode.STANDARD,
        description=(
            "Acquisition mode: 'standard' (basic fetch), 'aggressive' (session recovery, "
            "search form submission), or 'deep_scan' (all recovery strategies, multiple retries)."
        ),
    )


logger = logging.getLogger(__name__)


# ─── Module-level globals ────────────────────────────────────────────────
# These are populated by the lifespan handler but referenced by route handlers.
# They are intentionally module-level to support the existing router pattern.
# Pre-initialize CONFIG with defaults so it's available before lifespan runs.
from app.config import settings as _cfg  # noqa

jobs_store: Dict[str, Any] = {}
recycle_bin_store: Dict[str, Any] = {}
CONFIG: Dict[str, Any] = {
    "max_discovery_urls": _cfg.MAX_DISCOVERY_URLS,
    "per_url_timeout_seconds": _cfg.PER_URL_TIMEOUT_SECONDS,
    "max_job_runtime_seconds": _cfg.MAX_JOB_RUNTIME_SECONDS,
    "ai_structuring_timeout_seconds": _cfg.AI_STRUCTURING_TIMEOUT_SECONDS,
    "insight_timeout_seconds": _cfg.INSIGHT_TIMEOUT_SECONDS,
    "max_job_history": _cfg.MAX_JOB_HISTORY,
    "max_recycle_bin_history": _cfg.MAX_RECYCLE_BIN_HISTORY,
}
gossip = None
heartbeat_mgr = None
_background_tasks: list[asyncio.Task] = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan event handler for FastAPI startup/shutdown.

    Migrated from deprecated @app.on_event(\"startup\") pattern.
    Handles all initialization: recovery framework, domain health,
    distributed readiness (gossip/heartbeat), state loading,
    and background task scheduling.
    """
    global CONFIG, gossip, heartbeat_mgr

    # ─── STARTUP ──────────────────────────────────────────────────────

    # Strict Production Security Check
    if settings.ENV.lower() == "production":
        if not settings.CORS_ORIGINS or "*" in settings.CORS_ORIGINS:
            raise ValueError(
                "CORS_ORIGINS contains wildcard '*' or is empty. In production environment, "
                "CORS_ORIGINS must be locked down to trusted domains for safety."
            )
        if not settings.API_KEY or not settings.API_KEY.strip():
            raise ValueError(
                "API_KEY is empty or not configured. In production environment, "
                "API_KEY must be explicitly set to secure all API endpoints."
            )

    # Initialize event cascade (safe: scheduler is lazy-created, no circular import)
    from app.graph_update_scheduler import get_scheduler
    get_scheduler()

    # Initialize Recovery Framework
    from app.recovery_handlers import register_all_recovery_handlers
    register_all_recovery_handlers()

    # Initialize Domain Health Monitor
    from app.domain_health_alerts import get_domain_health_monitor
    get_domain_health_monitor()
    logger.info("Domain health monitor initialized")

    # Initialize Distributed Readiness (Gossip + Heartbeat)
    from app.gossip_substrate import get_gossip_substrate
    from app.heartbeat_manager import get_heartbeat_manager
    gossip = get_gossip_substrate(node_id="main")
    heartbeat_mgr = get_heartbeat_manager()
    gossip.integrate_heartbeat(heartbeat_mgr)
    logger.info(
        "Gossip substrate integrated with heartbeat: %d peers registered",
        len(gossip.known_nodes),
    )

    # Runtime safety rails — driven by centralized config
    CONFIG = {
        "max_discovery_urls": settings.MAX_DISCOVERY_URLS,
        "per_url_timeout_seconds": settings.PER_URL_TIMEOUT_SECONDS,
        "max_job_runtime_seconds": settings.MAX_JOB_RUNTIME_SECONDS,
        "ai_structuring_timeout_seconds": settings.AI_STRUCTURING_TIMEOUT_SECONDS,
        "insight_timeout_seconds": settings.INSIGHT_TIMEOUT_SECONDS,
        "max_job_history": settings.MAX_JOB_HISTORY,
        "max_recycle_bin_history": settings.MAX_RECYCLE_BIN_HISTORY,
    }

    # Resolve the repository lazily so env vars can be patched before startup.
    global job_repo
    job_repo = get_job_repository()

    # Durable job store & semantic field state — single DB read on startup
    # Use the repository factory to support SQLite or Postgres transparently
    loaded_jobs, loaded_recycle, world_state_data = job_repo.load_all()
    jobs_store.clear()
    jobs_store.update(loaded_jobs)
    recycle_bin_store.clear()
    recycle_bin_store.update(loaded_recycle)

    # Restore semantic world state from persisted data
    if world_state_data:
        from app.semantic_world_state import get_world_state
        try:
            get_world_state().from_dict(world_state_data)
            logger.info(
                "Restored semantic world state from %s", get_state_file_path()
            )
        except Exception as e:
            logger.exception("Failed to restore semantic world state: %s", e)

    # Schedule periodic gossip propagation
    task = asyncio.create_task(_periodic_gossip_propagation())
    _background_tasks.append(task)
    logger.info("Gossip propagation background task scheduled")

    yield
    # ─── SHUTDOWN ─────────────────────────────────────────────────────

    # Cancel all background tasks
    for t in _background_tasks:
        t.cancel()
    await asyncio.gather(*_background_tasks, return_exceptions=True)
    _background_tasks.clear()
    logger.info("Background tasks cleaned up")


def _schedule_background_task(coro):
    """Schedule a background task with error handling."""
    task = asyncio.create_task(coro)

    def _handle_task_result(t: asyncio.Task):
        try:
            t.result()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("Background task failed: %s", e, exc_info=True)

    task.add_done_callback(_handle_task_result)
    return task


# Create FastAPI app with lifespan
app = FastAPI(
    title="DataForge — General-Purpose Web Scraper",
    description="AI-powered scraper that extracts structured data from any website",
    version="2.0.0",
    lifespan=lifespan,
)

from fastapi.middleware.cors import CORSMiddleware

# Configure CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── API Key Auth + Rate Limit Middleware ────────────────────────────────


@app.middleware("http")
async def api_key_middleware(request: Request, call_next):
    if settings.API_KEY and request.url.path.startswith("/api/"):
        if "/docs" not in request.url.path and "/openapi" not in request.url.path:
            api_key = request.headers.get("X-API-Key", "")
            if api_key != settings.API_KEY:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Invalid or missing API key. Provide X-API-Key header."},
                )
    response = await call_next(request)
    return response


# ─── Rate Limiting Middleware ────────────────────────────────────────

rate_limiter = RateLimiterMiddleware(
    global_limit=settings.RATE_LIMIT_GLOBAL,
)
app.add_middleware(BaseHTTPMiddleware, dispatch=rate_limiter.middleware)


# ─── Periodic Gossip State Propagation ───────────────────────────────

async def _periodic_gossip_propagation():
    """Propagate gossip state every 60 seconds."""
    while True:
        await asyncio.sleep(settings.GOSSIP_PROPAGATION_INTERVAL)
        try:
            if gossip is not None:
                propagated = gossip.propagate_state_via_gossip(heartbeat_manager=heartbeat_mgr)
                if propagated:
                    logger.debug("Propagated gossip state to %d peers", propagated)
        except Exception as e:
            logger.debug("Gossip propagation skipped: %s", e)


def _persist_single_wrapper(job_id: str, critical: bool = False) -> None:
    """Persist a single job to SQLite.

    Args:
        job_id: The job ID to persist.
        critical: If True, re-raise on failure. Use for terminal states
            (completed, failed, canceled, degraded, empty_result).
            If False (default), log and swallow. Use for hot-path progress updates.
    """
    job = jobs_store.get(job_id)
    if job:
        try:
            job_repo.save_single(job)
        except Exception as e:
            logger.error("Failed to persist single job %s: %s", job_id, e)
            if critical:
                raise


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
        # Non-critical: hot-path progress/log persistence is best-effort
        persist_state_single_fn=lambda: _persist_single_wrapper(job_id, critical=False),
        # Critical: terminal state single-row persistence must not be silently lost
        persist_state_single_critical_fn=lambda: _persist_single_wrapper(job_id, critical=True),
    )


def _persist_state_wrapper():
    repo = get_job_repository()
    repo.save_all(jobs=jobs_store, recycle_bin=recycle_bin_store)


# Include Routers
app.include_router(
    create_jobs_router(
        jobs_store=jobs_store,
        recycle_bin_store=recycle_bin_store,
        persist_state_fn=_persist_state_wrapper,
        schedule_task_fn=_schedule_background_task,
        run_job_coro_fn=_run_job_wrapper,
        config=CONFIG,
    )
)

app.include_router(
    create_exports_router(jobs_store=jobs_store)
)

app.include_router(scraper_router)

from app.routers.operator import router as operator_router
app.include_router(operator_router)


# ─── Routes ──────────────────────────────────────────────────────────────


@app.get("/")
async def root():
    return {"message": "DataForge API v2", "docs": "/docs", "dashboard": "/app"}


@app.get("/health")
async def health():
    """Liveness probe — always returns 200 if the process is alive."""
    return {"status": "ok"}


@app.get("/ready")
async def ready():
    """Readiness probe — checks that the configured storage backend is reachable.

    Uses the active JobRepository's health_check() if available (Postgres),
    otherwise falls back to SQLite storage health (SQLite).
    Returns 503 if the backend is unhealthy.
    """
    repo = get_job_repository()
    if hasattr(repo, "health_check"):
        health = repo.health_check()
    else:
        from app.job_store import get_storage_health
        health = get_storage_health()

    if not health["ok"]:
        return JSONResponse(
            status_code=503,
            content={
                "status": "not_ready",
                "error": health.get("error", "Unknown storage health issue"),
                "schema_version": health.get("schema_version", 0),
                "expected_version": health.get("expected_version", 0),
            },
        )

    backend = getattr(repo, "backend", "sqlite")
    return {
        "status": "ready",
        "backend": backend,
        "storage": "ok",
        "migrations": "ok",
        "schema_version": health.get("schema_version", 0),
        "job_count": health.get("job_count", len(jobs_store)),
        "recycle_bin_count": health.get("recycle_bin_count", len(recycle_bin_store)),
    }


@app.get("/api/system/storage/status")
async def storage_status():
    """Detailed storage backend status — uses the active JobRepository."""
    repo = get_job_repository()
    if hasattr(repo, "health_check"):
        health = repo.health_check()
        return {
            "backend": "postgres",
            "ok": health.get("ok", False),
            "schema_version": health.get("schema_version", 0),
            "expected_version": health.get("expected_version", 0),
            "job_count": health.get("job_count", 0),
            "recycle_bin_count": health.get("recycle_bin_count", 0),
        }
    from app.job_store import get_storage_status
    return get_storage_status()


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
            "degraded": counts.get(JobStatus.DEGRADED.value, 0),
            "empty_result": counts.get(JobStatus.EMPTY_RESULT.value, 0),
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


@app.get("/api/system/crystalline")
async def system_crystalline():
    """Returns the synthesized high-integrity knowledge units."""
    from app.semantic_world_state import get_world_state
    ws = get_world_state()
    return {
        "records": ws.crystalline_records,
        "count": len(ws.crystalline_records),
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
    """Merge an external knowledge manifold into the current field."""
    from app.semantic_world_state import get_world_state
    ws = get_world_state()

    # 1. Merge Manifold (Geometric Beliefs)
    remote_manifold = data.get("role_manifold", {})
    merged_roles = 0
    for role, vec in remote_manifold.items():
        if ws.has_manifold_role(role):
            ws.blend_manifold_vector(role, list(vec), alpha=0.7, beta=0.3)
        else:
            ws.set_manifold_vector(role, list(vec))
        merged_roles += 1

    # 2. Merge Exclusions (Topological Constraints)
    remote_exc = data.get("learned_exclusions", {})
    for k_str, val in remote_exc.items():
        parts = k_str.split("|")
        if len(parts) == 2:
            key = tuple(sorted(parts))
            from app.instability_api import InstabilityAPI
            inst_api = InstabilityAPI(ws=ws)
            current = inst_api.get_learned_exclusion(key[0], key[1])
            inst_api.set_exclusion(key[0], key[1], max(current, val))

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
        "telemetry": ws.observability_telemetry[-50:],
        "heatmap": ws.observability_heatmap,
        "causal_trace": ws.get_causal_telemetry()[-20:],
        "health_index": ws._observability.get_semantic_health_index(ws.capture_governance_snapshot()),
        "hierarchy": {
            "envelopes": list(ws.abstraction_envelopes.keys()),
            "levels": {r: ws.get_role_level(r) for r in ws.role_manifold},
        },
    }


@app.get("/api/system/domain-policy")
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


@app.get("/api/system/acquisition/telemetry")
async def acquisition_telemetry():
    """Exposes acquisition telemetry: state distribution, recovery rates, recent events."""
    from app.acquisition_telemetry import get_acquisition_telemetry
    return get_acquisition_telemetry().get_summary()


@app.get("/api/system/history/topology")
async def system_topology_history(limit: int = 20):
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
            history.append({
                "idx": idx,
                "timestamp": entry["timestamp"],
                "type": entry["type"],
                "topology": snapshot["topology"],
            })

    return {"history": history}


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
        "active_actions": ws.active_actions,
        "available_tools": plugins.get_available_tools(),
        "action_history": ws.action_history[-30:],
        "active_intents": ws.active_intents,
    }


@app.get("/api/system/replay/status")
async def system_replay_status():
    """Returns the status of the large-scale persistent replay buffer."""
    from app.replay_buffer import get_replay_buffer
    rb = get_replay_buffer()
    return {
        "buffer": rb.status(),
        "segments": rb.get_segment_info(),
        "checkpoints": len(rb._checkpoints.entries) if hasattr(rb, "_checkpoints") else 0,
    }


@app.get("/api/system/replay/chain")
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


@app.get("/api/system/replay/events")
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


@app.post("/api/system/refactor/compress")
async def trigger_manifold_compression():
    """Trigger an autonomous manifold compression cycle."""
    from app.semantic_world_state import get_world_state
    from app.llm_bridge import get_plugin_manager
    plugins = get_plugin_manager(ws=get_world_state())
    result = plugins.call_tool("manifold_compressor")
    return {"result": result}


@app.get("/api/system/diagnostics/export")
async def export_system_diagnostics():
    """Generates and exports an authenticated and sanitized system diagnostics ZIP bundle."""
    import io
    import zipfile
    import json
    import re
    from fastapi import Response
    from app.config import settings
    from app.selector_memory import get_selector_memory
    from app.semantic_world_state import get_world_state

    # Regular expressions for PII sanitization
    email_regex = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
    phone_regex = re.compile(r"\+?\b\d[\d\s()\-]{8,14}\d\b")
    sensitive_keys = {"authorization", "auth", "api_key", "key", "password", "token", "secret", "signature", "alert_webhook_url", "credential", "session", "cookie", "bearer", "private", "client_secret", "api_secret", "access_key", "secret_key"}

    def sanitize_value(val):
        if isinstance(val, str):
            val = email_regex.sub("<redacted_email>", val)
            val = phone_regex.sub("<redacted_phone>", val)
            return val
        elif isinstance(val, dict):
            return {
                k: ("********" if any(s in k.lower() for s in sensitive_keys) else sanitize_value(v))
                for k, v in val.items()
            }
        elif isinstance(val, list):
            return [sanitize_value(item) for item in val]
        else:
            return val

    # 1. anonymized_state.json
    anonymized_jobs = {}
    for j_id, job in jobs_store.items():
        if hasattr(job, "model_dump"):
            job_dict = job.model_dump()
        elif hasattr(job, "dict"):
            job_dict = job.dict()
        else:
            job_dict = dict(job)
        anonymized_jobs[j_id] = sanitize_value(job_dict)

    anonymized_recycle = {}
    for j_id, job in recycle_bin_store.items():
        if hasattr(job, "model_dump"):
            job_dict = job.model_dump()
        elif hasattr(job, "dict"):
            job_dict = job.dict()
        else:
            job_dict = dict(job)
        anonymized_recycle[j_id] = sanitize_value(job_dict)

    anonymized_state = {
        "jobs": anonymized_jobs,
        "recycle_bin": anonymized_recycle
    }

    # 2. active_settings.json
    settings_dict = {}
    if hasattr(settings, "model_dump"):
        settings_dict = settings.model_dump()
    elif hasattr(settings, "dict"):
        settings_dict = settings.dict()
    else:
        settings_dict = dict(settings)

    masked_settings = {}
    for k, v in settings_dict.items():
        if any(s in k.lower() for s in sensitive_keys):
            masked_settings[k] = "********"
        else:
            masked_settings[k] = sanitize_value(v)

    # 3. selector_decay_snapshots.json
    selector_decay_snapshots = {}
    try:
        memory = get_selector_memory()
        if memory and hasattr(memory, "_memory"):
            for domain, entry in memory._memory.items():
                conf = memory._compute_confidence(entry)
                selector_decay_snapshots[domain] = {
                    "selectors": entry.get("selectors"),
                    "success_count": entry.get("success_count", 0),
                    "failure_count": entry.get("failure_count", 0),
                    "first_seen": entry.get("first_seen"),
                    "last_success": entry.get("last_success"),
                    "confidence": {
                        "raw_confidence": conf.raw_confidence,
                        "age_factor": conf.age_factor,
                        "freshness_factor": conf.freshness_factor,
                        "final_score": conf.final_score,
                        "reason": conf.reason
                    }
                }
    except Exception as e:
        logger.exception("Failed to build selector decay snapshots for diagnostics: %s", e)
        selector_decay_snapshots = {"error": {"message": str(e)}}

    # 4. telemetry_snapshots.json
    telemetry_snapshots = []
    try:
        ws = get_world_state()
        if hasattr(ws, "_observability") and ws._observability:
            telemetry_snapshots = sanitize_value(ws._observability.telemetry)
    except Exception as e:
        logger.exception("Failed to build telemetry snapshots for diagnostics: %s", e)
        telemetry_snapshots = [{"error": str(e)}]

    # Create ZIP archive in memory
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        zip_file.writestr("anonymized_state.json", json.dumps(anonymized_state, indent=2))
        zip_file.writestr("active_settings.json", json.dumps(masked_settings, indent=2))
        zip_file.writestr("selector_decay_snapshots.json", json.dumps(selector_decay_snapshots, indent=2))
        zip_file.writestr("telemetry_snapshots.json", json.dumps(telemetry_snapshots, indent=2))

    zip_buffer.seek(0)
    headers = {
        "Content-Disposition": "attachment; filename=dataforge_diagnostics.zip"
    }
    return Response(zip_buffer.getvalue(), media_type="application/zip", headers=headers)


# ─── URL Analyzer Endpoint ──────────────────────────────────────────────


@app.post("/api/url/analyze")
async def analyze_url(req: URLPreviewRequest):
    """Analyze a URL and auto-detect what data fields can be extracted.
    
    Fetches the URL, analyzes page structure, detects value patterns,
    and uses LLM to discover all data fields with their CSS selectors,
    types, confidence scores, and example values.
    
    This is the "preview URL → suggest fields" step that lets users
    see what data is available before deciding what to scrape.
    
    Note: A 120-second overall timeout is enforced to prevent hanging
    connections. If the page takes too long to render or the LLM is
    unresponsive, a clear timeout error is returned instead of a
    connection reset / cryptic NetworkError on the frontend.
    
    Returns:
        url: The analyzed URL
        page_structure: Type of structure (table|cards|list|mixed)
        structure_confidence: How confident we are in the structure type
        estimated_record_count: Estimated number of records on the page
        item_container: CSS selector for repeating items
        fetch_method: Method used to fetch the page
        fetch_time_ms: Time taken to fetch and analyze
        anti_bot_score: Likelihood the page has anti-bot protection
        suggested_fields: List of detected fields with name, type, selector, example, confidence
    """
    from app.selector_discovery import analyze_url_for_fields
    
    URL_ANALYZER_TIMEOUT = settings.URL_ANALYZER_TIMEOUT
    
    try:
        result = await asyncio.wait_for(
            analyze_url_for_fields(url=req.url, search_params=req.search_params, acquisition_mode=req.acquisition_mode),
            timeout=URL_ANALYZER_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.warning("[URLAnalyzer] Timeout after %ds analyzing %s", URL_ANALYZER_TIMEOUT, req.url)
        return JSONResponse(
            status_code=408,
            content={
                "url": req.url,
                "error": f"Analysis timed out after {URL_ANALYZER_TIMEOUT} seconds. The page may be too slow, heavy, or protected by anti-bot measures.",
                "redirect_info": None,
                "content_quality": None,
                "page_structure": "unknown",
                "structure_confidence": 0.0,
                "estimated_record_count": 0,
                "item_container": None,
                "suggested_fields": [],
                "anti_bot_score": 0.0,
            },
        )
    
    if "error" in result and result["error"]:
        return JSONResponse(status_code=422, content=result)
    
    return result


# ─── Serve Frontend (must be AFTER all API route definitions) ────────────
FRONTEND_DIR = Path(__file__).parent.parent.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/app", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
    DASHBOARD_DIR = FRONTEND_DIR / "dashboard"
    if DASHBOARD_DIR.exists():
        app.mount("/dashboard", StaticFiles(directory=str(DASHBOARD_DIR), html=True), name="dashboard")


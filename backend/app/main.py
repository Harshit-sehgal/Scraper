"""
FastAPI Main Server — DataForge General-Purpose Web Scraper API.
"""

from app.routers.operator import router as operator_router
from fastapi.middleware.cors import CORSMiddleware
from enum import Enum
import time
from app.audit_logger import log_auth_event
from app.utils.rbac import UserRole, require_role
from app.rate_limiter import RateLimiterMiddleware
import asyncio
import logging
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict, Any

from fastapi import FastAPI, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, Response
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


class AcquisitionMode(str, Enum):
    """Acquisition mode for URL preview / analysis.

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
            "the URL has expired (e.g. expired session token). Keys are semantic field names "
            "and values are the search values (e.g. 'location', 'date', 'query')."
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
    """Lifespan event handler for FastAPI startup / shutdown.

    Migrated from deprecated @app.on_event(\"startup\") pattern.
    Handles all initialization: recovery framework, domain health,
    distributed readiness (gossip / heartbeat), state loading,
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
        from app.utils.prod_security_validator import validate_production_credentials

        validate_production_credentials(settings)

    # Initialize event cascade (safe: scheduler is lazy-created, no circular
    # import)
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
            logger.info("Restored semantic world state from %s", get_state_file_path())
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

    # Persist semantic world state to repository if Postgres supports it
    try:
        repo = get_job_repository()
        if hasattr(repo, "save_world_state"):
            from app.semantic_world_state import get_world_state

            ws = get_world_state()
            try:
                repo.save_world_state(ws.to_dict())
                logger.info("Semantic world state persisted to repository on shutdown")
            except Exception as e:
                logger.warning("Failed to persist world state on shutdown: %s", e)
    except Exception as e:
        logger.warning("Failed to check repository support for world state during shutdown: %s", e)

    # Flush any pending background state writes
    try:
        from app.state_store import flush_state_writes

        flush_state_writes()
    except Exception as e:
        logger.warning("Failed to flush state writes during shutdown: %s", e)

    # Close Postgres connection pool if active
    try:
        from app.postgres_repository import shutdown_postgres

        shutdown_postgres()
    except ImportError:
        logger.debug("Postgres support is not installed; no Postgres pool to close")
    except Exception as e:
        logger.warning("Failed to close Postgres connection pool during shutdown: %s", e)


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
# Disable interactive API docs in production to prevent schema leakage
_docs_url = None if settings.ENV.lower() == "production" else "/docs"
_redoc_url = None if settings.ENV.lower() == "production" else "/redoc"
_openapi_url = None if settings.ENV.lower() == "production" else "/openapi.json"

app = FastAPI(
    title="DataForge — General-Purpose Web Scraper",
    description="Web extraction backend for supported accessible pages",
    version="2.0.0",
    lifespan=lifespan,
    docs_url=_docs_url,
    redoc_url=_redoc_url,
    openapi_url=_openapi_url,
)


# Configure CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Request Body Size Limit ───────────────────────────────────────────


MAX_BODY_SIZE = 5 * 1024 * 1024  # 5MB


@app.middleware("http")
async def body_size_middleware(request: Request, call_next):
    """Limit request body size to prevent abuse."""
    if request.method not in ("POST", "PUT", "PATCH") or not request.url.path.startswith("/api/"):
        return await call_next(request)

    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_BODY_SIZE:
                return JSONResponse(
                    status_code=413,
                    content={"detail": "Request body too large (max 5MB)"},
                )
            return await call_next(request)
        except (ValueError, TypeError):
            pass

    chunks: list[bytes] = []
    bytes_received = 0
    async for chunk in request.stream():
        bytes_received += len(chunk)
        if bytes_received > MAX_BODY_SIZE:
            return JSONResponse(
                status_code=413,
                content={"detail": "Request body too large (max 5MB)"},
            )
        chunks.append(chunk)

    body = b"".join(chunks)
    replayed = False

    async def replay_body():
        nonlocal replayed
        if replayed:
            return {"type": "http.request", "body": b"", "more_body": False}
        replayed = True
        return {"type": "http.request", "body": body, "more_body": False}

    request._receive = replay_body
    return await call_next(request)


# ─── API Key Auth Middleware ────────────────────────────────────────────────


@app.middleware("http")
async def api_key_middleware(request: Request, call_next):
    if (
        settings.API_KEY or settings.ADMIN_API_KEY or getattr(settings, "OPERATOR_API_KEY", "")
    ) and request.url.path.startswith("/api/"):
        # Protect /docs and /openapi behind API key in production
        is_docs_path = "/docs" in request.url.path or "/openapi" in request.url.path
        if not is_docs_path or settings.ENV.lower() == "production":
            api_key = request.headers.get("X-API-Key", "")
            admin_key_header = request.headers.get("X-Admin-Key", "")
            auth_header = request.headers.get("Authorization", "")
            auth_scheme, _, auth_token = auth_header.partition(" ")
            bearer_token = auth_token.strip() if auth_scheme.lower() == "bearer" else ""

            def is_match(provided, expected):
                if not expected or not provided:
                    return False
                return secrets.compare_digest(provided, expected)

            # Track which role was matched during auth to avoid redundant
            # comparisons
            matched_role: str | None = None
            if settings.API_KEY and (is_match(api_key, settings.API_KEY) or is_match(bearer_token, settings.API_KEY)):
                matched_role = "user"
            elif getattr(settings, "OPERATOR_API_KEY", "") and (
                is_match(api_key, settings.OPERATOR_API_KEY) or is_match(bearer_token, settings.OPERATOR_API_KEY)
            ):
                matched_role = "operator"
            elif settings.ADMIN_API_KEY and (
                is_match(api_key, settings.ADMIN_API_KEY)
                or is_match(bearer_token, settings.ADMIN_API_KEY)
                or is_match(admin_key_header, settings.ADMIN_API_KEY)
            ):
                matched_role = "admin"

            if not matched_role:
                log_auth_event(
                    actor=request.client.host if request.client else "unknown",
                    action="api_key_auth",
                    resource=request.url.path,
                    outcome="failure",
                    details={"method": request.method, "has_bearer": bool(bearer_token)},
                )
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Invalid or missing API key. Provide X-API-Key or Authorization Bearer token."},
                )
            # Log successful auth for non-GET requests (mutations) only
            # to avoid noise from routine page loads
            if request.method != "GET":
                log_auth_event(
                    actor=f"{matched_role}:{
                        request.client.host if request.client else 'unknown'}",
                    action="api_key_auth",
                    resource=request.url.path,
                    outcome="success",
                    details={"role": matched_role, "method": request.method},
                )
    response = await call_next(request)
    return response


# ─── Rate Limiting Middleware ────────────────────────────────────────

rate_limiter = RateLimiterMiddleware(
    global_limit=settings.RATE_LIMIT_GLOBAL,
)
app.add_middleware(BaseHTTPMiddleware, dispatch=rate_limiter.middleware)


# ─── Metrics / Request Latency Middleware ─────────────────────────────


@app.middleware("http")
async def latency_tracking_middleware(request: Request, call_next):
    """Track API and metrics endpoint request durations for Prometheus export."""
    path = request.url.path
    # Only track API routes and the metrics endpoint itself
    if path.startswith("/api/") or path == "/metrics" or path in ("/health", "/ready"):
        start = time.time()
        try:
            response = await call_next(request)
            return response
        finally:
            duration = time.time() - start
            from app.metrics_collector import record_request_latency

            record_request_latency(duration)
    else:
        return await call_next(request)


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
    """Persist a single job to the configured backend.

    Resolves the repository lazily via get_job_repository() so this works
    before lifespan runs (e.g. in tests).

    Args:
        job_id: The job ID to persist.
        critical: If True, re-raise on failure. Use for terminal states
            (completed, failed, canceled, degraded, empty_result).
            If False (default), log and swallow. Use for hot-path progress updates.
    """
    job = jobs_store.get(job_id)
    if job:
        try:
            get_job_repository().save_single(job)
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
        # Non-critical: hot-path progress / log persistence is best-effort
        persist_state_single_fn=lambda: _persist_single_wrapper(job_id, critical=False),
        # Critical: terminal state single-row persistence must not be silently
        # lost
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

app.include_router(create_exports_router(jobs_store=jobs_store))

app.include_router(scraper_router)

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

    In production mode, returns minimal info to avoid leaking backend / schema details.
    """
    start_time = time.time()
    repo = get_job_repository()
    try:
        if hasattr(repo, "health_check"):
            health = repo.health_check()
        else:
            from app.job_store import get_storage_health

            health = get_storage_health()

        duration = time.time() - start_time
        from app.metrics_collector import record_health_check_latency as _rchl

        _rchl(duration)

        if not health["ok"]:
            content = {"status": "not_ready"}
            if settings.ENV.lower() != "production":
                content["error"] = health.get("error", "Backend unhealthy")
            return JSONResponse(
                status_code=503,
                content=content,
            )

        # In production return minimal info to avoid leaking backend / schema
        # details
        if settings.ENV.lower() == "production":
            return {"status": "ready"}

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
    except Exception as e:
        duration = time.time() - start_time
        from app.metrics_collector import record_health_check_latency

        record_health_check_latency(duration)
        content = {"status": "not_ready"}
        if settings.ENV.lower() != "production":
            content["error"] = str(e)
        return JSONResponse(
            status_code=503,
            content=content,
        )


@app.get("/api / system / storage / status")
async def storage_status():
    """Detailed storage backend status — uses the active JobRepository."""
    repo = get_job_repository()
    if hasattr(repo, "health_check"):
        health = repo.health_check()
        return {
            "backend": "postgres",
            "ok": health.get("ok", False),
            "error": health.get("error"),
            "schema_version": health.get("schema_version", 0),
            "expected_version": health.get("expected_version", 0),
            "job_count": health.get("job_count", 0),
            "recycle_bin_count": health.get("recycle_bin_count", 0),
        }
    from app.job_store import get_storage_status

    return get_storage_status()


@app.get("/api / system / status")
async def system_status():
    from app.models import JobStatus

    counts = {s.value: 0 for s in JobStatus}
    for job in jobs_store.values():
        status_key = str(job.status.value if isinstance(job.status, JobStatus) else job.status)
        if status_key not in counts:
            counts[status_key] = 0
        counts[status_key] += 1

    active = (
        counts.get(JobStatus.PENDING.value, 0)
        + counts.get(JobStatus.DISCOVERING.value, 0)
        + counts.get(JobStatus.RUNNING.value, 0)
    )

    from app.state_store import get_state_file_path
    from app.storage_interface import get_job_repository

    repo = get_job_repository()
    backend = getattr(repo, "backend", "sqlite")
    response = {
        "status": "online",
        "backend": backend,
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
    }
    if settings.ENV.lower() != "production":
        response["state_file"] = str(get_state_file_path())
    return response


@app.get("/api / system / topology")
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
        "role_compatibility": [
            {"role": k[0], "type": k[1], "score": round(v, 3)} for k, v in ws.role_compatibility.items()
        ],
        "drift_logs": {role: ws._observability.get_role_drift(role) for role in ws.get_manifold_roles()},
        "meso_clusters": ws.meso_clusters,
        "macro_continents": ws.macro_continents,
    }


@app.get("/api / system / crystalline")
async def system_crystalline():
    """Returns the synthesized high-integrity knowledge units."""
    from app.semantic_world_state import get_world_state

    ws = get_world_state()
    return {
        "records": ws.crystalline_records,
        "count": len(ws.crystalline_records),
    }


@app.get("/api / system / export / knowledge")
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
        from fastapi import HTTPException

        raise HTTPException(
            status_code=403,
            detail="Admin API key required. Provide X-Admin-Key header.",
        )


@app.post("/api / system / merge / knowledge")
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


@app.get("/api / system / search")
async def system_search(query: str, limit: int = 5):
    """Perform topological search on crystalline records."""
    from app.semantic_world_state import get_world_state

    ws = get_world_state()
    results = ws.topological_search(query)[:limit]
    return {"results": results, "query": query}


@app.get("/api / system / observability")
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


@app.get("/api / system / domain-policy")
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


@app.get("/api / system / acquisition / telemetry")
async def acquisition_telemetry():
    """Exposes acquisition telemetry: state distribution, recovery rates, recent events."""
    from app.acquisition_telemetry import get_acquisition_telemetry

    return get_acquisition_telemetry().get_summary()


@app.get("/api / system / history / topology")
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


@app.post("/api / system / scheduler / step")
async def process_cognitive_tasks(budget_ms: float = 100.0, _role=Depends(require_role([UserRole.ADMIN]))):
    """Manually trigger processing of the cognitive task queue."""
    from app.semantic_world_state import get_world_state

    ws = get_world_state()
    completed = ws.process_cognitive_queue(budget_ms=budget_ms)
    return {"status": "success", "tasks_completed": completed}


@app.get("/api / system / agency")
async def system_agency():
    """Returns the state of automated agency and tools."""
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


@app.get("/api / system / replay / status")
async def system_replay_status():
    """Returns the status of the large-scale persistent replay buffer."""
    from app.replay_buffer import get_replay_buffer

    rb = get_replay_buffer()
    return {
        "buffer": rb.status(),
        "segments": rb.get_segment_info(),
        "checkpoints": len(rb._checkpoints.entries) if hasattr(rb, "_checkpoints") else 0,
    }


@app.get("/api / system / replay / chain")
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


@app.get("/api / system / replay / events")
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


@app.post("/api / system / refactor / compress")
async def trigger_manifold_compression(_role=Depends(require_role([UserRole.ADMIN]))):
    """Trigger a manifold compression cycle."""
    from app.semantic_world_state import get_world_state
    from app.llm_bridge import get_plugin_manager

    plugins = get_plugin_manager(ws=get_world_state())
    result = plugins.call_tool("manifold_compressor")
    return {"result": result}


@app.get("/api / system / diagnostics / export")
async def export_system_diagnostics(_role=Depends(require_role([UserRole.ADMIN]))):
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
    sensitive_keys = {
        "authorization",
        "auth",
        "api_key",
        "key",
        "password",
        "token",
        "secret",
        "signature",
        "alert_webhook_url",
        "credential",
        "session",
        "cookie",
        "bearer",
        "private",
        "client_secret",
        "api_secret",
        "access_key",
        "secret_key",
    }

    def sanitize_value(val, _depth=0, _max_depth=50):
        if _depth >= _max_depth:
            return val
        if isinstance(val, str):
            val = email_regex.sub("<redacted_email>", val)
            val = phone_regex.sub("<redacted_phone>", val)
            return val
        elif isinstance(val, dict):
            return {
                k: (
                    "********"
                    if any(s in k.lower() for s in sensitive_keys)
                    else sanitize_value(v, _depth=_depth + 1, _max_depth=_max_depth)
                )
                for k, v in val.items()
            }
        elif isinstance(val, list):
            return [sanitize_value(item, _depth=_depth + 1, _max_depth=_max_depth) for item in val]
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

    anonymized_state = {"jobs": anonymized_jobs, "recycle_bin": anonymized_recycle}

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
                        "reason": conf.reason,
                    },
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
    headers = {"Content-Disposition": "attachment; filename=dataforge_diagnostics.zip"}
    return Response(zip_buffer.getvalue(), media_type="application / zip", headers=headers)


# ─── URL Analyzer Endpoint ──────────────────────────────────────────────


@app.post("/api / url / analyze")
async def analyze_url(
    req: URLPreviewRequest, _role: UserRole = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR]))
):
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
    from app.url_safety import validate_public_http_url

    try:
        validate_public_http_url(req.url)
    except ValueError as e:
        return JSONResponse(
            status_code=400,
            content={
                "url": req.url,
                "error": f"URL failed security validation: {e}",
                "page_structure": "unknown",
                "structure_confidence": 0.0,
                "estimated_record_count": 0,
                "item_container": None,
                "suggested_fields": [],
                "anti_bot_score": 0.0,
            },
        )

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
                "error": (
                    f"Analysis timed out after {URL_ANALYZER_TIMEOUT} seconds. "
                    "The page may be too slow, heavy, or protected by anti-bot measures."
                ),
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


# ─── Prometheus /metrics endpoint ───────────────────────────────────────

# ─── Prometheus Metrics State ──────────────────────────────────────────
# Module-level collectors for runtime metrics.
# Shared state is in app.metrics_collector to avoid circular imports with
# worker_queue.

METRICS_COLLECTION_ERRORS = 0


def _prometheus_label_text(labels: dict[str, str]) -> str:
    if not labels:
        return ""
    escaped = {key: str(value).replace("\\", "\\\\").replace('"', '\\"') for key, value in labels.items()}
    return "{" + ",".join(f'{key}="{value}"' for key, value in escaped.items()) + "}"


def _basic_metric_line(name: str, value: float | int, labels: dict[str, str] | None = None) -> str:
    return f"{name}{_prometheus_label_text(labels or {})} {value}"


def _render_basic_metrics_text() -> str:
    """Render a minimal Prometheus exposition if prometheus_client is unavailable."""
    from app.metrics_collector import (
        get_errors,
        get_health_check_latencies,
        get_llm_calls,
        get_request_latencies,
        get_requests_total,
        get_worker_failures,
    )
    from app.models import JobStatus

    lines: list[str] = []

    counts = {s.value: 0 for s in JobStatus}
    for job in jobs_store.values():
        status_key = str(job.status.value if isinstance(job.status, JobStatus) else job.status)
        counts[status_key] = counts.get(status_key, 0) + 1
    for status, count in counts.items():
        lines.append(_basic_metric_line("dataforge_jobs_total", count, {"status": status}))

    lines.append(_basic_metric_line("dataforge_recycle_bin_total", len(recycle_bin_store)))

    backend_ok = 1
    try:
        repo = get_job_repository()
        backend = getattr(repo, "backend", "sqlite")
        lines.append(_basic_metric_line("dataforge_backend", 1, {"backend": backend}))
    except Exception as e:
        backend_ok = 0
        logging.getLogger(__name__).error("Metrics fallback: backend collection failed: %s", e)
    lines.append(_basic_metric_line("dataforge_backend_collection_ok", backend_ok))

    queue_ok = 1
    try:
        from app.worker_queue import get_worker_queue

        q_status = get_worker_queue().get_status()
        lines.append(_basic_metric_line("dataforge_queue_pending", q_status.get("pending", 0)))
        lines.append(_basic_metric_line("dataforge_queue_running", q_status.get("running", 0)))
        lines.append(_basic_metric_line("dataforge_queue_dead_letter", q_status.get("dead_letter", 0)))
    except Exception as e:
        queue_ok = 0
        logging.getLogger(__name__).error("Metrics fallback: queue collection failed: %s", e)
    lines.append(_basic_metric_line("dataforge_queue_collection_ok", queue_ok))

    for task_type, count in get_worker_failures().items():
        lines.append(_basic_metric_line("dataforge_worker_failures_total", count, {"task_type": task_type}))

    if settings.METRICS_ENABLE_HISTOGRAMS:
        request_latencies = get_request_latencies()
        if request_latencies:
            lines.append(_basic_metric_line("dataforge_request_duration_seconds_count", len(request_latencies)))
            lines.append(_basic_metric_line("dataforge_request_duration_seconds_sum", sum(request_latencies)))

        health_latencies = get_health_check_latencies()
        if health_latencies:
            lines.append(
                _basic_metric_line("dataforge_backend_health_check_duration_seconds_count", len(health_latencies))
            )
            lines.append(
                _basic_metric_line("dataforge_backend_health_check_duration_seconds_sum", sum(health_latencies))
            )

    lines.append(_basic_metric_line("dataforge_metrics_collection_error_total", METRICS_COLLECTION_ERRORS))

    errors_dict = get_errors()
    for err_type, count in errors_dict.items():
        lines.append(_basic_metric_line("dataforge_errors_total", count, {"type": err_type}))
    if "database" not in errors_dict:
        lines.append(_basic_metric_line("dataforge_errors_total", 0, {"type": "database"}))

    lines.append(_basic_metric_line("dataforge_llm_calls_total", get_llm_calls()))
    lines.append(_basic_metric_line("dataforge_requests_total", get_requests_total()))

    return "\n".join(lines) + "\n"


@app.get("/metrics")
async def metrics(request: Request):
    """Prometheus-formatted metrics endpoint for DataForge scraper.

    Exposes job counts, queue depth, runtime stats, request latencies,
    worker failure counts, and backend health check durations.

    Protected by METRICS_TOKEN if configured (Bearer token or X-API-Key).
    """
    # Auth check
    if settings.METRICS_TOKEN:
        auth_header = request.headers.get("Authorization", "")
        api_key_header = request.headers.get("X-API-Key", "")
        # Accept either Authorization: Bearer <token> or X-API-Key: <token>
        bearer_token = ""
        if auth_header.startswith("Bearer "):
            bearer_token = auth_header[7:]
        if not secrets.compare_digest(bearer_token, settings.METRICS_TOKEN) and not secrets.compare_digest(
            api_key_header, settings.METRICS_TOKEN
        ):
            return JSONResponse(
                status_code=403,
                content={
                    "detail": "Invalid or missing metrics token. Provide Authorization: Bearer <token> or X-API-Key header."
                },
            )

    global METRICS_COLLECTION_ERRORS
    try:
        from prometheus_client import generate_latest, Gauge, Histogram
    except ModuleNotFoundError:
        return Response(content=_render_basic_metrics_text(), media_type="text / plain")
    from prometheus_client.core import CollectorRegistry

    # Clear registry to avoid duplicate registration errors on hot-reload
    registry = CollectorRegistry()

    # ── Job counts by status ─────────────────────────────────────────────
    from app.models import JobStatus

    counts = {s.value: 0 for s in JobStatus}
    for job in jobs_store.values():
        status_key = str(job.status.value if isinstance(job.status, JobStatus) else job.status)
        counts[status_key] = counts.get(status_key, 0) + 1

    job_total = Gauge("dataforge_jobs_total", "Total jobs", ["status"], registry=registry)
    for status, count in counts.items():
        job_total.labels(status=status).set(count)

    # Recycle bin count
    recycle_gauge = Gauge("dataforge_recycle_bin_total", "Total jobs in recycle bin", registry=registry)
    recycle_gauge.set(len(recycle_bin_store))

    # Runtime limits
    for key, val in CONFIG.items():
        g = Gauge(f"dataforge_config_{key}", f"Config value for {key}", registry=registry)
        try:
            g.set(float(val))
        except (TypeError, ValueError):
            pass

    # ── Repository backend ──────────────────────────────────────────────
    backend_ok = 1
    try:
        repo = get_job_repository()
        backend = getattr(repo, "backend", "sqlite")
        backend_gauge = Gauge("dataforge_backend", "Storage backend type", ["backend"], registry=registry)
        backend_gauge.labels(backend=backend).set(1)
    except Exception as e:
        backend_ok = 0
        METRICS_COLLECTION_ERRORS += 1
        logging.getLogger(__name__).error("Metrics: backend collection failed: %s", e)

    backend_ok_gauge = Gauge(
        "dataforge_backend_collection_ok", "Whether storage backend metrics collected successfully", registry=registry
    )
    backend_ok_gauge.set(backend_ok)

    # ── Worker queue stats ──────────────────────────────────────────────
    queue_ok = 1
    try:
        from app.worker_queue import get_worker_queue

        q = get_worker_queue()
        q_status = q.get_status()
        queue_pending = Gauge("dataforge_queue_pending", "Pending tasks in worker queue", registry=registry)
        queue_pending.set(q_status.get("pending", 0))
        queue_running = Gauge("dataforge_queue_running", "Running tasks in worker queue", registry=registry)
        queue_running.set(q_status.get("running", 0))
        queue_dead_letter = Gauge("dataforge_queue_dead_letter", "Dead letter queue size", registry=registry)
        queue_dead_letter.set(q_status.get("dead_letter", 0))
    except Exception as e:
        queue_ok = 0
        METRICS_COLLECTION_ERRORS += 1
        logging.getLogger(__name__).error("Metrics: queue collection failed: %s", e)

    queue_ok_gauge = Gauge(
        "dataforge_queue_collection_ok", "Whether worker queue metrics collected successfully", registry=registry
    )
    queue_ok_gauge.set(queue_ok)

    # ── Worker failure counters ─────────────────────────────────────────
    from app.metrics_collector import get_worker_failures

    failures = get_worker_failures()
    if failures:
        failure_gauge = Gauge(
            "dataforge_worker_failures_total", "Total worker failures by task type", ["task_type"], registry=registry
        )
        for task_type, count in failures.items():
            failure_gauge.labels(task_type=task_type).set(count)

    # ── Request duration histogram ──────────────────────────────────────
    from app.metrics_collector import get_request_latencies, get_health_check_latencies

    if settings.METRICS_ENABLE_HISTOGRAMS:
        req_latencies = get_request_latencies()
        if req_latencies:
            buckets = [float(b.strip()) for b in settings.METRICS_HISTOGRAM_BUCKETS.split(",") if b.strip()]
            req_hist = Histogram(
                "dataforge_request_duration_seconds",
                "API request duration in seconds",
                buckets=buckets,
                registry=registry,
            )
            for v in req_latencies:
                req_hist.observe(v)

    # ── Backend health check latency histogram ──────────────────────────
    if settings.METRICS_ENABLE_HISTOGRAMS:
        health_latencies = get_health_check_latencies()
        if health_latencies:
            buckets = [float(b.strip()) for b in settings.METRICS_HISTOGRAM_BUCKETS.split(",") if b.strip()]
            health_hist = Histogram(
                "dataforge_backend_health_check_duration_seconds",
                "Backend health check duration in seconds",
                buckets=buckets,
                registry=registry,
            )
            for v in health_latencies:
                health_hist.observe(v)

    # ── Cumulative collection errors ────────────────────────────────────
    error_total_gauge = Gauge(
        "dataforge_metrics_collection_error_total", "Total collection errors encountered", registry=registry
    )
    error_total_gauge.set(METRICS_COLLECTION_ERRORS)

    # ── Cumulative error counts by type (database, scraper, etc.) ───────
    from app.metrics_collector import get_errors, get_llm_calls, get_requests_total

    errors_dict = get_errors()
    errors_gauge = Gauge("dataforge_errors_total", "Cumulative error count by type", ["type"], registry=registry)
    for err_type, count in errors_dict.items():
        errors_gauge.labels(type=err_type).set(count)
    if "database" not in errors_dict:
        errors_gauge.labels(type="database").set(0)

    # ── Cumulative LLM calls count ──────────────────────────────────────
    llm_gauge = Gauge("dataforge_llm_calls_total", "Cumulative LLM calls count", registry=registry)
    llm_gauge.set(get_llm_calls())

    # ── Cumulative requests count ───────────────────────────────────────
    requests_gauge = Gauge("dataforge_requests_total", "Total requests count", registry=registry)
    requests_gauge.set(get_requests_total())

    return Response(content=generate_latest(registry), media_type="text / plain")


# ─── Serve Frontend (must be AFTER all API route definitions) ────────────
FRONTEND_DIR = Path(__file__).parent.parent.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/app", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
    DASHBOARD_DIR = FRONTEND_DIR / "dashboard"
    if DASHBOARD_DIR.exists():
        app.mount("/dashboard", StaticFiles(directory=str(DASHBOARD_DIR), html=True), name="dashboard")

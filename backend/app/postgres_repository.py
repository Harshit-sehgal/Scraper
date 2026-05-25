"""Production-grade Postgres-backed JobRepository implementation.

Provides:
- Connection pooling via asyncpg
- Schema auto-migration
- Transactional batch writes
- Same interface as SQLiteJobRepository (via JobRepository ABC)
- Configurable via DATAFORGE_DATABASE_URL env var

Usage:
    repo = PostgresJobRepository()
    jobs, recycle, ws = await repo.load_all()
    await repo.save_all(jobs, recycle)
"""

import asyncio
import datetime
import json
import logging
import os
from typing import Optional

from app.models import Job, JobStatus
from app.storage_interface import JobRepository

logger = logging.getLogger(__name__)

_CURRENT_SCHEMA_VERSION = 1


def _get_database_url() -> str:
    """Resolve the Postgres DSN from environment or settings."""
    url = os.getenv("DATAFORGE_DATABASE_URL", "").strip()
    if url:
        return url
    try:
        from app.config import settings
        url = getattr(settings, "DATABASE_URL", "")
    except Exception:
        pass
    if url:
        return url
    # Sensible local default for development
    return "postgresql://dataforge:dataforge@localhost:5432/dataforge"


def _job_to_row(job: Job) -> dict:
    """Convert a Job model to a flat row dict for Postgres storage."""
    return {
        "id": job.id,
        "name": job.name,
        "status": job.status.value if hasattr(job.status, "value") else str(job.status),
        "mode": job.mode.value if hasattr(job.mode, "value") else str(job.mode),
        "topic": job.topic or "",
        "intent": job.intent or "",
        "urls": json.dumps(job.urls or []),
        "schema_fields": json.dumps(
            [f.model_dump() if hasattr(f, "model_dump") else f for f in (job.schema_fields or [])]
        ),
        "filters": json.dumps(
            [f.model_dump() if hasattr(f, "model_dump") else f for f in (job.filters or [])]
        ) if hasattr(job, "filters") else "[]",
        "results": json.dumps(job.results or []),
        "logs": json.dumps(
            [log.model_dump() if hasattr(log, "model_dump") else log for log in (job.logs or [])]
        ),
        "total_records": job.total_records or 0,
        "filtered_records": job.filtered_records or 0,
        "total_llm_calls": job.total_llm_calls or 0,
        "error": job.error if job.error is not None else "",
        "warnings": json.dumps(job.warnings or []),
        "quality_report": json.dumps(job.quality_report if hasattr(job, "quality_report") else {}),
        "analysis": job.analysis if job.analysis is not None else "",
        "discovered_urls": json.dumps(job.discovered_urls if hasattr(job, "discovered_urls") else []),
        "selectors_map": json.dumps(job.selectors_map if hasattr(job, "selectors_map") else {}),
        "search_params": json.dumps(
            job.search_params if hasattr(job, "search_params") and job.search_params is not None else {}
        ),
        "max_pages": job.max_pages if hasattr(job, "max_pages") else 0,
        "progress_current": job.progress_current or 0,
        "progress_total": job.progress_total or 0,
        "estimated_cost_usd": job.estimated_cost_usd or 0,
        "cancel_requested": job.cancel_requested,
        "created_at": job.created_at or "",
        "completed_at": job.completed_at if job.completed_at is not None else "",
        "min_record_score": job.min_record_score if job.min_record_score is not None else 0.35,
        "acquisition_mode": (
            getattr(job.acquisition_mode, "value")
            if hasattr(job.acquisition_mode, "value")
            else str(job.acquisition_mode or "standard")
        ),
        "location": job.location or "",
        "preferred_domain": job.preferred_domain or "",
        "source_policy": job.source_policy.value
        if hasattr(job.source_policy, "value")
        else str(job.source_policy),
        "max_per_domain": job.max_per_domain or 4,
        "origin_location": job.origin_location or "",
        "max_distance_km": job.max_distance_km,
        "pagination": job.pagination,
        "deduplicate": job.deduplicate,
        "deduplicate_field": job.deduplicate_field or "",
        "started_at": job.started_at if job.started_at is not None else "",
        "results_on_disk": job.results_on_disk,
        "results_file_path": job.results_file_path if job.results_file_path is not None else "",
        "updated_at": datetime.datetime.now().isoformat(),
    }


def _row_to_job(row: dict) -> Optional[Job]:
    """Convert a Postgres row dict back to a Job model."""
    try:
        from app.models import SourcePolicy

        source_policy_str = row.get("source_policy", "all_sources")
        try:
            sp = SourcePolicy(source_policy_str)
        except Exception:
            sp = SourcePolicy.ALL_SOURCES

        return Job.model_validate({
            "id": row["id"],
            "name": row["name"],
            "status": row["status"],
            "mode": row.get("mode", "manual"),
            "topic": row.get("topic", ""),
            "intent": row.get("intent", ""),
            "urls": json.loads(row.get("urls", "[]")),
            "schema_fields": json.loads(row.get("schema_fields", "[]")),
            "filters": json.loads(row.get("filters", "[]")),
            "results": json.loads(row.get("results", "[]")),
            "logs": json.loads(row.get("logs", "[]")),
            "total_records": row.get("total_records", 0),
            "filtered_records": row.get("filtered_records", 0),
            "total_llm_calls": row.get("total_llm_calls", 0),
            "error": row.get("error") or None,
            "quality_report": json.loads(row.get("quality_report", "{}")),
            "analysis": row.get("analysis") or None,
            "discovered_urls": json.loads(row.get("discovered_urls", "[]")),
            "selectors_map": json.loads(row.get("selectors_map", "{}")),
            "search_params": json.loads(row.get("search_params", "{}")) or None,
            "max_pages": row.get("max_pages", 0),
            "progress_current": row.get("progress_current", 0),
            "progress_total": row.get("progress_total", 0),
            "estimated_cost_usd": row.get("estimated_cost_usd", 0),
            "cancel_requested": bool(row.get("cancel_requested", False)),
            "created_at": row.get("created_at", ""),
            "completed_at": row.get("completed_at") or None,
            "min_record_score": row.get("min_record_score", 0.35),
            "location": row.get("location", ""),
            "preferred_domain": row.get("preferred_domain", ""),
            "source_policy": sp,
            "max_per_domain": row.get("max_per_domain", 4),
            "origin_location": row.get("origin_location", ""),
            "max_distance_km": row.get("max_distance_km"),
            "pagination": bool(row.get("pagination", False)),
            "deduplicate": bool(row.get("deduplicate", True)),
            "deduplicate_field": row.get("deduplicate_field", ""),
            "started_at": row.get("started_at") if row.get("started_at") else None,
            "results_on_disk": bool(row.get("results_on_disk", False)),
            "results_file_path": row.get("results_file_path") if row.get("results_file_path") else None,
            "warnings": json.loads(row.get("warnings", "[]")),
            "acquisition_mode": row.get("acquisition_mode", "standard"),
        })
    except Exception as e:
        logger.warning("Failed to deserialize Postgres job row: %s", e)
        return None


# ───────────────────────────────────────────────────────────────────────
# Connection pool singleton
# ───────────────────────────────────────────────────────────────────────

_pool = None
_pool_lock = asyncio.Lock()


async def _get_pool():
    """Get or create the asyncpg connection pool."""
    global _pool
    if _pool is None:
        async with _pool_lock:
            if _pool is None:
                import asyncpg
                dsn = _get_database_url()
                _pool = await asyncpg.create_pool(
                    dsn=dsn,
                    min_size=2,
                    max_size=10,
                    command_timeout=30,
                )
                logger.info("Created asyncpg pool for %s", dsn.split("@")[-1] if "@" in dsn else dsn)
    return _pool


async def _close_pool():
    """Close the connection pool."""
    global _pool
    if _pool is not None:
        pool = _pool
        _pool = None
        await pool.close()
        logger.info("Closed asyncpg pool")


# ───────────────────────────────────────────────────────────────────────
# Schema management
# ───────────────────────────────────────────────────────────────────────

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    mode TEXT NOT NULL DEFAULT 'manual',
    topic TEXT DEFAULT '',
    intent TEXT DEFAULT '',
    urls TEXT NOT NULL DEFAULT '[]',
    schema_fields TEXT NOT NULL DEFAULT '[]',
    filters TEXT DEFAULT '[]',
    results TEXT DEFAULT '[]',
    logs TEXT DEFAULT '[]',
    total_records INTEGER DEFAULT 0,
    filtered_records INTEGER DEFAULT 0,
    total_llm_calls INTEGER DEFAULT 0,
    error TEXT DEFAULT '',
    warnings TEXT DEFAULT '',
    quality_report TEXT DEFAULT '{}',
    analysis TEXT DEFAULT '',
    discovered_urls TEXT DEFAULT '[]',
    selectors_map TEXT DEFAULT '{}',
    search_params TEXT DEFAULT '{}',
    max_pages INTEGER DEFAULT 0,
    progress_current INTEGER DEFAULT 0,
    progress_total INTEGER DEFAULT 0,
    estimated_cost_usd REAL DEFAULT 0,
    cancel_requested BOOLEAN DEFAULT FALSE,
    created_at TEXT DEFAULT '',
    completed_at TEXT DEFAULT '',
    min_record_score REAL DEFAULT 0.35,
    acquisition_mode TEXT DEFAULT 'standard',
    location TEXT DEFAULT '',
    preferred_domain TEXT DEFAULT '',
    source_policy TEXT DEFAULT 'all_sources',
    max_per_domain INTEGER DEFAULT 4,
    origin_location TEXT DEFAULT '',
    max_distance_km REAL DEFAULT NULL,
    pagination BOOLEAN DEFAULT FALSE,
    deduplicate BOOLEAN DEFAULT TRUE,
    deduplicate_field TEXT DEFAULT '',
    started_at TEXT DEFAULT '',
    results_on_disk BOOLEAN DEFAULT FALSE,
    results_file_path TEXT DEFAULT '',
    updated_at TEXT DEFAULT '',
    deleted_at TEXT DEFAULT NULL
);

CREATE TABLE IF NOT EXISTS recycle_bin (
    LIKE jobs INCLUDING ALL
);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_recycle_bin_created_at ON recycle_bin(created_at DESC);
"""


async def _ensure_schema():
    """Run schema migrations to ensure tables exist and are up to date."""
    pool = await _get_pool()
    async with pool.acquire() as conn:
        # Create schema_version table if missing
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY
            )
        """)
        row = await conn.fetchrow("SELECT MAX(version) FROM schema_version")
        current = row[0] if row and row[0] is not None else 0

        if current < _CURRENT_SCHEMA_VERSION:
            if current < 1:
                # Create jobs table
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS jobs (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'pending'
                    )
                """)
                # Add all columns — we use a single migration for v1
                columns = [
                    "mode TEXT DEFAULT 'manual'",
                    "topic TEXT DEFAULT ''",
                    "intent TEXT DEFAULT ''",
                    "urls TEXT DEFAULT '[]'",
                    "schema_fields TEXT DEFAULT '[]'",
                    "filters TEXT DEFAULT '[]'",
                    "results TEXT DEFAULT '[]'",
                    "logs TEXT DEFAULT '[]'",
                    "total_records INTEGER DEFAULT 0",
                    "filtered_records INTEGER DEFAULT 0",
                    "total_llm_calls INTEGER DEFAULT 0",
                    "error TEXT DEFAULT ''",
                    "warnings TEXT DEFAULT ''",
                    "quality_report TEXT DEFAULT '{}'",
                    "analysis TEXT DEFAULT ''",
                    "discovered_urls TEXT DEFAULT '[]'",
                    "selectors_map TEXT DEFAULT '{}'",
                    "search_params TEXT DEFAULT '{}'",
                    "max_pages INTEGER DEFAULT 0",
                    "progress_current INTEGER DEFAULT 0",
                    "progress_total INTEGER DEFAULT 0",
                    "estimated_cost_usd REAL DEFAULT 0",
                    "cancel_requested BOOLEAN DEFAULT FALSE",
                    "created_at TEXT DEFAULT ''",
                    "completed_at TEXT DEFAULT ''",
                    "min_record_score REAL DEFAULT 0.35",
                    "acquisition_mode TEXT DEFAULT 'standard'",
                    "location TEXT DEFAULT ''",
                    "preferred_domain TEXT DEFAULT ''",
                    "source_policy TEXT DEFAULT 'all_sources'",
                    "max_per_domain INTEGER DEFAULT 4",
                    "origin_location TEXT DEFAULT ''",
                    "max_distance_km REAL DEFAULT NULL",
                    "pagination BOOLEAN DEFAULT FALSE",
                    "deduplicate BOOLEAN DEFAULT TRUE",
                    "deduplicate_field TEXT DEFAULT ''",
                    "started_at TEXT DEFAULT ''",
                    "results_on_disk BOOLEAN DEFAULT FALSE",
                    "results_file_path TEXT DEFAULT ''",
                    "updated_at TEXT DEFAULT ''",
                    "deleted_at TEXT DEFAULT NULL",
                ]
                for col_def in columns:
                    try:
                        await conn.execute(f"ALTER TABLE jobs ADD COLUMN IF NOT EXISTS {col_def}")
                    except Exception:
                        # Column may already exist — ignore
                        pass

                # Create recycle_bin with same schema
                try:
                    await conn.execute("""
                        CREATE TABLE IF NOT EXISTS recycle_bin (
                            LIKE jobs INCLUDING ALL
                        )
                    """)
                except Exception:
                    # Fallback: create recycle_bin manually
                    await conn.execute("""
                        CREATE TABLE IF NOT EXISTS recycle_bin (
                            id TEXT PRIMARY KEY,
                            name TEXT NOT NULL,
                            status TEXT NOT NULL DEFAULT 'pending',
                            mode TEXT DEFAULT 'manual',
                            topic TEXT DEFAULT '',
                            intent TEXT DEFAULT '',
                            urls TEXT DEFAULT '[]',
                            schema_fields TEXT DEFAULT '[]',
                            filters TEXT DEFAULT '[]',
                            results TEXT DEFAULT '[]',
                            logs TEXT DEFAULT '[]',
                            total_records INTEGER DEFAULT 0,
                            filtered_records INTEGER DEFAULT 0,
                            total_llm_calls INTEGER DEFAULT 0,
                            error TEXT DEFAULT '',
                            warnings TEXT DEFAULT '',
                            quality_report TEXT DEFAULT '{}',
                            analysis TEXT DEFAULT '',
                            discovered_urls TEXT DEFAULT '[]',
                            selectors_map TEXT DEFAULT '{}',
                            search_params TEXT DEFAULT '{}',
                            max_pages INTEGER DEFAULT 0,
                            progress_current INTEGER DEFAULT 0,
                            progress_total INTEGER DEFAULT 0,
                            estimated_cost_usd REAL DEFAULT 0,
                            cancel_requested BOOLEAN DEFAULT FALSE,
                            created_at TEXT DEFAULT '',
                            completed_at TEXT DEFAULT '',
                            min_record_score REAL DEFAULT 0.35,
                            acquisition_mode TEXT DEFAULT 'standard',
                            deleted_at TEXT DEFAULT ''
                        )
                    """)

                # Create indexes
                for idx_sql in [
                    "CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)",
                    "CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at DESC)",
                    "CREATE INDEX IF NOT EXISTS idx_recycle_bin_created_at ON recycle_bin(created_at DESC)",
                ]:
                    try:
                        await conn.execute(idx_sql)
                    except Exception:
                        pass

            await conn.execute("DELETE FROM schema_version")
            await conn.execute("INSERT INTO schema_version (version) VALUES ($1)", _CURRENT_SCHEMA_VERSION)
            logger.info("Postgres schema migrated to version %d", _CURRENT_SCHEMA_VERSION)


# ───────────────────────────────────────────────────────────────────────
# Repository implementation
# ───────────────────────────────────────────────────────────────────────


class PostgresJobRepository(JobRepository):
    """Production-grade Postgres-backed JobRepository.

    Uses asyncpg for async connection pooling and transactional safety.
    Falls back gracefully if Postgres is unavailable (use SQLiteRepository instead).
    """

    def __init__(self, auto_ensure_schema: bool = True):
        self._auto_ensure_schema = auto_ensure_schema
        self._schema_ensured = False

    async def _ensure(self):
        if self._auto_ensure_schema and not self._schema_ensured:
            await _ensure_schema()
            self._schema_ensured = True

    # ─── Sync-compatible wrappers (for legacy callers) ─────────────────

    def load_jobs(self) -> dict[str, Job]:
        return self._run_async(self._load_jobs_impl())

    def load_recycle_bin(self) -> dict[str, Job]:
        return self._run_async(self._load_recycle_bin_impl())

    def load_all(self) -> tuple[dict[str, Job], dict[str, Job], Optional[dict]]:
        return self._run_async(self._load_all_impl())

    def save_all(self, jobs: dict[str, Job], recycle_bin: dict[str, Job]) -> None:
        self._run_async(self._save_all_impl(jobs, recycle_bin))

    def save_single(self, job: Job) -> None:
        self._run_async(self._save_single_impl(job))

    @staticmethod
    def _run_async(coro):
        """Run an async coroutine synchronously (for callers that expect sync)."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # We're inside an async context — create a new task
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(asyncio.run, coro)
                    return future.result()
            else:
                return asyncio.run(coro)
        except RuntimeError:
            return asyncio.run(coro)

    # ─── Async implementations ─────────────────────────────────────────

    async def _load_jobs_impl(self) -> dict[str, Job]:
        await self._ensure()
        pool = await _get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM jobs WHERE deleted_at IS NULL")
            jobs: dict[str, Job] = {}
            for row in rows:
                job = _row_to_job(dict(row))
                if job:
                    jobs[job.id] = job
            return jobs

    async def _load_recycle_bin_impl(self) -> dict[str, Job]:
        await self._ensure()
        pool = await _get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM recycle_bin")
            jobs: dict[str, Job] = {}
            for row in rows:
                job = _row_to_job(dict(row))
                if job:
                    jobs[job.id] = job
            return jobs

    async def _load_all_impl(self) -> tuple[dict[str, Job], dict[str, Job], Optional[dict]]:
        await self._ensure()
        pool = await _get_pool()
        async with pool.acquire() as conn:
            # Load jobs
            job_rows = await conn.fetch("SELECT * FROM jobs WHERE deleted_at IS NULL")
            jobs_store: dict[str, Job] = {}
            for row in job_rows:
                job = _row_to_job(dict(row))
                if job:
                    jobs_store[job.id] = job

            # Recover in-progress jobs (same as SQLite behavior)
            now_iso = datetime.datetime.now().isoformat()
            dirty_ids = []
            for job in list(jobs_store.values()):
                if job.status in {JobStatus.PENDING, JobStatus.DISCOVERING, JobStatus.RUNNING}:
                    job.status = JobStatus.FAILED
                    job.error = "Recovered after restart while still in progress."
                    job.completed_at = now_iso
                    job.cancel_requested = False
                    dirty_ids.append(job.id)

            # Persist recovery to DB — do not rely on in-memory-only changes
            if dirty_ids:
                await conn.execute(
                    """UPDATE jobs
                       SET status = 'failed',
                           error = 'Recovered after restart while still in progress.',
                           completed_at = $1,
                           cancel_requested = FALSE
                       WHERE id = ANY($2::text[])""",
                    now_iso, dirty_ids,
                )
                logger.info("Recovered %d in-progress job(s) in Postgres", len(dirty_ids))

            # Load recycle bin
            recycle_rows = await conn.fetch("SELECT * FROM recycle_bin")
            recycle_store: dict[str, Job] = {}
            for row in recycle_rows:
                job = _row_to_job(dict(row))
                if job:
                    recycle_store[job.id] = job

            world_state_data = None
            return jobs_store, recycle_store, world_state_data

    async def _save_all_impl(self, jobs: dict[str, Job], recycle_bin: dict[str, Job]) -> None:
        await self._ensure()
        pool = await _get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                # Clear and re-insert jobs
                await conn.execute("DELETE FROM jobs WHERE deleted_at IS NULL")
                for job in jobs.values():
                    row = _job_to_row(job)
                    cols = ", ".join(row.keys())
                    ph = ", ".join(f"${i+1}" for i in range(len(row)))
                    await conn.execute(
                        f"INSERT INTO jobs ({cols}) VALUES ({ph}) ON CONFLICT (id) DO UPDATE SET updated_at = EXCLUDED.updated_at",
                        *row.values(),
                    )

                # Clear and re-insert recycle bin
                await conn.execute("DELETE FROM recycle_bin")
                for job in recycle_bin.values():
                    row = _job_to_row(job)
                    row["deleted_at"] = datetime.datetime.now().isoformat()
                    cols = ", ".join(row.keys())
                    ph = ", ".join(f"${i+1}" for i in range(len(row)))
                    await conn.execute(
                        f"INSERT INTO recycle_bin ({cols}) VALUES ({ph}) ON CONFLICT (id) DO NOTHING",
                        *row.values(),
                    )

    async def _save_single_impl(self, job: Job) -> None:
        await self._ensure()
        pool = await _get_pool()
        async with pool.acquire() as conn:
            row = _job_to_row(job)
            cols = ", ".join(row.keys())
            ph = ", ".join(f"${i+1}" for i in range(len(row)))
            update_cols = ", ".join(f"{k} = EXCLUDED.{k}" for k in row.keys() if k != "id")
            await conn.execute(
                f"INSERT INTO jobs ({cols}) VALUES ({ph}) ON CONFLICT (id) DO UPDATE SET {update_cols}",
                *row.values(),
            )

    async def health_check(self) -> dict:
        """Check Postgres connectivity and schema health."""
        try:
            pool = await _get_pool()
            async with pool.acquire() as conn:
                version = await conn.fetchval("SELECT MAX(version) FROM schema_version")
                job_count = await conn.fetchval("SELECT COUNT(*) FROM jobs WHERE deleted_at IS NULL")
                recycle_count = await conn.fetchval("SELECT COUNT(*) FROM recycle_bin")
                return {
                    "ok": True,
                    "backend": "postgres",
                    "schema_version": version or 0,
                    "expected_version": _CURRENT_SCHEMA_VERSION,
                    "job_count": job_count or 0,
                    "recycle_bin_count": recycle_count or 0,
                }
        except Exception as e:
            logger.error("Postgres health check failed: %s", e)
            return {
                "ok": False,
                "backend": "postgres",
                "error": str(e),
                "schema_version": 0,
                "expected_version": _CURRENT_SCHEMA_VERSION,
            }


async def create_postgres_repository() -> PostgresJobRepository:
    """Factory: create and return a ready-to-use PostgresJobRepository."""
    repo = PostgresJobRepository()
    await repo._ensure()
    return repo


async def shutdown_postgres():
    """Close the Postgres connection pool."""
    await _close_pool()


def verify_postgres_connectivity() -> dict:
    """Synchronously verify Postgres is reachable before activating the repository.

    Uses a standalone connection (not the shared pool) so the pool is
    never leaked on failure or left open if the caller falls back to SQLite.

    Returns a dict with 'ok': True/False and optional 'error' message.
    Used by the repository factory (get_job_repository) at startup.
    """
    try:
        dsn = _get_database_url()
        import asyncpg

        def _probe() -> bool:
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                conn = loop.run_until_complete(asyncpg.connect(dsn=dsn, timeout=10))
                try:
                    val = loop.run_until_complete(conn.fetchval("SELECT 1"))
                    return val == 1
                finally:
                    loop.run_until_complete(conn.close())
            finally:
                loop.close()

        ok = _probe()
        return {"ok": ok} if ok else {"ok": False, "error": "Postgres SELECT 1 returned unexpected result"}
    except ImportError as e:
        return {"ok": False, "error": f"asyncpg not installed: {e}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

"""Write/mutation job routes — ``POST/DELETE`` endpoints for jobs and recycle bin.

Extracted from ``routers/jobs.py`` during the router refactoring to separate
mutation routes from read-only routes.

All routes are registered by ``register_jobs_write_routes(router, manager, ...)``
which is called from ``app.routers.jobs.create_jobs_router``.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import re
from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.discovery import (
    DiscoveryDependencyError,
    discover_urls,
    infer_source_metadata,
)
from app.filters import process_results
from app.models import (
    DiscoveryRequest,
    Job,
    JobCreate,
    JobStatus,
    SchemaSuggestionRequest,
    ScrapeMode,
)
from app.routers.jobs_state import (
    JobStoreManager,
    lookup_idempotency_fingerprint,
    lookup_idempotency_key,
    record_idempotency_key,
    save_job,
)
from app.scraper import ai_clean_and_align_records
from app.storage_interface import get_job_repository
from app.utils.job import deduplicate_results, mark_job_canceled, normalize_job_results
from app.utils.quality import build_quality_report, compute_source_breakdown, safe_score
from app.utils.rbac import UserRole, require_role

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)


def register_jobs_write_routes(
    router: APIRouter,
    manager: JobStoreManager,
    schedule_task_fn: Callable,
    run_job_coro_fn: Callable,
) -> None:
    """Register all write/mutation job endpoints on the given router.

    Args:
        router: The APIRouter to register routes on.
        manager: Thread-safe store manager for jobs and recycle bin.
        schedule_task_fn: Callable to schedule a background task (fires-and-forgets a coroutine).
        run_job_coro_fn: Callable that returns a coroutine to run a job by ID.
    """

    @router.post("/api/discover")
    async def discover(
        req: DiscoveryRequest,
        _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR]))],
    ):
        """Auto-discover best URLs to scrape for a topic."""
        try:
            results = await discover_urls(
                query=req.topic,
                domain=req.domain,
                num_results=req.num_results,
                location=req.location,
                data_fields=req.schema_field_names,
                origin_location=req.origin_location,
                max_distance_km=req.max_distance_km,
                source_policy=req.source_policy,
                max_per_domain=req.max_per_domain,
            )
        except DiscoveryDependencyError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        from app.url_safety import validate_public_http_url

        safe_results = []
        for r in results:
            url = r.get("url")
            if url:
                try:
                    validate_public_http_url(url)
                    safe_results.append(r)
                except ValueError:
                    pass  # nosec B110
        return {"urls": safe_results}

    @router.post("/api/schema/suggest")
    async def suggest_schema(
        req: SchemaSuggestionRequest,
        _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR]))],
    ):
        """Infer topic + schema fields from plain-language user intent."""
        from app.insight_engine import suggest_schema_from_intent  # research-shell, lazy

        return await suggest_schema_from_intent(req.intent, max_fields=req.max_fields)

    @router.post("/api/jobs")
    async def create_job(
        job_data: JobCreate,
        request: Request,
        _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR]))],
    ):
        manual_urls = [u.strip() for u in job_data.urls if str(u or "").strip()]
        urls = manual_urls if job_data.mode == ScrapeMode.MANUAL else []

        # Defence-in-depth: reject SSRF targets in manual URLs (loopback,
        # private RFC1918, link-local, cloud-metadata, internal TLDs)
        # BEFORE persisting the job. Mirrors the same guard on
        # /api/scraper/diagnostics so a manual-mode operator cannot pivot
        # to internal services via the job queue.
        from app.url_safety import validate_public_http_url

        safe_urls: list[str] = []
        for u in manual_urls:
            try:
                validate_public_http_url(u)
                safe_urls.append(u)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"URL failed security validation: {u}",
                ) from None
        urls = safe_urls if job_data.mode == ScrapeMode.MANUAL else []

        idem_key = (request.headers.get("Idempotency-Key") or "").strip()
        if idem_key and not re.fullmatch(r"[A-Za-z0-9_\-]{1,128}", idem_key):
            raise HTTPException(
                status_code=400,
                detail=(
                    "Idempotency-Key header is invalid. Allowed characters: letters, digits, underscore, hyphen. Max length: 128."
                ),
            )
        if idem_key:
            existing_job_id = await run_in_threadpool(
                lookup_idempotency_key,
                idem_key,
            )
            if existing_job_id is not None:
                existing_fingerprint = await run_in_threadpool(
                    lookup_idempotency_fingerprint,
                    idem_key,
                )
                if (
                    existing_fingerprint is not None
                    and existing_fingerprint != f"{job_data.mode.value}:{job_data.name}:{','.join(manual_urls)}"
                ):
                    raise HTTPException(
                        status_code=409,
                        detail="Conflict: Another request with a different payload was already sent for this Idempotency-Key.",
                    )

                cached = manager.jobs_store.get(existing_job_id)
                if cached is not None:
                    return {
                        "job_id": cached.id,
                        "status": cached.status.value,
                        "idempotent_replay": True,
                    }
                return {
                    "job_id": existing_job_id,
                    "status": "unknown",
                    "idempotent_replay": True,
                }

        job = Job(
            name=job_data.name,
            mode=job_data.mode,
            intent=job_data.intent,
            urls=urls,
            topic=job_data.topic,
            location=job_data.location,
            preferred_domain=job_data.preferred_domain,
            source_policy=job_data.source_policy,
            max_per_domain=job_data.max_per_domain,
            origin_location=job_data.origin_location,
            max_distance_km=job_data.max_distance_km,
            schema_fields=job_data.schema_fields,
            filters=job_data.filters,
            selectors_map=job_data.selectors_map,
            search_params=job_data.search_params,
            pagination=job_data.pagination,
            max_pages=job_data.max_pages,
            deduplicate=job_data.deduplicate,
            deduplicate_field=job_data.deduplicate_field,
            min_record_score=job_data.min_record_score,
        )
        manager.jobs_store[job.id] = job
        await save_job(job)

        if idem_key:
            fingerprint = f"{job_data.mode.value}:{job_data.name}:{','.join(manual_urls)}"
            await run_in_threadpool(
                record_idempotency_key,
                idem_key,
                job.id,
                fingerprint,
            )

        if settings.WORKER_QUEUE:
            try:
                from app.worker_queue import Priority, get_worker_queue

                queue = get_worker_queue()
                task_id = await queue.enqueue(
                    task_type="scrape_job",
                    payload={"job_id": job.id},
                    priority=Priority.NORMAL,
                    task_id=job.id,
                )
                logger.info("Job %s enqueued to worker queue (task=%s)", job.id, task_id)
            except Exception as e:
                if settings.ENV.lower() == "production":
                    logger.exception(
                        "Failed to enqueue job %s to worker queue in production",
                        job.id,
                    )
                    if job.id in manager.jobs_store:
                        del manager.jobs_store[job.id]
                    try:
                        repo = get_job_repository()
                        repo.hard_delete(job.id)
                    except (AttributeError, ImportError, RuntimeError):
                        logger.warning("Failed to hard-delete job %s after enqueue failure", job.id)
                    raise HTTPException(
                        status_code=503,
                        detail=(
                            f"Failed to enqueue job {job.id} to worker queue. "
                            "Inline fallback is disabled in production. "
                            "Check that the worker queue is running and healthy."
                        ),
                    ) from None
                logger.warning(
                    "Failed to enqueue job %s to worker queue, falling back to inline: %s",
                    job.id,
                    e,
                )
                schedule_task_fn(run_job_coro_fn(job.id))
        else:
            schedule_task_fn(run_job_coro_fn(job.id))

        return {
            "job_id": job.id,
            "status": job.status.value,
            "idempotent_replay": False,
        }

    @router.post("/api/jobs/{job_id}/cancel")
    async def cancel_job(
        job_id: str,
        _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR]))],
    ):
        with manager.lock:
            if job_id not in manager.jobs_store:
                raise HTTPException(status_code=404, detail="Job not found")
            job = manager.jobs_store[job_id]
            if job.status in {
                JobStatus.COMPLETED,
                JobStatus.DEGRADED,
                JobStatus.EMPTY_RESULT,
                JobStatus.FAILED,
                JobStatus.CANCELED,
            }:
                return {
                    "job_id": job.id,
                    "status": job.status.value,
                    "cancel_requested": bool(job.cancel_requested),
                    "message": "Job already in terminal state",
                }

            job.cancel_requested = True
            if job.status == JobStatus.PENDING:
                mark_job_canceled(job, "Canceled before execution.")

        if settings.WORKER_QUEUE:
            try:
                from app.worker_queue import get_worker_queue

                queue = get_worker_queue()
                await queue.cancel(job_id)
            except Exception as e:
                logger.warning(
                    "Failed to cancel queued task for job %s: %s",
                    job_id,
                    e,
                )

        await save_job(job)
        return {
            "job_id": job.id,
            "status": job.status.value,
            "cancel_requested": True,
            "cancel_queued_task": True,
            "message": "Cancellation requested",
        }

    @router.post("/api/jobs/{job_id}/backfill-metadata")
    async def backfill_job_metadata(
        job_id: str,
        _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR]))],
    ):
        """Explicitly backfill source metadata for manual-mode job results."""
        job = await run_in_threadpool(manager.get_job, job_id)

        results_list = list(job.results)
        if job.results_on_disk:
            from app.utils.job_results_store import load_job_results_from_disk

            results_list = await run_in_threadpool(load_job_results_from_disk, job.id, job.results_file_path)

        updated = False
        for row in results_list:
            source_url = str(row.get("source_url") or "")
            source_type = str(row.get("source_type") or "unknown").strip().lower()
            if source_type == "unknown" and source_url:
                inferred = infer_source_metadata(url=source_url)
                row["source_type"] = str(inferred.get("source_type") or "unknown")
                row["source_trust_score"] = round(safe_score(inferred.get("source_trust_score") or 0.4), 3)
                updated = True

        if updated:
            job.results = results_list
            if job.results_on_disk:
                from app.utils.job_results_store import save_job_results_to_disk

                await run_in_threadpool(save_job_results_to_disk, job.id, results_list)
            await save_job(job)

        return {"message": "Metadata backfilled successfully", "updated": updated}

    @router.post("/api/jobs/{job_id}/reclean")
    async def reclean_job(
        job_id: str,
        _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR]))],
    ):
        """Re-run AI cleaning and schema alignment on existing job results without re-scraping URLs."""
        with manager.lock:
            if job_id not in manager.jobs_store:
                raise HTTPException(status_code=404, detail="Job not found")
            job = manager.jobs_store[job_id]
            if job.status in {JobStatus.PENDING, JobStatus.DISCOVERING, JobStatus.RUNNING}:
                raise HTTPException(
                    status_code=409,
                    detail="Job is still running; wait for completion before re-cleaning",
                )

        results_list = list(job.results)
        loaded_from_disk = False
        if job.results_on_disk:
            from app.utils.job_results_store import load_job_results_from_disk

            results_list = await run_in_threadpool(load_job_results_from_disk, job.id, job.results_file_path)
            loaded_from_disk = True

        if not results_list:
            raise HTTPException(status_code=400, detail="No results to re-clean")
        if not job.schema_fields:
            raise HTTPException(status_code=400, detail="Job has no schema fields for re-cleaning")

        started = datetime.datetime.now(datetime.timezone.utc).isoformat()
        before_records = len(results_list)
        working_rows = [dict(r) for r in results_list]
        reclean_warnings: list[str] = []

        previous_status = job.status
        job.status = JobStatus.RUNNING

        ai_report = {
            "applied": False,
            "input_records": len(working_rows),
            "output_records": len(working_rows),
            "total_chunks": 0,
            "ai_chunks": 0,
            "fallback_chunks": 0,
            "model_fallback_mode": False,
            "noise_rows_removed": 0,
            "capped_records": 0,
            "quality_filtered_after_ai": 0,
        }

        try:
            try:
                cleaned_rows, ai_report = await asyncio.wait_for(
                    ai_clean_and_align_records(
                        working_rows,
                        job.schema_fields,
                        min_record_score=job.min_record_score,
                    ),
                    timeout=settings.AI_STRUCTURING_TIMEOUT_SECONDS,
                )
            except TimeoutError:
                cleaned_rows = working_rows
                timeout_s = settings.AI_STRUCTURING_TIMEOUT_SECONDS
                reclean_warnings.append(
                    f"AI re-clean timed out after {timeout_s}s; used deterministic post-processing.",
                )
            except Exception:
                logging.exception("Re-clean failed")
                cleaned_rows = working_rows
                reclean_warnings.append("AI re-clean failed; used deterministic post-processing.")
                logging.exception("Job %s: Re-clean failed", job_id)

            filtered_results, total, filtered_count, type_integrity_report = await process_results(
                cleaned_rows,
                job.schema_fields,
                job.filters,
            )

            if job.deduplicate and filtered_results:
                filtered_results = deduplicate_results(
                    records=filtered_results,
                    schema_fields=job.schema_fields,
                    deduplicate_field=job.deduplicate_field,
                )
                filtered_count = len(filtered_results)

            for row in filtered_results:
                source_url = str(row.get("source_url") or "")
                source_type = str(row.get("source_type") or "unknown").strip().lower()
                if source_type == "unknown" and source_url:
                    inferred = infer_source_metadata(url=source_url)
                    row["source_type"] = str(inferred.get("source_type") or "unknown")
                    row["source_trust_score"] = round(safe_score(inferred.get("source_trust_score") or 0.4), 3)

            job.results = normalize_job_results(filtered_results, job.schema_fields)
            job.total_records = total
            job.filtered_records = filtered_count
            job.completed_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
            job.status = JobStatus.COMPLETED

            scraped_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
            for row in job.results:
                row["scraped_at"] = scraped_at

            if len(job.results) > settings.JOB_RESULTS_DISK_OFFLOAD_THRESHOLD:
                from app.utils.job_results_store import save_job_results_to_disk

                file_path = await run_in_threadpool(save_job_results_to_disk, job.id, job.results)
                job.results_on_disk = True
                job.results_file_path = file_path
                job.results = []
            elif loaded_from_disk:
                from app.utils.job_results_store import delete_job_results_from_disk

                await run_in_threadpool(delete_job_results_from_disk, job.id, job.results_file_path)
                job.results_on_disk = False
                job.results_file_path = None

            prev_quality = dict(job.quality_report or {})
            existing_warnings = list(prev_quality.get("warnings") or [])
            radius_report = prev_quality.get("radius")
            if not isinstance(radius_report, dict):
                radius_report = {
                    "applied": False,
                    "reason": "not_configured",
                    "origin": job.origin_location,
                    "max_distance_km": job.max_distance_km,
                }

            ai_source_prediction = prev_quality.get("ai_source_prediction")
            if not isinstance(ai_source_prediction, dict):
                ai_source_prediction = {
                    "sources_attempted": 0,
                    "sources_with_ai_structuring": 0,
                    "records_processed": 0,
                    "records_ai_structured": 0,
                }

            source_breakdown = compute_source_breakdown(filtered_results)
            quality = build_quality_report(
                raw_results=cleaned_rows,
                post_filter_count=len(filtered_results),
                post_radius_count=len(filtered_results),
                radius_report=radius_report,
                final_results=filtered_results,
                min_record_score=job.min_record_score,
                type_integrity_report=type_integrity_report,
                source_breakdown=source_breakdown,
                ai_source_prediction=ai_source_prediction,
                ai_structuring_report=ai_report,
                warnings=[*existing_warnings, *reclean_warnings],
            )

            quality["reclean"] = {
                "applied": True,
                "started_at": started,
                "completed_at": job.completed_at,
                "before_records": before_records,
                "after_records": filtered_count,
                "ai_structuring": ai_report,
                "warnings": reclean_warnings,
            }
            job.quality_report = quality
            await save_job(job)
        except Exception as e:
            logging.getLogger(__name__).exception(
                "Job %s: Reclean failed irrecoverably, restoring previous status %s",
                job_id,
                previous_status.value if hasattr(previous_status, "value") else previous_status,
            )
            job.status = previous_status
            reclean_warnings.append(f"Reclean failed: {e}")
            try:
                await save_job(job)
            except Exception:
                logging.getLogger(__name__).exception(
                    "Job %s: Failed to persist job state after reclean rollback",
                    job_id,
                )
            raise HTTPException(status_code=500, detail=f"Reclean failed: {e}") from e

        return {
            "job_id": job.id,
            "status": job.status.value,
            "before_records": before_records,
            "after_records": filtered_count,
            "warnings": reclean_warnings,
        }

    @router.delete("/api/jobs/{job_id}")
    async def delete_job(
        job_id: str,
        _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN]))],
    ):
        with manager.lock:
            if job_id not in manager.jobs_store:
                raise HTTPException(status_code=404, detail="Job not found")
            job = manager.jobs_store[job_id]
            if job.status in {JobStatus.PENDING, JobStatus.DISCOVERING, JobStatus.RUNNING}:
                raise HTTPException(
                    status_code=409,
                    detail="Cannot delete/recycle an active job. Cancel the job first.",
                )
        # Consistency contract: the in-memory pop is fast (microseconds) and
        # the repo.move_to_recycle_bin call is the slow part (a network round
        # trip + transaction). We deliberately release the lock between
        # them so concurrent reads / writes to other jobs are not blocked
        # while we wait for the DB. The trade-off is that, if the DB move
        # fails after the in-memory pop, the in-memory store is consistent
        # (job is gone) but the persistent store is not (job is still
        # active). Callers therefore MUST treat the in-memory store as the
        # source of truth; the persistent store is only a recovery record.
        # If you need strict cross-store consistency, wrap both steps in
        # a single ``with manager.lock:`` and accept the throughput cost.
        repo = get_job_repository()
        await run_in_threadpool(repo.move_to_recycle_bin, job_id)
        with manager.lock:
            if job_id in manager.jobs_store:
                manager.recycle_bin_store[job_id] = manager.jobs_store.pop(job_id)
        return {"message": "Job moved to recycle bin"}

    @router.delete("/api/jobs/cleanup/terminal")
    async def clear_terminal_jobs(
        _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN]))],  # noqa: B008, RUF100
        keep_recent: Annotated[int, Query(ge=0, le=5000)] = 5,
    ):
        terminal_statuses = {
            JobStatus.COMPLETED,
            JobStatus.DEGRADED,
            JobStatus.EMPTY_RESULT,
            JobStatus.FAILED,
            JobStatus.CANCELED,
        }
        with manager.lock:
            terminal = [(jid, job) for jid, job in manager.jobs_store.items() if job.status in terminal_statuses]

        if not terminal:
            return {
                "message": "No terminal jobs to clear",
                "cleared": 0,
                "kept_recent": keep_recent,
                "remaining": len(manager.jobs_store),
            }

        terminal.sort(key=lambda item: item[1].created_at, reverse=True)
        keep_ids = {jid for jid, _ in terminal[:keep_recent]}

        removed = 0
        repo = get_job_repository()

        for jid, _ in terminal:
            if jid in keep_ids:
                continue
            await run_in_threadpool(repo.move_to_recycle_bin, jid)
            with manager.lock:
                if jid in manager.jobs_store:
                    manager.recycle_bin_store[jid] = manager.jobs_store.pop(jid)
            removed += 1

        with manager.lock:
            remaining = len(manager.jobs_store)

        return {
            "message": f"Cleared {removed} terminal jobs",
            "cleared": removed,
            "kept_recent": keep_recent,
            "remaining": remaining,
        }

    @router.post("/api/recycle_bin/{job_id}/restore")
    async def restore_job(
        job_id: str,
        _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN]))],
    ):
        with manager.lock:
            if job_id not in manager.recycle_bin_store:
                raise HTTPException(status_code=404, detail="Job not in recycle bin")
        repo = get_job_repository()
        await run_in_threadpool(repo.restore_from_recycle_bin, job_id)
        with manager.lock:
            if job_id in manager.recycle_bin_store:
                manager.jobs_store[job_id] = manager.recycle_bin_store.pop(job_id)
        return {"message": "Job restored"}

    @router.delete("/api/recycle_bin/{job_id}")
    async def hard_delete_job(
        job_id: str,
        _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN]))],
    ):
        with manager.lock:
            if job_id not in manager.recycle_bin_store:
                raise HTTPException(status_code=404, detail="Job not in recycle bin")
            job = manager.recycle_bin_store.get(job_id)
            file_path = job.results_file_path if job else None
        if file_path:
            from app.utils.job_results_store import delete_job_results_from_disk

            await run_in_threadpool(delete_job_results_from_disk, job_id, file_path)
        repo = get_job_repository()
        await run_in_threadpool(repo.hard_delete, job_id)
        with manager.lock:
            manager.recycle_bin_store.pop(job_id, None)
        return {"message": "Job permanently deleted"}

    @router.delete("/api/recycle_bin")
    async def clear_recycle_bin(
        _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN]))],
    ):
        from app.utils.job_results_store import delete_job_results_from_disk

        with manager.lock:
            snapshot = list(manager.recycle_bin_store.items())
            count = len(snapshot)
        for jid, job in snapshot:
            file_path = job.results_file_path if job else None
            if file_path:
                await run_in_threadpool(delete_job_results_from_disk, jid, file_path)
        repo = get_job_repository()
        for jid, _ in snapshot:
            await run_in_threadpool(repo.hard_delete, jid)
        with manager.lock:
            for jid, _ in snapshot:
                manager.recycle_bin_store.pop(jid, None)
        return {"message": f"Recycle bin cleared ({count} items)", "cleared": count}

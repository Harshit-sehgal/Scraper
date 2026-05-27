import asyncio
import datetime
import logging
import threading
from typing import Callable

from fastapi import APIRouter, HTTPException, Query, Depends
from app.utils.rbac import UserRole, require_role

from app.config import settings
from app.discovery import discover_urls, infer_source_metadata
from app.filters import process_results
from app.models import (
    DiscoveryRequest,
    Job,
    JobCreate,
    JobStatus,
    SchemaSuggestionRequest,
    ScrapeMode,
)
from app.scraper import (
    ai_clean_and_align_records,
    suggest_schema_from_intent,
)
from app.utils.job import deduplicate_results, mark_job_canceled, normalize_job_results
from app.utils.quality import build_quality_report, compute_source_breakdown, safe_score
from app.storage_interface import get_job_repository


def _save_job(job) -> None:
    """Persist a single job through the configured repository."""
    get_job_repository().save_single(job)


def create_jobs_router(
    jobs_store: dict,
    recycle_bin_store: dict,
    persist_state_fn: Callable,
    schedule_task_fn: Callable,
    run_job_coro_fn: Callable,
    config: dict,
):
    router = APIRouter()

    # ── Thread-safe store access ───────────────────────────────────────
    # Protect concurrent access to jobs_store and recycle_bin_store.
    # These are Python dicts shared across async requests; a threading lock
    # is sufficient because critical sections are microsecond-level lookups.
    _store_lock = threading.Lock()

    def _get_job(job_id: str) -> Job:
        """Thread-safe lookup returning the job or raising 404."""
        with _store_lock:
            if job_id not in jobs_store:
                raise HTTPException(status_code=404, detail="Job not found")
            return jobs_store[job_id]

    def _pop_job(job_id: str) -> Job:
        """Thread-safe pop from jobs_store, raising 404 if missing."""
        with _store_lock:
            if job_id not in jobs_store:
                raise HTTPException(status_code=404, detail="Job not found")
            return jobs_store.pop(job_id)

    def _move_to_recycle_bin(job: Job) -> None:
        """Thread-safe move from jobs_store to recycle_bin_store."""
        with _store_lock:
            recycle_bin_store[job.id] = job
            jobs_store.pop(job.id, None)

    def _pop_from_recycle_bin(job_id: str) -> Job:
        """Thread-safe pop from recycle_bin_store, raising 404 if missing."""
        with _store_lock:
            if job_id not in recycle_bin_store:
                raise HTTPException(status_code=404, detail="Job not in recycle bin")
            return recycle_bin_store.pop(job_id)

    @router.post("/api/discover")
    async def discover(req: DiscoveryRequest):
        """Auto-discover best URLs to scrape for a topic."""
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
        from app.url_safety import validate_public_http_url
        safe_results = []
        for r in results:
            url = r.get("url")
            if url:
                try:
                    validate_public_http_url(url)
                    safe_results.append(r)
                except ValueError:
                    pass
        return {"urls": safe_results}

    @router.post("/api/schema/suggest")
    async def suggest_schema(req: SchemaSuggestionRequest):
        """Infer topic + schema fields from plain-language user intent."""
        suggestion = await suggest_schema_from_intent(req.intent, max_fields=req.max_fields)
        return suggestion

    @router.get("/api/jobs")
    async def list_jobs():
        with _store_lock:
            ordered = sorted(jobs_store.values(), key=lambda j: j.created_at, reverse=True)
            return {"jobs": [job.model_dump() for job in ordered]}

    @router.get("/api/jobs/{job_id}")
    async def get_job(job_id: str, include_results: bool = Query(False)):
        job = _get_job(job_id)

        results_list = []
        if include_results:
            results_list = list(job.results)
            if job.results_on_disk:
                from app.utils.job_results_store import load_job_results_from_disk
                results_list = load_job_results_from_disk(job.id, job.results_file_path)

        dumped = job.model_dump()
        dumped["results"] = results_list
        return dumped

    @router.get("/api/jobs/{job_id}/results")
    async def get_job_results(job_id: str, limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0)):
        """Return a paginated slice of job results."""
        job = _get_job(job_id)

        if job.results_on_disk:
            from app.utils.job_results_store import load_paginated_job_results_from_disk
            page, total = load_paginated_job_results_from_disk(
                job.id, limit=limit, offset=offset, file_path=job.results_file_path,
            )
        else:
            results_list = list(job.results)
            total = len(results_list)
            page = results_list[offset:offset + limit]

        next_offset = offset + limit if (offset + limit) < total else None

        return {
            "job_id": job_id,
            "results": page,
            "total": total,
            "limit": limit,
            "offset": offset,
            "next_offset": next_offset,
            "returned": len(page),
        }

    @router.post("/api/jobs/{job_id}/backfill-metadata")
    async def backfill_job_metadata(job_id: str):
        """Explicitly backfill source metadata for manual-mode job results."""
        job = _get_job(job_id)

        results_list = list(job.results)
        if job.results_on_disk:
            from app.utils.job_results_store import load_job_results_from_disk
            results_list = load_job_results_from_disk(job.id, job.results_file_path)

        from app.discovery import infer_source_metadata
        from app.utils.quality import safe_score
        
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
                save_job_results_to_disk(job.id, results_list)
            _save_job(job)

        return {"message": "Metadata backfilled successfully", "updated": updated}

    @router.post("/api/jobs")
    async def create_job(job_data: JobCreate, _role: UserRole = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR]))):
        import os

        manual_urls = [u.strip() for u in job_data.urls if str(u or "").strip()]
        urls = manual_urls if job_data.mode == ScrapeMode.MANUAL else []

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
        jobs_store[job.id] = job
        _save_job(job)

        # If DATAFORGE_WORKER_QUEUE is set, enqueue the job for async processing
        worker_queue_enabled = os.getenv("DATAFORGE_WORKER_QUEUE", "").strip()
        if worker_queue_enabled and worker_queue_enabled.lower() in ("1", "true", "yes"):
            try:
                from app.worker_queue import get_worker_queue, Priority
                queue = get_worker_queue()
                task_id = await queue.enqueue(
                    task_type="scrape_job",
                    payload={"job_id": job.id},
                    priority=Priority.NORMAL,
                    task_id=job.id,
                )
                logging.getLogger(__name__).info(
                    "Job %s enqueued to worker queue (task=%s)", job.id, task_id
                )
            except Exception as e:
                if settings.ENV.lower() == "production":
                    logging.getLogger(__name__).error(
                        "Failed to enqueue job %s to worker queue in production: %s",
                        job.id, e,
                    )
                    if job.id in jobs_store:
                        del jobs_store[job.id]
                    try:
                        repo = get_job_repository()
                        repo.hard_delete(job.id)
                    except Exception:
                        pass
                    raise HTTPException(
                        status_code=503,
                        detail=(
                            f"Failed to enqueue job {job.id} to worker queue. "
                            "Inline fallback is disabled in production. "
                            "Check that the worker queue is running and healthy."
                        ),
                    )
                logging.getLogger(__name__).warning(
                    "Failed to enqueue job %s to worker queue, falling back to inline: %s",
                    job.id, e,
                )
                schedule_task_fn(run_job_coro_fn(job.id))
        else:
            schedule_task_fn(run_job_coro_fn(job.id))

        return {"job_id": job.id, "status": job.status.value}

    @router.post("/api/jobs/{job_id}/cancel")
    async def cancel_job(job_id: str, _role: UserRole = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR]))):
        if job_id not in jobs_store:
            raise HTTPException(status_code=404, detail="Job not found")

        job = jobs_store[job_id]
        if job.status in {JobStatus.COMPLETED, JobStatus.DEGRADED, JobStatus.EMPTY_RESULT, JobStatus.FAILED, JobStatus.CANCELED}:
            return {
                "job_id": job.id,
                "status": job.status.value,
                "cancel_requested": bool(job.cancel_requested),
                "message": "Job already in terminal state",
            }

        job.cancel_requested = True
        if job.status == JobStatus.PENDING:
            mark_job_canceled(job, "Canceled before execution.")

        # Cancel the queued task if worker queue is enabled
        import os as _os
        worker_queue_enabled = _os.getenv("DATAFORGE_WORKER_QUEUE", "").strip()
        if worker_queue_enabled and worker_queue_enabled.lower() in ("1", "true", "yes"):
            try:
                from app.worker_queue import get_worker_queue
                queue = get_worker_queue()
                await queue.cancel(job_id)
            except Exception as e:
                logging.getLogger(__name__).warning(
                    "Failed to cancel queued task for job %s: %s", job_id, e,
                )

        _save_job(job)
        return {
            "job_id": job.id,
            "status": job.status.value,
            "cancel_requested": True,
            "cancel_queued_task": True,
            "message": "Cancellation requested",
        }

    @router.post("/api/jobs/{job_id}/reclean")
    async def reclean_job(job_id: str, _role: UserRole = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR]))):
        """Re-run AI cleaning and schema alignment on existing job results without re-scraping URLs."""
        if job_id not in jobs_store:
            raise HTTPException(status_code=404, detail="Job not found")

        job = jobs_store[job_id]
        if job.status in {JobStatus.PENDING, JobStatus.DISCOVERING, JobStatus.RUNNING}:
            raise HTTPException(status_code=409, detail="Job is still running; wait for completion before re-cleaning")
        
        results_list = list(job.results)
        loaded_from_disk = False
        if job.results_on_disk:
            from app.utils.job_results_store import load_job_results_from_disk
            results_list = load_job_results_from_disk(job.id, job.results_file_path)
            loaded_from_disk = True

        if not results_list:
            raise HTTPException(status_code=400, detail="No results to re-clean")
        if not job.schema_fields:
            raise HTTPException(status_code=400, detail="Job has no schema fields for re-cleaning")

        started = datetime.datetime.now().isoformat()
        before_records = len(results_list)
        working_rows = [dict(r) for r in results_list]
        reclean_warnings: list[str] = []

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
            cleaned_rows, ai_report = await asyncio.wait_for(
                ai_clean_and_align_records(
                    working_rows,
                    job.schema_fields,
                    min_record_score=job.min_record_score,
                ),
                timeout=config["ai_structuring_timeout_seconds"],
            )
        except asyncio.TimeoutError:
            cleaned_rows = working_rows
            reclean_warnings.append(
                f"AI re-clean timed out after {config['ai_structuring_timeout_seconds']}s; used deterministic post-processing."
            )
        except Exception as e:
            logging.exception(e)
            cleaned_rows = working_rows
            reclean_warnings.append("AI re-clean failed; used deterministic post-processing.")
            logging.error("Job %s: Re-clean failed: %s", job_id, e)

        filtered_results, total, filtered_count, type_integrity_report = process_results(
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

        # Backfill manual-mode source metadata so users don't only see "unknown".
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
        job.completed_at = datetime.datetime.now().isoformat()
        job.status = JobStatus.COMPLETED

        # Update timestamps on refreshed records.
        scraped_at = datetime.datetime.now().isoformat()
        for row in job.results:
            row["scraped_at"] = scraped_at

        # Save back to disk if results remain above the configured in-memory threshold.
        if len(job.results) > settings.JOB_RESULTS_DISK_OFFLOAD_THRESHOLD:
            from app.utils.job_results_store import save_job_results_to_disk
            file_path = save_job_results_to_disk(job.id, job.results)
            job.results_on_disk = True
            job.results_file_path = file_path
            job.results = []
        else:
            if loaded_from_disk:
                from app.utils.job_results_store import delete_job_results_from_disk
                delete_job_results_from_disk(job.id, job.results_file_path)
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
        _save_job(job)

        return {
            "job_id": job.id,
            "status": job.status.value,
            "before_records": before_records,
            "after_records": filtered_count,
            "warnings": reclean_warnings,
        }

    @router.delete("/api/jobs/{job_id}")
    async def delete_job(job_id: str, _role: UserRole = Depends(require_role([UserRole.ADMIN]))):
        if job_id not in jobs_store:
            raise HTTPException(status_code=404, detail="Job not found")
        job = jobs_store[job_id]
        if job.status in {JobStatus.PENDING, JobStatus.DISCOVERING, JobStatus.RUNNING}:
            raise HTTPException(
                status_code=409,
                detail="Cannot delete/recycle an active job. Cancel the job first."
            )
        repo = get_job_repository()
        repo.move_to_recycle_bin(job_id)
        recycle_bin_store[job_id] = jobs_store.pop(job_id)
        return {"message": "Job moved to recycle bin"}

    @router.delete("/api/jobs/cleanup/terminal")
    async def clear_terminal_jobs(keep_recent: int = Query(5, ge=0, le=5000), _role: UserRole = Depends(require_role([UserRole.ADMIN]))):
        terminal_statuses = {JobStatus.COMPLETED, JobStatus.DEGRADED, JobStatus.EMPTY_RESULT, JobStatus.FAILED, JobStatus.CANCELED}
        terminal = [
            (jid, job)
            for jid, job in jobs_store.items()
            if job.status in terminal_statuses
        ]

        if not terminal:
            return {
                "message": "No terminal jobs to clear",
                "cleared": 0,
                "kept_recent": keep_recent,
                "remaining": len(jobs_store),
            }

        terminal.sort(key=lambda item: item[1].created_at, reverse=True)
        keep_ids = {jid for jid, _ in terminal[:keep_recent]}

        removed = 0
        repo = get_job_repository()

        for jid, _ in terminal:
            if jid in keep_ids:
                continue
            repo.move_to_recycle_bin(jid)
            if jid in jobs_store:
                recycle_bin_store[jid] = jobs_store.pop(jid)
            removed += 1

        return {
            "message": f"Cleared {removed} terminal jobs",
            "cleared": removed,
            "kept_recent": keep_recent,
            "remaining": len(jobs_store),
        }

    @router.get("/api/recycle_bin")
    async def list_recycle_bin():
        ordered = sorted(recycle_bin_store.values(), key=lambda j: j.created_at, reverse=True)
        return {"jobs": [job.model_dump() for job in ordered]}

    @router.post("/api/recycle_bin/{job_id}/restore")
    async def restore_job(job_id: str, _role: UserRole = Depends(require_role([UserRole.ADMIN]))):
        if job_id not in recycle_bin_store:
            raise HTTPException(status_code=404, detail="Job not in recycle bin")
        repo = get_job_repository()
        repo.restore_from_recycle_bin(job_id)
        jobs_store[job_id] = recycle_bin_store.pop(job_id)
        return {"message": "Job restored"}

    @router.delete("/api/recycle_bin/{job_id}")
    async def hard_delete_job(job_id: str, _role: UserRole = Depends(require_role([UserRole.ADMIN]))):
        if job_id not in recycle_bin_store:
            raise HTTPException(status_code=404, detail="Job not in recycle bin")
        from app.utils.job_results_store import delete_job_results_from_disk
        job = recycle_bin_store.get(job_id)
        file_path = job.results_file_path if job else None
        delete_job_results_from_disk(job_id, file_path)
        repo = get_job_repository()
        repo.hard_delete(job_id)
        del recycle_bin_store[job_id]
        return {"message": "Job permanently deleted"}

    @router.delete("/api/recycle_bin")
    async def clear_recycle_bin(_role: UserRole = Depends(require_role([UserRole.ADMIN]))):
        count = len(recycle_bin_store)
        from app.utils.job_results_store import delete_job_results_from_disk
        for jid in list(recycle_bin_store.keys()):
            job = recycle_bin_store.get(jid)
            file_path = job.results_file_path if job else None
            delete_job_results_from_disk(jid, file_path)
        repo = get_job_repository()
        for jid in list(recycle_bin_store.keys()):
            repo.hard_delete(jid)
        recycle_bin_store.clear()
        return {"message": f"Recycle bin cleared ({count} items)", "cleared": count}

    return router

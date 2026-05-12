import asyncio
import datetime
import logging

from fastapi import APIRouter, HTTPException, Query

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

def create_jobs_router(
    jobs_store: dict,
    recycle_bin_store: dict,
    persist_state_fn,
    schedule_task_fn,
    run_job_coro_fn,
    config: dict,
):
    router = APIRouter()

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
        return {"urls": results}

    @router.post("/api/schema/suggest")
    async def suggest_schema(req: SchemaSuggestionRequest):
        """Infer topic + schema fields from plain-language user intent."""
        suggestion = await suggest_schema_from_intent(req.intent, max_fields=req.max_fields)
        return suggestion

    @router.get("/api/jobs")
    async def list_jobs():
        ordered = sorted(jobs_store.values(), key=lambda j: j.created_at, reverse=True)
        return {"jobs": [job.model_dump() for job in ordered]}

    @router.get("/api/jobs/{job_id}")
    async def get_job(job_id: str):
        if job_id not in jobs_store:
            raise HTTPException(status_code=404, detail="Job not found")
        job = jobs_store[job_id]
        
        # Backfill source metadata helper logic
        if job.results:
            changed = False
            for row in job.results:
                source_url = str(row.get("source_url") or "").strip()
                if not source_url:
                    continue

                source_type = str(row.get("source_type") or "unknown").strip().lower()
                trust_score = row.get("source_trust_score")
                if source_type != "unknown" and trust_score is not None:
                    continue

                inferred = infer_source_metadata(url=source_url)
                row["source_type"] = str(inferred.get("source_type") or "unknown")
                row["source_trust_score"] = round(safe_score(inferred.get("source_trust_score") or 0.4), 3)
                changed = True

            if changed:
                q = dict(job.quality_report or {})
                q["source_breakdown"] = compute_source_breakdown(job.results)
                job.quality_report = q
                persist_state_fn()
                
        return job.model_dump()

    @router.post("/api/jobs")
    async def create_job(job_data: JobCreate):
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
            pagination=job_data.pagination,
            max_pages=job_data.max_pages,
            deduplicate=job_data.deduplicate,
            deduplicate_field=job_data.deduplicate_field,
            min_record_score=job_data.min_record_score,
        )
        jobs_store[job.id] = job
        persist_state_fn()
        schedule_task_fn(run_job_coro_fn(job.id))
        return {"job_id": job.id, "status": job.status.value}

    @router.post("/api/jobs/{job_id}/cancel")
    async def cancel_job(job_id: str):
        if job_id not in jobs_store:
            raise HTTPException(status_code=404, detail="Job not found")

        job = jobs_store[job_id]
        if job.status in {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELED}:
            return {
                "job_id": job.id,
                "status": job.status.value,
                "cancel_requested": bool(job.cancel_requested),
                "message": "Job already in terminal state",
            }

        job.cancel_requested = True
        if job.status == JobStatus.PENDING:
            mark_job_canceled(job, "Canceled before execution.")

        persist_state_fn()
        return {
            "job_id": job.id,
            "status": job.status.value,
            "cancel_requested": True,
            "message": "Cancellation requested",
        }

    @router.post("/api/jobs/{job_id}/reclean")
    async def reclean_job(job_id: str):
        """Re-run AI cleaning and schema alignment on existing job results without re-scraping URLs."""
        if job_id not in jobs_store:
            raise HTTPException(status_code=404, detail="Job not found")

        job = jobs_store[job_id]
        if job.status in {JobStatus.PENDING, JobStatus.DISCOVERING, JobStatus.RUNNING}:
            raise HTTPException(status_code=409, detail="Job is still running; wait for completion before re-cleaning")
        if not job.results:
            raise HTTPException(status_code=400, detail="No results to re-clean")
        if not job.schema_fields:
            raise HTTPException(status_code=400, detail="Job has no schema fields for re-cleaning")

        started = datetime.datetime.now().isoformat()
        before_records = len(job.results)
        working_rows = [dict(r) for r in job.results]
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
            print(f"[Job {job_id}] Re-clean failed: {e}")

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
            "after_records": len(job.results),
            "ai_structuring": ai_report,
            "warnings": reclean_warnings,
        }
        job.quality_report = quality
        persist_state_fn()

        return {
            "job_id": job.id,
            "status": job.status.value,
            "before_records": before_records,
            "after_records": len(job.results),
            "warnings": reclean_warnings,
        }

    @router.delete("/api/jobs/{job_id}")
    async def delete_job(job_id: str):
        if job_id not in jobs_store:
            raise HTTPException(status_code=404, detail="Job not found")
        recycle_bin_store[job_id] = jobs_store.pop(job_id)
        persist_state_fn()
        return {"message": "Job moved to recycle bin"}

    @router.delete("/api/jobs/cleanup/terminal")
    async def clear_terminal_jobs(keep_recent: int = Query(5, ge=0, le=5000)):
        terminal_statuses = {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELED}
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
        for jid, _ in terminal:
            if jid in keep_ids:
                continue
            del jobs_store[jid]
            removed += 1

        if removed:
            persist_state_fn()

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
    async def restore_job(job_id: str):
        if job_id not in recycle_bin_store:
            raise HTTPException(status_code=404, detail="Job not in recycle bin")
        jobs_store[job_id] = recycle_bin_store.pop(job_id)
        persist_state_fn()
        return {"message": "Job restored"}

    @router.delete("/api/recycle_bin/{job_id}")
    async def hard_delete_job(job_id: str):
        if job_id not in recycle_bin_store:
            raise HTTPException(status_code=404, detail="Job not in recycle bin")
        del recycle_bin_store[job_id]
        persist_state_fn()
        return {"message": "Job permanently deleted"}

    @router.delete("/api/recycle_bin")
    async def clear_recycle_bin():
        count = len(recycle_bin_store)
        recycle_bin_store.clear()
        if count:
            persist_state_fn()
        return {"message": f"Recycle bin cleared ({count} items)"}

    return router

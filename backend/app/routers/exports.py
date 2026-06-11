"""Thin FastAPI router for export endpoints.

All pure formatting / streaming / sheet-collision logic lives in
:mod:`app.services.exports`. This module owns only:

* Route definitions (``/api/jobs/{id}/export/{csv,json,excel}`` and
  ``/api/exports/batch``)
* Auth dependency wiring (operator/admin required)
* Usage-metering side effects (calls into
  :func:`app.utils.usage_ledger.record_usage` and
  :func:`app.metrics_collector.record_export_outcome`)
* The repository-refresh hook that pulls a fresh job from the
  repository in worker mode before exporting (so we never export a
  stale in-memory copy)

Keeping the router thin lets us unit-test the formatting logic in
isolation and makes future changes (e.g. switching to a faster Excel
library, adding new export formats) safe — they happen in the
service module without touching FastAPI machinery.
"""

from __future__ import annotations

import logging
import threading
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.services import exports as export_service
from app.utils.export import safe_export_filename
from app.utils.rbac import UserRole, require_role_with_user

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════
# Request / response schemas
# ════════════════════════════════════════════════════════════════════


class BatchExportRequest(BaseModel):
    """Request body for batch export endpoint."""

    job_ids: list[str] = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Job IDs to include in the batch export",
    )
    format: str = Field(
        "csv",
        description="Export format: csv, json, or xlsx",
    )
    flatten: bool = Field(
        True,
        description="When True, all results are combined into a single output. "
        "When False, CSV uses separator rows and Excel uses one sheet per job.",
    )


# ════════════════════════════════════════════════════════════════════
# Side-effect helpers
# ════════════════════════════════════════════════════════════════════


def _record_export_outcome(fmt: str, success: bool) -> None:
    """Record an export generation outcome for the metrics endpoint.

    A broken metrics subsystem must never turn a successful export
    into a 5xx.
    """
    try:
        from app.metrics_collector import record_export_outcome

        record_export_outcome(fmt, success)
    except Exception:
        logger.debug("Failed to record export outcome metric for %s", fmt)


def _export_idempotency_key(request: Request, fmt: str, job_ids: list[str]) -> str:
    header = request.headers.get("Idempotency-Key") or request.headers.get("X-Idempotency-Key") or ""
    if not header:
        return ""
    return f"export:{fmt}:{','.join(sorted(job_ids))}:{header}"


def _record_export_usage(user_id: str, fmt: str, job_ids: list[str], request: Request) -> None:
    from app.utils.usage_ledger import UsageType, get_usage_ledger

    metadata: dict[str, Any] = {"format": fmt}
    if len(job_ids) == 1:
        metadata["job_id"] = job_ids[0]
    else:
        metadata["job_ids"] = list(job_ids)
    try:
        get_usage_ledger().record_usage(
            user_id,
            UsageType.EXPORT_GENERATED,
            quantity=1,
            metadata=metadata,
            idempotency_key=_export_idempotency_key(request, fmt, job_ids),
        )
    except ValueError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc


def _log_export_access(
    user_id: str,
    fmt: str,
    job_ids: list[str],
    request: Request,
    *,
    success: bool,
) -> None:
    """P1-COMPLIANCE-001: log every export access to the audit log.

    Best-effort: a broken audit logger must never turn a successful
    export into a 5xx. Failures are swallowed and logged at DEBUG.
    """
    try:
        from app.audit_logger import log_data_access

        metadata: dict[str, Any] = {
            "format": fmt,
            "job_count": len(job_ids),
            "client_ip": _get_client_ip_for_audit(request),
        }
        if len(job_ids) == 1:
            metadata["job_id"] = job_ids[0]
        else:
            metadata["job_ids"] = list(job_ids)
        # Surface org_id / project_id from the resolved auth context
        # so the audit log carries tenant attribution.
        org_id = ""
        project_id = ""
        try:
            ctx = getattr(getattr(request, "state", None), "auth_context", None)
            if ctx is not None:
                org_id = getattr(ctx, "org_id", "") or ""
                project_id = getattr(ctx, "project_id", "") or ""
        except Exception:
            org_id = ""
            project_id = ""
        log_data_access(
            actor=user_id,
            action=f"export_{fmt}",
            resource=f"jobs:{','.join(job_ids)}" if job_ids else "jobs:",
            details=metadata,
            outcome="success" if success else "failure",
            org_id=org_id,
            project_id=project_id,
        )
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("Failed to log export access for %s: %s", fmt, e)


def _get_client_ip_for_audit(request: Request) -> str:
    """Best-effort client IP extraction for audit log lines."""
    try:
        return request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (
            request.client.host if request.client else "unknown"
        )
    except Exception:
        return "unknown"


# ════════════════════════════════════════════════════════════════════
# Router factory
# ════════════════════════════════════════════════════════════════════


def create_exports_router(jobs_store: dict[str, Any]):
    """Build the export APIRouter.

    The router exposes:

    * ``GET /api/jobs/{job_id}/export/csv``
    * ``GET /api/jobs/{job_id}/export/json``
    * ``GET /api/jobs/{job_id}/export/excel``
    * ``POST /api/exports/batch``

    All endpoints require admin or operator role. Auth is resolved
    through the shared :func:`app.utils.rbac.require_role_with_user`
    dependency (the 2-tuple legacy form — exports predate the
    org_id/project_id wiring and operate over the legacy owner
    model).
    """
    router = APIRouter()

    # Single-process lock guarding refresh-from-repo writes into
    # ``jobs_store``. Two concurrent export requests otherwise race
    # and observe a partially-overwritten job.
    _store_lock = threading.Lock()

    def _refresh_job_for_export(job_id: str) -> None:
        """Refresh job from repository in worker mode to avoid stale exports."""
        if not settings.WORKER_QUEUE:
            return
        try:
            from app.storage_interface import get_job_repository

            repo = get_job_repository()
            fresh = repo.get_job(job_id)
            if fresh is not None:
                with _store_lock:
                    jobs_store[job_id] = fresh
        except Exception:
            logger.debug("Failed to refresh job %s from repo for export", job_id)

    # ─── Single-job exports ─────────────────────────────────────────

    @router.get("/api/jobs/{job_id}/export/csv")
    async def export_csv(
        job_id: str,
        request: Request,
        auth: Annotated[tuple[UserRole, str], Depends(require_role_with_user([UserRole.ADMIN, UserRole.OPERATOR]))],
    ):
        try:
            result = await _export_csv_impl(job_id)
            _record_export_usage(auth[1], "csv", [job_id], request)
        except HTTPException:
            _record_export_outcome("csv", False)
            _log_export_access(auth[1], "csv", [job_id], request, success=False)
            raise
        except Exception:
            _record_export_outcome("csv", False)
            _log_export_access(auth[1], "csv", [job_id], request, success=False)
            raise
        else:
            _record_export_outcome("csv", True)
            _log_export_access(auth[1], "csv", [job_id], request, success=True)
            return result

    async def _export_csv_impl(job_id: str):
        await run_in_threadpool(_refresh_job_for_export, job_id)
        job = jobs_store.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        if job.results_on_disk:
            from app.utils.job_results_store import load_paginated_job_results_from_disk

            return StreamingResponse(
                export_service.stream_csv_from_disk(job, load_paginated_job_results_from_disk),
                media_type="text/csv",
                headers={"Content-Disposition": f'attachment; filename="{safe_export_filename(job.name, "csv")}"'},
            )

        try:
            body = export_service.build_csv_bytes(job)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return StreamingResponse(
            iter([body]),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{safe_export_filename(job.name, "csv")}"'},
        )

    @router.get("/api/jobs/{job_id}/export/json")
    async def export_json(
        job_id: str,
        request: Request,
        auth: Annotated[tuple[UserRole, str], Depends(require_role_with_user([UserRole.ADMIN, UserRole.OPERATOR]))],
    ):
        try:
            result = await _export_json_impl(job_id)
            _record_export_usage(auth[1], "json", [job_id], request)
        except HTTPException:
            _record_export_outcome("json", False)
            _log_export_access(auth[1], "json", [job_id], request, success=False)
            raise
        except Exception:
            _record_export_outcome("json", False)
            _log_export_access(auth[1], "json", [job_id], request, success=False)
            raise
        else:
            _record_export_outcome("json", True)
            _log_export_access(auth[1], "json", [job_id], request, success=True)
            return result

    async def _export_json_impl(job_id: str):
        await run_in_threadpool(_refresh_job_for_export, job_id)
        job = jobs_store.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        if job.results_on_disk:
            from app.utils.job_results_store import load_paginated_job_results_from_disk

            return StreamingResponse(
                export_service.stream_json_from_disk(job, load_paginated_job_results_from_disk),
                media_type="application/json",
                headers={"Content-Disposition": f'attachment; filename="{safe_export_filename(job.name, "json")}"'},
            )

        try:
            body = export_service.build_json_bytes(job)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return StreamingResponse(
            iter([body]),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{safe_export_filename(job.name, "json")}"'},
        )

    @router.get("/api/jobs/{job_id}/export/excel")
    async def export_excel(
        job_id: str,
        request: Request,
        auth: Annotated[tuple[UserRole, str], Depends(require_role_with_user([UserRole.ADMIN, UserRole.OPERATOR]))],
    ):
        try:
            result = await _export_excel_impl(job_id)
            _record_export_usage(auth[1], "excel", [job_id], request)
        except HTTPException:
            _record_export_outcome("excel", False)
            _log_export_access(auth[1], "excel", [job_id], request, success=False)
            raise
        except Exception:
            _record_export_outcome("excel", False)
            _log_export_access(auth[1], "excel", [job_id], request, success=False)
            raise
        _record_export_outcome("excel", True)
        _log_export_access(auth[1], "excel", [job_id], request, success=True)
        return result

    async def _export_excel_impl(job_id: str):
        await run_in_threadpool(_refresh_job_for_export, job_id)
        job = jobs_store.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        if job.results_on_disk:
            from app.utils.job_results_store import load_paginated_job_results_from_disk

            try:
                content_bytes = await run_in_threadpool(
                    export_service.build_excel_bytes,
                    job,
                    load_paginated_job_results_from_disk,
                )
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        else:
            try:
                content_bytes = await run_in_threadpool(export_service.build_excel_bytes, job)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

        return StreamingResponse(
            iter([content_bytes]),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{safe_export_filename(job.name, "xlsx")}"'},
        )

    # ─── Batch export ───────────────────────────────────────────────

    @router.post("/api/exports/batch")
    async def batch_export(
        request: Request,
        body: BatchExportRequest,
        auth: Annotated[tuple[UserRole, str], Depends(require_role_with_user([UserRole.ADMIN, UserRole.OPERATOR]))],
    ):
        try:
            result = await _batch_export_impl(body)
            _record_export_usage(auth[1], f"batch_{body.format}", body.job_ids, request)
        except HTTPException:
            _record_export_outcome(f"batch_{body.format}", False)
            _log_export_access(auth[1], f"batch_{body.format}", body.job_ids, request, success=False)
            raise
        except Exception:
            _record_export_outcome(f"batch_{body.format}", False)
            _log_export_access(auth[1], f"batch_{body.format}", body.job_ids, request, success=False)
            raise
        else:
            _record_export_outcome(f"batch_{body.format}", True)
            _log_export_access(auth[1], f"batch_{body.format}", body.job_ids, request, success=True)
            return result

    async def _batch_export_impl(body: BatchExportRequest):
        fmt = body.format.lower()
        if fmt not in ("csv", "json", "xlsx"):
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported format '{fmt}'. Supported: csv, json, xlsx",
            )

        # Resolve all jobs — fail fast on any missing ID.
        missing: list[str] = []
        for _jid in body.job_ids:
            if _jid not in jobs_store:
                missing.append(_jid)
            else:
                await run_in_threadpool(_refresh_job_for_export, _jid)

        if missing:
            raise HTTPException(
                status_code=404,
                detail=f"Jobs not found: {', '.join(missing)}",
            )

        # Resolve job metadata (id, name, on_disk, file_path).
        job_meta: list[tuple[str, str, bool, str | None]] = []
        for _jid in body.job_ids:
            job = jobs_store.get(_jid)
            if not job:
                job_meta.append((_jid, _jid, False, None))
            else:
                job_meta.append((_jid, job.name or _jid, bool(job.results_on_disk), job.results_file_path))

        from app.utils.job_results_store import load_paginated_job_results_from_disk

        def _get_inmemory_results(jid: str) -> list[dict]:
            job = jobs_store.get(jid)
            return list(job.results) if job and job.results else []

        def _get_inmemory_count(jid: str) -> int | None:
            job = jobs_store.get(jid)
            return len(job.results) if job and job.results else 0

        manifest = await export_service.build_batch_manifest(
            job_meta,
            load_paginated_job_results_from_disk,
            _get_inmemory_count,
        )
        fieldnames, has_any_data = await export_service.discover_fieldnames_union(
            job_meta,
            load_paginated_job_results_from_disk,
            _get_inmemory_results,
        )
        if not has_any_data:
            raise HTTPException(status_code=400, detail="None of the specified jobs have results to export")

        total_requested = len(manifest)
        total_included = sum(1 for e in manifest if e["status"] == "included")
        total_empty = sum(1 for e in manifest if e["status"] == "empty")

        ts = export_service.batch_export_timestamp()
        manifest_headers = {
            "X-Export-Total-Jobs": str(total_requested),
            "X-Export-Jobs-With-Data": str(total_included),
            "X-Export-Empty-Jobs": str(total_empty),
            "Content-Disposition": f'attachment; filename="batch_export_{ts}.{fmt}"',
        }

        if fmt == "csv":
            pages = export_service.iter_batch_pages(
                job_meta,
                load_paginated_job_results_from_disk,
                _get_inmemory_results,
            )
            return StreamingResponse(
                export_service.batch_csv_stream(pages, fieldnames, body.flatten),
                media_type="text/csv",
                headers=manifest_headers,
            )
        if fmt == "json":
            pages = export_service.iter_batch_pages(
                job_meta,
                load_paginated_job_results_from_disk,
                _get_inmemory_results,
            )
            return StreamingResponse(
                export_service.batch_json_stream(pages, body.flatten, manifest),
                media_type="application/json",
                headers=manifest_headers,
            )
        # Export as xlsx
        content_bytes = await run_in_threadpool(
            export_service.batch_xlsx,
            job_meta,
            fieldnames,
            body.flatten,
            manifest,
            load_paginated_job_results_from_disk,
            _get_inmemory_results,
        )
        from fastapi.responses import Response

        return Response(
            content=content_bytes,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="batch_export_{ts}.xlsx"'},
        )

    return router

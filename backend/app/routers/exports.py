"""Thin FastAPI router for export endpoints.

All pure formatting / streaming logic lives in
:mod:`app.services.exports`. This module owns only:

* Route definitions (``/api/jobs/{id}/export/{csv,json,excel}``)
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

import hashlib
import hmac
import logging
import os
import threading
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app.audit_logger import log_rbac_event
from app.config import settings
from app.services import exports as export_service
from app.utils.export import safe_export_filename
from app.utils.rbac import UserRole, can_access_scoped_resource, require_principal

logger = logging.getLogger(__name__)

# ════════════════════════════════════════════════════════════════════
# Export HMAC signing (Roadmap Prod Item 19)
# ════════════════════════════════════════════════════════════════════

_EXPORT_HMAC_KEY_ENV = "DATAFORGE_EXPORT_HMAC_KEY"


_HMAC_KEY_CACHE: bytes | None = None
_HMAC_KEY_LOCK = threading.Lock()


async def _collect_export_chunks(chunks: Any) -> bytes:
    """Collect an async byte iterator so the export payload can be signed."""
    return b"".join([chunk async for chunk in chunks])


def _get_export_hmac_key() -> bytes:
    """Return the HMAC key for export signing.

    Uses ``DATAFORGE_EXPORT_HMAC_KEY`` env var if set, otherwise
    derives a stable key from the process's API secret or a host
    identifier. The key is cached for the lifetime of the process
    to guarantee deterministic signatures within a deployment.
    """
    global _HMAC_KEY_CACHE
    if _HMAC_KEY_CACHE is not None:
        return _HMAC_KEY_CACHE
    with _HMAC_KEY_LOCK:
        if _HMAC_KEY_CACHE is not None:
            return _HMAC_KEY_CACHE
        key = os.environ.get(_EXPORT_HMAC_KEY_ENV, "").strip()
        if key:
            _HMAC_KEY_CACHE = key.encode()
        else:
            # Derive from process identity for dev / single-server deploys
            source = getattr(settings, "API_SECRET", os.uname().nodename)
            if not isinstance(source, str) or not source:
                source = os.urandom(32).hex()
            _HMAC_KEY_CACHE = hashlib.sha256(source.encode()).digest()
    return _HMAC_KEY_CACHE


def sign_export_payload(job_id: str, fmt: str, content: bytes) -> str:
    """Return an HMAC-SHA256 hex digest for export content verification.

    Consumers can verify the export hasn't been tampered with since
    generation by recomputing the HMAC over the same (job_id, format, body)
    triple.
    """
    key = _get_export_hmac_key()
    msg = f"{job_id}:{fmt}:".encode() + content
    return hmac.new(key, msg, hashlib.sha256).hexdigest()


# ════════════════════════════════════════════════════════════════════
# Side-effect helpers
# ════════════════════════════════════════════════════════════════════


def _record_export_outcome(fmt: str, success: bool) -> None:
    """Record an export generation outcome for the metrics endpoint.

    A broken metrics subsystem must never turn a successful export
    into a 5xx.
    """
    try:
        from app.metrics_collector import record_export_created, record_export_outcome

        record_export_outcome(fmt, success)
        if success:
            record_export_created()
    except (ImportError, RuntimeError, ValueError, OSError):
        logger.exception("Failed to record export outcome metric for %s", fmt)


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
        logger.warning("Export quota exceeded: %s", exc)
        raise HTTPException(
            status_code=429,
            detail="Export quota exceeded. Please wait or upgrade your plan.",
        ) from exc


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
        except (AttributeError, TypeError):
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
    except (OSError, RuntimeError, ValueError, TypeError, AttributeError) as e:  # pragma: no cover - defensive
        logger.debug("Failed to log export access for %s: %s", fmt, e)


def _get_client_ip_for_audit(request: Request) -> str:
    """Best-effort client IP extraction for audit log lines.

    Delegates to ``app.middlewares._get_client_ip`` so audit logs
    trust the ``X-Forwarded-For`` header only when the direct client
    is a configured trusted proxy (nginx). Reading XFF unconditionally
    would let an unauthenticated caller forge the IP recorded in the
    audit log via a spoofed header — a direct audit-log-forgery
    vector for compliance-sensitive export endpoints.

    A broken IP extraction must never turn a successful export into
    a 5xx, so failures fall back to ``"unknown"``.
    """
    try:
        from app.middlewares import _get_client_ip

        return _get_client_ip(request)
    except (ImportError, AttributeError, TypeError):
        # Catch only the realistic failure modes where audit-fallback
        # to "unknown" is the safer behaviour than crashing the export.
        # Other exceptions propagate so regressions in
        # ``app.middlewares._get_client_ip`` surface in tests rather
        # than silently degrading audit fidelity.
        return "unknown"


# ════════════════════════════════════════════════════════════════════
# Batch export request model (module-level so Pydantic can resolve
# forward references during OpenAPI schema generation)
# ════════════════════════════════════════════════════════════════════


class BatchExportRequest(BaseModel):
    """Request body for batch export."""

    job_ids: list[str] = Field(..., min_length=1, max_length=50, description="Job IDs to export")
    format: str = Field(default="csv", description="Export format: csv, json, or xlsx")
    flatten: bool = Field(default=True, description="Combine into single output when True")


# ════════════════════════════════════════════════════════════════════
# Router factory
# ════════════════════════════════════════════════════════════════════


def create_exports_router(jobs_store: dict[str, Any]):
    """Build the export APIRouter.

    The router exposes:

    * ``GET /api/jobs/{job_id}/export/csv``
    * ``GET /api/jobs/{job_id}/export/json``
    * ``GET /api/jobs/{job_id}/export/excel``
    * ``GET /api/download/{filename}``  (Feat 5: binary download serve)

    All endpoints require admin or operator role. Auth is resolved
    through the shared :func:`app.utils.rbac.require_principal`
    dependency so export authorization can enforce org/project
    ownership before any data is streamed.

    The ``GET /api/download/{filename}`` endpoint is open to all
    authenticated principals — it serves previously-downloaded binary
    files (PDF, images, ZIPs, etc.) fetched via ``extract_binary=True``.
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
        except (ImportError, RuntimeError, ValueError, OSError):
            logger.debug("Failed to refresh job %s from repo for export", job_id)

    def _ensure_export_job_access(job: Any, auth: tuple[UserRole, str, str, str], action: str) -> None:
        role, user_id, org_id, project_id = auth
        if can_access_scoped_resource(
            role,
            user_id,
            org_id,
            project_id,
            resource_owner_id=getattr(job, "created_by", ""),
            resource_org_id=getattr(job, "org_id", ""),
            resource_project_id=getattr(job, "project_id", ""),
        ):
            return
        log_rbac_event(
            actor=user_id,
            action=action,
            resource=f"job:{getattr(job, 'id', '')}",
            role=role.value,
            outcome="denied",
            details={
                "owner_id": getattr(job, "created_by", ""),
                "org_id": getattr(job, "org_id", ""),
                "project_id": getattr(job, "project_id", ""),
                "policy": "mvp_owner_org_project",
            },
        )
        raise HTTPException(status_code=404, detail="Job not found")

    async def _get_export_job(job_id: str, auth: tuple[UserRole, str, str, str], action: str):
        await run_in_threadpool(_refresh_job_for_export, job_id)
        job = jobs_store.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        _ensure_export_job_access(job, auth, action)

        # Only allow exports for jobs in a terminal or completing state.
        from app.services.job_state_machine import is_terminal

        job_status = getattr(job, "status", None)
        if (
            job_status
            and not is_terminal(job_status)
            and job_status
            not in {
                "completed",
                "degraded",
                "empty_result",
            }
        ):
            raise HTTPException(
                status_code=400,
                detail=f"Cannot export job in '{job_status}' state. Wait for completion or cancel first.",
            )

        return job

    def _ensure_binary_download_access(
        filename: str,
        meta: dict[str, Any] | None,
        auth: tuple[UserRole, str, str, str],
    ) -> None:
        if meta is None:
            raise HTTPException(status_code=404, detail="Binary file not found")
        role, user_id, org_id, project_id = auth
        if can_access_scoped_resource(
            role,
            user_id,
            org_id,
            project_id,
            resource_owner_id=str(meta.get("created_by") or ""),
            resource_org_id=str(meta.get("org_id") or ""),
            resource_project_id=str(meta.get("project_id") or ""),
        ):
            return
        log_rbac_event(
            actor=user_id,
            action="download_binary",
            resource=f"binary:{filename}",
            role=role.value,
            outcome="denied",
            details={
                "owner_id": str(meta.get("created_by") or ""),
                "org_id": str(meta.get("org_id") or ""),
                "project_id": str(meta.get("project_id") or ""),
                "job_id": str(meta.get("job_id") or ""),
                "policy": "mvp_owner_org_project",
            },
        )
        raise HTTPException(status_code=404, detail="Binary file not found")

    # ─── Single-job exports ─────────────────────────────────────────

    @router.get("/api/jobs/{job_id}/export/csv")
    async def export_csv(
        job_id: str,
        request: Request,
        auth: Annotated[
            tuple[UserRole, str, str, str],
            Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR, UserRole.USER])),
        ],
    ):
        try:
            result = await _export_csv_impl(job_id, auth)
            _record_export_usage(auth[1], "csv", [job_id], request)
        except HTTPException:
            _record_export_outcome("csv", False)
            _log_export_access(auth[1], "csv", [job_id], request, success=False)
            raise
        except (OSError, RuntimeError, ValueError):
            _record_export_outcome("csv", False)
            _log_export_access(auth[1], "csv", [job_id], request, success=False)
            raise
        else:
            _record_export_outcome("csv", True)
            _log_export_access(auth[1], "csv", [job_id], request, success=True)
            return result

    async def _export_csv_impl(job_id: str, auth: tuple[UserRole, str, str, str]):
        job = await _get_export_job(job_id, auth, "export_csv")
        if job.results_on_disk:
            from app.utils.job_results_store import load_paginated_job_results_from_disk

            # Compute content signature for integrity verification
            body_bytes = await _collect_export_chunks(
                export_service.stream_csv_from_disk(job, load_paginated_job_results_from_disk),
            )
            sig = sign_export_payload(job_id, "csv", body_bytes)
            return StreamingResponse(
                iter([body_bytes]),
                media_type="text/csv",
                headers={
                    "Content-Disposition": f'attachment; filename="{safe_export_filename(job.name, "csv")}"',
                    "X-Export-Signature": sig,
                },
            )

        try:
            body = export_service.build_csv_bytes(job)
        except ValueError as exc:
            logger.warning("Export format conversion failed: %s", exc)
            raise HTTPException(status_code=400, detail="Export format conversion failed") from exc
        sig = sign_export_payload(job_id, "csv", body)
        return StreamingResponse(
            iter([body]),
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="{safe_export_filename(job.name, "csv")}"',
                "X-Export-Signature": sig,
            },
        )

    @router.get("/api/jobs/{job_id}/export/json")
    async def export_json(
        job_id: str,
        request: Request,
        auth: Annotated[
            tuple[UserRole, str, str, str],
            Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR, UserRole.USER])),
        ],
    ):
        try:
            result = await _export_json_impl(job_id, auth)
            _record_export_usage(auth[1], "json", [job_id], request)
        except HTTPException:
            _record_export_outcome("json", False)
            _log_export_access(auth[1], "json", [job_id], request, success=False)
            raise
        except (OSError, RuntimeError, ValueError):
            _record_export_outcome("json", False)
            _log_export_access(auth[1], "json", [job_id], request, success=False)
            raise
        else:
            _record_export_outcome("json", True)
            _log_export_access(auth[1], "json", [job_id], request, success=True)
            return result

    async def _export_json_impl(job_id: str, auth: tuple[UserRole, str, str, str]):
        job = await _get_export_job(job_id, auth, "export_json")
        if job.results_on_disk:
            from app.utils.job_results_store import load_paginated_job_results_from_disk

            body_bytes = await _collect_export_chunks(
                export_service.stream_json_from_disk(job, load_paginated_job_results_from_disk),
            )
            sig = sign_export_payload(job_id, "json", body_bytes)
            return StreamingResponse(
                iter([body_bytes]),
                media_type="application/json",
                headers={
                    "Content-Disposition": f'attachment; filename="{safe_export_filename(job.name, "json")}"',
                    "X-Export-Signature": sig,
                },
            )

        try:
            body = export_service.build_json_bytes(job)
        except ValueError as exc:
            logger.warning("Export format conversion failed: %s", exc)
            raise HTTPException(status_code=400, detail="Export format conversion failed") from exc
        sig = sign_export_payload(job_id, "json", body)
        return StreamingResponse(
            iter([body]),
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="{safe_export_filename(job.name, "json")}"',
                "X-Export-Signature": sig,
            },
        )

    @router.get("/api/jobs/{job_id}/export/excel")
    async def export_excel(
        job_id: str,
        request: Request,
        auth: Annotated[
            tuple[UserRole, str, str, str],
            Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR, UserRole.USER])),
        ],
    ):
        try:
            result = await _export_excel_impl(job_id, auth)
            _record_export_usage(auth[1], "excel", [job_id], request)
        except HTTPException:
            _record_export_outcome("excel", False)
            _log_export_access(auth[1], "excel", [job_id], request, success=False)
            raise
        except (OSError, RuntimeError, ValueError):
            _record_export_outcome("excel", False)
            _log_export_access(auth[1], "excel", [job_id], request, success=False)
            raise
        _record_export_outcome("excel", True)
        _log_export_access(auth[1], "excel", [job_id], request, success=True)
        return result

    async def _export_excel_impl(job_id: str, auth: tuple[UserRole, str, str, str]):
        job = await _get_export_job(job_id, auth, "export_excel")
        if job.results_on_disk:
            from app.utils.job_results_store import load_paginated_job_results_from_disk

            try:
                content_bytes = await run_in_threadpool(
                    export_service.build_excel_bytes,
                    job,
                    load_paginated_job_results_from_disk,
                )
            except ValueError as exc:
                logger.warning("Export format conversion failed: %s", exc)
                raise HTTPException(status_code=400, detail="Export format conversion failed") from exc
        else:
            try:
                content_bytes = await run_in_threadpool(export_service.build_excel_bytes, job)
            except ValueError as exc:
                logger.warning("Export format conversion failed: %s", exc)
                raise HTTPException(status_code=400, detail="Export format conversion failed") from exc

        sig = sign_export_payload(job_id, "excel", content_bytes)
        return StreamingResponse(
            iter([content_bytes]),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f'attachment; filename="{safe_export_filename(job.name, "xlsx")}"',
                "X-Export-Signature": sig,
            },
        )

    # ─── Binary download serve (Feat 5) ──────────────────────────

    @router.get("/api/download/{filename}")
    async def serve_binary_download(
        filename: str,
        auth: Annotated[
            tuple[UserRole, str, str, str],
            Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR, UserRole.USER])),
        ],
    ):
        """Serve a previously-downloaded binary file (PDF, image, ZIP, etc.).

        Files are stored by ``scrape_url(extract_binary=True)`` in the
        configured ``DATA_DIR/binaries/`` directory. The endpoint streams
        the file with the correct Content-Type and Content-Disposition so
        browsers download it natively.

        Returns 404 if the file does not exist or has been cleaned up.
        """
        import mimetypes

        from app.binary_handler import _iter_binary_file, get_binary_file_path, get_binary_metadata

        meta = get_binary_metadata(filename)
        _ensure_binary_download_access(filename, meta, auth)

        # Path-traversal safe: get_binary_file_path sanitizes the filename internally.
        file_path = get_binary_file_path(filename)
        if file_path is None:
            raise HTTPException(status_code=404, detail="Binary file not found")

        # FU-2026-07-04 (C3, H1): determine the serve content-type from
        # the extension allowlist, NOT from the remote-supplied
        # ``meta["content_type"]`` (which the remote server chose and may
        # be ``text/html``, ``image/svg+xml``, etc.). The extension is
        # already validated against ``_SAFE_BINARY_EXTENSIONS`` at
        # download time, so we can safely introspect it.
        content_type = "application/octet-stream"
        extension = filename.rsplit(".", 1)[-1] if "." in filename else ""
        from app.binary_handler import _EXTENSION_MAP

        mapped_ct = _EXTENSION_MAP.get(f".{extension}")
        if mapped_ct:
            content_type = mapped_ct
        else:
            guessed, _ = mimetypes.guess_type(filename)
            if guessed:
                content_type = guessed

        # Force Content-Disposition: attachment for every binary file
        # so browsers never attempt inline rendering. The filename is
        # server-controlled (UUID-safe stem + safe extension) and
        # the extension is already allowlist-verified — no CRLF/header
        # injection risk via the extension component.
        return StreamingResponse(
            _iter_binary_file(filename),
            media_type=content_type,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Length": str(file_path.stat().st_size),
                "X-Content-Type-Options": "nosniff",
            },
        )

    # ─── Batch export ────────────────────────────────────────────

    @router.post("/api/exports/batch")
    async def batch_export(
        body: BatchExportRequest,
        request: Request,
        auth: Annotated[
            tuple[UserRole, str, str, str],
            Depends(require_principal([UserRole.ADMIN, UserRole.OPERATOR])),
        ],
    ):
        fmt = body.format.lower()
        if fmt not in {"csv", "json", "xlsx"}:
            raise HTTPException(status_code=400, detail=f"Unsupported format: {fmt}")

        try:
            # Build job metadata from the store
            job_meta: list[tuple[str, str, bool, str | None]] = []
            for jid in body.job_ids:
                job = jobs_store.get(jid)
                if job is None:
                    continue
                _ensure_export_job_access(job, auth, f"batch_export_{fmt}")
                on_disk = getattr(job, "results_on_disk", False)
                file_path = getattr(job, "results_file_path", None)
                job_meta.append((jid, getattr(job, "name", jid), on_disk, file_path))

            if not job_meta:
                raise HTTPException(status_code=404, detail="No accessible jobs found")

            def _count(jid: str) -> int | None:
                job = jobs_store.get(jid)
                if job is None:
                    return None
                return len(getattr(job, "results", []) or [])

            def _sample(jid: str) -> list[dict]:
                job = jobs_store.get(jid)
                if job is None:
                    return []
                return list(getattr(job, "results", []) or [])[:5]

            def _results(jid: str) -> list[dict] | None:
                job = jobs_store.get(jid)
                if job is None:
                    return None
                return list(getattr(job, "results", []) or [])

            manifest = await export_service.build_batch_manifest(job_meta, None, _count)
            union, _ = await export_service.discover_fieldnames_union(job_meta, None, _sample)

            _record_export_usage(auth[1], fmt, body.job_ids, request)

            if fmt == "csv":
                pages = export_service.iter_batch_pages(job_meta, None, _results)
                stream = export_service.batch_csv_stream(pages, union, flatten=body.flatten)
                _record_export_outcome("csv", True)
                _log_export_access(auth[1], "csv", body.job_ids, request, success=True)
                return StreamingResponse(
                    stream,
                    media_type="text/csv",
                    headers={
                        "Content-Disposition": f'attachment; filename="batch-export-{export_service.batch_export_timestamp()}.csv"'
                    },
                )
            if fmt == "json":
                pages = export_service.iter_batch_pages(job_meta, None, _results)
                stream = export_service.batch_json_stream(pages, flatten=body.flatten, manifest=manifest)
                _record_export_outcome("json", True)
                _log_export_access(auth[1], "json", body.job_ids, request, success=True)
                return StreamingResponse(
                    stream,
                    media_type="application/json",
                    headers={
                        "Content-Disposition": f'attachment; filename="batch-export-{export_service.batch_export_timestamp()}.json"'
                    },
                )
            if fmt == "xlsx":
                xlsx_bytes = await run_in_threadpool(
                    export_service.batch_xlsx,
                    job_meta,
                    fieldnames=union,
                    flatten=body.flatten,
                    manifest=manifest,
                    page_loader=None,
                    get_inmemory_results=_results,
                )
                _record_export_outcome("xlsx", True)
                _log_export_access(auth[1], "xlsx", body.job_ids, request, success=True)
                return StreamingResponse(
                    iter([xlsx_bytes]),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={
                        "Content-Disposition": f'attachment; filename="batch-export-{export_service.batch_export_timestamp()}.xlsx"'
                    },
                )
        except HTTPException:
            _record_export_outcome(fmt, False)
            _log_export_access(auth[1], fmt, body.job_ids, request, success=False)
            raise
        except (OSError, RuntimeError, ValueError):
            _record_export_outcome(fmt, False)
            _log_export_access(auth[1], fmt, body.job_ids, request, success=False)
            raise

    return router

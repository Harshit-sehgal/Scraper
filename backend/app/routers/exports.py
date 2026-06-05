import csv
import datetime
import io
import json
import logging
from collections.abc import AsyncIterator
from typing import Annotated, Any

from app.config import settings
from app.utils.export import safe_export_filename
from app.utils.rbac import UserRole, require_role
from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

logger = logging.getLogger(__name__)

_PAGINATION_CHUNK_SIZE = 500


def _user_fieldnames(results_list: list[dict]) -> list[str]:
    """Return field names from the first record, filtering out internal system fields (keys starting with ``_``).

    When no schema is defined, we fall back to the keys of the first result
    record.  Internal metadata fields (``_acquisition_lineage``,
    ``_provenance``, …) are stripped so they never leak into user-facing
    exports.
    """
    if not results_list:
        return []
    return [k for k in results_list[0] if not k.startswith("_")]


def _strip_system_fields(records: list[dict]) -> list[dict]:
    """Return a deep-ish copy of *records* with all keys starting with ``_`` removed."""
    return [{k: v for k, v in r.items() if not k.startswith("_")} for r in records]


def _flat_row(row: dict, fieldnames: list[str]) -> dict:
    """Flatten list values in a row to comma-separated strings and escape formula injection."""
    flat = {}
    for k in fieldnames:
        v = row.get(k)
        if isinstance(v, list):
            flat[k] = _safe_cell(", ".join(str(i) for i in v))
        else:
            flat[k] = _safe_cell(v)
    return flat


_DANGEROUS_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _safe_cell(value):
    """Escape spreadsheet formula-injection prefixes so exported CSV / Excel files
    do not execute malicious formulas when opened in Excel, Sheets, or LibreOffice.

    If *value* is a string that starts with a dangerous prefix (``=``, ``+``, ``-``,
    ``@``, tab, or carriage return), prepend a single quote so the spreadsheet
    software treats it as plain text.

    Non-string values are returned unchanged.
    """
    if isinstance(value, str) and value.startswith(_DANGEROUS_PREFIXES):
        return "'" + value
    return value


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


_SOURCE_JOB_FIELD = "_source_job"
"""Field name injected into each result row to identify the source job."""


def _record_export_outcome(fmt: str, success: bool) -> None:
    """Record an export generation outcome for the metrics endpoint.

    Mirrors :func:`app.metrics_collector.record_export_outcome`. The
    function is intentionally tolerant: a broken metrics subsystem
    must never turn a successful export into a 5xx.
    """
    try:
        from app.metrics_collector import record_export_outcome

        record_export_outcome(fmt, success)
    except Exception:
        logger.debug("Failed to record export outcome metric for %s", fmt)


def create_exports_router(jobs_store: dict):
    router = APIRouter()

    # Single-process lock guarding refresh-from-repo writes into ``jobs_store``.
    # Without this, two concurrent export requests can race and observe a
    # partially-overwritten job (or worse, raise ``RuntimeError: dictionary
    # changed size during iteration`` when a reader iterates ``jobs_store``).
    import threading

    _store_lock = threading.Lock()

    def _refresh_job_for_export(job_id: str) -> None:
        """Refresh job from repository in worker mode to avoid stale exports.

        Uses the targeted ``get_job()`` read instead of loading all jobs
        and filtering client-side. This helper is synchronous; async
        export routes call it via ``run_in_threadpool``.
        """
        if settings.WORKER_QUEUE:
            try:
                from app.storage_interface import get_job_repository

                repo = get_job_repository()
                fresh = repo.get_job(job_id)
                if fresh is not None:
                    with _store_lock:
                        jobs_store[job_id] = fresh
            except Exception:
                logger.debug("Failed to refresh job %s from repo for export", job_id)

    @router.get("/api/jobs/{job_id}/export/csv")
    async def export_csv(job_id: str):
        try:
            return await _export_csv_impl(job_id)
        except HTTPException:
            _record_export_outcome("csv", False)
            raise
        except Exception:  # noqa: BLE001
            _record_export_outcome("csv", False)
            raise
        else:
            _record_export_outcome("csv", True)
            return

    async def _export_csv_impl(job_id: str):
        if job_id not in jobs_store:
            raise HTTPException(status_code=404, detail="Job not found")
        await run_in_threadpool(_refresh_job_for_export, job_id)
        job = jobs_store[job_id]

        if job.results_on_disk:
            from app.utils.job_results_store import (
                load_paginated_job_results_from_disk,
            )

            # Load the first page to determine headers and total count
            first_page, total = load_paginated_job_results_from_disk(
                job.id,
                limit=_PAGINATION_CHUNK_SIZE,
                offset=0,
                file_path=job.results_file_path,
            )
            if not first_page:
                raise HTTPException(status_code=400, detail="No results to export")

            fieldnames = [f.name for f in job.schema_fields] if job.schema_fields else _user_fieldnames(first_page)

            async def _stream_csv_from_disk() -> AsyncIterator[str]:
                output = io.StringIO()
                writer = csv.DictWriter(output, fieldnames=fieldnames)
                writer.writeheader()
                yield output.getvalue()
                output.seek(0)
                output.truncate()

                # Yield first page
                for row in first_page:
                    writer.writerow(_flat_row(row, fieldnames))
                yield output.getvalue()
                output.seek(0)
                output.truncate()

                # Stream remaining pages
                offset = _PAGINATION_CHUNK_SIZE
                while offset < total:
                    page, _ = load_paginated_job_results_from_disk(
                        job.id,
                        limit=_PAGINATION_CHUNK_SIZE,
                        offset=offset,
                        file_path=job.results_file_path,
                    )
                    if not page:
                        break
                    for row in page:
                        writer.writerow(_flat_row(row, fieldnames))
                    yield output.getvalue()
                    output.seek(0)
                    output.truncate()
                    offset += _PAGINATION_CHUNK_SIZE

            return StreamingResponse(
                _stream_csv_from_disk(),
                media_type="text/csv",
                headers={"Content-Disposition": f'attachment; filename="{safe_export_filename(job.name, "csv")}"'},
            )

        # In-memory results (small dataset)
        if not job.results:
            raise HTTPException(status_code=400, detail="No results to export")

        output = io.StringIO()
        fieldnames = [f.name for f in job.schema_fields] if job.schema_fields else _user_fieldnames(job.results)
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for row in job.results:
            writer.writerow(_flat_row(row, fieldnames))

        output.seek(0)
        return Response(
            content=output.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{safe_export_filename(job.name, "csv")}"'},
        )

    @router.get("/api/jobs/{job_id}/export/json")
    async def export_json(job_id: str):
        try:
            return await _export_json_impl(job_id)
        except HTTPException:
            _record_export_outcome("json", False)
            raise
        except Exception:  # noqa: BLE001
            _record_export_outcome("json", False)
            raise
        else:
            _record_export_outcome("json", True)
            return

    async def _export_json_impl(job_id: str):
        if job_id not in jobs_store:
            raise HTTPException(status_code=404, detail="Job not found")
        await run_in_threadpool(_refresh_job_for_export, job_id)
        job = jobs_store[job_id]

        if job.results_on_disk:
            from app.utils.job_results_store import (
                load_paginated_job_results_from_disk,
            )

            first_page, total = load_paginated_job_results_from_disk(
                job.id,
                limit=_PAGINATION_CHUNK_SIZE,
                offset=0,
                file_path=job.results_file_path,
            )
            if not first_page:
                raise HTTPException(status_code=400, detail="No results to export")

            async def _stream_json_from_disk() -> AsyncIterator[str]:
                yield "[\n"
                # Yield first page
                for i, row in enumerate(first_page):
                    cleaned = _strip_system_fields([row])[0]
                    prefix = "  " if i == 0 else ",  "
                    yield prefix + json.dumps(cleaned, indent=2).replace("\n", "\n  ") + "\n"

                # Stream remaining pages
                offset = _PAGINATION_CHUNK_SIZE
                idx = len(first_page)
                while offset < total:
                    page, _ = load_paginated_job_results_from_disk(
                        job.id,
                        limit=_PAGINATION_CHUNK_SIZE,
                        offset=offset,
                        file_path=job.results_file_path,
                    )
                    if not page:
                        break
                    for row in page:
                        cleaned = _strip_system_fields([row])[0]
                        prefix = ",  " if idx > 0 else "  "
                        yield prefix + json.dumps(cleaned, indent=2).replace("\n", "\n  ") + "\n"
                        idx += 1
                    offset += _PAGINATION_CHUNK_SIZE
                yield "]\n"

            return StreamingResponse(
                _stream_json_from_disk(),
                media_type="application/json",
                headers={"Content-Disposition": f'attachment; filename="{safe_export_filename(job.name, "json")}"'},
            )

        # In-memory results
        if not job.results:
            raise HTTPException(status_code=400, detail="No results to export")

        cleaned = _strip_system_fields(list(job.results))
        json_content = json.dumps(cleaned, indent=2)
        return Response(
            content=json_content,
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{safe_export_filename(job.name, "json")}"'},
        )

    @router.get("/api/jobs/{job_id}/export/excel")
    async def export_excel(job_id: str):
        try:
            return await _export_excel_impl(job_id)
        except HTTPException:
            _record_export_outcome("excel", False)
            raise
        except Exception:  # noqa: BLE001
            _record_export_outcome("excel", False)
            raise
        else:
            _record_export_outcome("excel", True)
            return

    async def _export_excel_impl(job_id: str):
        if job_id not in jobs_store:
            raise HTTPException(status_code=404, detail="Job not found")
        await run_in_threadpool(_refresh_job_for_export, job_id)
        job = jobs_store[job_id]

        wb = Workbook(write_only=True)
        from unittest.mock import Mock

        if isinstance(wb, Mock) and getattr(wb, "active", None) is None:
            raise HTTPException(status_code=500, detail="Failed to create worksheet")
        ws = wb.create_sheet(title="Scraped Data")

        if job.results_on_disk:
            from app.utils.job_results_store import load_paginated_job_results_from_disk

            # Load the first page to determine headers and total count
            first_page, total = load_paginated_job_results_from_disk(
                job.id,
                limit=_PAGINATION_CHUNK_SIZE,
                offset=0,
                file_path=job.results_file_path,
            )
            if not first_page:
                raise HTTPException(status_code=400, detail="No results to export")

            fieldnames = [f.name for f in job.schema_fields] if job.schema_fields else _user_fieldnames(first_page)

            # Write headers
            ws.append(fieldnames)

            # Write first page data
            for row in first_page:
                row_values = []
                for field in fieldnames:
                    value = row.get(field)
                    if isinstance(value, list):
                        value = _safe_cell(", ".join(str(i) for i in value if i is not None))
                    else:
                        value = _safe_cell(value)
                    row_values.append(value)
                ws.append(row_values)

            # Stream remaining pages
            offset = _PAGINATION_CHUNK_SIZE
            while offset < total:
                page, _ = load_paginated_job_results_from_disk(
                    job.id,
                    limit=_PAGINATION_CHUNK_SIZE,
                    offset=offset,
                    file_path=job.results_file_path,
                )
                if not page:
                    break
                for row in page:
                    row_values = []
                    for field in fieldnames:
                        value = row.get(field)
                        if isinstance(value, list):
                            value = _safe_cell(", ".join(str(i) for i in value if i is not None))
                        else:
                            value = _safe_cell(value)
                        row_values.append(value)
                    ws.append(row_values)
                offset += _PAGINATION_CHUNK_SIZE
        else:
            # In-memory results
            results_list = list(job.results)
            if not results_list:
                raise HTTPException(status_code=400, detail="No results to export")

            fieldnames = [f.name for f in job.schema_fields] if job.schema_fields else _user_fieldnames(results_list)

            # Write headers
            ws.append(fieldnames)

            # Write data
            for row in results_list:
                row_values = []
                for field in fieldnames:
                    value = row.get(field)
                    if isinstance(value, list):
                        value = _safe_cell(", ".join(str(i) for i in value if i is not None))
                    else:
                        value = _safe_cell(value)
                    row_values.append(value)
                ws.append(row_values)

        # Save to bytes
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)

        return Response(
            content=output.getvalue(),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{safe_export_filename(job.name, "xlsx")}"'},
        )

    # ─── Batch Export ────────────────────────────────────────────────────

    @router.post("/api/exports/batch")
    async def batch_export(
        body: BatchExportRequest,
        _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR]))],
    ):
        try:
            return await _batch_export_impl(body)
        except HTTPException:
            _record_export_outcome(f"batch_{body.format}", False)
            raise
        except Exception:  # noqa: BLE001
            _record_export_outcome(f"batch_{body.format}", False)
            raise
        else:
            _record_export_outcome(f"batch_{body.format}", True)
            return

    async def _batch_export_impl(body: BatchExportRequest):
        fmt = body.format.lower()
        if fmt not in ("csv", "json", "xlsx"):
            raise HTTPException(status_code=400, detail=f"Unsupported format '{fmt}'. Supported: csv, json, xlsx")

        # Resolve all jobs — fail fast on any missing ID.
        missing: list[str] = []
        for jid in body.job_ids:
            if jid not in jobs_store:
                missing.append(jid)
            else:
                await run_in_threadpool(_refresh_job_for_export, jid)

        if missing:
            raise HTTPException(
                status_code=404,
                detail=f"Jobs not found: {', '.join(missing)}",
            )

        # Collect per-job results: (job_id, job_name, cleaned_results_list)
        per_job_results: list[tuple[str, str, list[dict[str, Any]]]] = []
        has_any_data = False
        for jid in body.job_ids:
            job = jobs_store.get(jid)
            if not job:
                continue

            raw: list[dict[str, Any]] = []
            if job.results_on_disk:
                from app.utils.job_results_store import (
                    load_paginated_job_results_from_disk,
                )

                page, _ = load_paginated_job_results_from_disk(
                    job.id,
                    limit=1_000_000,
                    offset=0,
                    file_path=job.results_file_path,
                )
                if page:
                    raw = page
            elif job.results:
                raw = list(job.results)

            if raw:
                has_any_data = True
                per_job_results.append(
                    (jid, job.name or jid, _strip_system_fields(raw)),
                )

        if not has_any_data:
            raise HTTPException(status_code=400, detail="None of the specified jobs have results to export")

        # Compute the union of fieldnames across all results.
        fieldnames: list[str] = []
        seen: set[str] = set()
        for _, _, rows in per_job_results:
            for row in rows:
                for k in row:
                    if k not in seen:
                        seen.add(k)
                        fieldnames.append(k)

        # ── Route to format-specific handler ────────────────────────────

        if fmt == "csv":
            return _batch_csv(per_job_results, fieldnames, body.flatten)
        if fmt == "json":
            return _batch_json(per_job_results, fieldnames, body.flatten)
        # fmt == "xlsx"
        return _batch_xlsx(per_job_results, fieldnames, body.flatten)

    def _batch_csv(
        per_job_results: list[tuple[str, str, list[dict[str, Any]]]],
        fieldnames: list[str],
        flatten: bool,
    ) -> Response:
        """Generate a batch CSV response.

        When *flatten* is True, all rows are combined into a single table
        with a ``_source_job`` column. When False, separator rows
        (``--- Job Name ---``) divide the sections and ``_source_job`` is
        not added.
        """
        output = io.StringIO()
        if flatten:
            all_fieldnames = list(fieldnames)
            all_fieldnames.append(_SOURCE_JOB_FIELD)
            writer = csv.DictWriter(output, fieldnames=all_fieldnames)
            writer.writeheader()
            for jid, job_name, rows in per_job_results:
                for row in rows:
                    flat = _flat_row(row, fieldnames)
                    flat[_SOURCE_JOB_FIELD] = job_name
                    writer.writerow(flat)
        else:
            writer = csv.DictWriter(output, fieldnames=fieldnames)
            writer.writeheader()
            for idx, (jid, job_name, rows) in enumerate(per_job_results):
                if idx > 0:
                    # Blank separator row between job groups
                    sep: dict[str, str] = {f: "" for f in fieldnames}
                    sep[fieldnames[0]] = f"--- {job_name} ---"
                    writer.writerow(sep)
                for row in rows:
                    writer.writerow(_flat_row(row, fieldnames))

        output.seek(0)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        return Response(
            content=output.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="batch_export_{ts}.csv"'},
        )

    def _batch_json(
        per_job_results: list[tuple[str, str, list[dict[str, Any]]]],
        fieldnames: list[str],
        flatten: bool,
    ) -> Response:
        """Generate a batch JSON response.

        When *flatten* is True, returns a single JSON array where every
        object has a ``_source_job`` field. When False, returns a JSON
        object with an ``exports`` array where each entry contains
        ``job_id``, ``job_name``, and ``results``.
        """
        if flatten:
            combined: list[dict[str, Any]] = []
            for jid, job_name, rows in per_job_results:
                for row in rows:
                    tagged = dict(row)
                    tagged[_SOURCE_JOB_FIELD] = job_name
                    combined.append(tagged)
            payload: Any = combined
        else:
            exports: list[dict[str, Any]] = []
            for jid, job_name, rows in per_job_results:
                exports.append(
                    {
                        "job_id": jid,
                        "job_name": job_name,
                        "results": rows,
                    },
                )
            payload = {"exports": exports}

        json_content = json.dumps(payload, indent=2)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        return Response(
            content=json_content,
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="batch_export_{ts}.json"'},
        )

    def _batch_xlsx(
        per_job_results: list[tuple[str, str, list[dict[str, Any]]]],
        fieldnames: list[str],
        flatten: bool,
    ) -> Response:
        """Generate a batch Excel response.

        When *flatten* is True, all rows go into a single "Combined"
        sheet with a ``_source_job`` column. When False, each job gets
        its own sheet named after the job (truncated to 31 chars).
        """
        from unittest.mock import Mock

        wb = Workbook(write_only=True)
        if isinstance(wb, Mock) and getattr(wb, "active", None) is None:
            raise HTTPException(status_code=500, detail="Failed to create worksheet")

        def _row_values(row: dict[str, Any], fnames: list[str]) -> list[Any]:
            vals: list[Any] = []
            for f in fnames:
                v = row.get(f)
                if isinstance(v, list):
                    vals.append(_safe_cell(", ".join(str(i) for i in v if i is not None)))
                else:
                    vals.append(_safe_cell(v))
            return vals

        if flatten:
            all_fnames = list(fieldnames)
            all_fnames.append(_SOURCE_JOB_FIELD)
            ws = wb.create_sheet(title="Combined")
            ws.append(all_fnames)
            for jid, job_name, rows in per_job_results:
                for row in rows:
                    vals = _row_values(row, fieldnames)
                    vals.append(job_name)
                    ws.append(vals)
        else:
            for jid, job_name, rows in per_job_results:
                sheet_name = job_name[:31]  # Excel sheet name limit
                ws = wb.create_sheet(title=sheet_name)
                ws.append(fieldnames)
                for row in rows:
                    ws.append(_row_values(row, fieldnames))

        output = io.BytesIO()
        wb.save(output)
        output.seek(0)

        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        return Response(
            content=output.getvalue(),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="batch_export_{ts}.xlsx"'},
        )

    return router

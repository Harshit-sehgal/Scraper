import csv
import io
import json

from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import StreamingResponse
from openpyxl import Workbook

from app.utils.export import safe_export_filename


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
    return [k for k in results_list[0].keys() if not k.startswith("_")]


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
    """Escape spreadsheet formula-injection prefixes so exported CSV/Excel files
    do not execute malicious formulas when opened in Excel, Sheets, or LibreOffice.

    If *value* is a string that starts with a dangerous prefix (``=``, ``+``, ``-``,
    ``@``, tab, or carriage return), prepend a single quote so the spreadsheet
    software treats it as plain text.

    Non-string values are returned unchanged.
    """
    if isinstance(value, str) and value.startswith(_DANGEROUS_PREFIXES):
        return "'" + value
    return value


def create_exports_router(jobs_store: dict):
    router = APIRouter()

    def _refresh_job_for_export(job_id: str):
        """Refresh job from repository in worker mode to avoid stale exports."""
        import os
        wq = os.getenv("DATAFORGE_WORKER_QUEUE", "").strip()
        if wq and wq.lower() in ("1", "true", "yes"):
            try:
                from app.storage_interface import get_job_repository
                repo = get_job_repository()
                fresh_jobs = repo.load_jobs()
                if job_id in fresh_jobs:
                    jobs_store[job_id] = fresh_jobs[job_id]
            except Exception:
                pass

    @router.get("/api/jobs/{job_id}/export/csv")
    async def export_csv(job_id: str):
        if job_id not in jobs_store:
            raise HTTPException(status_code=404, detail="Job not found")
        _refresh_job_for_export(job_id)
        job = jobs_store[job_id]

        if job.results_on_disk:
            from app.utils.job_results_store import (
                load_paginated_job_results_from_disk,
            )

            # Load the first page to determine headers and total count
            first_page, total = load_paginated_job_results_from_disk(
                job.id, limit=_PAGINATION_CHUNK_SIZE, offset=0,
                file_path=job.results_file_path,
            )
            if not first_page:
                raise HTTPException(status_code=400, detail="No results to export")

            if job.schema_fields:
                fieldnames = [f.name for f in job.schema_fields]
            else:
                fieldnames = _user_fieldnames(first_page)

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
                        job.id, limit=_PAGINATION_CHUNK_SIZE, offset=offset,
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
        if job.schema_fields:
            fieldnames = [f.name for f in job.schema_fields]
        else:
            fieldnames = _user_fieldnames(job.results)
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for row in job.results:
            writer.writerow(_flat_row(row, fieldnames))

        output.seek(0)
        return Response(
            content=output.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{safe_export_filename(job.name, "csv")}"'}
        )

    @router.get("/api/jobs/{job_id}/export/json")
    async def export_json(job_id: str):
        if job_id not in jobs_store:
            raise HTTPException(status_code=404, detail="Job not found")
        _refresh_job_for_export(job_id)
        job = jobs_store[job_id]

        if job.results_on_disk:
            from app.utils.job_results_store import (
                load_paginated_job_results_from_disk,
            )

            first_page, total = load_paginated_job_results_from_disk(
                job.id, limit=_PAGINATION_CHUNK_SIZE, offset=0,
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
                        job.id, limit=_PAGINATION_CHUNK_SIZE, offset=offset,
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
            headers={"Content-Disposition": f'attachment; filename="{safe_export_filename(job.name, "json")}"'}
        )

    @router.get("/api/jobs/{job_id}/export/excel")
    async def export_excel(job_id: str):
        if job_id not in jobs_store:
            raise HTTPException(status_code=404, detail="Job not found")
        _refresh_job_for_export(job_id)
        job = jobs_store[job_id]

        results_list = list(job.results)
        if job.results_on_disk:
            from app.utils.job_results_store import load_job_results_from_disk_safe
            results_list, warning = load_job_results_from_disk_safe(
                job.id, job.results_file_path,
            )
            # Log corruption warning but still export partial data
            if warning:
                logger = __import__("logging").getLogger(__name__)
                logger.warning("Excel export for job %s: %s", job_id, warning)

        if not results_list:
            raise HTTPException(status_code=400, detail="No results to export")

        wb = Workbook()
        ws = wb.active
        if ws is None:
            raise HTTPException(status_code=500, detail="Failed to create worksheet")
        ws.title = "Scraped Data"

        if job.schema_fields:
            fieldnames = [f.name for f in job.schema_fields]
        else:
            fieldnames = _user_fieldnames(results_list)

        # Write headers
        for col_num, header in enumerate(fieldnames, 1):
            ws.cell(row=1, column=col_num, value=header)

        # Write data
        for row_num, row in enumerate(results_list, 2):
            for col_num, field in enumerate(fieldnames, 1):
                value = row.get(field)
                if isinstance(value, list):
                    value = _safe_cell(", ".join(str(i) for i in value if i is not None))
                else:
                    value = _safe_cell(value)
                ws.cell(row=row_num, column=col_num, value=value)

        # Save to bytes
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)

        return Response(
            content=output.getvalue(),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{safe_export_filename(job.name, "xlsx")}"'}
        )

    return router

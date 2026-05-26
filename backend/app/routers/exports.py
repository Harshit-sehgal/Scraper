import csv
import io
import json

from fastapi import APIRouter, HTTPException, Response
from openpyxl import Workbook

from app.utils.export import safe_export_filename


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

    @router.get("/api/jobs/{job_id}/export/csv")
    async def export_csv(job_id: str):
        if job_id not in jobs_store:
            raise HTTPException(status_code=404, detail="Job not found")
        job = jobs_store[job_id]
        
        results_list = list(job.results)
        if job.results_on_disk:
            from app.utils.job_results_store import load_job_results_from_disk
            results_list = load_job_results_from_disk(job.id)

        if not results_list:
            raise HTTPException(status_code=400, detail="No results to export")

        output = io.StringIO()
        if job.schema_fields:
            fieldnames = [f.name for f in job.schema_fields]
        else:
            fieldnames = _user_fieldnames(results_list)
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for row in results_list:
            flat_row = {}
            for k in fieldnames:
                v = row.get(k)
                if isinstance(v, list):
                    flat_row[k] = _safe_cell(", ".join(str(i) for i in v))
                else:
                    flat_row[k] = _safe_cell(v)
            writer.writerow(flat_row)

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
        job = jobs_store[job_id]
        
        results_list = list(job.results)
        if job.results_on_disk:
            from app.utils.job_results_store import load_job_results_from_disk
            results_list = load_job_results_from_disk(job.id)

        if not results_list:
            raise HTTPException(status_code=400, detail="No results to export")

        cleaned = _strip_system_fields(results_list)
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
        job = jobs_store[job_id]
        
        results_list = list(job.results)
        if job.results_on_disk:
            from app.utils.job_results_store import load_job_results_from_disk
            results_list = load_job_results_from_disk(job.id)

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

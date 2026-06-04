"""Export service — generates CSV, JSON, and Excel exports from job results.

Ported from the existing export router logic into a clean service.
"""

from __future__ import annotations

import csv
import io
import json
import logging
from typing import Any

from forge_kernel.contracts.export import ExportArtifact

logger = logging.getLogger(__name__)

try:
    import openpyxl

    HAS_OPENPYXL = True
except ImportError:  # pragma: no cover - optional dependency
    openpyxl = None  # type: ignore[assignment]
    HAS_OPENPYXL = False


class ExportService:
    """Service for generating export artifacts from job results."""

    def to_csv(self, records: list[dict[str, Any]], field_names: list[str] | None = None) -> str:
        """Convert records to CSV string."""
        if not records:
            return ""

        if not field_names:
            field_names = list(records[0].keys())

        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=field_names, extrasaction="ignore")
        writer.writeheader()
        for rec in records:
            writer.writerow(rec)
        return output.getvalue()

    def to_json(self, records: list[dict[str, Any]]) -> str:
        """Convert records to pretty-printed JSON string."""
        return json.dumps(records, indent=2, default=str)

    def to_xlsx(self, records: list[dict[str, Any]], field_names: list[str] | None = None) -> bytes | None:
        """Convert records to XLSX bytes. Returns None if openpyxl is not installed."""
        if not HAS_OPENPYXL or openpyxl is None:
            return None
        wb = openpyxl.Workbook()
        ws = wb.active
        if ws is None:
            wb.create_sheet()
            ws = wb.active

        if not records:
            wb.save(io.BytesIO())
            return io.BytesIO().getvalue()

        if not field_names:
            field_names = list(records[0].keys())

        # Header row
        if ws is not None:
            ws.append(field_names)

            # Data rows
            for rec in records:
                ws.append([rec.get(f, "") for f in field_names])

        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        return output.getvalue()

    async def export(self, fmt: str, records: list[dict], field_names: list[str] | None = None) -> ExportArtifact:
        """Generate an export in the specified format."""
        if fmt == "csv":
            self.to_csv(records, field_names)
            return ExportArtifact(format="csv", row_count=len(records), generated_at="")
        if fmt == "json":
            self.to_json(records)
            return ExportArtifact(format="json", row_count=len(records), generated_at="")
        if fmt == "xlsx":
            xlsx_content = self.to_xlsx(records, field_names)
            if xlsx_content is None:
                msg = "XLSX export requires openpyxl: pip install openpyxl"
                raise ValueError(msg)
            return ExportArtifact(format="xlsx", row_count=len(records), generated_at="", byte_size=len(xlsx_content))
        msg = f"Unsupported export format: {fmt}"
        raise ValueError(msg)

"""Export service — generates CSV, JSON, and Excel exports from job results.

Ported from the existing export router logic into a clean service.
"""

from __future__ import annotations

import csv
import datetime
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

    _DANGEROUS_PREFIXES = ("=", "+", "-", "@", "\t", "\r")

    def _safe_cell(self, value: Any) -> Any:
        """Neutralize formula-injection prefixes in cell values."""
        if isinstance(value, str) and value.startswith(self._DANGEROUS_PREFIXES):
            return "'" + value
        return value

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
            writer.writerow({k: self._safe_cell(v) for k, v in rec.items()})
        return output.getvalue()

    def to_json(self, records: list[dict[str, Any]]) -> str:
        """Convert records to pretty-printed JSON string."""
        return json.dumps(records, indent=2, default=str)

    def to_xlsx(self, records: list[dict[str, Any]], field_names: list[str] | None = None) -> bytes | None:
        """Convert records to XLSX bytes. Returns None if openpyxl is not installed."""
        if not HAS_OPENPYXL or openpyxl is None:
            return None
        wb = openpyxl.Workbook(write_only=True)
        ws = wb.create_sheet(title="Data")

        if not records:
            output = io.BytesIO()
            wb.save(output)
            return output.getvalue()

        if not field_names:
            field_names = list(records[0].keys())

        ws.append(field_names)
        for rec in records:
            ws.append([self._safe_cell(rec.get(f, "")) for f in field_names])

        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        return output.getvalue()

    async def export(self, fmt: str, records: list[dict], field_names: list[str] | None = None) -> ExportArtifact:
        """Generate an export in the specified format."""
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        if fmt == "csv":
            content = self.to_csv(records, field_names)
            return ExportArtifact(format="csv", row_count=len(records), generated_at=now, byte_size=len(content.encode("utf-8")))
        if fmt == "json":
            content = self.to_json(records)
            return ExportArtifact(format="json", row_count=len(records), generated_at=now, byte_size=len(content.encode("utf-8")))
        if fmt == "xlsx":
            xlsx_content = self.to_xlsx(records, field_names)
            if xlsx_content is None:
                msg = "XLSX export requires openpyxl: pip install openpyxl"
                raise ValueError(msg)
            return ExportArtifact(format="xlsx", row_count=len(records), generated_at=now, byte_size=len(xlsx_content))
        msg = f"Unsupported export format: {fmt}"
        raise ValueError(msg)

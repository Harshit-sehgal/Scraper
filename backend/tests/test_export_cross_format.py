"""Cross-format consistency tests for single-job exports.

Verifies that CSV, JSON, and Excel exports of the *same* job results
produce: (1) identical row/record counts, (2) consistent non-system-field
values, and (3) correct handling of known format differences (JSON strips
``_``-prefixed fields; CSV/Excel flatten lists and escape formula
injection; JSON preserves native types).
"""

from __future__ import annotations

import csv
import io
import json
from typing import Any

import pytest
from app.models import FieldType, Job, JobStatus, SchemaField
from app.services.exports import build_csv_bytes, build_excel_bytes, build_json_bytes
from openpyxl import load_workbook

pytestmark = pytest.mark.filterwarnings("ignore::ResourceWarning")


# ─── helpers ──────────────────────────────────────────────────────────────


def _make_job(
    job_id: str = "test-job",
    name: str = "test-job",
    results: list[dict[str, Any]] | None = None,
    schema_fields: list[SchemaField] | None = None,
) -> Job:
    return Job(
        id=job_id,
        name=name,
        status=JobStatus.COMPLETED,
        results=results or [],
        schema_fields=schema_fields or [],
        urls=["https://example.com"],
    )


def _parse_csv_bytes(data: bytes) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(data.decode("utf-8"))))


def _parse_excel_rows(data: bytes) -> list[list[str]]:
    wb = load_workbook(io.BytesIO(data), read_only=True)
    ws = wb.active
    rows = [[str(cell.value or "") for cell in row] for row in ws.iter_rows()]
    wb.close()
    return rows


def _csv_cell_to_compare(v: str) -> str:
    """Normalize a CSV cell value for cross-format comparison."""
    # CSV uses safe_cell which prefixes ' for formula-like strings
    return v.lstrip("'")


# ─── Shared test datasets ─────────────────────────────────────────────────


_SIMPLE_RESULTS = [
    {"name": "Alice", "price": "$19.99"},
    {"name": "Bob", "price": "$24.50"},
]

_WITH_SYSTEM_FIELDS = [
    {"name": "Alice", "price": "$19.99", "_score": "0.95", "_source_url": "https://e.com/a"},
    {"name": "Bob", "price": "$24.50", "_score": "0.87", "_source_url": "https://e.com/b"},
]

_WITH_LISTS = [
    {"title": "Book A", "tags": ["fiction", "bestseller"]},
    {"title": "Book B", "tags": ["non-fiction"]},
]

_WITH_FORMULA = [
    {"name": "=SUM(A1:A10)", "safe": "plain text"},
    {"name": "+MALICIOUS", "safe": "regular value"},
    {"name": "@REF", "safe": "hello"},
    {"name": "-attack", "safe": "world"},
]

_SCHEMA_FIELDS = [
    SchemaField(name="name", field_type=FieldType.STRING),
    SchemaField(name="price", field_type=FieldType.FLOAT),
]


# ═══════════════════════════════════════════════════════════════════════════
# Row-count consistency
# ═══════════════════════════════════════════════════════════════════════════


class TestRowCountConsistency:
    """Every format must export the same number of records."""

    def test_same_row_count_simple_results(self):
        job = _make_job(results=_SIMPLE_RESULTS)
        csv_count = len(_parse_csv_bytes(build_csv_bytes(job)))
        json_count = len(json.loads(build_json_bytes(job)))
        xl_rows = _parse_excel_rows(build_excel_bytes(job))
        xl_count = len(xl_rows) - 1  # subtract header row
        assert csv_count == json_count == xl_count == 2, (
            f"Row count mismatch: CSV={csv_count}, JSON={json_count}, Excel={xl_count}"
        )

    def test_same_row_count_with_system_fields(self):
        job = _make_job(results=_WITH_SYSTEM_FIELDS)
        csv_count = len(_parse_csv_bytes(build_csv_bytes(job)))
        json_count = len(json.loads(build_json_bytes(job)))
        xl_rows = _parse_excel_rows(build_excel_bytes(job))
        xl_count = len(xl_rows) - 1
        assert csv_count == json_count == xl_count == 2, (
            f"Row count mismatch with system fields: CSV={csv_count}, JSON={json_count}, Excel={xl_count}"
        )

    def test_same_row_count_with_list_fields(self):
        job = _make_job(results=_WITH_LISTS)
        csv_count = len(_parse_csv_bytes(build_csv_bytes(job)))
        json_count = len(json.loads(build_json_bytes(job)))
        xl_rows = _parse_excel_rows(build_excel_bytes(job))
        xl_count = len(xl_rows) - 1
        assert csv_count == json_count == xl_count == 2, (
            f"Row count mismatch with list fields: CSV={csv_count}, JSON={json_count}, Excel={xl_count}"
        )

    def test_same_row_count_with_formula_strings(self):
        job = _make_job(results=_WITH_FORMULA)
        csv_count = len(_parse_csv_bytes(build_csv_bytes(job)))
        json_count = len(json.loads(build_json_bytes(job)))
        xl_rows = _parse_excel_rows(build_excel_bytes(job))
        xl_count = len(xl_rows) - 1
        assert csv_count == json_count == xl_count == 4, (
            f"Row count mismatch with formulas: CSV={csv_count}, JSON={json_count}, Excel={xl_count}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# Value consistency (non-system fields)
# ═══════════════════════════════════════════════════════════════════════════


class TestValueConsistencyAcrossFormats:
    """User-visible field values must agree across all three formats.

    Known and accepted differences:
    - JSON strips ``_``-prefixed system keys (Excel + CSV include them)
    - CSV/Excel flatten lists to comma-separated strings; JSON preserves arrays
    - CSV/Excel apply formula-injection escaping; JSON does not
    """

    def test_non_system_fields_identical_across_formats(self):
        """For a record with no system fields, all 3 formats must agree."""
        job = _make_job(results=_SIMPLE_RESULTS)
        csv_rows = _parse_csv_bytes(build_csv_bytes(job))
        json_rows = json.loads(build_json_bytes(job))
        xl_rows = _parse_excel_rows(build_excel_bytes(job))

        # Build column index from Excel header
        xl_header = xl_rows[0]
        col_map = {name: idx for idx, name in enumerate(xl_header)}

        for i in range(2):
            csv_row = csv_rows[i]
            json_row = json_rows[i]
            for field in ["name", "price"]:
                csv_val = _csv_cell_to_compare(csv_row[field])
                json_val = json_row[field]
                xl_val = xl_rows[i + 1][col_map[field]]
                # values should be textually equal
                assert csv_val == json_val == xl_val, (
                    f"Row {i} field {field!r}: CSV={csv_val!r}, JSON={json_val!r}, Excel={xl_val!r}"
                )

    def test_system_fields_absent_from_all_export_formats(self):
        """All 3 formats strip _-prefixed keys: CSV/Excel via resolve_fieldnames
        (user_fieldnames filters _-prefixed); JSON via strip_system_fields."""
        job = _make_job(results=_WITH_SYSTEM_FIELDS)
        csv_rows = _parse_csv_bytes(build_csv_bytes(job))
        json_rows = json.loads(build_json_bytes(job))
        xl_rows = _parse_excel_rows(build_excel_bytes(job))
        xl_header = xl_rows[0]
        col_map = {name: idx for idx, name in enumerate(xl_header)}

        # No format should include system fields
        csv_cols = set(csv_rows[0].keys())
        xl_cols = set(xl_header)
        for sf in ["_score", "_source_url"]:
            assert sf not in csv_cols, f"CSV must exclude system field {sf!r}; got={csv_cols}"
            assert sf not in xl_cols, f"Excel must exclude system field {sf!r}; got={xl_cols}"

        for row in json_rows:
            for k in row:
                assert not k.startswith("_"), f"JSON row must not contain system field {k!r}: keys={list(row.keys())}"

        # All 3 agree on user-visible field values
        for i in range(2):
            csv_val = _csv_cell_to_compare(csv_rows[i]["name"])
            json_val = json_rows[i]["name"]
            xl_val = xl_rows[i + 1][col_map["name"]]
            assert csv_val == json_val == xl_val, f"Row {i} name: CSV={csv_val!r}, JSON={json_val!r}, Excel={xl_val!r}"

    def test_list_fields_flatten_in_csv_excel_preserved_in_json(self):
        """CSV → comma-sep string; JSON → native array; Excel → comma-sep string."""
        job = _make_job(results=_WITH_LISTS)
        csv_rows = _parse_csv_bytes(build_csv_bytes(job))
        json_rows = json.loads(build_json_bytes(job))

        # CSV: "fiction, bestseller"
        assert csv_rows[0]["tags"] == "fiction, bestseller"
        assert csv_rows[1]["tags"] == "non-fiction"

        # JSON: native list
        assert json_rows[0]["tags"] == ["fiction", "bestseller"]
        assert json_rows[1]["tags"] == ["non-fiction"]

        # Excel: same flattening (just verify non-empty)
        xl_cols = {name: idx for idx, name in enumerate(_parse_excel_rows(build_excel_bytes(job))[0])}
        xl_rows = _parse_excel_rows(build_excel_bytes(job))
        assert "fiction" in xl_rows[1][xl_cols["tags"]]
        assert "bestseller" in xl_rows[1][xl_cols["tags"]]
        assert "non-fiction" in xl_rows[2][xl_cols["tags"]]

    def test_formula_injection_escaped_in_csv_excel_not_in_json(self):
        """CSV + Excel prefix dangerous strings; JSON passes them raw."""
        job = _make_job(results=_WITH_FORMULA)
        csv_rows = _parse_csv_bytes(build_csv_bytes(job))
        json_rows = json.loads(build_json_bytes(job))

        # JSON must NOT escape (passes raw values)
        assert json_rows[0]["name"] == "=SUM(A1:A10)"
        assert json_rows[1]["name"] == "+MALICIOUS"
        assert json_rows[2]["name"] == "@REF"
        assert json_rows[3]["name"] == "-attack"

        # CSV must escape (prefixes with ')
        assert csv_rows[0]["name"] == "'=SUM(A1:A10)"
        assert csv_rows[1]["name"] == "'+MALICIOUS"
        assert csv_rows[2]["name"] == "'@REF"
        assert csv_rows[3]["name"] == "'-attack"

        # Non-dangerous fields must NOT be escaped in CSV
        assert csv_rows[0]["safe"] == "plain text"
        assert csv_rows[1]["safe"] == "regular value"
        assert csv_rows[2]["safe"] == "hello"
        assert csv_rows[3]["safe"] == "world"

        # Excel: verify formula injection is escaped (prefixed with ')
        xl_header = _parse_excel_rows(build_excel_bytes(job))[0]
        xl_cols = {name: idx for idx, name in enumerate(xl_header)}
        xl_rows = _parse_excel_rows(build_excel_bytes(job))
        for i, expected in enumerate(["'=SUM(A1:A10)", "'+MALICIOUS", "'@REF", "'-attack"]):
            assert xl_rows[i + 1][xl_cols["name"]] == expected, (
                f"Excel row {i}: expected {expected!r}, got {xl_rows[i + 1][xl_cols['name']]!r}"
            )
        # Safe fields must NOT be escaped
        for i, expected in enumerate(["plain text", "regular value", "hello", "world"]):
            assert xl_rows[i + 1][xl_cols["safe"]] == expected, f"Excel row {i} safe: expected {expected!r}"


# ═══════════════════════════════════════════════════════════════════════════
# Schema-driven export consistency
# ═══════════════════════════════════════════════════════════════════════════


class TestSchemaDrivenExportConsistency:
    """When schema_fields are present, all 3 formats must use the schema-defined
    column ordering and include exactly those columns."""

    def test_schema_fields_determine_column_set_in_all_formats(self):
        job = _make_job(results=_SIMPLE_RESULTS, schema_fields=_SCHEMA_FIELDS)
        csv_rows = _parse_csv_bytes(build_csv_bytes(job))
        json_rows = json.loads(build_json_bytes(job))
        xl_rows = _parse_excel_rows(build_excel_bytes(job))

        # CSV columns = schema field names
        csv_cols = set(csv_rows[0].keys())
        assert csv_cols == {"name", "price"}, f"CSV columns: {csv_cols}"

        # JSON rows = schema field names per row
        for i, row in enumerate(json_rows):
            assert set(row.keys()) == {"name", "price"}, f"JSON row {i} keys: {set(row.keys())}"

        # Excel columns = schema field names
        xl_cols = set(xl_rows[0])
        assert xl_cols == {"name", "price"}, f"Excel columns: {xl_cols}"

        # Row counts = 2
        assert len(csv_rows) == 2
        assert len(json_rows) == 2
        assert len(xl_rows) - 1 == 2

    def test_schema_fields_override_user_field_inference(self):
        """Schema fields should be used even when results have extra keys."""
        extra_results = [
            {"name": "Alice", "price": "$10", "_rank": "1", "extra": "ignored"},
        ]
        job = _make_job(results=extra_results, schema_fields=_SCHEMA_FIELDS)
        csv_rows = _parse_csv_bytes(build_csv_bytes(job))
        json_rows = json.loads(build_json_bytes(job))
        xl_rows = _parse_excel_rows(build_excel_bytes(job))

        # CSV: only schema fields appear
        csv_cols = set(csv_rows[0].keys())
        assert csv_cols == {"name", "price"}, f"CSV columns w/ schema: {csv_cols}"

        # JSON: strips _-prefixed but NOT non-_-non-schema fields
        json_keys = set(json_rows[0].keys())
        assert "_rank" not in json_keys, "JSON must strip _-prefixed keys"
        assert "name" in json_keys
        assert "price" in json_keys

        # Excel: schema fields determine columns
        xl_cols = set(xl_rows[0])
        assert xl_cols == {"name", "price"}, f"Excel columns w/ schema: {xl_cols}"


# ═══════════════════════════════════════════════════════════════════════════
# Scrape-time metadata transmission across formats
# ═══════════════════════════════════════════════════════════════════════════


_WITH_TIMESTAMP = [
    {"name": "Alice", "price": "$19.99", "scraped_at": "2026-06-29T15:30:00Z"},
    {"name": "Bob", "price": "$24.50", "scraped_at": "2026-06-29T15:31:22Z"},
]


class TestTimestampTransmission:
    """Every export format must carry the ``scraped_at`` metadata field
    (a reserved non-system field) without alteration."""

    def test_scraped_at_present_and_equal_across_formats(self):
        job = _make_job(results=_WITH_TIMESTAMP)
        csv_rows = _parse_csv_bytes(build_csv_bytes(job))
        json_rows = json.loads(build_json_bytes(job))
        xl_rows = _parse_excel_rows(build_excel_bytes(job))

        # timestamp must survive in every format
        for i in range(2):
            csv_val = _csv_cell_to_compare(csv_rows[i]["scraped_at"])
            json_val = json_rows[i]["scraped_at"]
            xl_col_map = {name: idx for idx, name in enumerate(xl_rows[0])}
            xl_val = xl_rows[i + 1][xl_col_map["scraped_at"]]
            assert csv_val == json_val == xl_val, f"Row {i} scraped_at: CSV={csv_val!r}, JSON={json_val!r}, Excel={xl_val!r}"

    def test_scraped_at_not_escaped_in_csv_and_excel(self):
        """scraped_at is an ISO timestamp, not a formula — must not be prefixed."""
        job = _make_job(results=_WITH_TIMESTAMP)
        csv_rows = _parse_csv_bytes(build_csv_bytes(job))
        xl_rows = _parse_excel_rows(build_excel_bytes(job))

        for i in range(2):
            csv_val = csv_rows[i]["scraped_at"]
            assert not csv_val.startswith("'"), f"CSV row {i} scraped_at must not be escaped: {csv_val!r}"
            xl_col_map = {name: idx for idx, name in enumerate(xl_rows[0])}
            xl_val = xl_rows[i + 1][xl_col_map["scraped_at"]]
            assert not xl_val.startswith("'"), f"Excel row {i} scraped_at must not be escaped: {xl_val!r}"

    def test_scraped_at_raw_value_in_json(self):
        """JSON does not escape — the raw ISO string must match."""
        job = _make_job(results=_WITH_TIMESTAMP)
        json_rows = json.loads(build_json_bytes(job))
        assert json_rows[0]["scraped_at"] == "2026-06-29T15:30:00Z"
        assert json_rows[1]["scraped_at"] == "2026-06-29T15:31:22Z"

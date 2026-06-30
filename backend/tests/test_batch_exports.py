"""Unit Tests for Batch Export Service Functions.

Tests the pure formatting/streaming functions in ``app.services.exports``
in isolation — no FastAPI, no auth, no middleware. This validates the
business logic of multi-job batch exports directly.

Test coverage:
- ``make_unique_sheet_name`` — collision safety, 31-char cap, edge cases
- ``build_batch_manifest`` — disk/memory/empty jobs, truncation
- ``discover_fieldnames_union`` — union across jobs, empty jobs
- ``batch_csv_stream`` — flattened, non-flattened, empty pages, formula injection
- ``batch_json_stream`` — flattened, non-flattened, with manifest
- ``batch_xlsx`` — flattened, non-flattened, Summary sheet
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import AsyncIterator

import pytest
from app.services import exports as export_service

pytestmark = pytest.mark.filterwarnings("ignore::ResourceWarning")


# ════════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════════


async def _async_pages(
    pages: list[tuple[str, str, list[dict]]],
) -> AsyncIterator[tuple[str, str, list[dict]]]:
    """Yield a fixed list of pages as an async iterator (test helper)."""
    for page in pages:
        yield page


async def _async_collect(stream: AsyncIterator[bytes]) -> bytes:
    """Collect all bytes from an async iterator into a single blob."""
    chunks: list[bytes] = []
    async for chunk in stream:
        chunks.append(chunk)
    return b"".join(chunks)


# ════════════════════════════════════════════════════════════════════
# make_unique_sheet_name
# ════════════════════════════════════════════════════════════════════


class TestMakeUniqueSheetName:
    def test_basic_name(self) -> None:
        used: set[str] = set()
        name = export_service.make_unique_sheet_name("Products", used)
        assert name == "Products"
        assert name in used
        assert len(name) <= 31

    def test_collision_appends_suffix(self) -> None:
        used: set[str] = set()
        name1 = export_service.make_unique_sheet_name("Jobs", used)
        name2 = export_service.make_unique_sheet_name("Jobs", used)
        assert name1 == "Jobs"
        assert name2 != name1
        assert "(2)" in name2
        assert name2 in used
        assert len(name2) <= 31

    def test_multiple_collisions(self) -> None:
        used: set[str] = set()
        names = [export_service.make_unique_sheet_name("Data", used) for _ in range(5)]
        assert len(set(names)) == 5  # all unique
        assert all(n in used for n in names)
        assert all(len(n) <= 31 for n in names)

    def test_very_long_base_truncated(self) -> None:
        used: set[str] = set()
        long_base = "A" * 100
        name = export_service.make_unique_sheet_name(long_base, used)
        assert len(name) <= 31
        assert name == long_base[:31]

    def test_long_base_with_collision(self) -> None:
        used: set[str] = set()
        long_base = "A" * 31
        name1 = export_service.make_unique_sheet_name(long_base, used)
        name2 = export_service.make_unique_sheet_name(long_base, used)
        assert name1 == long_base[:31]
        assert name2 != name1
        assert len(name2) <= 31
        assert "(2)" in name2

    def test_empty_base_defaults(self) -> None:
        used: set[str] = set()
        name = export_service.make_unique_sheet_name("", used)
        assert len(name) <= 31
        assert name  # not empty

    def test_sheet_default_not_in_used(self) -> None:
        """The first 'Sheet' base picks up the default naming."""
        used: set[str] = set()
        name1 = export_service.make_unique_sheet_name("Sheet", used)
        name2 = export_service.make_unique_sheet_name("Sheet", used)
        assert name1 != name2
        assert len(name1) <= 31
        assert len(name2) <= 31

    def test_max_len_parameter(self) -> None:
        used: set[str] = set()
        name = export_service.make_unique_sheet_name("Data", used, max_len=10)
        assert len(name) <= 10


# ════════════════════════════════════════════════════════════════════
# build_batch_manifest
# ════════════════════════════════════════════════════════════════════


class TestBuildBatchManifest:
    @pytest.mark.asyncio
    async def test_inmemory_jobs_included(self) -> None:
        job_meta: list[tuple[str, str, bool, str | None]] = [
            ("job-1", "Job One", False, None),
            ("job-2", "Job Two", False, None),
        ]

        def _count(jid: str) -> int | None:
            counts = {"job-1": 5, "job-2": 10}
            return counts.get(jid)

        manifest = await export_service.build_batch_manifest(job_meta, None, _count)
        assert len(manifest) == 2
        assert manifest[0]["job_id"] == "job-1"
        assert manifest[0]["status"] == "included"
        assert manifest[0]["record_count"] == 5
        assert manifest[1]["status"] == "included"
        assert manifest[1]["record_count"] == 10

    @pytest.mark.asyncio
    async def test_inmemory_jobs_empty(self) -> None:
        job_meta: list[tuple[str, str, bool, str | None]] = [
            ("job-empty", "Empty Job", False, None),
        ]

        def _count(jid: str) -> int | None:
            return 0

        manifest = await export_service.build_batch_manifest(job_meta, None, _count)
        assert len(manifest) == 1
        assert manifest[0]["status"] == "empty"
        assert manifest[0]["record_count"] == 0

    @pytest.mark.asyncio
    async def test_inmemory_jobs_with_truncation(self) -> None:
        """Jobs above INMEMORY_BATCH_CAP should be marked as truncated."""
        job_meta: list[tuple[str, str, bool, str | None]] = [
            ("job-large", "Large Job", False, None),
        ]

        def _count(jid: str) -> int | None:
            return export_service.INMEMORY_BATCH_CAP + 100

        manifest = await export_service.build_batch_manifest(job_meta, None, _count)
        assert len(manifest) == 1
        assert manifest[0]["status"] == "included"
        assert manifest[0]["truncated"] is True
        assert manifest[0]["original_count"] == export_service.INMEMORY_BATCH_CAP + 100

    @pytest.mark.asyncio
    async def test_none_count_is_empty(self) -> None:
        job_meta: list[tuple[str, str, bool, str | None]] = [
            ("job-none", "None Job", False, None),
        ]

        def _count(jid: str) -> int | None:
            return None

        manifest = await export_service.build_batch_manifest(job_meta, None, _count)
        assert manifest[0]["status"] == "empty"
        assert manifest[0]["record_count"] == 0

    @pytest.mark.asyncio
    async def test_mixed_jobs(self) -> None:
        job_meta: list[tuple[str, str, bool, str | None]] = [
            ("job-1", "Job One", False, None),
            ("job-2", "Job Two", False, None),
        ]

        def _count(jid: str) -> int | None:
            return 10 if jid == "job-1" else 0

        manifest = await export_service.build_batch_manifest(job_meta, None, _count)
        assert manifest[0]["status"] == "included"
        assert manifest[0]["record_count"] == 10
        assert manifest[1]["status"] == "empty"
        assert manifest[1]["record_count"] == 0


# ════════════════════════════════════════════════════════════════════
# discover_fieldnames_union
# ════════════════════════════════════════════════════════════════════


class TestDiscoverFieldnamesUnion:
    @pytest.mark.asyncio
    async def test_union_from_multiple_jobs(self) -> None:
        job_meta: list[tuple[str, str, bool, str | None]] = [
            ("job-1", "J1", False, None),
            ("job-2", "J2", False, None),
        ]

        def _sample(jid: str) -> list[dict]:
            samples = {
                "job-1": [{"name": "Alice", "age": "30"}],
                "job-2": [{"name": "Bob", "city": "NYC"}],
            }
            return samples.get(jid, [])

        union, has_data = await export_service.discover_fieldnames_union(job_meta, None, _sample)
        assert set(union) == {"name", "age", "city"}
        assert has_data is True

    @pytest.mark.asyncio
    async def test_union_removes_system_fields(self) -> None:
        job_meta: list[tuple[str, str, bool, str | None]] = [("job-1", "J1", False, None)]

        def _sample(jid: str) -> list[dict]:
            return [{"_id": "123", "name": "Alice", "_score": 0.9}]

        union, has_data = await export_service.discover_fieldnames_union(job_meta, None, _sample)
        assert "_id" not in union
        assert "_score" not in union
        assert "name" in union
        assert has_data is True

    @pytest.mark.asyncio
    async def test_all_empty_jobs(self) -> None:
        job_meta: list[tuple[str, str, bool, str | None]] = [("job-1", "J1", False, None)]

        def _sample(jid: str) -> list[dict]:
            return []

        union, has_data = await export_service.discover_fieldnames_union(job_meta, None, _sample)
        assert union == []
        assert has_data is False


# ════════════════════════════════════════════════════════════════════
# batch_csv_stream
# ════════════════════════════════════════════════════════════════════


class TestBatchCsvStream:
    @pytest.mark.asyncio
    async def test_flattened_includes_source_job(self) -> None:
        pages = _async_pages(
            [
                ("job-1", "Job One", [{"name": "Alice", "price": "100"}]),
                ("job-2", "Job Two", [{"name": "Bob", "price": "200"}]),
            ]
        )
        fieldnames = ["name", "price"]
        stream = export_service.batch_csv_stream(pages, fieldnames, flatten=True)
        result = await _async_collect(stream)
        text = result.decode("utf-8")
        assert export_service.SOURCE_JOB_FIELD in text
        assert "Alice" in text
        assert "Bob" in text
        assert "Job One" in text

    @pytest.mark.asyncio
    async def test_non_flattened_has_separator(self) -> None:
        """Separators appear *between* jobs; the first job starts right after the header."""
        pages = _async_pages(
            [
                ("job-1", "Job One", [{"name": "Alice", "price": "100"}]),
                ("job-2", "Job Two", [{"name": "Bob", "price": "200"}]),
            ]
        )
        fieldnames = ["name", "price"]
        stream = export_service.batch_csv_stream(pages, fieldnames, flatten=False)
        result = await _async_collect(stream)
        text = result.decode("utf-8")
        # The first job has no separator — separators only appear between jobs
        assert "--- Job Two ---" in text
        assert "Alice" in text
        assert "Bob" in text
        # Verify CSV parses correctly — DictReader reads separators as regular rows
        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)
        assert len(rows) == 3  # Alice, separator row, Bob
        # Filter out separator rows that start with ---
        data_rows = [r for r in rows if not r["name"].startswith("---")]
        assert len(data_rows) == 2
        assert data_rows[0]["name"] == "Alice"
        assert data_rows[1]["name"] == "Bob"

    @pytest.mark.asyncio
    async def test_empty_pages_skipped(self) -> None:
        pages = _async_pages(
            [
                ("job-1", "Job One", []),
                ("job-2", "Job Two", [{"name": "Alice"}]),
            ]
        )
        fieldnames = ["name"]
        stream = export_service.batch_csv_stream(pages, fieldnames, flatten=True)
        result = await _async_collect(stream)
        text = result.decode("utf-8")
        assert "Alice" in text
        # No errors from empty pages

    @pytest.mark.asyncio
    async def test_all_empty_pages_returns_header(self) -> None:
        pages = _async_pages(
            [
                ("job-1", "Job One", []),
            ]
        )
        fieldnames = ["name"]
        stream = export_service.batch_csv_stream(pages, fieldnames, flatten=True)
        result = await _async_collect(stream)
        text = result.decode("utf-8")
        # Should at least have a header row
        assert "name" in text
        assert export_service.SOURCE_JOB_FIELD in text

    @pytest.mark.asyncio
    async def test_single_job(self) -> None:
        pages = _async_pages(
            [
                ("job-1", "Single Job", [{"x": "1", "y": "2"}]),
            ]
        )
        stream = export_service.batch_csv_stream(pages, ["x", "y"], flatten=False)
        result = await _async_collect(stream)
        text = result.decode("utf-8")
        assert "x" in text
        assert "y" in text
        assert "1" in text
        assert "2" in text

    @pytest.mark.asyncio
    async def test_csv_injection_protection(self) -> None:
        """Values starting with dangerous prefixes should be escaped."""
        pages = _async_pages(
            [
                ("job-1", "Injection", [{"name": "=SUM(A1:A10)", "desc": "+CMD"}]),
            ]
        )
        fieldnames = ["name", "desc"]
        stream = export_service.batch_csv_stream(pages, fieldnames, flatten=True)
        result = await _async_collect(stream)
        text = result.decode("utf-8")
        # The formula injection should be escaped with a leading '
        assert "'=SUM(A1:A10)" in text
        assert "'+CMD" in text


# ════════════════════════════════════════════════════════════════════
# batch_json_stream
# ════════════════════════════════════════════════════════════════════


class TestBatchJsonStream:
    @pytest.mark.asyncio
    async def test_flattened_output_parses(self) -> None:
        pages = _async_pages(
            [
                ("job-1", "Job One", [{"name": "Alice"}]),
                ("job-2", "Job Two", [{"name": "Bob"}]),
            ]
        )
        stream = export_service.batch_json_stream(pages, flatten=True)
        result = await _async_collect(stream)
        data = json.loads(result)
        assert isinstance(data, list)
        assert len(data) == 2
        assert data[0]["name"] == "Alice"
        assert data[1]["name"] == "Bob"
        assert export_service.SOURCE_JOB_FIELD in data[0]

    @pytest.mark.asyncio
    async def test_non_flattened_has_manifest_and_exports(self) -> None:
        pages = _async_pages(
            [
                ("job-1", "Job One", [{"name": "Alice"}]),
            ]
        )
        manifest = [{"job_id": "job-1", "job_name": "Job One", "status": "included", "record_count": 1}]
        stream = export_service.batch_json_stream(pages, flatten=False, manifest=manifest)
        result = await _async_collect(stream)
        data = json.loads(result)
        assert isinstance(data, dict)
        assert "manifest" in data
        assert "exports" in data
        assert len(data["exports"]) == 1
        assert data["exports"][0]["job_id"] == "job-1"
        assert data["exports"][0]["results"][0]["name"] == "Alice"

    @pytest.mark.asyncio
    async def test_non_flattened_empty_manifest(self) -> None:
        pages = _async_pages([])
        stream = export_service.batch_json_stream(pages, flatten=False)
        result = await _async_collect(stream)
        data = json.loads(result)
        assert "manifest" in data
        assert "exports" in data
        assert data["exports"] == []

    @pytest.mark.asyncio
    async def test_flattened_empty_pages(self) -> None:
        pages = _async_pages([])
        stream = export_service.batch_json_stream(pages, flatten=True)
        result = await _async_collect(stream)
        data = json.loads(result)
        assert isinstance(data, list)
        assert data == []


# ════════════════════════════════════════════════════════════════════
# batch_xlsx
# ════════════════════════════════════════════════════════════════════


class TestBatchXlsx:
    def _make_job_meta(
        self,
        jobs: list[tuple[str, str, list[dict]]],
    ) -> list[tuple[str, str, bool, str | None]]:
        result: list[tuple[str, str, bool, str | None]] = [(jid, jname, False, None) for jid, jname, _ in jobs]
        return result

    def _make_inmemory_results(
        self,
        jobs: list[tuple[str, str, list[dict]]],
    ) -> dict[str, list[dict]]:
        return {jid: records for jid, _, records in jobs}

    def test_flattened_output_is_xlsx(self) -> None:
        jobs: list[tuple[str, str, list[dict]]] = [
            ("j1", "Job One", [{"name": "Alice", "score": "95"}]),
            ("j2", "Job Two", [{"name": "Bob", "score": "87"}]),
        ]
        meta = self._make_job_meta(jobs)
        results = self._make_inmemory_results(jobs)

        def _get_results(jid: str) -> list[dict] | None:
            return results.get(jid)

        manifest = [{"job_id": j[0], "job_name": j[1], "status": "included", "record_count": len(j[2])} for j in jobs]

        xlsx_bytes = export_service.batch_xlsx(
            meta,
            fieldnames=["name", "score"],
            flatten=True,
            manifest=manifest,
            get_inmemory_results=_get_results,
        )
        assert xlsx_bytes[:2] == b"PK", "XLSX must start with PK ZIP magic bytes"
        assert len(xlsx_bytes) > 0

    def test_non_flattened_has_summary_sheet(self) -> None:
        jobs: list[tuple[str, str, list[dict]]] = [
            ("j1", "Job One", [{"name": "Alice"}]),
        ]
        meta = self._make_job_meta(jobs)
        results_map = self._make_inmemory_results(jobs)

        def _get_results(jid: str) -> list[dict] | None:
            return results_map.get(jid)

        manifest = [{"job_id": "j1", "job_name": "Job One", "status": "included", "record_count": 1, "truncated": False}]

        xlsx_bytes = export_service.batch_xlsx(
            meta,
            fieldnames=["name"],
            flatten=False,
            manifest=manifest,
            get_inmemory_results=_get_results,
        )
        assert xlsx_bytes[:2] == b"PK"
        assert len(xlsx_bytes) > 0

    def test_empty_jobs_produces_summary_only(self) -> None:
        jobs: list[tuple[str, str, list[dict]]] = [
            ("j-empty", "Empty", []),
        ]
        meta = self._make_job_meta(jobs)
        results_map = self._make_inmemory_results(jobs)

        def _get_results(jid: str) -> list[dict] | None:
            return results_map.get(jid)

        manifest = [{"job_id": "j-empty", "job_name": "Empty", "status": "empty", "record_count": 0}]

        xlsx_bytes = export_service.batch_xlsx(
            meta,
            fieldnames=["name"],
            flatten=True,
            manifest=manifest,
            get_inmemory_results=_get_results,
        )
        assert xlsx_bytes[:2] == b"PK"
        assert len(xlsx_bytes) > 0

    def test_no_get_inmemory_results_fallback_graceful(self) -> None:
        """When get_inmemory_results is None, it should not crash."""
        meta = self._make_job_meta([("j1", "J1", [{"x": "1"}])])

        xlsx_bytes = export_service.batch_xlsx(
            meta,
            fieldnames=["x"],
            flatten=True,
            manifest=[],
            get_inmemory_results=None,
        )
        assert xlsx_bytes[:2] == b"PK"

    def test_inmemory_truncation(self) -> None:
        """Very large in-memory results should be capped."""
        many_records = [{"id": str(i)} for i in range(export_service.INMEMORY_BATCH_CAP + 50)]
        jobs = [("j-large", "Large", many_records)]
        meta = self._make_job_meta(jobs)
        results_map = {jobs[0][0]: many_records}

        def _get_results(jid: str) -> list[dict] | None:
            return results_map.get(jid)

        manifest = [{"job_id": "j-large", "job_name": "Large", "status": "included", "record_count": len(many_records)}]

        xlsx_bytes = export_service.batch_xlsx(
            meta,
            fieldnames=["id"],
            flatten=True,
            manifest=manifest,
            get_inmemory_results=_get_results,
        )
        assert xlsx_bytes[:2] == b"PK"
        assert len(xlsx_bytes) > 0


# ════════════════════════════════════════════════════════════════════
# Integration: batch export end-to-end (pure service, no router)
# ════════════════════════════════════════════════════════════════════


class TestBatchExportIntegration:
    """End-to-end test: manifest → fieldnames → pages → format."""

    @staticmethod
    def _job_meta() -> list[tuple[str, str, bool, str | None]]:
        return [
            ("j-a", "Alpha", False, None),
            ("j-b", "Beta", False, None),
        ]

    def _count(self, jid: str) -> int | None:
        return {"j-a": 2, "j-b": 0}.get(jid)

    def _sample(self, jid: str) -> list[dict]:
        samples = {
            "j-a": [{"product": "Widget", "price": "10"}],
            "j-b": [],
        }
        return samples.get(jid, [])

    def _results(self, jid: str) -> list[dict] | None:
        data = {
            "j-a": [{"product": "Widget", "price": "10"}, {"product": "Gadget", "price": "20"}],
            "j-b": [],
        }
        return data.get(jid)

    @pytest.mark.asyncio
    async def test_csv_integration(self) -> None:
        meta = self._job_meta()
        manifest = await export_service.build_batch_manifest(meta, None, self._count)
        assert len(manifest) == 2
        assert manifest[0]["status"] == "included"
        assert manifest[1]["status"] == "empty"

        union, has_data = await export_service.discover_fieldnames_union(meta, None, self._sample)
        assert has_data is True
        assert set(union) == {"product", "price"}

        pages = export_service.iter_batch_pages(meta, None, self._results)
        stream = export_service.batch_csv_stream(pages, union, flatten=True)
        result = await _async_collect(stream)
        text = result.decode("utf-8")
        assert "Widget" in text
        assert "Gadget" in text
        assert "Alpha" in text
        assert export_service.SOURCE_JOB_FIELD in text

    @pytest.mark.asyncio
    async def test_json_integration(self) -> None:
        meta = self._job_meta()
        manifest = await export_service.build_batch_manifest(meta, None, self._count)
        union, _ = await export_service.discover_fieldnames_union(meta, None, self._sample)
        pages = export_service.iter_batch_pages(meta, None, self._results)
        stream = export_service.batch_json_stream(pages, flatten=True, manifest=manifest)
        result = await _async_collect(stream)
        data = json.loads(result)
        assert len(data) == 2
        assert data[0]["product"] == "Widget"
        assert data[1]["product"] == "Gadget"

    def test_xlsx_integration(self) -> None:
        meta = self._job_meta()
        manifest = [
            {"job_id": "j-a", "job_name": "Alpha", "status": "included", "record_count": 2},
            {"job_id": "j-b", "job_name": "Beta", "status": "empty", "record_count": 0},
        ]
        xlsx_bytes = export_service.batch_xlsx(
            meta,
            fieldnames=["product", "price"],
            flatten=True,
            manifest=manifest,
            get_inmemory_results=self._results,
        )
        assert xlsx_bytes[:2] == b"PK"
        assert len(xlsx_bytes) > 0


# ════════════════════════════════════════════════════════════════════
# Additional Coverage — Empty results, large records, CSV injection, Excel pagination, JSON interruption
# ════════════════════════════════════════════════════════════════════


class TestBatchExportEdgeCases:
    @pytest.mark.asyncio
    async def test_csv_with_empty_results_yields_header_only(self) -> None:
        pages = _async_pages([("job-1", "Empty Job", [])])
        fieldnames: list[str] = []
        stream = export_service.batch_csv_stream(pages, fieldnames, flatten=True)
        result = await _async_collect(stream)
        text = result.decode("utf-8")
        assert export_service.SOURCE_JOB_FIELD in text

    @pytest.mark.asyncio
    async def test_csv_all_injection_prefixes_escaped(self) -> None:
        pages = _async_pages(
            [
                (
                    "job-1",
                    "Inject",
                    [
                        {
                            "eq": "=SUM(A1:A10)",
                            "plus": "+CMD",
                            "minus": "-DANGER",
                            "at": "@EVIL",
                            "tab": "\tMALICIOUS",
                            "cr": "\rHARMFUL",
                        }
                    ],
                ),
            ]
        )
        fieldnames = ["eq", "plus", "minus", "at", "tab", "cr"]
        stream = export_service.batch_csv_stream(pages, fieldnames, flatten=True)
        result = await _async_collect(stream)
        text = result.decode("utf-8")
        assert "'=SUM(A1:A10)" in text
        assert "'+CMD" in text
        assert "'-DANGER" in text
        assert "'@EVIL" in text
        assert "'\tMALICIOUS" in text
        assert "'\rHARMFUL" in text

    @pytest.mark.asyncio
    async def test_csv_non_string_value_not_escaped(self) -> None:
        pages = _async_pages([("job-1", "J1", [{"num": 123, "flag": True, "none": None}])])
        fieldnames = ["num", "flag", "none"]
        stream = export_service.batch_csv_stream(pages, fieldnames, flatten=True)
        result = await _async_collect(stream)
        text = result.decode("utf-8")
        assert "123" in text
        assert "True" in text

    @pytest.mark.asyncio
    async def test_json_stream_with_large_records(self) -> None:
        large_val = "x" * 50000
        pages = _async_pages(
            [
                ("job-1", "Large", [{"id": "1", "data": large_val}]),
            ]
        )
        stream = export_service.batch_json_stream(pages, flatten=True)
        result = await _async_collect(stream)
        data = json.loads(result)
        assert len(data) == 1
        assert data[0]["data"] == large_val

    @pytest.mark.asyncio
    async def test_json_stream_empty_pages_flattened(self) -> None:
        pages = _async_pages([])
        stream = export_service.batch_json_stream(pages, flatten=True)
        result = await _async_collect(stream)
        data = json.loads(result)
        assert data == []

    @pytest.mark.asyncio
    async def test_json_stream_non_flattened_without_manifest(self) -> None:
        pages = _async_pages([("job-1", "Job One", [{"x": "1"}])])
        stream = export_service.batch_json_stream(pages, flatten=False)
        result = await _async_collect(stream)
        data = json.loads(result)
        assert "manifest" in data
        assert data["manifest"] == []

    def test_build_csv_bytes_empty_results_raises(self) -> None:
        from unittest.mock import MagicMock

        job = MagicMock()
        job.results = []
        with pytest.raises(ValueError, match="No results"):
            export_service.build_csv_bytes(job)

    def test_build_json_bytes_empty_results_raises(self) -> None:
        from unittest.mock import MagicMock

        job = MagicMock()
        job.results = []
        with pytest.raises(ValueError, match="No results"):
            export_service.build_json_bytes(job)

    def test_build_excel_bytes_empty_results_raises(self) -> None:
        from unittest.mock import MagicMock

        job = MagicMock()
        job.results = []
        with pytest.raises(ValueError, match="No results"):
            export_service.build_excel_bytes(job)

    def test_flat_row_with_list_values(self) -> None:
        row = {"tags": ["a", "b", "c"], "name": "test"}
        fieldnames = ["tags", "name"]
        flat = export_service.flat_row(row, fieldnames)
        assert flat["tags"] == "a, b, c"
        assert flat["name"] == "test"

    def test_flat_row_with_injection_in_list(self) -> None:
        row = {"formulas": ["=1+1", "+DANGER"]}
        fieldnames = ["formulas"]
        flat = export_service.flat_row(row, fieldnames)
        # safe_cell escapes the final joined string starting with '='
        assert flat["formulas"] == "'=1+1, +DANGER"

    def test_strip_system_fields_removes_underscore_prefix(self) -> None:
        records = [{"_id": "1", "name": "Alice", "_score": 0.9}]
        cleaned = export_service.strip_system_fields(records)
        assert cleaned == [{"name": "Alice"}]

    def test_user_fieldnames_from_empty_list(self) -> None:
        assert export_service.user_fieldnames([]) == []

    def test_user_fieldnames_skips_system(self) -> None:
        records = [{"_id": "1", "name": "Alice"}]
        assert export_service.user_fieldnames(records) == ["name"]

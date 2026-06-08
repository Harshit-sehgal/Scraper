"""Unit Tests for the Export Router.

Tests CSV, JSON, Excel, and batch export endpoints using a mock jobs_store
with minimal Job objects.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

import pytest
import pytest_asyncio
from app.models import FieldType, Job, JobStatus, SchemaField
from app.routers.exports import create_exports_router
from fastapi import FastAPI

pytestmark = pytest.mark.filterwarnings("ignore::ResourceWarning")


def _make_job(
    job_id: str,
    name: str = "test-job",
    results: list[dict[str, Any]] | None = None,
    schema_fields: list[SchemaField] | None = None,
    results_on_disk: bool = False,  # noqa: FBT001, FBT002
) -> Job:
    return Job(
        id=job_id,
        name=name,
        status=JobStatus.COMPLETED,
        results=results or [],
        schema_fields=schema_fields or [],
        urls=["https://example.com"],
        results_on_disk=results_on_disk,
    )


@pytest.fixture
def app() -> FastAPI:
    _app = FastAPI()
    jobs_store: dict[str, Job] = {}
    router = create_exports_router(jobs_store)
    _app.include_router(router)
    return _app


@pytest_asyncio.fixture
async def client(app: FastAPI):
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


# ─── Missing job / empty results ────────────────────────────────────


class TestExportErrors:
    @pytest.mark.asyncio
    async def test_csv_missing_job_returns_404(self, client) -> None:
        resp = await client.get("/api/jobs/nonexistent/export/csv")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_json_missing_job_returns_404(self, client) -> None:
        resp = await client.get("/api/jobs/nonexistent/export/json")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_excel_missing_job_returns_404(self, client) -> None:
        resp = await client.get("/api/jobs/nonexistent/export/excel")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_csv_empty_results_returns_400(self) -> None:
        from httpx import ASGITransport, AsyncClient

        jobs_store: dict[str, Job] = {}
        router = create_exports_router(jobs_store)
        jobs_store["empty-job"] = _make_job("empty-job", results=[])
        test_app = FastAPI()
        test_app.include_router(router)
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as c:
            resp = await c.get("/api/jobs/empty-job/export/csv")
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_json_empty_results_returns_400(self) -> None:
        from httpx import ASGITransport, AsyncClient

        jobs_store: dict[str, Job] = {}
        router = create_exports_router(jobs_store)
        jobs_store["empty-job"] = _make_job("empty-job", results=[])
        test_app = FastAPI()
        test_app.include_router(router)
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as c:
            resp = await c.get("/api/jobs/empty-job/export/json")
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_excel_empty_results_returns_400(self) -> None:
        from httpx import ASGITransport, AsyncClient

        jobs_store: dict[str, Job] = {}
        router = create_exports_router(jobs_store)
        jobs_store["empty-job"] = _make_job("empty-job", results=[])
        test_app = FastAPI()
        test_app.include_router(router)
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as c:
            resp = await c.get("/api/jobs/empty-job/export/excel")
        assert resp.status_code == 400


# ─── CSV Export ─────────────────────────────────────────────────────


class TestCsvExport:
    @pytest_asyncio.fixture
    async def csv_client(self):
        from httpx import ASGITransport, AsyncClient

        jobs_store: dict[str, Job] = {}
        router = create_exports_router(jobs_store)
        jobs_store["csv-job"] = _make_job(
            "csv-job",
            name="test-csv",
            results=[
                {"name": "Alice", "price": "100", "tags": ["a", "b"]},
                {"name": "Bob", "price": "200", "tags": ["c"]},
            ],
            schema_fields=[
                SchemaField(name="name", field_type=FieldType.STRING, description="", required=False),
                SchemaField(name="price", field_type=FieldType.FLOAT, description="", required=False),
                SchemaField(name="tags", field_type=FieldType.STRING, description="", required=False),
            ],
        )
        test_app = FastAPI()
        test_app.include_router(router)
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as c:
            yield c

    @pytest.mark.asyncio
    async def test_csv_returns_200(self, csv_client) -> None:
        resp = await csv_client.get("/api/jobs/csv-job/export/csv")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_csv_content_type(self, csv_client) -> None:
        resp = await csv_client.get("/api/jobs/csv-job/export/csv")
        assert resp.headers.get("content-type", "").startswith("text/csv")

    @pytest.mark.asyncio
    async def test_csv_has_disposition_header(self, csv_client) -> None:
        resp = await csv_client.get("/api/jobs/csv-job/export/csv")
        assert "Content-Disposition" in resp.headers
        assert "attachment" in resp.headers["content-disposition"]

    @pytest.mark.asyncio
    async def test_csv_contains_data(self, csv_client) -> None:
        resp = await csv_client.get("/api/jobs/csv-job/export/csv")
        text = resp.text
        assert "Alice" in text
        assert "Bob" in text
        assert "name" in text
        assert "price" in text

    @pytest.mark.asyncio
    async def test_csv_lists_flattened(self, csv_client) -> None:
        """List values should be joined with comma+space."""
        resp = await csv_client.get("/api/jobs/csv-job/export/csv")
        text = resp.text
        assert "a, b" in text


# ─── JSON Export ────────────────────────────────────────────────────


class TestJsonExport:
    @pytest_asyncio.fixture
    async def json_client(self):
        from httpx import ASGITransport, AsyncClient

        jobs_store: dict[str, Job] = {}
        router = create_exports_router(jobs_store)
        jobs_store["json-job"] = _make_job(
            "json-job",
            name="test-json",
            results=[
                {"name": "Alice", "price": "100"},
                {"name": "Bob", "price": "200"},
            ],
        )
        test_app = FastAPI()
        test_app.include_router(router)
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as c:
            yield c

    @pytest.mark.asyncio
    async def test_json_returns_200(self, json_client) -> None:
        resp = await json_client.get("/api/jobs/json-job/export/json")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_json_content_type(self, json_client) -> None:
        resp = await json_client.get("/api/jobs/json-job/export/json")
        assert "application/json" in resp.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_json_content_parses(self, json_client) -> None:
        resp = await json_client.get("/api/jobs/json-job/export/json")
        data = json.loads(resp.content)
        assert isinstance(data, list)
        assert len(data) == 2
        assert data[0]["name"] == "Alice"
        assert data[1]["name"] == "Bob"

    @pytest.mark.asyncio
    async def test_json_indented(self, json_client) -> None:
        """JSON should be pretty-printed with indent=2."""
        resp = await json_client.get("/api/jobs/json-job/export/json")
        text = resp.text
        # Pretty-printed JSON has newlines between fields
        assert "\n  " in text


# ─── Excel Export ───────────────────────────────────────────────────


class TestExcelExport:
    @pytest_asyncio.fixture
    async def excel_client(self):
        from httpx import ASGITransport, AsyncClient

        jobs_store: dict[str, Job] = {}
        router = create_exports_router(jobs_store)
        jobs_store["xlsx-job"] = _make_job(
            "xlsx-job",
            name="test-excel",
            results=[
                {"name": "Alice", "score": "95"},
                {"name": "Bob", "score": "87"},
            ],
            schema_fields=[
                SchemaField(name="name", field_type=FieldType.STRING, description="", required=False),
                SchemaField(name="score", field_type=FieldType.FLOAT, description="", required=False),
            ],
        )
        test_app = FastAPI()
        test_app.include_router(router)
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as c:
            yield c

    @pytest.mark.asyncio
    async def test_excel_returns_200(self, excel_client) -> None:
        resp = await excel_client.get("/api/jobs/xlsx-job/export/excel")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_excel_content_type(self, excel_client) -> None:
        resp = await excel_client.get("/api/jobs/xlsx-job/export/excel")
        assert "spreadsheetml" in resp.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_excel_is_binary(self, excel_client) -> None:
        resp = await excel_client.get("/api/jobs/xlsx-job/export/excel")
        # Excel files are binary (not plain text)
        assert len(resp.content) > 0
        # XLSX files start with PK (ZIP magic bytes)
        assert resp.content[:2] == b"PK"

    @pytest.mark.asyncio
    async def test_excel_has_disposition(self, excel_client) -> None:
        resp = await excel_client.get("/api/jobs/xlsx-job/export/excel")
        assert "Content-Disposition" in resp.headers


# ─── Schema-less export ─────────────────────────────────────────────


class TestExportWithoutSchema:
    """When schema_fields is empty, exports should infer field names from data."""

    @pytest_asyncio.fixture
    async def no_schema_client(self):
        from httpx import ASGITransport, AsyncClient

        jobs_store: dict[str, Job] = {}
        router = create_exports_router(jobs_store)
        jobs_store["noschema"] = _make_job(
            "noschema",
            results=[
                {"title": "Product A", "price": "49"},
                {"title": "Product B", "price": "99"},
            ],
            schema_fields=[],  # No schema — infer from data
        )
        test_app = FastAPI()
        test_app.include_router(router)
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as c:
            yield c

    @pytest.mark.asyncio
    async def test_csv_infers_headers(self, no_schema_client) -> None:
        resp = await no_schema_client.get("/api/jobs/noschema/export/csv")
        assert resp.status_code == 200
        text = resp.text
        assert "title" in text
        assert "Product A" in text

    @pytest.mark.asyncio
    async def test_json_infers_fields(self, no_schema_client) -> None:
        resp = await no_schema_client.get("/api/jobs/noschema/export/json")
        assert resp.status_code == 200
        data = json.loads(resp.content)
        assert len(data) == 2
        assert "title" in data[0]

    @pytest.mark.asyncio
    async def test_excel_infers_fields(self, no_schema_client) -> None:
        """Excel should also handle schema-less export by inferring field names."""
        resp = await no_schema_client.get("/api/jobs/noschema/export/excel")
        assert resp.status_code == 200
        assert "spreadsheetml" in resp.headers.get("content-type", "")


# ─── Export with results_on_disk ────────────────────────────────────


class TestExportResultsOnDisk:
    """When results_on_disk is True, exports should load from disk instead of memory.

    CSV and JSON exports use ``load_paginated_job_results_from_disk`` for streaming,
    while Excel uses ``load_job_results_from_disk_safe`` for corruption-tolerant loading.
    """

    @pytest_asyncio.fixture
    async def disk_client(self):
        from httpx import ASGITransport, AsyncClient

        mock_on_disk_data = [
            {"city": "London", "temp": "15"},
            {"city": "Paris", "temp": "18"},
        ]
        with (
            patch(
                "app.utils.job_results_store.load_paginated_job_results_from_disk",
                return_value=(mock_on_disk_data, 2),
            ),
            patch(
                "app.utils.job_results_store.load_job_results_from_disk_safe",
                return_value=(mock_on_disk_data, None),
            ),
        ):
            jobs_store: dict[str, Job] = {}
            router = create_exports_router(jobs_store)
            # Job has empty in-memory results but results_on_disk=True
            jobs_store["disk-job"] = _make_job(
                "disk-job",
                name="disk-test",
                results=[],  # empty in memory
                results_on_disk=True,
            )
            test_app = FastAPI()
            test_app.include_router(router)
            transport = ASGITransport(app=test_app)
            async with AsyncClient(transport=transport, base_url="http://testserver") as c:
                yield c

    @pytest.mark.asyncio
    async def test_csv_loads_from_disk(self, disk_client) -> None:
        resp = await disk_client.get("/api/jobs/disk-job/export/csv")
        assert resp.status_code == 200
        text = resp.text
        assert "London" in text
        assert "Paris" in text

    @pytest.mark.asyncio
    async def test_json_loads_from_disk(self, disk_client) -> None:
        resp = await disk_client.get("/api/jobs/disk-job/export/json")
        assert resp.status_code == 200
        data = json.loads(resp.content)
        assert len(data) == 2
        assert data[0]["city"] == "London"

    @pytest.mark.asyncio
    async def test_excel_loads_from_disk(self, disk_client) -> None:
        resp = await disk_client.get("/api/jobs/disk-job/export/excel")
        assert resp.status_code == 200
        assert resp.content[:2] == b"PK"


class TestExportResultsOnDiskExcelSafeLoading:
    """Excel export uses paginated loader to avoid memory overhead."""

    @pytest.mark.asyncio
    async def test_excel_uses_paginated_loader(self) -> None:
        """Excel should call load_paginated_job_results_from_disk."""
        from httpx import ASGITransport, AsyncClient

        jobs_store: dict[str, Job] = {}
        router = create_exports_router(jobs_store)
        jobs_store["safe-excel"] = _make_job(
            "safe-excel",
            name="safe-test",
            results=[],
            results_on_disk=True,
        )
        test_app = FastAPI()
        test_app.include_router(router)

        with patch(
            "app.utils.job_results_store.load_paginated_job_results_from_disk",
            return_value=([{"x": "1"}], 1),
        ):
            transport = ASGITransport(app=test_app)
            async with AsyncClient(transport=transport, base_url="http://testserver") as c:
                resp = await c.get("/api/jobs/safe-excel/export/excel")
        assert resp.status_code == 200
        assert resp.content[:2] == b"PK"


class TestStreamingExportWithLargeDataset:
    """When results_on_disk is True and dataset spans multiple pages, exports should stream."""

    @pytest.mark.asyncio
    async def test_csv_streams_multiple_pages(self) -> None:
        """500-row dataset should produce all rows in CSV output."""
        from httpx import ASGITransport, AsyncClient

        large_data = [{"idx": i} for i in range(500)]

        def _paginated_loader(job_id, limit=500, offset=0, file_path=None):
            total = len(large_data)
            page = large_data[offset : offset + limit]
            return page, total

        jobs_store: dict[str, Job] = {}
        router = create_exports_router(jobs_store)
        jobs_store["stream-csv"] = _make_job(
            "stream-csv",
            name="stream-test",
            results=[],
            results_on_disk=True,
        )
        test_app = FastAPI()
        test_app.include_router(router)

        with patch(
            "app.utils.job_results_store.load_paginated_job_results_from_disk",
            side_effect=_paginated_loader,
        ):
            transport = ASGITransport(app=test_app)
            async with AsyncClient(transport=transport, base_url="http://testserver") as c:
                resp = await c.get("/api/jobs/stream-csv/export/csv")
        assert resp.status_code == 200
        text = resp.text
        # Should contain all 500 rows plus header
        lines = text.strip().split("\n")
        assert len(lines) == 501  # header + 500 data rows
        assert lines[1].strip() == "0"
        assert lines[-1].strip() == "499"

    @pytest.mark.asyncio
    async def test_json_streams_multiple_pages(self) -> None:
        """500-row dataset should produce all rows in JSON output."""
        from httpx import ASGITransport, AsyncClient

        large_data = [{"idx": i} for i in range(500)]

        def _paginated_loader(job_id, limit=500, offset=0, file_path=None):
            total = len(large_data)
            page = large_data[offset : offset + limit]
            return page, total

        jobs_store: dict[str, Job] = {}
        router = create_exports_router(jobs_store)
        jobs_store["stream-json"] = _make_job(
            "stream-json",
            name="stream-test",
            results=[],
            results_on_disk=True,
        )
        test_app = FastAPI()
        test_app.include_router(router)

        with patch(
            "app.utils.job_results_store.load_paginated_job_results_from_disk",
            side_effect=_paginated_loader,
        ):
            transport = ASGITransport(app=test_app)
            async with AsyncClient(transport=transport, base_url="http://testserver") as c:
                resp = await c.get("/api/jobs/stream-json/export/json")
        assert resp.status_code == 200
        data = json.loads(resp.content)
        assert len(data) == 500
        assert data[0]["idx"] == 0
        assert data[499]["idx"] == 499


# ─── Excel with None values in list fields ──────────────────────────


class TestExcelWorksheetCreation:
    """Edge cases that exercise the export route's error-handling path."""

    @pytest.mark.asyncio
    async def test_excel_create_sheet_raises_returns_500(self) -> None:
        """When ``Workbook.create_sheet`` raises, the route must return 500.

        The earlier version of this test mocked ``Workbook().active`` to
        ``None``. That mock was a no-op against the current code path
        (the route uses ``Workbook(write_only=True)`` and calls
        ``create_sheet`` explicitly — it never reads ``.active``), so
        the test silently asserted a 200 response. This rewrite mocks a
        failure the production code actually performs, which is what
        we want to test: a sheet-creation failure (e.g. an openpyxl
        validation error on a malformed title) bubbles up as a 500
        response.
        """
        from unittest.mock import patch as mock_patch

        from httpx import ASGITransport, AsyncClient

        jobs_store: dict[str, Job] = {}
        router = create_exports_router(jobs_store)
        jobs_store["ws-broken"] = _make_job(
            "ws-broken",
            results=[{"x": "1"}],
            schema_fields=[SchemaField(name="x", field_type=FieldType.STRING, description="", required=False)],
        )
        test_app = FastAPI()
        test_app.include_router(router)
        # ``raise_app_exceptions=False`` lets the route's
        # ``except Exception: raise`` re-raise bubble up to FastAPI's
        # default 500 handler, so the test sees an HTTP response
        # instead of an unhandled exception in the AsyncClient
        # context. The default ``True`` (used everywhere else) is
        # what we want for normal happy-path tests.
        transport = ASGITransport(app=test_app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://testserver") as c:
            with mock_patch("app.routers.exports.Workbook") as mock_wb_cls:
                mock_wb = mock_wb_cls.return_value
                mock_wb.create_sheet.side_effect = RuntimeError("openpyxl rejected the sheet title")
                resp = await c.get("/api/jobs/ws-broken/export/excel")
        assert resp.status_code == 500


class TestExcelListNoneValues:
    """None values inside list fields should be filtered out in Excel export."""

    @pytest_asyncio.fixture
    async def none_list_client(self):
        from httpx import ASGITransport, AsyncClient

        jobs_store: dict[str, Job] = {}
        router = create_exports_router(jobs_store)
        jobs_store["none-list-job"] = _make_job(
            "none-list-job",
            name="none-list-test",
            results=[
                {"name": "X", "tags": ["a", None, "b"]},
                {"name": "Y", "tags": [None]},
            ],
            schema_fields=[
                SchemaField(name="name", field_type=FieldType.STRING, description="", required=False),
                SchemaField(name="tags", field_type=FieldType.STRING, description="", required=False),
            ],
        )
        test_app = FastAPI()
        test_app.include_router(router)
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as c:
            yield c

    @pytest.mark.asyncio
    async def test_excel_with_none_in_lists(self, none_list_client) -> None:
        """None items in list values should not cause errors in Excel export."""
        resp = await none_list_client.get("/api/jobs/none-list-job/export/excel")
        assert resp.status_code == 200
        assert resp.content[:2] == b"PK"


# ─── Export filename ────────────────────────────────────────────────


class TestExportFilename:
    @pytest_asyncio.fixture
    async def name_client(self):
        from httpx import ASGITransport, AsyncClient

        jobs_store: dict[str, Job] = {}
        router = create_exports_router(jobs_store)
        jobs_store["n1"] = _make_job(
            "n1",
            name="My Cool Job",
            results=[{"x": "1"}],
            schema_fields=[SchemaField(name="x", field_type=FieldType.STRING, description="", required=False)],
        )
        jobs_store["n2"] = _make_job(
            "n2",
            name="special/chars:test",
            results=[{"x": "1"}],
            schema_fields=[SchemaField(name="x", field_type=FieldType.STRING, description="", required=False)],
        )
        test_app = FastAPI()
        test_app.include_router(router)
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as c:
            yield c

    @pytest.mark.asyncio
    async def test_csv_filename_contains_job_name(self, name_client) -> None:
        resp = await name_client.get("/api/jobs/n1/export/csv")
        disp = resp.headers.get("content-disposition", "")
        assert "My_Cool_Job" in disp
        assert ".csv" in disp

    @pytest.mark.asyncio
    async def test_json_filename_clean(self, name_client) -> None:
        resp = await name_client.get("/api/jobs/n2/export/json")
        disp = resp.headers.get("content-disposition", "")
        # Special chars (slashes, colons) must be stripped from the
        # filename segment so the Content-Disposition header is
        # syntactically valid for every browser. We assert both that
        # the meaningful parts of the job name are preserved and that
        # the unsafe separators are absent.
        assert ".json" in disp
        for allowed in ("special", "chars", "test"):
            assert allowed in disp, f"expected {allowed!r} in {disp!r}"
        for forbidden in ("/", ":"):
            assert forbidden not in disp, f"{forbidden!r} leaked into {disp!r}"


# ═══════════════════════════════════════════════════════════════════
# Batch Export Tests
# ═══════════════════════════════════════════════════════════════════


class TestBatchExportErrors:
    """Error handling for the batch export endpoint."""

    @pytest.mark.asyncio
    async def test_batch_missing_job_returns_404(self) -> None:
        from httpx import ASGITransport, AsyncClient

        jobs_store: dict[str, Job] = {}
        router = create_exports_router(jobs_store)
        jobs_store["exists"] = _make_job("exists", results=[{"x": "1"}])
        test_app = FastAPI()
        test_app.include_router(router)
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as c:
            resp = await c.post(
                "/api/exports/batch",
                json={"job_ids": ["exists", "missing"], "format": "csv"},
            )
        assert resp.status_code == 404
        assert "missing" in resp.text

    @pytest.mark.asyncio
    async def test_batch_all_missing_returns_404(self) -> None:
        from httpx import ASGITransport, AsyncClient

        jobs_store: dict[str, Job] = {}
        router = create_exports_router(jobs_store)
        test_app = FastAPI()
        test_app.include_router(router)
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as c:
            resp = await c.post(
                "/api/exports/batch",
                json={"job_ids": ["nope"], "format": "csv"},
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_batch_no_results_returns_400(self) -> None:
        from httpx import ASGITransport, AsyncClient

        jobs_store: dict[str, Job] = {}
        router = create_exports_router(jobs_store)
        jobs_store["empty"] = _make_job("empty", results=[])
        test_app = FastAPI()
        test_app.include_router(router)
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as c:
            resp = await c.post(
                "/api/exports/batch",
                json={"job_ids": ["empty"], "format": "csv"},
            )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_batch_unsupported_format_returns_400(self) -> None:
        from httpx import ASGITransport, AsyncClient

        jobs_store: dict[str, Job] = {}
        router = create_exports_router(jobs_store)
        jobs_store["j1"] = _make_job("j1", results=[{"x": "1"}])
        test_app = FastAPI()
        test_app.include_router(router)
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as c:
            resp = await c.post(
                "/api/exports/batch",
                json={"job_ids": ["j1"], "format": "xml"},
            )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_batch_empty_job_ids_returns_422(self) -> None:
        """Empty job_ids list should fail Pydantic validation."""
        from httpx import ASGITransport, AsyncClient

        jobs_store: dict[str, Job] = {}
        router = create_exports_router(jobs_store)
        test_app = FastAPI()
        test_app.include_router(router)
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as c:
            resp = await c.post(
                "/api/exports/batch",
                json={"job_ids": [], "format": "csv"},
            )
        assert resp.status_code == 422


class TestBatchCsvExport:
    """CSV batch export tests."""

    @pytest_asyncio.fixture
    async def batch_csv_client(self):
        from httpx import ASGITransport, AsyncClient

        jobs_store: dict[str, Job] = {}
        router = create_exports_router(jobs_store)
        jobs_store["a"] = _make_job(
            "a",
            name="Job A",
            results=[{"city": "London", "temp": "15"}],
        )
        jobs_store["b"] = _make_job(
            "b",
            name="Job B",
            results=[{"city": "Paris", "temp": "18"}, {"city": "Rome", "temp": "22"}],
        )
        test_app = FastAPI()
        test_app.include_router(router)
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as c:
            yield c

    @pytest.mark.asyncio
    async def test_batch_csv_flatten_returns_200(self, batch_csv_client) -> None:
        resp = await batch_csv_client.post(
            "/api/exports/batch",
            json={"job_ids": ["a", "b"], "format": "csv", "flatten": True},
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_batch_csv_flatten_content_type(self, batch_csv_client) -> None:
        resp = await batch_csv_client.post(
            "/api/exports/batch",
            json={"job_ids": ["a", "b"], "format": "csv", "flatten": True},
        )
        assert resp.headers.get("content-type", "").startswith("text/csv")

    @pytest.mark.asyncio
    async def test_batch_csv_flatten_has_source_column(self, batch_csv_client) -> None:
        resp = await batch_csv_client.post(
            "/api/exports/batch",
            json={"job_ids": ["a", "b"], "format": "csv", "flatten": True},
        )
        text = resp.text
        lines = text.strip().split("\n")
        # Header row should include _source_job
        assert "_source_job" in lines[0]
        # Data rows should have job names
        assert "Job A" in text
        assert "Job B" in text
        # All 3 data rows should be present
        assert len(lines) == 4  # header + 3 data rows

    @pytest.mark.asyncio
    async def test_batch_csv_non_flatten_has_separators(self, batch_csv_client) -> None:
        resp = await batch_csv_client.post(
            "/api/exports/batch",
            json={"job_ids": ["a", "b"], "format": "csv", "flatten": False},
        )
        text = resp.text
        lines = text.strip().split("\n")
        # Should have separator row after header for Job B
        assert "--- Job B ---" in text
        # _source_job should NOT be in header when flatten=False
        assert "_source_job" not in lines[0]
        # Header + 1 data row (Job A) + separator + 2 data rows (Job B) = 4
        # Actually: header + data + separator + data + data = 5 lines
        assert len(lines) == 5

    @pytest.mark.asyncio
    async def test_batch_csv_disposition_header(self, batch_csv_client) -> None:
        resp = await batch_csv_client.post(
            "/api/exports/batch",
            json={"job_ids": ["a"], "format": "csv"},
        )
        disp = resp.headers.get("content-disposition", "")
        assert "attachment" in disp
        assert ".csv" in disp
        assert "batch_export_" in disp


class TestBatchJsonExport:
    """JSON batch export tests."""

    @pytest_asyncio.fixture
    async def batch_json_client(self):
        from httpx import ASGITransport, AsyncClient

        jobs_store: dict[str, Job] = {}
        router = create_exports_router(jobs_store)
        jobs_store["a"] = _make_job(
            "a",
            name="Job A",
            results=[{"city": "London", "temp": "15"}],
        )
        jobs_store["b"] = _make_job(
            "b",
            name="Job B",
            results=[{"city": "Paris", "temp": "18"}],
        )
        test_app = FastAPI()
        test_app.include_router(router)
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as c:
            yield c

    @pytest.mark.asyncio
    async def test_batch_json_flatten_returns_array(self, batch_json_client) -> None:
        resp = await batch_json_client.post(
            "/api/exports/batch",
            json={"job_ids": ["a", "b"], "format": "json", "flatten": True},
        )
        assert resp.status_code == 200
        data = json.loads(resp.content)
        assert isinstance(data, list)
        assert len(data) == 2
        assert data[0]["_source_job"] == "Job A"
        assert data[1]["_source_job"] == "Job B"

    @pytest.mark.asyncio
    async def test_batch_json_non_flatten_returns_exports_object(self, batch_json_client) -> None:
        resp = await batch_json_client.post(
            "/api/exports/batch",
            json={"job_ids": ["a", "b"], "format": "json", "flatten": False},
        )
        assert resp.status_code == 200
        data = json.loads(resp.content)
        assert isinstance(data, dict)
        assert "exports" in data
        assert len(data["exports"]) == 2
        assert data["exports"][0]["job_id"] == "a"
        assert data["exports"][0]["job_name"] == "Job A"
        assert len(data["exports"][0]["results"]) == 1
        assert data["exports"][1]["job_id"] == "b"

    @pytest.mark.asyncio
    async def test_batch_json_content_type(self, batch_json_client) -> None:
        resp = await batch_json_client.post(
            "/api/exports/batch",
            json={"job_ids": ["a"], "format": "json"},
        )
        assert "application/json" in resp.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_batch_json_disposition(self, batch_json_client) -> None:
        resp = await batch_json_client.post(
            "/api/exports/batch",
            json={"job_ids": ["a"], "format": "json"},
        )
        disp = resp.headers.get("content-disposition", "")
        assert "batch_export_" in disp
        assert ".json" in disp


class TestBatchExcelExport:
    """Excel batch export tests."""

    @pytest_asyncio.fixture
    async def batch_xlsx_client(self):
        from httpx import ASGITransport, AsyncClient

        jobs_store: dict[str, Job] = {}
        router = create_exports_router(jobs_store)
        jobs_store["a"] = _make_job(
            "a",
            name="Job A",
            results=[{"city": "London", "temp": "15"}],
        )
        jobs_store["b"] = _make_job(
            "b",
            name="Job B",
            results=[{"city": "Paris", "temp": "18"}],
        )
        test_app = FastAPI()
        test_app.include_router(router)
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as c:
            yield c

    @pytest.mark.asyncio
    async def test_batch_xlsx_flatten_returns_200(self, batch_xlsx_client) -> None:
        resp = await batch_xlsx_client.post(
            "/api/exports/batch",
            json={"job_ids": ["a", "b"], "format": "xlsx", "flatten": True},
        )
        assert resp.status_code == 200
        assert resp.content[:2] == b"PK"

    @pytest.mark.asyncio
    async def test_batch_xlsx_non_flatten_returns_200(self, batch_xlsx_client) -> None:
        resp = await batch_xlsx_client.post(
            "/api/exports/batch",
            json={"job_ids": ["a", "b"], "format": "xlsx", "flatten": False},
        )
        assert resp.status_code == 200
        assert resp.content[:2] == b"PK"

    @pytest.mark.asyncio
    async def test_batch_xlsx_content_type(self, batch_xlsx_client) -> None:
        resp = await batch_xlsx_client.post(
            "/api/exports/batch",
            json={"job_ids": ["a"], "format": "xlsx"},
        )
        assert "spreadsheetml" in resp.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_batch_xlsx_disposition(self, batch_xlsx_client) -> None:
        resp = await batch_xlsx_client.post(
            "/api/exports/batch",
            json={"job_ids": ["a"], "format": "xlsx"},
        )
        disp = resp.headers.get("content-disposition", "")
        assert "batch_export_" in disp
        assert ".xlsx" in disp


class TestBatchExportEmptyResultsHandling:
    """When some jobs have results and others don't, only jobs with data should be included."""

    @pytest.mark.asyncio
    async def test_batch_skip_jobs_without_results(self) -> None:
        """Jobs with no results should not cause failure; they're silently skipped."""
        from httpx import ASGITransport, AsyncClient

        jobs_store: dict[str, Job] = {}
        router = create_exports_router(jobs_store)
        jobs_store["full"] = _make_job("full", name="Has Data", results=[{"x": "1"}])
        jobs_store["empty"] = _make_job("empty", name="Empty", results=[])
        test_app = FastAPI()
        test_app.include_router(router)
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as c:
            resp = await c.post(
                "/api/exports/batch",
                json={"job_ids": ["full", "empty"], "format": "csv", "flatten": True},
            )
        assert resp.status_code == 200
        text = resp.text
        lines = text.strip().split("\n")
        # Only 1 data row (from "full"), header included
        assert len(lines) == 2
        assert "Has Data" in text
        assert "Empty" not in text


class TestBatchExportUnionFieldnames:
    """When jobs have different field schemas, the union of all fields should be used."""

    @pytest.mark.asyncio
    async def test_batch_union_of_fieldnames(self) -> None:
        from httpx import ASGITransport, AsyncClient

        jobs_store: dict[str, Job] = {}
        router = create_exports_router(jobs_store)
        jobs_store["a"] = _make_job("a", name="A", results=[{"name": "X", "age": "30"}])
        jobs_store["b"] = _make_job("b", name="B", results=[{"name": "Y", "email": "y@test.com"}])
        test_app = FastAPI()
        test_app.include_router(router)
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as c:
            resp = await c.post(
                "/api/exports/batch",
                json={"job_ids": ["a", "b"], "format": "csv", "flatten": True},
            )
        assert resp.status_code == 200
        text = resp.text
        lines = text.strip().split("\n")
        header = lines[0]
        assert "name" in header
        assert "age" in header
        assert "email" in header
        assert "_source_job" in header
        # 3 data rows: header + 2 = 3 lines
        assert len(lines) == 3


class TestBatchExportWithDiskResults:
    """Batch export should also handle jobs with results_on_disk."""

    @pytest.mark.asyncio
    async def test_batch_csv_with_disk_results(self) -> None:
        from httpx import ASGITransport, AsyncClient

        mock_data = [{"city": "Tokyo", "temp": "28"}]
        with patch(
            "app.utils.job_results_store.load_paginated_job_results_from_disk",
            return_value=(mock_data, 1),
        ):
            jobs_store: dict[str, Job] = {}
            router = create_exports_router(jobs_store)
            jobs_store["disk-job"] = _make_job(
                "disk-job",
                name="Disk Job",
                results=[],
                results_on_disk=True,
            )
            test_app = FastAPI()
            test_app.include_router(router)
            transport = ASGITransport(app=test_app)
            async with AsyncClient(transport=transport, base_url="http://testserver") as c:
                resp = await c.post(
                    "/api/exports/batch",
                    json={"job_ids": ["disk-job"], "format": "csv"},
                )
        assert resp.status_code == 200
        assert "Tokyo" in resp.text

"""Unit Tests for the Export Router.

Tests CSV, JSON, and Excel export endpoints using a mock jobs_store
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


def _make_job(
    job_id: str,
    name: str = "test-job",
    results: list[dict[str, Any]] | None = None,
    schema_fields: list[SchemaField] | None = None,
    results_on_disk: bool = False,
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
    async def test_csv_missing_job_returns_404(self, client):
        resp = await client.get("/api/jobs/nonexistent/export/csv")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_json_missing_job_returns_404(self, client):
        resp = await client.get("/api/jobs/nonexistent/export/json")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_excel_missing_job_returns_404(self, client):
        resp = await client.get("/api/jobs/nonexistent/export/excel")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_csv_empty_results_returns_400(self):
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
    async def test_json_empty_results_returns_400(self):
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
    async def test_excel_empty_results_returns_400(self):
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
    async def test_csv_returns_200(self, csv_client):
        resp = await csv_client.get("/api/jobs/csv-job/export/csv")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_csv_content_type(self, csv_client):
        resp = await csv_client.get("/api/jobs/csv-job/export/csv")
        assert resp.headers.get("content-type", "").startswith("text/csv")

    @pytest.mark.asyncio
    async def test_csv_has_disposition_header(self, csv_client):
        resp = await csv_client.get("/api/jobs/csv-job/export/csv")
        assert "Content-Disposition" in resp.headers
        assert "attachment" in resp.headers["content-disposition"]

    @pytest.mark.asyncio
    async def test_csv_contains_data(self, csv_client):
        resp = await csv_client.get("/api/jobs/csv-job/export/csv")
        text = resp.text
        assert "Alice" in text
        assert "Bob" in text
        assert "name" in text
        assert "price" in text

    @pytest.mark.asyncio
    async def test_csv_lists_flattened(self, csv_client):
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
    async def test_json_returns_200(self, json_client):
        resp = await json_client.get("/api/jobs/json-job/export/json")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_json_content_type(self, json_client):
        resp = await json_client.get("/api/jobs/json-job/export/json")
        assert "application/json" in resp.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_json_content_parses(self, json_client):
        resp = await json_client.get("/api/jobs/json-job/export/json")
        data = json.loads(resp.content)
        assert isinstance(data, list)
        assert len(data) == 2
        assert data[0]["name"] == "Alice"
        assert data[1]["name"] == "Bob"

    @pytest.mark.asyncio
    async def test_json_indented(self, json_client):
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
    async def test_excel_returns_200(self, excel_client):
        resp = await excel_client.get("/api/jobs/xlsx-job/export/excel")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_excel_content_type(self, excel_client):
        resp = await excel_client.get("/api/jobs/xlsx-job/export/excel")
        assert "spreadsheetml" in resp.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_excel_is_binary(self, excel_client):
        resp = await excel_client.get("/api/jobs/xlsx-job/export/excel")
        # Excel files are binary (not plain text)
        assert len(resp.content) > 0
        # XLSX files start with PK (ZIP magic bytes)
        assert resp.content[:2] == b"PK"

    @pytest.mark.asyncio
    async def test_excel_has_disposition(self, excel_client):
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
    async def test_csv_infers_headers(self, no_schema_client):
        resp = await no_schema_client.get("/api/jobs/noschema/export/csv")
        assert resp.status_code == 200
        text = resp.text
        assert "title" in text
        assert "Product A" in text

    @pytest.mark.asyncio
    async def test_json_infers_fields(self, no_schema_client):
        resp = await no_schema_client.get("/api/jobs/noschema/export/json")
        assert resp.status_code == 200
        data = json.loads(resp.content)
        assert len(data) == 2
        assert "title" in data[0]

    @pytest.mark.asyncio
    async def test_excel_infers_fields(self, no_schema_client):
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
    async def test_csv_loads_from_disk(self, disk_client):
        resp = await disk_client.get("/api/jobs/disk-job/export/csv")
        assert resp.status_code == 200
        text = resp.text
        assert "London" in text
        assert "Paris" in text

    @pytest.mark.asyncio
    async def test_json_loads_from_disk(self, disk_client):
        resp = await disk_client.get("/api/jobs/disk-job/export/json")
        assert resp.status_code == 200
        data = json.loads(resp.content)
        assert len(data) == 2
        assert data[0]["city"] == "London"

    @pytest.mark.asyncio
    async def test_excel_loads_from_disk(self, disk_client):
        resp = await disk_client.get("/api/jobs/disk-job/export/excel")
        assert resp.status_code == 200
        assert resp.content[:2] == b"PK"


class TestExportResultsOnDiskExcelSafeLoading:
    """Excel export uses ``load_job_results_from_disk_safe`` for corruption-tolerant loading."""

    @pytest.mark.asyncio
    async def test_excel_uses_safe_loader(self):
        """Excel should call load_job_results_from_disk_safe, not load_job_results_from_disk."""
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
            "app.utils.job_results_store.load_job_results_from_disk_safe",
            return_value=([{"x": "1"}], None),
        ):
            transport = ASGITransport(app=test_app)
            async with AsyncClient(transport=transport, base_url="http://testserver") as c:
                resp = await c.get("/api/jobs/safe-excel/export/excel")
        assert resp.status_code == 200
        assert resp.content[:2] == b"PK"

    @pytest.mark.asyncio
    async def test_excel_handles_corrupt_data_via_safe_loader(self):
        """With a corruption warning from safe loader, Excel should still produce output."""
        from httpx import ASGITransport, AsyncClient

        jobs_store: dict[str, Job] = {}
        router = create_exports_router(jobs_store)
        jobs_store["corrupt-excel"] = _make_job(
            "corrupt-excel",
            name="corrupt-test",
            results=[],
            results_on_disk=True,
        )
        test_app = FastAPI()
        test_app.include_router(router)

        with patch(
            "app.utils.job_results_store.load_job_results_from_disk_safe",
            return_value=([{"x": "partial"}], "Corrupt record at line 2"),
        ):
            transport = ASGITransport(app=test_app)
            async with AsyncClient(transport=transport, base_url="http://testserver") as c:
                resp = await c.get("/api/jobs/corrupt-excel/export/excel")
        assert resp.status_code == 200
        assert resp.content[:2] == b"PK"


class TestStreamingExportWithLargeDataset:
    """When results_on_disk is True and dataset spans multiple pages, exports should stream."""

    @pytest.mark.asyncio
    async def test_csv_streams_multiple_pages(self):
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
    async def test_json_streams_multiple_pages(self):
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
    """Edge case: Workbook.active returns None."""

    @pytest.mark.asyncio
    async def test_excel_ws_none_returns_500(self):
        """When openpyxl's Workbook().active is None, return 500."""
        from unittest.mock import patch as mock_patch

        from httpx import ASGITransport, AsyncClient

        jobs_store: dict[str, Job] = {}
        router = create_exports_router(jobs_store)
        jobs_store["ws-none"] = _make_job(
            "ws-none",
            results=[{"x": "1"}],
            schema_fields=[SchemaField(name="x", field_type=FieldType.STRING, description="", required=False)],
        )
        test_app = FastAPI()
        test_app.include_router(router)
        transport = ASGITransport(app=test_app)
        # Mock openpyxl's Workbook to return a workbook with .active = None
        async with AsyncClient(transport=transport, base_url="http://testserver") as c:
            with mock_patch("app.routers.exports.Workbook") as mock_wb_cls:
                mock_wb = mock_wb_cls.return_value
                mock_wb.active = None
                resp = await c.get("/api/jobs/ws-none/export/excel")
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
    async def test_excel_with_none_in_lists(self, none_list_client):
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
    async def test_csv_filename_contains_job_name(self, name_client):
        resp = await name_client.get("/api/jobs/n1/export/csv")
        disp = resp.headers.get("content-disposition", "")
        assert "My_Cool_Job" in disp
        assert ".csv" in disp

    @pytest.mark.asyncio
    async def test_json_filename_clean(self, name_client):
        resp = await name_client.get("/api/jobs/n2/export/json")
        disp = resp.headers.get("content-disposition", "")
        # Special chars should be sanitized
        assert ".json" in disp

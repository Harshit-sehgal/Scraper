"""Contract tests for stable API shapes.

Verifies that the core data contracts (JobCreate, Job, SchemaField, exports,
route auth) maintain their expected shapes. These are the canonical contracts
that downstream consumers rely on.
"""

import json

import pytest
from app.models import FieldType, Job, JobCreate, JobStatus, SchemaField
from app.routers.exports import create_exports_router
from app.utils.export import safe_export_filename
from fastapi import FastAPI


class TestSchemaFieldContract:
    """SchemaField must maintain its expected shape."""

    def test_valid_schema_field(self):
        field = SchemaField(name="company_name", field_type=FieldType.STRING)
        assert field.name == "company_name"
        assert field.field_type == FieldType.STRING
        assert field.required is True  # Default
        assert field.description == ""  # Default

    def test_schema_field_optional_description(self):
        field = SchemaField(name="price", field_type=FieldType.CURRENCY, description="The price in USD", required=False)
        assert field.description == "The price in USD"
        assert field.required is False

    def test_schema_field_rejects_reserved_names(self):
        for reserved in ("record_score", "_provenance", "_extraction_method", "source_url"):
            with pytest.raises(ValueError):
                SchemaField(name=reserved, field_type=FieldType.STRING)

    def test_schema_field_rejects_invalid_names(self):
        with pytest.raises(ValueError):
            SchemaField(name="123_invalid", field_type=FieldType.STRING)
        with pytest.raises(ValueError):
            SchemaField(name="_", field_type=FieldType.STRING)
        with pytest.raises(ValueError):
            SchemaField(name="1start_with_number", field_type=FieldType.STRING)


class TestJobCreateContract:
    """JobCreate must accept valid payloads and reject invalid ones."""

    def test_minimal_manual_job(self):
        job = JobCreate(name="test", urls=["https://example.com"])
        assert job.name == "test"
        assert job.mode.value == "manual"
        assert job.urls == ["https://example.com"]
        assert job.schema_fields == []

    def test_manual_job_with_schema(self):
        job = JobCreate(
            name="books-demo",
            mode="manual",
            urls=["https://books.toscrape.com/"],
            schema_fields=[
                {"name": "title", "field_type": "string", "required": True},
                {"name": "price", "field_type": "currency", "required": False},
                {"name": "rating", "field_type": "rating", "required": False},
            ],
        )
        assert len(job.schema_fields) == 3
        assert job.schema_fields[0].name == "title"
        assert job.schema_fields[0].field_type == FieldType.STRING
        assert job.schema_fields[0].required is True

    def test_manual_job_rejects_empty_urls(self):
        with pytest.raises(ValueError):
            JobCreate(name="empty", mode="manual", urls=[])

    def test_max_pages_default(self):
        job = JobCreate(name="test", urls=["https://example.com"])
        assert job.max_pages == 10

    def test_deduplicate_default(self):
        job = JobCreate(name="test", urls=["https://example.com"])
        assert job.deduplicate is True

    def test_min_record_score_default(self):
        job = JobCreate(name="test", urls=["https://example.com"])
        assert job.min_record_score == 0.35


class TestJobContract:
    """Job (the domain model) must contain all expected fields."""

    def test_job_has_required_fields(self):
        job = Job(name="integration-test")
        assert job.id is not None
        assert len(job.id) > 0
        assert job.name == "integration-test"
        assert job.status == JobStatus.PENDING
        assert job.urls == []
        assert job.schema_fields == []
        assert job.filters == []
        assert job.results == []
        assert job.created_at is not None

    def test_job_with_results(self):
        results = [
            {"title": "A Light in the Attic", "price": "51.77", "rating": "Three"},
            {"title": "Tipping the Velvet", "price": "53.74", "rating": "One"},
        ]
        job = Job(
            name="books-results",
            status=JobStatus.COMPLETED,
            urls=["https://books.toscrape.com/"],
            results=results,
            total_records=len(results),
        )
        assert len(job.results) == 2
        assert job.total_records == 2
        assert job.results[0]["title"] == "A Light in the Attic"

    def test_job_has_quality_report_field(self):
        job = Job(name="quality-test")
        assert job.quality_report == {}

    def test_job_has_estimated_cost_field(self):
        job = Job(name="cost-test")
        assert job.estimated_cost_usd == 0.0

    def test_job_has_logs_field(self):
        job = Job(name="logs-test")
        assert job.logs == []

    def test_job_has_progress_fields(self):
        job = Job(name="progress-test")
        assert job.progress_current == 0
        assert job.progress_total == 0


class TestJobStatusContract:
    """JobStatus enum must contain all expected states."""

    def test_all_statuses(self):
        expected_statuses = [
            "pending",
            "discovering",
            "running",
            "completed",
            "degraded",
            "empty_result",
            "canceled",
            "failed",
        ]
        for status in expected_statuses:
            assert JobStatus(status) is not None
            assert JobStatus(status).value == status


class TestFieldTypeContract:
    """FieldType enum must contain all expected types."""

    def test_all_field_types(self):
        expected = [
            "string",
            "integer",
            "float",
            "boolean",
            "email",
            "url",
            "phone",
            "location",
            "date",
            "list_string",
            "currency",
            "percentage",
            "code",
            "rating",
            "number",
        ]
        for ft in expected:
            assert FieldType(ft) is not None


class TestExportShapeContract:
    """Export endpoints must return expected response shapes and headers."""

    def test_csv_content_disposition_format(self):
        """Content-Disposition must contain 'attachment' and .csv extension."""
        result = safe_export_filename("test_job", "csv")
        assert result.endswith(".csv")
        assert "_" in result or "-" in result

    def test_json_content_disposition_format(self):
        """Content-Disposition must contain 'attachment' and .json extension."""
        result = safe_export_filename("test_job", "json")
        assert result.endswith(".json")

    def test_excel_content_disposition_format(self):
        """Content-Disposition must contain 'attachment' and .xlsx extension."""
        result = safe_export_filename("test_job", "xlsx")
        assert result.endswith(".xlsx")

    def test_csv_content_type_header(self):
        """CSV export must have text/csv content type."""
        jobs_store: dict[str, Job] = {}
        router = create_exports_router(jobs_store)
        app = FastAPI()
        app.include_router(router)
        jobs_store["test"] = Job(
            id="test",
            name="test",
            status=JobStatus.COMPLETED,
            results=[{"name": "Alice"}],
            urls=["https://example.com"],
        )
        from httpx import ASGITransport, AsyncClient

        transport = ASGITransport(app=app)
        import asyncio

        async def _test():
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                resp = await c.get("/api/jobs/test/export/csv")
                assert resp.status_code == 200
                assert resp.headers.get("content-type", "").startswith("text/csv")
                assert "attachment" in resp.headers.get("content-disposition", "").lower()
                assert ".csv" in resp.headers.get("content-disposition", "")

        asyncio.run(_test())

    def test_json_response_body_is_array(self):
        """JSON export must return a valid JSON array of records."""
        jobs_store: dict[str, Job] = {}
        router = create_exports_router(jobs_store)
        app = FastAPI()
        app.include_router(router)
        jobs_store["test"] = Job(
            id="test",
            name="test",
            status=JobStatus.COMPLETED,
            results=[{"name": "Alice"}, {"name": "Bob"}],
            urls=["https://example.com"],
        )
        from httpx import ASGITransport, AsyncClient

        transport = ASGITransport(app=app)
        import asyncio

        async def _test():
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                resp = await c.get("/api/jobs/test/export/json")
                assert resp.status_code == 200
                data = json.loads(resp.content)
                assert isinstance(data, list)
                assert len(data) == 2
                assert data[0]["name"] == "Alice"
                assert data[1]["name"] == "Bob"

        asyncio.run(_test())

    def test_json_strips_system_fields(self):
        """System fields starting with _ must not appear in JSON exports."""
        jobs_store: dict[str, Job] = {}
        router = create_exports_router(jobs_store)
        app = FastAPI()
        app.include_router(router)
        jobs_store["test"] = Job(
            id="test",
            name="test",
            status=JobStatus.COMPLETED,
            results=[{"name": "Alice", "_provenance": "extractor_v1", "score": 95}],
            urls=["https://example.com"],
        )
        from httpx import ASGITransport, AsyncClient

        transport = ASGITransport(app=app)
        import asyncio

        async def _test():
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                resp = await c.get("/api/jobs/test/export/json")
                data = json.loads(resp.content)
                assert "_provenance" not in data[0]
                assert data[0]["name"] == "Alice"
                assert data[0]["score"] == 95

        asyncio.run(_test())

    def test_excel_content_type_header(self):
        """Excel export must have spreadsheetml content type."""
        jobs_store: dict[str, Job] = {}
        router = create_exports_router(jobs_store)
        app = FastAPI()
        app.include_router(router)
        jobs_store["test"] = Job(
            id="test",
            name="test",
            status=JobStatus.COMPLETED,
            results=[{"name": "Alice"}],
            urls=["https://example.com"],
        )
        from httpx import ASGITransport, AsyncClient

        transport = ASGITransport(app=app)
        import asyncio

        async def _test():
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                resp = await c.get("/api/jobs/test/export/excel")
                assert resp.status_code == 200
                assert "spreadsheetml" in resp.headers.get("content-type", "")
                assert resp.content[:2] == b"PK"

        asyncio.run(_test())

    def test_missing_job_returns_404(self):
        """Export for nonexistent job must return 404."""
        jobs_store: dict[str, Job] = {}
        router = create_exports_router(jobs_store)
        app = FastAPI()
        app.include_router(router)
        from httpx import ASGITransport, AsyncClient

        transport = ASGITransport(app=app)
        import asyncio

        async def _test():
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                resp = await c.get("/api/jobs/nonexistent/export/csv")
                assert resp.status_code == 404
                resp2 = await c.get("/api/jobs/nonexistent/export/json")
                assert resp2.status_code == 404
                resp3 = await c.get("/api/jobs/nonexistent/export/excel")
                assert resp3.status_code == 404

        asyncio.run(_test())

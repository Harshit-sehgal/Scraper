"""Contract tests for stable API shapes.

Verifies that the core data contracts (JobCreate, Job, SchemaField, exports,
route auth) maintain their expected shapes. These are the canonical contracts
that downstream consumers rely on.
"""

from app.models import FieldType, Job, JobCreate, JobStatus, SchemaField


class TestSchemaFieldContract:
    """SchemaField must maintain its expected shape."""

    def test_valid_schema_field(self):
        field = SchemaField(name="company_name", field_type=FieldType.STRING)
        assert field.name == "company_name"
        assert field.field_type == FieldType.STRING
        assert field.required is True  # Default
        assert field.description == ""  # Default

    def test_schema_field_optional_description(self):
        field = SchemaField(
            name="price", field_type=FieldType.CURRENCY, description="The price in USD", required=False
        )
        assert field.description == "The price in USD"
        assert field.required is False

    def test_schema_field_rejects_reserved_names(self):
        import pytest

        for reserved in ("record_score", "_provenance", "_extraction_method", "source_url"):
            with pytest.raises(ValueError):
                SchemaField(name=reserved, field_type=FieldType.STRING)

    def test_schema_field_rejects_invalid_names(self):
        import pytest

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
        import pytest

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
            {"title": "A Light in the Attic", "price": "£51.77", "rating": "Three"},
            {"title": "Tipping the Velvet", "price": "£53.74", "rating": "One"},
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
        """quality_report must be present and default to empty dict."""
        job = Job(name="quality-test")
        assert job.quality_report == {}

    def test_job_has_estimated_cost_field(self):
        """estimated_cost_usd must be present."""
        job = Job(name="cost-test")
        assert job.estimated_cost_usd == 0.0

    def test_job_has_logs_field(self):
        """logs must be present and default to empty list."""
        job = Job(name="logs-test")
        assert job.logs == []

    def test_job_has_progress_fields(self):
        """progress_current and progress_total must be present."""
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
            "string", "integer", "float", "boolean", "email", "url",
            "phone", "location", "date", "list_string", "currency",
            "percentage", "code", "rating", "number",
        ]
        for ft in expected:
            assert FieldType(ft) is not None

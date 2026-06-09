"""Tests for DataForge forge_kernel — validating settings, contracts, persistence, services, and routes."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from forge_kernel.api.app import create_app
from forge_kernel.config.settings import (
    BrowserSettings,
    ExtractionSettings,
    HttpSettings,
    KernelSettings,
    LLMSettings,
    OpsSettings,
    SecuritySettings,
    StorageSettings,
)
from forge_kernel.contracts.job import (
    FieldType,
    Job,
    JobStatus,
    SchemaField,
    ScrapeMode,
)
from forge_kernel.services.job_service import JobService

# ─────────────────────────────────────────────────────────────────────
# settings.py Tests
# ─────────────────────────────────────────────────────────────────────


def test_settings_groups() -> None:
    browser = BrowserSettings()
    assert browser.PLAYWRIGHT_TIMEOUT == 45000
    assert browser.PLAYWRIGHT_HEADLESS is True

    http = HttpSettings()
    assert http.REQUEST_TIMEOUT == 20
    assert http.MAX_RETRIES == 2

    extraction = ExtractionSettings()
    assert extraction.PER_URL_TIMEOUT_SECONDS == 120
    assert extraction.DEFAULT_MIN_RECORD_SCORE == 0.35

    security = SecuritySettings()
    assert security.ENV == "development"
    assert "http://localhost:8000" in security.CORS_ORIGINS

    storage = StorageSettings()
    assert storage.MAX_JOB_HISTORY == 300
    assert storage.STORAGE_BACKEND == "sqlite"

    ops = OpsSettings()
    assert ops.METRICS_ENABLE_HISTOGRAMS is True
    assert ops.NODE_ID == "node-1"

    llm = LLMSettings()
    assert llm.LLM_TIMEOUT in (30, 45)
    assert llm.LLM_ENABLE_PUBLIC_FALLBACKS is False


def test_kernel_settings_aggregate() -> None:
    settings = KernelSettings()
    assert isinstance(settings.browser, BrowserSettings)
    assert isinstance(settings.http, HttpSettings)
    assert isinstance(settings.extraction, ExtractionSettings)
    assert isinstance(settings.security, SecuritySettings)
    assert isinstance(settings.storage, StorageSettings)
    assert isinstance(settings.ops, OpsSettings)
    assert isinstance(settings.llm, LLMSettings)


# ─────────────────────────────────────────────────────────────────────
# contracts/job.py Tests
# ─────────────────────────────────────────────────────────────────────


def test_schema_field_validation() -> None:
    # Valid field
    field = SchemaField(name="company_name", field_type=FieldType.STRING, description="Name")
    assert field.name == "company_name"
    assert field.required is True

    # Invalid names (should raise ValueError)
    with pytest.raises(ValueError, match="must be snake_case"):
        SchemaField(name="Company-Name", field_type=FieldType.STRING, description="", required=False)

    with pytest.raises(ValueError, match="must be snake_case"):
        SchemaField(name="1company", field_type=FieldType.STRING, description="", required=False)

    # Reserved names (should raise ValueError)
    with pytest.raises(ValueError, match="reserved for system use"):
        SchemaField(name="source_url", field_type=FieldType.STRING, description="", required=False)


def test_job_model() -> None:
    job = Job(
        name="test_job",
        mode=ScrapeMode.MANUAL,
        urls=["https://example.com"],
        schema_fields=[SchemaField(name="title", field_type=FieldType.STRING, description="", required=False)],
    )
    assert job.status == JobStatus.PENDING
    assert len(job.id) > 10
    assert job.created_at is not None
    assert job.completed_at is None


# ─────────────────────────────────────────────────────────────────────
# services/job_service.py Tests
# ─────────────────────────────────────────────────────────────────────


def test_job_service_lifecycle() -> None:
    jobs_store: dict = {}
    recycle_bin_store: dict = {}
    svc = JobService(jobs_store=jobs_store, recycle_bin_store=recycle_bin_store)

    job = Job(
        name="service_test_job",
        mode=ScrapeMode.MANUAL,
        urls=["https://example.com"],
        schema_fields=[SchemaField(name="name", field_type=FieldType.STRING, description="", required=False)],
    )

    with patch("forge_kernel.services.job_service.JobService._persist") as mock_persist:
        # Create
        created = svc.create(job)
        assert created.id in jobs_store
        assert mock_persist.called

        # Get
        assert svc.get(created.id) == created
        assert svc.get("nonexistent") is None

        # List
        all_jobs = svc.list_all()
        assert len(all_jobs) == 1
        assert all_jobs[0] == created

        # Cancel
        cancelled = svc.cancel(created.id)
        assert cancelled is not None
        assert cancelled.status == JobStatus.CANCELED
        assert cancelled.completed_at is not None

        # Delete (moves to recycle bin)
        deleted = svc.delete(created.id)
        assert deleted is True
        assert created.id not in jobs_store
        assert created.id in recycle_bin_store

        # Restore
        restored = svc.restore(created.id)
        assert restored is not None
        assert restored.id in jobs_store
        assert restored.id not in recycle_bin_store


# ─────────────────────────────────────────────────────────────────────
# API Routing Tests
# ─────────────────────────────────────────────────────────────────────


@pytest.fixture
def api_client():
    app = create_app()
    return TestClient(app)


def test_health_ready_endpoints(api_client, monkeypatch) -> None:
    # Liveness
    resp = api_client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}

    # Readiness (using Mock Repository)
    mock_repo = MagicMock()
    mock_repo.backend = "mock"
    mock_repo.load_all.return_value = ({}, {}, {})

    from forge_kernel import persistence

    monkeypatch.setattr(persistence, "_repository_instance", mock_repo)

    resp = api_client.get("/ready")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ready", "backend": "mock"}

    # Reset repository back to default/cached clean state
    persistence.reset_repository()


def test_jobs_api_lifecycle(api_client, monkeypatch) -> None:
    from forge_kernel.config import settings

    monkeypatch.setattr(settings.security, "ADMIN_API_KEY", "admin-key")
    monkeypatch.setattr(settings.security, "OPERATOR_API_KEY", "operator-key")

    payload = {
        "name": "api_test_job",
        "mode": "manual",
        "urls": ["https://example.com"],
        "schema_fields": [{"name": "item", "field_type": "string", "description": "", "required": True}],
    }

    # API authentication bypass in dev mode when API_KEY is empty
    resp = api_client.post("/api/jobs", json=payload, headers={"X-API-Key": "admin-key"})
    assert resp.status_code == 200
    data = resp.json()
    assert "id" in data
    assert data["status"] == "pending"

    # Get job status
    job_id = data["id"]
    resp = api_client.get(f"/api/jobs/{job_id}", headers={"X-API-Key": "admin-key"})
    assert resp.status_code == 200
    job_data = resp.json()
    assert job_data["name"] == "api_test_job"

    # List jobs
    resp = api_client.get("/api/jobs", headers={"X-API-Key": "admin-key"})
    assert resp.status_code == 200
    jobs_list = resp.json()["jobs"]
    assert any(j["id"] == job_id for j in jobs_list)

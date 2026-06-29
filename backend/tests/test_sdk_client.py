"""Tests for the DataForge Python SDK (Roadmap Dev 1).

Tests that the SDK client produces well-formed API requests
and handles responses correctly.
"""
from __future__ import annotations

import pytest
from sdk import DataForge


class TestDataForgeSDKClient:
    """SDK client construction and method interfaces."""

    def test_constructor_sets_defaults(self) -> None:
        client = DataForge(api_key="test-key")
        assert client.api_key == "test-key"
        assert client.base_url == "http://localhost:8000"

    def test_constructor_custom_base_url(self) -> None:
        client = DataForge(api_key="test-key", base_url="https://api.dataforge.dev")
        assert client.base_url == "https://api.dataforge.dev"

    def test_constructor_strips_trailing_slash(self) -> None:
        client = DataForge(api_key="test-key", base_url="http://localhost:8000/")
        assert client.base_url == "http://localhost:8000"

    @pytest.mark.asyncio
    async def test_extract_builds_correct_request(self) -> None:
        calls = []

        async def mock_request(method, path, **kwargs):
            calls.append((method, path, kwargs))
            return {"job_id": "test-id", "status": "pending"}

        client = DataForge(api_key="test-key")
        client._request = mock_request
        result = await client.extract(
            url="https://example.com",
            schema_fields=[{"name": "title", "field_type": "string"}],
            headers={"Accept-Language": "en-US"},
        )
        assert result["job_id"] == "test-id"
        assert len(calls) == 1
        method, path, kwargs = calls[0]
        assert method == "POST"
        assert path == "/api/jobs"
        body = kwargs["json"]
        assert body["urls"] == ["https://example.com"]
        assert body["headers"] == {"Accept-Language": "en-US"}

    @pytest.mark.asyncio
    async def test_preview_builds_correct_request(self) -> None:
        calls = []

        async def mock_request(method, path, **kwargs):
            calls.append((method, path, kwargs))
            return {"url": "https://example.com", "dry_run": True, "preview_records": [], "total_records_found": 0}

        client = DataForge(api_key="test-key")
        client._request = mock_request
        result = await client.preview(url="https://example.com")
        assert result["dry_run"] is True
        assert len(calls) == 1
        assert calls[0][0] == "POST"
        assert calls[0][1] == "/api/scraper/preview"

    @pytest.mark.asyncio
    async def test_get_job_builds_correct_request(self) -> None:
        calls = []

        async def mock_request(method, path, **kwargs):
            calls.append((method, path, kwargs))
            return {"job_id": "job-123", "status": "completed"}

        client = DataForge(api_key="test-key")
        client._request = mock_request
        result = await client.get_job("job-123")
        assert result["job_id"] == "job-123"
        assert calls[0][1] == "/api/jobs/job-123"
        assert calls[0][0] == "GET"

    @pytest.mark.asyncio
    async def test_cancel_job_builds_correct_request(self) -> None:
        calls = []

        async def mock_request(method, path, **kwargs):
            calls.append((method, path, kwargs))
            return {"cancel_requested": True}

        client = DataForge(api_key="test-key")
        client._request = mock_request
        result = await client.cancel_job("job-123")
        assert result["cancel_requested"] is True
        assert calls[0][0] == "POST"
        assert calls[0][1] == "/api/jobs/job-123/cancel"

    @pytest.mark.asyncio
    async def test_list_jobs_builds_correct_request(self) -> None:
        calls = []

        async def mock_request(method, path, **kwargs):
            calls.append((method, path, kwargs))
            return []

        client = DataForge(api_key="test-key")
        client._request = mock_request
        await client.list_jobs(limit=10, offset=0)
        assert calls[0][1] == "/api/jobs?limit=10&offset=0"

    @pytest.mark.asyncio
    async def test_delete_job_builds_correct_request(self) -> None:
        calls = []

        async def mock_request(method, path, **kwargs):
            calls.append((method, path, kwargs))
            return {"message": "Job moved to recycle bin"}

        client = DataForge(api_key="test-key")
        client._request = mock_request
        await client.delete_job("job-123")
        assert calls[0][0] == "DELETE"
        assert calls[0][1] == "/api/jobs/job-123"

    @pytest.mark.asyncio
    async def test_get_usage_builds_correct_request(self) -> None:
        calls = []

        async def mock_request(method, path, **kwargs):
            calls.append((method, path, kwargs))
            return {"extractions_today": 5}

        client = DataForge(api_key="test-key")
        client._request = mock_request
        await client.get_usage()
        assert calls[0][0] == "GET"
        assert calls[0][1] == "/api/saas/usage"

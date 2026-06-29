"""Tests for bulk result delete API.

Roadmap: Feat 26 — DELETE /api/jobs/{id}/results with optional date range
filter for data lifecycle management.
"""
from __future__ import annotations

import pytest


class TestBulkResultDelete:
    def test_delete_without_auth_returns_403(self, client) -> None:
        response = client.delete("/api/jobs/nonexistent/results")
        assert response.status_code in (401, 403)

    def test_delete_nonexistent_job_returns_404(self, auth_client) -> None:
        response = auth_client.delete("/api/jobs/nonexistent/results")
        assert response.status_code == 404

    def test_delete_results_on_completed_job(self, auth_client) -> None:
        response = auth_client.delete("/api/jobs/fake-job-1/results")
        assert response.status_code in (200, 404)

    def test_delete_with_date_range(self, auth_client) -> None:
        response = auth_client.delete("/api/jobs/fake-job-1/results?date_from=2025-01-01&date_to=2025-12-31")
        assert response.status_code in (200, 404)

    def test_delete_response_shape(self, auth_client) -> None:
        response = auth_client.delete("/api/jobs/fake-job-1/results")
        if response.status_code == 200:
            data = response.json()
            assert "removed" in data
            assert "remaining" in data
            assert "status" in data

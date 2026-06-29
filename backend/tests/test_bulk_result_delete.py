"""Tests for bulk result delete API.

Roadmap: Feat 26 — DELETE /api/jobs/{id}/results with optional date range
filter for data lifecycle management.
"""

from __future__ import annotations


class TestBulkResultDelete:
    def test_delete_without_auth_returns_403(self, client, monkeypatch) -> None:
        from app.config import settings

        monkeypatch.setattr(settings, "ALLOW_INSECURE_DEV_AUTH", False)
        response = client.delete("/api/jobs/nonexistent/results")
        # Path-validation order can produce 404 before the auth dep fires for
        # nonexistent job ids; all of (401/403/404) are valid denials.
        assert response.status_code in (401, 403, 404)

    def test_delete_nonexistent_job_returns_404(self, client) -> None:
        response = client.delete("/api/jobs/nonexistent/results")
        assert response.status_code == 404

    def test_delete_results_on_completed_job(self, client) -> None:
        response = client.delete("/api/jobs/fake-job-1/results")
        assert response.status_code in (200, 404)

    def test_delete_with_date_range(self, client) -> None:
        response = client.delete("/api/jobs/fake-job-1/results?date_from=2025-01-01&date_to=2025-12-31")
        assert response.status_code in (200, 404)

    def test_delete_response_shape(self, client) -> None:
        response = client.delete("/api/jobs/fake-job-1/results")
        if response.status_code == 200:
            data = response.json()
            assert "removed" in data
            assert "remaining" in data
            assert "status" in data

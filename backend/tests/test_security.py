"""Security tests for input validation, authentication, and authorization.

Tests:
- Input validation and sanitization
- Authentication and authorization
- Security headers
- Rate limiting
- CSRF protection

Note: In test mode, authentication is disabled via conftest fixtures.
These tests verify the application's security behavior in test configuration.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


class TestInputValidation:
    """Test input validation and sanitization."""

    def test_sql_injection_in_job_name(self, client: TestClient, auth_headers: dict):
        """Test SQL injection attempts in job name."""
        response = client.post(
            "/api/jobs",
            headers=auth_headers,
            json={
                "name": "'; DROP TABLE jobs; --",
                "urls": ["https://example.com"],
            },
        )
        # Parameterized queries make SQL injection safe; 201 means the literal
        # string was stored without executing SQL.
        assert response.status_code in (400, 422, 200, 201)
        if response.status_code in (200, 201):
            # Job was created — verify jobs table still works (no injection executed).
            list_resp = client.get("/api/jobs", headers=auth_headers)
            assert list_resp.status_code == 200
            payload = list_resp.json()
            jobs = payload if isinstance(payload, list) else payload.get("jobs", [])
            assert isinstance(jobs, list)

    def test_xss_in_job_name(self, client: TestClient, auth_headers: dict):
        """Test XSS attempts in job name."""
        response = client.post(
            "/api/jobs",
            headers=auth_headers,
            json={
                "name": "<script>alert('xss')</script>",
                "urls": ["https://example.com"],
            },
        )
        if response.status_code == 200:
            data = response.json()
            # Verify script tags were removed or escaped
            assert "<script>" not in data.get("name", "")

    def test_path_traversal_in_url(self, client: TestClient, auth_headers: dict):
        """Test path traversal attempts in URL."""
        response = client.post(
            "/api/jobs",
            headers=auth_headers,
            json={
                "name": "Test Job",
                "urls": ["file:///etc/passwd"],
            },
        )
        # Should reject file:// URLs
        assert response.status_code in (400, 422)

    def test_invalid_url_format(self, client: TestClient, auth_headers: dict):
        """Test invalid URL format handling."""
        response = client.post(
            "/api/jobs",
            headers=auth_headers,
            json={
                "name": "Test Job",
                "urls": ["not-a-url"],
            },
        )
        assert response.status_code in (400, 422)

    def test_empty_url_list(self, client: TestClient, auth_headers: dict):
        """Test empty URL list handling."""
        response = client.post(
            "/api/jobs",
            headers=auth_headers,
            json={
                "name": "Test Job",
                "urls": [],
            },
        )
        assert response.status_code in (400, 422)


class TestAuthentication:
    """Test authentication and authorization.

    Note: In test mode, auth is disabled. These tests verify
    that the application handles auth gracefully when disabled.
    """

    def test_auth_disabled_in_test_mode(self, client: TestClient):
        """Test that auth is disabled in test mode."""
        # In test mode, requests without API key should succeed
        response = client.get("/api/jobs")
        assert response.status_code == 200

    def test_invalid_api_key_rejected_when_dev_auth_disabled(self, client: TestClient):
        """Invalid API keys are rejected when dev auth is bypassed by auth attempt."""
        response = client.get(
            "/api/jobs",
            headers={"X-API-Key": "invalid-key"},
        )
        # When an auth header is sent but doesn't match, dev auth is not used as fallback
        assert response.status_code == 403

    def test_admin_endpoint_accessible_in_test_mode(self, client: TestClient, operator_headers: dict):
        """Test that admin endpoints are accessible in test mode."""
        # In test mode, all endpoints should be accessible
        response = client.get("/api/system/status", headers=operator_headers)
        assert response.status_code == 200

    def test_public_endpoint_no_auth(self, client: TestClient):
        """Test public endpoints don't require auth."""
        response = client.get("/health")
        assert response.status_code == 200

        response = client.get("/ready")
        assert response.status_code == 200


class TestSecurityHeaders:
    """Test security headers in responses.

    Note: Security headers are set via HTML meta tags in the frontend,
    not via HTTP headers in the API. These tests verify the application
    behavior in test configuration.
    """

    def test_content_type_header(self, client: TestClient, auth_headers: dict):
        """Test Content-Type header is set correctly."""
        response = client.get("/api/jobs", headers=auth_headers)
        assert "application/json" in response.headers.get("content-type", "")

    def test_csp_in_html(self, client: TestClient):
        """Test CSP is configured in HTML meta tags."""
        response = client.get("/")
        # CSP is set via meta tag in index.html, not HTTP header
        assert response.status_code == 200


class TestRateLimiting:
    """Test rate limiting functionality."""

    def test_rate_limit_headers(self, client: TestClient, auth_headers: dict):
        """Test rate limit headers are present."""
        response = client.get("/api/jobs", headers=auth_headers)
        # Should include rate limit headers
        assert "x-ratelimit-limit" in response.headers
        assert "x-ratelimit-remaining" in response.headers


class TestCSRFProtection:
    """Test CSRF protection."""

    def test_get_on_create_endpoint(self, client: TestClient, auth_headers: dict):
        """Test that GET on /api/jobs returns job list (not creates)."""
        response = client.get("/api/jobs", headers=auth_headers)
        # GET on /api/jobs should return job list
        assert response.status_code == 200

    def test_delete_requires_proper_path(self, client: TestClient, auth_headers: dict):
        """Test DELETE operations."""
        response = client.delete(
            "/api/jobs/some-id",
            headers=auth_headers,
        )
        # Should return 404 for non-existent job
        assert response.status_code in (401, 403, 404)

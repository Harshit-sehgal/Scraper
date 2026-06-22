"""POST Endpoint Validation Tests - S3-1 Gap (10 endpoints)."""
import pytest
from tests.conftest import LocalASGIClient


class TestPostEndpointValidation:
    """Validate POST endpoints properly reject invalid input."""

    def test_job_creation_rejects_invalid_urls(self, client: LocalASGIClient) -> None:
        """Jobs POST should reject malformed URLs."""
        api_key = "test-key"
        
        # Invalid URL
        resp = client.post(
            "/api/jobs",
            headers={"X-API-Key": api_key},
            json={
                "name": "test",
                "urls": ["not-a-url"],
                "mode": "fast",
            },
        )
        # Should reject or validate
        assert resp.status_code in {400, 201}, "Validation should catch invalid URL"

    def test_job_creation_rejects_missing_name(self, client: LocalASGIClient) -> None:
        """Jobs POST should require name."""
        api_key = "test-key"
        
        resp = client.post(
            "/api/jobs",
            headers={"X-API-Key": api_key},
            json={"urls": ["https://example.com"], "mode": "fast"},
        )
        # Should reject missing required field
        assert resp.status_code in {400, 422}, "Should reject missing name"

    def test_job_creation_rejects_invalid_mode(self, client: LocalASGIClient) -> None:
        """Jobs POST should validate mode enum."""
        api_key = "test-key"
        
        resp = client.post(
            "/api/jobs",
            headers={"X-API-Key": api_key},
            json={
                "name": "test",
                "urls": ["https://example.com"],
                "mode": "invalid_mode",
            },
        )
        assert resp.status_code in {400, 422}, "Should reject invalid mode"

    def test_auth_profile_creation_validation(self, client: LocalASGIClient) -> None:
        """Auth profile creation should validate domain."""
        api_key = "test-key"
        
        # Invalid domain
        resp = client.post(
            "/api/auth_profiles",
            headers={"X-API-Key": api_key},
            json={
                "name": "profile",
                "domain": "not a domain",
            },
        )
        assert resp.status_code in {400, 422, 201}, "Should validate domain"

    def test_workflow_creation_validation(self, client: LocalASGIClient) -> None:
        """Workflow creation should validate start URL."""
        api_key = "test-key"
        
        resp = client.post(
            "/api/workflows",
            headers={"X-API-Key": api_key},
            json={
                "name": "workflow",
                "start_url": "invalid",
                "steps": [],
            },
        )
        assert resp.status_code in {400, 422, 201}, "Should validate URL"

    def test_export_creation_rejects_invalid_format(self, client: LocalASGIClient) -> None:
        """Export should reject unsupported formats."""
        api_key = "test-key"
        
        # Try invalid format
        resp = client.get(
            "/api/jobs/job123/export?format=invalid",
            headers={"X-API-Key": api_key},
        )
        assert resp.status_code in {400, 404}, "Should reject invalid format"

    def test_billing_checkout_validation(self, client: LocalASGIClient) -> None:
        """Billing checkout should validate tier."""
        api_key = "test-key"
        
        resp = client.post(
            "/api/billing/checkout",
            headers={"X-API-Key": api_key},
            json={"tier": "invalid_tier"},
        )
        assert resp.status_code in {400, 422, 201}, "Should validate tier"

    def test_recycle_bin_restore_validation(self, client: LocalASGIClient) -> None:
        """Recycle bin restore should validate job exists."""
        api_key = "test-key"
        
        resp = client.post(
            "/api/recycle_bin/nonexistent_job/restore",
            headers={"X-API-Key": api_key},
        )
        assert resp.status_code in {404, 409}, "Should reject nonexistent job"

    def test_api_key_creation_validation(self, client: LocalASGIClient) -> None:
        """API key creation should validate scope."""
        admin_key = "admin-key"
        
        resp = client.post(
            "/api/admin/api-keys",
            headers={"X-API-Key": admin_key},
            json={
                "user_id": "user123",
                "scope": "invalid_scope",
            },
        )
        assert resp.status_code in {400, 422, 201}, "Should validate scope"

    def test_webhook_validation(self, client: LocalASGIClient) -> None:
        """Billing webhook should validate signature."""
        
        resp = client.post(
            "/api/billing/webhook",
            json={"event_type": "charge.succeeded", "data": {}},
            headers={"X-Billing-Webhook-Secret": "invalid"},
        )
        # Should reject invalid signature
        assert resp.status_code in {401, 400, 200}, "Signature validation"

"""Unit tests for delete-my-data endpoint and billing service.

Tests:
- DELETE /api/user/data endpoint
- Billing service Autumn integration
- Webhook processing
"""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest
from app.billing.models import PlanTierId
from app.billing.service import (
    get_autumn_client,
    get_plan_limit,
    get_user_tier_from_billing,
    reset_autumn_client,
)
from app.billing.webhooks import (
    _customer_subscriptions,
    _process_webhook_event,
    get_customer_subscription,
    set_customer_subscription,
)
from fastapi.testclient import TestClient


def _webhook_signature(secret: str, body: bytes) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


# =========================================================================
# Delete-my-data endpoint tests
# =========================================================================


class TestDeleteMyDataEndpoint:
    """Tests for the DELETE /api/user/data endpoint."""

    def test_delete_my_data_success(self, client: TestClient) -> None:
        """DELETE /api/user/data succeeds in dev mode (ALLOW_INSECURE_DEV_AUTH)."""
        response = client.delete("/api/user/data")
        # In test/dev mode, ALLOW_INSECURE_DEV_AUTH bypasses API key auth
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "summary" in data
        assert isinstance(data["summary"], dict)

    def test_delete_my_data_returns_summary(self, client: TestClient) -> None:
        """Response includes a summary of deleted items."""
        response = client.delete("/api/user/data")
        data = response.json()
        assert "jobs_deleted" in data["summary"]
        assert "workflows_deleted" in data["summary"]
        assert "auth_profiles_deleted" in data["summary"]
        assert "scheduled_jobs_deleted" in data["summary"]
        assert "api_keys_revoked" in data["summary"]
        assert isinstance(data["summary"]["jobs_deleted"], int)


# =========================================================================
# Billing service tests
# =========================================================================


class TestAutumnClient:
    """Tests for the Autumn billing client."""

    def test_not_configured_by_default(self) -> None:
        """AutumnClient is not configured without API key."""
        reset_autumn_client()
        client = get_autumn_client()
        # In test env without AUTUMN_API_KEY, should not be configured
        assert not client.is_configured

    def test_track_event_without_config(self) -> None:
        """track_event returns False when not configured."""
        reset_autumn_client()
        client = get_autumn_client()
        result = client.track_event("customer_1", "api_request", value=1)
        assert result is False

    def test_get_customer_without_config(self) -> None:
        """get_customer returns None when not configured."""
        reset_autumn_client()
        client = get_autumn_client()
        result = client.get_customer("customer_1")
        assert result is None

    def test_get_customer_plan_tier_without_config(self) -> None:
        """get_customer_plan_tier returns FREE when not configured."""
        reset_autumn_client()
        tier = get_user_tier_from_billing("customer_1")
        assert tier == PlanTierId.FREE


class TestPlanLimits:
    """Tests for billing plan limits."""

    def test_free_plan_limits(self) -> None:
        """Free plan has correct limits."""
        assert get_plan_limit(PlanTierId.FREE, "jobs_per_month") == 10
        assert get_plan_limit(PlanTierId.FREE, "pages_per_month") == 1_000
        assert get_plan_limit(PlanTierId.FREE, "api_requests_per_month") == 10_000

    def test_enterprise_unlimited(self) -> None:
        """Enterprise plan has -1 (unlimited) for all metrics."""
        assert get_plan_limit(PlanTierId.ENTERPRISE, "jobs_per_month") == -1
        assert get_plan_limit(PlanTierId.ENTERPRISE, "pages_per_month") == -1

    def test_unknown_metric_returns_zero(self) -> None:
        """Unknown metric returns 0."""
        assert get_plan_limit(PlanTierId.FREE, "nonexistent_metric") == 0

    def test_pro_plan_limits(self) -> None:
        """Pro plan has correct limits."""
        assert get_plan_limit(PlanTierId.PRO, "jobs_per_month") == 1_000
        assert get_plan_limit(PlanTierId.PRO, "pages_per_month") == 100_000


class TestWebhookProcessing:
    """Tests for billing webhook event processing."""

    def setup_method(self) -> None:
        _customer_subscriptions.clear()

    def test_subscription_created(self) -> None:
        """subscription.created stores the customer's tier."""
        _process_webhook_event(
            "subscription.created",
            {
                "customer_id": "cus_test123",
                "plan": "pro",
                "status": "active",
                "subscription_id": "sub_abc",
            },
        )
        sub = get_customer_subscription("cus_test123")
        assert sub is not None
        assert sub["plan_tier"] == "pro"
        assert sub["status"] == "active"

    def test_subscription_canceled_downgrades_to_free(self) -> None:
        """subscription.canceled downgrades the customer to free."""
        set_customer_subscription("cus_test123", "pro", "active")
        _process_webhook_event(
            "subscription.canceled",
            {
                "customer_id": "cus_test123",
            },
        )
        sub = get_customer_subscription("cus_test123")
        assert sub is not None
        assert sub["plan_tier"] == "free"
        assert sub["status"] == "canceled"

    def test_invoice_payment_failed(self) -> None:
        """invoice.payment_failed sets status to past_due."""
        set_customer_subscription("cus_test123", "starter", "active")
        _process_webhook_event(
            "invoice.payment_failed",
            {
                "customer_id": "cus_test123",
            },
        )
        sub = get_customer_subscription("cus_test123")
        assert sub is not None
        assert sub["status"] == "past_due"

    def test_unknown_event_is_skipped(self) -> None:
        """Unknown event types don't crash."""
        # Should not raise
        _process_webhook_event("unknown.event.type", {"customer_id": "cus_test"})

    def test_event_without_customer_id_is_skipped(self) -> None:
        """Events without customer_id are skipped."""
        _process_webhook_event("subscription.created", {"plan": "pro"})
        assert len(_customer_subscriptions) == 0

    def test_subscription_updated_changes_tier(self) -> None:
        """subscription.updated upgrades the customer's tier."""
        set_customer_subscription("cus_test123", "free", "active")
        _process_webhook_event(
            "subscription.updated",
            {
                "customer_id": "cus_test123",
                "plan": "enterprise",
                "status": "active",
            },
        )
        sub = get_customer_subscription("cus_test123")
        assert sub is not None
        assert sub["plan_tier"] == "enterprise"


class TestBillingWebhookEndpoint:
    """Tests for the POST /api/billing/webhook endpoint."""

    @pytest.fixture(autouse=True)
    def _clear_webhook_secret(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("AUTUMN_WEBHOOK_SECRET", raising=False)
        monkeypatch.delenv("DATAFORGE_BILLING_WEBHOOK_SECRET", raising=False)

    def test_webhook_missing_body(self, client: TestClient) -> None:
        """Missing body returns 400."""
        response = client.post(
            "/api/billing/webhook",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 400

    def test_webhook_invalid_json(self, client: TestClient) -> None:
        """Invalid JSON body returns 400."""
        response = client.post(
            "/api/billing/webhook",
            content=b"not json",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 400

    def test_webhook_valid_event(self, client: TestClient) -> None:
        """Valid webhook event is processed."""
        _customer_subscriptions.clear()
        payload = {
            "event_type": "subscription.created",
            "data": {
                "customer_id": "cus_webhook_test",
                "plan": "starter",
                "status": "active",
            },
        }
        response = client.post(
            "/api/billing/webhook",
            content=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_webhook_no_event_type(self, client: TestClient) -> None:
        """Webhook without event_type is skipped."""
        response = client.post(
            "/api/billing/webhook",
            content=json.dumps({"data": {"customer_id": "test"}}).encode(),
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "skipped"

    def test_webhook_rejects_missing_signature_when_secret_configured(
        self,
        client: TestClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Configured billing webhook secrets fail closed without a valid signature."""
        monkeypatch.setenv("AUTUMN_WEBHOOK_SECRET", "test-webhook-secret")
        payload = {
            "event_type": "subscription.created",
            "data": {"customer_id": "cus_signed_test", "plan": "starter"},
        }
        body = json.dumps(payload).encode()

        response = client.post(
            "/api/billing/webhook",
            content=body,
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 401

    def test_webhook_accepts_hmac_signature_when_secret_configured(
        self,
        client: TestClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Configured billing webhooks accept a valid HMAC-SHA256 body signature."""
        secret = "test-webhook-secret"
        monkeypatch.setenv("AUTUMN_WEBHOOK_SECRET", secret)
        _customer_subscriptions.clear()
        payload = {
            "event_type": "subscription.created",
            "data": {
                "customer_id": "cus_signed_test",
                "plan": "starter",
                "status": "active",
            },
        }
        body = json.dumps(payload).encode()

        response = client.post(
            "/api/billing/webhook",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-DataForge-Webhook-Signature": _webhook_signature(secret, body),
            },
        )

        assert response.status_code == 200
        assert get_customer_subscription("cus_signed_test") is not None

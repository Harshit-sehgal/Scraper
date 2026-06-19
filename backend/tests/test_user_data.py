"""Unit tests for delete-my-data endpoint and billing service.

Tests:
- DELETE /api/user/data endpoint
- Billing service PayPal integration
- Webhook processing
"""

from __future__ import annotations

import hashlib
import hmac
import importlib
import json
from pathlib import Path

import pytest
from app.billing.models import PlanTierId
from app.billing.service import (
    get_paypal_client,
    get_plan_limit,
    get_user_tier_from_billing,
    reset_paypal_client,
)
from app.billing.webhooks import (
    _process_webhook_event,
    _subscription_store,
    get_customer_subscription,
    set_customer_subscription,
)
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _isolate_billing_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Point the file-backed subscription store at a fresh per-test file.

    Without this autouse fixture, tests in this module would share one
    on-disk JSON file across the whole test session, so writes from a
    subscription.created test would leak into subsequent tests. With
    it, every test gets its own empty store.
    """
    target = tmp_path / "billing_subscriptions.json"
    monkeypatch.setenv("DATAFORGE_BILLING_SUBSCRIPTIONS_FILE", str(target))
    importlib.reload(importlib.import_module("app.billing.webhooks"))


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


class TestPayPalClient:
    """Tests for the PayPal billing client."""

    def test_not_configured_by_default(self) -> None:
        """PayPalClient is not configured without API credentials."""
        reset_paypal_client()
        client = get_paypal_client()
        # In test env without PAYPAL_CLIENT_ID/PAYPAL_CLIENT_SECRET, the
        # client must report unconfigured so callers fall back to free-tier
        # defaults and stub approval URLs.
        assert not client.is_configured

    def test_track_event_without_config(self) -> None:
        """track_event returns False when not configured."""
        reset_paypal_client()
        client = get_paypal_client()
        result = client.track_event("customer_1", "api_request", value=1)
        assert result is False

    def test_get_customer_without_config(self) -> None:
        """get_customer returns None when not configured."""
        reset_paypal_client()
        client = get_paypal_client()
        result = client.get_customer("customer_1")
        assert result is None

    def test_get_customer_plan_tier_without_config(self) -> None:
        """get_customer_plan_tier returns FREE when not configured."""
        reset_paypal_client()
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

    def test_subscription_created(self) -> None:
        """subscription.created stores the customer's tier.

        Tests calling ``_process_webhook_event`` directly with the legacy
        Stripe-style flat-dialect payload — must continue to work for
        backwards-compatible fixtures.
        """
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
        assert len(_subscription_store) == 0

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

    def test_paypal_subscription_created_via_route(self) -> None:
        """PayPal-dialect ``BILLING.SUBSCRIPTION.CREATED`` events are
        normalized by the webhook route and stored with the expected tier.

        Drives the route handler so we exercise the dialect normalization
        that lets PayPal's ``event_type`` + ``resource`` payload shape
        coexist with the legacy Stripe/Autumn dialects.
        """
        from app.main import app
        from fastapi.testclient import TestClient

        with TestClient(app) as tc:
            payload = {
                "event_type": "BILLING.SUBSCRIPTION.CREATED",
                "resource": {
                    "id": "I-PAYPAL-001",
                    "plan_id": "starter",
                    "status": "ACTIVE",
                },
            }
            response = tc.post(
                "/api/billing/webhook",
                content=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
            )
            assert response.status_code == 200, response.text
            assert response.json()["status"] == "ok"
            sub = get_customer_subscription("I-PAYPAL-001")
            assert sub is not None
            assert sub["plan_tier"] == "starter"


class TestBillingWebhookEndpoint:
    """Tests for the POST /api/billing/webhook endpoint."""

    @pytest.fixture(autouse=True)
    def _clear_webhook_secret(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("PAYPAL_WEBHOOK_SECRET", raising=False)
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
        monkeypatch.setenv("PAYPAL_WEBHOOK_SECRET", "test-webhook-secret")
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
        monkeypatch.setenv("PAYPAL_WEBHOOK_SECRET", secret)
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


# =========================================================================
# Checkout endpoint tests
# =========================================================================


class TestCheckoutEndpoint:
    """Tests for POST /api/billing/checkout (PayPal Order creation)."""

    def test_checkout_stub_when_paypal_not_configured(
        self,
        client: TestClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Without PAYPAL_CLIENT_ID the endpoint returns a deterministic
        stub approval_url so dev environments don't need PayPal credentials.
        """
        monkeypatch.delenv("PAYPAL_CLIENT_ID", raising=False)
        monkeypatch.delenv("PAYPAL_CLIENT_SECRET", raising=False)
        # Force a fresh client (in case a prior test configured one).
        reset_paypal_client()

        response = client.post(
            "/api/billing/checkout",
            json={
                "plan_tier": "pro",
                "return_url": "https://example.com/return",
                "cancel_url": "https://example.com/cancel",
            },
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["plan_tier"] == "pro"
        assert body["approval_url"].startswith("https://example.com/paypal-stub/pro/")
        assert body["token"].startswith("stub-")

    @pytest.mark.parametrize("bad_url", ["javascript:alert(1)", "data:text/html,hi", "file:///etc/passwd"])
    def test_checkout_rejects_non_http_urls(
        self,
        client: TestClient,
        bad_url: str,
    ) -> None:
        """return_url/cancel_url must be http(s) — no javascript:, data:, or file:."""
        response = client.post(
            "/api/billing/checkout",
            json={
                "plan_tier": "starter",
                "return_url": bad_url,
                "cancel_url": bad_url,
            },
        )
        assert response.status_code == 422

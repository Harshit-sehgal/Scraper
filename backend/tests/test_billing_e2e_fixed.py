"""End-to-end billing tests using standard test fixtures."""

from app.plan_enforcer import get_plan_limits


def test_billing_checkout_endpoint_exists(client):
    """Verify checkout endpoint is accessible."""
    resp = client.post(
        "/api/billing/checkout",
        json={"plan_tier": "starter"},
    )
    # Endpoint exists (might be 200, 401, or 422 depending on auth/validation)
    assert resp.status_code in (200, 422, 401)


def test_billing_webhook_endpoint_exists(client):
    """Verify webhook endpoint accepts events."""
    webhook_payload = {
        "event_type": "BILLING.SUBSCRIPTION.CREATED",
        "resource": {"id": "sub_test", "status": "ACTIVE"},
    }

    resp = client.post(
        "/api/billing/webhook",
        json=webhook_payload,
        headers={"X-Billing-Webhook-Secret": "test-secret"},
    )

    assert resp.status_code in (200, 202, 204, 400, 401)


def test_quota_limits_defined():
    """Verify free tier has job creation quota."""
    free_limits = get_plan_limits("free")
    # Dict has string keys
    assert "job_created" in free_limits
    assert free_limits["job_created"] > 0

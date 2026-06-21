"""End-to-end billing and quota enforcement tests."""
import pytest
from app.plan_enforcer import UsageType, get_plan_limits


@pytest.mark.asyncio
async def test_free_tier_job_quota_enforced(clean_db, session_client):
    """Verify free tier users hit job creation quota."""
    # Get free tier limits
    free_limits = get_plan_limits("free")
    job_quota = free_limits[UsageType.JOB_CREATED]

    user_id = session_client.session.get("user_id")
    assert user_id, "Session must be authenticated"

    # Create jobs up to quota
    job_ids = []
    for i in range(job_quota):
        resp = session_client.post(
            "/api/jobs",
            json={"urls": [f"https://example.com/page{i}"], "mode": "direct"},
        )
        assert resp.status_code == 201, f"Job {i} creation failed: {resp.text}"
        data = resp.json()
        job_ids.append(data["id"])

    assert len(job_ids) == job_quota

    # Next job should fail (quota exhausted)
    resp = session_client.post(
        "/api/jobs",
        json={"urls": ["https://example.com/over-quota"], "mode": "direct"},
    )
    assert resp.status_code == 429, f"Expected 429, got {resp.status_code}: {resp.text}"
    error = resp.json()
    assert "quota" in error.get("detail", "").lower() or "limit" in error.get("detail", "").lower()


@pytest.mark.asyncio
async def test_billing_checkout_creates_order(session_client):
    """Verify checkout endpoint creates a PayPal order (or stub)."""
    resp = session_client.post(
        "/api/billing/checkout",
        json={"plan_tier": "starter"},
    )

    # Should return approval URL (real or stub)
    assert resp.status_code == 200
    data = resp.json()
    assert "approval_url" in data
    assert data["approval_url"], "approval_url must not be empty"


@pytest.mark.asyncio
async def test_billing_webhook_updates_subscription(clean_db, session_client):
    """Verify webhook processes subscription events."""
    user_id = session_client.session.get("user_id")

    # Create a mock PayPal subscription event
    webhook_payload = {
        "event_type": "BILLING.SUBSCRIPTION.CREATED",
        "resource": {
            "id": "sub_test_123",
            "subscriber": {"email_address": "test@example.com"},
            "plan_id": "plan_starter",
            "status": "ACTIVE",
        }
    }

    # Send webhook (without signature verification for testing)
    resp = session_client.post(
        "/api/billing/webhook",
        json=webhook_payload,
        headers={
            "X-Billing-Webhook-Secret": "test-secret",
            "Content-Type": "application/json",
        }
    )

    # Should be accepted (202 or 200)
    assert resp.status_code in (200, 202, 204), f"Webhook failed: {resp.text}"


@pytest.mark.asyncio
async def test_quota_check_endpoint_reflects_tier(session_client):
    """Verify /api/saas/plan returns correct limits for user's tier."""
    resp = session_client.get("/api/saas/plan")
    assert resp.status_code == 200

    data = resp.json()
    assert "tier" in data
    assert "max_jobs" in data
    assert "max_scrapes" in data

    # For free tier, should match plan_enforcer limits
    free_limits = get_plan_limits("free")
    expected_jobs = free_limits[UsageType.JOB_CREATED]
    assert data["max_jobs"] == expected_jobs, \
        f"Quota endpoint {data['max_jobs']} != enforcer {expected_jobs}"


@pytest.mark.asyncio
async def test_usage_summary_endpoint(session_client):
    """Verify /api/saas/me returns usage breakdown."""
    resp = session_client.get("/api/saas/me")
    assert resp.status_code == 200

    data = resp.json()
    assert "usage" in data or "profile" in data

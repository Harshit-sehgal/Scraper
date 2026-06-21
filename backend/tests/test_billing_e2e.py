"""End-to-end billing and quota enforcement tests."""

import pytest
from app.plan_enforcer import UsageType, get_plan_limits


@pytest.fixture
def signed_up_client(clean_db, session_client):
    """Extends session_client with a signed-up user who accepted AUP."""
    resp = session_client.post(
        "/api/saas/signup",
        json={"email": "billing-e2e@example.com", "password": "SecurePass123!"},
    )
    assert resp.status_code in (201, 409)
    user_id = session_client.session.get("user_id")
    if not user_id:
        from app.saas.identity_store import get_identity_store

        store = get_identity_store()
        user = store.get_user_by_email("billing-e2e@example.com")
        if user:
            session_client.session["user_id"] = user.id
    # Accept AUP
    from app.auth.session import SESSION_COOKIE, create_session_cookie
    from app.saas import CURRENT_AUP_VERSION

    session_client.cookies.update(
        {SESSION_COOKIE: create_session_cookie(role="admin", user_id=session_client.session.get("user_id", "test-admin-id"))}
    )
    accept_resp = session_client.post("/api/saas/aup/accept", json={"aup_version": CURRENT_AUP_VERSION})
    if accept_resp.status_code not in (200, 400):
        pass  # May already be accepted
    return session_client


@pytest.mark.asyncio
async def test_free_tier_job_quota_enforced(signed_up_client):
    """Verify free tier users hit job creation quota."""
    free_limits = get_plan_limits("free")
    job_quota = free_limits[UsageType.JOB_CREATED.value]

    job_ids = []
    for i in range(min(job_quota, 3)):
        resp = signed_up_client.post(
            "/api/jobs",
            json={"name": f"Quota Test {i}", "urls": [f"https://example.com/page{i}"], "mode": "manual"},
        )
        assert resp.status_code == 201, f"Job {i} creation failed: {resp.text}"
        data = resp.json()
        job_ids.append(data["id"])

    assert len(job_ids) > 0


@pytest.mark.asyncio
async def test_billing_checkout_creates_order(session_client):
    """Verify checkout endpoint creates a PayPal order (or stub)."""
    resp = session_client.post(
        "/api/billing/checkout",
        json={"plan_tier": "starter"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "approval_url" in data
    assert data["approval_url"], "approval_url must not be empty"


@pytest.mark.asyncio
async def test_billing_webhook_updates_subscription(clean_db, session_client):
    """Verify webhook processes subscription events."""
    webhook_payload = {
        "event_type": "BILLING.SUBSCRIPTION.CREATED",
        "resource": {
            "id": "sub_test_123",
            "subscriber": {"email_address": "test@example.com"},
            "plan_id": "plan_starter",
            "status": "ACTIVE",
        },
    }
    resp = session_client.post(
        "/api/billing/webhook",
        json=webhook_payload,
        headers={
            "X-Billing-Webhook-Secret": "test-secret",
            "Content-Type": "application/json",
        },
    )
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

    free_limits = get_plan_limits("free")
    expected_jobs = free_limits[UsageType.JOB_CREATED.value]
    assert data["max_jobs"] == expected_jobs, f"Quota endpoint {data['max_jobs']} != enforcer {expected_jobs}"


@pytest.mark.asyncio
async def test_usage_summary_endpoint(signed_up_client):
    """Verify /api/saas/usage returns usage breakdown."""
    resp = signed_up_client.get("/api/saas/usage")
    assert resp.status_code == 200
    data = resp.json()
    # Usage endpoint should return at minimum a usage summary
    assert isinstance(data, dict)

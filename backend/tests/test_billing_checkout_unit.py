"""Unit tests for billing checkout module."""

from unittest.mock import patch

import pytest
from app.billing.checkout import CheckoutRequest, CheckoutResponse, create_checkout


def test_checkout_request_validation():
    """Verify checkout request validation."""
    # Valid plan tiers
    for tier in ["starter", "pro", "enterprise"]:
        req = CheckoutRequest(plan_tier=tier)
        assert req.plan_tier == tier

    # Invalid tier should fail
    with pytest.raises((ValueError, AssertionError)):
        CheckoutRequest(plan_tier="invalid")


@pytest.mark.asyncio
async def test_create_checkout_returns_approval_url():
    """Verify checkout creates an approval URL."""
    req = CheckoutRequest(plan_tier="starter")
    resp = await create_checkout(req, _role="admin")

    assert isinstance(resp, CheckoutResponse)
    assert resp.approval_url is not None
    assert len(resp.approval_url) > 0
    # URL should be http(s) or a stub
    assert resp.approval_url.startswith("http://") or resp.approval_url.startswith("https://")


@pytest.mark.asyncio
async def test_checkout_with_unconfigured_paypal():
    """Verify checkout returns stub URL when PayPal not configured."""
    import os

    # Clear PayPal env vars
    with patch.dict(
        os.environ,
        {
            "PAYPAL_CLIENT_ID": "",
            "PAYPAL_CLIENT_SECRET": "",
        },
    ):
        req = CheckoutRequest(plan_tier="pro")
        resp = await create_checkout(req, _role="admin")

        # Should return a deterministic stub URL
        assert resp.approval_url is not None
        assert len(resp.approval_url) > 0


def test_checkout_response_serialization():
    """Verify checkout response can be serialized."""
    resp = CheckoutResponse(
        approval_url="https://example.com/approve",
        token="order_123",
        plan_tier="starter",
    )

    # Should be JSON-serializable
    import json

    json_str = json.dumps(
        {
            "approval_url": resp.approval_url,
            "token": resp.token,
        }
    )
    assert "https://example.com/approve" in json_str

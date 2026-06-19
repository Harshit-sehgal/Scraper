"""Regression tests for billing customer -> plan tier resolution.

PayPal Subscriptions API returns ``plan_id`` (a UUID-style string set in the
PayPal Dashboard) rather than a human plan name. We map that back to the
internal ``PlanTierId`` via ``PAYPAL_PLAN_ID_STARTER`` / ``PAYPAL_PLAN_ID_PRO``
/ ``PAYPAL_PLAN_ID_ENTERPRISE`` env vars in ``PayPalClient``.

These tests mock ``requests.get`` to return a fake PayPal Subscriptions API
response, then assert ``get_customer`` maps it to the correct ``PlanTierId``
(not FREE).
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest
from app.billing.models import PlanTierId, SubscriptionStatus
from app.billing.service import PayPalClient, reset_paypal_client


def _fake_paypal_response(
    plan_id: str,
    sub_status: str = "ACTIVE",
    customer_id: str = "I-TEST",
    email: str = "user@example.com",
) -> MagicMock:
    """Build a fake ``requests.Response`` that looks like PayPal GET
    /v1/billing/subscriptions/{id} response.
    """
    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.raise_for_status = MagicMock()
    fake_resp.json.return_value = {
        "id": customer_id,
        "plan_id": plan_id,
        "status": sub_status,
        "subscriber": {"email_address": email},
    }
    return fake_resp


# Environment variables every test needs so the client initialises.
_BASE_ENV = {
    "PAYPAL_CLIENT_ID": "test-client-id",
    "PAYPAL_CLIENT_SECRET": "test-client-secret",
}


@pytest.fixture(autouse=True)
def _reset_client() -> None:
    """Reset the PayPalClient singleton before every test."""
    reset_paypal_client()


def _configured_client() -> PayPalClient:
    """Create and arm a PayPalClient that appears properly configured.

    We mock ``_ensure_client`` to return a sentinel (bypasses OAuth token
    request) and ``_ensure_token`` to return a fake bearer token.
    """
    client = PayPalClient()
    client._initialized = True
    client._http_client = MagicMock()  # sentinel: not None → is_configured
    client._access_token = "fake-bearer-token"
    client._access_token_expires_at = float("inf")
    return client


@pytest.mark.parametrize(
    ("plan_id_env_value", "expected_tier"),
    [
        ("P-STARTER-TEST123", PlanTierId.STARTER),
        ("P-PRO-TEST123", PlanTierId.PRO),
        ("P-ENTERPRISE-TEST123", PlanTierId.ENTERPRISE),
    ],
)
def test_get_customer_maps_paid_plan_id_to_correct_tier(plan_id_env_value: str, expected_tier: PlanTierId) -> None:
    """A paid plan_id from PayPal MUST resolve to the matching PlanTierId,
    not silently collapse to FREE.

    Each tier's plan_id is sourced from the env var mapped in
    ``_PLAN_ID_ENV_BY_TIER`` (e.g. ``PAYPAL_PLAN_ID_STARTER``).
    """
    env_var_by_tier = {
        PlanTierId.STARTER: "PAYPAL_PLAN_ID_STARTER",
        PlanTierId.PRO: "PAYPAL_PLAN_ID_PRO",
        PlanTierId.ENTERPRISE: "PAYPAL_PLAN_ID_ENTERPRISE",
    }
    target_env = env_var_by_tier[expected_tier]
    fake_resp = _fake_paypal_response(plan_id=plan_id_env_value)

    with patch.dict(
        os.environ,
        {**_BASE_ENV, target_env: plan_id_env_value},
        clear=False,
    ):
        client = _configured_client()
        with patch("app.billing.service.requests.get", return_value=fake_resp):
            info = client.get_customer("I-TEST")

    assert info is not None, "get_customer should return CustomerInfo when the provider returns a customer"
    assert info.plan_tier == expected_tier, (
        f"plan_id={plan_id_env_value!r} should map to {expected_tier!r}, got {info.plan_tier!r} "
        f"(regression: paid tiers silently resolving to FREE)"
    )


def test_get_customer_unknown_plan_id_falls_back_to_free() -> None:
    """An unrecognized plan_id still falls back to FREE (safe default)."""
    fake_resp = _fake_paypal_response(plan_id="P-PLATINUM-MAX-9999")
    with patch.dict(os.environ, _BASE_ENV, clear=False):
        client = _configured_client()
        with patch("app.billing.service.requests.get", return_value=fake_resp):
            info = client.get_customer("I-UNKNOWN")
    assert info is not None
    assert info.plan_tier == PlanTierId.FREE


@pytest.mark.parametrize(
    ("sub_status", "expected_status"),
    [
        ("ACTIVE", SubscriptionStatus.ACTIVE),
        ("SUSPENDED", SubscriptionStatus.PAST_DUE),
        ("CANCELLED", SubscriptionStatus.CANCELED),
        ("APPROVAL_PENDING", SubscriptionStatus.ACTIVE),
    ],
)
def test_get_customer_maps_subscription_status(sub_status: str, expected_status: SubscriptionStatus) -> None:
    """Subscription status resolution must lowercase the PayPal status and
    match against ``SubscriptionStatus`` values — never collapse to a single
    sentinel."""
    fake_resp = _fake_paypal_response(plan_id="P-PRO-TEST123", sub_status=sub_status)
    with patch.dict(
        os.environ,
        {**_BASE_ENV, "PAYPAL_PLAN_ID_PRO": "P-PRO-TEST123"},
        clear=False,
    ):
        client = _configured_client()
        with patch("app.billing.service.requests.get", return_value=fake_resp):
            info = client.get_customer("I-TEST")
    assert info is not None
    assert info.subscription_status == expected_status


def test_get_customer_plan_tier_returns_pro_for_pro_customer() -> None:
    """End-to-end: get_customer_plan_tier must not collapse a pro customer to FREE."""
    fake_resp = _fake_paypal_response(plan_id="P-PRO-TEST123")
    with patch.dict(
        os.environ,
        {**_BASE_ENV, "PAYPAL_PLAN_ID_PRO": "P-PRO-TEST123"},
        clear=False,
    ):
        client = _configured_client()
        with patch("app.billing.service.requests.get", return_value=fake_resp):
            tier = client.get_customer_plan_tier("I-TEST")
    assert tier == PlanTierId.PRO


def test_get_customer_returns_none_on_404() -> None:
    """A 404 from PayPal should return None, not crash."""
    fake_resp = MagicMock()
    fake_resp.status_code = 404
    with patch.dict(os.environ, _BASE_ENV, clear=False):
        client = _configured_client()
        with patch("app.billing.service.requests.get", return_value=fake_resp):
            info = client.get_customer("I-MISSING")
    assert info is None


def test_get_customer_returns_none_when_not_configured() -> None:
    """When no PayPal credentials are set, get_customer returns None safely."""
    reset_paypal_client()
    with patch.dict(os.environ, {}, clear=True):
        client = PayPalClient()
        info = client.get_customer("I-ANYCUSTOMER")
    assert info is None


def test_get_customer_plan_tier_falls_back_to_free_when_not_configured() -> None:
    """When no PayPal credentials are set, get_customer_plan_tier falls back to FREE."""
    reset_paypal_client()
    with patch.dict(os.environ, {}, clear=True):
        client = PayPalClient()
        tier = client.get_customer_plan_tier("I-ANYCUSTOMER")
    assert tier == PlanTierId.FREE

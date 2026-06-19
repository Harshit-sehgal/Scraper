"""Regression tests for billing customer -> plan tier resolution.

PayPal Subscriptions API returns ``plan_id`` (a UUID-style string set in the
PayPal Dashboard) rather than a human plan name. We map that back to the
internal ``PlanTierId`` via ``PAYPAL_PLAN_ID_STARTER`` / ``PAYPAL_PLAN_ID_PRO``
/ ``PAYPAL_PLAN_ID_ENTERPRISE`` env vars in ``PayPalClient``.

These tests construct a fake ``paypalhttp`` SDK whose ``HttpClient.execute``
returns a SimpleNamespace whose ``.result`` is a SimpleNamespace Subscription
with ``plan_id`` and ``status`` attributes, then assert ``get_customer`` maps
it to the correct ``PlanTierId`` (not FREE).
"""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from app.billing.models import PlanTierId, SubscriptionStatus
from app.billing.service import PayPalClient


def _fake_paypal_http(
    plan_id: str,
    sub_status: str = "ACTIVE",
    customer_id: str = "I-TEST",
):
    """Build a fake ``paypalhttp`` SDK matching the SHAPE ``get_customer``
    reads:

    ``client.execute(request)`` → object whose ``.result`` is the subscription
    body (a SimpleNamespace with ``plan_id``, ``status``, and ``subscriber``).
    """
    body = SimpleNamespace(
        id=customer_id,
        plan_id=plan_id,
        status=sub_status,
        subscriber={"email_address": "user@example.com"},
    )
    fake_response = SimpleNamespace(result=body)
    fake_http_client = SimpleNamespace(execute=lambda request: fake_response)
    fake_paypalhttp = SimpleNamespace(
        HttpClient=lambda *a, **kw: fake_http_client,
        subscriptions=SimpleNamespace(SubscriptionsGet=lambda cid: SimpleNamespace()),
    )
    return fake_paypalhttp, fake_http_client


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
    fake_payload, _ = _fake_paypal_http(plan_id=plan_id_env_value)

    # ``patch.dict`` must remain ACTIVE during ``get_customer`` because
    # ``_resolve_tier_from_plan_id`` reads ``os.environ.get(plan_id_env_var)``
    # on every call. Keep both patches inside a single ``with`` block.
    with patch.dict(
        os.environ,
        {target_env: plan_id_env_value, "PAYPAL_CLIENT_ID": "x", "PAYPAL_CLIENT_SECRET": "y"},
        clear=False,
    ):
        client = PayPalClient()
        # Disarm _ensure_client (it would auto-import real paypalhttp)
        # and pin the fake SDK as the lazy-initialized module.
        client._initialized = True
        with (
            patch.object(client, "_paypalhttp", new=fake_payload),
            patch.object(client, "_client", new=fake_payload.HttpClient()),
        ):
            info = client.get_customer("I-TEST")

    assert info is not None, "get_customer should return CustomerInfo when the provider returns a customer"
    assert info.plan_tier == expected_tier, (
        f"plan_id={plan_id_env_value!r} should map to {expected_tier!r}, got {info.plan_tier!r} "
        f"(regression: paid tiers silently resolving to FREE)"
    )


def test_get_customer_unknown_plan_id_falls_back_to_free() -> None:
    """An unrecognized plan_id still falls back to FREE (safe default)."""
    fake_payload, _ = _fake_paypal_http(plan_id="P-PLATINUM-MAX-9999")
    with patch.dict(os.environ, {}, clear=False):
        client = PayPalClient()
        client._initialized = True
        with (
            patch.object(client, "_paypalhttp", new=fake_payload),
            patch.object(client, "_client", new=fake_payload.HttpClient()),
        ):
            info = client.get_customer("I-UNKNOWN")
    assert info is not None
    assert info.plan_tier == PlanTierId.FREE


@pytest.mark.parametrize(
    ("sub_status", "expected_status"),
    [
        ("ACTIVE", SubscriptionStatus.ACTIVE),
        ("SUSPENDED", SubscriptionStatus.PAST_DUE),
        ("CANCELLED", SubscriptionStatus.CANCELED),
        ("APPROVAL_PENDING", SubscriptionStatus.ACTIVE),  # unknown → defaults to ACTIVE
    ],
)
def test_get_customer_maps_subscription_status(sub_status: str, expected_status: SubscriptionStatus) -> None:
    """Subscription status resolution must lowercase the PayPal status and
    match against ``SubscriptionStatus`` values — never collapse to a single
    sentinel."""
    fake_payload, _ = _fake_paypal_http(plan_id="P-PRO-TEST123", sub_status=sub_status)
    with patch.dict(
        os.environ,
        {"PAYPAL_PLAN_ID_PRO": "P-PRO-TEST123", "PAYPAL_CLIENT_ID": "x", "PAYPAL_CLIENT_SECRET": "y"},
        clear=False,
    ):
        client = PayPalClient()
        client._initialized = True
        with (
            patch.object(client, "_paypalhttp", new=fake_payload),
            patch.object(client, "_client", new=fake_payload.HttpClient()),
        ):
            info = client.get_customer("I-TEST")
    assert info is not None
    assert info.subscription_status == expected_status


def test_get_customer_plan_tier_returns_pro_for_pro_customer() -> None:
    """End-to-end: get_customer_plan_tier must not collapse a pro customer to FREE."""
    fake_payload, _ = _fake_paypal_http(plan_id="P-PRO-TEST123")
    with patch.dict(
        os.environ,
        {"PAYPAL_PLAN_ID_PRO": "P-PRO-TEST123", "PAYPAL_CLIENT_ID": "x", "PAYPAL_CLIENT_SECRET": "y"},
        clear=False,
    ):
        client = PayPalClient()
        client._initialized = True
        with (
            patch.object(client, "_paypalhttp", new=fake_payload),
            patch.object(client, "_client", new=fake_payload.HttpClient()),
        ):
            tier = client.get_customer_plan_tier("I-TEST")
    assert tier == PlanTierId.PRO

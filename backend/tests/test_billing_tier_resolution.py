"""Regression tests for billing customer -> plan tier resolution.

Bug S-001: ``AutumnClient.get_customer`` previously tested
``plan_name.lower() in PlanTierId.__members__``. ``__members__`` keys
are the UPPERCASE Python identifiers (``FREE``, ``STARTER``, ...) while
the provider returns the lowercase ``.value`` (``free``, ``starter``),
so the membership test was always ``False`` and every paid customer
silently resolved to ``PlanTierId.FREE`` — making the entire paid-plan
billing tier resolution a no-op.

These tests construct a fake Autumn customer object whose subscription
plan name is a real paid tier and assert ``get_customer`` maps it to
the correct ``PlanTierId`` (not FREE).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from app.billing.models import PlanTierId, SubscriptionStatus
from app.billing.service import AutumnClient


def _fake_customer(plan_name: str, sub_status: str = "active") -> SimpleNamespace:
    """Build a fake Autumn customer object matching the getattr shape
    ``get_customer`` reads (``subscription.plan`` dict, ``subscription.status``)."""
    return SimpleNamespace(
        email="user@example.com",
        name="Test User",
        subscription=SimpleNamespace(
            plan={"name": plan_name},
            status=sub_status,
        ),
    )


@pytest.mark.parametrize(
    ("plan_name", "expected_tier"),
    [
        ("free", PlanTierId.FREE),
        ("starter", PlanTierId.STARTER),
        ("pro", PlanTierId.PRO),
        ("enterprise", PlanTierId.ENTERPRISE),
        ("STARTER", PlanTierId.STARTER),  # case-insensitive
        ("Pro", PlanTierId.PRO),
    ],
)
def test_get_customer_maps_paid_plan_name_to_correct_tier(plan_name: str, expected_tier: PlanTierId) -> None:
    """A paid plan name from the provider MUST resolve to the matching
    PlanTierId, not silently collapse to FREE."""
    client = AutumnClient()
    with patch.object(client, "_ensure_client", return_value=object()), patch("app.billing.service.autumn", create=True):
        # Patch the client.lookup to return our fake customer.
        fake_autumn = SimpleNamespace(
            customers=SimpleNamespace(get=lambda customer_id: _fake_customer(plan_name)),
        )
        with patch.object(client, "_ensure_client", return_value=fake_autumn):
            info = client.get_customer("cust_123")
    assert info is not None, "get_customer should return CustomerInfo when the provider returns a customer"
    assert info.plan_tier == expected_tier, (
        f"plan_name={plan_name!r} should map to {expected_tier!r}, got {info.plan_tier!r} "
        f"(regression: paid tiers silently resolving to FREE)"
    )


def test_get_customer_unknown_plan_name_falls_back_to_free() -> None:
    """An unrecognized plan name still falls back to FREE (safe default)."""
    client = AutumnClient()
    fake_autumn = SimpleNamespace(
        customers=SimpleNamespace(get=lambda customer_id: _fake_customer("platinum_max")),
    )
    with patch.object(client, "_ensure_client", return_value=fake_autumn):
        info = client.get_customer("cust_456")
    assert info is not None
    assert info.plan_tier == PlanTierId.FREE


@pytest.mark.parametrize(
    ("sub_status", "expected_status"),
    [
        ("active", SubscriptionStatus.ACTIVE),
        ("past_due", SubscriptionStatus.PAST_DUE),
        ("canceled", SubscriptionStatus.CANCELED),
        ("trialing", SubscriptionStatus.TRIALING),
    ],
)
def test_get_customer_maps_subscription_status(sub_status: str, expected_status: SubscriptionStatus) -> None:
    """Subscription status resolution must use ``.value`` set, not ``__members__``."""
    client = AutumnClient()
    fake_autumn = SimpleNamespace(
        customers=SimpleNamespace(get=lambda customer_id: _fake_customer("pro", sub_status)),
    )
    with patch.object(client, "_ensure_client", return_value=fake_autumn):
        info = client.get_customer("cust_789")
    assert info is not None
    assert info.subscription_status == expected_status


def test_get_customer_plan_tier_returns_pro_for_pro_customer() -> None:
    """End-to-end: get_customer_plan_tier must not collapse a pro customer to FREE."""
    client = AutumnClient()
    fake_autumn = SimpleNamespace(
        customers=SimpleNamespace(get=lambda customer_id: _fake_customer("pro")),
    )
    with patch.object(client, "_ensure_client", return_value=fake_autumn):
        tier = client.get_customer_plan_tier("cust_pro")
    assert tier == PlanTierId.PRO

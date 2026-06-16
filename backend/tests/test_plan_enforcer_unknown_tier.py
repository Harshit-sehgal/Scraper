"""Regression test for plan_enforcer._user_tier tier normalization.

Bug: ``plan_enforcer._user_tier`` previously returned ``tier.value``
verbatim. ``check_usage_limit`` then ran ``_PLAN_LIMITS.get((tier, X))``
and on a miss returned ``(True, ...)``, treating the request as
unlimited. A corrupted or stale billing record whose ``plan_tier``
field was a non-canonical string (e.g. ``"platinum_max"``, ``"PRO"``
with stray casing, ``""``) could therefore bypass ALL plan limits.

Fix: ``_user_tier`` now normalises the returned value through the
``KNOWN_TIERS = {"free", "starter", "pro", "enterprise"}`` allow-list,
defaulting to ``"free"`` for any value not in that set so the
enforcement layer always sees a tier with a concrete limit.

These tests pin the new behavior by mocking the billing-service
import of ``app.billing.service.get_user_tier_from_billing`` and
asserting the normalised result for several inputs.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from app.billing.models import PlanTierId
from app.plan_enforcer import KNOWN_TIERS, _user_tier, check_usage_limit


def _stub_tier(value: PlanTierId | None):
    """Build a fake billing-service return that yields *value*."""

    def _fake_get_user_tier_from_billing(_user_id: str) -> PlanTierId | None:
        return value

    return _fake_get_user_tier_from_billing


def test_user_tier_returns_canonical_tier() -> None:
    """A canonical PlanTierId value is passed through."""
    with patch(
        "app.billing.service.get_user_tier_from_billing",
        _stub_tier(PlanTierId.PRO),
    ):
        assert _user_tier("user_canonical") == "pro"


@pytest.mark.parametrize(
    "tier_value",
    [
        "free",
        "starter",
        "pro",
        "enterprise",
    ],
)
def test_user_tier_accepts_all_known_tier_strings(tier_value: str) -> None:
    """All four KNOWN_TIERS pass through unchanged."""
    enum_value = PlanTierId(tier_value)
    with patch(
        "app.billing.service.get_user_tier_from_billing",
        _stub_tier(enum_value),
    ):
        assert _user_tier("user_known") == tier_value
    assert tier_value in KNOWN_TIERS


def test_user_tier_falls_back_when_tier_missing() -> None:
    """If the billing service returns None, the user is treated as free."""
    with patch(
        "app.billing.service.get_user_tier_from_billing",
        _stub_tier(None),
    ):
        assert _user_tier("user_unconfigured") == "free"


def test_user_tier_falls_back_on_unknown_tier_string() -> None:
    """An unrecognized PlanTierId value falls back to ``"free"``."""
    # Build a fake billing-service return whose ``.value`` is a string
    # outside the canonical allow-list. We bypass the enum so the test
    # is honest about what happens when billing data contains an
    # arbitrary tier label.
    class _FakeTier:
        value = "platinum_max"

    with patch(
        "app.billing.service.get_user_tier_from_billing",
        _fake_get_user_tier_from_billing := lambda _uid: _FakeTier(),
    ):
        # Plan enforcer must NOT pass "platinum_max" through.
        assert _user_tier("user_unknown_tier") == "free"


def test_user_tier_falls_back_on_uppercase_variant() -> None:
    """Stray casing falls back to ``"free"`` (canonical set is lowercase)."""
    class _FakeTier:
        value = "PRO"  # uppercase vs canonical "pro"

    with patch(
        "app.billing.service.get_user_tier_from_billing",
        lambda _uid: _FakeTier(),
    ):
        assert _user_tier("user_pro_uppercase") == "free"


def test_user_tier_falls_back_on_empty_string() -> None:
    """A billing record with empty plan_tier does not slip through."""
    class _FakeTier:
        value = ""

    with patch(
        "app.billing.service.get_user_tier_from_billing",
        lambda _uid: _FakeTier(),
    ):
        assert _user_tier("user_empty") == "free"


def test_user_tier_falls_back_on_billing_service_error() -> None:
    """An exception from the billing service is caught and falls back to free."""

    def _explode(_uid: str) -> PlanTierId:
        msg = "billing service unreachable"
        raise RuntimeError(msg)

    with patch(
        "app.billing.service.get_user_tier_from_billing",
        _explode,
    ):
        assert _user_tier("user_error") == "free"


def test_user_tier_falls_back_when_billing_returns_plain_string() -> None:
    """A non-PlanTierId billing return does NOT crash ``tier.value``.

    Pins the contract that a billing-layer regression returning a
    plain ``str`` (or any truthy object without a ``.value``
    attribute) is treated as a failed lookup and falls back to
    ``"free"`` — the request must not 500 just because the upstream
    service changed shape.
    """

    def _fake_get_user_tier_from_billing(_uid: str) -> str:
        # Plain ``str`` — has no ``.value`` attribute.
        return "pro"

    with patch(
        "app.billing.service.get_user_tier_from_billing",
        _fake_get_user_tier_from_billing,
    ):
        assert _user_tier("user_string_tier") == "free"


def test_check_usage_limit_enforces_free_quotas_for_unknown_tier() -> None:
    """End-to-end: unknown-tier users are still bounded by free-tier quotas.

    Pins the security goal: an attacker who plants an unknown tier in
    their billing record cannot bypass job_quota enforcement.
    """

    class _FakeTier:
        value = "lol_attacker"

    with patch(
        "app.billing.service.get_user_tier_from_billing",
        lambda _uid: _FakeTier(),
    ):
        from app.utils.usage_ledger import UsageType

        allowed, details = check_usage_limit("user_attacker", UsageType.JOB_CREATED)
        assert details["tier"] == "free"
        # If the bug were present, details["tier"] would be "lol_attacker"
        # and details["limit"] would be -1 (unlimited). Confirm neither.
        assert details["limit"] != -1
        assert details["limit"] == 10  # free tier job quota
        # The user is still allowed at this stage (first call auto-sets
        # the quota and returns ``True``); the safety property is that
        # ``limit`` is concrete and the tier name is canonical.
        assert isinstance(allowed, bool)

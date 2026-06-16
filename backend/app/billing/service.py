"""Autumn billing service — usage-based metering and subscription management.

Provides the BillingService class that wraps the Autumn Python SDK for:
- Tracking metered usage events (API calls, page fetches, jobs, etc.)
- Looking up customer subscription tiers and limits
- Checking if a customer has sufficient balance/credit
- Processing subscription webhooks

Fallback behavior: When Autumn is not configured (no API key in dev/test),
the service returns free-tier defaults so the application works without
a billing provider during development.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from app.billing.models import CustomerInfo, PlanTierId, SubscriptionStatus

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_AUTUMN_API_KEY_ENV = "AUTUMN_API_KEY"
_AUTUMN_API_URL_ENV = "AUTUMN_API_URL"
_DEFAULT_AUTUMN_API_URL = "https://api.useautumn.com"

# ---------------------------------------------------------------------------
# Plan limit definitions (same as plan_enforcer.py, kept in sync)
# ---------------------------------------------------------------------------

PLAN_LIMITS: dict[tuple[PlanTierId, str], int] = {
    (PlanTierId.FREE, "jobs_per_month"): 10,
    (PlanTierId.FREE, "pages_per_month"): 1_000,
    (PlanTierId.FREE, "scheduled_jobs"): 5,
    (PlanTierId.FREE, "api_requests_per_month"): 10_000,
    (PlanTierId.STARTER, "jobs_per_month"): 100,
    (PlanTierId.STARTER, "pages_per_month"): 10_000,
    (PlanTierId.STARTER, "scheduled_jobs"): 50,
    (PlanTierId.STARTER, "api_requests_per_month"): 100_000,
    (PlanTierId.PRO, "jobs_per_month"): 1_000,
    (PlanTierId.PRO, "pages_per_month"): 100_000,
    (PlanTierId.PRO, "scheduled_jobs"): 500,
    (PlanTierId.PRO, "api_requests_per_month"): 1_000_000,
    (PlanTierId.ENTERPRISE, "jobs_per_month"): -1,
    (PlanTierId.ENTERPRISE, "pages_per_month"): -1,
    (PlanTierId.ENTERPRISE, "scheduled_jobs"): -1,
    (PlanTierId.ENTERPRISE, "api_requests_per_month"): -1,
}

# ---------------------------------------------------------------------------
# Autumn client wrapper
# ---------------------------------------------------------------------------


class AutumnClient:
    """Thin wrapper around the Autumn Python SDK.

    Falls back to free-tier defaults when the SDK is not installed
    or the API key is not configured (development mode).
    """

    def __init__(self) -> None:
        self._api_key = os.environ.get(_AUTUMN_API_KEY_ENV, "")
        self._api_url = os.environ.get(_AUTUMN_API_URL_ENV, _DEFAULT_AUTUMN_API_URL)
        self._client: Any = None
        self._initialized = False

    def _ensure_client(self) -> Any:
        """Lazy-initialize the Autumn SDK client."""
        if self._initialized:
            return self._client
        self._initialized = True

        if not self._api_key:
            logger.info("AUTUMN_API_KEY not configured — billing disabled, using free-tier defaults")
            return None

        try:
            # Autumn Python SDK (pip install autumn-sdk)
            import autumn  # type: ignore[import-untyped]

            self._client = autumn.Client(api_key=self._api_key, base_url=self._api_url)
            logger.info("Autumn billing client initialized")
        except ImportError:
            logger.warning("autumn-sdk not installed — billing disabled, using free-tier defaults")
        except (RuntimeError, ValueError, OSError) as e:
            logger.warning("Failed to initialize Autumn client: %s", e)

        return self._client

    @property
    def is_configured(self) -> bool:
        """Whether the Autumn client is properly configured."""
        return self._ensure_client() is not None

    def track_event(self, customer_id: str, event_name: str, value: int = 1, **kwargs: Any) -> bool:
        """Track a metered usage event.

        Args:
            customer_id: The Autumn/Stripe customer ID.
            event_name: The event name defined in your Autumn pricing plan.
            value: The quantity (default 1).
            **kwargs: Additional properties to attach to the event.

        Returns:
            True if the event was tracked successfully, False otherwise.
        """
        client = self._ensure_client()
        if client is None:
            logger.debug("Billing disabled — skipping event tracking for %s", event_name)
            return False
        try:
            client.track(customer_id=customer_id, event_name=event_name, value=value, properties=kwargs)
            logger.debug("Tracked billing event: customer=%s event=%s value=%d", customer_id, event_name, value)
            return True
        except (RuntimeError, ValueError, OSError) as e:
            logger.warning("Failed to track billing event %s for %s: %s", event_name, customer_id, e)
            return False

    def get_customer(self, customer_id: str) -> CustomerInfo | None:
        """Look up a customer's subscription and plan tier.

        Returns CustomerInfo with the current plan tier, or None if
        the customer is not found.
        """
        client = self._ensure_client()
        if client is None:
            return None
        try:
            customer = client.customers.get(customer_id=customer_id)
            if customer is None:
                return None
            plan_name = (
                getattr(customer.subscription, "plan", {}).get("name", "free") if hasattr(customer, "subscription") else "free"
            )
            sub_status = getattr(customer.subscription, "status", "active") if hasattr(customer, "subscription") else "active"
            return CustomerInfo(
                customer_id=customer_id,
                email=getattr(customer, "email", ""),
                name=getattr(customer, "name", ""),
                plan_tier=PlanTierId(plan_name.lower()) if plan_name.lower() in PlanTierId.__members__ else PlanTierId.FREE,
                subscription_status=SubscriptionStatus(sub_status)
                if sub_status in SubscriptionStatus.__members__
                else SubscriptionStatus.ACTIVE,
            )
        except (RuntimeError, ValueError, OSError) as e:
            logger.warning("Failed to lookup customer %s: %s", customer_id, e)
            return None

    def get_customer_plan_tier(self, customer_id: str) -> PlanTierId:
        """Get the plan tier for a customer.

        Falls back to FREE if the customer is not found or billing
        is not configured.
        """
        customer = self.get_customer(customer_id)
        if customer is None:
            return PlanTierId.FREE
        return customer.plan_tier

    def check_balance(self, customer_id: str, amount: int) -> bool:
        """Check if a customer has sufficient credit balance.

        Args:
            customer_id: The Autumn/Stripe customer ID.
            amount: The amount to check (in the billing currency unit).

        Returns:
            True if the customer has sufficient balance, False if
            not or if billing is not configured.
        """
        client = self._ensure_client()
        if client is None:
            logger.debug("Billing disabled — skipping balance check")
            return True
        try:
            result = client.check_balance(customer_id=customer_id, amount=amount)
            return bool(getattr(result, "sufficient", False))
        except (RuntimeError, ValueError, OSError) as e:
            logger.warning("Failed to check balance for %s: %s", customer_id, e)
            return True  # Fail open in dev


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_autumn_client: AutumnClient | None = None


def get_autumn_client() -> AutumnClient:
    """Return the module-level Autumn client singleton."""
    global _autumn_client
    if _autumn_client is None:
        _autumn_client = AutumnClient()
    return _autumn_client


def reset_autumn_client(client: AutumnClient | None = None) -> None:
    """Reset the Autumn client singleton (for tests)."""
    global _autumn_client
    _autumn_client = client


# ---------------------------------------------------------------------------
# High-level helpers
# ---------------------------------------------------------------------------


def get_plan_limit(tier: PlanTierId, metric: str) -> int:
    """Return the plan limit for a given tier and metric.

    Returns -1 for unlimited.
    """
    return PLAN_LIMITS.get((tier, metric), 0)


def get_user_tier_from_billing(user_id: str) -> PlanTierId:
    """Look up a user's plan tier via the billing provider.

    Uses the Autumn customer ID (which may be the same as the user_id
    or mapped via the identity store). Falls back to FREE when billing
    is not configured.
    """
    client = get_autumn_client()
    if not client.is_configured:
        return PlanTierId.FREE
    return client.get_customer_plan_tier(user_id)


# ---------------------------------------------------------------------------
# Re-export for convenience
# ---------------------------------------------------------------------------

__all__ = [
    "PLAN_LIMITS",
    "AutumnClient",
    "get_autumn_client",
    "get_plan_limit",
    "get_user_tier_from_billing",
    "reset_autumn_client",
]

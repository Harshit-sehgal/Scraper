"""PayPal billing service — usage-based metering and subscription management.

Provides the BillingService class that wraps the public PayPal REST API for:
- Looking up customer subscription tiers and limits (GET /v1/billing/subscriptions/{id})
- Tracking metered usage events (logged only — PayPal Billing has no metered events API;
  the quota counts are read from the local subscription store instead)
- Subscription webhook processing (in `webhooks.py`)

Fallback behavior: When PayPal is not configured (no client credentials in dev/test),
the service returns free-tier defaults so the application works without a gateway
during development.

Environment variables:
    PAYPAL_CLIENT_ID       — PayPal REST API client ID (OAuth)
    PAYPAL_CLIENT_SECRET   — PayPal REST API client secret (OAuth)
    PAYPAL_API_URL         — Override the REST API base URL (default: https://api-m.sandbox.paypal.com)
    PAYPAL_ENVIRONMENT     — "live" | "sandbox" (default: "sandbox")
    PAYPAL_WEBHOOK_SECRET  — Optional shared-secret webhook secret (alternative to PayPal cert verify)
    PAYPAL_PLAN_ID_STARTER / PAYPAL_PLAN_ID_PRO / PAYPAL_PLAN_ID_ENTERPRISE
                            — Plan IDs created in the PayPal Dashboard
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import requests  # type: ignore[import-untyped]

from app.billing.models import CustomerInfo, PlanTierId, SubscriptionStatus

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_PAYPAL_CLIENT_ID_ENV = "PAYPAL_CLIENT_ID"
_PAYPAL_CLIENT_SECRET_KEY_ENV = "PAYPAL_CLIENT_SECRET"  # noqa: S105  # nosec B105 — env-var NAME, not a credential
_PAYPAL_API_URL_ENV = "PAYPAL_API_URL"
_PAYPAL_ENVIRONMENT_ENV = "PAYPAL_ENVIRONMENT"
_DEFAULT_PAYPAL_API_URL = "https://api-m.sandbox.paypal.com"

# Map our internal plan tier names → PayPal Plan IDs (set in the PayPal Dashboard).
_PLAN_ID_ENV_BY_TIER: dict[PlanTierId, str] = {
    PlanTierId.STARTER: "PAYPAL_PLAN_ID_STARTER",
    PlanTierId.PRO: "PAYPAL_PLAN_ID_PRO",
    PlanTierId.ENTERPRISE: "PAYPAL_PLAN_ID_ENTERPRISE",
}
_DEFAULT_PLAN_PRICES_USD: dict[PlanTierId, str] = {
    PlanTierId.STARTER: "29.00",
    PlanTierId.PRO: "99.00",
    PlanTierId.ENTERPRISE: "299.00",
}

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

# Map PayPal's subscription status strings to our internal SubscriptionStatus values.
_PAYPAL_STATUS_MAP: dict[str, SubscriptionStatus] = {
    "active": SubscriptionStatus.ACTIVE,
    "approval_pending": SubscriptionStatus.ACTIVE,
    "suspended": SubscriptionStatus.PAST_DUE,
    "past_due": SubscriptionStatus.PAST_DUE,
    "cancelled": SubscriptionStatus.CANCELED,
    "canceled": SubscriptionStatus.CANCELED,
    "expired": SubscriptionStatus.EXPIRED,
    "unpaid": SubscriptionStatus.UNPAID,
    "trialing": SubscriptionStatus.TRIALING,
    "incomplete": SubscriptionStatus.INCOMPLETE,
}

# ---------------------------------------------------------------------------
# PayPal REST API client
# ---------------------------------------------------------------------------


class PayPalClient:
    """Wrapper around the PayPal REST API.

    Uses the paypal-checkout-sdk for Orders API v2 (checkout) and
    direct requests for OAuth + Subscriptions API v1.

    Falls back to free-tier defaults when credentials are not configured.
    """

    def __init__(self) -> None:
        self._client_id = os.environ.get(_PAYPAL_CLIENT_ID_ENV, "")
        self._client_secret = os.environ.get(_PAYPAL_CLIENT_SECRET_KEY_ENV, "")
        self._api_url = os.environ.get(_PAYPAL_API_URL_ENV, _DEFAULT_PAYPAL_API_URL)
        self._environment = os.environ.get(_PAYPAL_ENVIRONMENT_ENV, "sandbox").lower()
        self._initialized = False
        self._http_client: Any = None  # paypalcheckoutsdk.core.PayPalHttpClient
        self._access_token: str = ""
        self._access_token_expires_at: float = 0.0
        # Module-level plan-id → tier cache (immutable after startup).
        self._plan_id_cache: dict[str, PlanTierId] | None = None

    def _ensure_client(self) -> Any:
        """Lazy-initialize the PayPal HTTP client and OAuth token."""
        if self._initialized:
            return self._http_client
        self._initialized = True

        if not self._client_id or not self._client_secret:
            logger.info("PAYPAL_CLIENT_ID/PAYPAL_CLIENT_SECRET not configured — billing disabled, using free-tier defaults")
            return None

        try:
            from paypalcheckoutsdk.core import (  # type: ignore[import-untyped]
                LiveEnvironment,
                PayPalHttpClient,
                SandboxEnvironment,
            )

            env_cls = LiveEnvironment if self._environment == "live" else SandboxEnvironment
            self._http_client = PayPalHttpClient(env_cls(self._client_id, self._client_secret))
            self._refresh_access_token()
            logger.info("PayPal billing client initialized (env=%s)", self._environment)
        except ImportError:
            logger.warning("paypal-checkout-sdk not installed — billing disabled, using free-tier defaults")
        except (RuntimeError, ValueError, OSError) as e:
            logger.warning("Failed to initialize PayPal client: %s", e)

        return self._http_client

    def _refresh_access_token(self) -> None:
        """Fetch a fresh bearer token via PayPal's OAuth2 token endpoint."""
        if not self._client_id or not self._client_secret:
            return
        try:
            resp = requests.post(
                f"{self._api_url}/v1/oauth2/token",
                data={"grant_type": "client_credentials"},
                auth=(self._client_id, self._client_secret),
                headers={"Accept": "application/json"},
                timeout=30,
            )
            resp.raise_for_status()
            body = resp.json()
            self._access_token = body.get("access_token", "")
            expires_in = int(body.get("expires_in", 3600))
            # Refresh 60s early to avoid edge-of-expiry 401s.
            self._access_token_expires_at = time.time() + max(expires_in - 60, 60)
            logger.debug("PayPal access token refreshed (expires_in=%ds)", expires_in)
        except (requests.RequestException, ValueError, KeyError, OSError) as e:
            logger.warning("Failed to refresh PayPal access token: %s", e)

    def _ensure_token(self) -> str:
        """Return a valid access token, refreshing if expired."""
        if not self._access_token or time.time() > self._access_token_expires_at:
            self._refresh_access_token()
        return self._access_token

    @property
    def is_configured(self) -> bool:
        """Whether the PayPal client is properly configured."""
        return self._ensure_client() is not None

    def track_event(self, customer_id: str, event_name: str, value: int = 1, **kwargs: Any) -> bool:
        """Track a metered usage event.

        PayPal's Billing Subscriptions API does not expose a metered-events endpoint.
        Quotas are enforced via the local subscription store; this method exists for
        API parity with the previous Autumn-based interface and only logs the event.
        """
        if not self.is_configured:
            logger.debug("Billing disabled — skipping event tracking for %s", event_name)
            return False
        logger.debug(
            "PayPal billing event (no-op): customer=%s event=%s value=%d extra=%s",
            customer_id,
            event_name,
            value,
            kwargs,
        )
        return True

    def get_customer(self, customer_id: str) -> CustomerInfo | None:
        """Look up a customer's subscription and plan tier via PayPal Subscriptions API v1.

        Calls GET /v1/billing/subscriptions/{id} with a fresh OAuth bearer token.
        Returns CustomerInfo with the current plan tier, or None if not found.
        """
        if not self.is_configured:
            return None

        token = self._ensure_token()
        if not token:
            return None

        try:
            resp = requests.get(
                f"{self._api_url}/v1/billing/subscriptions/{customer_id}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                timeout=30,
            )
            if resp.status_code == 404:
                logger.debug("Subscription %s not found in PayPal", customer_id)
                return None
            resp.raise_for_status()
            body: dict[str, Any] = resp.json()

            plan_id = str(body.get("plan_id", "") or "")
            status_str = str(body.get("status", "ACTIVE")).lower()
            tier = self._resolve_tier_from_plan_id(plan_id)

            subscriber: dict[str, Any] = body.get("subscriber", {}) or {}
            email = str(subscriber.get("email_address", "") or "")

            return CustomerInfo(
                customer_id=customer_id,
                email=email,
                name="",
                plan_tier=tier,
                subscription_status=_PAYPAL_STATUS_MAP.get(status_str, SubscriptionStatus.ACTIVE),
                subscription_id=customer_id,
            )
        except (requests.RequestException, ValueError, KeyError, OSError) as e:
            logger.warning("Failed to lookup subscription %s: %s", customer_id, e)
            return None

    def _resolve_tier_from_plan_id(self, plan_id: str) -> PlanTierId:
        """Map a PayPal plan_id back to an internal PlanTierId via env vars.

        The plan-id → tier mapping is cached after first resolution since
        env vars and plan IDs are immutable for the process lifetime.
        """
        if not plan_id:
            return PlanTierId.FREE

        if self._plan_id_cache is not None:
            return self._plan_id_cache.get(plan_id, PlanTierId.FREE)

        # Build the cache once (module-level data, never changes).
        self._plan_id_cache = {}
        for tier, env_name in _PLAN_ID_ENV_BY_TIER.items():
            expected = os.environ.get(env_name, "").strip()
            if expected:
                self._plan_id_cache[expected] = tier
        return self._plan_id_cache.get(plan_id, PlanTierId.FREE)

    def get_customer_plan_tier(self, customer_id: str) -> PlanTierId:
        """Get the plan tier for a customer. Falls back to FREE if not found."""
        customer = self.get_customer(customer_id)
        if customer is None:
            return PlanTierId.FREE
        return customer.plan_tier

    def check_balance(self, customer_id: str, amount: int) -> bool:  # noqa: ARG002
        """Check whether a customer has remaining quota.

        PayPal Subscriptions don't expose a real-time balance counter via the REST API.
        We rely on the local subscription store + plan_enforcer for actual quota gating.
        This implementation returns True in all cases (fail-open) to preserve
        the prior API shape.
        """
        if not self.is_configured:
            logger.debug("Billing disabled — skipping balance check")
        return True

    def plan_price(self, tier: PlanTierId | str) -> str:
        """Return the dollar price string used in checkout for a tier."""
        if isinstance(tier, str):
            try:
                tier = PlanTierId(tier)
            except ValueError:
                return "0.00"
        return _DEFAULT_PLAN_PRICES_USD.get(tier, "0.00")


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_paypal_client: PayPalClient | None = None


def get_paypal_client() -> PayPalClient:
    """Return the module-level PayPal client singleton."""
    global _paypal_client
    if _paypal_client is None:
        _paypal_client = PayPalClient()
    return _paypal_client


def reset_paypal_client(client: PayPalClient | None = None) -> None:
    """Reset the PayPal client singleton (for tests)."""
    global _paypal_client
    _paypal_client = client


# ---------------------------------------------------------------------------
# High-level helpers
# ---------------------------------------------------------------------------


def get_plan_limit(tier: PlanTierId, metric: str) -> int:
    """Return the plan limit for a given tier and metric.

    Returns -1 for unlimited.
    """
    return PLAN_LIMITS.get((tier, metric), 0)


def get_user_tier_from_billing(user_id: str) -> PlanTierId:
    """Look up a user's plan tier via the PayPal subscription id.

    Falls back to FREE when billing is not configured.
    """
    client = get_paypal_client()
    if not client.is_configured:
        return PlanTierId.FREE
    return client.get_customer_plan_tier(user_id)


# ---------------------------------------------------------------------------
# Re-export for convenience
# ---------------------------------------------------------------------------

__all__ = [
    "PLAN_LIMITS",
    "PayPalClient",
    "get_paypal_client",
    "get_plan_limit",
    "get_user_tier_from_billing",
    "reset_paypal_client",
]

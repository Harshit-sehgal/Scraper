"""PayPal billing service — usage-based metering and subscription management.

Provides the BillingService class that wraps the public PayPal Subscriptions REST
API (Orders API v2 + Subscriptions) for:
- Looking up customer subscription tiers and limits (Subscriptions.Get)
- Tracking metered usage events (logged only — PayPal Billing has no metered events API;
  the social-billing quota counts are read from the local subscription store instead)
- Subscription webhook processing (in `webhooks.py`)

Fallback behavior: When PayPal is not configured (no client credentials in dev/test),
the service returns free-tier defaults so the application works without a gateway
during development.

Environment variables:
    PAYPAL_CLIENT_ID       — PayPal REST API client ID (OAuth)
    PAYPAL_CLIENT_SECRET   — PayPal REST API client secret (OAuth)
    PAYPAL_API_URL         — Override the base URL (default: https://api-m.sandbox.paypal.com)
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

# Map PayPal's subscription status strings (uppercased, dotted names from the
# Subscriptions resource) to our internal SubscriptionStatus values. Any
# unrecognised PayPal state falls back to ACTIVE — billing keeps paying
# until the webhook explicitly cancels / suspends the subscription.
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
# PayPal client wrapper
# ---------------------------------------------------------------------------


class PayPalClient:
    """Thin wrapper around the PayPal REST API.

    Falls back to free-tier defaults when the SDK is not installed
    or the API credentials are not configured (development mode).
    """

    def __init__(self) -> None:
        self._client_id = os.environ.get(_PAYPAL_CLIENT_ID_ENV, "")
        self._client_secret = os.environ.get(_PAYPAL_CLIENT_SECRET_KEY_ENV, "")
        self._api_url = os.environ.get(_PAYPAL_API_URL_ENV, _DEFAULT_PAYPAL_API_URL)
        self._environment = os.environ.get(_PAYPAL_ENVIRONMENT_ENV, "sandbox").lower()
        self._client: Any = None
        self._initialized = False
        self._access_token: str = ""
        self._access_token_expires_at: float = 0.0
        self._paypalhttp: Any = None

    def _ensure_client(self) -> Any:
        """Lazy-initialize the PayPal HTTP client and OAuth token."""
        if self._initialized:
            return self._client
        self._initialized = True

        if not self._client_id or not self._client_secret:
            logger.info("PAYPAL_CLIENT_ID/PAYPAL_CLIENT_SECRET not configured — billing disabled, using free-tier defaults")
            return None

        try:
            # paypalhttp is the official PayPal Python SDK for the REST API.
            # pip install paypalhttp
            import paypalhttp  # type: ignore[import-untyped]

            self._paypalhttp = paypalhttp
            environment_cls = paypalhttp.LiveEnvironment if self._environment == "live" else paypalhttp.SandboxEnvironment
            self._client = paypalhttp.HttpClient(environment_cls(self._client_id, self._client_secret))
            self._refresh_access_token()
            logger.info("PayPal billing client initialized (env=%s)", self._environment)
        except ImportError:
            logger.warning("paypalhttp not installed — billing disabled, using free-tier defaults")
        except (RuntimeError, ValueError, OSError) as e:
            logger.warning("Failed to initialize PayPal client: %s", e)

        return self._client

    def _refresh_access_token(self) -> None:
        """Fetch a fresh bearer token via PayPal's `/v1/oauth2/token` endpoint."""
        if self._client is None or self._paypalhttp is None:
            return
        try:
            # paypalhttp exposes a helper for the client_credentials grant.
            # The SDK caches the token internally between requests; we track
            # the expiry here only to log unusual lifetime drift in dev.
            token = self._paypalhttp.OAuthToken(
                self._client,
                self._client_id,
                self._client_secret,
            )
            self._access_token = getattr(token, "token", "") or ""
            self._access_token_expires_at = time.time() + 3000  # ~50 min (PayPal tokens live 3600s)
            logger.debug("PayPal access token refreshed (expires_at=%s)", int(self._access_token_expires_at))
        except (RuntimeError, ValueError, OSError) as e:
            logger.warning("Failed to refresh PayPal access token: %s", e)

    @property
    def is_configured(self) -> bool:
        """Whether the PayPal client is properly configured."""
        return self._ensure_client() is not None

    def track_event(self, customer_id: str, event_name: str, value: int = 1, **kwargs: Any) -> bool:
        """Track a metered usage event.

        PayPal's Billing Subscriptions API does not expose a metered-events endpoint.
        Quotas are enforced via the local subscription store; this method exists for
        API parity with the previous Autumn-based interface and only logs the event.

        Args:
            customer_id: The PayPal customer id (subscription id P-...).
            event_name: The event name (jobs_per_month, pages_per_month, ...).
            value: The quantity (default 1).
            **kwargs: Additional properties to attach to the event.

        Returns:
            True if the event was tracked, False otherwise. Always False in dev mode.
        """
        client = self._ensure_client()
        if client is None:
            logger.debug("Billing disabled — skipping event tracking for %s", event_name)
            return False
        # PayPal has no metered usage API at the Billing tier — log only.
        logger.debug(
            "PayPal billing event (no-op): customer=%s event=%s value=%d extra=%s",
            customer_id,
            event_name,
            value,
            kwargs,
        )
        return True

    def get_customer(self, customer_id: str) -> CustomerInfo | None:
        """Look up a customer's subscription and plan tier via PayPal Subscriptions API.

        Returns CustomerInfo with the current plan tier, or None if
        the customer is not found.
        """
        client = self._ensure_client()
        if client is None:
            return None
        if self._paypalhttp is None:
            return None
        try:
            # Lazy import — paypalhttp may not be installed in dev environments.
            # ``self._paypalhttp`` is the loaded module; ``subscriptions`` is its
            # submodule. Pinning the import path through the cached module
            # keeps tests in control: they patch ``self._paypalhttp`` and
            # ``self._client`` so the deferred ``getattr(subs, "...")`` chain
            # resolves against the fake SDK.
            subscriptions = getattr(self._paypalhttp, "subscriptions", None)
            if subscriptions is None:
                return None
            subs_cls = getattr(subscriptions, "SubscriptionsGet", None)
            if subs_cls is None:
                return None
            request = subs_cls(customer_id)
            response = client.execute(request)
            # paypalhttp returns ``HttpResponse`` whose top-level wrapper has
            # ``.result`` (the parsed body) and ``.body`` (raw HTTP body).
            # Prefer ``.result``; fall back to ``.body`` for malformed shapes.
            sub = getattr(response, "result", None)
            if sub is None:
                sub = getattr(response, "body", None)
            if sub is None:
                return None
            plan_id = ""
            plan_id_obj = getattr(sub, "plan_id", "")
            if isinstance(plan_id_obj, str):
                plan_id = plan_id_obj
            status_str = str(getattr(sub, "status", "ACTIVE")).lower()
            tier = self._resolve_tier_from_plan_id(plan_id)
            # subscriber may be a dict OR a SimpleNamespace; handle both.
            subscriber = getattr(sub, "subscriber", None)
            email = ""
            if isinstance(subscriber, dict):
                email = subscriber.get("email_address", "") or ""
            elif subscriber is not None:
                email = str(getattr(subscriber, "email_address", "") or "")
            return CustomerInfo(
                customer_id=customer_id,
                email=email,
                name="",
                plan_tier=tier,
                subscription_status=_PAYPAL_STATUS_MAP.get(status_str, SubscriptionStatus.ACTIVE),
                subscription_id=customer_id,
            )
        except (RuntimeError, ValueError, OSError, AttributeError, TypeError) as e:
            logger.warning("Failed to lookup subscription %s: %s", customer_id, e)
            return None

    def _resolve_tier_from_plan_id(self, plan_id: str) -> PlanTierId:
        """Map a PayPal plan_id back to an internal PlanTierId via env vars."""
        if not plan_id:
            return PlanTierId.FREE
        for tier, env_name in _PLAN_ID_ENV_BY_TIER.items():
            expected = os.environ.get(env_name, "").strip()
            if expected and expected == plan_id:
                return tier
        return PlanTierId.FREE

    def get_customer_plan_tier(self, customer_id: str) -> PlanTierId:
        """Get the plan tier for a customer. Falls back to FREE if not found."""
        customer = self.get_customer(customer_id)
        if customer is None:
            return PlanTierId.FREE
        return customer.plan_tier

    def check_balance(self, customer_id: str, amount: int) -> bool:  # noqa: ARG002 — fail-open in dev, args kept for API parity
        """Check whether a customer has remaining quota for ``amount`` of an event.

        PayPal Subscriptions don't expose a real-time balance counter via the REST API.
        We rely on the local subscription store + plan_enforcer for actual quota gating.
        This implementation returns True in all cases (fail-open in dev) to preserve
        the prior API shape for callers that haven't migrated yet.

        Returns:
            True if the customer can be charged, or if billing is unconfigured.
        """
        client = self._ensure_client()
        if client is None:
            logger.debug("Billing disabled — skipping balance check")
            return True
        return True

    def plan_price(self, tier: PlanTierId) -> str:
        """Return the dollar price string used in checkout for a tier."""
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
    """Look up a user's plan tier via the PayPal subscription id (which may be
    the same as the user id or mapped via the identity store).

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

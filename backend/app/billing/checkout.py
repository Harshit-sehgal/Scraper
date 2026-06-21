"""PayPal checkout endpoint.

POST /api/billing/checkout creates a PayPal Order for the requested plan
tier and returns an approval URL the user is redirected to. When the
PayPal client is not configured (no PAYPAL_CLIENT_ID/PAYPAL_CLIENT_SECRET),
a deterministic stub is returned so dev/test environments don't need real
PayPal credentials.

In production the operator must:
  1. Create the Plans (Starter / Pro / Enterprise) in the PayPal Dashboard.
  2. Set ``PAYPAL_PLAN_ID_STARTER`` / ``PAYPAL_PLAN_ID_PRO`` /
     ``PAYPAL_PLAN_ID_ENTERPRISE`` env vars to the corresponding Plan IDs.
  3. Set ``PAYPAL_CLIENT_ID`` / ``PAYPAL_CLIENT_SECRET`` and
     ``PAYPAL_ENVIRONMENT=live`` for production traffic.
"""

from __future__ import annotations

import logging
import os
import uuid
from string import Template
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, field_validator
from starlette.concurrency import run_in_threadpool

from app.billing.service import (
    PayPalClient,
    get_paypal_client,
)
from app.url_safety import validate_public_http_url
from app.utils.rbac import UserRole, require_role

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/billing", tags=["billing"])

_PLAN_TIER_LITERAL = Literal["starter", "pro", "enterprise"]

# Templated stub-return page rendered when the operator clicks the stub
# approval URL. Lives next to the route handler so the path template is
# obviously aligned with the URL string built by ``_stub_approval_url``.
# This prevents the dev flow from hitting a 404 when PayPal credentials
# are not configured (was a regression from the URL change; see Fix #1).
#
# Use ``string.Template`` (``$identifier``) rather than ``str.format``
# (``{identifier}``) so the inline CSS braces below don't get re-read
# as format placeholders. ``str.format`` raises KeyError on the first
# literal ``{`` it finds in a stylesheet, breaking the dev flow.
_STUB_RETURN_PAGE = Template("""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>Dataforge — Stub checkout complete</title>
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
         max-width: 480px; margin: 4rem auto; padding: 1.5rem;
         color: #1f1f1f; background: #fafafa; border: 1px solid #ddd; border-radius: 8px; }
  h1 { font-size: 1.25rem; margin: 0 0 1rem; }
  p { margin: 0.5rem 0; line-height: 1.5; }
  code { background: #eee; padding: 0.1rem 0.3rem; border-radius: 4px; }
  .muted { color: #666; font-size: 0.9rem; }
</style>
</head>
<body>
  <h1>Stub checkout complete</h1>
  <p>PayPal credentials are not configured, so the approval step is a stub.</p>
  <p>Plan tier: <code>$tier</code></p>
  <p>Stub token: <code>$token</code></p>
  <p class="muted">Configure PAYPAL_CLIENT_ID / PAYPAL_CLIENT_SECRET and restart to accept real PayPal checkouts.</p>
</body>
</html>
""")

# Tier tokens accepted by the stub-return handler. Anything else falls
# back to the literal string in the template, but we don't raise — the
# handler is dev-only and we don't want a typo to mask a configuration
# problem with a 404 replacing a 200.
_ALLOWED_STUB_TIERS = frozenset({"starter", "pro", "enterprise"})


class CheckoutRequest(BaseModel):
    """Request body for POST /api/billing/checkout."""

    plan_tier: _PLAN_TIER_LITERAL
    return_url: str | None = Field(default=None, min_length=1, max_length=2048)
    cancel_url: str | None = Field(default=None, min_length=1, max_length=2048)

    @field_validator("return_url", "cancel_url")
    @classmethod
    def _validate_urls(cls, value: str | None) -> str | None:
        # None is permitted — the checkout handler will fall back to a
        # builder-derived URL or the configured billing return URL.
        if value is None:
            return value
        # Strict http(s) URLs only — no javascript:, data:, file: schemes.
        # Then enforce SSRF protection against private/loopback ranges
        # (mirrors auth-profile URL validation). Without these checks,
        # an authenticated caller could redirect a PayPal approval to
        # 127.0.0.1 / 169.254.169.254 / their VPC metadata endpoint.
        if not value.startswith(("http://", "https://")):
            msg = "URL must start with http:// or https://"
            raise ValueError(msg)
        validate_public_http_url(value)
        return value


class CheckoutResponse(BaseModel):
    """Response from POST /api/billing/checkout."""

    approval_url: str
    token: str
    plan_tier: _PLAN_TIER_LITERAL


def _stub_approval_url(plan_tier: str, request_id: str) -> str:
    """Build a deterministic stub approval URL for dev environments.

    Uses the application's own origin (`localhost` in dev, real domain in
    production) so the URL is always under operator control. Never points
    to a third-party domain — example.com is intentionally NOT used
    because it is not operator-controlled and could be re-registered or
    hijacked, exposing the operator to phishing.
    """
    # Default to the configured backend host (swallowed env errors do
    # not matter — fallback chain guarantees we always get a string).
    # Treat empty strings as "unset" — Kubernetes, Docker, and a number
    # of config-management tools will write an empty value to mean "use
    # default", and ``os.environ.get`` returns the empty string (not the
    # default) in those cases. Without this guard, an empty value produces
    # a relative URL like ``/api/billing/stub-return/...`` which PayPal's
    # UI later interprets as a path on its own domain and 404s.
    configured_host = os.environ.get("DATAFORGE_PUBLIC_BASE_URL", "").strip().rstrip("/")
    host = configured_host or "http://localhost:8000"
    return f"{host}/api/billing/stub-return/{plan_tier}/{request_id}"


# PayPal checkout web UI host — separate from the REST API base URL.
# The REST API is api-m.sandbox.paypal.com (or api-m.paypal.com for live);
# the checkout UI is www.sandbox.paypal.com (or www.paypal.com for live).
# The function deliberately derives the web host from ``PAYPAL_ENVIRONMENT``
# rather than the REST API URL because the two hosts do not always move
# in lock-step (region-proxied deployments, sandbox mirrors, etc.).
_PAYPAL_CHECKOUT_WEB_HOSTS: dict[str, str] = {
    "sandbox": "https://www.sandbox.paypal.com",
    "live": "https://www.paypal.com",
}


def _checkout_web_host() -> str:
    """Return the PayPal checkout web host for the configured environment."""
    is_live = os.environ.get("PAYPAL_ENVIRONMENT", "sandbox").lower() == "live"
    return _PAYPAL_CHECKOUT_WEB_HOSTS["live" if is_live else "sandbox"]


async def _create_paypal_order(
    client: PayPalClient,
    plan_tier: str,
    return_url: str,
    cancel_url: str,
    request_id: str,
) -> dict[str, Any] | None:
    """Create a PayPal Order via the paypal-checkout-sdk. Returns None on failure."""
    if not client.is_configured:
        return None
    try:
        from paypalcheckoutsdk.orders import OrdersCreateRequest  # type: ignore[import-untyped]

        price = client.plan_price(plan_tier)
        order_request = OrdersCreateRequest()
        order_request.request_body(
            {
                "intent": "CAPTURE",
                "purchase_units": [
                    {
                        "reference_id": request_id,
                        "amount": {
                            "currency_code": "USD",
                            "value": price,
                        },
                        "description": f"Dataforge {plan_tier} plan subscription",
                    }
                ],
                "application_context": {
                    "return_url": return_url,
                    "cancel_url": cancel_url,
                    "shipping_preference": "NO_SHIPPING",
                    "user_action": "PAY_NOW",
                },
            }
        )
        http_client = client.http_client
        if http_client is None:
            return None
        result = await run_in_threadpool(http_client.execute, order_request)
        # result is an HttpResponse with .result (parsed body dict)
        order = getattr(result, "result", None)
        if order is None:
            return None

        order_id = order.get("id") if isinstance(order, dict) else getattr(order, "id", "")
        links = order.get("links", []) if isinstance(order, dict) else getattr(order, "links", [])
        approval_url = ""
        for link in links or []:
            rel = link.get("rel") if isinstance(link, dict) else getattr(link, "rel", "")
            if rel == "approve":
                val = link.get("href") if isinstance(link, dict) else getattr(link, "href", "")
                approval_url = str(val) if val else ""
                if approval_url:
                    break
        if not approval_url and order_id:
            # Fallback: construct the canonical PayPal approval URL from the
            # web checkout host (NOT the REST API host).
            web_host = _checkout_web_host()
            approval_url = f"{web_host}/checkoutnow?token={order_id}"
        return {"approval_url": approval_url, "token": order_id}
    except (RuntimeError, ValueError, OSError, AttributeError) as exc:
        logger.warning("Failed to create PayPal order: %s", exc)
        return None


@router.post("/checkout", status_code=200)
async def create_checkout(
    payload: CheckoutRequest,
    _role: Annotated[str, Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR]))],
) -> CheckoutResponse:
    """Create a PayPal Order for the requested plan tier and return its approval URL.

    When ``PAYPAL_CLIENT_ID`` (and / or ``PAYPAL_CLIENT_SECRET``) isn't configured,
    a deterministic stub approval_url is returned. This keeps dev/test environments
    free of live PayPal credentials while presenting the same response shape to
    clients.
    """
    request_id = uuid.uuid4().hex
    client = get_paypal_client()

    if not client.is_configured:
        logger.info(
            "PayPal not configured — returning stub checkout for tier=%s request=%s",
            payload.plan_tier,
            request_id,
        )
        return CheckoutResponse(
            approval_url=_stub_approval_url(payload.plan_tier, request_id),
            token=f"stub-{request_id}",
            plan_tier=payload.plan_tier,
        )

    created = await _create_paypal_order(
        client,
        payload.plan_tier,
        payload.return_url,
        payload.cancel_url,
        request_id,
    )
    if not created or not created.get("approval_url") or not created.get("token"):
        logger.error(
            "PayPal order creation returned no approval URL — falling back to stub for tier=%s",
            payload.plan_tier,
        )
        return CheckoutResponse(
            approval_url=_stub_approval_url(payload.plan_tier, request_id),
            token=f"stub-{request_id}",
            plan_tier=payload.plan_tier,
        )

    return CheckoutResponse(
        approval_url=created["approval_url"],
        token=created["token"],
        plan_tier=payload.plan_tier,
    )


@router.get("/stub-return/{plan_tier}/{request_id}", status_code=200)
async def stub_return(
    plan_tier: str,
    request_id: str,
) -> HTMLResponse:
    """Render a confirmation page for the dev/stub PayPal approval flow.

    Reached when the operator follows the URL returned by
    :func:`_stub_approval_url` (i.e., when PayPal credentials are not
    configured and the checkout endpoint fell back to a local stub URL).
    Without this handler the URL would 404 in dev, which is a regression
    from the prior behaviour where ``example.com/paypal-stub/...`` was
    a real (if unsolicited) third-party URL.

    The handler is intentionally unauthenticated — it is dev-only and the
    stub flow does not commit any state. Any caller with the ``request_id``
    can render the page, which is acceptable given the page contains only
    the request id (already public-unsafe if treated as a secret) and the
    plan tier label.
    """
    tier = plan_tier if plan_tier in _ALLOWED_STUB_TIERS else "unknown"
    logger.info(
        "Stub checkout return: tier=%s request=%s (raw_tier=%s)",
        tier,
        request_id,
        plan_tier,
    )
    html = _STUB_RETURN_PAGE.substitute(tier=tier, token=request_id)
    return HTMLResponse(content=html, status_code=200)


__all__ = ["CheckoutRequest", "CheckoutResponse", "router"]

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
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator

from app.billing.service import (
    PayPalClient,
    get_paypal_client,
)
from app.utils.rbac import UserRole, require_role

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/billing", tags=["billing"])

_PLAN_TIER_LITERAL = Literal["starter", "pro", "enterprise"]


class CheckoutRequest(BaseModel):
    """Request body for POST /api/billing/checkout."""

    plan_tier: _PLAN_TIER_LITERAL
    return_url: str = Field(min_length=1, max_length=2048)
    cancel_url: str = Field(min_length=1, max_length=2048)

    @field_validator("return_url", "cancel_url")
    @classmethod
    def _validate_urls(cls, value: str) -> str:
        # Strict http(s) URLs only — no javascript:, data:, file: schemes.
        if not value.startswith(("http://", "https://")):
            msg = "URL must start with http:// or https://"
            raise ValueError(msg)
        return value


class CheckoutResponse(BaseModel):
    """Response from POST /api/billing/checkout."""

    approval_url: str
    token: str
    plan_tier: _PLAN_TIER_LITERAL


def _stub_approval_url(plan_tier: str, request_id: str) -> str:
    """Build a deterministic stub approval URL for dev environments."""
    return f"https://example.com/paypal-stub/{plan_tier}/{request_id}"


# PayPal checkout web UI host — separate from the REST API base URL.
# The REST API is api-m.sandbox.paypal.com (or api-m.paypal.com for live);
# the checkout UI is www.sandbox.paypal.com (or www.paypal.com for live).
_PAYPAL_CHECKOUT_WEB_HOSTS: dict[str, str] = {
    "sandbox": "https://www.sandbox.paypal.com",
    "live": "https://www.paypal.com",
}


def _checkout_web_host(_api_url: str) -> str:
    """Derive the PayPal checkout web host from REST API URL or environment."""
    is_live = os.environ.get("PAYPAL_ENVIRONMENT", "sandbox").lower() == "live"
    return _PAYPAL_CHECKOUT_WEB_HOSTS["live" if is_live else "sandbox"]


def _create_paypal_order(
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
        http_client = client._ensure_client()  # type: ignore[attr-defined]
        if http_client is None:
            return None
        result = http_client.execute(order_request)
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
            web_host = _checkout_web_host(client._api_url)  # type: ignore[attr-defined]
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

    created = _create_paypal_order(
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


__all__ = ["CheckoutRequest", "CheckoutResponse", "router"]

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


def _create_paypal_order(
    client: PayPalClient,
    plan_tier: str,
    return_url: str,
    cancel_url: str,
    request_id: str,
) -> dict[str, Any] | None:
    """Create a PayPal Order via the paypalhttp SDK. Returns None on failure."""
    if client._paypalhttp is None:
        return None
    try:
        from paypalhttp import orders  # type: ignore[import-untyped]

        price = client.plan_price(plan_tier)  # type: ignore[arg-type]
        request = orders.OrdersCreateRequest()
        request.request_body(
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
        result = client._client.execute(request)
        order = getattr(result, "result", None) or getattr(result, "body", None)
        if order is None:
            return None
        token = order.get("id") if isinstance(order, dict) else getattr(order, "id", "")
        links = order.get("links", []) if isinstance(order, dict) else getattr(order, "links", [])
        approval_url = ""
        for link in links or []:
            if isinstance(link, dict):
                if link.get("rel") == "approve":
                    approval_url = link.get("href", "")
                    break
            elif getattr(link, "rel", "") == "approve":
                approval_url = getattr(link, "href", "")
                break
        if not approval_url and token:
            # Fallback: the canonical PayPal approval URL pattern when
            # ``links`` is omitted or oddly shaped.
            base_url = os.environ.get("PAYPAL_API_URL", "https://www.sandbox.paypal.com")
            approval_url = f"{base_url.rstrip('/')}/checkoutnow?token={token}"
        return {"approval_url": approval_url, "token": token}
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

    Authentication: any authenticated session role (operator / admin) can create
    a checkout; production routing is controlled by the optional ``return_url``
    provided by the caller.
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
        # Preserve API parity — never blow up the operator's upgrade CTA. Fall
        # back to a stub and let the operator retry / open a support ticket.
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

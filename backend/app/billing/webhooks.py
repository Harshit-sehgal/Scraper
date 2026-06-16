"""Webhook handler for billing events from Autumn/Stripe.

Processes subscription lifecycle events:
- subscription.created / subscription.updated — update user plan tiers
- subscription.canceled / subscription.expired — downgrade to free
- invoice.payment_failed — flag account as past_due
- customer.subscription.deleted — clean up

The webhook endpoint is mounted at POST /api/billing/webhook.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request

from app.billing.models import PlanTierId, SubscriptionStatus
from app.config import settings
from app.utils.rbac import UserRole, require_role

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/billing", tags=["billing"])
_SIGNATURE_HEADERS = (
    "X-DataForge-Webhook-Signature",
    "X-Autumn-Signature",
    "X-Webhook-Signature",
)
_SECRET_HEADERS = (
    "X-DataForge-Webhook-Secret",
    "X-Autumn-Webhook-Secret",
    "X-Webhook-Secret",
)


# In-memory subscription state (replace with DB in production)
# Maps customer_id -> {tier, status, subscription_id}
_customer_subscriptions: dict[str, dict[str, Any]] = {}


def get_customer_subscription(customer_id: str) -> dict[str, Any] | None:
    """Get the stored subscription for a customer."""
    return _customer_subscriptions.get(customer_id)


def set_customer_subscription(customer_id: str, tier: str, status: str, subscription_id: str = "") -> None:
    """Store or update a customer's subscription."""
    _customer_subscriptions[customer_id] = {
        "customer_id": customer_id,
        "plan_tier": tier,
        "status": status,
        "subscription_id": subscription_id,
    }


def delete_customer_subscription(customer_id: str) -> None:
    """Remove a customer's subscription record."""
    _customer_subscriptions.pop(customer_id, None)


def _configured_webhook_secret() -> str:
    """Return the configured billing webhook verification secret, if any."""
    configured = str(getattr(settings, "BILLING_WEBHOOK_SECRET", "") or "").strip()
    if configured:
        return configured
    for env_var in ("AUTUMN_WEBHOOK_SECRET", "STRIPE_WEBHOOK_SECRET"):
        value = os.environ.get(env_var, "").strip()
        if value:
            return value
    return ""


def _signature_candidates(header_value: str) -> list[str]:
    """Extract digest candidates from common signature header formats."""
    candidates: list[str] = []
    for part in header_value.split(","):
        item = part.strip()
        if not item:
            continue
        if "=" not in item:
            candidates.append(item)
            continue
        key, _, value = item.partition("=")
        if key.strip().lower() in {"sha256", "v1"} and value.strip():
            candidates.append(value.strip())
    return candidates


def _verify_billing_webhook(request: Request, raw_body: bytes) -> None:
    """Verify webhook authenticity when a billing webhook secret is configured."""
    secret = _configured_webhook_secret()
    if not secret:
        if settings.ENV.lower() == "production":
            raise HTTPException(status_code=503, detail="Billing webhook secret is not configured.")
        return

    for header in _SECRET_HEADERS:
        provided = request.headers.get(header, "").strip()
        if provided and hmac.compare_digest(provided, secret):
            return

    signature_header = ""
    for header in _SIGNATURE_HEADERS:
        signature_header = request.headers.get(header, "").strip()
        if signature_header:
            break
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    for candidate in _signature_candidates(signature_header):
        if hmac.compare_digest(candidate, expected):
            return
    raise HTTPException(status_code=401, detail="Invalid billing webhook signature.")


# ---------------------------------------------------------------------------
# Webhook endpoint
# ---------------------------------------------------------------------------


@router.post("/webhook", status_code=200)
async def billing_webhook(request: Request) -> dict[str, str]:
    """Receive billing webhook events from Autumn/Stripe.

    This endpoint is called by Autumn/Stripe when subscription events
    occur. It processes the event and updates the local subscription
    state accordingly.

    Authentication: This endpoint uses the Autumn webhook secret for
    verification (in production), or the admin API key for testing.
    The body is parsed as JSON.
    """
    raw_body = await request.body()
    _verify_billing_webhook(request, raw_body)
    try:
        loaded = json.loads(raw_body.decode("utf-8"))
        if not isinstance(loaded, dict):
            msg = "Webhook payload must be a JSON object"
            raise TypeError(msg)
        body: dict[str, Any] = loaded
    except Exception as exc:
        logger.debug("Invalid billing webhook JSON body: %s", exc)
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    event_type: str = str(body.get("event_type", body.get("type", "")) or "")
    data: dict[str, Any] = body.get("data", {}) if isinstance(body, dict) else {}
    customer_id: str = str(data.get("customer_id", data.get("customer", data.get("id", ""))) or "")

    logger.info("Billing webhook received: event=%s customer=%s", event_type, customer_id)

    if not event_type:
        return {"status": "skipped", "reason": "No event_type provided"}

    _process_webhook_event(event_type, data)

    return {"status": "ok", "event": event_type}


def _process_webhook_event(event_type: str, data: dict[str, Any]) -> None:
    """Internal processor for webhook events.

    Separated from the route handler for testability.
    """
    customer_id: str = ""
    if isinstance(data, dict):
        customer_id = str(data.get("customer_id", data.get("customer", data.get("id", ""))) or "")

    if not customer_id:
        logger.warning("Webhook event %s has no customer_id", event_type)
        return

    if event_type in ("subscription.created", "subscription.updated", "customer.subscription.updated"):
        plan_name: str = "free"
        status: str = "active"
        sub_id: str = ""
        if isinstance(data, dict):
            for plan_key in ("plan", "plan_tier", "plan_name"):
                v = data.get(plan_key)
                if isinstance(v, str):
                    plan_name = v
                    break
            v = data.get("status")
            if isinstance(v, str):
                status = v
            for sub_key in ("subscription_id", "id"):
                v = data.get(sub_key)
                if isinstance(v, str):
                    sub_id = v
                    break

        # Normalize plan name (compare against PlanTierId values, which are lowercase)
        normalized_plan = plan_name.lower() if plan_name else "free"
        valid_tiers = {t.value for t in PlanTierId}
        if normalized_plan not in valid_tiers:
            normalized_plan = "free"

        set_customer_subscription(
            customer_id=customer_id,
            tier=normalized_plan,
            status=status,
            subscription_id=sub_id,
        )
        logger.info("Subscription %s: customer=%s tier=%s status=%s", event_type, customer_id, normalized_plan, status)

    elif event_type in ("subscription.canceled", "customer.subscription.deleted", "subscription.expired"):
        set_customer_subscription(
            customer_id=customer_id,
            tier=PlanTierId.FREE.value,
            status="canceled",
        )
        logger.info("Subscription %s: customer=%s downgraded to free", event_type, customer_id)

    elif event_type == "invoice.payment_failed":
        existing = get_customer_subscription(customer_id)
        if existing:
            existing["status"] = SubscriptionStatus.PAST_DUE.value
        logger.warning("Payment failed for customer=%s", customer_id)

    elif event_type == "customer.created":
        logger.info("Customer created: %s", customer_id)

    else:
        logger.debug("Unhandled webhook event type: %s", event_type)


# ---------------------------------------------------------------------------
# Management endpoints
# ---------------------------------------------------------------------------


@router.get("/subscriptions", status_code=200)
async def list_subscriptions(
    _role: Annotated[str, Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR]))],
) -> dict[str, Any]:
    """List all tracked subscriptions (admin/operator only)."""
    return {
        "total": len(_customer_subscriptions),
        "subscriptions": list(_customer_subscriptions.values()),
    }


@router.get("/subscriptions/{customer_id}", status_code=200)
async def get_subscription(
    customer_id: str,
    _role: Annotated[str, Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR]))],
) -> dict[str, Any]:
    """Get subscription details for a customer (admin/operator only)."""
    sub = get_customer_subscription(customer_id)
    if sub is None:
        return {"customer_id": customer_id, "plan_tier": "free", "status": "unknown"}
    return sub

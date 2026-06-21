"""Pydantic models for the billing system.

Defines plan tiers, subscription statuses, and billing event payloads
used by the PayPal Subscriptions API integration and plan enforcement layer.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class PlanTierId(StrEnum):
    """Available subscription plan tiers."""

    FREE = "free"
    STARTER = "starter"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class SubscriptionStatus(StrEnum):
    """Status of a customer subscription."""

    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELED = "canceled"
    UNPAID = "unpaid"
    TRIALING = "trialing"
    INCOMPLETE = "incomplete"
    EXPIRED = "expired"


class PayPalEventType(StrEnum):
    """Canonical PayPal Billing Subscriptions webhook event types mapped onto
    our SubscriptionStatus / PlanTierId state machine."""

    SUBSCRIPTION_CREATED = "BILLING.SUBSCRIPTION.CREATED"
    SUBSCRIPTION_UPDATED = "BILLING.SUBSCRIPTION.UPDATED"
    SUBSCRIPTION_CANCELLED = "BILLING.SUBSCRIPTION.CANCELLED"
    SUBSCRIPTION_SUSPENDED = "BILLING.SUBSCRIPTION.SUSPENDED"
    SUBSCRIPTION_PAYMENT_FAILED = "BILLING.SUBSCRIPTION.PAYMENT.FAILED"
    PAYMENT_SALE_COMPLETED = "PAYMENT.SALE.COMPLETED"
    PAYMENT_SALE_FAILED = "PAYMENT.SALE.FAILED"
    CUSTOMER_CREATED = "CUSTOMER.CREATED"


class CustomerInfo(BaseModel):
    """Customer information returned by the billing provider."""

    customer_id: str
    email: str
    name: str = ""
    plan_tier: PlanTierId = PlanTierId.FREE
    subscription_status: SubscriptionStatus = SubscriptionStatus.ACTIVE
    subscription_id: str = ""
    is_trialing: bool = False
    trial_end: str | None = None


class MeteredEvent(BaseModel):
    """An event to track for usage-based billing."""

    event_name: str
    customer_id: str
    value: int = 1
    metadata: dict | None = None


class BillingWebhookPayload(BaseModel):
    """Generic billing webhook payload.

    Supports PayPal's nested format (``event_type`` + ``resource``),
    Stripe-style top-level ``type`` events, and the legacy ``Autumn`` flat
    ``event_type`` form. The webhook handler normalizes across all three.
    """

    event_type: str
    data: dict = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())

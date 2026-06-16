"""Pydantic models for the billing system.

Defines plan tiers, subscription statuses, and billing event payloads
used by the Autumn integration and plan enforcement layer.
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
    """Generic webhook payload from Autumn/Stripe."""

    event_type: str
    data: dict = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())

"""Pydantic models for the billing system.

Defines plan tiers, subscription statuses, and billing event payloads
used by the PayPal Subscriptions API integration and plan enforcement layer.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel


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


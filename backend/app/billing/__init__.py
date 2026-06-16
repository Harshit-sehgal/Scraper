"""Billing — usage-based metering and subscription management.

Integrates with Autumn (useautumn.com) for usage-based billing built
on Stripe. Handles metered event tracking, subscription tier lookups,
webhook processing, and plan enforcement.

Environment variables:
    AUTUMN_API_KEY — Autumn secret API key (required for production)
    AUTUMN_API_URL  — Autumn API base URL (optional, default: https://api.useautumn.com)
"""

from __future__ import annotations

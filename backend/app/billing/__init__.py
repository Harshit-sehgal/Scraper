"""Billing — subscription management.

Integrates with PayPal Subscriptions (api-m.paypal.com / api-m.sandbox.paypal.com).
Handles subscription lifecycle lookups, webhook processing, and plan enforcement.

Environment variables:
    PAYPAL_CLIENT_ID           — PayPal REST API client ID (required for production)
    PAYPAL_CLIENT_SECRET       — PayPal REST API client secret (required for production)
    PAYPAL_API_URL             — Override the base URL (default: https://api-m.sandbox.paypal.com)
    PAYPAL_WEBHOOK_SECRET      — Optional shared-secret webhook secret (alternative to PayPal cert verify)
    PAYPAL_PLAN_ID_STARTER     — PayPal plan ID for the Starter tier
    PAYPAL_PLAN_ID_PRO         — PayPal plan ID for the Pro tier
    PAYPAL_PLAN_ID_ENTERPRISE  — PayPal plan ID for the Enterprise tier
"""

from __future__ import annotations

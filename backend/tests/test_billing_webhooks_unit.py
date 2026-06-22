"""Unit tests for billing webhooks module."""

from app.billing.webhooks import _normalize_webhook, _SubscriptionStore


def test_normalize_paypal_webhook():
    """Verify PayPal webhooks normalize correctly."""
    paypal_event = {
        "event_type": "BILLING.SUBSCRIPTION.CREATED",
        "resource": {
            "id": "sub_123",
            "status": "ACTIVE",
            "plan_id": "plan_starter",
        },
    }

    # Normalize should extract common fields
    normalized = _normalize_webhook(paypal_event)
    assert normalized is not None
    event_type, customer_id, data = normalized

    assert event_type == "BILLING.SUBSCRIPTION.CREATED"
    # PayPal resources put the subscription id on ``resource.id`` but the
    # normalizer deliberately skips bare ``id`` fields (those can be PayPal
    # event-level ids like WH-...). Here the resource has no separate
    # ``subscription_id`` key, so customer_id remains empty and callers
    # should use ``data["id"]`` for the subscription reference.
    assert customer_id == ""
    assert data is not None
    assert data.get("id") == "sub_123"


def test_normalize_stripe_webhook():
    """Verify Stripe webhooks normalize correctly (compatibility)."""
    stripe_event = {
        "type": "customer.subscription.created",
        "data": {
            "object": {
                "id": "sub_stripe_123",
                "customer": "cust_123",
                "status": "active",
            }
        },
    }

    normalized = _normalize_webhook(stripe_event)
    assert normalized is not None
    event_type, customer_id, data = normalized

    # Should be in Stripe format
    assert "customer" in str(event_type).lower() or "subscription" in str(event_type).lower()


def test_subscription_store_persists_subscriptions():
    """Verify subscription store can persist and retrieve."""
    store = _SubscriptionStore()

    # Add a subscription
    store.set("user_123", tier="plan_pro", status="active", subscription_id="sub_456")

    # Retrieve
    sub = store.get("user_123")
    assert sub is not None
    assert sub["subscription_id"] == "sub_456"
    assert sub["plan_tier"] == "plan_pro"


def test_subscription_store_handles_missing_keys():
    """Verify subscription store doesn't crash on missing keys."""
    store = _SubscriptionStore()

    # Get non-existent key
    sub = store.get("nonexistent_user")
    assert sub is None

    # Delete non-existent key
    store.delete("nonexistent_user")  # Should not raise

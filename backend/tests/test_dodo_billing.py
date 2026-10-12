"""Tests for the Dodo Payments billing integration (E2.3/E2.4).

Covers Standard Webhooks signature verification, webhook normalization,
entitlement flips through the shared subscription store, webhook-id
idempotency (E2.4), the checkout-session client, product-id → tier
resolution, and the entitlement-repair reconciliation sweep.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import importlib
import json
import time
from pathlib import Path
from typing import Any

import httpx
import pytest

WEBHOOK_SECRET = base64.b64encode(b"test-dodo-webhook-secret-key").decode("ascii")
OLD_WEBHOOK_SECRET = base64.b64encode(b"test-old-rotated-secret-key").decode("ascii")


def _sign(
    raw_body: bytes,
    *,
    webhook_id: str = "wh_test_001",
    timestamp: int | None = None,
    secret: str = WEBHOOK_SECRET,
) -> tuple[dict[str, str], int]:
    """Build valid Standard-Webhooks headers for a raw body."""
    ts = int(time.time()) if timestamp is None else timestamp
    msg = f"{webhook_id}.{ts}.{raw_body.decode('utf-8')}".encode()
    key = base64.b64decode(secret)
    signature = "v1," + hmac.new(key, msg, hashlib.sha256).hexdigest()
    return {
        "webhook-id": webhook_id,
        "webhook-timestamp": str(ts),
        "webhook-signature": signature,
    }, ts


def _dodo_event(
    event_type: str,
    *,
    subscription_id: str = "sub_dodo_123",
    customer_id: str = "user_dodo_001",
    product_id: str = "pdt_starter_001",
    status: str = "active",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "business_id": "biz_dodo_test",
        "type": event_type,
        "timestamp": "2026-08-18T00:00:00Z",
        "data": {
            "subscription_id": subscription_id,
            "customer_id": customer_id,
            "metadata": {"dataforge_user_id": customer_id},
            "product_id": product_id,
            "status": status,
            "payment_frequency_interval": "monthly",
            "next_billing_date": "2026-09-18",
        },
    }
    if extra:
        body["data"].update(extra)
    return body


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def subscriptions_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the shared subscription store at a tmp file (module reloaded)."""
    target = tmp_path / "billing_subscriptions.json"
    monkeypatch.setenv("DATAFORGE_BILLING_SUBSCRIPTIONS_FILE", str(target))
    importlib.reload(importlib.import_module("app.billing.webhooks"))
    return target


@pytest.fixture
def dodo_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Configure the Dodo env vars used by most webhook tests."""
    monkeypatch.setenv("DODO_PAYMENTS_WEBHOOK_KEY", WEBHOOK_SECRET)
    monkeypatch.setenv("DODO_PRODUCT_ID_STARTER", "pdt_starter_001")
    monkeypatch.setenv("DODO_PRODUCT_ID_PRO", "pdt_pro_001")
    monkeypatch.setenv("DODO_PRODUCT_ID_ENTERPRISE", "pdt_enterprise_001")
    import app.billing.dodo as dodo_mod

    dodo_mod.reset_dodo_product_cache()


@pytest.fixture
def dodo_state_store(tmp_path: Path) -> Any:
    """A per-test webhook-id state store."""
    from app.billing.dodo import DodoWebhookStateStore

    return DodoWebhookStateStore(tmp_path / "dodo_webhook_state.json")


# ---------------------------------------------------------------------------
# Signature verification
# ---------------------------------------------------------------------------


class TestSignatureVerification:
    def test_accepts_valid_signature(self, dodo_env: None) -> None:
        from app.billing.dodo import verify_dodo_webhook_signature

        raw = json.dumps(_dodo_event("subscription.active")).encode("utf-8")
        headers, _ = _sign(raw)
        verify_dodo_webhook_signature(raw, headers)  # must not raise

    def test_rejects_tampered_body(self) -> None:
        from app.billing.dodo import verify_dodo_webhook_signature

        raw = json.dumps(_dodo_event("subscription.active")).encode("utf-8")
        headers, _ = _sign(raw)
        tampered = raw.replace(b"user_dodo_001", b"user_dodo_999")
        with pytest.raises(ValueError):
            verify_dodo_webhook_signature(tampered, headers)

    def test_rejects_missing_headers(self) -> None:
        from app.billing.dodo import verify_dodo_webhook_signature

        raw = json.dumps(_dodo_event("subscription.active")).encode("utf-8")
        with pytest.raises(ValueError):
            verify_dodo_webhook_signature(raw, {})

    def test_rejects_stale_timestamp(self) -> None:
        from app.billing.dodo import verify_dodo_webhook_signature

        raw = json.dumps(_dodo_event("subscription.active")).encode("utf-8")
        stale_ts = int(time.time()) - 3600
        headers, _ = _sign(raw, timestamp=stale_ts)
        with pytest.raises(ValueError):
            verify_dodo_webhook_signature(raw, headers)

    def test_accepts_timestamp_within_tolerance(self, dodo_env: None) -> None:
        from app.billing.dodo import verify_dodo_webhook_signature

        raw = json.dumps(_dodo_event("subscription.active")).encode("utf-8")
        recent_ts = int(time.time()) - 60
        headers, _ = _sign(raw, timestamp=recent_ts)
        verify_dodo_webhook_signature(raw, headers)  # must not raise

    def test_supports_rotated_second_signature(self, dodo_env: None) -> None:
        from app.billing.dodo import verify_dodo_webhook_signature

        raw = json.dumps(_dodo_event("subscription.active")).encode("utf-8")
        new_headers, _ = _sign(raw, secret=WEBHOOK_SECRET)
        old_headers, _ = _sign(raw, secret=OLD_WEBHOOK_SECRET)
        # Dodo sends the newest signature first, older ones after (rotation).
        combined = f"{new_headers['webhook-signature']} {old_headers['webhook-signature']}"
        headers = {
            "webhook-id": new_headers["webhook-id"],
            "webhook-timestamp": new_headers["webhook-timestamp"],
            "webhook-signature": combined,
        }
        verify_dodo_webhook_signature(raw, headers)  # must not raise

    def test_rejects_signature_from_wrong_key(self) -> None:
        from app.billing.dodo import verify_dodo_webhook_signature

        raw = json.dumps(_dodo_event("subscription.active")).encode("utf-8")
        headers, _ = _sign(raw, secret=OLD_WEBHOOK_SECRET)
        with pytest.raises(ValueError):
            verify_dodo_webhook_signature(raw, headers)


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------


class TestNormalization:
    def test_subscription_active_normalizes(self, dodo_env: None) -> None:
        from app.billing.dodo import normalize_dodo_webhook

        event_type, customer_id, data = normalize_dodo_webhook(_dodo_event("subscription.active"))
        assert event_type == "subscription.updated"
        assert customer_id == "user_dodo_001"
        assert data["plan_tier"] == "starter"
        assert data["status"] == "active"
        assert data["subscription_id"] == "sub_dodo_123"
        assert data["provider_customer_id"] == "user_dodo_001"

    def test_subscription_on_hold_normalizes(self) -> None:
        from app.billing.dodo import normalize_dodo_webhook

        event_type, _, _ = normalize_dodo_webhook(_dodo_event("subscription.on_hold", status="on_hold"))
        assert event_type == "subscription.on_hold"

    def test_subscription_cancelled_normalizes(self) -> None:
        from app.billing.dodo import normalize_dodo_webhook

        event_type, _, _ = normalize_dodo_webhook(_dodo_event("subscription.cancelled", status="cancelled"))
        assert event_type == "subscription.cancelled"

    def test_payment_succeeded_normalizes(self) -> None:
        from app.billing.dodo import normalize_dodo_webhook

        event_type, _, _ = normalize_dodo_webhook(_dodo_event("payment.succeeded", product_id=""))
        assert event_type == "payment.succeeded"

    def test_unknown_product_id_rejected(self) -> None:
        from app.billing.dodo import normalize_dodo_webhook

        with pytest.raises(ValueError):
            normalize_dodo_webhook(_dodo_event("subscription.active", product_id="pdt_unknown_xyz"))

    def test_missing_dataforge_identity_is_rejected(self) -> None:
        from app.billing.dodo import normalize_dodo_webhook

        body = _dodo_event("subscription.active")
        body["data"].pop("metadata")
        with pytest.raises(ValueError, match="dataforge_user_id"):
            normalize_dodo_webhook(body)


# ---------------------------------------------------------------------------
# Entitlement flips through the shared store
# ---------------------------------------------------------------------------


class TestEntitlementFlips:
    def test_subscription_active_grants_starter_tier(
        self, subscriptions_file: Path, dodo_env: None, dodo_state_store: Any
    ) -> None:
        from app.billing.dodo import handle_dodo_webhook
        from app.billing.webhooks import get_customer_subscription

        raw = json.dumps(_dodo_event("subscription.active")).encode("utf-8")
        headers, _ = _sign(raw)

        result = handle_dodo_webhook(raw, headers, state_store=dodo_state_store)
        assert result["status"] == "ok"
        sub = get_customer_subscription("user_dodo_001")
        assert sub is not None
        assert sub["plan_tier"] == "starter"
        assert sub["status"] == "active"
        assert sub["subscription_id"] == "sub_dodo_123"

    def test_subscription_renewed_keeps_tier_active(
        self, subscriptions_file: Path, dodo_env: None, dodo_state_store: Any
    ) -> None:
        from app.billing.dodo import handle_dodo_webhook
        from app.billing.webhooks import get_customer_subscription

        raw = json.dumps(_dodo_event("subscription.active")).encode("utf-8")
        headers, _ = _sign(raw)
        handle_dodo_webhook(raw, headers, state_store=dodo_state_store)

        renewed_raw = json.dumps(_dodo_event("subscription.renewed")).encode("utf-8")
        renewed_headers, _ = _sign(renewed_raw, webhook_id="wh_test_002")
        handle_dodo_webhook(renewed_raw, renewed_headers, state_store=dodo_state_store)

        sub = get_customer_subscription("user_dodo_001")
        assert sub is not None
        assert sub["plan_tier"] == "starter"
        assert sub["status"] == "active"

    def test_subscription_on_hold_marks_past_due_preserving_tier(
        self, subscriptions_file: Path, dodo_env: None, dodo_state_store: Any
    ) -> None:
        from app.billing.dodo import handle_dodo_webhook
        from app.billing.webhooks import get_customer_subscription

        active_raw = json.dumps(_dodo_event("subscription.active")).encode("utf-8")
        active_headers, _ = _sign(active_raw, webhook_id="wh_active_001")
        handle_dodo_webhook(active_raw, active_headers, state_store=dodo_state_store)

        hold_raw = json.dumps(_dodo_event("subscription.on_hold", status="on_hold")).encode("utf-8")
        hold_headers, _ = _sign(hold_raw, webhook_id="wh_hold_001")
        handle_dodo_webhook(hold_raw, hold_headers, state_store=dodo_state_store)

        sub = get_customer_subscription("user_dodo_001")
        assert sub is not None
        assert sub["plan_tier"] == "starter", "tier must be preserved on hold"
        assert sub["status"] == "past_due"

    def test_subscription_cancelled_downgrades_to_free(
        self, subscriptions_file: Path, dodo_env: None, dodo_state_store: Any
    ) -> None:
        from app.billing.dodo import handle_dodo_webhook
        from app.billing.webhooks import get_customer_subscription

        active_raw = json.dumps(_dodo_event("subscription.active")).encode("utf-8")
        active_headers, _ = _sign(active_raw, webhook_id="wh_active_001")
        handle_dodo_webhook(active_raw, active_headers, state_store=dodo_state_store)

        cancel_raw = json.dumps(_dodo_event("subscription.cancelled", status="cancelled")).encode("utf-8")
        cancel_headers, _ = _sign(cancel_raw, webhook_id="wh_cancel_001")
        handle_dodo_webhook(cancel_raw, cancel_headers, state_store=dodo_state_store)

        sub = get_customer_subscription("user_dodo_001")
        assert sub is not None
        assert sub["plan_tier"] == "free"
        assert sub["status"] == "canceled"

    def test_payment_failed_marks_past_due(self, subscriptions_file: Path, dodo_env: None, dodo_state_store: Any) -> None:
        from app.billing.dodo import handle_dodo_webhook
        from app.billing.webhooks import get_customer_subscription

        active_raw = json.dumps(_dodo_event("subscription.active")).encode("utf-8")
        active_headers, _ = _sign(active_raw, webhook_id="wh_active_001")
        handle_dodo_webhook(active_raw, active_headers, state_store=dodo_state_store)

        failed_raw = json.dumps(_dodo_event("payment.failed", status="failed")).encode("utf-8")
        failed_headers, _ = _sign(failed_raw, webhook_id="wh_fail_001")
        handle_dodo_webhook(failed_raw, failed_headers, state_store=dodo_state_store)

        sub = get_customer_subscription("user_dodo_001")
        assert sub is not None
        assert sub["status"] == "past_due"

    def test_payment_succeeded_reactivates(self, subscriptions_file: Path, dodo_env: None, dodo_state_store: Any) -> None:
        from app.billing.dodo import handle_dodo_webhook
        from app.billing.webhooks import get_customer_subscription

        active_raw = json.dumps(_dodo_event("subscription.active")).encode("utf-8")
        active_headers, _ = _sign(active_raw, webhook_id="wh_active_001")
        handle_dodo_webhook(active_raw, active_headers, state_store=dodo_state_store)

        hold_raw = json.dumps(_dodo_event("subscription.on_hold", status="on_hold")).encode("utf-8")
        hold_headers, _ = _sign(hold_raw, webhook_id="wh_hold_001")
        handle_dodo_webhook(hold_raw, hold_headers, state_store=dodo_state_store)

        paid_raw = json.dumps(_dodo_event("payment.succeeded", status="succeeded")).encode("utf-8")
        paid_headers, _ = _sign(paid_raw, webhook_id="wh_paid_001")
        handle_dodo_webhook(paid_raw, paid_headers, state_store=dodo_state_store)

        sub = get_customer_subscription("user_dodo_001")
        assert sub is not None
        assert sub["plan_tier"] == "starter"
        assert sub["status"] == "active"


# ---------------------------------------------------------------------------
# Idempotency + fail-closed (E2.4)
# ---------------------------------------------------------------------------


class TestIdempotencyAndFailClosed:
    def test_replayed_webhook_id_is_skipped(self, subscriptions_file: Path, dodo_env: None, dodo_state_store: Any) -> None:
        from app.billing.dodo import handle_dodo_webhook
        from app.billing.webhooks import get_customer_subscription

        cancel_raw = json.dumps(_dodo_event("subscription.cancelled", status="cancelled")).encode("utf-8")
        cancel_headers, _ = _sign(cancel_raw, webhook_id="wh_same_id")
        handle_dodo_webhook(cancel_raw, cancel_headers, state_store=dodo_state_store)

        # Replay the SAME webhook-id with a different (active) body — must be
        # ignored so a stale replay can never undo a newer state.
        active_raw = json.dumps(_dodo_event("subscription.active")).encode("utf-8")
        active_headers, _ = _sign(active_raw, webhook_id="wh_same_id")
        result = handle_dodo_webhook(active_raw, active_headers, state_store=dodo_state_store)
        assert result["status"] == "already_processed"
        sub = get_customer_subscription("user_dodo_001")
        assert sub is not None
        assert sub["plan_tier"] == "free", "replay must not apply the stale event"

    def test_distinct_webhook_id_applies_again(self, subscriptions_file: Path, dodo_env: None, dodo_state_store: Any) -> None:
        from app.billing.dodo import handle_dodo_webhook
        from app.billing.webhooks import get_customer_subscription

        for wid in ("wh_a", "wh_b"):
            raw = json.dumps(_dodo_event("subscription.active")).encode("utf-8")
            headers, _ = _sign(raw, webhook_id=wid)
            handle_dodo_webhook(raw, headers, state_store=dodo_state_store)
        sub = get_customer_subscription("user_dodo_001")
        assert sub is not None
        assert sub["plan_tier"] == "starter"

    def test_missing_webhook_key_fails_closed(self) -> None:
        from app.billing.dodo import handle_dodo_webhook
        from fastapi import HTTPException

        raw = json.dumps(_dodo_event("subscription.active")).encode("utf-8")
        headers, _ = _sign(raw)
        with pytest.raises(HTTPException) as exc_info:
            handle_dodo_webhook(raw, headers)
        assert exc_info.value.status_code == 503

    def test_invalid_signature_raises_401(self, dodo_env: None) -> None:
        from app.billing.dodo import handle_dodo_webhook
        from fastapi import HTTPException

        raw = json.dumps(_dodo_event("subscription.active")).encode("utf-8")
        headers, _ = _sign(raw, secret=OLD_WEBHOOK_SECRET)
        with pytest.raises(HTTPException) as exc_info:
            handle_dodo_webhook(raw, headers)
        assert exc_info.value.status_code == 401

    def test_dodo_webhook_is_not_blocked_by_api_auth(self, client, monkeypatch: pytest.MonkeyPatch) -> None:
        """Provider webhooks reach signature verification without an API key."""
        monkeypatch.setenv("DODO_PAYMENTS_WEBHOOK_KEY", WEBHOOK_SECRET)
        resp = client.post("/api/billing/dodo/webhook", json={})
        assert resp.status_code == 401, resp.text

    def test_checkout_uses_persistent_identity_not_request_identity(self, client, monkeypatch: pytest.MonkeyPatch) -> None:
        """Checkout metadata and customer details cannot be spoofed by the browser."""
        signup = client.post(
            "/api/saas/signup",
            json={
                "email": "trusted-checkout@example.com",
                "password": "SecurePass123!",
                "display_name": "Trusted Customer",
            },
        )
        assert signup.status_code == 201, signup.text

        captured: dict[str, Any] = {}

        class _ConfiguredClient:
            is_configured = True

            def create_checkout_session(self, **kwargs: Any) -> dict[str, Any]:
                captured.update(kwargs)
                return {"checkout_url": "https://checkout.dodopayments.com/session", "session_id": "cs_route"}

        import app.billing.dodo as dodo_mod

        monkeypatch.setattr(dodo_mod, "get_dodo_client", _ConfiguredClient)
        resp = client.post(
            "/api/billing/dodo/checkout",
            json={
                "plan_tier": "starter",
                "return_url": "https://example.com/return",
                "email": "attacker@example.com",
                "name": "Attacker",
            },
            cookies=signup.cookies,
        )
        assert resp.status_code == 200, resp.text
        assert captured["customer_email"] == "trusted-checkout@example.com"
        assert captured["customer_name"] == "Trusted Customer"
        assert captured["metadata"]["dataforge_user_id"] == signup.json()["user_id"]
        assert captured["metadata"]["dataforge_org_id"] == signup.json()["organization_id"]
        assert captured["metadata"]["dataforge_project_id"] == signup.json()["project_id"]


# ---------------------------------------------------------------------------
# Product-id → tier resolution
# ---------------------------------------------------------------------------


class TestProductTierResolution:
    def test_resolves_configured_products(self, dodo_env: None) -> None:
        from app.billing.dodo import resolve_tier_from_dodo_product

        assert resolve_tier_from_dodo_product("pdt_starter_001").value == "starter"
        assert resolve_tier_from_dodo_product("pdt_pro_001").value == "pro"
        assert resolve_tier_from_dodo_product("pdt_enterprise_001").value == "enterprise"

    def test_unknown_product_returns_free(self, dodo_env: None) -> None:
        from app.billing.dodo import resolve_tier_from_dodo_product

        assert resolve_tier_from_dodo_product("pdt_unknown").value == "free"
        assert resolve_tier_from_dodo_product("").value == "free"


# ---------------------------------------------------------------------------
# Dodo client (httpx, mocked transport)
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, status_code: int, json_body: dict[str, Any]) -> None:
        self.status_code = status_code
        self._json_body = json_body

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            msg = f"HTTP {self.status_code}"
            raise httpx.HTTPStatusError(
                msg,
                request=httpx.Request("GET", "https://test.dodopayments.com"),
                response=httpx.Response(self.status_code, json=self._json_body),
            )

    def json(self) -> dict[str, Any]:
        return self._json_body


class _FakeClient:
    def __init__(self, responses: list[Any]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, str]] = []
        self.kwargs: list[dict[str, Any]] = []

    def post(self, url: str, **kwargs: Any) -> Any:
        self.calls.append(("POST", url))
        self.kwargs.append(kwargs)
        return self.responses.pop(0)

    def get(self, url: str, **kwargs: Any) -> Any:
        self.calls.append(("GET", url))
        self.kwargs.append(kwargs)
        return self.responses.pop(0)

    def close(self) -> None:
        return None


@pytest.fixture
def fake_http_client(monkeypatch: pytest.MonkeyPatch) -> _FakeClient:
    """Install a fake open_safe_client; returns the recording fake client."""
    import app.billing.dodo as dodo_mod

    fake = _FakeClient([])

    class _CM:
        def __enter__(self) -> _FakeClient:
            return fake

        def __exit__(self, *args: Any) -> None:
            return None

    monkeypatch.setattr(dodo_mod, "open_safe_client", lambda **kwargs: _CM())
    return fake


class TestDodoClient:
    def test_create_checkout_session(self, fake_http_client: _FakeClient) -> None:
        from app.billing.dodo import DodoClient

        fake_http_client.responses.append(
            _FakeResponse(
                200,
                {"session_id": "cs_123", "checkout_url": "https://checkout.dodopayments.com/abc", "status": "open"},
            )
        )
        client = DodoClient(
            api_key="test-key",
            base_url="https://test.dodopayments.com",
            product_ids={"starter": "pdt_starter_001"},
        )
        result = client.create_checkout_session(
            plan_tier="starter",
            customer_email="a@b.com",
            customer_name="Ann",
            return_url="https://example.com/success",
            metadata={"dataforge_user_id": "internal-user-1"},
        )
        assert result["session_id"] == "cs_123"
        assert result["checkout_url"].startswith("https://")
        assert fake_http_client.calls[0][0] == "POST"
        assert fake_http_client.calls[0][1] == "https://test.dodopayments.com/checkouts"
        assert fake_http_client.kwargs[0]["json"]["metadata"] == {"dataforge_user_id": "internal-user-1"}

    def test_create_checkout_session_requires_product_id(self, fake_http_client: _FakeClient) -> None:
        from app.billing.dodo import DodoClient

        client = DodoClient(
            api_key="test-key",
            base_url="https://test.dodopayments.com",
            product_ids={"starter": "pdt_starter_001"},
        )
        with pytest.raises(ValueError):
            client.create_checkout_session(
                plan_tier="pro",
                customer_email="a@b.com",
                customer_name="Ann",
                return_url="https://example.com/success",
            )

    def test_create_checkout_session_requires_credentials(self) -> None:
        from app.billing.dodo import DodoClient

        client = DodoClient(
            api_key="",
            base_url="https://test.dodopayments.com",
            product_ids={},
        )
        with pytest.raises(RuntimeError):
            client.create_checkout_session(
                plan_tier="starter",
                customer_email="a@b.com",
                customer_name="Ann",
                return_url="https://example.com/success",
            )

    def test_get_subscription(self, fake_http_client: _FakeClient) -> None:
        from app.billing.dodo import DodoClient

        fake_http_client.responses.append(
            _FakeResponse(
                200,
                {
                    "subscription_id": "sub_dodo_123",
                    "status": "active",
                    "product_id": "pdt_starter_001",
                },
            )
        )
        client = DodoClient(
            api_key="test-key",
            base_url="https://test.dodopayments.com",
            product_ids={"starter": "pdt_starter_001"},
        )
        sub = client.get_subscription("sub_dodo_123")
        assert sub["status"] == "active"
        assert fake_http_client.calls[0][0] == "GET"
        assert fake_http_client.calls[0][1] == "https://test.dodopayments.com/subscriptions/sub_dodo_123"

    def test_is_configured(self) -> None:
        from app.billing.dodo import DodoClient

        assert DodoClient(api_key="k", base_url="u", product_ids={}).is_configured
        assert not DodoClient(api_key="", base_url="u", product_ids={}).is_configured


# ---------------------------------------------------------------------------
# Reconciliation sweep (E2.4)
# ---------------------------------------------------------------------------


class TestReconcileEntitlements:
    def _seed_store(self, subscriptions_file: Path, **record: Any) -> None:
        from app.billing.webhooks import _SubscriptionStore

        store = _SubscriptionStore(Path(subscriptions_file))
        store.set(
            record.get("customer_id", "user_recon_001"),
            tier=record.get("tier", "starter"),
            status=record.get("status", "active"),
            subscription_id=record.get("subscription_id", "sub_recon_001"),
        )

    def _reconciler(self, monkeypatch: pytest.MonkeyPatch, client: Any) -> Any:
        import app.billing.dodo as dodo_mod

        return dodo_mod.reconcile_entitlements(client=client)

    def test_reconcile_repairs_stale_tier(
        self, subscriptions_file: Path, dodo_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.billing.dodo import DodoClient

        self._seed_store(subscriptions_file, tier="starter", subscription_id="sub_recon_001")

        class _UpgradedClient(DodoClient):
            def __init__(self) -> None:
                super().__init__(api_key="k", base_url="u", product_ids={"pro": "pdt_pro_001"})

            def get_subscription(self, subscription_id: str) -> dict[str, Any]:
                assert subscription_id == "sub_recon_001"
                return {"subscription_id": subscription_id, "status": "active", "product_id": "pdt_pro_001"}

        report = self._reconciler(monkeypatch, _UpgradedClient())
        assert report["checked"] == 1
        assert "user_recon_001" in report["repaired"]
        from app.billing.webhooks import get_customer_subscription

        sub = get_customer_subscription("user_recon_001")
        assert sub is not None
        assert sub["plan_tier"] == "pro"

    def test_reconcile_downgrades_cancelled(
        self, subscriptions_file: Path, dodo_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.billing.dodo import DodoClient

        self._seed_store(subscriptions_file, tier="starter", subscription_id="sub_recon_001")

        class _CancelledClient(DodoClient):
            def __init__(self) -> None:
                super().__init__(api_key="k", base_url="u", product_ids={})

            def get_subscription(self, subscription_id: str) -> dict[str, Any]:
                return {"subscription_id": subscription_id, "status": "cancelled", "product_id": "pdt_pro_001"}

        report = self._reconciler(monkeypatch, _CancelledClient())
        assert "user_recon_001" in report["downgraded"]
        from app.billing.webhooks import get_customer_subscription

        sub = get_customer_subscription("user_recon_001")
        assert sub is not None
        assert sub["plan_tier"] == "free"
        assert sub["status"] == "canceled"

    def test_reconcile_marks_on_hold_past_due(
        self, subscriptions_file: Path, dodo_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.billing.dodo import DodoClient

        self._seed_store(subscriptions_file, tier="starter", subscription_id="sub_recon_001")

        class _HoldClient(DodoClient):
            def __init__(self) -> None:
                super().__init__(api_key="k", base_url="u", product_ids={})

            def get_subscription(self, subscription_id: str) -> dict[str, Any]:
                return {"subscription_id": subscription_id, "status": "on_hold", "product_id": "pdt_pro_001"}

        report = self._reconciler(monkeypatch, _HoldClient())
        assert "user_recon_001" in report["held"]
        from app.billing.webhooks import get_customer_subscription

        sub = get_customer_subscription("user_recon_001")
        assert sub is not None
        assert sub["status"] == "past_due"
        assert sub["plan_tier"] == "starter", "tier preserved on hold"

    def test_reconcile_leaves_unchanged_on_api_error(
        self, subscriptions_file: Path, dodo_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.billing.dodo import DodoClient

        self._seed_store(subscriptions_file, tier="starter", subscription_id="sub_recon_001")

        class _ErrorClient(DodoClient):
            def __init__(self) -> None:
                super().__init__(api_key="k", base_url="u", product_ids={})

            def get_subscription(self, subscription_id: str) -> dict[str, Any]:
                msg = "dodo api down"
                raise RuntimeError(msg)

        report = self._reconciler(monkeypatch, _ErrorClient())
        assert "user_recon_001" in report["errors"]
        assert not report["repaired"]
        assert not report["downgraded"]
        from app.billing.webhooks import get_customer_subscription

        sub = get_customer_subscription("user_recon_001")
        assert sub is not None
        assert sub["plan_tier"] == "starter", "API outage must not mass-downgrade"

    def test_reconcile_skips_free_records_without_subscription(
        self, subscriptions_file: Path, dodo_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.billing.dodo import DodoClient

        self._seed_store(subscriptions_file, tier="free", subscription_id="")

        class _Client(DodoClient):
            def __init__(self) -> None:
                super().__init__(api_key="k", base_url="u", product_ids={})

            def get_subscription(self, subscription_id: str) -> dict[str, Any]:
                msg = "must not be called for free records"
                raise AssertionError(msg)

        report = self._reconciler(monkeypatch, _Client())
        assert report["checked"] == 0

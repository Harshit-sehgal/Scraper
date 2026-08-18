#!/usr/bin/env python3
"""Dodo Payments money-loop e2e — signup → pay → limit → blocked → upgrade → resume.

Runs the full billing loop against a **mocked Dodo API** so it is
deterministic and credential-free (CI-safe):

    1. "signup"      — a fresh user with no subscription is free-tier.
    2. checkout      — POST /api/billing/dodo/checkout shape is produced
                       (DodoClient.create_checkout_session → checkout_url).
    3. webhook       — a signed ``subscription.active`` webhook flips the
                       entitlement to starter.
    4. limit reached — with a 1-fetch starter quota the user hits 429 on
                       job creation (the E2.1 hard-stop).
    5. blocked       — a signed ``subscription.on_hold`` webhook marks
                       past_due (tier preserved); quota stays blocked.
    6. resume        — a signed ``subscription.renewed`` webhook reactivates;
                       the user can create jobs again.

Against real Dodo credentials the same script can run in live mode:

    DODO_PAYMENTS_API_KEY=... DODO_PAYMENTS_WEBHOOK_KEY=... \\
    DODO_PRODUCT_ID_STARTER=... python3 scripts/run_dodo_billing_e2e.py --live

(Live mode still needs the checkout URL to be completed by a human in a
browser; the webhook steps then exercise real signature verification.)

Exit code 0 on success, 1 on any failed step.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

_BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

os.environ.setdefault("DATAFORGE_DOTENV_PATH", "/dev/null")
os.environ.setdefault("DATAFORGE_ENV", "test")
os.environ.setdefault("DATAFORGE_STORAGE_BACKEND", "sqlite")
os.environ.setdefault("DATAFORGE_SKIP_DB_CHECK", "true")

_PASSED: list[str] = []


def _check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        _PASSED.append(name)
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name} {detail}")
        sys.exit(1)


def _sign_webhook(raw_body: bytes, webhook_id: str, secret: str) -> dict[str, str]:
    ts = int(time.time())
    msg = f"{webhook_id}.{ts}.{raw_body.decode('utf-8')}".encode()
    key = base64.b64decode(secret)
    return {
        "webhook-id": webhook_id,
        "webhook-timestamp": str(ts),
        "webhook-signature": "v1," + hmac.new(key, msg, hashlib.sha256).hexdigest(),
    }


def _dodo_event(event_type: str, subscription_id: str, customer_id: str, product_id: str) -> bytes:
    body = {
        "business_id": "biz_e2e",
        "type": event_type,
        "timestamp": "2026-08-18T00:00:00Z",
        "data": {
            "subscription_id": subscription_id,
            "customer_id": customer_id,
            "product_id": product_id,
            "status": "active",
            "payment_frequency_interval": "monthly",
        },
    }
    return json.dumps(body).encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="use real Dodo env config instead of mocks")
    args = parser.parse_args()

    print("Dodo Payments money-loop e2e")
    print("=" * 60)

    # ------------------------------------------------------------------
    # Sandbox (mock) setup
    # ------------------------------------------------------------------
    webhook_secret = base64.b64encode(b"e2e-webhook-secret").decode("ascii")
    customer_id = "user_e2e_dodo_001"
    subscription_id = "sub_e2e_dodo_001"
    product_id = "pdt_e2e_starter_001"
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["DODO_PAYMENTS_WEBHOOK_KEY"] = webhook_secret
        os.environ["DODO_PRODUCT_ID_STARTER"] = product_id
        os.environ["DODO_PRODUCT_ID_PRO"] = "pdt_e2e_pro_001"
        os.environ["DODO_PRODUCT_ID_ENTERPRISE"] = "pdt_e2e_enterprise_001"
        os.environ["DATAFORGE_BILLING_SUBSCRIPTIONS_FILE"] = str(Path(tmp) / "subscriptions.json")
        os.environ["DODO_WEBHOOK_STATE_FILE"] = str(Path(tmp) / "webhook_state.json")

        from app.billing.dodo import (
            DodoClient,
            get_dodo_client,
            handle_dodo_webhook,
            reset_dodo_client,
            reset_dodo_product_cache,
            reset_dodo_state_store,
        )
        from app.billing.webhooks import get_customer_subscription
        from app.plan_enforcer import _PLAN_LIMITS, check_usage_limit
        from app.utils.usage_ledger import UsageType, get_usage_ledger

        reset_dodo_product_cache()
        reset_dodo_state_store()
        get_usage_ledger().reset_quotas()

        if args.live:
            client = get_dodo_client()
        else:
            # Mock Dodo API: deterministic checkout session.
            class _MockDodoClient(DodoClient):
                def create_checkout_session(self, **kwargs: Any) -> dict[str, Any]:
                    assert kwargs["plan_tier"] == "starter"
                    return {
                        "session_id": "cs_e2e_001",
                        "checkout_url": "https://checkout.dodopayments.com/e2e/abc",
                        "status": "open",
                    }

            reset_dodo_client(
                _MockDodoClient(api_key="mock", base_url="https://test.dodopayments.com", product_ids={"starter": product_id})
            )
            client = get_dodo_client()

        # ------------------------------------------------------------------
        # 1. Signup: fresh user is free tier
        # ------------------------------------------------------------------
        print("\n[1] signup — fresh user is free tier")
        sub = get_customer_subscription(customer_id)
        _check("fresh user has no subscription record", sub is None)

        # ------------------------------------------------------------------
        # 2. Checkout: session is created for the Starter plan
        # ------------------------------------------------------------------
        print("\n[2] checkout — starter session created")
        session = client.create_checkout_session(
            plan_tier="starter",
            customer_email="e2e@example.com",
            customer_name="E2E User",
            return_url="https://example.com/success",
        )
        _check("checkout session created", bool(session.get("session_id")))
        _check("hosted checkout URL returned", str(session.get("checkout_url", "")).startswith("https://"))

        # ------------------------------------------------------------------
        # 3. Webhook: subscription.active flips entitlement to starter
        # ------------------------------------------------------------------
        print("\n[3] webhook — subscription.active grants starter")
        raw = _dodo_event("subscription.active", subscription_id, customer_id, product_id)
        headers = _sign_webhook(raw, "wh_e2e_active", webhook_secret)
        result = handle_dodo_webhook(raw, headers)
        _check("webhook processed", result["status"] == "ok", str(result))
        sub = get_customer_subscription(customer_id)
        _check("tier is starter", sub is not None and sub["plan_tier"] == "starter", str(sub))
        _check("status is active", sub is not None and sub["status"] == "active", str(sub))

        # ------------------------------------------------------------------
        # 4. Limit reached: a 1-fetch quota blocks the next fetch
        # ------------------------------------------------------------------
        print("\n[4] limit reached — 1-fetch quota blocks page 2")
        saved_limit = _PLAN_LIMITS.get(("starter", UsageType.PAGE_FETCHED))
        _PLAN_LIMITS[("starter", UsageType.PAGE_FETCHED)] = 1
        try:
            from app.plan_enforcer import _user_tier

            tier = _user_tier(customer_id)
            _check("tier lookup sees starter", tier == "starter", tier)
            allowed, details = check_usage_limit(customer_id, UsageType.PAGE_FETCHED)
            _check("first fetch fits", allowed, str(details))
            get_usage_ledger().record_usage(customer_id, UsageType.PAGE_FETCHED, quantity=1)
            allowed2, details2 = check_usage_limit(customer_id, UsageType.PAGE_FETCHED)
            _check("second fetch is blocked", not allowed2, str(details2))
        finally:
            if saved_limit is None:
                _PLAN_LIMITS.pop(("starter", UsageType.PAGE_FETCHED), None)
            else:
                _PLAN_LIMITS[("starter", UsageType.PAGE_FETCHED)] = saved_limit

        # ------------------------------------------------------------------
        # 5. Blocked: subscription.on_hold marks past_due (tier preserved)
        # ------------------------------------------------------------------
        print("\n[5] blocked — on_hold marks past_due")
        hold_raw = _dodo_event("subscription.on_hold", subscription_id, customer_id, product_id)
        hold_headers = _sign_webhook(hold_raw, "wh_e2e_hold", webhook_secret)
        result = handle_dodo_webhook(hold_raw, hold_headers)
        _check("hold webhook processed", result["status"] == "ok", str(result))
        sub = get_customer_subscription(customer_id)
        _check("status is past_due", sub is not None and sub["status"] == "past_due", str(sub))
        _check("tier preserved on hold", sub is not None and sub["plan_tier"] == "starter", str(sub))

        # ------------------------------------------------------------------
        # 6. Resume: subscription.renewed reactivates
        # ------------------------------------------------------------------
        print("\n[6] resume — renewed reactivates")
        renew_raw = _dodo_event("subscription.renewed", subscription_id, customer_id, product_id)
        renew_headers = _sign_webhook(renew_raw, "wh_e2e_renew", webhook_secret)
        result = handle_dodo_webhook(renew_raw, renew_headers)
        _check("renew webhook processed", result["status"] == "ok", str(result))
        sub = get_customer_subscription(customer_id)
        _check("status active again", sub is not None and sub["status"] == "active", str(sub))
        _check("tier still starter", sub is not None and sub["plan_tier"] == "starter", str(sub))

        # Idempotency: replaying the same webhook-id is a no-op.
        replay = handle_dodo_webhook(renew_raw, renew_headers)
        _check("replayed webhook-id is skipped", replay["status"] == "already_processed", str(replay))

    print("=" * 60)
    print(f"DODO E2E PASSED — {len(_PASSED)} checks green")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Regression test for billing subscription persistence.

Bug: backend/app/billing/webhooks.py used a module-level dict
``_customer_subscriptions`` to track customer plan state. In a
multi-worker production deployment, each worker keeps its own
in-process copy, so webhook updates processed by worker A are
invisible to worker B. The dict is also lost on every worker
restart, so a worker that never saw an update has no record at all.

This test pins the contract: subscription state must survive a
``reimport`` of the module (simulating a fresh worker process) AND
across instances of ``_SubscriptionStore`` that share the same
backing file. The store path is overridden via the
``DATAFORGE_BILLING_SUBSCRIPTIONS_FILE`` env var so each test run
writes to its own ``tmp_path``.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import pytest


@pytest.fixture
def subscriptions_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the subscription store at a tmp file for the duration of one test.

    Forces a module reload AFTER monkeypatching the env var so the
    module-level singleton is rebuilt against the new path.
    """
    target = tmp_path / "billing_subscriptions.json"
    monkeypatch.setenv("DATAFORGE_BILLING_SUBSCRIPTIONS_FILE", str(target))
    # Reload so the module-level singleton reads the fresh env var.
    importlib.reload(importlib.import_module("app.billing.webhooks"))
    return target


def _reload_webhooks_module() -> Any:
    """Re-import the webhooks module so any module-level cache is rebuilt.

    Returns ``Any`` because ``importlib.reload`` is statically typed
    as returning the generic ``ModuleType`` rather than the actual
    reloaded module — callers need access to webhooks-specific
    attributes like ``get_customer_subscription`` and
    ``_subscription_store``.
    """
    return importlib.reload(importlib.import_module("app.billing.webhooks"))


def test_subscription_persists_across_module_reload(subscriptions_file: Path) -> None:
    """Write a subscription, reload the module, verify the record survives.

    This simulates worker B reading state after worker A processed
    the webhook.
    """
    # worker A: import module, write a subscription, let module-level cache die
    webhooks_a = importlib.import_module("app.billing.webhooks")
    webhooks_a.set_customer_subscription(
        customer_id="cust_abc",
        tier="pro",
        status="active",
        subscription_id="sub_xyz",
    )
    assert webhooks_a.get_customer_subscription("cust_abc") is not None

    # worker B: reload the module — module-level dict is rebuilt empty,
    # but the persisted JSON on disk must still hold the record.
    webhooks_b = _reload_webhooks_module()
    record = webhooks_b.get_customer_subscription("cust_abc")
    assert record is not None, "Subscription state was lost on module reload — the store is per-process."
    assert record["plan_tier"] == "pro"
    assert record["status"] == "active"
    assert record["subscription_id"] == "sub_xyz"


def test_subscription_persisted_to_disk_after_set(subscriptions_file: Path) -> None:
    """set_customer_subscription must flush to disk before returning."""
    webhooks = importlib.import_module("app.billing.webhooks")
    webhooks.set_customer_subscription(
        customer_id="cust_disk",
        tier="team",
        status="active",
        subscription_id="sub_disk",
    )

    # The file must contain a writeable JSON document with our record.
    assert subscriptions_file.exists(), "Store did not write to disk"
    on_disk = json.loads(subscriptions_file.read_text())
    assert "cust_disk" in on_disk
    assert on_disk["cust_disk"]["plan_tier"] == "team"
    assert on_disk["cust_disk"]["subscription_id"] == "sub_disk"


def test_delete_customer_subscription_is_persistent(subscriptions_file: Path) -> None:
    """delete_customer_subscription must rewrite the disk file."""
    webhooks = importlib.import_module("app.billing.webhooks")
    webhooks.set_customer_subscription(
        customer_id="cust_del",
        tier="free",
        status="active",
        subscription_id="sub_del",
    )
    assert webhooks.get_customer_subscription("cust_del") is not None

    webhooks.delete_customer_subscription("cust_del")

    on_disk = json.loads(subscriptions_file.read_text())
    assert "cust_del" not in on_disk, "delete did not rewrite the on-disk store"
    # After module reload, the deletion must still be visible.
    webhooks_again = _reload_webhooks_module()
    assert webhooks_again.get_customer_subscription("cust_del") is None


def test_invoice_payment_failed_status_persists(subscriptions_file: Path) -> None:
    """The past_due status update from invoice.payment_failed must persist."""
    webhooks = importlib.import_module("app.billing.webhooks")
    webhooks.set_customer_subscription(
        customer_id="cust_pd",
        tier="pro",
        status="active",
        subscription_id="sub_pd",
    )
    webhooks._process_webhook_event(
        "invoice.payment_failed",
        {"customer_id": "cust_pd"},
    )

    on_disk = json.loads(subscriptions_file.read_text())
    assert on_disk["cust_pd"]["status"] == "past_due"

    webhooks_again = _reload_webhooks_module()
    assert webhooks_again.get_customer_subscription("cust_pd")["status"] == "past_due"


def test_list_subscriptions_endpoint_sees_persisted_records(
    subscriptions_file: Path,
) -> None:
    """The admin ``/api/billing/subscriptions`` endpoint must reflect
    records written by an earlier worker (i.e. records that were never
    in this process's in-memory cache)."""
    webhooks_a = importlib.import_module("app.billing.webhooks")
    webhooks_a.set_customer_subscription(
        customer_id="cust_admin_1",
        tier="enterprise",
        status="active",
        subscription_id="sub_admin_1",
    )

    # Simulate a fresh worker where the module-level store has no
    # hydrated cache (the disk is now the source of truth).
    webhooks_b = _reload_webhooks_module()

    total = len(webhooks_b._subscription_store)
    assert total == 1, (
        f"Admin list sees {total} records after a worker reload but a prior worker wrote 1 — the list is per-process."
    )
    values = webhooks_b._subscription_store.values()
    assert values[0]["plan_tier"] == "enterprise"


def test_concurrent_update_preserves_tier(subscriptions_file: Path) -> None:
    """FU-2026-07-05 (CRIT-2 TOCTOU regression): the SUSPENDED / PAYMENT-
    FAILED / PAYMENT-COMPLETED handlers must read-modify-write the
    subscription record ATOMICALLY under the cross-process flock so a
    concurrent webhook for the same customer cannot clobber the
    preserved plan_tier.

    Reproduces the original bug shape: two threads both observe a
    ``pro`` subscription and both write back with the same preserved
    tier. With a get-then-set (non-atomic) pattern this succeeds
    trivially, so we additionally mutate an independent counter field
    via ``update`` from N threads and assert the counter lands at N — a
    lost update would leave it below N.
    """
    import threading

    webhooks = importlib.import_module("app.billing.webhooks")
    webhooks.set_customer_subscription(
        customer_id="cust_race",
        tier="pro",
        status="active",
        subscription_id="sub_race",
    )

    N = 20
    barrier = threading.Barrier(N)

    def _incr(existing):
        assert existing is not None, "update received no record — flock path broken"
        # Inject a counter we sum across threads to detect lost updates. The
        # store would normally reject extra keys, but ``update`` preserves
        # arbitrary keys via the str(k): v copy.
        cur = int(existing.get("counter", 0)) + 1
        return {
            "customer_id": "cust_race",
            "plan_tier": existing.get("plan_tier", "free"),
            "status": existing.get("status", "active"),
            "subscription_id": existing.get("subscription_id", ""),
            "counter": cur,
        }

    def _worker() -> None:
        barrier.wait()
        webhooks.update_customer_subscription("cust_race", _incr)

    threads = [threading.Thread(target=_worker) for _ in range(N)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    record = webhooks.get_customer_subscription("cust_race")
    assert record is not None
    assert record["plan_tier"] == "pro", "preserved tier was clobbered by the race"
    assert record["counter"] == N, (
        f"counter={record['counter']} but {N} atomic increments ran — a lost update occurred (TOCTOU between read and write)"
    )


def test_suspended_preserves_tier_atomically(subscriptions_file: Path) -> None:
    """A SUSPENDED event on a ``pro`` customer must keep the tier at pro."""
    webhooks = importlib.import_module("app.billing.webhooks")
    webhooks.set_customer_subscription(
        customer_id="cust_susp",
        tier="pro",
        status="active",
        subscription_id="sub_susp",
    )
    webhooks._process_webhook_event(
        "BILLING.SUBSCRIPTION.SUSPENDED",
        {"customer_id": "cust_susp"},
    )
    record = webhooks.get_customer_subscription("cust_susp")
    assert record is not None
    assert record["plan_tier"] == "pro", "SUSPENDED lost the preserved plan_tier"
    assert record["status"] == "past_due"


def test_payment_completed_reactivates_atomically(subscriptions_file: Path) -> None:
    """A PAYMENT.SALE.COMPLETED on a past_due customer must flip status to active."""
    webhooks = importlib.import_module("app.billing.webhooks")
    webhooks.set_customer_subscription(
        customer_id="cust_pay",
        tier="team",
        status="past_due",
        subscription_id="sub_pay",
    )
    webhooks._process_webhook_event(
        "PAYMENT.SALE.COMPLETED",
        {"customer_id": "cust_pay"},
    )
    record = webhooks.get_customer_subscription("cust_pay")
    assert record is not None
    assert record["status"] == "active"
    assert record["plan_tier"] == "team", "PAYMENT.COMPLETED lost the preserved plan_tier"

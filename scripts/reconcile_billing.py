#!/usr/bin/env python3
"""Dodo Payments entitlement reconciliation (E2.4).

Walks the local subscription store and repairs entitlements against
the real Dodo API (statuses active/on_hold/cancelled per Dodo):

- active/trialing  → tier repaired to the product's plan, status active
- on_hold/past_due/failed/incomplete → status past_due (tier preserved)
- cancelled/expired/unpaid → downgraded to free/canceled
- API error / unknown subscription → record untouched, reported as error
  (an API outage must never mass-downgrade customers)

Configure with real credentials:

    DODO_PAYMENTS_API_KEY=... DODO_PAYMENTS_WEBHOOK_KEY=... \\
    DODO_PRODUCT_ID_STARTER=... DODO_PRODUCT_ID_PRO=... \\
    DODO_PRODUCT_ID_ENTERPRISE=... \\
    DATAFORGE_BILLING_SUBSCRIPTIONS_FILE=... \\
    python3 scripts/reconcile_billing.py [--json artifacts/billing/reconcile.json]

Exit code 0 when reconciliation ran with zero errors; 2 when skipped
(unconfigured); 1 when errors were reported.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

os.environ.setdefault("DATAFORGE_DOTENV_PATH", "/dev/null")
os.environ.setdefault("DATAFORGE_ENV", "test")
os.environ.setdefault("DATAFORGE_STORAGE_BACKEND", "sqlite")
os.environ.setdefault("DATAFORGE_SKIP_DB_CHECK", "true")

from app.billing.dodo import reconcile_entitlements


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json",
        type=Path,
        default=None,
        help="write the machine-readable report to this path",
    )
    args = parser.parse_args()

    print("Dodo Payments entitlement reconciliation")
    print("=" * 60)
    report = reconcile_entitlements()

    if report.get("skipped"):
        print(f"SKIPPED: {report['reason']}")
        return 2

    for key, label in (
        ("checked", "subscriptions checked"),
        ("repaired", "tiers repaired"),
        ("held", "marked past_due"),
        ("downgraded", "downgraded to free"),
        ("errors", "lookup errors (untouched)"),
    ):
        value = report[key]
        if isinstance(value, list):
            print(f"  {label}: {len(value)}")
            for customer_id in value:
                print(f"      {customer_id}")
        else:
            print(f"  {label}: {value}")

    if args.json is not None:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2) + "\n")
        print(f"report written to {args.json}")

    if report["errors"]:
        print(f"RECONCILE FAILED: {len(report['errors'])} lookup errors")
        return 1
    print("RECONCILE OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())

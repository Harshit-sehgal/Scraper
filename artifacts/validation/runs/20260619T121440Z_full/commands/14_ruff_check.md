# ruff_check

- status: failed
- command: `/usr/bin/python3 -m ruff check backend scripts`
- working_directory: `/home/harshit/Documents/Work/Money/scraper`
- start_time: 2026-06-19T12:19:30.385373+00:00
- end_time: 2026-06-19T12:19:30.413874+00:00
- duration_seconds: 0.03
- exit_code: 1
- timeout_seconds: 300
- required: true
- redaction_applied: true

## stdout

```text
I001 [*] Import block is un-sorted or un-formatted
  --> backend/app/billing/checkout.py:17:1
   |
15 |   """
16 |
17 | / from __future__ import annotations
18 | |
19 | | import logging
20 | | import os
21 | | import uuid
22 | | from typing import Annotated, Any, Literal
23 | |
24 | | from fastapi import APIRouter, Depends
25 | | from pydantic import BaseModel, Field, field_validator
26 | |
27 | | from app.utils.rbac import UserRole, require_role
28 | | from app.billing.service import (
29 | |     PayPalClient,
30 | |     get_paypal_client,
31 | | )
   | |_^
32 |
33 |   logger = logging.getLogger(__name__)
   |
help: Organize imports

PIE810 Call `startswith` once with a `tuple`
  --> backend/app/billing/checkout.py:51:17
   |
49 |     def _validate_urls(cls, value: str) -> str:
50 |         # Strict http(s) URLs only — no javascript:, data:, file: schemes.
51 |         if not (value.startswith("http://") or value.startswith("https://")):
   |                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
52 |             raise ValueError("URL must start with http:// or https://")
53 |         return value
   |
help: Merge into a single `startswith` call

EM101 Exception must not use a string literal, assign to variable first
  --> backend/app/billing/checkout.py:52:30
   |
50 |         # Strict http(s) URLs only — no javascript:, data:, file: schemes.
51 |         if not (value.startswith("http://") or value.startswith("https://")):
52 |             raise ValueError("URL must start with http:// or https://")
   |                              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
53 |         return value
   |
help: Assign to variable; remove string literal

RUF100 [*] Unused `noqa` directive (non-enabled: `SLF001`)
  --> backend/app/billing/checkout.py:77:37
   |
75 | ) -> dict[str, Any] | None:
76 |     """Create a PayPal Order via the paypalhttp SDK. Returns None on failure."""
77 |     if client._paypalhttp is None:  # noqa: SLF001 — internal SDK guard
   |                                     ^^^^^^^^^^^^^^
78 |         return None
79 |     try:
   |
help: Remove unused `noqa` directive

RUF100 [*] Unused `noqa` directive (non-enabled: `SLF001`)
   --> backend/app/billing/checkout.py:105:51
    |
103 |             }
104 |         )
105 |         result = client._client.execute(request)  # noqa: SLF001
    |                                                   ^^^^^^^^^^^^^^
106 |         order = getattr(result, "result", None) or getattr(result, "body", None)
107 |         if order is None:
    |
help: Remove unused `noqa` directive

PLR5501 [*] Use `elif` instead of `else` then `if`, to reduce indentation
   --> backend/app/billing/checkout.py:117:13
    |
115 |                       approval_url = link.get("href", "")
116 |                       break
117 | /             else:
118 | |                 if getattr(link, "rel", "") == "approve":
    | |________________^
119 |                       approval_url = getattr(link, "href", "")
120 |                       break
    |
help: Convert to `elif`

RUF022 [*] `__all__` is not sorted
   --> backend/app/billing/checkout.py:190:11
    |
190 | __all__ = ["router", "CheckoutRequest", "CheckoutResponse"]
    |           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |
help: Apply an isort-style sorting to `__all__`

S105 Possible hardcoded password assigned to: "_PAYPAL_CLIENT_SECRET_ENV"
  --> backend/app/billing/service.py:40:29
   |
39 | _PAYPAL_CLIENT_ID_ENV = "PAYPAL_CLIENT_ID"
40 | _PAYPAL_CLIENT_SECRET_ENV = [REDACTED]
   |                             ^^^^^^^^^^^^^^^^^^^^^^
41 | _PAYPAL_API_URL_ENV = "PAYPAL_API_URL"
42 | _PAYPAL_ENVIRONMENT_ENV = "PAYPAL_ENVIRONMENT"
   |

UP037 [*] Remove quotes from type annotation
  --> backend/app/billing/service.py:84:31
   |
82 | # unrecognised PayPal state falls back to ACTIVE — billing keeps paying
83 | # until the webhook explicitly cancels / suspends the subscription.
84 | _PAYPAL_STATUS_MAP: dict[str, "SubscriptionStatus"] = {
   |                               ^^^^^^^^^^^^^^^^^^^^
85 |     "active": SubscriptionStatus.ACTIVE,
86 |     "approval_pending": SubscriptionStatus.ACTIVE,
   |
help: Remove quotes

ARG002 Unused method argument: `customer_id`
   --> backend/app/billing/service.py:281:29
    |
279 |         return customer.plan_tier
280 |
281 |     def check_balance(self, customer_id: str, amount: int) -> bool:
    |                             ^^^^^^^^^^^
282 |         """Check whether a customer has remaining quota for ``amount`` of an event.
    |

ARG002 Unused method argument: `amount`
   --> backend/app/billing/service.py:281:47
    |
279 |         return customer.plan_tier
280 |
281 |     def check_balance(self, customer_id: str, amount: int) -> bool:
    |                                               ^^^^^^
282 |         """Check whether a customer has remaining quota for ``amount`` of an event.
    |

SIM102 Use a single `if` statement instead of nested `if` statements
   --> backend/app/billing/webhooks.py:374:5
    |
372 |               customer_id = v
373 |               break
374 | /     if not customer_id:
375 | |         # PayPal subscription id (I-...) lives on resource.id but only on
376 | |         # SUBSCRIPTION events. For PAYMENT.* events we use billing_id in
377 | |         # the resource (or fall back to empty).
378 | |         if isinstance(data, dict):
    | |__________________________________^
379 |               for key in ("billing_id", "subscription_id", "id"):
380 |                   v = data.get(key)
    |
help: Combine `if` statements using `and`

PLR1714 Consider merging multiple comparisons.
   --> backend/app/billing/webhooks.py:506:10
    |
504 |         logger.warning("Payment failed for customer=%s", customer_id)
505 |
506 |     elif event_type == "customer.created" or event_type == "CUSTOMER.CREATED":
    |          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
507 |         logger.info("Customer created: %s", customer_id)
    |
help: Merge multiple comparisons

I001 [*] Import block is un-sorted or un-formatted
  --> backend/app/main.py:8:1
   |
 6 |   """
 7 |
 8 | / from __future__ import annotations
 9 | |
10 | | import logging
11 | | from pathlib import Path
12 | |
13 | | from fastapi import FastAPI
14 | | from fastapi.middleware.cors import CORSMiddleware
15 | | from fastapi.staticfiles import StaticFiles
16 | | from starlette.middleware.base import BaseHTTPMiddleware
17 | |
18 | | from app import runtime_deps
19 | | from app.billing.webhooks import router as billing_webhook_router
20 | | from app.billing.checkout import router as billing_checkout_router
21 | | from app.config import settings
22 | | from app.globals import CONFIG, jobs_store, recycle_bin_store
23 | | from app.lifespan import (
24 | |     lifespan,
25 | |     persist_single_wrapper,
26 | |     persist_state_wrapper,
27 | |     run_job_wrapper,
28 | |     schedule_background_task,
29 | | )
30 | | from app.middlewares import (
31 | |     api_key_middleware,
32 | |     body_size_middleware,
33 | |     csp_report_only_middleware,
34 | |     latency_tracking_middleware,
35 | |     rate_limiter,
36 | |     security_headers_middleware,
37 | | )
38 | | from app.routers.auth_profiles import router as auth_profiles_router
39 | |
40 | | # NOTE: app.routers.experimental is intentionally NOT imported at module
41 | | # load time. It is imported lazily inside configure_routes() so that the
42 | | # research router module (and its transitive research imports) is never
43 | | # loaded at startup when ENABLE_EXPERIMENTAL_ROUTES is False.
44 | | from app.routers.exports import create_exports_router
45 | | from app.routers.health import router as health_router
46 | | from app.routers.intelligence import router as intelligence_router
47 | | from app.routers.jobs import create_jobs_router
48 | | from app.routers.operator import router as operator_router
49 | | from app.routers.scheduled_monitoring import router as scheduled_monitoring_router
50 | | from app.routers.scraper import router as scraper_router
51 | | from app.routers.session import router as session_router
52 | | from app.routers.system import router as system_router
53 | | from app.routers.user_data import router as user_data_router
54 | | from app.routers.workflow import draft_router as workflow_draft_router
55 | | from app.routers.workflow import router as workflow_router
56 | | from app.saas.router import router as saas_router
57 | | from app.services.job_runner import run_job
58 | | from app.storage_interface import get_job_repository
   | |____________________________________________________^
59 |
60 |   logger = logging.getLogger(__name__)
   |
help: Organize imports

I001 [*] Import block is un-sorted or un-formatted
   --> backend/tests/test_user_data.py:229:9
    |
227 |           coexist with the legacy Stripe/Autumn dialects.
228 |           """
229 | /         from fastapi.testclient import TestClient
230 | |
231 | |         from app.main import app
    | |________________________________^
232 |
233 |           with TestClient(app) as tc:
    |
help: Organize imports

Found 15 errors.
[*] 8 fixable with the `--fix` option (3 hidden fixes can be enabled with the `--unsafe-fixes` option).

```

## stderr

```text

```

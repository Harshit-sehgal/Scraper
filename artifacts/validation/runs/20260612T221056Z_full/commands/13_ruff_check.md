# ruff_check

- status: failed
- command: `/usr/bin/python3 -m ruff check backend scripts`
- working_directory: `/home/harshit/Documents/Work/Money/scraper`
- start_time: 2026-06-12T22:14:40.811630+00:00
- end_time: 2026-06-12T22:14:40.849843+00:00
- duration_seconds: 0.04
- exit_code: 1
- timeout_seconds: 300
- required: true
- redaction_applied: false

## stdout

```text
PIE794 Class field `auth_profile_id` is defined multiple times
   --> backend/app/models.py:427:5
    |
426 |     # Auth
427 |     auth_profile_id: str | None = Field(default=None, description="Optional auth profile for authenticated scraping")
    |     ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
428 |
429 |     # Status
    |
help: Remove duplicate field definition for `auth_profile_id`

F401 [*] `functools.lru_cache` imported but unused
  --> backend/app/plan_enforcer.py:17:23
   |
16 | import logging
17 | from functools import lru_cache
   |                       ^^^^^^^^^
18 | from typing import Any
   |
help: Remove unused import: `functools.lru_cache`

F401 [*] `app.utils.rbac.AuthContext` imported but unused
  --> backend/app/plan_enforcer.py:22:28
   |
20 | from fastapi import HTTPException, Request
21 |
22 | from app.utils.rbac import AuthContext, resolve_auth_context
   |                            ^^^^^^^^^^^
23 | from app.utils.usage_ledger import QuotaPeriod, UsageType, get_usage_ledger
   |
help: Remove unused import: `app.utils.rbac.AuthContext`

ARG001 Unused function argument: `user_id`
  --> backend/app/plan_enforcer.py:61:16
   |
61 | def _user_tier(user_id: str) -> str:
   |                ^^^^^^^
62 |     """Return the user's subscription tier.
   |

I001 [*] Import block is un-sorted or un-formatted
  --> backend/app/routers/jobs_write.py:10:1
   |
 8 |   """
 9 |
10 | / from __future__ import annotations
11 | |
12 | | import asyncio
13 | | import datetime
14 | | import logging
15 | | import re
16 | | from typing import TYPE_CHECKING, Annotated, Any
17 | |
18 | | from fastapi import APIRouter, Depends, HTTPException, Query, Request
19 | | from starlette.concurrency import run_in_threadpool
20 | |
21 | | from app.audit_logger import log_admin_action, log_job_event
22 | | from app.config import settings
23 | | from app.discovery import (
24 | |     DiscoveryDependencyError,
25 | |     discover_urls,
26 | |     infer_source_metadata,
27 | | )
28 | | from app.filters import process_results
29 | | from app.models import (
30 | |     DiscoveryRequest,
31 | |     Job,
32 | |     JobCreate,
33 | |     JobStatus,
34 | |     SchemaSuggestionRequest,
35 | |     ScrapeMode,
36 | | )
37 | | from app.routers.jobs_state import (
38 | |     JobStoreManager,
39 | |     canonical_request_fingerprint,
40 | |     lookup_idempotency_fingerprint,
41 | |     lookup_idempotency_key,
42 | |     record_idempotency_key,
43 | |     save_job,
44 | | )
45 | | from app.scraper import ai_clean_and_align_records
46 | | from app.storage_interface import get_job_repository
47 | | from app.utils.job import deduplicate_results, mark_job_canceled, normalize_job_results
48 | | from app.utils.quality import build_quality_report, compute_source_breakdown, safe_score
49 | | from app.utils.rbac import UserRole, get_current_user, require_role
50 | | from app.utils.usage_ledger import UsageType, get_usage_ledger
51 | | from app.plan_enforcer import require_plan_limit
   | |________________________________________________^
52 |
53 |   if TYPE_CHECKING:
   |
help: Organize imports

FAST002 FastAPI dependency without `Annotated`
   --> backend/app/routers/jobs_write.py:141:9
    |
139 |         request: Request,
140 |         _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR]))],
141 |         _plan_check: "dict[str, Any]" = Depends(require_plan_limit(UsageType.JOB_CREATED, quantity=1)),
    |         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
142 |     ):
143 |         # Extract user identity for data isolation
    |
help: Replace with `typing.Annotated`

UP037 [*] Remove quotes from type annotation
   --> backend/app/routers/jobs_write.py:141:22
    |
139 |         request: Request,
140 |         _role: Annotated[UserRole, Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR]))],
141 |         _plan_check: "dict[str, Any]" = Depends(require_plan_limit(UsageType.JOB_CREATED, quantity=1)),
    |                      ^^^^^^^^^^^^^^^^
142 |     ):
143 |         # Extract user identity for data isolation
    |
help: Remove quotes

Found 7 errors.
[*] 4 fixable with the `--fix` option (2 hidden fixes can be enabled with the `--unsafe-fixes` option).

```

## stderr

```text

```

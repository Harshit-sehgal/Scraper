# ruff_check

- status: failed
- command: `/usr/bin/python3 -m ruff check backend scripts`
- working_directory: `/home/harshit/Documents/Work/Money/scraper`
- start_time: 2026-06-12T16:24:10.707705+00:00
- end_time: 2026-06-12T16:24:10.744586+00:00
- duration_seconds: 0.04
- exit_code: 1
- timeout_seconds: 300
- required: true
- redaction_applied: true

## stdout

```text
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
19 | | from app.config import settings
20 | | from app.globals import CONFIG, jobs_store, recycle_bin_store
21 | | from app.lifespan import (
22 | |     lifespan,
23 | |     persist_single_wrapper,
24 | |     persist_state_wrapper,
25 | |     run_job_wrapper,
26 | |     schedule_background_task,
27 | | )
28 | | from app.middlewares import (
29 | |     api_key_middleware,
30 | |     body_size_middleware,
31 | |     csp_report_only_middleware,
32 | |     latency_tracking_middleware,
33 | |     rate_limiter,
34 | | )
35 | |
36 | | # NOTE: app.routers.experimental is intentionally NOT imported at module
37 | | # load time. It is imported lazily inside configure_routes() so that the
38 | | # research router module (and its transitive research imports) is never
39 | | # loaded at startup when ENABLE_EXPERIMENTAL_ROUTES is False.
40 | | from app.routers.exports import create_exports_router
41 | | from app.routers.health import router as health_router
42 | | from app.routers.jobs import create_jobs_router
43 | | from app.routers.operator import router as operator_router
44 | | from app.routers.intelligence import router as intelligence_router
45 | | from app.routers.scraper import router as scraper_router
46 | | from app.routers.auth_profiles import router as auth_profiles_router
47 | | from app.routers.scheduled_monitoring import router as scheduled_monitoring_router
48 | | from app.routers.workflow import router as workflow_router
49 | | from app.routers.session import router as session_router
50 | | from app.routers.system import router as system_router
51 | | from app.saas.router import router as saas_router
52 | | from app.services.job_runner import run_job
53 | | from app.storage_interface import get_job_repository
   | |____________________________________________________^
54 |
55 |   logger = logging.getLogger(__name__)
   |
help: Organize imports

EM101 Exception must not use a string literal, assign to variable first
   --> backend/app/models.py:365:30
    |
363 |     def validate_selector(cls, v: str) -> str:
364 |         if v and len(v) > 500:
365 |             raise ValueError("Selector must be at most 500 characters")
    |                              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
366 |         return v
    |
help: Assign to variable; remove string literal

EM101 Exception must not use a string literal, assign to variable first
   --> backend/app/models.py:421:30
    |
419 |     def validate_workflow(self):
420 |         if len(self.steps) > 100:
421 |             raise ValueError("Workflow cannot have more than 100 steps")
    |                              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
422 |         if len(self.search_params) > 50:
423 |             raise ValueError("search_params cannot have more than 50 keys")
    |
help: Assign to variable; remove string literal

EM101 Exception must not use a string literal, assign to variable first
   --> backend/app/models.py:423:30
    |
421 |             raise ValueError("Workflow cannot have more than 100 steps")
422 |         if len(self.search_params) > 50:
423 |             raise ValueError("search_params cannot have more than 50 keys")
    |                              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
424 |         return self
    |
help: Assign to variable; remove string literal

EM101 Exception must not use a string literal, assign to variable first
   --> backend/app/models.py:440:30
    |
438 |     def validate_create(self):
439 |         if not self.name or not self.name.strip():
440 |             raise ValueError("Workflow name is required")
    |                              ^^^^^^^^^^^^^^^^^^^^^^^^^^^
441 |         if len(self.steps) > 100:
442 |             raise ValueError("Workflow cannot have more than 100 steps")
    |
help: Assign to variable; remove string literal

EM101 Exception must not use a string literal, assign to variable first
   --> backend/app/models.py:442:30
    |
440 |             raise ValueError("Workflow name is required")
441 |         if len(self.steps) > 100:
442 |             raise ValueError("Workflow cannot have more than 100 steps")
    |                              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
443 |         if len(self.search_params) > 50:
444 |             raise ValueError("search_params cannot have more than 50 keys")
    |
help: Assign to variable; remove string literal

EM101 Exception must not use a string literal, assign to variable first
   --> backend/app/models.py:444:30
    |
442 |             raise ValueError("Workflow cannot have more than 100 steps")
443 |         if len(self.search_params) > 50:
444 |             raise ValueError("search_params cannot have more than 50 keys")
    |                              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
445 |         return self
    |
help: Assign to variable; remove string literal

F811 Redefinition of unused `AuthProfile` from line 469
   --> backend/app/models.py:566:7
    |
566 | class AuthProfile(BaseModel):
    |       ^^^^^^^^^^^ `AuthProfile` redefined here
567 |     """Authentication profile for scraping behind login walls."""
568 |     id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    |
   ::: backend/app/models.py:469:7
    |
469 | class AuthProfile(BaseModel):
    |       ----------- previous definition of `AuthProfile` here
470 |     """Stored browser session for authenticated scraping.
    |
help: Remove definition: `AuthProfile`

EM101 Exception must not use a string literal, assign to variable first
   --> backend/app/models.py:593:30
    |
591 |     def validate_create(self):
592 |         if not self.name or not self.name.strip():
593 |             raise ValueError("Auth profile name is required")
    |                              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
594 |         if not self.domain or not self.domain.strip():
595 |             raise ValueError("Domain is required")
    |
help: Assign to variable; remove string literal

EM101 Exception must not use a string literal, assign to variable first
   --> backend/app/models.py:595:30
    |
593 |             raise ValueError("Auth profile name is required")
594 |         if not self.domain or not self.domain.strip():
595 |             raise ValueError("Domain is required")
    |                              ^^^^^^^^^^^^^^^^^^^^
596 |         return self
    |
help: Assign to variable; remove string literal

I001 [*] Import block is un-sorted or un-formatted
  --> backend/app/routers/auth_profiles.py:9:1
   |
 7 |   """
 8 |
 9 | / from __future__ import annotations
10 | |
11 | | import datetime
12 | | import logging
13 | | from typing import Annotated, Any
14 | |
15 | | from fastapi import APIRouter, HTTPException, Depends
16 | |
17 | | from app.utils.rbac import UserRole, can_access_scoped_resource, require_principal
18 | | from app.models import AuthProfile, AuthProfileStatus
   | |_____________________________________________________^
19 |
20 |   logger = logging.getLogger(__name__)
   |
help: Organize imports

F401 [*] `app.models.AuthProfileStatus` imported but unused
  --> backend/app/routers/auth_profiles.py:18:37
   |
17 | from app.utils.rbac import UserRole, can_access_scoped_resource, require_principal
18 | from app.models import AuthProfile, AuthProfileStatus
   |                                     ^^^^^^^^^^^^^^^^^
19 |
20 | logger = logging.getLogger(__name__)
   |
help: Remove unused import: `app.models.AuthProfileStatus`

RET501 [*] Do not explicitly `return None` in function if it is the only possible return value
   --> backend/app/routers/auth_profiles.py:124:5
    |
122 |     del _auth_profiles[profile_id]
123 |     logger.info("Auth profile deleted: %s", profile_id)
124 |     return None
    |     ^^^^^^^^^^^
    |
help: Remove explicit `return None`

PLR1711 [*] Useless `return` statement at end of function
   --> backend/app/routers/auth_profiles.py:124:5
    |
122 |     del _auth_profiles[profile_id]
123 |     logger.info("Auth profile deleted: %s", profile_id)
124 |     return None
    |     ^^^^^^^^^^^
    |
help: Remove useless `return` statement

I001 [*] Import block is un-sorted or un-formatted
  --> backend/app/routers/scheduled_monitoring.py:8:1
   |
 6 |   """
 7 |
 8 | / from __future__ import annotations
 9 | |
10 | | import datetime
11 | | import logging
12 | | from typing import Annotated, Any
13 | |
14 | | from fastapi import APIRouter, HTTPException, Depends, Query
15 | |
16 | | from app.utils.rbac import UserRole, can_access_scoped_resource, require_principal
17 | | from app.models import ScheduledJob, ScheduledJobFrequency
   | |__________________________________________________________^
18 |
19 |   logger = logging.getLogger(__name__)
   |
help: Organize imports

FAST002 FastAPI dependency without `Annotated`
  --> backend/app/routers/scheduled_monitoring.py:83:5
   |
81 |     ],
82 |     enabled_only: bool = False,
83 |     limit: int = Query(20, ge=1, le=100),
   |     ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
84 |     offset: int = Query(0, ge=0),
85 | ):
   |
help: Replace with `typing.Annotated`

FAST002 FastAPI dependency without `Annotated`
  --> backend/app/routers/scheduled_monitoring.py:84:5
   |
82 |     enabled_only: bool = False,
83 |     limit: int = Query(20, ge=1, le=100),
84 |     offset: int = Query(0, ge=0),
   |     ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
85 | ):
86 |     """List scheduled jobs with optional filtering."""
   |
help: Replace with `typing.Annotated`

RET501 [*] Do not explicitly `return None` in function if it is the only possible return value
   --> backend/app/routers/scheduled_monitoring.py:141:5
    |
139 |     del _scheduled_jobs[job_id]
140 |     logger.info("Scheduled job deleted: %s", job_id)
141 |     return None
    |     ^^^^^^^^^^^
    |
help: Remove explicit `return None`

PLR1711 [*] Useless `return` statement at end of function
   --> backend/app/routers/scheduled_monitoring.py:141:5
    |
139 |     del _scheduled_jobs[job_id]
140 |     logger.info("Scheduled job deleted: %s", job_id)
141 |     return None
    |     ^^^^^^^^^^^
    |
help: Remove useless `return` statement

I001 [*] Import block is un-sorted or un-formatted
  --> backend/app/routers/workflow.py:7:1
   |
 5 |   """
 6 |
 7 | / from __future__ import annotations
 8 | |
 9 | | import datetime
10 | | import logging
11 | | import uuid
12 | | from typing import Annotated, Any
13 | |
14 | | from fastapi import APIRouter, HTTPException, Depends, Query
15 | |
16 | | from app.utils.rbac import UserRole, can_access_scoped_resource, require_principal
17 | | from app.models import (
18 | |     Workflow,
19 | |     WorkflowCreate,
20 | |     WorkflowUpdate,
21 | |     WorkflowStatus,
22 | | )
   | |_^
23 |
24 |   logger = logging.getLogger(__name__)
   |
help: Organize imports

FAST002 FastAPI dependency without `Annotated`
   --> backend/app/routers/workflow.py:100:5
    |
 98 |     status: str | None = None,
 99 |     domain: str | None = None,
100 |     limit: int = Query(20, ge=1, le=100),
    |     ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
101 |     offset: int = Query(0, ge=0),
102 | ):
    |
help: Replace with `typing.Annotated`

FAST002 FastAPI dependency without `Annotated`
   --> backend/app/routers/workflow.py:101:5
    |
 99 |     domain: str | None = None,
100 |     limit: int = Query(20, ge=1, le=100),
101 |     offset: int = Query(0, ge=0),
    |     ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
102 | ):
103 |     """List workflows with optional filtering.
    |
help: Replace with `typing.Annotated`

RET501 [*] Do not explicitly `return None` in function if it is the only possible return value
   --> backend/app/routers/workflow.py:173:5
    |
171 |     del _workflows[workflow_id]
172 |     logger.info("Workflow deleted: %s", workflow_id)
173 |     return None
    |     ^^^^^^^^^^^
    |
help: Remove explicit `return None`

PLR1711 [*] Useless `return` statement at end of function
   --> backend/app/routers/workflow.py:173:5
    |
171 |     del _workflows[workflow_id]
172 |     logger.info("Workflow deleted: %s", workflow_id)
173 |     return None
    |     ^^^^^^^^^^^
    |
help: Remove useless `return` statement

I001 [*] Import block is un-sorted or un-formatted
  --> backend/app/saas/router.py:11:1
   |
 9 |   """
10 |
11 | / from __future__ import annotations
12 | |
13 | | import logging
14 | | from typing import Annotated
15 | |
16 | | from fastapi import APIRouter, Depends, HTTPException
17 | | from pydantic import BaseModel, Field
18 | |
19 | | from app.audit_logger import log_job_event
20 | | from app.saas.identity_store import get_identity_store, IdentityStoreError
21 | | from app.utils.rbac import UserRole, require_role_with_user
22 | |
23 | | # Models & services
24 | | from app.saas.models import (
25 | |     User,
26 | |     UserStatus,
27 | |     Organization,
28 | |     Membership,
29 | |     MembershipRole,
30 | |     Project,
31 | | )
32 | | from app.saas.service import SignupService
   | |__________________________________________^
33 |
34 |   logger = logging.getLogger(__name__)
   |
help: Organize imports

F401 [*] `app.saas.models.User` imported but unused
  --> backend/app/saas/router.py:25:5
   |
23 | # Models & services
24 | from app.saas.models import (
25 |     User,
   |     ^^^^
26 |     UserStatus,
27 |     Organization,
   |
help: Remove unused import

F401 [*] `app.saas.models.UserStatus` imported but unused
  --> backend/app/saas/router.py:26:5
   |
24 | from app.saas.models import (
25 |     User,
26 |     UserStatus,
   |     ^^^^^^^^^^
27 |     Organization,
28 |     Membership,
   |
help: Remove unused import

SLOT000 Subclasses of `str` should define `__slots__`
   --> backend/app/saas/router.py:586:7
    |
584 | # ═══════════════════════════════════════════════════════════════════════
585 |
586 | class PlanTier(str):
    |       ^^^^^^^^
587 |     """Subscription plan tiers."""
    |

ARG001 Unused function argument: `auth`
   --> backend/app/saas/router.py:608:5
    |
606 | @router.get("/plan", response_model=PlanInfoResponse)
607 | async def get_plan_info(
608 |     auth: Annotated[
    |     ^^^^
609 |         tuple[UserRole, str],
610 |         Depends(require_role_with_user([UserRole.ADMIN, UserRole.OPERATOR, UserRole.USER])),
    |

COM812 [*] Trailing comma missing
  --> backend/app/url_analyzer.py:98:6
   |
96 |         "referrer",
97 |         "redirect",
98 |     }
   |      ^
99 | )
   |
help: Add trailing comma

COM812 [*] Trailing comma missing
   --> backend/app/url_analyzer.py:118:6
    |
116 |         "go",
117 |         "goto",
118 |     }
    |      ^
119 | )
    |
help: Add trailing comma

COM812 [*] Trailing comma missing
   --> backend/app/url_analyzer.py:133:6
    |
131 |         "search-results",
132 |         "search",
133 |     }
    |      ^
134 | )
    |
help: Add trailing comma

COM812 [*] Trailing comma missing
   --> backend/app/url_analyzer.py:182:6
    |
180 |         ".eot",
181 |         ".otf",
182 |     }
    |      ^
183 | )
    |
help: Add trailing comma

COM812 [*] Trailing comma missing
   --> backend/app/url_analyzer.py:204:6
    |
202 |         "/authorize",
203 |         "/authorize/",
204 |     }
    |      ^
205 | )
    |
help: Add trailing comma

COM812 [*] Trailing comma missing
   --> backend/app/url_analyzer.py:228:6
    |
226 |         "/public-api/",
227 |         "/api-gateway/",
228 |     }
    |      ^
229 | )
    |
help: Add trailing comma

COM812 [*] Trailing comma missing
   --> backend/app/url_analyzer.py:240:6
    |
238 |         "svc.",
239 |         "service.",
240 |     }
    |      ^
241 | )
    |
help: Add trailing comma

ARG001 Unused function argument: `session_signals`
   --> backend/app/url_analyzer.py:351:5
    |
349 | def _recommend_mode(
350 |     classification: UrlClassification,
351 |     session_signals: [REDACTED]
    |     ^^^^^^^^^^^^^^^
352 |     pagination_signals: dict,
353 |     is_login: bool,
    |

ARG001 Unused function argument: `pagination_signals`
   --> backend/app/url_analyzer.py:352:5
    |
350 |     classification: UrlClassification,
351 |     session_signals: [REDACTED]
352 |     pagination_signals: dict,
    |     ^^^^^^^^^^^^^^^^^^
353 |     is_login: bool,
354 |     is_download: bool,
    |

COM812 [*] Trailing comma missing
   --> backend/app/url_analyzer.py:366:68
    |
364 |     if is_download:
365 |         return ScrapingMode.NOT_RECOMMENDED, [
366 |             "This URL points to a file download, not an HTML page."
    |                                                                    ^
367 |         ]
    |
help: Add trailing comma

F841 Local variable `parsed` is assigned to but never used
   --> backend/app/url_analyzer.py:478:5
    |
476 |         )
477 |
478 |     parsed = urlparse(url)
    |     ^^^^^^
479 |
480 |     # --- Heuristic extraction ------------------------------------------------
    |
help: Remove assignment to unused variable `parsed`

ARG001 Unused function argument: `headless`
  --> backend/app/workflow_executor.py:20:48
   |
20 | async def execute_workflow(workflow: Workflow, headless: bool = True) -> dict[str, Any]:
   |                                                ^^^^^^^^
21 |     """Execute a workflow and return extraction results.
   |

I001 [*] Import block is un-sorted or un-formatted
 --> backend/tests/test_auth_profiles.py:3:1
  |
1 |   """Tests for the Auth Profiles router."""
2 |
3 | / import pytest
4 | | from fastapi.testclient import TestClient
5 | |
6 | | from app.models import AuthProfile, AuthProfileStatus
  | |_____________________________________________________^
  |
help: Organize imports

F401 [*] `pytest` imported but unused
 --> backend/tests/test_auth_profiles.py:3:8
  |
1 | """Tests for the Auth Profiles router."""
2 |
3 | import pytest
  |        ^^^^^^
4 | from fastapi.testclient import TestClient
  |
help: Remove unused import: `pytest`

I001 [*] Import block is un-sorted or un-formatted
  --> backend/tests/test_saas_router.py:10:5
   |
 8 |   def reset_identity_store_fixture():
 9 |       """Reset the identity store before each SaaS router test."""
10 | /     from app.saas.identity_store import reset_identity_store, SQLiteIdentityStore
11 | |     import tempfile
12 | |     import os
   | |_____________^
13 |
14 |       with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
   |
help: Organize imports

I001 [*] Import block is un-sorted or un-formatted
 --> backend/tests/test_scheduled_monitoring.py:3:1
  |
1 |   """Tests for the Scheduled Monitoring router."""
2 |
3 | / import pytest
4 | | from fastapi.testclient import TestClient
5 | |
6 | | from app.models import ScheduledJob, ScheduledJobFrequency
  | |__________________________________________________________^
  |
help: Organize imports

F401 [*] `pytest` imported but unused
 --> backend/tests/test_scheduled_monitoring.py:3:8
  |
1 | """Tests for the Scheduled Monitoring router."""
2 |
3 | import pytest
  |        ^^^^^^
4 | from fastapi.testclient import TestClient
  |
help: Remove unused import: `pytest`

I001 [*] Import block is un-sorted or un-formatted
  --> backend/tests/test_url_analyzer.py:2:1
   |
 2 | / from app.url_analyzer import (
 3 | |     UrlClassification,
 4 | |     ScrapingMode,
 5 | |     analyze_url,
 6 | |     _detect_session_signals,
 7 | |     _detect_pagination_signals,
 8 | |     _detect_login_path,
 9 | |     _detect_file_download,
10 | |     _detect_api_endpoint,
11 | |     _has_infinite_scroll_keywords,
12 | |     _recommend_mode,
13 | | )
   | |_^
   |
help: Organize imports

COM812 [*] Trailing comma missing
   --> backend/tests/test_url_analyzer.py:156:77
    |
154 |     def test_download_recommends_not_recommended(self):
155 |         mode, steps = _recommend_mode(
156 |             UrlClassification.FILE_DOWNLOAD_PAGE, {}, {}, False, True, False
    |                                                                             ^
157 |         )
158 |         assert mode == ScrapingMode.NOT_RECOMMENDED
    |
help: Add trailing comma

COM812 [*] Trailing comma missing
   --> backend/tests/test_url_analyzer.py:162:78
    |
160 |     def test_login_recommends_auth_profile(self):
161 |         mode, steps = _recommend_mode(
162 |             UrlClassification.LOGIN_REQUIRED_PAGE, {}, {}, True, False, False
    |                                                                              ^
163 |         )
164 |         assert mode == ScrapingMode.AUTH_PROFILE
    |
help: Add trailing comma

COM812 [*] Trailing comma missing
   --> backend/tests/test_url_analyzer.py:168:102
    |
166 |     def test_session_bound_recommends_workflow_replay(self):
167 |         mode, steps = _recommend_mode(
168 |             UrlClassification.SESSION_BOUND_URL, {"has_session_param": True}, {}, False, False, False
    |                                                                                                      ^
169 |         )
170 |         assert mode == ScrapingMode.WORKFLOW_REPLAY
    |
help: Add trailing comma

COM812 [*] Trailing comma missing
   --> backend/tests/test_url_analyzer.py:174:78
    |
172 |     def test_normal_page_recommends_direct_scrape(self):
173 |         mode, steps = _recommend_mode(
174 |             UrlClassification.NORMAL_STATIC_PAGE, {}, {}, False, False, False
    |                                                                              ^
175 |         )
176 |         assert mode == ScrapingMode.DIRECT_SCRAPE
    |
help: Add trailing comma

COM812 [*] Trailing comma missing
   --> backend/tests/test_url_analyzer.py:180:82
    |
178 |     def test_api_recommends_direct_scrape(self):
179 |         mode, steps = _recommend_mode(
180 |             UrlClassification.NETWORK_API_BACKED_PAGE, {}, {}, False, False, True
    |                                                                                  ^
181 |         )
182 |         assert mode == ScrapingMode.DIRECT_SCRAPE
    |
help: Add trailing comma

I001 [*] Import block is un-sorted or un-formatted
  --> backend/tests/test_workflow.py:3:1
   |
 1 |   """Tests for the Workflow router and models."""
 2 |
 3 | / import pytest
 4 | | from fastapi.testclient import TestClient
 5 | |
 6 | | from app.models import (
 7 | |     Workflow,
 8 | |     WorkflowCreate,
 9 | |     WorkflowUpdate,
10 | |     WorkflowStatus,
11 | |     WorkflowStep,
12 | |     WorkflowStepType,
13 | |     WorkflowPaginationConfig,
14 | | )
   | |_^
   |
help: Organize imports

Found 53 errors.
[*] 34 fixable with the `--fix` option (13 hidden fixes can be enabled with the `--unsafe-fixes` option).

```

## stderr

```text

```

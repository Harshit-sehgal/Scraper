# ruff_check

- status: failed
- command: `/usr/bin/python3 -m ruff check backend scripts`
- working_directory: `/home/harshit/Documents/Work/Money/scraper`
- start_time: 2026-06-12T18:48:13.675405+00:00
- end_time: 2026-06-12T18:48:13.731841+00:00
- duration_seconds: 0.06
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
48 | | from app.routers.workflow import draft_router as workflow_draft_router
49 | | from app.routers.workflow import router as workflow_router
50 | | from app.routers.session import router as session_router
51 | | from app.routers.system import router as system_router
52 | | from app.saas.router import router as saas_router
53 | | from app.services.job_runner import run_job
54 | | from app.storage_interface import get_job_repository
   | |____________________________________________________^
55 |
56 |   logger = logging.getLogger(__name__)
   |
help: Organize imports

EM101 Exception must not use a string literal, assign to variable first
   --> backend/app/models.py:375:30
    |
373 |     def validate_selector(cls, v: str) -> str:
374 |         if v and len(v) > 500:
375 |             raise ValueError("Selector must be at most 500 characters")
    |                              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
376 |         return v
    |
help: Assign to variable; remove string literal

EM101 Exception must not use a string literal, assign to variable first
   --> backend/app/models.py:434:30
    |
432 |     def validate_workflow(self):
433 |         if len(self.steps) > 100:
434 |             raise ValueError("Workflow cannot have more than 100 steps")
    |                              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
435 |         if len(self.search_params) > 50:
436 |             raise ValueError("search_params cannot have more than 50 keys")
    |
help: Assign to variable; remove string literal

EM101 Exception must not use a string literal, assign to variable first
   --> backend/app/models.py:436:30
    |
434 |             raise ValueError("Workflow cannot have more than 100 steps")
435 |         if len(self.search_params) > 50:
436 |             raise ValueError("search_params cannot have more than 50 keys")
    |                              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
437 |         return self
    |
help: Assign to variable; remove string literal

EM101 Exception must not use a string literal, assign to variable first
   --> backend/app/models.py:455:30
    |
453 |     def validate_create(self):
454 |         if not self.name or not self.name.strip():
455 |             raise ValueError("Workflow name is required")
    |                              ^^^^^^^^^^^^^^^^^^^^^^^^^^^
456 |         if len(self.steps) > 100:
457 |             raise ValueError("Workflow cannot have more than 100 steps")
    |
help: Assign to variable; remove string literal

EM101 Exception must not use a string literal, assign to variable first
   --> backend/app/models.py:457:30
    |
455 |             raise ValueError("Workflow name is required")
456 |         if len(self.steps) > 100:
457 |             raise ValueError("Workflow cannot have more than 100 steps")
    |                              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
458 |         if len(self.search_params) > 50:
459 |             raise ValueError("search_params cannot have more than 50 keys")
    |
help: Assign to variable; remove string literal

EM101 Exception must not use a string literal, assign to variable first
   --> backend/app/models.py:459:30
    |
457 |             raise ValueError("Workflow cannot have more than 100 steps")
458 |         if len(self.search_params) > 50:
459 |             raise ValueError("search_params cannot have more than 50 keys")
    |                              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
460 |         return self
    |
help: Assign to variable; remove string literal

F811 Redefinition of unused `AuthProfile` from line 486
   --> backend/app/models.py:583:7
    |
583 | class AuthProfile(BaseModel):
    |       ^^^^^^^^^^^ `AuthProfile` redefined here
584 |     """Authentication profile for scraping behind login walls."""
585 |     id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    |
   ::: backend/app/models.py:486:7
    |
486 | class AuthProfile(BaseModel):
    |       ----------- previous definition of `AuthProfile` here
487 |     """Stored browser session for authenticated scraping.
    |
help: Remove definition: `AuthProfile`

EM101 Exception must not use a string literal, assign to variable first
   --> backend/app/models.py:610:30
    |
608 |     def validate_create(self):
609 |         if not self.name or not self.name.strip():
610 |             raise ValueError("Auth profile name is required")
    |                              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
611 |         if not self.domain or not self.domain.strip():
612 |             raise ValueError("Domain is required")
    |
help: Assign to variable; remove string literal

EM101 Exception must not use a string literal, assign to variable first
   --> backend/app/models.py:612:30
    |
610 |             raise ValueError("Auth profile name is required")
611 |         if not self.domain or not self.domain.strip():
612 |             raise ValueError("Domain is required")
    |                              ^^^^^^^^^^^^^^^^^^^^
613 |         return self
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
10 | | import json
11 | | import logging
12 | | import os
13 | | from pathlib import Path
14 | | import uuid
15 | | from typing import Annotated, Any
16 | |
17 | | from fastapi import APIRouter, HTTPException, Depends, Query
18 | | from pydantic import BaseModel, Field
19 | |
20 | | from app.models import SchemaField, WorkflowStep
21 | | from app.services.workflow_runner import (
22 | |     detect_fields_from_html,
23 | |     preview_workflow_snapshot,
24 | |     steps_from_manual_mapping,
25 | | )
26 | | from app.url_analyzer import analyze_url as analyze_guided_url
27 | | from app.url_safety import validate_public_http_url
28 | | from app.utils.rbac import UserRole, can_access_scoped_resource, require_principal
29 | | from app.models import (
30 | |     Workflow,
31 | |     WorkflowCreate,
32 | |     WorkflowUpdate,
33 | |     WorkflowStatus,
34 | | )
   | |_^
35 |
36 |   logger = logging.getLogger(__name__)
   |
help: Organize imports

F401 [*] `app.models.WorkflowStep` imported but unused
  --> backend/app/routers/workflow.py:20:37
   |
18 | from pydantic import BaseModel, Field
19 |
20 | from app.models import SchemaField, WorkflowStep
   |                                     ^^^^^^^^^^^^
21 | from app.services.workflow_runner import (
22 |     detect_fields_from_html,
   |
help: Remove unused import: `app.models.WorkflowStep`

FAST002 FastAPI dependency without `Annotated`
   --> backend/app/routers/workflow.py:302:5
    |
300 |     status: str | None = None,
301 |     domain: str | None = None,
302 |     limit: int = Query(20, ge=1, le=100),
    |     ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
303 |     offset: int = Query(0, ge=0),
304 | ):
    |
help: Replace with `typing.Annotated`

FAST002 FastAPI dependency without `Annotated`
   --> backend/app/routers/workflow.py:303:5
    |
301 |     domain: str | None = None,
302 |     limit: int = Query(20, ge=1, le=100),
303 |     offset: int = Query(0, ge=0),
    |     ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
304 | ):
305 |     """List workflows with optional filtering.
    |
help: Replace with `typing.Annotated`

RET501 [*] Do not explicitly `return None` in function if it is the only possible return value
   --> backend/app/routers/workflow.py:390:5
    |
388 |     _persist_workflows()
389 |     logger.info("Workflow deleted: %s", workflow_id)
390 |     return None
    |     ^^^^^^^^^^^
    |
help: Remove explicit `return None`

PLR1711 [*] Useless `return` statement at end of function
   --> backend/app/routers/workflow.py:390:5
    |
388 |     _persist_workflows()
389 |     logger.info("Workflow deleted: %s", workflow_id)
390 |     return None
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

SIM102 Use a single `if` statement instead of nested `if` statements
  --> backend/app/services/workflow_runner.py:90:9
   |
88 |           if tag == "button" and control_type not in {"submit", "button"}:
89 |               continue
90 | /         if tag == "input" and control_type in {"hidden", "submit", "button", "reset", "image"}:
91 | |             if control_type not in {"submit", "button"}:
   | |________________________________________________________^
92 |                   continue
   |
help: Combine `if` statements using `and`

COM812 [*] Trailing comma missing
   --> backend/app/services/workflow_runner.py:115:14
    |
113 |                 "evidence": evidence,
114 |                 "possible_values": possible_values,
115 |             }
    |              ^
116 |         )
117 |     return fields
    |
help: Add trailing comma

COM812 [*] Trailing comma missing
   --> backend/app/services/workflow_runner.py:133:10
    |
131 |             description="Open stable workflow start URL",
132 |             order=0,
133 |         )
    |          ^
134 |     ]
135 |     for field in fields:
    |
help: Add trailing comma

COM812 [*] Trailing comma missing
   --> backend/app/services/workflow_runner.py:154:14
    |
152 |                 description=f"{step_type.value} {label}",
153 |                 order=len(steps),
154 |             )
    |              ^
155 |         )
156 |     if submit_action:
    |
help: Add trailing comma

COM812 [*] Trailing comma missing
   --> backend/app/services/workflow_runner.py:164:14
    |
162 |                 description="Submit workflow form",
163 |                 order=len(steps),
164 |             )
    |              ^
165 |         )
166 |     steps.append(
    |
help: Add trailing comma

COM812 [*] Trailing comma missing
   --> backend/app/services/workflow_runner.py:172:10
    |
170 |             description="Bounded wait after submit",
171 |             order=len(steps),
172 |         )
    |          ^
173 |     )
174 |     return steps
    |
help: Add trailing comma

COM812 [*] Trailing comma missing
   --> backend/app/url_analyzer.py:103:6
    |
101 |         "transactionid",
102 |         "bookingsession",
103 |     }
    |      ^
104 | )
    |
help: Add trailing comma

COM812 [*] Trailing comma missing
   --> backend/app/url_analyzer.py:126:6
    |
124 |         "go",
125 |         "goto",
126 |     }
    |      ^
127 | )
    |
help: Add trailing comma

COM812 [*] Trailing comma missing
   --> backend/app/url_analyzer.py:141:6
    |
139 |         "search-results",
140 |         "search",
141 |     }
    |      ^
142 | )
    |
help: Add trailing comma

COM812 [*] Trailing comma missing
   --> backend/app/url_analyzer.py:190:6
    |
188 |         ".eot",
189 |         ".otf",
190 |     }
    |      ^
191 | )
    |
help: Add trailing comma

COM812 [*] Trailing comma missing
   --> backend/app/url_analyzer.py:212:6
    |
210 |         "/authorize",
211 |         "/authorize/",
212 |     }
    |      ^
213 | )
    |
help: Add trailing comma

COM812 [*] Trailing comma missing
   --> backend/app/url_analyzer.py:236:6
    |
234 |         "/public-api/",
235 |         "/api-gateway/",
236 |     }
    |      ^
237 | )
    |
help: Add trailing comma

COM812 [*] Trailing comma missing
   --> backend/app/url_analyzer.py:248:6
    |
246 |         "svc.",
247 |         "service.",
248 |     }
    |      ^
249 | )
    |
help: Add trailing comma

COM812 [*] Trailing comma missing
   --> backend/app/url_analyzer.py:418:18
    |
416 |                     "reason": reason,
417 |                     "requires_confirmation": True,
418 |                 }
    |                  ^
419 |             )
    |
help: Add trailing comma

ARG001 Unused function argument: `session_signals`
   --> backend/app/url_analyzer.py:444:5
    |
442 | def _recommend_mode(
443 |     classification: UrlClassification,
444 |     session_signals: [REDACTED]
    |     ^^^^^^^^^^^^^^^
445 |     pagination_signals: dict,
446 |     is_login: bool,
    |

ARG001 Unused function argument: `pagination_signals`
   --> backend/app/url_analyzer.py:445:5
    |
443 |     classification: UrlClassification,
444 |     session_signals: [REDACTED]
445 |     pagination_signals: dict,
    |     ^^^^^^^^^^^^^^^^^^
446 |     is_login: bool,
447 |     is_download: bool,
    |

COM812 [*] Trailing comma missing
   --> backend/app/url_analyzer.py:459:68
    |
457 |     if is_download:
458 |         return ScrapingMode.MANUAL_REVIEW_REQUIRED, [
459 |             "This URL points to a file download, not an HTML page."
    |                                                                    ^
460 |         ]
    |
help: Add trailing comma

COM812 [*] Trailing comma missing
   --> backend/app/url_analyzer.py:565:22
    |
563 |                         "confidence": 1.0,
564 |                         "evidence": "URL safety validation rejected this target.",
565 |                     }
    |                      ^
566 |                 ],
567 |                 "risk_level": "blocked",
    |
help: Add trailing comma

COM812 [*] Trailing comma missing
   --> backend/app/url_analyzer.py:581:14
    |
579 |                 "confidence": self.confidence,
580 |                 "evidence": self.reason,
581 |             }
    |              ^
582 |         ]
583 |         session_signals = [REDACTED] {}) if isinstance(self.signals, dict) else {}
    |
help: Add trailing comma

F841 Local variable `parsed` is assigned to but never used
   --> backend/app/url_analyzer.py:650:5
    |
648 |         )
649 |
650 |     parsed = urlparse(url)
    |     ^^^^^^
651 |
652 |     # --- Heuristic extraction ------------------------------------------------
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
 6 | |     redact_sensitive_url,
 7 | |     suggested_start_urls,
 8 | |     _detect_session_signals,
 9 | |     _detect_pagination_signals,
10 | |     _detect_login_path,
11 | |     _detect_file_download,
12 | |     _detect_api_endpoint,
13 | |     _has_infinite_scroll_keywords,
14 | |     _recommend_mode,
15 | | )
   | |_^
   |
help: Organize imports

COM812 [*] Trailing comma missing
   --> backend/tests/test_url_analyzer.py:164:77
    |
162 |     def test_download_recommends_not_recommended(self):
163 |         mode, steps = _recommend_mode(
164 |             UrlClassification.FILE_DOWNLOAD_PAGE, {}, {}, False, True, False
    |                                                                             ^
165 |         )
166 |         assert mode == ScrapingMode.MANUAL_REVIEW_REQUIRED
    |
help: Add trailing comma

COM812 [*] Trailing comma missing
   --> backend/tests/test_url_analyzer.py:170:78
    |
168 |     def test_login_recommends_auth_profile(self):
169 |         mode, steps = _recommend_mode(
170 |             UrlClassification.LOGIN_REQUIRED_PAGE, {}, {}, True, False, False
    |                                                                              ^
171 |         )
172 |         assert mode == ScrapingMode.AUTH_PROFILE
    |
help: Add trailing comma

COM812 [*] Trailing comma missing
   --> backend/tests/test_url_analyzer.py:176:102
    |
174 |     def test_session_bound_recommends_workflow_replay(self):
175 |         mode, steps = _recommend_mode(
176 |             UrlClassification.SESSION_BOUND_URL, {"has_session_param": True}, {}, False, False, False
    |                                                                                                      ^
177 |         )
178 |         assert mode == ScrapingMode.WORKFLOW_REPLAY
    |
help: Add trailing comma

COM812 [*] Trailing comma missing
   --> backend/tests/test_url_analyzer.py:182:78
    |
180 |     def test_normal_page_recommends_direct_scrape(self):
181 |         mode, steps = _recommend_mode(
182 |             UrlClassification.NORMAL_STATIC_PAGE, {}, {}, False, False, False
    |                                                                              ^
183 |         )
184 |         assert mode == ScrapingMode.DIRECT_SCRAPE
    |
help: Add trailing comma

COM812 [*] Trailing comma missing
   --> backend/tests/test_url_analyzer.py:188:82
    |
186 |     def test_api_recommends_direct_scrape(self):
187 |         mode, steps = _recommend_mode(
188 |             UrlClassification.NETWORK_API_BACKED_PAGE, {}, {}, False, False, True
    |                                                                                  ^
189 |         )
190 |         assert mode == ScrapingMode.DIRECT_SCRAPE
    |
help: Add trailing comma

COM812 [*] Trailing comma missing
   --> backend/tests/test_url_analyzer.py:291:74
    |
289 |     def test_redact_sensitive_url_preserves_non_sensitive_params(self):
290 |         redacted, applied = redact_sensitive_url(
291 |             "https://example.com/path?token=[REDACTED]
    |                                                                          ^
292 |         )
293 |         assert applied is True
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

Found 64 errors.
[*] 44 fixable with the `--fix` option (13 hidden fixes can be enabled with the `--unsafe-fixes` option).

```

## stderr

```text

```

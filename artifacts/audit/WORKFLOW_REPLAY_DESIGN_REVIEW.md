# Workflow Replay Design Review

Date: 2026-06-12

## Scope

Prompt 9 requires Workflow Replay for session/search/form URLs. The safe
approach is to recreate a legitimate user action from a stable start URL:
open the start page, fill user-provided fields, submit normally, preview
the resulting page, extract a sample, and save a reusable workflow.

This review records reusable code, Prompt 9 implementation decisions,
and remaining gaps after the Workflow Replay foundation work.

## Existing Reusable Pieces

### URL Intelligence

- `backend/app/url_analyzer.py` detects session-bound URLs, redacts
  temporary parameter values, and suggests stable start URLs.
- `POST /api/url/analyze` returns the Prompt 8 guided response.
- `POST /api/workflow-drafts/from-url-analysis` creates a lightweight
  draft entry from URL analysis.

### Workflow Model And Router

- `backend/app/models.py` already defines `Workflow`, `WorkflowCreate`,
  `WorkflowUpdate`, `WorkflowStep`, and `WorkflowPaginationConfig`.
- `backend/app/routers/workflow.py` already exposes workflow CRUD,
  preview, and run endpoints.
- Current workflow storage is an in-process dictionary. Prompt 9 adds
  basic JSON persistence for workflow definitions, but full repository
  parity remains a later storage task.
- Current workflow routes use `require_principal` and
  `can_access_scoped_resource` for owner/org/project checks.

### Form Detection

- `backend/app/search_form_recovery.py` exposes `_detect_search_form`,
  `_build_absolute_url`, and `_map_search_params_to_fields`.
- These functions use BeautifulSoup and are safe for local HTML
  fixtures.

### Selector And Extraction Utilities

- `backend/app/selector_discovery.py` exposes field discovery for fetched
  pages, but it is intentionally large and not refactored in this phase.
- Prompt 9 uses a small workflow-specific detector for form fields rather
  than modifying selector discovery.

### Browser/Playwright

- Existing scraper paths use Playwright/browser support elsewhere in the
  app.
- `backend/app/workflow_executor.py` remains a legacy placeholder, but
  Prompt 9 workflow preview routes now use
  `backend/app/services/workflow_runner.py`.
- The Prompt 9 runner executes local HTML snapshots for deterministic
  tests and can be extended to full Playwright execution.

## Implemented In Prompt 9

- Field detection endpoint for workflow drafts, using local HTML
  snapshots.
- Manual mapping endpoint that converts corrected form fields into
  workflow steps.
- Bounded workflow preview that returns sample rows, timeline, warnings,
  and friendly failure details.
- PATCH alias for workflow update.
- Workflow status values for `paused` and `failed`.
- Step actions for `goto`, `check`, `uncheck`, `press`,
  `wait_for_url`, `wait_for_selector`, `wait_for_text`, and
  `wait_for_timeout_limited`.
- Best-effort JSON persistence for workflow definitions.
- Frontend Workflow Builder draft handoff panel.

## Remaining After Prompt 9

- Live Playwright browser automation from arbitrary start URLs is not
  wired into route preview/run behavior.
- Field detection is verified for local HTML snapshots, not live pages.
- Screenshots are returned as `null`.
- SQLite/Postgres workflow repository parity is not complete.
- Frontend detect/preview/save/run controls are visible but not fully
  interactive.

## Implementation Direction

- Keep route handlers thin and put replay logic in
  `backend/app/services/workflow_runner.py`.
- Use local HTML snapshot execution for deterministic tests and safe
  fixture preview.
- Bound all waits and return friendly failures instead of raising raw
  browser or selector errors.
- Redact sensitive workflow values in responses and logs.
- Preserve current workflow CRUD behavior and add only focused Prompt 9
  endpoints.
- Do not implement CAPTCHA bypass, anti-bot bypass, login bypass,
  session ID brute force, token forging, raw cookie paste, paywall
  bypass, or private/internal network scraping.

## Deferred

- Full Playwright browser automation for arbitrary live sites remains
  behind the runner boundary and should be expanded with browser-marked
  tests.
- SQLite/Postgres workflow repository parity is not complete in this
  phase.
- Full frontend Workflow Builder polish is limited by existing UI
  structure; Prompt 9 adds backend/API and minimal guided entry support.

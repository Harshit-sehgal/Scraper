# Workflow Replay

Current status: Prompt 9 foundation implemented in the current checkout.

## Purpose

Workflow Replay is the guided path for session, search-result, and
form-based websites where saving the final result URL is brittle. The
safe approach is to start from a stable public page, use user-provided
field values, submit the form normally, and extract a bounded preview
from the resulting page.

This feature must not brute-force session identifiers, forge tokens,
bypass login, bypass CAPTCHA or anti-bot systems, bypass paywalls, or
accept raw cookie dumps.

## Backend APIs

Implemented routes:

```text
POST /api/workflow-drafts/from-url-analysis
POST /api/workflow-drafts/{draft_id}/detect-fields
POST /api/workflow-drafts/{draft_id}/manual-mapping
POST /api/workflows
GET /api/workflows
GET /api/workflows/{workflow_id}
PUT /api/workflows/{workflow_id}
PATCH /api/workflows/{workflow_id}
DELETE /api/workflows/{workflow_id}
POST /api/workflows/{workflow_id}/preview
POST /api/workflows/{workflow_id}/run
```

## Model

The `Workflow` model now includes the Prompt 9 fields needed for the
replay foundation:

- `mode`, defaulting to `workflow_replay`
- `original_url`
- `start_url`
- `search_params`
- `steps`
- `extraction_schema`
- `pagination_config`
- `auth_profile_id`
- `version`
- `status`
- `created_at`, `updated_at`, `last_run_at`, `last_success_at`,
  `last_failure_reason`
- `user_id`, `org_id`, `project_id`

Supported step actions include:

```text
goto
fill
select
check
uncheck
click
press
wait_for_url
wait_for_selector
wait_for_text
wait_for_timeout_limited
extract
```

All waits added by the manual mapping helper are bounded. The snapshot
runner caps `wait_for_timeout_limited` at 10 seconds.

## Field Detection

`POST /api/workflow-drafts/{draft_id}/detect-fields` currently detects
fields from a supplied local HTML snapshot. It identifies:

- text/search/date inputs
- selects and options
- checkboxes/radio inputs
- textarea fields
- submit buttons

Returned field data includes:

- `label`
- `selector`
- `type`
- `required_guess`
- `confidence`
- `evidence`
- `possible_values`

Signals include `label[for]`, placeholders, names/ids, ARIA labels,
input types, required attributes, select options, and submit controls.

## Manual Mapping

`POST /api/workflow-drafts/{draft_id}/manual-mapping` converts corrected
field mappings into saved workflow steps:

```json
{
  "fields": [
    {
      "label": "Keyword",
      "selector": "#q",
      "value": "laptops",
      "action": "fill"
    }
  ],
  "submit_action": {
    "action": "click",
    "selector": "#submit"
  }
}
```

The route validates the selected start URL with the existing URL safety
policy before saving any workflow.

## Preview

`POST /api/workflows/{workflow_id}/preview` runs a deterministic local
HTML snapshot preview through `backend/app/services/workflow_runner.py`.
It returns:

- `preview_status`
- `sample_rows`
- `timeline`
- `warnings`
- `failure_type` and friendly failure data when a selector is missing
- `last_url`
- `page_title`
- `screenshot`, currently `null`

Sensitive step values are redacted in the timeline when the label,
description, or selector looks like password/token/session/cookie/auth
material.

## Frontend

The New Job URL Analyzer can create a Workflow Replay draft from URL
Intelligence. A Workflow Builder draft panel now shows:

- start URL confirmation
- redacted original URL
- detected reason
- detected fields area
- manual mapping JSON area
- preview area
- step timeline
- disabled save/run controls until the full interactive flow is wired

## Storage And Access Control

Workflow CRUD routes stamp `user_id`, `org_id`, and `project_id` from the
central auth context and filter/check access before list/get/update/delete
/preview/run. Draft routes also stamp the auth context and use the same
scope helper for draft mutation endpoints.

Workflow definitions are persisted best-effort to
`backend/data/workflows.json` or `DATAFORGE_WORKFLOW_STORE_FILE` when
configured. This is not a database migration and does not yet provide
Postgres parity.

## Verified Tests

Prompt 9 targeted tests:

```text
PYTHONPATH=backend python3 -m pytest backend/tests/test_workflow.py -q
npm run test -- frontend/js/analyzer.test.js
```

At implementation time:

- `backend/tests/test_workflow.py`: 25 passed
- `frontend/js/analyzer.test.js`: 26 passed

## Remaining Gaps

- Full live Playwright navigation from a start URL is not wired into the
  route yet.
- Field detection is verified for local HTML snapshots, not arbitrary
  live pages.
- Preview executes a deterministic snapshot runner, not a full browser
  replay.
- Screenshots are returned as `null`.
- Postgres workflow persistence and migrations are not implemented.
- Frontend builder controls are visible but full detect/preview/save/run
  interactivity is not fully wired.

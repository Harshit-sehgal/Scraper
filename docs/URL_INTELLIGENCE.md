# URL Intelligence

Current status: implemented for Prompt 8 in the current checkout.

## Purpose

URL Intelligence gives users a no-fetch first pass before they start a
scrape. It classifies the pasted URL, flags temporary/session-like URL
parameters, applies URL safety validation, and recommends one of the
guided entry modes.

## Backend

Primary endpoint:

```text
POST /api/url/analyze
```

Request:

```json
{
  "url": "https://example.com/search/results?sessionId=abc123",
  "fetch_preview": false
}
```

With `fetch_preview=false`, the endpoint does not fetch the target page.
It validates the URL with the existing SSRF/domain safety policy and then
returns:

- `safe_to_fetch`
- `classifications`
- `risk_level`
- `recommended_mode`
- `user_message`
- `technical_findings`
- `suggested_start_urls`
- `next_steps`
- `redactions_applied`

With `fetch_preview=true`, the older field-discovery path still runs and
adds guided URL intelligence under `url_intelligence`.

Legacy compatibility endpoint:

```text
GET /api/intelligence/analyze-url?url=...
```

This route now returns the same guided response shape after URL safety
validation.

## Classifications

Implemented URL-only classifications include:

- `normal_static_page`
- `search_result_page`
- `session_bound_url`
- `login_required_page`
- `pagination_page`
- `infinite_scroll_page`
- `load_more_page`
- `network_api_backed_page`
- `file_download_page`
- `blocked_or_challenge_page`
- `empty_or_low_data_page`
- `unsafe_url`
- `unknown`

Page-content classifications are only heuristic unless
`fetch_preview=true` is used.

## Modes

Supported recommendations:

- `direct_scrape`
- `workflow_replay_recommended`
- `auth_profile_recommended`
- `manual_review_required`
- `blocked_or_unsafe`
- `unknown`

## Session URL Detection

The session-bound detector checks explicit temporary/session parameter
names such as `sessionId`, `session_id`, `sid`, `jsessionid`,
`searchId`, `resultId`, `requestId`, `token`, `authToken`, `flowId`,
`state`, `nonce`, `conversationId`, `transactionId`, and
`bookingSession`.

Generic `id` is intentionally not treated as session-bound by itself.

Sensitive values are redacted in responses. Example:

```text
abc123xyz789 -> abc1...x789
```

## Suggested Start URLs

For a URL like:

```text
https://example.com/search/results?sessionId=abc123
```

the analyzer suggests stable start URLs:

```text
https://example.com/search
https://example.com/
```

Suggestions include confidence and require user confirmation.

## Frontend

The existing New Job URL Analyzer panel renders the guided response:

- Normal URL: Direct Scrape action.
- Session URL: Try Direct Scrape Once and Create Reliable Workflow.
- Login-looking URL: Auth Profile recommendation.
- Unsafe URL: blocked state with no continue action.

The panel can create a workflow draft through:

```text
POST /api/workflow-drafts/from-url-analysis
```

Prompt 9 adds fixture-backed field detection, manual mapping, bounded
snapshot preview, timeline output, and a visible frontend Workflow
Builder draft panel. Full live Playwright navigation from arbitrary
start URLs remains a documented Workflow Replay gap; see
`docs/WORKFLOW_REPLAY.md`.

## Evidence

Prompt 8 targeted tests:

```text
PYTHONPATH=backend python3 -m pytest backend/tests/test_url_analyzer.py -q
npm run test -- frontend/js/analyzer.test.js
```

At implementation time both targeted commands passed.

Prompt 9 follow-up evidence:

```text
PYTHONPATH=backend python3 -m pytest backend/tests/test_workflow.py -q
npm run test -- frontend/js/analyzer.test.js
```

At Prompt 9 implementation time, the backend Workflow tests passed with
25 tests and the frontend analyzer tests passed with 26 tests.

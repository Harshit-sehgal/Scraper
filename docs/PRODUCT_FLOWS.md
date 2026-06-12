# Product Flows

Current status: Prompt 8 implemented URL Intelligence and guided scrape
entry. Prompt 9 added the tested Workflow Replay foundation for draft
creation, fixture-backed field detection, manual mapping, bounded
snapshot preview, and timeline/failure responses.

## Guided URL Entry

1. User opens New Job and pastes a URL.
2. Frontend sends `POST /api/url/analyze` with `fetch_preview=false`.
3. Backend validates the URL with the existing safety policy.
4. Backend returns classifications, risk, recommended mode, safe start
   URL suggestions, and redacted technical findings.
5. Frontend renders the URL Intelligence panel and mode-specific actions.

## Direct Scrape

Used when the URL appears to be a normal public page.

Current behavior:

- The panel recommends `direct_scrape`.
- The Direct Scrape action fills the existing manual URL list.
- Existing job creation and URL safety checks still apply when the job
  is submitted.

## Session/Search URL

Used when the URL contains temporary/session-like parameters or appears
to be a brittle result page.

Current behavior:

- The panel recommends `workflow_replay_recommended`.
- Temporary values are redacted before display.
- Stable start URL suggestions are shown through the API response.
- The Create Reliable Workflow action creates a draft entry with:
  - redacted `original_url`
  - `recommended_start_urls`
  - `selected_start_url`
  - `detected_reason`
  - `initial_mode = workflow_replay`

Prompt 9 implemented:

- field detection from a local HTML snapshot
- manual mapping to bounded workflow steps
- saved draft workflow creation
- deterministic preview against a supplied HTML snapshot
- timeline/sample/friendly failure responses
- sensitive step value redaction

Still not implemented:

- live Playwright navigation from arbitrary start URLs
- screenshot capture during preview
- Postgres workflow persistence/migrations
- fully interactive frontend detect/preview/save/run controls

## Login-Looking URL

Used when the URL path looks like login/auth/SSO.

Current behavior:

- The panel recommends `auth_profile_recommended`.
- Auth Profile setup is not fully wired into this flow yet.

## Unsafe URL

Used when URL safety validation rejects the target, such as loopback,
internal hostnames, unsafe IPs, internal TLDs, unsupported schemes, or
admin denylisted domains.

Current behavior:

- The API returns `safe_to_fetch=false`.
- The panel recommends `blocked_or_unsafe`.
- The continue action is disabled.

## Safety Boundary

These flows do not implement CAPTCHA bypass, anti-bot bypass, paywall
bypass, login bypass, session ID brute forcing, token forging, private
network scraping, or raw cookie dumping.

## Workflow Replay Preview

Current backend preview flow:

1. User creates a draft from URL Intelligence.
2. User confirms or overrides the stable start URL.
3. Backend detects fields from an HTML snapshot.
4. User-provided mapping is converted into `goto`, field action,
   submit, and bounded wait steps.
5. Backend preview executes those steps against the snapshot and returns
   sample rows, timeline, warnings, or friendly failure details.

See `docs/WORKFLOW_REPLAY.md` for endpoint details and current gaps.

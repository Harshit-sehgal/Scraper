# DataForge Scraper - Implementation Plan

Date: 2026-06-12
Scope: planning only; no implementation fixes were made in Prompt 2.

## Phase 1: P0 Safety Fixes

- **goal:** Close verified auth, tenant-isolation, export, workflow, auth-profile, schedule, and SaaS route-policy gaps.
- **why it matters:** These are the paths most likely to leak tenant data or mutate SaaS state incorrectly.
- **tasks:** Add failing P0 tests first; fix export ownership checks; tenant-scope workflows, auth profiles, and scheduled monitoring; resolve SaaS mutation route policy; verify storage ownership parity.
- **files likely involved:** `backend/app/routers/exports.py`, `backend/app/routers/workflow.py`, `backend/app/routers/auth_profiles.py`, `backend/app/routers/scheduled_monitoring.py`, `backend/app/saas/router.py`, `backend/app/utils/rbac.py`, storage repositories, P0 tests.
- **tests:** Cross-org export/workflow/auth-profile/schedule tests; route-auth matrix; SQLite/Postgres ownership parity; existing P0 auth, billing, quota tests.
- **acceptance criteria:** All verified P0 issue tests fail before fixes, pass after fixes, and full targeted P0 suite exits 0.
- **do-not-do warnings:** Do not add inline auth checks that bypass `resolve_auth_context`; do not weaken route protection; do not add scraping bypass behavior.

## Phase 2: Reproducible Validation/CI

- **goal:** Make backend, frontend, static, and docs validation reproducible from a clean checkout.
- **why it matters:** Product work is unsafe if the baseline stays red or depends on local assumptions.
- **tasks:** Fix full backend pytest failures; add missing local ASGI client methods; mock external Telegram sends in tests; clean ruff/pyflakes; format frontend CSS; document `python3` baseline; optionally add a single validation runner.
- **files likely involved:** `backend/tests/conftest.py`, failing backend tests, notifier tests, linted backend files, `frontend/styles.css`, validation docs.
- **tests:** `python3 -m pytest backend/tests -q`, ruff, pyflakes, `npm run test`, `npm run lint:js`.
- **acceptance criteria:** All required validation commands exit 0 and evidence is recorded in `docs/AGENT_TRUTH.md` or `artifacts/audit/VALIDATION_REPORT.md`.
- **do-not-do warnings:** Do not delete failing tests to get green output; do not claim CI success without current logs.

## Phase 3: URL Intelligence + Direct/Workflow Mode Foundation

- **goal:** Give users a truthful decision layer before they run extraction.
- **why it matters:** The product should guide users toward direct scraping for simple public pages and workflow replay for dynamic/session-bound pages.
- **tasks:** Harden URL classification; detect session parameters, login-like pages, search pages, pagination, and network/API candidates; expose direct/workflow mode recommendation in frontend; keep unsafe targets blocked.
- **files likely involved:** URL analyzer, session URL detector, URL safety utilities, intelligence router, frontend analyzer UI.
- **tests:** URL classifier fixtures, safety-deny cases, frontend rendering tests, API contract tests.
- **acceptance criteria:** A pasted URL returns mode, confidence, safety warnings, and explicit next action without overclaiming.
- **do-not-do warnings:** Do not bypass robots/auth/CAPTCHA/paywalls; do not treat session-token URLs as stable.

## Phase 4: Workflow Replay System

- **goal:** Persist, preview, and replay user-confirmed browser steps.
- **why it matters:** Dynamic and search-driven sites need repeatable workflows instead of brittle one-off URLs.
- **tasks:** Build tenant-scoped workflow persistence; implement bounded step replay; add preview/dry-run; support search params, manual mappings, and workflow versions.
- **files likely involved:** workflow router/service/storage, Playwright runner, models, frontend workflow builder.
- **tests:** Workflow CRUD isolation, replay fixture tests, preview tests, versioning tests.
- **acceptance criteria:** A user can save, preview, run, and version a workflow without exposing another tenant's workflow.
- **do-not-do warnings:** Do not mix experimental research code into stable routes; do not execute unbounded browser actions.

## Phase 5: Auth Profiles

- **goal:** Safely support user-provided login sessions for lawful targets.
- **why it matters:** Many legitimate extraction workflows require a user to log into their own account, but session material is highly sensitive.
- **tasks:** Consolidate AuthProfile models; encrypt storage state; tenant-scope CRUD; add manual login flow; detect expiry; integrate profiles with workflow/job execution.
- **files likely involved:** auth profile router/service/models, encryption utilities, Playwright login flow, job/workflow execution.
- **tests:** Encryption/non-exposure tests, cross-tenant profile tests, expiry detection fixtures, job integration tests.
- **acceptance criteria:** Tokens/cookies are encrypted, never returned, domain-scoped, tenant-scoped, and removable.
- **do-not-do warnings:** Do not store raw cookies/tokens in logs or responses; do not build login bypass or CAPTCHA bypass.

## Phase 6: Real-World Extraction Depth

- **goal:** Support pagination, infinite scroll, load-more controls, and public network/API extraction.
- **why it matters:** Real user pages rarely fit one static HTML fetch.
- **tasks:** Add bounded pagination strategies; implement scroll/load-more loops; capture public XHR/fetch responses with redaction; record step timeline and screenshots.
- **files likely involved:** scraper, pagination service, network capture, workflow executor, artifact storage, frontend result view.
- **tests:** Fixture pages for pagination/scroll/load-more/network JSON, cap/timeout tests, redaction tests.
- **acceptance criteria:** Extraction depth increases while remaining bounded, observable, and lawful.
- **do-not-do warnings:** Do not capture or log authorization headers, cookies, tokens, or private API data.

## Phase 7: Data Quality Layer

- **goal:** Turn raw extraction into validated, useful structured data.
- **why it matters:** SaaS value comes from reliable outputs, not merely scraped text.
- **tasks:** Build schema builder; cleaning rules; duplicate detection; quality score; failure explanations.
- **files likely involved:** schema models, cleaning engine, quality utilities, exports, frontend schema/result UI.
- **tests:** Field validation, cleaning, dedupe, quality scoring, failure classifier tests.
- **acceptance criteria:** Each completed job exposes clean data, validation errors, duplicate stats, and quality score.
- **do-not-do warnings:** Do not silently discard user data without reporting it.

## Phase 8: SaaS Foundation

- **goal:** Complete workspace, project, team, API key, metering, billing, audit, and retention foundations.
- **why it matters:** The product cannot be SaaS-ready without identity, isolation, billing, and lifecycle controls.
- **tasks:** Harden org/project/team membership; project API keys; usage metering/enforcement; billing enforcement; audit log reads; data retention/delete flows.
- **files likely involved:** `backend/app/saas`, RBAC, usage ledger, billing, audit logger, recycle bin/results storage, frontend dashboard.
- **tests:** Membership isolation, key scope, quota/billing, audit log isolation, retention/delete tests.
- **acceptance criteria:** Every SaaS resource is tenant-scoped and every billable action is metered/enforced.
- **do-not-do warnings:** Do not add admin all-access without explicit tests; do not expose audit/usage data across tenants.

## Phase 9: Benchmarks And Production Readiness

- **goal:** Prove the system is ready for a target deployment environment.
- **why it matters:** Production readiness is operational evidence, not a document claim.
- **tasks:** Build lawful benchmark corpus; run load and browser E2E tests; verify staging deployment, TLS, secrets, backups, restore drill, monitoring, alerts, and incident runbooks.
- **files likely involved:** benchmark scripts/fixtures, CI config, deployment docs, monitoring/alerting docs, operations runbooks.
- **tests:** Benchmark suite, Playwright E2E, load tests, restore drill, alert delivery drill.
- **acceptance criteria:** Current logs prove readiness gates pass in the target environment.
- **do-not-do warnings:** Do not call the project production-ready or 100/100 SaaS-ready without current deployment evidence.

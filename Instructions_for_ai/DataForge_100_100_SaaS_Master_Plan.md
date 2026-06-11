# DataForge Scraper - 100/100 SaaS Readiness Master Plan

**Prepared for:** Harshit Sehgal
**Prepared on:** 2026-06-09
**Repository inspected:** `/mnt/data/Scraper-main(18).zip`, extracted to `/mnt/data/scraper_analysis/Scraper-main`
**Purpose:** Give a coding agent a low-hallucination, step-by-step plan to turn the current project into a serious SaaS product.

---

## 1. Important honesty note about the request for 10,000+ issues

You asked for all issues and said the list may be in the thousands, minimum 10k. I will not fake 10,000 verified bugs. That would be dangerous for Codex/OpenCode because it would send the agent chasing invented problems.

What I can honestly provide is:

1. **42 verified issues** from the existing inspected backlog.
2. **2428 static issue candidates** extracted from actual repository lines. These are real code/doc locations, but each still needs human/agent verification before being called a bug.
3. A **10,070-row SaaS readiness work-item matrix**. This is not a list of confirmed bugs. It is a structured audit/remediation checklist across 100 components x 100 SaaS risk categories. It lets an agent systematically find and fix the thousands of real issues that usually appear when converting a pre-production prototype into a production SaaS.

This is the correct way to reach 100/100 without hallucination.

Generated supporting files:

- `DataForge_Static_Issue_Candidates.csv` - actual static candidates from repo lines.
- `DataForge_10000_SaaS_Readiness_Work_Items.csv` - 10,000 structured audit/remediation tasks.
- `DataForge_Issue_Backlog.csv` - verified issue backlog already prepared earlier.

---

## 2. Current project status

**Current maturity estimate:** **55/100**
**Target:** **100/100 SaaS-ready product**
**Classification:** advanced pre-production prototype / internal platform, not public SaaS yet.

| Area | Current estimate | 100/100 target | Gate to upgrade |
|---|---:|---:|---|
| Product clarity | 70/100 | 100/100 | ICP, use cases, pricing, onboarding, paid beta evidence |
| Core extraction value | 60/100 | 100/100 | Labeled benchmark corpus, quality score, source lineage, repeatability |
| Backend architecture | 65/100 | 100/100 | App DI, small services, stable API contracts, multi-instance safety |
| Test reliability | 35/100 | 100/100 | Unit tests isolated, full suite green, timeout guards, CI tiers |
| Security/compliance | 45/100 | 100/100 | Multi-tenant authZ, SSRF/egress hardening, AUP, retention/deletion |
| Operations/deployment | 30/100 | 100/100 | Docker/Compose/cloud deploy proven, backup/restore drill, SLO alerts |
| Frontend/UX | 40/100 | 100/100 | Real SaaS UI, onboarding, project/results workflows, accessibility |
| Billing/business | 10/100 | 100/100 | Plans, metering, quotas, payment, support workflows |
| Documentation truth | 60/100 | 100/100 | Docs generated/verified by commands, stable vs experimental split |
| Overall readiness | 55/100 | 100/100 | All P0/P1 closed, beta users succeed, production drills pass |

### Plain verdict

The project has real engineering depth: FastAPI, Playwright, storage, exports, tests, metrics, docs, and many experimental modules. But a 100/100 SaaS product needs more than code volume. It needs trustworthy tests, stable API contracts, tenant isolation, billing, security, supportability, legal boundaries, onboarding, production deployment evidence, and paid-user validation.

The immediate target is not to add more experimental intelligence. The target is to make the stable core reliable, measurable, secure, and sellable.

---

## 3. What 100/100 means for this project

A 100/100 DataForge product should be:

1. **Useful:** a clear target user can extract data faster and more reliably than with manual scripts.
2. **Honest:** docs, marketing, API behavior, and runtime behavior match.
3. **Reliable:** jobs have bounded timeouts, retries, cancellation, idempotency, and recovery.
4. **Secure:** no tenant data leaks, no SSRF/egress holes, no unsafe dashboard exposure, no leaked secrets.
5. **Compliant:** acceptable-use policy, robots/domain controls, retention/deletion, audit logs, and no anti-bot overclaiming.
6. **Observable:** every job has traceable steps, logs, metrics, failure class, and support diagnostics.
7. **Scalable:** workers, browser sessions, storage, exports, queues, and rate limits scale by plan and tenant.
8. **Chargeable:** usage metering, plan limits, billing, invoices, support, and customer success flows exist.
9. **Maintainable:** large monoliths are reduced behind tested interfaces.
10. **Agent-safe:** coding agents can make small changes without trusting stale docs or rewriting huge modules blindly.

---

## 4. Product definition for SaaS readiness

### Recommended v1 positioning

**DataForge Scraper should be positioned as:**

> A controlled web data extraction platform for teams that need repeatable extraction from accessible websites, with schema-guided jobs, quality scoring, exports, monitoring, and safe operational controls.

### Avoid these claims

Do not claim:

- universal extraction from every website;
- guaranteed anti-bot bypass;
- legal permission to scrape all sites;
- fully autonomous extraction without review;
- production readiness before deployment/security/load/restore evidence exists.

### Recommended first customer segment

Pick one first; do not target everyone.

Best initial candidates:

1. **Small agencies** managing repeated public-data extraction for clients.
2. **Growth/SEO teams** needing monitored extraction from known public pages.
3. **Research/data teams** needing repeatable exports and quality checks.
4. **Internal ops teams** scraping their own/partner-accessible pages.

For v1, avoid high-risk targets like bypassing login walls, marketplaces with heavy anti-bot rules, financial trading data, medical/personal data, or protected content.

---

## 5. Verified issues that must be solved

These are the verified issues from the existing backlog. They are the starting point. A coding agent should treat P0 and P1 items as blockers before public SaaS work.

| ID | Severity | Area | Issue | First action |
|---|---|---|---|---|
| A1 | P0 | Tests | Router closures bypass monkeypatched test scheduler/runner | Refactor app dependency injection |
| A2 | P0 | Tests | Full test suite not verified green; timed run hangs/slows | Add timeouts and split test tiers |
| B1 | P0 | Concurrency | Sync lock held across await in restore | Remove await under manager.lock |
| A3 | P1 | Tooling | Ruff/mypy/bandit/frontend tests not run in sandbox | Add bootstrap/doctor command |
| C1 | P1 | Docs/API | API docs only lint with experimental routes | Split stable/experimental docs |
| C3 | P1 | Docs | CODE_REVIEW_BUGS.md is stale | Replace with verified status table |
| C4 | P1 | Deploy | Env copy docs conflict with Compose file | Standardize .env.production |
| D1 | P1 | API | Idempotency fingerprint incomplete | Hash full validated request |
| D2 | P1 | Jobs | run_job is too large and coupled | Characterize then extract services |
| E1 | P1 | Exports | Batch exports still memory-heavy | Implement true streaming/chunked export |
| F1 | P1 | Storage | Migration path not production-proven | Add versioned migration fixtures/tests |
| F2 | P1 | State | Repository vs memory source-of-truth unclear | Document and enforce production state model |
| G1 | P1 | Security | Production secrets placeholders must fail clearly | Add secret generator and startup checks |
| G2 | P1 | Auth | Dashboard auth not public-SaaS-ready | Choose SSO/internal or session auth |
| G3 | P1 | SSRF | Need network-level egress hardening | Add deploy/network controls and tests |
| I1 | P1 | Quality | Current benchmark pass not verified | Build reproducible benchmark corpus |
| J1 | P1 | Deploy | Docker/Compose not verified | Run container smoke in Docker env |
| J2 | P1 | Ops | Backup/restore not proven | Run staging restore drill |
| K1 | P1 | Docs | Status docs mix historical/current/future claims | Create generated current status doc |
| K2 | P1 | Product | Core vs research boundary can be misunderstood | Add feature tier table |
| L1 | P1 | Maintainability | Large monoliths create high change risk | Strangler refactor with tests |
| B2 | P1 | Lifecycle | Bulk clear can partially fail | Add transactional/per-job semantics |
| B3 | P1 | State | Multi-instance consistency not proven | Add shared-DB multi-app tests |
| C2 | P2 | Docs | Route counts inconsistent | Generate route inventory docs |
| C5 | P2 | Auth | CSP route intent ambiguous | Decide public vs protected route |
| E2 | P2 | Exports | Batch export missing/empty semantics unclear | Add export manifest/statuses |
| G4 | P2 | Compliance | Anti-bot/stealth language risk | Rewrite claims and add compliance checklist |
| H1 | P2 | Frontend | Frontend tests not run from ZIP | Run npm ci/lint/test/e2e |
| H2 | P2 | Frontend | Experimental UI visible beside stable UI | Gate experimental UI |
| H3 | P2 | Frontend | Vendored deps need update path | Add version/hash/update process |
| I2 | P2 | Acquisition | Auto acquisition needs quality gates | Fake-provider tests and metrics |
| I3 | P2 | Extraction | Selector/orchestrator functions too large | Extract and test components |
| J3 | P2 | Ops | Incident runbook placeholders | Replace/remove fake contacts |
| L2 | P2 | Cleanup | TODO/placeholder surface large | Generate and classify TODO inventory |
| B4 | P2 | Lifecycle | Log executor shutdown unclear | Own executor in lifespan and close |
| M1 | P0 | Tests/Network | API/unit tests can hang on real DNS lookup in URL safety validation | Inject/mock DNS resolver and make tests DNS-independent |
| M2 | P1 | API/Performance | Synchronous socket.getaddrinfo runs inside an async request handler | Move DNS validation off the event loop and add bounded timeout/cache |
| M3 | P1 | CI/Test Config | Main SQLite full-suite CI command has no per-test timeout | Configure pytest-timeout globally for full-suite jobs |
| M4 | P1 | Dependencies/Tooling | pyproject optional dev dependencies are out of sync with requirements-dev and CI | Pick one source of truth and regenerate dependency docs/locks |
| M5 | P1 | Docs/Auth Tooling | Generated route auth matrix gives environment-incomplete /metrics guidance | Make route_auth_matrix environment-aware for metrics/docs routes |
| M6 | P1 | Test Data | API tests use live-looking external URLs without isolating URL safety resolution | Replace live DNS-dependent URL fixtures with deterministic fixtures |
| M7 | P2 | Frontend Tooling | Frontend syntax check can be mistaken for full frontend test validation | Separate frontend syntax, unit, lint, and e2e status in docs |

---

## 6. Static issue candidates found from actual repository lines

These are not all confirmed bugs. They are grep/static-analysis candidates that need triage. The supporting CSV has file, line, evidence, category, and first action.

| Candidate category | Count |
|---|---:|
| Async path audit | 1773 |
| Blocking/wait strategy audit | 66 |
| Concurrency/lock audit | 47 |
| DNS/network isolation | 9 |
| Exception handling audit | 334 |
| General static candidate | 24 |
| Placeholder/deployment truth audit | 169 |
| TODO/publish-blocker audit | 6 |

### How to triage static candidates safely

For each candidate:

1. Open the exact file and line.
2. Decide if it is production code, test code, docs, fixture, or archived material.
3. Decide whether it is intentional, false positive, real bug, tech debt, or docs cleanup.
4. If real, create a ticket with severity and acceptance criteria.
5. If false positive, add a clear suppression or note so future scans do not keep reporting it.
6. If docs-only, decide whether it affects product truth.

Never bulk-fix static candidates blindly. Especially avoid mass-changing exception handlers, sleeps, locks, or placeholder references without understanding context.

---

## 7. Highest-priority remediation sequence

### Step 1: make tests deterministic

**Problem:** API/unit tests can perform real DNS resolution and hang. Router dependencies may bypass monkeypatches. Full suite is not proven green.

**Do:**

1. Introduce injected runtime dependencies in app factory.
2. Replace post-import monkeypatch reliance with test app factory dependencies.
3. Add fake DNS resolver for unit/API tests.
4. Mark true live-network tests as `integration` or `network`.
5. Add pytest-timeout globally.
6. Split test commands into fast unit, API contract, browser, postgres, integration, benchmark.

**Why:** Without deterministic tests, every coding-agent change is risky and unverifiable.

### Step 2: fix async/concurrency safety

**Problem:** blocking DNS in async routes and sync locks across await can freeze the app under load.

**Do:**

1. Move DNS resolution to bounded thread pool or async resolver.
2. Add resolver cache with safe TTL and DNS rebinding protections.
3. Replace problematic sync lock paths with async-safe architecture or split critical section before await.
4. Add concurrency tests with simultaneous create/cancel/restore/export.

**Why:** SaaS reliability depends on bounded runtime and no event-loop blockage.

### Step 3: stabilize API and docs truth

**Problem:** docs match experimental route mode but default app has fewer routes. Status docs mix historical/current/future claims.

**Do:**

1. Generate stable API docs from route inventory with experimental disabled.
2. Generate experimental API docs separately.
3. Add docs freshness date and verification command output.
4. Make docs lint run in CI for both modes.

**Why:** Agents and users will make wrong decisions if docs are stale.

### Step 4: define SaaS data model before UI/billing

**Problem:** current project looks more internal/single-tenant than SaaS.

**Do:**

1. Add users, organizations, memberships, projects, API keys, usage ledger, plan limits.
2. Add tenant ID to jobs/results/events/exports/logs.
3. Add tenant isolation tests before exposing SaaS UI.
4. Define admin vs customer routes.

**Why:** Retrofitting tenancy after billing is painful and dangerous.

### Step 5: make the job engine production-grade

**Problem:** job lifecycle, queue semantics, idempotency, retries, cancellation, and crash recovery need proof.

**Do:**

1. Define state machine.
2. Implement full idempotency fingerprint.
3. Add worker leases and recovery.
4. Add cancellation propagation.
5. Add per-tenant/domain concurrency limits.
6. Add job event timeline.

**Why:** Customers pay for reliable outcomes, not just job creation endpoints.

### Step 6: make extraction quality measurable

**Problem:** extraction success must be measured, not assumed.

**Do:**

1. Build fixture corpus for selected v1 use cases.
2. Track precision/recall/completeness/duplicates/runtime.
3. Store source lineage and confidence.
4. Add result review and manual correction.
5. Show quality report in UI/export.

**Why:** This is the product's core value.

### Step 7: make SaaS deployable and supportable

**Problem:** Docker/Compose/cloud deployment and restore were not proven in this environment.

**Do:**

1. Choose one primary deployment path.
2. Run staging smoke tests.
3. Run backup/restore drill.
4. Add SLOs and alert rules.
5. Add support diagnostics bundle.
6. Protect internal dashboards.

**Why:** Production readiness must be proven with drills, not described in docs.

---


## 8. Twelve-month development plan to reach 100/100

This roadmap assumes disciplined engineering. Do not move to a later phase until the acceptance gates of the earlier phase pass. A 100/100 product is not achieved by adding more modules; it is achieved by making the stable core boring, measurable, secure, and useful for paying users.

### Phase 0 - Week 1 to Week 2: freeze truth and create the safe working base

**Goal:** make the repo safe for coding agents and humans.

**Components:** repo bootstrap, test isolation, docs truth, static candidate triage, agent workflow.

**Steps:**
1. Create a clean branch named `stabilize/phase-0-truth`.
2. Run the baseline verification commands from the handoff document and save outputs under `artifacts/verification/YYYY-MM-DD/`.
3. Add a `make doctor` command that checks Python version, required system tools, dependency installation, Playwright browser availability, env variables, and Node tooling.
4. Add global pytest timeout configuration and separate test markers: `unit`, `api`, `integration`, `browser`, `postgres`, `network`, `slow`, `benchmark`.
5. Make unit/API tests DNS-independent by injecting/mocking DNS resolution and refusing external network unless test marker explicitly allows it.
6. Split docs into current-stable docs and experimental docs. Stable docs must match default route inventory.
7. Create a decision record: stable core vs experimental lab.

**Why:** all later work depends on trustworthy tests and docs. Without this, coding agents will make changes based on stale claims.

**Acceptance gate:**
- `pytest backend/tests/test_api_regressions.py -vv -x` completes quickly.
- Full `pytest --collect-only` passes.
- No unmarked unit/API test performs real DNS or live internet access.
- Stable route docs match route inventory with experimental routes disabled.

### Phase 1 - Month 1: close all P0 blockers

**Goal:** eliminate hangs, unsafe concurrency, and test/runtime blockers.

**Components:** dependency injection, job scheduling, DNS resolver, async safety, restore route lock, CI timeout.

**Steps:**
1. Introduce an application dependency container: `RuntimeDeps` or `AppServices`.
2. Register routers with injected services instead of captured module globals.
3. Replace monkeypatch-dependent test fixtures with app factory fixtures.
4. Centralize DNS resolution behind a resolver interface with sync/async-safe implementations.
5. Move blocking DNS work out of async request handlers using `asyncio.to_thread` or an async resolver with bounded timeout.
6. Fix the restore route so no synchronous lock is held across `await`.
7. Add concurrency tests for restore, cancel, create, reclean, export, and delete.
8. Make CI fail quickly on test hangs.

**Acceptance gate:**
- All P0 issues in the verified backlog are closed with tests.
- `pytest backend/tests/test_api_regressions.py backend/tests/test_url_safety.py -vv` passes under timeout.
- No `threading.Lock` is held across `await` in stable API paths.

### Phase 2 - Month 2: define the SaaS product core

**Goal:** decide exactly what the sellable product is.

**Components:** product requirements, ICP, use cases, pricing metrics, limits, stable feature set, public claims.

**Steps:**
1. Define the first ideal customer profile: agency, growth team, research team, ecommerce ops, or internal data team. Pick one first.
2. Define the first three supported use cases with legal/ethical boundaries.
3. Define unsupported claims: no universal extraction, no anti-bot bypass promise, no scraping of protected/private sites without permission.
4. Define pricing metric: jobs, pages, browser-minutes, extracted records, storage, exports, or seats.
5. Define plan limits for Free/Starter/Pro/Business.
6. Define v1 user journeys: create project, add job, preview extraction, run job, review results, export, schedule, monitor.
7. Write a product requirements document and keep it in docs/product.

**Acceptance gate:**
- One-page PRD exists.
- Pricing metrics map directly to technical usage counters.
- Marketing copy does not overclaim.

### Phase 3 - Month 3: SaaS foundation - tenants, users, orgs, and billing ledger

**Goal:** convert from single-user/internal platform to multi-tenant SaaS foundation.

**Components:** users, organizations, projects, tenant-aware repositories, roles, invitations, usage ledger.

**Steps:**
1. Add database tables for users, organizations, memberships, projects, API keys, usage events, billing accounts, and plan limits.
2. Add tenant context middleware and explicit tenant filters in every repository query.
3. Add negative isolation tests: user A must never read, export, delete, restore, or see user B data.
4. Implement API key scopes and route permissions.
5. Add usage event recording for pages fetched, browser sessions, job duration, records extracted, exports, storage bytes, and failed jobs.
6. Build a simple billing ledger before integrating payments.
7. Add admin/operator routes behind separate roles and audit logs.

**Acceptance gate:**
- Tenant isolation tests pass across jobs, results, logs, exports, recycle bin, metrics, and admin views.
- Every public route has auth/authZ tests.

### Phase 4 - Month 4: extraction quality system

**Goal:** make extraction measurable and improvable.

**Components:** benchmark corpus, quality scoring, confidence, schema suggestions, data lineage, failure taxonomy.

**Steps:**
1. Build a labeled corpus of legal, fixture-based pages for target use cases.
2. Measure precision, recall, field completeness, duplicate rate, hallucination/false positive rate, and run time.
3. Persist source lineage for every record: URL, timestamp, extraction method, field source, confidence, selector/text path, and normalization steps.
4. Expose confidence and failure reasons in the API and UI.
5. Add manual correction/review flow to improve schemas/selectors.
6. Create a regression capture pipeline for customer-safe failed cases.

**Acceptance gate:**
- A benchmark report is generated on every release.
- Quality metrics are visible to users and support staff.

### Phase 5 - Month 5: production-grade job engine

**Goal:** make jobs reliable under crashes, retries, cancellations, and scale.

**Components:** queue semantics, retries, cancellation, worker health, idempotency, backpressure, concurrency limits.

**Steps:**
1. Specify job state machine in docs and enforce it in code.
2. Implement complete idempotency fingerprints from normalized validated requests.
3. Add worker lease/heartbeat/reclaim behavior for Postgres queue.
4. Add per-tenant and per-domain concurrency controls.
5. Add cancellation tokens through browser/fetch/export paths.
6. Implement retry policy with typed failure reasons and max attempts.
7. Add crash recovery tests by killing/restarting workers.

**Acceptance gate:**
- Jobs never stay permanently stuck without a recovery path.
- Duplicate requests do not create duplicate uncontrolled work.
- Cancel works during pending, running, browser, extraction, and export stages.

### Phase 6 - Month 6: private beta SaaS MVP

**Goal:** launch to a small controlled beta, not public SaaS.

**Components:** onboarding, dashboard, project workflow, auth, billing stub, support diagnostics, deployment.

**Steps:**
1. Create a clean SaaS UI separate from internal operator dashboard.
2. Add login/signup/invite/team flow.
3. Add project/job/results/export workflow.
4. Add simple usage page and plan limit display.
5. Deploy staging and production with backups, monitoring, TLS, and protected dashboards.
6. Add support diagnostics bundle with redaction.
7. Onboard 5-10 beta users and manually observe failures.

**Acceptance gate:**
- Beta users complete the main workflow without developer help.
- Support can diagnose failed jobs without database shell access.

### Phase 7 - Month 7: payments, quotas, and customer controls

**Goal:** make the product chargeable without abuse or surprise costs.

**Components:** Stripe/Razorpay or chosen payment provider, usage ledger, invoices, plan enforcement, upgrade/downgrade, quotas.

**Steps:**
1. Integrate payment provider in test mode first.
2. Enforce quotas before expensive work starts.
3. Add usage alerts at 50%, 80%, 100%.
4. Add overage policy or hard stops.
5. Add per-plan browser/session/page/export/storage limits.
6. Add admin override with audit logs.

**Acceptance gate:**
- A paid plan can be purchased, limited, upgraded, downgraded, and canceled in test mode.
- Usage cannot exceed limits through direct API calls.

### Phase 8 - Month 8: security, compliance, and abuse prevention hardening

**Goal:** make the SaaS safe enough for real customers.

**Components:** threat model, SSRF, browser sandboxing, egress controls, AUP, audit logs, deletion/retention, secret scanning.

**Steps:**
1. Create threat model for SaaS scraping platform.
2. Run SSRF and egress tests for redirects, DNS rebinding, IPv6, private ranges, link-local, cloud metadata, localhost, and proxy paths.
3. Isolate browser execution in containers/network policies.
4. Add data retention settings and deletion workflows.
5. Add abuse heuristics and suspension process.
6. Run dependency and secret scans in CI.
7. Prepare ToS, Privacy Policy, Acceptable Use Policy, and customer deletion process.

**Acceptance gate:**
- Security checklist passes in staging and production.
- Customer data deletion is tested end-to-end.

### Phase 9 - Month 9: scale and cost optimization

**Goal:** support more customers without burning money.

**Components:** browser pool scaling, worker autoscaling, storage lifecycle, export jobs, caching, domain limits, cost dashboard.

**Steps:**
1. Track per-job cost: browser seconds, network bytes, CPU, memory, storage, export size.
2. Move large exports to async export jobs with signed downloads and retention limits.
3. Add worker autoscaling signals.
4. Add storage retention/offloading policies.
5. Add cache policy for safe reusable page metadata.
6. Load test target workloads for each plan.

**Acceptance gate:**
- Gross margin model exists and real usage metrics feed it.
- Load tests show plan-level capacity and bottlenecks.

### Phase 10 - Month 10: integrations and developer experience

**Goal:** make the product useful in real workflows.

**Components:** webhooks, API docs, SDK/CLI, Zapier/Make-style integrations, scheduled jobs, templates.

**Steps:**
1. Version the public API as `/api/v1`.
2. Add signed webhooks for job completed/failed/export ready.
3. Add SDK or CLI for job submission and export download.
4. Add templates for common use cases.
5. Add scheduled recurring jobs with quotas and domain policy.
6. Add docs-as-tests examples.

**Acceptance gate:**
- A developer can integrate using docs without asking you.
- Webhooks are signed, retryable, and idempotent.

### Phase 11 - Month 11: enterprise and team readiness

**Goal:** prepare higher-value accounts without distracting from core reliability.

**Components:** SSO optional, advanced audit logs, team permissions, data retention controls, export governance, support SLA.

**Steps:**
1. Add team roles and project-level permissions.
2. Add advanced audit log export.
3. Add retention policies per organization.
4. Add SSO only if beta demand proves it.
5. Add customer success playbooks and support severity definitions.

**Acceptance gate:**
- Business customers can onboard teams safely.
- Support SLAs and incident response are documented and drilled.

### Phase 12 - Month 12: v1 production launch and continuous 100/100 scoring

**Goal:** reach public v1 with evidence.

**Components:** release process, final security review, production drills, public docs, support, monitoring, GTM.

**Steps:**
1. Close all P0 and P1 issues.
2. Triage every static candidate and every high-severity 10k matrix item relevant to v1.
3. Run full CI, staging smoke, production smoke, load test, restore drill, and security test.
4. Publish honest docs and limitations.
5. Launch with limited plans and active monitoring.
6. Continue monthly 100-point score reassessment.

**Acceptance gate:**
- Production incidents have runbooks and owners.
- Backup restore evidence is recent.
- Paid users can run the full workflow with supportable failure modes.


---

## 9. 100/100 technical architecture target

### Stable SaaS architecture

1. **API gateway / reverse proxy:** TLS, request size limits, security headers, rate limiting.
2. **FastAPI app:** stateless customer API, route authZ, tenant context, request validation.
3. **Worker service:** job execution, browser work, extraction, retries, cancellation.
4. **Queue:** Postgres-backed queue or dedicated queue with leases and heartbeats.
5. **Database:** Postgres as source of truth for SaaS; SQLite only for local/dev.
6. **Object storage:** large results, screenshots, diagnostics bundles, exports.
7. **Browser isolation:** browser workers in isolated containers/network with resource limits.
8. **Usage ledger:** append-only usage events feeding billing/quotas/analytics.
9. **Observability:** logs, metrics, traces, job timelines, alerts.
10. **Admin console:** customer/job diagnostics, abuse controls, feature flags, audit logs.
11. **Customer dashboard:** projects, jobs, results, exports, usage, team, billing.
12. **Compliance layer:** retention, deletion, acceptable-use controls, robots/domain policy.

### Stable core modules

The stable v1 core should include only:

- auth/users/orgs/projects;
- job creation/read/cancel/delete/restore;
- safe URL validation;
- deterministic acquisition modes;
- browser/static fetching;
- schema-guided extraction;
- quality report and lineage;
- exports;
- usage metering;
- admin/support diagnostics;
- production monitoring.

### Experimental lab modules

Semantic/topology/adaptive/federation/research modules should be:

- disabled by default;
- hidden from normal customers;
- documented as experimental;
- tested separately;
- promoted only when measured value is proven.

---

## 10. SaaS feature checklist

### User/account layer

- Sign up, login, logout.
- Email verification.
- Password reset or OAuth/SSO later.
- Organizations and teams.
- Membership roles: owner, admin, developer, analyst, viewer.
- API keys scoped by project/org.
- Audit log for security-relevant actions.

### Project/job layer

- Projects group jobs and data.
- Job templates.
- Manual URL jobs.
- Search/topic-assisted jobs only if legally and technically bounded.
- Schema editor.
- Preview run before full run.
- Full run.
- Cancel/retry/reclean.
- Job timeline.
- Failure class and recovery suggestions.

### Result layer

- Paginated results.
- Field confidence.
- Source lineage.
- Duplicate marking.
- Manual correction/review.
- Export selected/all records.
- Export history.
- Retention controls.

### Billing/usage layer

- Usage events.
- Plan limits.
- Quota checks before expensive work.
- Usage page.
- Billing provider integration.
- Invoices/receipts.
- Upgrade/downgrade/cancel.
- Admin credits/overrides with audit logs.

### Security/compliance layer

- Tenant isolation.
- SSRF protection.
- DNS rebinding defense.
- Cloud metadata block.
- Internal IP block.
- Redirect validation.
- Browser sandbox.
- Secret scanning.
- Log redaction.
- Data deletion.
- Retention policies.
- Acceptable-use policy.
- Abuse monitoring.

### Operations layer

- Health/readiness/liveness.
- Metrics and alerts.
- Backup/restore.
- Deployment smoke tests.
- Incident runbook with real contacts.
- Release checklist.
- Rollback plan.
- Error budgets and SLOs.

---

## 11. Exact development workflow for coding agents

For every issue:

1. Read the relevant file and docs.
2. Reproduce the issue or write a failing test.
3. Make the smallest safe code change.
4. Run the narrow test.
5. Run the relevant broader test tier.
6. Update docs only if behavior changed.
7. Add acceptance evidence to issue notes.
8. Do not start unrelated refactors in the same change.

### Required PR template

Each PR should include:

- Issue ID.
- Files changed.
- Risk level.
- Tests added/changed.
- Commands run and output summary.
- Behavior before/after.
- Rollback plan.
- Docs updated or reason docs not needed.

### Required branch order

1. `stabilize/test-isolation-dns`
2. `stabilize/app-dependency-injection`
3. `stabilize/async-locks-timeouts`
4. `docs/stable-experimental-split`
5. `saas/tenant-data-model`
6. `saas/authz-usage-ledger`
7. `saas/customer-dashboard-mvp`
8. `saas/billing-quotas`
9. `prod/deploy-observability-drills`
10. `v1/release-hardening`

---


## 12. Paste-ready coding-agent instruction

You are working on DataForge Scraper. Treat this as a pre-production SaaS extraction platform, not a script. Your job is to move it toward a 100/100 SaaS product by making verified, small, evidence-backed changes.

Rules:
1. Do not trust docs unless a command verifies them.
2. Do not add features before closing P0/P1 stability, security, test, and truth issues.
3. Do not call unverified audit matrix rows confirmed bugs. Confirm each by reading code and running or adding tests.
4. Never use live internet/DNS in unit/API tests unless the test is explicitly marked integration/network.
5. Never hold sync locks across await.
6. Keep experimental modules behind flags.
7. Every PR must include tests, command output, docs update if behavior changed, and rollback notes.
8. Prefer one issue per change. Do not rewrite large files without characterization tests.

Start with these tasks in order:
1. Fix DNS/network isolation in API tests.
2. Refactor router dependencies into injected runtime services.
3. Add pytest timeout and test tiers.
4. Fix restore lock across await.
5. Split stable vs experimental route docs.
6. Add tenant/product SaaS PRD before billing or public UI work.

When in doubt, stop adding code and write the failing test first.


---

## 13. How to use the 10,070-row matrix

The 10k+ matrix is a way to systematically convert a prototype into a SaaS. It should not be dumped into an agent all at once. Use it like this:

1. Filter by `severity_hint` containing P0 or P1.
2. Filter by the component currently being worked on.
3. Convert only confirmed items into real tickets.
4. Close each item with evidence.
5. Defer P2/P3 polish until P0/P1 gates are passed.

Recommended first filters:

- component contains `URL safety`, `DNS`, `job`, `repository`, `worker`, `auth`, `tenant`, `billing`, `export`, `Docker`, `backup`, `frontend auth`.
- category in `Correctness`, `Reliability`, `Async safety`, `Network isolation`, `Security`, `SSRF/egress`, `AuthZ`, `Data isolation`, `Billing`, `Compliance`.

---

## 14. Final target state

DataForge reaches 100/100 only when all of these are true:

1. All P0/P1 verified issues are closed.
2. Static candidates are triaged or suppressed with reason.
3. Stable docs match runtime behavior.
4. Unit/API tests are network-isolated.
5. Full CI passes with timeout guards.
6. Multi-tenant isolation is tested.
7. Billing and usage limits cannot be bypassed.
8. Jobs can recover from worker/app crashes.
9. Large exports do not exhaust memory.
10. Security tests cover SSRF, tenant leaks, logs, secrets, and dashboards.
11. Backup/restore drill is recent and documented.
12. Production monitoring and alerts are live.
13. Beta users complete the workflow without developer help.
14. Marketing claims are honest.
15. Support can diagnose failures safely.
16. Release process is repeatable.
17. The product has paying users or strong beta conversion evidence.

Until then, call it what it is: a promising, advanced pre-production extraction platform that is being hardened into SaaS.

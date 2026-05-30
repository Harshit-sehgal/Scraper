# Project Handoff and Execution Plan

Last updated: 2026-05-29

This document explains what has been done so far, what the project truthfully is now, and how to proceed from the current cleaned baseline.

It is intended as the working plan after the truth-first cleanup. For the current project status, see `PROJECT_STATUS.md`. For detailed audit tables, evidence, and classification, see the deliverables in `docs/audit/`.

## Current Baseline

Repository: `https://github.com/Harshit-sehgal/Scraper`

Current pushed cleanup commit:

```text
a365e2f Truth-first audit cleanup
```

Current branch:

```text
main
```

The repository has been changed from a hype-heavy scraper project into a more defensible pre-production web extraction platform. The current docs intentionally avoid claims such as production-ready, fully autonomous, perfect accuracy, or works on any website.

The project should now be described as:

```text
DataForge Scraper is a pre-production FastAPI and Playwright-based web extraction platform with job APIs, result storage, telemetry, dashboard files, adaptive extraction components, tests, and production deployment work. It supports structured extraction from supported accessible public pages, subject to site structure, authentication, anti-bot controls, rate limits, legal constraints, configuration, and runtime environment.
```

## What Has Been Done So Far

### 1. Repository Truth Cleanup

Completed:

- Built a repository inventory after inspecting the actual tree.
- Counted files by category and documented the cleaned state.
- Identified stale generated reports, maturity reports, and old architecture claims.
- Moved historical and overconfident documents into `docs/archive/`.
- Removed runtime artifacts from the tracked project state.
- Updated `.gitignore` behavior where needed so archive evidence can remain tracked.

Current documented inventory:

| Area | Current Finding |
| --- | --- |
| Total files | 450 |
| Python files | 326 |
| Pytest-named test files | 142 |
| Markdown files | 39 |
| Config/deployment files | 15 |
| Frontend files | 8 |
| Script files | 16 |
| Benchmark/manual files | 26 |
| Archived historical/report files | 28 |
| Runtime artifacts | No tracked `.pyc`, `__pycache__`, `.pytest_cache`, `.mypy_cache`, `.db`, `.sqlite`, or `.log` files remained after cleanup |

Where to read details:

- `PROJECT_STATUS.md`
- [`docs/archive/audit/DELIVERABLE_1_TRUTH_INVENTORY.md`](archive/audit/DELIVERABLE_1_TRUTH_INVENTORY.md) — Inventory of false claims (archived)
- [`docs/archive/audit/DELIVERABLE_2_ARCHITECTURE_MAP.md`](archive/audit/DELIVERABLE_2_ARCHITECTURE_MAP.md) — Architecture reality vs claims (archived)
- [`docs/archive/audit/DELIVERABLE_3_CLAIMS_AUDIT.md`](archive/audit/DELIVERABLE_3_CLAIMS_AUDIT.md) — Detailed claims audit (archived)
- [`docs/archive/audit/DELIVERABLE_4_ERROR_ISSUE_LIST.md`](archive/audit/DELIVERABLE_4_ERROR_ISSUE_LIST.md) — Error and issue list (archived, all resolved)
- [`docs/archive/audit/DELIVERABLE_5_TEST_TRUTH_REPORT.md`](archive/audit/DELIVERABLE_5_TEST_TRUTH_REPORT.md) — Test truth assessment (archived)
- [`docs/archive/audit/DELIVERABLE_6_BENCHMARK_TRUTH_REPORT.md`](archive/audit/DELIVERABLE_6_BENCHMARK_TRUTH_REPORT.md) — Benchmark truth report (archived)
- [`docs/archive/audit/DELIVERABLE_7_SECURITY_REPORT.md`](archive/audit/DELIVERABLE_7_SECURITY_REPORT.md) — Security assessment (archived)
- [`docs/archive/audit/DELIVERABLE_8_DOCUMENTATION_CLEANUP.md`](archive/audit/DELIVERABLE_8_DOCUMENTATION_CLEANUP.md) — Documentation cleanup plan (archived, executed)
- [`docs/archive/audit/DELIVERABLE_9_CORRECTED_README.md`](archive/audit/DELIVERABLE_9_CORRECTED_README.md) — Corrected README template (archived, applied)

### 2. Documentation Rewritten Around Evidence

Completed:

- Rewrote `README.md` as a truthful project overview.
- Created/updated `PROJECT_STATUS.md` as the current source of truth.
- Created audit deliverables in `docs/audit/` with evidence-based findings.
- Created focused docs for architecture, API, setup, production, security, testing, benchmarking, limitations, and roadmap.
- Removed or archived stale claims such as 100% maturity, production-ready, GA-certified, self-healing, and works on any website.
- Reworded dashboard and frontend copy that implied real-time streaming or universal extraction.

Current docs structure:

```text
README.md
PROJECT_STATUS.md
docs/
  API.md
  ARCHITECTURE.md
  HANDOFF.md
  LIMITATIONS.md
  PRODUCTION.md
  PRODUCTION_STARTUP.md
  SECURITY.md
  SETUP.md
  audit/          (detailed audit deliverables)
  archive/        (historical/outdated docs)
```

### 3. Test and Validation Baseline

Completed locally during the audit:

```bash
python3 -m compileall -q backend scripts architecture_validator.py
python3 -m pyflakes backend/app scripts architecture_validator.py
python3 -m mypy backend/app --ignore-missing-imports
PYTHONPATH=backend python3 architecture_validator.py
PYTHONPATH=backend python3 -m pytest --collect-only -q -o addopts=
PYTHONPATH=backend python3 -m pytest -q -ra -o addopts=
```

Latest verified local test result (initial audit — counts have since increased to 1,884):

```text
1711 tests collected
1657 passed
54 skipped
```

**Current test count (as of May 30, 2026):** 1,884 tests collected. See `PROJECT_STATUS.md`.

Important interpretation:

- The local suite passed in the audited environment.
- Skipped tests are not counted as passed.
- Uncollected benchmark/manual scripts are not counted as passed.
- Passing local tests does not prove production readiness.
- Postgres production readiness is not proven because real Postgres service validation is still incomplete.

### 4. Benchmark Accuracy Fixed

Completed:

- Fixed benchmark accuracy scoring so extra records and extra schema fields are penalized.
- Added schema conformity scoring.
- Added tests around extra records and extra fields.
- Documented simulated benchmark behavior separately from real scraping reliability.

Why this matters:

The previous benchmark logic could make extraction quality look stronger than it was. The corrected benchmark math is more honest, but the benchmark framework still needs stronger fixture, replay, live, hostile, and longevity validation.

### 5. Production Environment Validation Improved

Completed:

- Improved `scripts/check_prod_env.py`.
- Production checker now merges process environment over env-file values.
- Production checker rejects placeholder or weak secrets.
- Database URL passwords are masked in output.
- Server startup now runs production env validation when `DATAFORGE_ENV=production`.
- Worker startup now runs production env validation when `DATAFORGE_ENV=production`.
- Added `scripts/start_worker.sh`.
- Docker production server command now uses the startup validation path.
- Production worker command in Compose now uses the startup validation path.

Important interpretation:

- `.env.production.example` is expected to fail validation because it contains placeholders.
- A real production `.env` must be created outside the repository.
- Production startup validation is improved, but full production deployment is not verified until Docker Compose, Postgres, Nginx, browser, metrics, and secrets are tested together.

### 6. Security and Leakage Fixes

Completed:

- Production readiness failure responses no longer expose internal exception strings.
- Production system status avoids exposing the state file path.
- Route auth tests were corrected to use proper operator/admin keys rather than weakening protected routes.
- API claims were aligned with actual user/operator/admin route behavior.
- SSRF and URL safety tests remain present and partially verified.
- Dashboard token storage risk is documented instead of hidden.

Remaining security truth:

- The dashboard still stores API keys in `localStorage`.
- A full route-by-route threat model is still needed.
- SSRF protection in application code should be supported by production network egress controls.
- Metrics exposure must be validated in the deployed network topology.

### 7. Dashboard Truth Cleanup

Completed:

- Removed universal extraction wording from frontend copy.
- Changed dashboard wording from real-time streaming to polling view.
- Removed misleading perfect/success wording.
- Updated CSP to allow the current CDN-based dashboard behavior with documented caveats. *(Resolved: assets now vendored locally, CSP is strict `script-src 'self'`.)*

Remaining dashboard truth:

- The dashboard should be treated as internal/private.
- **✅ CSP resolved:** Assets are vendored locally; strict `script-src 'self'` CSP is enforced.
- Token handling should be redesigned before exposing the dashboard to hostile/shared environments.

### 8. Scripts and Release Gates

Completed:

- Added/updated `scripts/verify_release.sh`.
- Reworded scripts that claimed broad success from limited checks.
- Added production-aware server and worker startup scripts.
- Kept release checks explicit rather than claiming every possible validation is covered.

Recommended command:

```bash
bash scripts/verify_release.sh
```

Use this as a local release sanity check, not as the only production proof.

## What Is Still Remaining

The project is in a much more honest state, but it is not production-ready. The remaining work is validation-heavy.

### Critical Remaining Work

| Priority | Area | Why It Matters |
| ---: | --- | --- |
| 1 | GitHub Actions / CI verification | Local passing tests are not enough; every push needs repeatable CI proof |
| 2 | Postgres CI | Postgres code exists, but production-readiness cannot be claimed while service-backed tests are skipped |
| 3 | Production Docker Compose validation | Deployment files exist, but the full stack has not been proven together |
| 4 | Security route matrix | Sensitive endpoints need explicit role tests and threat-model review |
| 5 | Benchmark redesign | Current benchmark tooling is useful but not enough to claim broad extraction reliability |
| 6 | Dashboard production hardening | Token storage and CSP/CDN behavior are not suitable for broad exposure |
| 7 | Dependency reproducibility | Lock files exist, but Docker currently installs from ranged requirements |

## How To Proceed

Work in phases. Do not add major new scraping features until CI, Postgres, production startup, security, and benchmark methodology are stronger.

## Phase 1: Confirm CI Is Actually Running

Goal: make GitHub Actions the first objective source of truth after every push.

Steps:

1. Open the GitHub repository.
2. Go to the Actions tab.
3. Confirm workflows are enabled.
4. Confirm the cleanup commit triggers a workflow.
5. If no workflow runs, inspect `.github/workflows/ci.yml`.
6. If workflow runs fail, fix CI before starting feature work.

Local commands:

```bash
git status --short --branch
git log --oneline --decorate --max-count=3
bash scripts/verify_release.sh
```

Expected evidence:

- GitHub Actions shows a run for the latest commit.
- CI either passes or has clear failing logs.
- Any failed job is fixed in a follow-up commit.

Do not claim:

- clean CI
- all checks passed
- production-ready

until the GitHub workflow is visibly green.

## Phase 2: Add Real Postgres Validation

> **Status Update (May 30, 2026):** Postgres CI validation is now complete — real Postgres service container configured, all Postgres integration tests pass with 0 skipped. See `PROJECT_STATUS.md`.

Goal: make Postgres support proven enough to describe as tested, not merely implemented.

Why:

The project has Postgres storage and queue code paths, but several Postgres tests are skipped unless a real service and flags are available.

Implementation steps:

1. Add a dedicated GitHub Actions job with a Postgres service container.
2. Install any needed Postgres client dependency, such as `psycopg2-binary`, in the CI environment.
3. Set `DATAFORGE_STORAGE_BACKEND=postgres`.
4. Set `DATAFORGE_DATABASE_URL` to the CI Postgres service URL.
5. Run Postgres-marked tests with the project flag, for example:

```bash
PYTHONPATH=backend python3 -m pytest backend/tests -q -o addopts= --run-postgres
```

6. Add tests for:

- connection failure handling
- migration/init behavior
- persistence after restart
- transaction behavior
- queue leasing and cleanup
- concurrent workers

Success criteria:

- Postgres tests run in CI instead of being skipped.
- Failures are real failures, not silently skipped.
- Docs can say Postgres paths are CI-tested, with scope clearly defined.

Do not claim:

- Postgres production-ready
- distributed queue reliability

until service-backed CI and deployment smoke tests pass.

## Phase 3: Validate Production Docker Compose

Goal: prove the production stack starts and basic routes work with real non-placeholder configuration.

Files involved:

- `Dockerfile`
- `docker-compose.prod.yml`
- `nginx.conf`
- `prometheus.yml`
- `prometheus_alerts.yml`
- `grafana/`
- `.env.production.example`
- `scripts/check_prod_env.py`
- `scripts/start_server.sh`
- `scripts/start_worker.sh`

Steps:

1. Create a real production env file outside source control:

```bash
cp .env.production.example .env.production.local
```

2. Replace every placeholder with a strong real value.
3. Keep `.env.production.local` out of git.
4. Validate it:

```bash
python3 scripts/check_prod_env.py --env-file .env.production.local
```

5. Build the image:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production.local build
```

6. Start the stack:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production.local up
```

7. Test health and readiness through the intended route:

```bash
curl -i http://localhost/health
curl -i http://localhost/ready
```

8. Check that public docs and public metrics exposure match the intended Nginx policy.

Success criteria:

- Production env validation passes with real secrets.
- Docker image builds.
- API container starts through `scripts/start_server.sh`.
- Worker starts through `scripts/start_worker.sh`.
- Nginx routes expected public endpoints only.
- Prometheus and Grafana start with non-default credentials.
- No stack trace or secret leaks through health/readiness responses.

Do not claim:

- production-ready
- hardened deployment

until this is repeated in a target-like environment.

## Phase 4: Build A Route-Level Security Matrix

Goal: every API route should have a known access level and tests proving that access level.

Access levels to use:

- public
- authenticated user
- operator
- admin
- internal only

Steps:

1. Generate the actual FastAPI route list from `app.main`.
2. Map every route to an access level.
3. Add tests that check:

- no key
- normal user key
- operator key
- admin key
- invalid key

4. Give special attention to:

- job creation
- job cancellation
- job deletion
- result export
- URL analysis
- selector mutation
- topology/state/export endpoints
- replay and diagnostic endpoints
- metrics
- scheduler or worker controls

Suggested route-list command:

```bash
PYTHONPATH=backend python3 - <<'PY'
from app.main import app
for route in app.routes:
    methods = ",".join(sorted(getattr(route, "methods", []) or []))
    print(f"{methods:20} {getattr(route, 'path', '')}")
PY
```

Success criteria:

- `docs/API.md` includes an access-level summary.
- Tests fail if a sensitive route becomes less protected.
- Public endpoints are intentionally public, not accidentally open.

Do not claim:

- enterprise-grade security
- fully secure

after this. You can only claim route access is tested to the documented level.

## Phase 5: Strengthen SSRF And Egress Controls

Goal: scraper URL safety should be treated as production-critical.

Application-level tests should cover:

- localhost
- private IPv4 ranges
- private IPv6 ranges
- metadata endpoints
- file URLs
- FTP or unsupported schemes
- redirects to private IPs
- encoded host bypasses
- username/password URL tricks
- unusual ports
- DNS rebinding-like resolution changes where practical

Production-level controls should include:

- container/network egress policy where available
- DNS restrictions where practical
- denylist for metadata IPs
- proxy rules that block private ranges
- logs for blocked URLs

Success criteria:

- URL safety tests cover direct and redirect cases.
- Production docs explain the app-level and network-level layers.
- Unsafe URLs fail closed.

Do not claim:

- complete SSRF protection
- safe against all URL bypasses

because SSRF defense is layered and environment-specific.

## Phase 6: Redesign Benchmarking

Goal: benchmark results should measure actual extraction quality instead of simulated success.

Benchmark categories:

| Category | Purpose | CI Status |
| --- | --- | --- |
| Metric simulation | Validate scoring math only | Should run in CI |
| Fixture benchmark | Deterministic HTML to golden records | Should run in CI |
| Replay benchmark | Captured pages/network payloads | Should run in CI if fixtures are stable |
| Local hostile benchmark | Local server with hostile patterns | Should run in CI if deterministic |
| Live benchmark | Real external sites | Manual or scheduled, not a release proof by itself |
| Longevity benchmark | Long-running stability | Scheduled/manual |

Required scoring behavior:

- punish missing records
- punish extra records
- punish wrong field values
- punish missing fields
- punish extra fields
- punish malformed output
- punish duplicate records
- punish schema mismatch
- record false positives separately
- record partial extraction separately

Steps:

1. Keep current metric tests for scoring math.
2. Create deterministic fixture pages with golden JSON outputs.
3. Add benchmark runner output in JSON.
4. Separate simulated, fixture, replay, and live reports.
5. Add CI job for deterministic benchmarks.
6. Add manual command for live benchmarks that records:

- date
- commit
- environment
- target list
- command
- result file
- failures

Success criteria:

- Simulated recovery is labeled simulated.
- Fixture benchmark fails on extra garbage output.
- Replay/live reports are not used as universal reliability claims.

Do not claim:

- perfect extraction accuracy
- works on any website
- benchmark-proven production reliability

unless the evidence is much stronger than the current project has.

## Phase 7: Dashboard Hardening

> **Status Update (May 30, 2026):** CSP is now strict `script-src 'self'` — all CDN assets (Tailwind CSS, Chart.js) are vendored locally. Dashboard loads under production CSP. Token storage risk remains.

Goal: make the dashboard safe enough for the intended deployment model.

Current truth:

- Dashboard exists.
- Dashboard is internal/private.
- Dashboard currently stores a normal API key in `localStorage`.
- Dashboard assets are vendored locally — strict CSP is enforced.
- Dashboard polls APIs; it is not a WebSocket/SSE real-time streaming UI.

Options:

| Option | Work Required | Best For |
| --- | --- | --- |
| Keep internal/private | Document risk, restrict network access | local/private operators |
| Vendor assets | Serve Chart/Tailwind locally and use strict CSP | production-like internal deployment |
| Session auth | Replace localStorage key pattern | shared/operator environments |
| Separate admin UI | Stronger role-specific dashboard | multi-user production |

Recommended next steps:

1. Vendor dashboard JS/CSS assets locally or remove CDN usage.
2. Tighten Nginx CSP back toward `script-src 'self'`.
3. Replace localStorage API-key storage with a safer session/auth model.
4. Add dashboard smoke tests under Nginx.
5. Add auth failure states to the dashboard.

Success criteria:

- Dashboard loads under production CSP.
- Dashboard does not expose long-lived privileged tokens to browser storage.
- Dashboard route access matches API role policy.

## Phase 8: Dependency Reproducibility

Goal: make builds repeatable enough for release validation.

Current truth:

- Lock files exist.
- Docker installs from `backend/requirements.txt`, which uses version ranges.
- This is not strict reproducibility.

Steps:

1. Decide whether production installs from:

- `backend/requirements.lock.txt`
- generated hash-locked requirements
- Poetry/uv/pip-tools lock file

2. Update Dockerfile to use the chosen lock strategy.
3. Add CI check that lock files are current.
4. Document how to update dependencies.
5. Add a dependency audit command if the team chooses one.

Success criteria:

- Docker and CI install the same pinned dependency set.
- Dependency update workflow is documented.
- Production build is not silently floating across dependency versions.

## Phase 9: Release Checklist

Goal: define what must pass before any production-facing release.

Minimum release gate:

```bash
python3 -m compileall -q backend scripts architecture_validator.py
python3 -m pyflakes backend/app scripts architecture_validator.py
python3 -m mypy backend/app --ignore-missing-imports
PYTHONPATH=backend python3 architecture_validator.py
PYTHONPATH=backend python3 -m pytest -q -ra -o addopts=
python3 scripts/check_prod_env.py --env-file .env.production.local
```

Additional production gate:

- GitHub Actions green on latest commit.
- Postgres CI job green.
- Docker image builds.
- Production compose starts.
- `/health` returns expected public response.
- `/ready` returns expected public response.
- Nginx blocks public metrics unless intentionally exposed.
- Nginx blocks public docs in production if that is the intended policy.
- Prometheus can scrape internally.
- Grafana starts with non-default credentials.
- Worker starts and can process a known fixture job.
- Browser automation works in the production image.
- Dashboard loads under production CSP.
- Route-level auth matrix passes.
- Benchmark fixture suite passes.

Release evidence should be saved as:

```text
docs/release-notes/YYYY-MM-DD-release-validation.md
```

Only create that file after running the commands. Do not generate release proof from assumptions.

## Immediate Next Actions

Do these first:

1. Revoke the exposed GitHub token.
2. Open GitHub Actions and confirm whether the latest commit has a workflow run.
3. Run `bash scripts/verify_release.sh` locally.
4. If CI is failing or disabled, fix CI before feature work.
5. Create GitHub issues from the priorities in this document.
6. Start with Postgres CI.
7. Then validate production Docker Compose.
8. Then add route-level auth matrix tests.
9. Then rebuild benchmark methodology.
10. Then harden dashboard auth/CSP.

## Suggested GitHub Issues

### Issue 1: Verify And Stabilize CI

Scope:

- Confirm GitHub Actions runs for every push.
- Fix any failures from the current cleanup commit.
- Keep local and CI commands aligned.

Acceptance criteria:

- Latest `main` commit has a visible CI run.
- CI is green or failing for known documented reasons.
- Testing status is captured in `PROJECT_STATUS.md` and `docs/LIMITATIONS.md`.

### Issue 2: Add Postgres Service CI

Scope:

- Add Postgres service container.
- Run Postgres-marked tests.
- Install required Postgres client dependency.
- Stop counting skipped Postgres tests as validation.

Acceptance criteria:

- Postgres tests execute in CI.
- Storage and queue tests are not skipped in the Postgres job.
- Failures include useful diagnostics.

### Issue 3: Production Compose Smoke Test

Scope:

- Build Docker image.
- Start `docker-compose.prod.yml` with real local secrets.
- Validate API, worker, Nginx, Prometheus, and Grafana startup behavior.

Acceptance criteria:

- Stack starts.
- Health/readiness pass.
- Placeholder secrets fail.
- Real non-placeholder env passes.

### Issue 4: Route Authorization Matrix

Scope:

- Generate actual route list.
- Classify routes.
- Add tests for no key, user key, operator key, admin key, and invalid key.

Acceptance criteria:

- Sensitive endpoints are not available to lower privilege keys.
- Public endpoints are documented.
- `docs/API.md` matches the tested route matrix.

### Issue 5: Benchmark Framework Upgrade

Scope:

- Separate simulation, fixture, replay, live, hostile, and longevity benchmarks.
- Add golden-record fixture benchmarks.
- Make benchmark output reproducible.

Acceptance criteria:

- Fixture benchmark punishes missing, extra, malformed, and wrong records.
- Live benchmark results are labeled live/manual.
- Simulated metrics are labeled simulation.

### Issue 6: Dashboard Production Hardening

Scope:

- Vendor CDN assets or explicitly accept relaxed CSP.
- Improve token handling.
- Add dashboard smoke tests.

Acceptance criteria:

- Dashboard loads under intended CSP.
- Auth failure states are clear.
- Token storage risk is removed or explicitly accepted for internal-only use.

### Issue 7: Dependency Lock Strategy

Scope:

- Choose production lock-file strategy.
- Update Docker and CI to install from the same locked set.
- Document dependency update workflow.

Acceptance criteria:

- Docker build uses pinned dependencies.
- CI verifies lock consistency.
- Docs explain how to update dependencies.

## What You Can Show Someone Now

You can show:

- The cleaned repository.
- `README.md`.
- `PROJECT_STATUS.md`.
- Audit deliverables in `docs/audit/`.
- Local and CI validation output showing test suite status (see `PROJECT_STATUS.md` for current counts).
- The current architecture and API docs.
- The roadmap and known limitations.

Phrase it as:

```text
This is a pre-production web extraction platform that has gone through a truth-first cleanup. The repository now documents what is verified, partially verified, and unverified. Local syntax, lint sanity, architecture validation, type-check baseline, and the collected local pytest suite have been run successfully, with 54 skipped tests documented. Production readiness, Postgres validation, benchmark methodology, and dashboard hardening remain active work.
```

## What You Should Not Show As Proof Yet

Do not use these as proof:

- archived maturity reports
- old 100% status claims
- simulated benchmark recovery numbers
- skipped Postgres tests
- uncollected manual benchmark scripts
- dashboard polling as real-time streaming
- local test success as production readiness
- production compose files as proof that deployment is validated

## What Must Not Be Claimed Yet

Do not claim:

- production-ready
- fully autonomous
- fully self-healing
- works on any website
- perfect extraction accuracy
- complete anti-bot resilience
- enterprise-grade security
- fully validated Postgres readiness
- real-time streaming dashboard
- fully centralized config
- all tests pass without mentioning skips

## Maintenance Rules Going Forward

Use these rules for every future change:

1. Every project claim must map to evidence.
2. Every skipped test must be visible and explained.
3. Every benchmark result must state whether it is simulation, fixture, replay, live, hostile, or longevity.
4. Every production claim must include the command/environment used to validate it.
5. Every sensitive route must have an access-level test.
6. Every new env var must be documented in setup and production docs.
7. Every dashboard security tradeoff must be documented.
8. Do not move archived reports back into root as current evidence.
9. Keep `PROJECT_STATUS.md` updated after meaningful validation changes.
10. Keep `docs/HANDOFF.md` updated when the execution plan changes.

## Short Version

What has been done:

- The project was audited and cleaned.
- False confidence was removed from current docs.
- Historical hype reports were archived.
- Accuracy metrics were made more honest.
- Production env validation was strengthened.
- Startup gates were added.
- Tests were fixed and run locally.
- The cleanup was pushed to GitHub.

What to do next:

- Revoke the exposed token.
- Verify GitHub Actions.
- Add Postgres CI.
- Validate production Docker Compose.
- Add route-level auth tests.
- Rebuild benchmarks around golden fixtures and replay.
- Harden dashboard auth and CSP.
- Make Docker dependency installs reproducible.

Current truth:

- This is a serious pre-production candidate.
- It is not yet production-ready.
- It is now much safer to share because it tells the truth about what is proven and what is not.

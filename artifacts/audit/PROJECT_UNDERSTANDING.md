# DataForge Scraper - Project Understanding

_Phase 0 baseline regenerated 2026-06-12 from current checkout
`7d47045`._

This document explains the repository in plain language using current
code inspection and command evidence. It does not rely on older status
claims.

## 1. What This Product Is Trying To Become

DataForge Scraper is intended to become a SaaS-ready, safe web data
extraction platform. The target product is a guided extraction
assistant, not just a basic scraper. A mature version should let users:

- paste URLs and receive safety/classification guidance;
- analyze whether a page is static, dynamic, search-driven,
  session-bound, login-required, API-backed, paginated, or unsuitable;
- run extraction jobs and retrieve structured results;
- export CSV/JSON/Excel data safely;
- build guided workflows for forms, pagination, and dynamic pages;
- reuse safe auth profiles for sites the user is allowed to access;
- schedule recurring monitoring jobs;
- manage SaaS identities, projects, quotas, and billing-related usage;
- maintain auditability and tenant/project isolation.

The product must remain lawful and safe. This audit did not find a
requirement to add CAPTCHA bypass, anti-bot bypass, paywall bypass,
login bypass, brute-forcing, private-system scraping, or unsafe
cookie/token handling. Those features remain out of scope.

## 2. What The Current Codebase Appears To Support

The current checkout contains a substantial pre-production platform:

| Capability | Evidence in code | Current validation |
| --- | --- | --- |
| FastAPI backend | `backend/app/main.py`, routers, middleware | compile and architecture gates pass under `python3` |
| URL safety and research boundary | `url_safety.py`, `session_url_detector.py`, research gate scripts | targeted URL/research tests pass |
| Job lifecycle and persistence | `routers/jobs*.py`, `job_store.py`, `storage_interface.py` | code present; full backend suite currently fails elsewhere |
| Export surface | `routers/exports.py`, `services/exports.py`, `utils/export.py` | code present; access controls should be preserved when editing |
| SaaS identity model | `backend/app/saas/*` | code present; route-auth invariant flags mutation routes for review |
| Usage/billing utilities | `utils/usage_ledger.py`, `utils/billing.py` | code present; targeted billing suite not rerun in this turn |
| URL intelligence | `url_analyzer.py`, `routers/intelligence.py` | code present; pyflakes/ruff find unused variable drift |
| Workflow replay | `workflow_executor.py`, `routers/workflow.py` | code present; update test fails because local test client lacks `.put()` |
| Auth profiles | `routers/auth_profiles.py`, `models.py` | code present; model/test mismatch and duplicate model definition found |
| Scheduled monitoring | `routers/scheduled_monitoring.py` | code present; update test fails because local test client lacks `.put()` |
| Static dashboard | `frontend/` | root vitest tests pass; Prettier fails on `frontend/styles.css` |
| Deployment scaffolding | Docker, Compose, nginx, Prometheus, Grafana | files present; no live deployment proof in this audit |

## 3. What The Current Codebase Does Not Yet Support Or Prove

- A green full backend test suite.
- A clean ruff/pyflakes baseline.
- Proven staging deployment, TLS, secrets management, backups, restore
  drill, sustained load, alert delivery, or incident drill.
- Proven Postgres parity in this turn.
- Proven Playwright browser E2E in this turn.
- External payment provider integration.
- Full retention/deletion and customer self-service account flows.
- A complete guided workflow UX from URL analysis to dry-run to saved
  workflow to recurring schedule.
- Browser-based auth-profile capture with encrypted storage state and
  expiry handling.
- Production readiness or 100/100 SaaS readiness.

## 4. What Is Backend

The backend is in `backend/app/` and `backend/forge_kernel/`.

Main areas:

- `main.py`, `lifespan.py`, `middlewares.py`: application factory,
  startup, middleware, auth/rate-limit/body-size/CSP behavior.
- `models.py`: Pydantic models for jobs, workflows, auth profiles,
  scheduled jobs, and related contracts.
- `routers/`: API route modules for jobs, scraper, exports, system,
  session, operator, health, intelligence, workflow, auth profiles,
  scheduled monitoring, and SaaS.
- `saas/`: user/org/project/membership/API-key models and identity
  services.
- `utils/`: RBAC, usage ledger, billing, export helpers, logging,
  retries, health, and notification utilities.
- `url_safety.py`, `session_url_detector.py`, `url_analyzer.py`: URL
  safety and classification.
- `job_store.py`, `storage_interface.py`, `postgres_repository*.py`:
  persistence layers.
- `services/`: extraction/export/job-runner support logic.
- `research/`: experimental code that must remain gated.

## 5. What Is Frontend

The frontend is a static vanilla JavaScript dashboard in `frontend/`.
It is driven by the root `package.json`.

Current pieces:

- `index.html`, `app.js`, `styles.css`: shell and styling.
- `frontend/js/*.js`: dashboard modules for API calls, analyzer,
  jobs, results, views, governance, telemetry, predictions, domain
  health, rate limits, recycle bin, and utilities.
- `frontend/js/*.test.js`: vitest unit tests.
- `frontend/e2e/*.spec.js`: Playwright specs, not run in this audit.
- `frontend/dashboard/`: dashboard page and vendored static assets.

Root `npm run test` passes. Root `npm run lint:js` fails because
Prettier reports `frontend/styles.css`.

## 6. What Is Test / CI / Dev Tooling

- `backend/tests/`: pytest suite and fixtures.
- `backend/benchmarks/`: benchmark tests.
- `frontend/js/*.test.js`: vitest unit tests.
- `frontend/e2e/`: Playwright E2E specs.
- `scripts/`: validation, docs, route matrix, production checks,
  benchmark, load, worker, and deployment helper scripts.
- `architecture_validator.py`: architecture gate.
- `.github/workflows/`: CI workflow definitions.
- `pyproject.toml`, `.pre-commit-config.yaml`, `.prettierrc`,
  `.stylelintrc.json`, `package.json`: local quality tooling.

## 7. What Is Experimental / Research

Experimental/research code is under `backend/app/research/` and is
gated by `DATAFORGE_ENABLE_EXPERIMENTAL_ROUTES`. The boundary check
passed in this audit:

```text
VALIDATION PASSED: 141 product-kernel files are free of top-level research imports.
```

Future edits should not import research modules at stable product
module import time unless the boundary and gate are deliberately
changed and tested.

## 8. What Is Production / Deployment Related

Deployment and operations files include:

- `Dockerfile`
- `docker-compose.yml`
- `docker-compose.prod.yml`
- `docker-compose.override.yml`
- `nginx.conf`
- `prometheus.yml`
- `prometheus_web.yml`
- `prometheus_alerts.yml`
- `alertmanager.yml`
- `grafana/`
- production and example env files
- scripts such as `check_prod_env.py`, `verify_production_deployment.py`,
  `staging_smoke_test.py`, `smoke_prod_stack.sh`

These files are scaffolding and local tooling evidence only. This
audit did not prove a real target production deployment.

## 9. What Is Verified By Commands

Verified passes:

- `python3 -m compileall -q backend scripts architecture_validator.py`
- `PYTHONPATH=backend python3 architecture_validator.py`
- `python3 scripts/check_research_boundary.py`
- `python3 scripts/validate_dependency_bounds.py`
- `python3 -m pytest backend/tests/test_url_safety.py backend/tests/test_research_boundary.py -q`
- `npm ci`
- `npm run test`
- `python3 -m bandit -r backend -q`
- `python3 artifacts/audit/gen_full_ledger.py`

Verified failures:

- literal `python ...` commands fail because `python` is not installed;
- full backend pytest has six failures;
- route-auth invariant has three SaaS mutation rows;
- ruff has 53 findings;
- pyflakes has seven findings;
- `npm run lint:js` fails on `frontend/styles.css`.

See `VALIDATION_REPORT.md` for exact command table and failure details.

## 10. What Is Unverified

- Full backend suite green status.
- Mypy status.
- pip-audit status.
- Postgres parity.
- Browser E2E.
- Load testing.
- Staging deployment.
- TLS/secrets/backups/restore drill/monitoring/alert delivery.
- Production readiness.
- 100/100 SaaS readiness.

## 11. What Docs Appear Stale Or Overconfident

Docs that should not be treated as current proof:

- `PROJECT_STATUS.md`
- `docs/CURRENT_STATUS.md`
- `docs/PRODUCTION_READINESS.md`
- `docs/ROADMAP.md`
- `docs/LIMITATIONS.md` where it repeats older 3025-test pass counts
- `README.md` and `docs/TESTING.md` where they point readers to
  older `PROJECT_STATUS.md` claims
- `Instructions_for_ai/DataForge_100_100_SaaS_Master_Plan.md`
- `Instructions_for_ai/PROGRESS.md`

Some of these documents contain useful plans or guardrails. Their
validation counts and maturity scores are not reproduced by this
audit.

## 12. Current Realistic Project Maturity

| Area | Realistic status |
| --- | --- |
| Backend foundation | Substantial and structured, but full pytest is red. |
| Security/auth baseline | Central RBAC and URL safety exist; SaaS mutation authorization needs review. |
| Tenant/project isolation | Present in model/router concepts; must be preserved and tested on every affected path. |
| Extraction capability | Broad code surface exists; benchmark/prod quality is not proven here. |
| Frontend | Unit tests pass; formatter fails; full guided UX not complete. |
| Billing/usage | Utilities exist; real provider integration and production enforcement are not proven. |
| Experimental boundary | Current boundary check passes. |
| Deployment | Scaffolding exists; real deployment readiness is unverified. |
| Documentation truth | Improved by this Phase 0 audit; older readiness docs remain stale/overconfident. |

Overall: DataForge is a real pre-production codebase with meaningful
backend, frontend, testing, and deployment scaffolding. It is not
production-ready. It is safe to proceed to Prompt 2 only if the next
phase fixes verified issues with focused tests and avoids unrelated
refactors or unsafe scraping behavior.

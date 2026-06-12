# DataForge Scraper - Project Structure Summary

_Phase 0 baseline regenerated 2026-06-12 from current checkout
`7d47045`._

This summary is based on the regenerated file ledger and current
command output. It does not claim production readiness.

## Verified Inventory Counts

Source: `artifacts/audit/FILE_AUDIT_LEDGER.csv`.

| Bucket | Count |
| --- | ---: |
| Total files inventoried | 29,148 |
| Project-owned files | 821 |
| Project-owned files deeply inspected | 818 |
| Skipped generated/vendor/binary/cache/log/archive files | 28,330 |
| Unknown classifications | 0 |
| Backend source | 265 |
| Frontend source | 41 |
| Tests and fixtures | 339 |
| Scripts | 44 |
| Config | 40 |
| Documentation | 79 |
| Docker/deployment/monitoring | 12 |
| Database migration/init files | 1 |
| Generated artifacts | 117 |
| Vendor files | 19,938 |
| Cache files | 8,129 |
| Log files | 140 |

The three project-owned files not deeply inspected are lockfiles:
`package-lock.json`, `uv.lock`, and
`backend/tests/test_semantic_state.json.lock`.

## Top-Level Shape

```text
scraper/
├── backend/
│   ├── app/                  FastAPI backend and extraction logic
│   ├── forge_kernel/         kernel-style backend modules
│   ├── tests/                pytest suite and fixtures
│   ├── benchmarks/           benchmark tests
│   ├── init-db/              database initialization SQL
│   ├── data/                 runtime/generated data
│   └── logs/                 runtime logs
├── frontend/
│   ├── js/                   vanilla JS modules and vitest tests
│   ├── dashboard/            dashboard pages/widgets plus vendored assets
│   ├── e2e/                  Playwright specs
│   ├── smoke/                smoke pages
│   ├── index.html
│   ├── app.js
│   ├── styles.css
│   ├── vitest.config.js
│   └── playwright.config.mjs
├── scripts/                  validation, docs, deployment, benchmark, worker scripts
├── docs/                     project docs and runbooks
├── Instructions_for_ai/      planning/progress documents; many are historical
├── .github/workflows/        CI workflow definitions
├── grafana/                  Grafana dashboards/provisioning
├── artifacts/
│   ├── audit/                Phase 0 audit outputs and generators
│   └── validation/           validation log artifacts
├── Dockerfile
├── docker-compose*.yml
├── nginx.conf
├── prometheus*.yml
├── alertmanager.yml
├── pyproject.toml
├── package.json
├── package-lock.json
├── uv.lock
├── architecture_validator.py
├── verify_compile.py
├── AGENTS.md
└── docs/AGENT_TRUTH.md
```

The checkout also contains local/vendor/cache trees including `.venv/`,
`node_modules/`, `.git/`, `.kilo/`, `.mypy_cache/`, `.ruff_cache/`,
`.pytest_cache/`, `playwright-report/`, and `test-results/`. They are
listed in the ledger but not treated as DataForge product code.

## Backend Map

`backend/app/` contains the FastAPI application and extraction
platform code.

| Area | Representative files | Phase 0 status |
| --- | --- | --- |
| App composition | `main.py`, `lifespan.py`, `middlewares.py` | compile/architecture gates pass |
| Auth/session/RBAC | `auth/session.py`, `utils/rbac.py`, middleware | targeted URL/research tests pass; full auth suite not rerun in this turn |
| Job APIs | `routers/jobs*.py`, `job_store.py`, `storage_interface.py` | present; full suite currently fails elsewhere before green status can be claimed |
| Exports | `routers/exports.py`, `services/exports.py`, `utils/export.py` | present; access-control details require targeted tests before edits |
| URL safety | `url_safety.py`, `admin_denylist.py`, `session_url_detector.py` | targeted `test_url_safety.py` passes |
| URL intelligence | `url_analyzer.py`, `routers/intelligence.py` | present; ruff/pyflakes report unused variable in `url_analyzer.py` |
| SaaS identity | `saas/models.py`, `saas/service.py`, `saas/router.py`, `saas/identity_store.py` | present; route-auth invariant flags three mutation routes for review |
| Workflow/auth profiles/scheduled monitoring | `routers/workflow.py`, `routers/auth_profiles.py`, `routers/scheduled_monitoring.py`, `workflow_executor.py` | present; full pytest has failures in this surface |
| Billing/usage | `utils/billing.py`, `utils/usage_ledger.py` | present; not rerun as a targeted suite in this turn |
| Audit/logging/notifications | `audit_logger.py`, `utils/telegram_notifier.py` | full pytest shows Telegram network attempt under tests |
| Research boundary | `app/research/`, `experimental_startup.py` | `check_research_boundary.py` passes |
| Storage parity | `postgres_repository*.py`, `psycopg3_repository.py` | code exists; Postgres parity not run in this turn |

## Frontend Map

The frontend is a static vanilla JavaScript dashboard, not a React or
Vue app. Root `package.json` drives frontend tooling.

| Area | Files | Phase 0 status |
| --- | --- | --- |
| Shell | `frontend/index.html`, `frontend/app.js`, `frontend/styles.css` | unit tests pass; Prettier fails on `styles.css` |
| Modules | `frontend/js/*.js` | vitest passes: 15 files, 269 tests |
| URL analyzer panel | `frontend/js/analyzer.js` | present; included in tests |
| E2E | `frontend/e2e/*.spec.js` | not run in this turn |
| Dashboard widgets | `frontend/dashboard/*` | present; `vendor/` assets listed |

## Tooling and CI

| Area | Files | Notes |
| --- | --- | --- |
| Python config | `pyproject.toml`, `.pre-commit-config.yaml`, `backend/.bandit` | config scanned |
| Frontend config | `package.json`, `.prettierrc`, `.stylelintrc.json`, `frontend/vitest.config.js`, `frontend/playwright.config.mjs` | root npm commands used |
| Validation scripts | `scripts/check_research_boundary.py`, `scripts/validate_dependency_bounds.py`, `architecture_validator.py` | pass under `python3` |
| CI | `.github/workflows/*.yml` | present but not executed in this local audit |
| Deployment | `Dockerfile`, `docker-compose*.yml`, `nginx.conf`, Prometheus/Grafana files | present but staging/TLS/load/alert evidence not produced |

## Experimental / Research

Research code lives under `backend/app/research/` and is guarded by
`DATAFORGE_ENABLE_EXPERIMENTAL_ROUTES`. The current boundary check
passed:

```text
VALIDATION PASSED: 141 product-kernel files are free of top-level research imports.
```

Do not move research imports into stable product paths without updating
the boundary tests and gate.

## Current Structural Risks

- Full backend pytest is not green.
- Route auth matrix flags three SaaS mutation routes for authorization
  review.
- `backend/app/models.py` contains duplicate `AuthProfile`
  definitions according to pyflakes/ruff.
- `LocalASGIClient` lacks `.put()` while workflow/scheduled tests use
  it.
- Test execution can attempt an external Telegram call.
- Frontend unit tests pass, but JS formatting fails on
  `frontend/styles.css`.
- Production deployment scaffolding exists, but no target-environment
  proof was produced in this audit.

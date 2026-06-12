# DataForge Scraper - Docs Truth Check

_Phase 0 baseline regenerated 2026-06-12 from current checkout
`7d47045`._

This report compares documentation claims against current command
evidence. The audit scanned project-owned docs through the file ledger,
but this report focuses on documents with status, readiness, roadmap,
production, or 100/100 claims.

## Current Evidence Baseline

Verified in this turn:

- `python3` compileall passes.
- Architecture validator passes.
- Research boundary check passes.
- Dependency bounds validation passes.
- Targeted URL safety and research-boundary tests pass.
- Full backend pytest fails with six failures.
- Root `npm ci` passes.
- Root `npm run test` passes with 15 test files and 269 tests.
- Root `npm run lint:js` fails on `frontend/styles.css`.
- Ruff and pyflakes fail.
- Bandit passes with warnings only.
- Full inventory lists 29,148 files.

Not verified in this turn:

- mypy.
- pip-audit.
- Postgres parity.
- Playwright browser E2E.
- staging deployment, TLS, secrets, backups, restore drill, load,
  monitoring, alert delivery, incident drills.

## Status / Readiness Docs

| Document | State | Evidence-based finding |
| --- | --- | --- |
| `docs/AGENT_TRUTH.md` | current | Regenerated in this Phase 0; use as the first truth source. |
| `artifacts/audit/VALIDATION_REPORT.md` | current | Regenerated in this Phase 0 with command results. |
| `artifacts/audit/FILE_AUDIT_LEDGER.csv` | current | Regenerated in this Phase 0 with 29,148 rows. |
| `artifacts/audit/FILE_AUDIT_LEDGER.md` | current | Regenerated in this Phase 0 with 29,148 rows. |
| `artifacts/audit/FILE_INVENTORY.md` | current | Regenerated in this Phase 0. |
| `PROJECT_STATUS.md` | overconfident/historical | Claims CI/local fast gates/lint/test suite pass 100% clean and quotes older maturity estimates. Current full backend pytest, ruff, pyflakes, and frontend lint do not reproduce that. |
| `docs/CURRENT_STATUS.md` | historical/partial | Has useful context but current validation does not reproduce a green full suite or production readiness. |
| `docs/PRODUCTION_READINESS.md` | partial guardrail | Correctly warns not to claim production-ready, but production readiness itself remains unproven. |
| `docs/ROADMAP.md` | historical/partial | Roadmap content is useful planning material, not current validation evidence. |
| `docs/CI_STATUS.md` | unverified | References CI/workflow status that was not checked from GitHub in this local audit. |
| `docs/COVERAGE_REPORT.md` | historical | Coverage numbers were not regenerated in this audit. |
| `docs/LIMITATIONS.md` | partial | Safety limitations are useful; the old `3025 passed, 78 skipped, 0 failed` claim is not reproduced. |
| `docs/TESTING.md` | partial | Test guidance exists, but any pointers to older all-green counts should defer to `docs/AGENT_TRUTH.md`. |
| `README.md` | partial | High-level product description is broadly aligned; references to `PROJECT_STATUS.md` as latest status are stale for this audit. |
| `Instructions_for_ai/DataForge_100_100_SaaS_Master_Plan.md` | aspirational/historical | Useful plan, but the title and target are not current state. |
| `Instructions_for_ai/DataForge_Coding_Agent_100_100_Prompt.txt` | aspirational/historical | Useful guardrails; not validation evidence. |
| `Instructions_for_ai/PROGRESS.md` | overconfident/historical | Contains 100/100 progress claims that current validation does not reproduce. |
| `CODE_REVIEW_BUGS.md` | historical | Older review artifact; not refreshed against this checkout. |

## API / Route Docs

| Document | State | Evidence-based finding |
| --- | --- | --- |
| `docs/API.md` | partial | API docs should be checked against regenerated route inventory before being treated as current. |
| `docs/API_STABLE.md` | partial | Stable route docs may be close, but route-auth matrix currently flags SaaS mutation routes for review. |
| `docs/API_EXPERIMENTAL.md` | historical/guarded | Experimental API is gated; do not treat as stable product surface. |
| `docs/API_EXPERIMENTAL_DIFF.md` | historical/guarded | Same as above. |
| `docs/ROUTE_AUTH_MATRIX.md` | stale/partial | Regenerate after resolving the route-auth invariant failures. |

## Production / Operations Docs

| Document | State | Evidence-based finding |
| --- | --- | --- |
| `docs/PRODUCTION.md` | unverified | Deployment instructions were not executed in a target environment. |
| `docs/PRODUCTION_STARTUP.md` | partial | Production safety concepts exist, but startup behavior was not exhaustively tested here. |
| `docs/DEPLOYMENT_CHECKLIST.md` | checklist | Not executed in this audit. |
| `docs/TLS_DEPLOYMENT.md` | checklist | TLS was not validated. |
| `docs/DISASTER_RECOVERY.md` | checklist | Restore drill was not run. |
| `docs/INCIDENT_RESPONSE.md` | process doc | Incident process not drilled. |
| `docs/INCIDENT_RUNBOOK.md` | process doc | Runbook not drilled. |
| `docs/MONITORING.md` | partial | Prometheus/Grafana files exist; alert delivery not validated. |

## Security / Safety Docs

| Document | State | Evidence-based finding |
| --- | --- | --- |
| `docs/SECURITY.md` | partial | Security guidance exists; no penetration test in this audit. |
| `docs/SSRF_EGRESS.md` | partial | URL safety tests pass, but production egress controls were not proven. |
| `docs/SECURITY_HEADERS.md` | partial | Header policy exists; browser validation not run. |
| `docs/DASHBOARD_AUTH.md` | partial | Dashboard auth posture should be checked before public exposure. |
| `docs/CONFIG_AUDIT.md` | historical/partial | Config should be rechecked after fixes. |

## Verified Stale Or Overconfident Claims

| Claim area | Why stale/overconfident |
| --- | --- |
| "100% clean tests" | Full backend pytest currently has six failures. |
| "lint clean" | Ruff has 53 findings; pyflakes has seven findings; frontend Prettier fails. |
| "production-ready" | No staging/TLS/secrets/backups/restore/load/alert proof was produced. |
| "100/100 SaaS-ready" | Payment integration, production drills, green full suite, and complete guided UX are not proven. |
| old `3025 passed` counts | Not reproduced in this audit. |

## Recommended Documentation Actions

1. Make `docs/AGENT_TRUTH.md` and `artifacts/audit/VALIDATION_REPORT.md`
   the current status entry points.
2. Update `PROJECT_STATUS.md` to remove or clearly mark old green-suite
   and maturity claims as historical.
3. Update `README.md`, `docs/TESTING.md`, and `docs/LIMITATIONS.md` so
   they do not point readers to stale all-green counts.
4. Regenerate route/API docs after fixing the route-auth matrix issue.
5. Keep production docs framed as checklists until target-environment
   deployment evidence exists.

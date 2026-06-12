# Validation System Review

Date: 2026-06-12
Commit: `7d47045`

This review inspected the repository validation surface before adding
the reproducible local runner for Prompt 4.

## Files And Areas Inspected

- `pyproject.toml`
- `package.json`
- `package-lock.json`
- `Makefile`
- `Dockerfile`
- `docker-compose.yml`
- `docker-compose.prod.yml`
- `.github/workflows/`
- `scripts/`
- `backend/tests/`
- `architecture_validator.py`
- `docs/TESTING.md`
- `docs/CI_STATUS.md`
- `docs/TEST_RELIABILITY.md`
- `README.md`
- `docs/AGENT_TRUTH.md`

## Existing Validation Commands

The repository already had useful validation commands:

- `python3 -m compileall -q backend scripts architecture_validator.py`
- `PYTHONPATH=backend python3 architecture_validator.py`
- `python3 scripts/check_research_boundary.py`
- `python3 scripts/validate_dependency_bounds.py`
- `python3 -m pytest backend/tests -q`
- `python3 -m ruff check backend scripts`
- `python3 -m pyflakes backend/app backend/tests`
- `python3 -m mypy backend`
- `python3 -m bandit -r backend -q`
- `python3 -m pip_audit`
- `npm ci`
- `npm run test`
- `npm run lint:js`

The project also had `scripts/run_validation.sh` and
`scripts/verify_all.sh`. They are useful historical scripts but did
not satisfy this phase by themselves because they did not provide all
of the following together: per-command structured logs, JSON summary,
timeouts for every subprocess, secret redaction, archived runs, and a
single documented quick gate for future agents.

## Existing CI Jobs

`.github/workflows/` contains separate workflows for:

- main CI
- browser E2E
- golden dataset
- image build
- nightly integration
- optional suites
- Postgres tests
- pre-commit CI
- production validation

All inspected workflows have job-level timeouts. The main CI already
runs many backend, frontend, lint, security, benchmark, and production
placeholder checks. Prompt 4 adds the same reproducible quick
validation command used locally and uploads its logs as a CI artifact.

## Missing Or Problematic Pieces Found

- No prior one-command Python runner produced both Markdown and JSON
  summaries with per-command logs.
- No prior runner archived every run under `artifacts/validation/runs/`.
- `Makefile` had a `validate` target without a recipe, while
  `api-docs-check` accidentally ran `scripts/verify_all.sh` after its
  route-inventory check.
- `README.md` still showed stale green lint/type status and pointed
  users to `PROJECT_STATUS.md` as the current truth source.
- `docs/TESTING.md` and `docs/CI_STATUS.md` contain historical status
  details that must be verified before reuse.
- Literal `python` is not installed in this local workspace; local
  documentation must use `python3` or a virtual environment.

## Current Commands That Fail

The full validation path currently fails. The current Prompt 4 full
run is archived at
`artifacts/validation/runs/20260612T162028Z_full/summary.md`.

Known failing checks:

- `backend_full_tests`: remaining auth-profile model contract failures
  and pyflakes gate failure.
- `ruff_check`: project-wide Ruff violations.
- `pyflakes`: duplicate `AuthProfile`, unused imports, and unused test
  imports.
- `mypy`: duplicate `AuthProfile` definition.
- `pip_audit`: 60 known vulnerabilities in 21 installed packages, plus
  unauditable system/local packages in the current environment.
- `frontend_lint_js`: Prettier drift in `frontend/styles.css`.

## Commands That Hung

No Prompt 4 command hung. The validation runner marks timeouts as
`timeout`, writes partial logs, and returns non-zero for required
checks.

## Undocumented Or Overlapping Checks

- `scripts/run_validation.sh` and `scripts/verify_all.sh` overlap with
  CI and the new local runner.
- CI repeats some quick checks after the new quick validation step.
  This is intentional for now because the existing jobs provide
  established CI behavior while the new step supplies archived command
  evidence.
- Optional Postgres, browser, live benchmark, and production checks
  are intentionally separate from quick validation.

## Stable Vs Experimental Boundary

Stable quick checks:

- compileall
- architecture validator
- research boundary
- dependency bounds
- URL safety/research smoke tests
- targeted P0 auth/tenant/billing/quota/route tests

Experimental or opt-in checks:

- Postgres integration tests requiring `--run-postgres`
- browser E2E requiring Playwright/browser setup
- live benchmark or network tests
- production environment validation beyond placeholder checks

Research modules remain under `backend/app/research/` and are guarded
by `DATAFORGE_ENABLE_EXPERIMENTAL_ROUTES`.

## Changes Made In Prompt 4

- Added `scripts/validate_local.py`.
- Added archived validation logs under `artifacts/validation/runs/`.
- Updated `Makefile` validation targets.
- Added `docs/VALIDATION.md`.
- Added this review.
- Updated CI to run `python scripts/validate_local.py --quick` and
  upload `artifacts/validation/`.
- Adjusted `--json` mode so stdout is parseable JSON and progress
  output goes to stderr.
- Updated `AGENTS.md`, `README.md`, `docs/AGENT_TRUTH.md`, and the
  issue ledger to use the new validation truth.

## Recommended Validation Structure

Use this order for future work:

1. Run `python3 scripts/validate_local.py --quick`.
2. Run targeted tests for the files being changed.
3. For backend-wide changes, run `python3 scripts/validate_local.py --backend`.
4. For frontend changes, run `python3 scripts/validate_local.py --frontend`.
5. Before release or major merge, run `python3 scripts/validate_local.py --full`.
6. Keep Postgres, browser, benchmark, and production checks explicit
   and separately documented.

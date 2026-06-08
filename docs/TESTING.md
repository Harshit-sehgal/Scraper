# Testing

**Last refreshed:** 2026-06-08
**Status:** Current local testing truth

Use explicit environment variables so local `.env` files do not change results.

## Required Local Commands

```bash
python3 -m compileall -q backend scripts architecture_validator.py
PYTHONPATH=backend python3 architecture_validator.py
python3 scripts/validate_dependency_bounds.py
python3 scripts/frontend_syntax_check.py
PYTHONPATH=backend DATAFORGE_DOTENV_PATH=/dev/null DATAFORGE_STORAGE_BACKEND=sqlite python3 -m pytest --collect-only -q backend/tests backend/benchmarks -o addopts=
PYTHONPATH=backend DATAFORGE_DOTENV_PATH=/dev/null DATAFORGE_STORAGE_BACKEND=sqlite python3 -m pytest -q backend/tests -o addopts=
PYTHONPATH=backend DATAFORGE_DOTENV_PATH=/dev/null DATAFORGE_STORAGE_BACKEND=sqlite python3 -m pytest -q backend/benchmarks -o addopts=
PYTHONPATH=backend DATAFORGE_DOTENV_PATH=/dev/null DATAFORGE_STORAGE_BACKEND=sqlite python3 -m coverage run --source=backend/app -m pytest -q backend/tests -o addopts= --tb=line --no-cov-on-fail
python3 -m coverage json -o coverage.json
python3 scripts/check_coverage_floors.py coverage.json
python3 -m coverage report --fail-under=60
```

## Latest Results

For the latest verified test counts, test run statuses, and benchmark results across SQLite, Postgres, Playwright browser, and Golden Dataset live suites, see [PROJECT_STATUS.md](../PROJECT_STATUS.md).

## Optional Groups

Postgres:

```bash
PYTHONPATH=backend DATAFORGE_DOTENV_PATH=/dev/null DATAFORGE_STORAGE_BACKEND=postgres python3 -m pytest backend/tests --run-postgres -q -o addopts=
```

Browser:

```bash
PYTHONPATH=backend DATAFORGE_DOTENV_PATH=/dev/null DATAFORGE_STORAGE_BACKEND=sqlite python3 -m pytest backend/tests --run-browser -q -o addopts=
```

Golden dataset:

```bash
PYTHONPATH=backend DATAFORGE_DOTENV_PATH=/dev/null DATAFORGE_STORAGE_BACKEND=sqlite python3 -m pytest backend/tests/test_golden_dataset.py --run-golden-dataset -q -o addopts=
```

## What Tests Do Not Prove

- Passing local tests does not prove production readiness in the target environment.
- Browser tests prove local Playwright behavior, not broad anti-bot bypass.
- Postgres tests prove local repository/queue behavior, not production failover, scheduling, or backups.
- Postgres and Playwright browser tests were validated in prior sessions; rerun `pytest backend/tests/ -v --ignore=backend/tests/unit -k postgres` and `npx playwright test` for fresh counts. Golden Dataset tests were verified (with 7/8 passing and httpbin.org skipped under expected 503 error). Docker image build and production Compose stack operations are documented historically.
- Route-auth tests verify registration and boundaries, but do not replace a security review or penetration test.

## Manual Tests

`backend/tests/manual_*.py` files are manual validation tools, not proof of default pytest health. Live network tests require explicit flags and should not be counted as safe offline tests.

# Testing

**Last refreshed:** 2026-06-01
**Status:** Current local testing truth

Use explicit environment variables so local `.env` files do not change results.

## Required Local Commands

```bash
python3 -m compileall -q backend scripts architecture_validator.py
PYTHONPATH=backend python3 architecture_validator.py
PYTHONPATH=backend DATAFORGE_DOTENV_PATH=/dev/null DATAFORGE_STORAGE_BACKEND=sqlite python3 -m pytest --collect-only -q backend/tests backend/benchmarks -o addopts=
PYTHONPATH=backend DATAFORGE_DOTENV_PATH=/dev/null DATAFORGE_STORAGE_BACKEND=sqlite python3 -m pytest -q backend/tests -o addopts=
PYTHONPATH=backend DATAFORGE_DOTENV_PATH=/dev/null DATAFORGE_STORAGE_BACKEND=sqlite python3 -m pytest -q backend/benchmarks -o addopts=
```

## Latest Results

| Command | Result | Meaning |
| --- | --- | --- |
| `compileall` | Passed with no output | Syntax is valid for checked Python files |
| `architecture_validator.py` | `VALIDATION PASSED: Architecture is lawful.` | Architecture rules pass |
| Pytest collection | `1912 tests collected in 0.41s` | Collection is clean |
| Safe SQLite backend suite | `1839 passed, 72 skipped in 107.06s` | Default local backend tests pass |
| Benchmark package | `1 passed in 0.27s` | Benchmark smoke/config test passes only |
| Route auth tests | `134 passed in 1.25s` | Route-auth matrix tests pass |
| Production security tests | `48 passed in 0.09s` | Placeholder/secret validation tests pass |
| Combined route/security tests | `182 passed in 1.31s` | Route-auth and production-security checks pass together |
| Postgres optional suite | `1883 passed, 28 skipped in 129.55s` | Postgres repository/queue tests pass locally |
| Browser optional suite | `1856 passed, 55 skipped in 116.73s` | Browser/local-server tests pass locally |
| Golden dataset optional suite | Stopped after one visible test and no progress for several minutes | Not validated |

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

- Passing local tests does not prove production readiness.
- Browser tests prove local Playwright behavior, not broad website compatibility.
- Postgres tests prove local repository/queue behavior, not production failover or backups.
- Golden dataset tests do not currently enforce accuracy thresholds.
- Route-auth tests do not replace a security review or penetration test.

## Manual Tests

`backend/tests/manual_*.py` files are manual validation tools, not proof of default pytest health. Live network tests require explicit flags and should not be counted as safe offline tests.

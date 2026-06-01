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
| Pytest collection | `1916 tests collected in 0.40s` | Collection is clean |
| Safe SQLite backend suite | `1843 passed, 72 skipped in 119.06s` | Default local backend tests pass |
| Benchmark package | `1 passed in 0.25s` | Benchmark smoke/config test passes only |
| Combined route/security/CORS tests | `183 passed in 1.83s` | Route-auth, production-security, and CORS preflight checks pass together |
| Postgres optional suite | `1885 passed, 28 skipped in 138.54s` | Local Postgres repository/queue tests pass |
| Browser optional suite | `1858 passed, 55 skipped in 125.64s` | Local browser/local-server tests pass |
| Golden dataset optional suite | `8 passed in 53.97s`; F1 books `0.650`, quotes `1.000`, countries `0.680`, example `1.000`, httpbin `1.000` | Live golden checks pass modest enforced thresholds |

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
- Golden dataset thresholds are modest and do not prove broad extraction accuracy.
- Route-auth tests do not replace a security review or penetration test.

## Manual Tests

`backend/tests/manual_*.py` files are manual validation tools, not proof of default pytest health. Live network tests require explicit flags and should not be counted as safe offline tests.

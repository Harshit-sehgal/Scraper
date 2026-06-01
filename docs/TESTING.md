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

Only the rows below with `/usr/bin/python3` were freshly rerun in this cleanup; the remaining historical rows in the repository should be treated as archived evidence until rerun.

| Command | Result | Meaning |
| --- | --- | --- |
| `compileall` | Passed with no output | Syntax is valid for checked Python files |
| `architecture_validator.py` | `VALIDATION PASSED: Architecture is lawful.` | Architecture rules pass |
| Pytest collection | `1920 tests collected in 0.43s` | Collection is clean |
| Safe SQLite backend suite | `1846 passed, 72 skipped in 121.71s` | Default local backend tests pass |
| Benchmark package | `1 passed, 1 skipped in 0.26s` | Benchmark smoke/config test passes only |
| Route auth matrix | Generated from the registered FastAPI app with `scripts/route_auth_matrix.py --format markdown` | Route access documentation is current |
| Production env example | `scripts/check_prod_env.py --env-file .env.production.example` fails intentionally on placeholders | Example env is not deployable as-is |

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
- Archived Postgres/browser/Compose/Docker/golden-dataset results should be treated as historical unless rerun in this refresh.
- Route-auth tests do not replace a security review or penetration test.

## Manual Tests

`backend/tests/manual_*.py` files are manual validation tools, not proof of default pytest health. Live network tests require explicit flags and should not be counted as safe offline tests.

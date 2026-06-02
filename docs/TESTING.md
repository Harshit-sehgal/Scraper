# Testing

**Last refreshed:** 2026-06-02
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

The following rows were freshly run in this session (2026-06-02). Results noted as *(archived)* were from the prior refresh (2026-06-01) and were not re-run.

| Command | Result | Meaning |
| --- | --- | --- |
| `compileall` | Passed with no output | Syntax is valid for checked Python files |
| `architecture_validator.py` | `VALIDATION PASSED: Architecture is lawful.` | Architecture rules pass |
| Pytest collection | `1937 tests collected in 0.40s` | Collection is clean |
| Safe SQLite backend suite | `1863 passed, 72 skipped, 0 failed in 120.39s` | Default local backend tests — 100% clean pass after fixing flaky `test_browser_pool_hard_recycling` |
| Postgres local tests | `1907 passed, 28 skipped, 0 failed in 142.41s` | Verified Postgres integration suite (rate-limiter flaky collisions resolved) |
| Playwright browser e2e | `10 passed, 0 failed in 10.11s` | Verified browser e2e suite |
| Golden dataset live tests | `7 passed, 1 skipped in 42.74s` | Verified live target extraction; 1 skipped due to external httpbin.org 503 error |
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

- Passing local tests does not prove production readiness in the target environment.
- Browser tests prove local Playwright behavior, not broad anti-bot bypass.
- Postgres tests prove local repository/queue behavior, not production failover, scheduling, or backups.
- Postgres and Playwright browser tests were freshly run and validated 100% passing in this session, and Golden Dataset tests were verified (with 7/8 passing and httpbin.org skipped under expected 503 error). Docker image build and production Compose stack operations are documented historically.
- Route-auth tests verify registration and boundaries, but do not replace a security review or penetration test.

## Manual Tests

`backend/tests/manual_*.py` files are manual validation tools, not proof of default pytest health. Live network tests require explicit flags and should not be counted as safe offline tests.

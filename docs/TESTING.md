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
| Safe SQLite backend suite | `1862 passed, 72 skipped, 1 failed in 121.77s` | Default local backend tests — 1 pre-existing flaky failure (`test_browser_pool_hard_recycling`) |
| Postgres local tests | `1905 passed, 2 failed, 28 skipped in 142.64s` *(archived from prior refresh)* | Full Postgres suite — 2 pre-existing rate limiter test failures (shared state collision) |
| Playwright browser e2e | `1878 passed, 2 failed, 55 skipped in 124.65s` *(archived from prior refresh)* | Full browser suite — 2 pre-existing rate limiter test failures (shared state collision) |
| Golden dataset live tests | `8 passed in 51.02s` *(archived from prior refresh)* | Target sites extracted under modest F1 thresholds (lowest 0.650) |
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
- Postgres, Playwright browser, and Golden Dataset tests were freshly run in the prior session (2026-06-01) and results are archived here. Docker image build and production Compose stack operations are documented historically.
- Route-auth tests verify registration and boundaries, but do not replace a security review or penetration test.

## Manual Tests

`backend/tests/manual_*.py` files are manual validation tools, not proof of default pytest health. Live network tests require explicit flags and should not be counted as safe offline tests.

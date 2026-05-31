# Testing

**Date:** 2026-05-31  
**Status:** Current local testing truth

## Safe Local Baseline

Run local tests with SQLite and without loading local `.env` files:

```bash
PYTHONPATH=backend \
DATAFORGE_DOTENV_PATH=/dev/null \
DATAFORGE_STORAGE_BACKEND=sqlite \
python3 -m pytest -q backend/tests -o addopts=
```

Latest verified result in this workspace:

```text
1837 passed, 72 skipped in 105.19s
```

## Collection

```bash
PYTHONPATH=backend \
DATAFORGE_DOTENV_PATH=/dev/null \
DATAFORGE_STORAGE_BACKEND=sqlite \
python3 -m pytest --collect-only -q backend/tests backend/benchmarks -o addopts=
```

Latest verified result:

```text
1910 tests collected in 0.41s
```

## Optional Test Groups

Postgres tests require a reachable Postgres service:

```bash
PYTHONPATH=backend python3 -m pytest backend/tests --run-postgres -q -o addopts=
```

Golden dataset tests require reviewed target metadata, expected outputs, and permission to access the target sites:

```bash
PYTHONPATH=backend python3 -m pytest backend/tests/test_golden_dataset.py --run-golden-dataset -q -o addopts=
```

Browser/local-server E2E tests require Playwright and permission to bind a local HTTP server:

```bash
PYTHONPATH=backend python3 -m pytest backend/tests --run-browser -q -o addopts=
```

## Manual Scripts

`backend/tests/manual_*.py` scripts are not proof of default pytest health. They are import-safe after cleanup, but they remain manual validation tools.

## Rules

- Do not count skipped tests as passed.
- Do not claim Postgres support is verified unless `--run-postgres` is run against a live service.
- Do not claim golden dataset accuracy unless `--run-golden-dataset` is run with reviewed expected outputs.
- Do not claim production readiness from unit tests.
- Include the exact command and environment when reporting test results.

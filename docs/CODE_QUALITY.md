# Code Quality Standards

**Last refreshed:** 2026-06-02

This document defines expected quality checks. It is not proof that every lint/type/coverage check currently passes. Only fresh command output should be used as evidence.

## Current Verified Snapshot (freshly run in this session)

- `python3 -m compileall -q backend scripts architecture_validator.py` passed with no output.
- `PYTHONPATH=backend python3 architecture_validator.py` passed with `VALIDATION PASSED: Architecture is lawful.`
- Pytest collection completed with `1937 tests collected in 0.40s`.
- Safe SQLite backend suite passed with `1862 passed, 72 skipped, 1 failed in 121.77s` (1 pre-existing flaky failure in `test_browser_pool_hard_recycling`).
- Combined route-auth, production-security, and CORS preflight tests passed (archived result: `183 passed in 1.83s` from prior refresh).
- Benchmark smoke passed with `1 passed, 1 skipped in 0.26s`.
- Route auth matrix generated 81 route entries with correct enforcement classification.
- Production env placeholder rejection verified: `scripts/check_prod_env.py` intentionally fails on placeholder values.

## Results from Prior Refresh (not re-run in this session)

- Postgres optional tests: `1885 passed, 28 skipped in 138.54s` *(archived)*.
- Browser optional tests: `1858 passed, 55 skipped in 125.64s` *(archived)*.
- Golden dataset live tests: `8 passed in 53.97s` with modest enforced F1 thresholds *(archived)*.
- Local Compose smoke built image `796fe80630f771d4da8257eb7ec3f07a003f92f63d668ac1ffc3b43007ee9fc9` *(archived)*.

## Not Verified In This Snapshot

- `flake8`
- `mypy`
- coverage percentage
- target-environment Docker/Compose startup

## Required Checks

```bash
python3 -m compileall -q backend scripts architecture_validator.py
PYTHONPATH=backend python3 architecture_validator.py
PYTHONPATH=backend DATAFORGE_DOTENV_PATH=/dev/null DATAFORGE_STORAGE_BACKEND=sqlite python3 -m pytest --collect-only -q backend/tests backend/benchmarks -o addopts=
PYTHONPATH=backend DATAFORGE_DOTENV_PATH=/dev/null DATAFORGE_STORAGE_BACKEND=sqlite python3 -m pytest -q backend/tests -o addopts=
```

Optional, if installed:

```bash
python3 -m pyflakes backend/app scripts architecture_validator.py
python3 -m mypy backend/app --ignore-missing-imports
```

## Standards

- Keep generated files, logs, databases, caches, and lock files out of source control.
- Prefer centralized configuration over scattered environment reads in app code.
- Keep optional external-service tests explicitly marked and documented.
- Do not weaken security checks to make tests pass.
- Do not describe fixture or simulated benchmarks as real-world validation.
- Add focused tests for new behavior and regression tests for bug fixes.

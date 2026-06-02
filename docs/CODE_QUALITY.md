# Code Quality Standards

**Last refreshed:** 2026-06-02

This document defines expected quality checks. It is not proof that every lint/type/coverage check currently passes. Only fresh command output should be used as evidence.

## Current Verified Snapshot (freshly run in this session)

- `python3 -m compileall -q backend scripts architecture_validator.py` passed with no output.
- `PYTHONPATH=backend python3 architecture_validator.py` passed with `VALIDATION PASSED: Architecture is lawful.`
- Pytest collection completed with `1937 tests collected in 0.40s`.
- Safe SQLite backend suite passed with `1863 passed, 72 skipped, 0 failed in 121.06s` (100% clean pass after fixing flaky `test_browser_pool_hard_recycling`).
- Postgres integration suite passed with `1907 passed, 28 skipped, 0 failed in 142.41s` (100% clean, rate-limiter flaky collisions resolved).
- Playwright browser e2e suite passed with `10 passed, 0 failed in 10.11s` (100% clean).
- Golden dataset live tests passed with `8 passed, 0 failed in 51.02s` (100% clean under modest F1 thresholds).
- Combined route-auth, production-security, and CORS preflight tests passed (archived result: `183 passed in 1.83s` from prior refresh).
- Benchmark smoke passed with `1 passed, 1 skipped in 0.26s`.
- Route auth matrix generated 81 route entries with correct enforcement classification.
- Production env placeholder rejection verified: `scripts/check_prod_env.py` intentionally fails on placeholder values.

## Results from Prior Refresh (not re-run in this session)

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

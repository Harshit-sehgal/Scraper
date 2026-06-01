# Code Quality Standards

**Last refreshed:** 2026-06-01

This document defines expected quality checks. It is not proof that every lint/type/coverage check currently passes. Only fresh command output should be used as evidence.

## Current Verified Snapshot

- `python3 -m compileall -q backend scripts architecture_validator.py` passed with no output.
- `PYTHONPATH=backend python3 architecture_validator.py` passed with `VALIDATION PASSED: Architecture is lawful.`
- Pytest collection completed with `1916 tests collected in 0.40s`.
- Safe SQLite backend suite passed with `1843 passed, 72 skipped in 119.06s`.
- Combined route-auth, production-security, and CORS preflight tests passed with `183 passed in 1.83s`.
- Postgres optional tests passed with `1885 passed, 28 skipped in 138.54s`.
- Browser optional tests passed with `1858 passed, 55 skipped in 125.64s`.
- Golden dataset live tests passed with `8 passed in 53.97s` and modest enforced F1 thresholds.
- Local Compose smoke built image `796fe80630f771d4da8257eb7ec3f07a003f92f63d668ac1ffc3b43007ee9fc9` and passed backend, worker, Postgres, Nginx, Prometheus, Grafana health, container Chromium, and one deterministic worker job.

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

# Code Quality Standards

**Last refreshed:** 2026-06-01

This document defines expected quality checks. It is not proof that every lint/type/coverage check currently passes. Only fresh command output should be used as evidence.

## Current Verified Snapshot

- `python3 -m compileall -q backend scripts architecture_validator.py` passed with no output.
- `PYTHONPATH=backend python3 architecture_validator.py` passed with `VALIDATION PASSED: Architecture is lawful.`
- Pytest collection completed with `1912 tests collected in 0.41s`.
- Safe SQLite backend suite passed with `1839 passed, 72 skipped in 107.06s`.
- Route-auth tests passed with `134 passed in 1.25s`.
- Production security tests passed with `48 passed in 0.09s`.
- Docker image build passed locally with image `2d6822c8ca4f`.
- Local Compose smoke passed for backend, worker, Postgres, Nginx, Prometheus scrape, container Chromium, and a one-job worker path.

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

# Code Quality Standards

**Last refreshed:** 2026-06-08

This document defines expected quality checks. It is not proof that every lint/type/coverage check currently passes. Only fresh command output should be used as evidence.

## Current Verified Snapshot

For the latest verified syntax, lint, type checking (mypy), and pytest collection/passing results across all test groups and environments, see [AGENT_TRUTH.md](AGENT_TRUTH.md) and run `python3 scripts/validate_local.py --quick` (current exit status reported in `artifacts/validation/latest_summary.md`).

## Not Verified In This Snapshot

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
python3 -m ruff check backend/app backend/tests
python3 -m ruff format --check backend/app backend/tests
python3 -m mypy backend/app backend/tests
python3 -m bandit -r backend/app -q
```

## Standards

- Keep generated files, logs, databases, caches, and lock files out of source control.
- Prefer centralized configuration over scattered environment reads in app code.
- Keep optional external-service tests explicitly marked and documented.
- Do not weaken security checks to make tests pass.
- Do not describe fixture or simulated benchmarks as real-world validation.
- Add focused tests for new behavior and regression tests for bug fixes.

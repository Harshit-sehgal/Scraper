# Code Quality Standards

This document defines the expected quality checks for DataForge Scraper. It is not
proof that every check currently passes. Only fresh command output should be used as
evidence.

## Current Verified Snapshot

Verified on 2026-05-31:

- Verified: `python3 -m compileall -q backend scripts architecture_validator.py` passed.
- Verified: `python3 architecture_validator.py` passed with `VALIDATION PASSED: Architecture is lawful.`
- Verified: pytest collection for `backend/tests backend/benchmarks` completed with `1910 tests collected in 0.41s`.
- Verified: full default backend pytest suite passed with `1837 passed, 72 skipped in 105.19s`.
- Verified: `backend/tests/test_pyflakes_fixes.py` passed, which runs pyflakes over `backend/app` and `backend/tests`.

Not verified in this snapshot:

- `flake8` result.
- `mypy` result.
- coverage percentage.
- coverage percentage.

Do not claim zero lint/type errors unless the relevant commands have just been run.

## Required Checks

Run these before claiming code quality status:

```bash
python3 -m compileall -q backend scripts architecture_validator.py
```

```bash
python3 architecture_validator.py
```

```bash
PYTHONPATH=backend DATAFORGE_DOTENV_PATH=/dev/null DATAFORGE_STORAGE_BACKEND=sqlite \
  python3 -m pytest --collect-only -q backend/tests backend/benchmarks -o addopts=
```

```bash
PYTHONPATH=backend DATAFORGE_DOTENV_PATH=/dev/null DATAFORGE_STORAGE_BACKEND=sqlite \
  python3 -m pytest -q backend/tests -o addopts=
```

Optional, if installed:

```bash
flake8 backend/
```

```bash
mypy backend/app --ignore-missing-imports
```

```bash
pyflakes backend/app scripts
```

## Standards

- Keep generated files, logs, databases, caches, and lock files out of source control.
- Prefer centralized configuration over scattered direct environment reads in app code.
- Keep tests honest: skip optional external-service tests explicitly and document why.
- Do not weaken security checks to make tests pass.
- Do not describe fixture or simulated benchmarks as real-world validation.
- Add focused tests for new behavior and regression tests for bug fixes.
- Use clear exception handling; avoid silent broad `except` blocks unless intentionally
  documented.

## Formatting

The repository contains `.flake8` configuration. New Python code should remain readable,
typed where useful, and formatted consistently with nearby code. Use `black` only when
the scope is intentional; avoid broad formatting churn during unrelated fixes.

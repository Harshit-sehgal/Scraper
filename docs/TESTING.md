# Testing

## Verified Commands During Audit

```bash
python3 -m compileall -q .
PYTHONPATH=backend python3 -c "import app.main"
python3 -m pyflakes backend/app scripts architecture_validator.py
python3 -m mypy backend/app --ignore-missing-imports
PYTHONPATH=backend python3 architecture_validator.py
PYTHONPATH=backend python3 -m pytest --collect-only -q -o addopts=
PYTHONPATH=backend python3 -m pytest -q
```

The full pytest suite required running outside the default sandbox because local HTTP/browser tests need socket binding.

Latest verified full run:

```text
1657 passed, 54 skipped in 126.64s
```

## What Passing Local Tests Mean

Passing local tests means the checked code paths worked in the audited environment. It does not prove production readiness, live website reliability, Postgres readiness, or browser behavior in Docker.

## Known Test Gaps

- Postgres tests require explicit real-service validation.
- Several benchmark/manual files are not collected by pytest.
- Some tests use fixtures or simulations and should not be treated as live reliability proof.
- mypy is run without checking many untyped function bodies.
- CI status was not verified from GitHub during this local audit.

## Recommended CI Expansion

1. Default unit/integration test job.
2. Postgres service-container job with marked Postgres tests.
3. Playwright/browser job.
4. Production compose smoke job.
5. Route-level auth matrix.
6. Benchmark fixture job with golden outputs.

# `backend/manual/` — Manual exploratory scripts

These are **not** pytest tests. They are exploratory / smoke scripts that
hit a live DataForge API (typically `http://localhost:8000`) over HTTP
and are run by hand during development.

## Why are they here, not in `backend/tests/`?

- They make **live HTTP calls** and depend on a running server, so they
  would fail (or hang) under the default pytest run.
- Their naming (`manual_*.py`) deliberately does not match the
  `python_files = ["test_*.py"]` discovery rule, so pytest never picks
  them up.
- They were originally in `backend/tests/manual_test_*.py` but
  contributed noise to dir listings, coverage stats, and CI log lines.
  Moving them out clarifies the boundary between automated tests and
  developer-facing exploration scripts.

## How are they protected from breaking?

`backend/tests/test_manual_tests.py` still asserts that every script in
this directory imports cleanly and has no top-level side effects. So
syntax errors or accidental import-time HTTP calls will fail the suite.

## How do I run one?

```bash
# Start the API first
DATAFORGE_STORAGE_BACKEND=sqlite \
  PYTHONPATH=backend \
  python3 -m uvicorn app.main:app --port 8000

# Then run a manual script (PYTHONPATH=backend so `app` imports work
# inside the script):
PYTHONPATH=backend python3 backend/manual/manual_chennai.py
```

Do **not** add these to CI. They require a real running server and a
network-reachable target.

## Adding a new exploratory script

1. Add `backend/manual/manual_<name>.py`
2. Use a `if __name__ == "__main__":` guard so import is side-effect-free
3. Add the module name to `MANUAL_TEST_FILES` in
   `backend/tests/test_manual_tests.py`
4. Verify `python3 -m pytest backend/tests/test_manual_tests.py -q` passes

# Route Authorization Matrix

**Date:** 2026-05-31
**Status:** Generated from the registered FastAPI app

The route authorization matrix is generated from `app.main:app` rather than hand-written docs.

```bash
PYTHONPATH=backend \
DATAFORGE_DOTENV_PATH=/dev/null \
DATAFORGE_STORAGE_BACKEND=sqlite \
python3 scripts/route_auth_matrix.py --format markdown
```

JSON output is also available:

```bash
PYTHONPATH=backend \
DATAFORGE_DOTENV_PATH=/dev/null \
DATAFORGE_STORAGE_BACKEND=sqlite \
python3 scripts/route_auth_matrix.py --format json
```

## Current Generated Summary

Verified in this workspace:

```text
81 route entries
47 authenticated-user routes
15 operator-or-admin routes
11 admin routes
4 development-docs routes
3 public routes
1 metrics-token-if-configured route
```

## Current Security Findings

Verified:

- API mutation routes now require operator/admin or admin access in the generated matrix.
- Regression replay generation routes are operator/admin protected:
  - `POST /api/scraper/regressions/{entry_id}/generate-test`
  - `POST /api/scraper/regressions/generate-all-tests`
- `POST /api/system/merge/knowledge` is admin-only and still has an additional legacy `X-Admin-Key` check when `ADMIN_API_KEY` is configured.
- `/metrics` is token-protected only when `DATAFORGE_METRICS_TOKEN` is configured.
- FastAPI docs routes are registered in the app and must be disabled or blocked in production.

Unknown:

- This matrix proves route registration and dependency classification. It is not a penetration test.
- Production proxy behavior was not tested in this pass.
- Full browser/dashboard exposure was not tested in this pass.

## Enforcement Test

```bash
PYTHONPATH=backend \
DATAFORGE_DOTENV_PATH=/dev/null \
DATAFORGE_STORAGE_BACKEND=sqlite \
python3 -m pytest -q backend/tests/test_route_auth_matrix_generator.py backend/tests/test_route_auth_matrix.py -o addopts=
```

Latest verified result:

```text
134 passed in 1.88s
```

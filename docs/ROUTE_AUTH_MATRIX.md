# Route Authorization Matrix

**Last refreshed:** 2026-06-08
**Status:** Generated from the registered FastAPI app

Generate the matrix:

```bash
PYTHONPATH=backend DATAFORGE_DOTENV_PATH=/dev/null DATAFORGE_STORAGE_BACKEND=sqlite python3 scripts/route_auth_matrix.py --format markdown
```

## Current Generated Summary

```text
50 route entries
6 authenticated-user routes
26 operator-or-admin routes
10 admin routes
4 development-docs routes
3 public routes
1 metrics-token-if-configured route
```

## Public Route Justification

- `/` is a root status endpoint.
- `/health` is a liveness endpoint.
- `/ready` is a readiness endpoint; production responses should stay minimal.

Static dashboard mounts at `/app` and `/dashboard` are internal surfaces and should not be treated as public-product endpoints.

## Metrics And Docs

- `/metrics` requires `DATAFORGE_METRICS_TOKEN` only when that token is configured.
- FastAPI docs routes are disabled by app config when `DATAFORGE_ENV=production`.
- Local Compose verified Nginx returns 404 for public `/docs`, `/redoc`, `/openapi.json`, and `/metrics`; repeat this behind the target ingress.

## Enforcement Test

```bash
PYTHONPATH=backend DATAFORGE_DOTENV_PATH=/dev/null DATAFORGE_STORAGE_BACKEND=sqlite python3 -m pytest -q backend/tests/test_route_auth_matrix.py backend/tests/test_route_auth_matrix_generator.py backend/tests/test_check_prod_env.py backend/tests/test_prod_security_validator.py backend/tests/test_production_hardening.py::test_backend_cors_origins_enforcement -o addopts=
```

Latest verified result:

```text
183 passed in 1.83s
```

This proves route registration/dependency classification, production-secret validation tests, and backend CORS preflight behavior. It is not a penetration test.

# Phase 1 Changes — P0 Safety Fixes

## Changes Made

### 1. Production Startup Checks (backend/app/main.py)

Added a production safety block in `create_app()` that runs before the FastAPI app is created:

- **Dev auth check**: If `ENV` is `production` and `ALLOW_INSECURE_DEV_AUTH` is `True`, raises `RuntimeError`
- **Session secret check**: If `ENV` is `production` and `SESSION_SECRET` is empty, raises `RuntimeError`

This ensures the application fails closed in production if two critical misconfigurations are present.

### 2. Startup Safety Tests (backend/tests/test_p0_auth_tenant.py)

Added two test functions:

- `test_startup_fails_when_dev_auth_enabled_in_production`: Verifies the dev auth check
- `test_startup_fails_when_session_secret_missing_in_production`: Verifies the session secret check

Both tests:
- Use `monkeypatch` to set the environment to production with the unsafe condition
- Assert that `create_app()` raises `RuntimeError` with the expected error message

## Files Changed

1. `backend/app/main.py` — Added production startup checks
2. `backend/tests/test_p0_auth_tenant.py` — Added startup safety tests

## Verification

Due to Bash tool restrictions, the test suite could not be executed during this session.
The test file was inspected for correctness (import added, test functions structured properly).
Test collection (`python3 -m pytest backend/tests -q --co`) previously passed, indicating all imports resolve.

## Acceptance

- [x] Dev auth check added to `create_app()`
- [x] Session secret check added to `create_app()`
- [x] Tests added to `test_p0_auth_tenant.py`
- [ ] Test execution verified (blocked by tooling)

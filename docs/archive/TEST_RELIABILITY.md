# Test Reliability Documentation

## Overview

DataForge uses a comprehensive testing strategy to ensure reliability and prevent regressions.

## Test Categories

| Category | Marker | Description |
|----------|--------|-------------|
| Unit | `@pytest.mark.unit` | Fast tests that don't touch network, database, or filesystem |
| API | `@pytest.mark.api` | API contract tests using FastAPI's TestClient |
| Integration | `@pytest.mark.integration` | Tests requiring external services (skipped by default) |
| Postgres | `@pytest.mark.postgres` | Tests requiring PostgreSQL (via testcontainers) |
| Browser | `@pytest.mark.browser` | Tests requiring Playwright/browser runtime |
| Network | `@pytest.mark.network` | Tests making live DNS/HTTP calls |
| Slow | `@pytest.mark.slow` | Tests with expected runtime > 5s |

## Running Tests

```bash
# Run all tests (excluding flaky network tests)
make test

# Run with coverage
make test-coverage

# Run specific file
make test-file FILE=test_jobs_api.py

# Run reliability checks (with retries)
make test-reliability

# Detect flaky tests
make test-flaky
```

## Coverage Requirements

- **Global minimum:** 60%
- **Routers:** 70%
- **Services:** 65%
- **Auth:** 75%
- **Utils:** 60%

Coverage is enforced in CI via `--cov-fail-under=60`.

## Flaky Test Policy

1. **Detection:** Run `make test-flaky` to detect flaky tests
2. **Marking:** Add `@pytest.mark.flaky` to known flaky tests
3. **Fixing:** Investigate root cause and fix within 1 week
4. **Removal:** Remove `@pytest.mark.flaky` after fix is verified

## Timeout Policy

- **Global timeout:** 30 seconds per test
- **Override:** `@pytest.mark.timeout(N)` for longer tests
- **Slow tests:** Mark with `@pytest.mark.slow` for selective CI tiers

## DNS Isolation

All tests use a DNS stand-in to prevent real network access:
- `conftest.py` provides autouse fixture
- Tests marked `@pytest.mark.network` bypass isolation
- Tests marked `@pytest.mark.integration` can access external services

## CI Integration

```bash
# Full CI check
make validate

# Doctor check (environment validation)
make doctor

# API docs check (route inventory)
make api-docs-check
```

## Best Practices

1. **Write isolation tests first** - Don't depend on external services
2. **Use fixtures** - Share test setup via `conftest.py`
3. **Mark appropriately** - Use correct markers for test categories
4. **Keep tests fast** - Unit tests should complete in < 1s
5. **Clean up** - Use `tmp_path` fixture for filesystem tests
6. **No secrets** - Never hardcode API keys in tests

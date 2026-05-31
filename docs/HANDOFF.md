# DataForge Scraper Handoff

**Date:** 2026-05-31
**Status:** Current, truth-first handoff

This handoff supersedes older status notes. For exact current evidence, use
`PROJECT_STATUS.md`, `docs/TESTING.md`, and `docs/ROUTE_AUTH_MATRIX.md`.

## Current Position

DataForge Scraper is a pre-production FastAPI and Playwright web extraction
platform. It has job APIs, extraction modules, storage code, exports, telemetry,
diagnostics, security utilities, and internal dashboard files. It also contains
experimental adaptive and semantic modules that are not validated production
capabilities.

Do not describe the project as production-ready, universal, fully autonomous,
self-healing, anti-bot immune, or guaranteed accurate.

## Verified In This Cleanup Pass

- Default SQLite backend test suite: `1837 passed, 72 skipped in 105.19s`.
- Test collection: `1910 tests collected in 0.41s`.
- Benchmark smoke check: `1 passed in 0.36s`.
- Route authorization matrix: 81 registered route entries generated from the
  FastAPI app.
- Route-auth tests: `134 passed in 1.88s`.
- Production secret validation tests: `48 passed in 0.08s`.
- Architecture validator: `VALIDATION PASSED: Architecture is lawful.`
- Python compile check passed.
- Runtime artifacts were removed from source control and ignored.

Skipped tests are not counted as passed. Browser/local-server E2E, golden
dataset, and Postgres tests require explicit flags and environment support.

## Still Unverified

- Docker image build and production Compose startup.
- Real Postgres service behavior.
- Worker behavior against Postgres in a deployed environment.
- Nginx/proxy behavior.
- Browser runtime behavior outside the skipped default tests.
- Dashboard behavior under production CSP/session constraints.
- Live extraction accuracy on a real golden dataset.
- Real-world anti-bot effectiveness.
- Backup/restore, load, and failure-recovery procedures.

## Next Engineering Priorities

1. Reproduce the default SQLite test baseline from a clean checkout.
2. Run Postgres tests with a real service using `--run-postgres`.
3. Run browser/local-server E2E tests in an environment that permits local socket
   binding using `--run-browser`.
4. Build and smoke-test the Docker and production Compose stack.
5. Create a real golden dataset with expected outputs before publishing accuracy
   numbers.
6. Keep active docs aligned with command output; move stale reports to archive or
   clearly mark them historical.

## Allowed Claims

- Pre-production web extraction platform.
- FastAPI and Playwright backend.
- Configurable structured extraction.
- Local SQLite mode.
- CSV, JSON, and Excel exports.
- Telemetry and diagnostics.
- Route authorization matrix tooling.
- Experimental adaptive and semantic components.

## Banned Claims

- Production-ready.
- Universal scraper.
- Fully autonomous.
- Self-healing.
- Anti-bot immune.
- Guaranteed accurate.
- All tests pass unless the exact fresh command, pass count, and skip count are
  included.

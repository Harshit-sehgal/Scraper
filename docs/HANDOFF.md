# DataForge Scraper Handoff

**Date:** 2026-05-31 (updated)
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
- **Postgres backend tests**: `1881 passed, 28 skipped in 119.73s`
  (requires `--run-postgres` + live Postgres 16 container).
- **Browser E2E tests**: `39 passed in 10.76s`
  (requires `--run-browser` + Playwright with Chromium installed).
- Architecture validator: `VALIDATION PASSED: Architecture is lawful.`
- Python compile check passed.
- Runtime artifacts were removed from source control and ignored.

Skipped tests are not counted as passed. Golden dataset tests require
`--run-golden-dataset` flag and a configured `sites.json`.

## Still Unverified

- Docker Compose production stack (Nginx, Prometheus, Grafana) startup.
- Worker queue behavior against Postgres in a deployed environment.
- Nginx proxy behavior.
- Dashboard behavior under production CSP/session constraints.
- Live extraction accuracy on a real golden dataset.
- Real-world anti-bot effectiveness.
- Backup/restore, load, and failure-recovery procedures.

## Next Engineering Priorities

1. Reproduce the full test baseline (SQLite + Postgres + browser) from a clean checkout.
2. Build and smoke-test the Docker Compose production stack (Nginx, Prometheus, Grafana).
3. Create a real golden dataset with expected outputs before publishing accuracy numbers.
4. Harden dashboard session handling for production environments (move from sessionStorage
   to secure patterns).
5. Keep active docs aligned with command output; move stale reports to archive or clearly
   mark them historical.

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

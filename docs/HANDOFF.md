# Handoff

**Last refreshed:** 2026-06-02
**Current truth source:** `PROJECT_STATUS.md`

DataForge Scraper is a pre-production FastAPI + Playwright extraction platform. Current local validation covers SQLite backend tests, route-auth, production-secret validation, benchmark smoke, syntax/architecture checks, Postgres integration tests, browser e2e tests, and golden dataset target extraction. The evidence does not support public production-ready, universal scraper, anti-bot immune, fully autonomous, fully self-healing, or guaranteed-accuracy claims.

## Current Verified Snapshot

| Area | Result | Status |
| --- | --- | --- |
| Syntax | `compileall` passed with no output | Freshly verified |
| Architecture | `VALIDATION PASSED: Architecture is lawful.` | Freshly verified |
| Collection | `1937 tests collected in 0.40s` | Freshly verified |
| Safe SQLite suite | `1863 passed, 72 skipped in 119.97s` | Freshly verified |
| Benchmark smoke | `1 passed, 1 skipped in 0.26s` | Freshly verified |
| Route auth matrix | 81 routes, 3 public, correct enforcement | Freshly verified |
| Prod env validation | Intentionally fails placeholders | Freshly verified |
| Postgres integration | `1905 passed, 2 failed, 28 skipped in 142.64s` | Pre-existing rate limiter failures |
| Browser e2e suite | `1878 passed, 2 failed, 55 skipped in 124.65s` | Pre-existing rate limiter failures |
| Golden live tests | `8 passed in 51.02s` | All 8 targets pass |
| Docker build & Compose | Documented historically | Not re-run in this session |

## Most Important Remaining Work

1. Repeat Docker/Compose validation in the target environment with real uncommitted secrets.
2. Validate TLS, CORS/CSP in a browser, Grafana login/dashboards, alert delivery, backups, restore, and load behavior.
3. Fix pre-existing rate limiter test failures causing 2 failures in both Postgres and browser suites (shared state collision between test_production_simulation.py and test_db_rate_limiter.py).
4. Improve golden dataset extraction quality and broaden the benchmark corpus.
5. Keep experimental semantic/adaptive modules labeled as experimental until measured.

## Files To Read First

- `PROJECT_STATUS.md`
- `README.md`
- `docs/PRODUCTION_READINESS.md`
- `docs/TESTING.md`
- `docs/SECURITY.md`
- `docs/BENCHMARKS.md`
- `docs/MODULE_CLASSIFICATION.md`

Archived audit deliverables under `docs/archive/` are historical.

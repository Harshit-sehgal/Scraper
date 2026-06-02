# Handoff

**Last refreshed:** 2026-06-02
**Current truth source:** `PROJECT_STATUS.md`

DataForge Scraper is a pre-production FastAPI + Playwright extraction platform. Current local validation covers SQLite backend tests, route-auth, production-secret validation, benchmark smoke, syntax/architecture checks, Postgres integration tests, browser e2e tests, and golden dataset target extraction. Do not claim public production-ready, universal scraper, anti-bot immune, fully autonomous, fully self-healing, or guaranteed-accuracy as the evidence does not support them.

## Current Verified Snapshot

| Area | Result | Status |
| --- | --- | --- |
| Syntax | `compileall` passed with no output | Freshly verified |
| Architecture | `VALIDATION PASSED: Architecture is lawful.` | Freshly verified |
| Collection | `1937 tests collected in 0.40s` | Freshly verified |
| Safe SQLite suite | `1863 passed, 72 skipped, 0 failed in 120.39s` | Freshly verified |
| Benchmark smoke | `1 passed, 1 skipped in 0.26s` | Freshly verified |
| Route auth matrix | 81 routes, 3 public, correct enforcement | Freshly verified |
| Prod env validation | Intentionally fails placeholders | Freshly verified |
| Postgres integration | `1907 passed, 28 skipped, 0 failed in 142.41s` | Freshly verified (Rate limit flaky collisions resolved via unique keys) |
| Browser e2e suite | `10 passed, 0 failed in 10.11s` | Freshly verified e2e tests |
| Golden live tests | `7 passed, 1 skipped in 42.74s` | Freshly verified (1 skipped due to external httpbin.org 503 error) |
| Docker build & Compose | Documented historically | Not re-run in this session |

## Most Important Remaining Work

1. Repeat Docker/Compose validation in the target environment with real uncommitted secrets.
2. Validate TLS, CORS/CSP in a browser, Grafana login/dashboards, alert delivery, backups, restore, and load behavior.
3. Improve golden dataset extraction quality and broaden the benchmark corpus.
4. Keep experimental semantic/adaptive modules labeled as experimental until measured.

## Files To Read First

- `PROJECT_STATUS.md`
- `README.md`
- `docs/PRODUCTION_READINESS.md`
- `docs/TESTING.md`
- `docs/SECURITY.md`
- `docs/BENCHMARKS.md`
- `docs/MODULE_CLASSIFICATION.md`

Archived audit deliverables under `docs/archive/` are historical.

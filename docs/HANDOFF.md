# Handoff

**Last refreshed:** 2026-06-01
**Current truth source:** `PROJECT_STATUS.md`

DataForge Scraper is a pre-production FastAPI + Playwright extraction platform. The current evidence supports local SQLite, Postgres/testcontainers, route-auth, production-secret-validation, browser/local-server tests, Docker build, and a minimal local Compose worker smoke. It does not support production-ready, universal scraper, anti-bot immune, fully autonomous, fully self-healing, or guaranteed-accuracy claims.

## Current Verified Snapshot

| Area | Result |
| --- | --- |
| Syntax | `compileall` passed with no output |
| Architecture | `VALIDATION PASSED: Architecture is lawful.` |
| Collection | `1912 tests collected in 0.41s` |
| Safe SQLite suite | `1839 passed, 72 skipped in 107.06s` |
| Benchmark smoke | `1 passed in 0.27s` |
| Route auth tests | `134 passed in 1.25s` |
| Production secret tests | `48 passed in 0.09s` |
| Combined route/security tests | `182 passed in 1.31s` |
| Postgres optional suite | `1883 passed, 28 skipped in 129.55s` |
| Browser optional suite | `1856 passed, 55 skipped in 116.73s` |
| Docker build | Built `dataforge:local` image `2d6822c8ca4f` |
| Local Compose smoke | Backend/worker/Postgres healthy; Nginx health/readiness/app routes checked; docs/OpenAPI/metrics blocked; Prometheus targets up; container Chromium launched; one worker job completed with 1 record |
| Golden live tests | Stalled after one visible test; stopped |

## Most Important Remaining Work

1. Repeat Docker/Compose validation in the target environment with real uncommitted secrets.
2. Validate TLS, CORS/CSP in a browser, Grafana login/dashboards, alert delivery, backups, restore, and load behavior.
3. Add enforced thresholds and timeouts to golden dataset tests.
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

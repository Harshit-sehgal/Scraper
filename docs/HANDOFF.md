# Handoff

**Last refreshed:** 2026-06-01
**Current truth source:** `PROJECT_STATUS.md`

DataForge Scraper is a pre-production FastAPI + Playwright extraction platform. The current refresh supports local SQLite, Postgres/testcontainers, browser/local-server tests, route-auth, production-secret validation, CORS preflight checks, benchmark smoke checks, golden dataset checks with modest thresholds, and a local production-like Compose smoke. The evidence does not support public production-ready, universal scraper, anti-bot immune, fully autonomous, fully self-healing, or guaranteed-accuracy claims.

## Current Verified Snapshot

| Area | Result |
| --- | --- |
| Syntax | `compileall` passed with no output |
| Architecture | `VALIDATION PASSED: Architecture is lawful.` |
| Collection | `1914 tests collected in 0.40s` |
| Safe SQLite suite | `1841 passed, 72 skipped in 116.54s` |
| Benchmark smoke | `1 passed in 0.25s` |
| Combined route/security/CORS tests | `183 passed in 1.83s` |
| Postgres optional suite | `1885 passed, 28 skipped in 138.54s` |
| Browser optional suite | `1858 passed, 55 skipped in 125.64s` |
| Docker build | Local smoke built image `796fe80630f771d4da8257eb7ec3f07a003f92f63d668ac1ffc3b43007ee9fc9` |
| Local Compose smoke | Passed for backend/worker/Postgres, Nginx route checks, Prometheus targets, Grafana health, container Chromium, CORS preflight, backup/restore smoke, and one deterministic worker job with 4 records |
| Golden live tests | `8 passed in 53.97s` with lowest F1 `0.650` |

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

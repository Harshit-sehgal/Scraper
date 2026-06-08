# Handoff

**Last refreshed:** 2026-06-08
**Current truth source:** `PROJECT_STATUS.md`

DataForge Scraper is a pre-production FastAPI + Playwright extraction platform. Current local validation covers SQLite backend tests, route-auth, production-secret validation, benchmark smoke, syntax/architecture checks, Postgres integration tests, browser e2e tests, and golden dataset target extraction. Do not claim public production-ready, universal scraper, anti-bot immune, fully autonomous, fully self-healing, or guaranteed-accuracy as the evidence does not support them.

## Current Verified Snapshot

For the latest verified snapshot, including exact test execution numbers, syntax compilation checks, architecture compliance validations, and docker/Compose environment statuses, see [PROJECT_STATUS.md](../PROJECT_STATUS.md).

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

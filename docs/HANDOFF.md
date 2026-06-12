# Handoff

> Historical note:
> This document may contain older project status claims.
> For current verified status, see `docs/AGENT_TRUTH.md`.
>
> Verification warning:
> Current validation, benchmark, route-auth, Postgres, browser, and golden-dataset claims in this file are not automatically trusted.
> Current readiness must be checked through `docs/AGENT_TRUTH.md` and the latest validation reports.

**Last refreshed:** 2026-06-08
**Current truth source:** `docs/AGENT_TRUTH.md`

DataForge Scraper is a pre-production FastAPI + Playwright extraction platform. Current local validation covers SQLite backend tests, route-auth, production-secret validation, benchmark smoke, syntax/architecture checks, Postgres integration tests, browser e2e tests, and golden dataset target extraction. Do not claim public production-ready, universal scraper, anti-bot immune, fully autonomous, fully self-healing, or guaranteed-accuracy as the evidence does not support them.

## Current Verified Snapshot

For the latest verified snapshot, including exact test execution numbers, syntax compilation checks, architecture compliance validations, and docker/Compose environment statuses, see [AGENT_TRUTH.md](AGENT_TRUTH.md).

## Most Important Remaining Work

1. Repeat Docker/Compose validation in the target environment with real uncommitted secrets.
2. Validate TLS, CORS/CSP in a browser, Grafana login/dashboards, alert delivery, backups, restore, and load behavior.
3. Improve golden dataset extraction quality and broaden the benchmark corpus.
4. Keep experimental semantic/adaptive modules labeled as experimental until measured.

## Files To Read First

- `docs/AGENT_TRUTH.md`
- `PROJECT_STATUS.md` (historical)
- `README.md`
- `docs/PRODUCTION_READINESS.md`
- `docs/TESTING.md`
- `docs/SECURITY.md`
- `docs/BENCHMARKS.md`
- `docs/MODULE_CLASSIFICATION.md`

Archived audit deliverables under `docs/archive/` are historical.

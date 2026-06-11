# API (Experimental)

**This file is auto-generated. Do not edit by hand.**

**Generated:** 2026-06-11 18:03:55 UTC
**Mode:** experimental routes **enabled** (`DATAFORGE_ENABLE_EXPERIMENTAL_ROUTES=true`).
**Verification command:**

```
python3 scripts/route_inventory_split.py --write
```

These endpoints are gated on the ``ENABLE_EXPERIMENTAL_ROUTES`` flag
and are not part of the stable v1 contract. They may change or be
removed without notice. They are not covered by the SaaS readiness
acceptance gate and must not be advertised to paying customers
without explicit opt-in.

For the production API surface, see [`API_STABLE.md`](API_STABLE.md).
For the diff between stable and experimental, see
[`API_EXPERIMENTAL_DIFF.md`](API_EXPERIMENTAL_DIFF.md).

## Job and Result Routes

| Method | Path |
| --- | --- |
| DELETE | `/api/jobs/cleanup/terminal` |
| DELETE | `/api/jobs/{job_id}` |
| GET | `/api/jobs` |
| GET | `/api/jobs/{job_id}` |
| GET | `/api/jobs/{job_id}/events` |
| GET | `/api/jobs/{job_id}/export/csv` |
| GET | `/api/jobs/{job_id}/export/excel` |
| GET | `/api/jobs/{job_id}/export/json` |
| GET | `/api/jobs/{job_id}/results` |
| POST | `/api/jobs` |
| POST | `/api/jobs/{job_id}/backfill-metadata` |
| POST | `/api/jobs/{job_id}/cancel` |
| POST | `/api/jobs/{job_id}/reclean` |

## Recycle Bin Routes

| Method | Path |
| --- | --- |
| DELETE | `/api/recycle_bin` |
| DELETE | `/api/recycle_bin/{job_id}` |
| GET | `/api/recycle_bin` |
| POST | `/api/recycle_bin/{job_id}/restore` |

## Discovery and URL Analysis

| Method | Path |
| --- | --- |
| POST | `/api/discover` |
| POST | `/api/schema/suggest` |
| POST | `/api/url/analyze` |

## Scraper/Telemetry Routes

| Method | Path |
| --- | --- |
| DELETE | `/api/scraper/telemetry` |
| GET | `/api/scraper/browser` |
| GET | `/api/scraper/config` |
| GET | `/api/scraper/economics` |
| GET | `/api/scraper/health/domain/{domain}` |
| GET | `/api/scraper/health/domains` |
| GET | `/api/scraper/health/legacy` |
| GET | `/api/scraper/health/summary` |
| GET | `/api/scraper/memory/stats` |
| GET | `/api/scraper/ml/optimize/domain/{domain}/history` |
| GET | `/api/scraper/regressions` |
| GET | `/api/scraper/regressions/{entry_id}` |
| GET | `/api/scraper/selectors/domain/{domain}` |
| GET | `/api/scraper/selectors/low-confidence` |
| GET | `/api/scraper/selectors/stats` |
| GET | `/api/scraper/stats` |
| GET | `/api/scraper/strategy/domain/{domain}` |
| GET | `/api/scraper/strategy/recommend/{domain}` |
| GET | `/api/scraper/strategy/report` |
| GET | `/api/scraper/telemetry` |
| GET | `/api/scraper/trends` |
| GET | `/api/scraper/trends/{domain}` |
| POST | `/api/scraper/diagnostics` |
| POST | `/api/scraper/ml/learn` |
| POST | `/api/scraper/ml/optimize/domain/{domain}` |
| POST | `/api/scraper/regressions/generate-all-tests` |
| POST | `/api/scraper/regressions/{entry_id}/generate-test` |
| POST | `/api/scraper/selectors/cleanup` |
| POST | `/api/scraper/strategy/evolve/{domain}` |
| POST | `/api/scraper/strategy/record` |

## Operator and System Routes

| Method | Path |
| --- | --- |
| DELETE | `/api/operator/denylist` |
| GET | `/api/operator/dashboard` |
| GET | `/api/operator/denylist` |
| GET | `/api/operator/health` |
| GET | `/api/operator/mode` |
| GET | `/api/operator/predictions` |
| GET | `/api/operator/predictions/{domain}` |
| GET | `/api/system/acquisition/telemetry` |
| GET | `/api/system/agency` |
| GET | `/api/system/crystalline` |
| GET | `/api/system/diagnostics/export` |
| GET | `/api/system/domain-policy` |
| GET | `/api/system/export/knowledge` |
| GET | `/api/system/history/topology` |
| GET | `/api/system/observability` |
| GET | `/api/system/rate-limit-stats` |
| GET | `/api/system/replay/chain` |
| GET | `/api/system/replay/events` |
| GET | `/api/system/replay/status` |
| GET | `/api/system/search` |
| GET | `/api/system/status` |
| GET | `/api/system/storage/status` |
| GET | `/api/system/topology` |
| POST | `/api/operator/denylist` |
| POST | `/api/operator/mode` |
| POST | `/api/system/csp-violations` |
| POST | `/api/system/merge/knowledge` |
| POST | `/api/system/refactor/compress` |
| POST | `/api/system/scheduler/step` |

## Session/Auth Routes

| Method | Path |
| --- | --- |
| DELETE | `/api/session` |
| GET | `/api/session/me` |
| POST | `/api/session` |

## Export Routes

| Method | Path |
| --- | --- |
| POST | `/api/exports/batch` |

## Other

| Method | Path |
| --- | --- |
| GET | `/api/saas/aup/status` |
| POST | `/api/saas/aup/accept` |

**Total routes:** 85

# API (Experimental Diff)

**This file is auto-generated. Do not edit by hand.**

**Generated:** 2026-06-22 01:44:04 UTC
**Mode:** `experimental_routes - stable_routes`

This is the set of routes that are exposed **only** when
``DATAFORGE_ENABLE_EXPERIMENTAL_ROUTES=true``. Every row below is a
route that does not exist in the production code path. The list is
the diff between [`API_EXPERIMENTAL.md`](API_EXPERIMENTAL.md) and
[`API_STABLE.md`](API_STABLE.md).

| Method | Path |
| --- | --- |
| GET | `/api/operator/dashboard` |
| GET | `/api/operator/health` |
| GET | `/api/operator/mode` |
| GET | `/api/operator/predictions` |
| GET | `/api/operator/predictions/{domain}` |
| GET | `/api/scraper/economics` |
| GET | `/api/scraper/health/domain/{domain}` |
| GET | `/api/scraper/health/domains` |
| GET | `/api/scraper/health/summary` |
| GET | `/api/scraper/ml/optimize/domain/{domain}/history` |
| GET | `/api/scraper/strategy/domain/{domain}` |
| GET | `/api/scraper/strategy/recommend/{domain}` |
| GET | `/api/scraper/strategy/report` |
| GET | `/api/scraper/trends` |
| GET | `/api/scraper/trends/{domain}` |
| GET | `/api/system/acquisition/telemetry` |
| GET | `/api/system/agency` |
| GET | `/api/system/crystalline` |
| GET | `/api/system/domain-policy` |
| GET | `/api/system/export/knowledge` |
| GET | `/api/system/history/topology` |
| GET | `/api/system/observability` |
| GET | `/api/system/replay/chain` |
| GET | `/api/system/replay/events` |
| GET | `/api/system/replay/status` |
| GET | `/api/system/search` |
| GET | `/api/system/topology` |
| POST | `/api/operator/mode` |
| POST | `/api/scraper/ml/learn` |
| POST | `/api/scraper/ml/optimize/domain/{domain}` |
| POST | `/api/scraper/strategy/evolve/{domain}` |
| POST | `/api/scraper/strategy/record` |
| POST | `/api/system/merge/knowledge` |
| POST | `/api/system/refactor/compress` |
| POST | `/api/system/scheduler/step` |

**Experimental-only routes:** 35

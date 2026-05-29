# API

This route list was generated from the FastAPI app during the audit. Production disables `/docs`, `/redoc`, and `/openapi.json` through app settings and Nginx.

## Public / Probe Routes

| Method | Path | Access |
| --- | --- | --- |
| GET | `/` | Public |
| GET | `/health` | Public liveness |
| GET | `/ready` | Public readiness; production response is minimal |
| GET | `/app` | Static main dashboard |
| GET | `/dashboard` | Static semantic dashboard |

## Job and Result Routes

| Method | Path | Intended Access |
| --- | --- | --- |
| GET | `/api/jobs` | Authenticated user |
| GET | `/api/jobs/{job_id}` | Authenticated user |
| GET | `/api/jobs/{job_id}/results` | Authenticated user |
| POST | `/api/jobs` | Operator or admin |
| POST | `/api/jobs/{job_id}/cancel` | Operator or admin |
| POST | `/api/jobs/{job_id}/reclean` | Operator or admin |
| POST | `/api/jobs/{job_id}/backfill-metadata` | Operator or admin |
| DELETE | `/api/jobs/{job_id}` | Admin |
| DELETE | `/api/jobs/cleanup/terminal` | Admin |
| GET | `/api/jobs/{job_id}/export/csv` | Authenticated user |
| GET | `/api/jobs/{job_id}/export/json` | Authenticated user |
| GET | `/api/jobs/{job_id}/export/excel` | Authenticated user |

## Recycle Bin Routes

| Method | Path | Intended Access |
| --- | --- | --- |
| GET | `/api/recycle_bin` | Authenticated user |
| POST | `/api/recycle_bin/{job_id}/restore` | Admin |
| DELETE | `/api/recycle_bin/{job_id}` | Admin |
| DELETE | `/api/recycle_bin` | Admin |

## Discovery and URL Analysis

| Method | Path | Intended Access |
| --- | --- | --- |
| POST | `/api/discover` | Operator or admin |
| POST | `/api/schema/suggest` | Operator or admin |
| POST | `/api/url/analyze` | Operator or admin |

## Scraper/Telemetry Routes

Most scraper mutation or diagnostic routes should be operator/admin only. Read-only telemetry routes still require API authentication when keys are configured.

Important routes include `/api/scraper/config`, `/api/scraper/telemetry`, `/api/scraper/stats`, `/api/scraper/browser`, `/api/scraper/diagnostics`, `/api/scraper/regressions/*`, `/api/scraper/selectors/*`, `/api/scraper/ml/*`, and `/api/scraper/strategy/*`.

## Operator and System Routes

Operator routes include `/api/operator/mode`, `/api/operator/dashboard`, `/api/operator/predictions`, and `/api/operator/health`.

System routes include `/api/system/status`, `/api/system/topology`, `/api/system/export/knowledge`, `/api/system/merge/knowledge`, `/api/system/scheduler/step`, `/api/system/refactor/compress`, and `/api/system/diagnostics/export`.

Admin-only routes include system merge, scheduler step, refactor compression, diagnostics export, and operator mode changes.

## Metrics

`GET /metrics` is protected by `DATAFORGE_METRICS_TOKEN` if configured. Production Nginx returns 404 for public `/metrics` and Prometheus is expected to scrape internally.

## Auth Notes

- `X-API-Key` or `Authorization: Bearer <token>` can provide user/operator/admin credentials.
- `X-Admin-Key` is accepted for admin compatibility.
- In development with no configured keys, routes may be permissive. Do not use that mode for production.

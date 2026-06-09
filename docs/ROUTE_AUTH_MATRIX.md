# Route Authorization Matrix

Generated from the registered FastAPI app. This is route-registration evidence, not a penetration test.

| Method | Path | Access | Enforcement | Notes |
| --- | --- | --- | --- | --- |
| `GET` | `/` | public | no API route auth | Dashboard/static/probe route; review before public exposure. |
| `POST` | `/api/discover` | operator-or-admin | require_role([admin, operator]) |  |
| `POST` | `/api/exports/batch` | operator-or-admin | require_role([admin, operator]) |  |
| `GET` | `/api/jobs` | authenticated-user | global /api/* API-key middleware |  |
| `POST` | `/api/jobs` | operator-or-admin | require_role([admin, operator]) |  |
| `DELETE` | `/api/jobs/cleanup/terminal` | admin | require_role([admin]) |  |
| `DELETE` | `/api/jobs/{job_id}` | admin | require_role([admin]) |  |
| `GET` | `/api/jobs/{job_id}` | authenticated-user | global /api/* API-key middleware |  |
| `POST` | `/api/jobs/{job_id}/backfill-metadata` | operator-or-admin | require_role([admin, operator]) |  |
| `POST` | `/api/jobs/{job_id}/cancel` | operator-or-admin | require_role([admin, operator]) |  |
| `GET` | `/api/jobs/{job_id}/events` | authenticated-user | global /api/* API-key middleware |  |
| `GET` | `/api/jobs/{job_id}/export/csv` | operator-or-admin | require_role([admin, operator]) |  |
| `GET` | `/api/jobs/{job_id}/export/excel` | operator-or-admin | require_role([admin, operator]) |  |
| `GET` | `/api/jobs/{job_id}/export/json` | operator-or-admin | require_role([admin, operator]) |  |
| `POST` | `/api/jobs/{job_id}/reclean` | operator-or-admin | require_role([admin, operator]) |  |
| `GET` | `/api/jobs/{job_id}/results` | authenticated-user | global /api/* API-key middleware |  |
| `DELETE` | `/api/recycle_bin` | admin | require_role([admin]) |  |
| `GET` | `/api/recycle_bin` | authenticated-user | global /api/* API-key middleware |  |
| `DELETE` | `/api/recycle_bin/{job_id}` | admin | require_role([admin]) |  |
| `POST` | `/api/recycle_bin/{job_id}/restore` | admin | require_role([admin]) |  |
| `POST` | `/api/schema/suggest` | operator-or-admin | require_role([admin, operator]) |  |
| `GET` | `/api/scraper/browser` | operator-or-admin | require_role([admin, operator]) |  |
| `GET` | `/api/scraper/config` | operator-or-admin | require_role([admin, operator]) |  |
| `POST` | `/api/scraper/diagnostics` | operator-or-admin | require_role([admin, operator]) |  |
| `GET` | `/api/scraper/health/legacy` | operator-or-admin | require_role([admin, operator]) |  |
| `GET` | `/api/scraper/memory/stats` | operator-or-admin | require_role([admin, operator]) |  |
| `GET` | `/api/scraper/regressions` | operator-or-admin | require_role([admin, operator]) |  |
| `POST` | `/api/scraper/regressions/generate-all-tests` | admin | require_role([admin]) |  |
| `GET` | `/api/scraper/regressions/{entry_id}` | operator-or-admin | require_role([admin, operator]) |  |
| `POST` | `/api/scraper/regressions/{entry_id}/generate-test` | admin | require_role([admin]) |  |
| `POST` | `/api/scraper/selectors/cleanup` | admin | require_role([admin]) |  |
| `GET` | `/api/scraper/selectors/domain/{domain}` | operator-or-admin | require_role([admin, operator]) |  |
| `GET` | `/api/scraper/selectors/low-confidence` | operator-or-admin | require_role([admin, operator]) |  |
| `GET` | `/api/scraper/selectors/stats` | operator-or-admin | require_role([admin, operator]) |  |
| `GET` | `/api/scraper/stats` | operator-or-admin | require_role([admin, operator]) |  |
| `DELETE` | `/api/scraper/telemetry` | admin | require_role([admin]) |  |
| `GET` | `/api/scraper/telemetry` | operator-or-admin | require_role([admin, operator]) |  |
| `DELETE` | `/api/session` | public | exempt from API-key middleware | Session self-service auth; separate cookie-based flow. |
| `POST` | `/api/session` | public | exempt from API-key middleware | Session self-service auth; separate cookie-based flow. |
| `GET` | `/api/session/me` | public | exempt from API-key middleware | Session self-service auth; separate cookie-based flow. |
| `POST` | `/api/system/csp-violations` | public | exempt from API-key middleware | Browser-generated CSP report; no API key possible. |
| `GET` | `/api/system/diagnostics/export` | admin | require_role([admin]) |  |
| `GET` | `/api/system/rate-limit-stats` | operator-or-admin | require_role([admin, operator]) |  |
| `GET` | `/api/system/status` | operator-or-admin | require_role([admin, operator]) |  |
| `GET` | `/api/system/storage/status` | operator-or-admin | require_role([admin, operator]) |  |
| `POST` | `/api/url/analyze` | operator-or-admin | require_role([admin, operator]) |  |
| `GET` | `/docs` | development-docs | FastAPI docs route plus production settings/proxy | Development-only route; must be disabled in production. |
| `GET` | `/docs/oauth2-redirect` | development-docs | FastAPI docs route plus production settings/proxy | Development-only route; must be disabled in production. |
| `GET` | `/health` | public | no API route auth | Dashboard/static/probe route; review before public exposure. |
| `GET` | `/metrics` | metrics-token-if-configured | settings.METRICS_TOKEN check in endpoint | Metrics token check active in production only. |
| `GET` | `/openapi.json` | development-docs | FastAPI docs route plus production settings/proxy | Development-only route; must be disabled in production. |
| `GET` | `/ready` | public | no API route auth | Dashboard/static/probe route; review before public exposure. |
| `GET` | `/redoc` | development-docs | FastAPI docs route plus production settings/proxy | Development-only route; must be disabled in production. |

# API (Stable)

**This file is auto-generated. Do not edit by hand.**

**Generated:** 2026-06-17 11:09:59 UTC
**Mode:** experimental routes **disabled** (`DATAFORGE_ENABLE_EXPERIMENTAL_ROUTES=false`).
**Verification command:**

```
python3 scripts/route_inventory_split.py --write
```

This is the source of truth for the production API surface. Anything
listed here is safe to depend on; anything not listed is not in the
production code path. Experimental / research routes are listed in
[`API_EXPERIMENTAL.md`](API_EXPERIMENTAL.md); the diff between the two
files is [`API_EXPERIMENTAL_DIFF.md`](API_EXPERIMENTAL_DIFF.md).

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
| GET | `/api/scraper/health/legacy` |
| GET | `/api/scraper/memory/stats` |
| GET | `/api/scraper/regressions` |
| GET | `/api/scraper/regressions/{entry_id}` |
| GET | `/api/scraper/selectors/domain/{domain}` |
| GET | `/api/scraper/selectors/low-confidence` |
| GET | `/api/scraper/selectors/stats` |
| GET | `/api/scraper/stats` |
| GET | `/api/scraper/telemetry` |
| POST | `/api/scraper/diagnostics` |
| POST | `/api/scraper/regressions/generate-all-tests` |
| POST | `/api/scraper/regressions/{entry_id}/generate-test` |
| POST | `/api/scraper/selectors/cleanup` |

## Operator and System Routes

| Method | Path |
| --- | --- |
| DELETE | `/api/operator/denylist` |
| GET | `/api/operator/denylist` |
| GET | `/api/system/audit-log` |
| GET | `/api/system/diagnostics/export` |
| GET | `/api/system/manifest` |
| GET | `/api/system/rate-limit-stats` |
| GET | `/api/system/status` |
| GET | `/api/system/storage/status` |
| POST | `/api/operator/denylist` |
| POST | `/api/system/csp-violations` |

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
| DELETE | `/api/auth-profiles/{profile_id}` |
| DELETE | `/api/saas/memberships/{membership_id}` |
| DELETE | `/api/saas/projects/{project_id}/keys/{key_id}` |
| DELETE | `/api/scheduled/{job_id}` |
| DELETE | `/api/user/data` |
| DELETE | `/api/workflows/{workflow_id}` |
| GET | `/api/auth-profiles` |
| GET | `/api/auth-profiles/{profile_id}` |
| GET | `/api/billing/subscriptions` |
| GET | `/api/billing/subscriptions/{customer_id}` |
| GET | `/api/intelligence/analyze-url` |
| GET | `/api/saas/aup/status` |
| GET | `/api/saas/me` |
| GET | `/api/saas/orgs` |
| GET | `/api/saas/orgs/{org_id}` |
| GET | `/api/saas/orgs/{org_id}/members` |
| GET | `/api/saas/orgs/{org_id}/projects` |
| GET | `/api/saas/plan` |
| GET | `/api/saas/projects/{project_id}` |
| GET | `/api/saas/projects/{project_id}/keys` |
| GET | `/api/scheduled` |
| GET | `/api/scheduled/{job_id}` |
| GET | `/api/scheduled/{job_id}/changes` |
| GET | `/api/workflows` |
| GET | `/api/workflows/{workflow_id}` |
| GET | `/api/workflows/{workflow_id}/runs` |
| GET | `/api/workflows/{workflow_id}/runs/{run_id}` |
| PATCH | `/api/workflows/{workflow_id}` |
| POST | `/api/auth-profiles` |
| POST | `/api/auth-profiles/{profile_id}/complete-login` |
| POST | `/api/auth-profiles/{profile_id}/revoke` |
| POST | `/api/auth-profiles/{profile_id}/start-login` |
| POST | `/api/auth-profiles/{profile_id}/validate` |
| POST | `/api/billing/webhook` |
| POST | `/api/saas/aup/accept` |
| POST | `/api/saas/orgs` |
| POST | `/api/saas/projects` |
| POST | `/api/saas/projects/{project_id}/keys` |
| POST | `/api/saas/signup` |
| POST | `/api/scheduled` |
| POST | `/api/workflow-drafts/from-url-analysis` |
| POST | `/api/workflow-drafts/{draft_id}/detect-fields` |
| POST | `/api/workflow-drafts/{draft_id}/manual-mapping` |
| POST | `/api/workflows` |
| POST | `/api/workflows/{workflow_id}/preview` |
| POST | `/api/workflows/{workflow_id}/run` |
| PUT | `/api/scheduled/{job_id}` |
| PUT | `/api/workflows/{workflow_id}` |

**Total routes:** 98

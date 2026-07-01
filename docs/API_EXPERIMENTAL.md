# API (Experimental)

**This file is auto-generated. Do not edit by hand.**

**Generated:** 2026-07-01 12:24:30 UTC
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
| DELETE | `/api/jobs/{job_id}/notification-channels/{channel_id}` |
| DELETE | `/api/jobs/{job_id}/results` |
| GET | `/api/jobs` |
| GET | `/api/jobs/{job_id}` |
| GET | `/api/jobs/{job_id}/cascade-trace` |
| GET | `/api/jobs/{job_id}/debug` |
| GET | `/api/jobs/{job_id}/diff` |
| GET | `/api/jobs/{job_id}/events` |
| GET | `/api/jobs/{job_id}/export/csv` |
| GET | `/api/jobs/{job_id}/export/excel` |
| GET | `/api/jobs/{job_id}/export/json` |
| GET | `/api/jobs/{job_id}/network-log` |
| GET | `/api/jobs/{job_id}/notification-channels` |
| GET | `/api/jobs/{job_id}/quality` |
| GET | `/api/jobs/{job_id}/quality/trends` |
| GET | `/api/jobs/{job_id}/results` |
| GET | `/api/jobs/{job_id}/screenshot` |
| GET | `/api/jobs/{job_id}/structured-events` |
| PATCH | `/api/jobs/{job_id}/extraction` |
| PATCH | `/api/jobs/{job_id}/fetch-strategy` |
| PATCH | `/api/jobs/{job_id}/headers` |
| PATCH | `/api/jobs/{job_id}/notification-channels/{channel_id}` |
| PATCH | `/api/jobs/{job_id}/results/{record_id}` |
| PATCH | `/api/jobs/{job_id}/strategy` |
| PATCH | `/api/jobs/{job_id}/user-agent` |
| PATCH | `/api/jobs/{job_id}/wait-conditions` |
| PATCH | `/api/jobs/{job_id}/webhook` |
| POST | `/api/jobs` |
| POST | `/api/jobs/batch` |
| POST | `/api/jobs/{job_id}/cancel` |
| POST | `/api/jobs/{job_id}/clone` |
| POST | `/api/jobs/{job_id}/email` |
| POST | `/api/jobs/{job_id}/notification-channels` |
| POST | `/api/jobs/{job_id}/reclean` |
| POST | `/api/jobs/{job_id}/webhook/redeliver` |

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
| POST | `/api/discover/sitemap` |
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
| POST | `/api/scraper/preview` |
| POST | `/api/scraper/regressions/generate-all-tests` |
| POST | `/api/scraper/regressions/{entry_id}/generate-test` |
| POST | `/api/scraper/screenshot` |
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
| GET | `/api/system/audit-log` |
| GET | `/api/system/crystalline` |
| GET | `/api/system/domain-policy` |
| GET | `/api/system/export/knowledge` |
| GET | `/api/system/extraction-health` |
| GET | `/api/system/extraction-rate` |
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
| DELETE | `/api/auth-profiles/{profile_id}` |
| DELETE | `/api/saas/memberships/{membership_id}` |
| DELETE | `/api/saas/orgs/{org_id}` |
| DELETE | `/api/saas/projects/{project_id}` |
| DELETE | `/api/saas/projects/{project_id}/keys/{key_id}` |
| DELETE | `/api/scheduled/{job_id}` |
| DELETE | `/api/templates/{template_id}` |
| DELETE | `/api/user/data` |
| DELETE | `/api/workflows/{workflow_id}` |
| GET | `/api/auth-profiles` |
| GET | `/api/auth-profiles/{profile_id}` |
| GET | `/api/billing/stub-return/{plan_tier}/{request_id}` |
| GET | `/api/billing/subscriptions` |
| GET | `/api/billing/subscriptions/{customer_id}` |
| GET | `/api/download/{filename}` |
| GET | `/api/reviews` |
| GET | `/api/reviews/{review_id}` |
| GET | `/api/saas/aup/status` |
| GET | `/api/saas/email-verification/status` |
| GET | `/api/saas/invitations/pending` |
| GET | `/api/saas/me` |
| GET | `/api/saas/orgs` |
| GET | `/api/saas/orgs/{org_id}` |
| GET | `/api/saas/orgs/{org_id}/invitations` |
| GET | `/api/saas/orgs/{org_id}/members` |
| GET | `/api/saas/orgs/{org_id}/projects` |
| GET | `/api/saas/plan` |
| GET | `/api/saas/projects/{project_id}` |
| GET | `/api/saas/projects/{project_id}/keys` |
| GET | `/api/saas/usage` |
| GET | `/api/scheduled` |
| GET | `/api/scheduled/{job_id}` |
| GET | `/api/scheduled/{job_id}/changes` |
| GET | `/api/templates` |
| GET | `/api/templates/{template_id}` |
| GET | `/api/usage/stats` |
| GET | `/api/workflows` |
| GET | `/api/workflows/{workflow_id}` |
| GET | `/api/workflows/{workflow_id}/runs` |
| GET | `/api/workflows/{workflow_id}/runs/{run_id}` |
| PATCH | `/api/reviews/{review_id}` |
| PATCH | `/api/templates/{template_id}` |
| PATCH | `/api/workflows/{workflow_id}` |
| POST | `/api/auth-profiles` |
| POST | `/api/auth-profiles/{profile_id}/complete-login` |
| POST | `/api/auth-profiles/{profile_id}/revoke` |
| POST | `/api/auth-profiles/{profile_id}/start-login` |
| POST | `/api/auth-profiles/{profile_id}/validate` |
| POST | `/api/billing/checkout` |
| POST | `/api/billing/webhook` |
| POST | `/api/compliance/gdpr/forget` |
| POST | `/api/saas/aup/accept` |
| POST | `/api/saas/email-verification/send` |
| POST | `/api/saas/email-verification/verify` |
| POST | `/api/saas/invitations/{invitation_id}/respond` |
| POST | `/api/saas/orgs` |
| POST | `/api/saas/orgs/{org_id}/invitations` |
| POST | `/api/saas/password-reset/request` |
| POST | `/api/saas/password-reset/reset` |
| POST | `/api/saas/projects` |
| POST | `/api/saas/projects/{project_id}/keys` |
| POST | `/api/saas/signup` |
| POST | `/api/scheduled` |
| POST | `/api/templates` |
| POST | `/api/usage/stats/record` |
| POST | `/api/workflow-drafts/from-url-analysis` |
| POST | `/api/workflow-drafts/{draft_id}/detect-fields` |
| POST | `/api/workflow-drafts/{draft_id}/manual-mapping` |
| POST | `/api/workflows` |
| POST | `/api/workflows/{workflow_id}/preview` |
| POST | `/api/workflows/{workflow_id}/run` |
| PUT | `/api/scheduled/{job_id}` |
| PUT | `/api/workflows/{workflow_id}` |

**Total routes:** 185

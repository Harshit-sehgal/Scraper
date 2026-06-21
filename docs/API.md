# API

This route list was generated from the FastAPI app during the audit. Production app config disables `/docs`, `/redoc`, and `/openapi.json`; Nginx behavior still needs runtime validation in a started production stack.

**Note:** The access levels below reflect the *intended* contract. A fresh generated route-auth matrix (via `scripts/route_auth_matrix.py`) should be checked against this table after any auth reclassification.

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
| GET | `/api/jobs` | Authenticated user (paginated: `?limit=&cursor=`, returns `next_cursor`) |
| GET | `/api/jobs/{job_id}` | Authenticated user |
| GET | `/api/jobs/{job_id}/results` | Authenticated user (paginated: `?limit=&offset=`) |
| GET | `/api/jobs/{job_id}/events` | Authenticated user (paginated: `?limit=&offset=&level=`) |
| POST | `/api/jobs` | Operator or admin |
| POST | `/api/jobs/{job_id}/cancel` | Operator or admin |
| POST | `/api/jobs/{job_id}/reclean` | Operator or admin |
| POST | `/api/jobs/{job_id}/backfill-metadata` | Operator or admin |
| DELETE | `/api/jobs/{job_id}` | Admin |
| DELETE | `/api/jobs/cleanup/terminal` | Admin |
| GET | `/api/jobs/{job_id}/export/csv` | Operator or admin |
| GET | `/api/jobs/{job_id}/export/json` | Operator or admin |
| GET | `/api/jobs/{job_id}/export/excel` | Operator or admin |

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
| GET | `/api/intelligence/analyze-url` | Authenticated user |

## Scraper/Telemetry Routes

All scraper routes require operator or admin access. Read-only routes (GET) and mutation routes (POST/DELETE) are both protected by `require_role` with appropriate role restrictions.

| Method | Path | Intended Access |
| --- | --- | --- |
| GET | `/api/scraper/browser` | Operator or admin |
| GET | `/api/scraper/config` | Operator or admin |
| GET | `/api/scraper/health/legacy` | Operator or admin |
| GET | `/api/scraper/memory/stats` | Operator or admin |
| GET | `/api/scraper/regressions` | Operator or admin |
| GET | `/api/scraper/regressions/{entry_id}` | Operator or admin |
| GET | `/api/scraper/selectors/domain/{domain}` | Operator or admin |
| GET | `/api/scraper/selectors/low-confidence` | Operator or admin |
| GET | `/api/scraper/selectors/stats` | Operator or admin |
| GET | `/api/scraper/stats` | Operator or admin |
| GET | `/api/scraper/telemetry` | Operator or admin |
| DELETE | `/api/scraper/telemetry` | Admin |
| POST | `/api/scraper/diagnostics` | Operator or admin |
| POST | `/api/scraper/regressions/generate-all-tests` | Admin |
| POST | `/api/scraper/regressions/{entry_id}/generate-test` | Admin |
| POST | `/api/scraper/selectors/cleanup` | Admin |

## Operator and System Routes

| Method | Path | Intended Access |
| --- | --- | --- |
| GET | `/api/operator/denylist` | Operator or admin |
| POST | `/api/operator/denylist` | Admin |
| DELETE | `/api/operator/denylist` | Admin |
| GET | `/api/system/status` | Operator or admin |
| GET | `/api/system/storage/status` | Operator or admin |
| GET | `/api/system/manifest` | User (any authenticated role) |
| GET | `/api/system/audit-log` | Admin |
| GET | `/api/system/diagnostics/export` | Admin |
| GET | `/api/system/rate-limit-stats` | Operator or admin |
| GET | `/api/system/retention/config` | Operator or admin |
| GET | `/api/system/retention/health` | Operator or admin |
| POST | `/api/system/retention/enforce` | Admin |
| POST | `/api/system/csp-violations` | Unauthenticated (browser-reported; middleware bypasses auth for this path) |

## Session/Auth Routes

| Method | Path | Intended Access |
| --- | --- | --- |
| POST | `/api/session` | Authenticated user (exchanges API key for session cookie) |
| DELETE | `/api/session` | Authenticated user (clears session cookie) |
| GET | `/api/session/me` | Authenticated user (returns current role) |

## Auth Profile Routes

| Method | Path | Intended Access |
| --- | --- | --- |
| GET | `/api/auth-profiles` | Operator or admin |
| POST | `/api/auth-profiles` | Operator or admin |
| GET | `/api/auth-profiles/{profile_id}` | Operator or admin |
| DELETE | `/api/auth-profiles/{profile_id}` | Operator or admin |
| POST | `/api/auth-profiles/{profile_id}/start-login` | Operator or admin |
| POST | `/api/auth-profiles/{profile_id}/complete-login` | Operator or admin |
| POST | `/api/auth-profiles/{profile_id}/validate` | Operator or admin |
| POST | `/api/auth-profiles/{profile_id}/revoke` | Operator or admin |

## SaaS / Compliance Routes

| Method | Path | Intended Access |
| --- | --- | --- |
| POST | `/api/saas/signup` | Public signup |
| GET | `/api/saas/me` | Authenticated user |
| GET | `/api/saas/plan` | Authenticated user |
| GET | `/api/saas/usage` | Authenticated user |
| GET | `/api/saas/aup/status` | Authenticated user |
| POST | `/api/saas/aup/accept` | Authenticated user |
| GET | `/api/saas/email-verification/status` | Authenticated user |
| POST | `/api/saas/email-verification/send` | Authenticated user |
| POST | `/api/saas/email-verification/verify` | Authenticated user |
| POST | `/api/saas/password-reset/request` | Public (email-based, no auth required) |
| POST | `/api/saas/password-reset/reset` | Public (token-based, no auth required) |
| GET | `/api/saas/invitations/pending` | Authenticated user |
| POST | `/api/saas/invitations/{invitation_id}/respond` | Authenticated user |
| GET | `/api/saas/orgs` | Authenticated user |
| POST | `/api/saas/orgs` | Operator or admin |
| DELETE | `/api/saas/orgs/{org_id}` | Operator or admin |
| GET | `/api/saas/orgs/{org_id}` | Authenticated user |
| GET | `/api/saas/orgs/{org_id}/members` | Authenticated user |
| GET | `/api/saas/orgs/{org_id}/projects` | Authenticated user |
| GET | `/api/saas/orgs/{org_id}/invitations` | Authenticated user |
| POST | `/api/saas/orgs/{org_id}/invitations` | Operator or admin |
| DELETE | `/api/saas/memberships/{membership_id}` | Operator or admin |
| POST | `/api/saas/projects` | Operator or admin |
| DELETE | `/api/saas/projects/{project_id}` | Operator or admin |
| GET | `/api/saas/projects/{project_id}` | Authenticated user |
| GET | `/api/saas/projects/{project_id}/keys` | Authenticated user |
| POST | `/api/saas/projects/{project_id}/keys` | Operator or admin |
| DELETE | `/api/saas/projects/{project_id}/keys/{key_id}` | Operator or admin |

## Workflow Routes

| Method | Path | Intended Access |
| --- | --- | --- |
| GET | `/api/workflows` | Operator or admin |
| POST | `/api/workflows` | Operator or admin |
| GET | `/api/workflows/{workflow_id}` | Operator or admin |
| PUT | `/api/workflows/{workflow_id}` | Operator or admin |
| PATCH | `/api/workflows/{workflow_id}` | Operator or admin |
| DELETE | `/api/workflows/{workflow_id}` | Operator or admin |
| POST | `/api/workflows/{workflow_id}/preview` | Operator or admin |
| POST | `/api/workflows/{workflow_id}/run` | Operator or admin |
| GET | `/api/workflows/{workflow_id}/runs` | Operator or admin |
| GET | `/api/workflows/{workflow_id}/runs/{run_id}` | Operator or admin |
| POST | `/api/workflow-drafts/from-url-analysis` | Operator or admin |
| POST | `/api/workflow-drafts/{draft_id}/detect-fields` | Operator or admin |
| POST | `/api/workflow-drafts/{draft_id}/manual-mapping` | Operator or admin |

## Scheduled Monitoring Routes

| Method | Path | Intended Access |
| --- | --- | --- |
| GET | `/api/scheduled` | Operator or admin |
| POST | `/api/scheduled` | Operator or admin |
| GET | `/api/scheduled/{job_id}` | Operator or admin |
| PUT | `/api/scheduled/{job_id}` | Operator or admin |
| DELETE | `/api/scheduled/{job_id}` | Operator or admin |
| GET | `/api/scheduled/{job_id}/changes` | Operator or admin |

## Billing and User Data Routes

| Method | Path | Intended Access |
| --- | --- | --- |
| POST | `/api/billing/checkout` | Operator or admin |
| POST | `/api/billing/webhook` | Billing webhook secret or HMAC signature |
| GET | `/api/billing/stub-return/{plan_tier}/{request_id}` | Unauthenticated (dev-only stub) |
| GET | `/api/billing/subscriptions` | Operator or admin |
| GET | `/api/billing/subscriptions/{customer_id}` | Operator or admin |
| DELETE | `/api/user/data` | Authenticated user (self-service deletion) |

## Batch Export

| Method | Path | Intended Access |
| --- | --- | --- |
| POST | `/api/exports/batch` | Operator or admin |

`POST /api/exports/batch` — Export results from multiple jobs in a single request. Operator or admin.

| Property | Type | Default | Description |
| --- | --- | --- | --- |
| `job_ids` | `string[]` | (required) | Job IDs to export (1–50) |
| `format` | `string` | `"csv"` | Output format: `csv`, `json`, or `xlsx` |
| `flatten` | `bool` | `true` | When True, results are combined into a single output. When False, jobs are separated (CSV uses separator rows, JSON uses an `exports` array, Excel uses one sheet per job). |

### CSV (`format: "csv"`)

- **flatten=True** (default): Single CSV table with all rows from all jobs. A `_source_job` column identifies the origin job. All fields across jobs are unioned into the header.
- **flatten=False**: Separator rows (`--- Job Name ---`) divide job sections. No `_source_job` column.

### JSON (`format: "json"`)

- **flatten=True**: Single JSON array where every object includes a `_source_job` field.
- **flatten=False**: A JSON object with an `exports` array:

  ```json
  {
    "exports": [
      {
        "job_id": "uuid-1",
        "job_name": "Job A",
        "results": [...]
      },
      {
        "job_id": "uuid-2",
        "job_name": "Job B",
        "results": [...]
      }
    ]
  }
  ```

### Excel (`format: "xlsx"`)

- **flatten=True**: Single "Combined" sheet with a `_source_job` column.
- **flatten=False**: One sheet per job (sheet name truncated to 31 characters).

### Error codes

| Status | Meaning |
| --- | --- |
| 200 | Successful export (file download) |
| 400 | None of the specified jobs have results |
| 404 | One or more job IDs not found |
| 422 | Empty `job_ids`, invalid format, or validation failure |

### Example

```bash
curl -X POST https://dataforge.example.com/api/exports/batch \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "job_ids": ["abc-123", "def-456"],
    "format": "csv",
    "flatten": true
  }' \
  -o combined_export.csv
```

## Rate Limiting

The API applies sliding-window rate limiting with two independent tiers:

**Tier 1: Aggregate global cap** — Controls total throughput across all clients combined.
- Default: `600 requests/minute` (`DATAFORGE_RATE_LIMIT_GLOBAL`)
- Route-specific overrides apply for expensive endpoints (URL analyze: 10/min, discovery: 15/min, etc.)

**Tier 2: Per-IP fair-sharing cap** — Ensures no single client can monopolise the API.
- Default: `100 requests/minute` per IP (`DATAFORGE_RATE_LIMIT_PER_IP`)
- Can be disabled via `DATAFORGE_RATE_LIMIT_PER_IP_ENABLED=false`
- This tier is separate from route-specific limits (those apply only to the aggregate tier)

**Database-backed counters**: In production/staging, `RATE_LIMIT_DB_BACKED` auto-promotes to `True`, using the shared `rate_limits` table so counters survive process restarts and work across multiple workers.

**Response headers**: Every API response includes:
- `X-RateLimit-Limit` — Max requests per window
- `X-RateLimit-Remaining` — Requests remaining in current window
- `X-RateLimit-Reset` — Unix timestamp when the window resets
- `Retry-After` — Seconds until retry (only on 429 responses)

**Safe IP extraction**: `X-Forwarded-For` is only trusted when the immediate peer is a private or loopback address (localhost, Docker subnet). External clients cannot spoof their IP.

## Auth Notes

- `X-API-Key` or `Authorization: Bearer <token>` can provide user/operator/admin credentials.
- `X-Admin-Key` is accepted for admin compatibility.
- In development with no configured keys, routes may be permissive. Do not use that mode for production.

## Idempotency

`POST /api/jobs` accepts an optional `Idempotency-Key` request header
(up to 128 characters). When set, a repeat request with the same
header value returns the originally-created `job_id` and the
response includes `idempotent_replay: true`. The first response
carries `idempotent_replay: false`. The mapping is persisted in
the `idempotency_keys` companion table and pruned after 7 days by
default (operators can call `prune_idempotency_keys(older_than_days=...)`).

This is a best-effort deduplication mechanism for client retry loops.
A conflicting `request_fingerprint` does not currently cause a
409; the latest record wins.

## Experimental / Research Routes (Gated)

The following routes are backed by research-shell modules and are **only available when `DATAFORGE_ENABLE_EXPERIMENTAL_ROUTES=true`**. They are not mounted in the default app configuration. See `backend/app/routers/experimental.py` for details.

### Operator Mode & Dashboard

| Method | Path | Intended Access |
| --- | --- | --- |
| GET | `/api/operator/dashboard` | Authenticated user |
| GET | `/api/operator/health` | Authenticated user |
| GET | `/api/operator/mode` | Authenticated user |
| GET | `/api/operator/predictions` | Authenticated user |
| GET | `/api/operator/predictions/{domain}` | Authenticated user |
| POST | `/api/operator/mode` | Admin |

### Scraper Research & ML

| Method | Path | Intended Access |
| --- | --- | --- |
| GET | `/api/scraper/economics` | Authenticated user |
| GET | `/api/scraper/health/summary` | Authenticated user |
| GET | `/api/scraper/health/domains` | Authenticated user |
| GET | `/api/scraper/health/domain/{domain}` | Authenticated user |
| GET | `/api/scraper/strategy/domain/{domain}` | Authenticated user |
| GET | `/api/scraper/strategy/recommend/{domain}` | Authenticated user |
| GET | `/api/scraper/strategy/report` | Authenticated user |
| GET | `/api/scraper/trends` | Authenticated user |
| GET | `/api/scraper/trends/{domain}` | Authenticated user |
| GET | `/api/scraper/ml/optimize/domain/{domain}/history` | Authenticated user |
| POST | `/api/scraper/strategy/evolve/{domain}` | Operator or admin |
| POST | `/api/scraper/strategy/record` | Operator or admin |
| POST | `/api/scraper/ml/learn` | Operator or admin |
| POST | `/api/scraper/ml/optimize/domain/{domain}` | Operator or admin |

### System Research Endpoints

| Method | Path | Intended Access |
| --- | --- | --- |
| GET | `/api/system/topology` | Authenticated user |
| GET | `/api/system/crystalline` | Authenticated user |
| GET | `/api/system/export/knowledge` | Authenticated user |
| GET | `/api/system/search` | Authenticated user |
| GET | `/api/system/observability` | Authenticated user |
| GET | `/api/system/history/topology` | Authenticated user |
| GET | `/api/system/agency` | Authenticated user |
| GET | `/api/system/replay/status` | Authenticated user |
| GET | `/api/system/replay/chain` | Authenticated user |
| GET | `/api/system/replay/events` | Authenticated user |
| POST | `/api/system/scheduler/step` | Admin |
| POST | `/api/system/refactor/compress` | Admin |
| GET | `/api/system/domain-policy` | Authenticated user |
| GET | `/api/system/acquisition/telemetry` | Authenticated user |
| POST | `/api/system/merge/knowledge` | Admin |

Enable experimental routes:
```bash
# Set this environment variable before starting the server
export DATAFORGE_ENABLE_EXPERIMENTAL_ROUTES=true
```

## Metrics

`GET /metrics` is protected by `DATAFORGE_METRICS_TOKEN` if configured. Local Compose verified public Nginx returns 404 for `/metrics`, while Prometheus scrapes `http://dataforge:8000/metrics` internally with the configured bearer token. Repeat this check behind the target ingress.

The following Prometheus metrics are exposed:

| Metric | Type | Labels | Description |
| --- | --- | --- | --- |
| `dataforge_rate_limit_global_hits_total` | Gauge | — | Cumulative rate limit hits by the aggregate global tier |
| `dataforge_rate_limit_per_ip_hits_total` | Gauge | — | Cumulative rate limit hits by the per-IP fair-sharing tier |

Both rate-limit hit counters are reset on process restart. They are incremented whenever the rate limiter middleware returns a 429 Too Many Requests response, and are exposed in both the Prometheus exposition format and the fallback text output.

### Alerting Rules (Prometheus)

The following alert rules are defined in `prometheus_alerts.yml` and evaluated by the DataForge Prometheus instance:

| Alert | Severity | Condition | Description |
| --- | --- | --- | --- |
| `DataForgeAPIInstanceDown` | critical | `up{job="dataforge"} == 0` for 1m | API server unreachable |
| `QueueBacklogHigh` | warning | `dataforge_queue_pending > 100` for 5m | Pending queue depth exceeds 100 |
| `HighJobFailureRate` | warning | `rate(dataforge_jobs_total{status="failed"}[5m]) > 0.1` for 10m | Jobs failing at > 0.1 req/s |
| `HighRateLimitBlockRate` | warning | `sum(rate(dataforge_rate_limit_global_hits_total[5m]) + rate(dataforge_rate_limit_per_ip_hits_total[5m])) > 0.5` for 5m | Rate limiter blocking > 0.5 req/s across both tiers |
| `WorkerHeartbeatStale` | critical | `dataforge_worker_heartbeat_alive == 0` for 2m | Worker process heartbeat stale |
| Database errors, CSP violations, SSRF, browser launch failures, extraction anomalies | varied | See `prometheus_alerts.yml` for full list | |

### Grafana Dashboard

The DataForge Production Overview dashboard (`grafana/dashboards/dataforge_overview.json`) includes the following rate-limit-related panels:

| Panel | Type | Metrics | Description |
| --- | --- | --- | --- |
| Rate Limit Blocks (1h) | Stat | `sum(increase(dataforge_rate_limit_global_hits_total[1h]))` | Total global-tier rate limit blocks in the last hour |
| Per-IP Blocks (1h) | Stat | `sum(increase(dataforge_rate_limit_per_ip_hits_total[1h]))` | Total per-IP rate limit blocks in the last hour |
| Rate Limit Block Rate | Timeseries | `rate(dataforge_rate_limit_global_hits_total[5m])` and `rate(dataforge_rate_limit_per_ip_hits_total[5m])` | Rate of blocks over time, broken down by tier, with threshold reference lines at 0.1 and 0.5 req/s |

Alerts for these panels route through Alertmanager (`alertmanager.yml`) to email and Slack channels based on severity.

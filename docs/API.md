# API

This route list was generated from the FastAPI app during the audit. Production app config disables `/docs`, `/redoc`, and `/openapi.json`; Nginx behavior still needs runtime validation in a started production stack.

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

| Method | Path | Intended Access |
| --- | --- | --- |
| GET | `/api/scraper/browser` | Operator or admin |
| GET | `/api/scraper/config` | Operator or admin |
| GET | `/api/scraper/economics` | Operator or admin |
| GET | `/api/scraper/health/summary` | Operator or admin |
| GET | `/api/scraper/health/legacy` | Operator or admin |
| GET | `/api/scraper/health/domains` | Operator or admin |
| GET | `/api/scraper/health/domain/{domain}` | Operator or admin |
| GET | `/api/scraper/memory/stats` | Operator or admin |
| GET | `/api/scraper/regressions` | Operator or admin |
| GET | `/api/scraper/regressions/{entry_id}` | Operator or admin |
| GET | `/api/scraper/selectors/domain/{domain}` | Operator or admin |
| GET | `/api/scraper/selectors/low-confidence` | Operator or admin |
| GET | `/api/scraper/selectors/stats` | Operator or admin |
| GET | `/api/scraper/stats` | Operator or admin |
| GET | `/api/scraper/strategy/domain/{domain}` | Operator or admin |
| GET | `/api/scraper/strategy/recommend/{domain}` | Operator or admin |
| GET | `/api/scraper/strategy/report` | Operator or admin |
| GET | `/api/scraper/telemetry` | Operator or admin |
| GET | `/api/scraper/trends` | Operator or admin |
| GET | `/api/scraper/trends/{domain}` | Operator or admin |
| GET | `/api/scraper/ml/optimize/domain/{domain}/history` | Operator or admin |
| DELETE | `/api/scraper/telemetry` | Admin |
| POST | `/api/scraper/diagnostics` | Operator or admin |
| POST | `/api/scraper/regressions/generate-all-tests` | Admin |
| POST | `/api/scraper/regressions/{entry_id}/generate-test` | Admin |
| POST | `/api/scraper/selectors/cleanup` | Admin |
| POST | `/api/scraper/strategy/evolve/{domain}` | Admin |
| POST | `/api/scraper/strategy/record` | Operator or admin |
| POST | `/api/scraper/ml/learn` | Admin |
| POST | `/api/scraper/ml/optimize/domain/{domain}` | Admin |

## Operator and System Routes

| Method | Path | Intended Access |
| --- | --- | --- |
| GET | `/api/operator/dashboard` | Operator or admin |
| GET | `/api/operator/health` | Operator or admin |
| GET | `/api/operator/mode` | Operator or admin |
| GET | `/api/operator/predictions` | Operator or admin |
| GET | `/api/operator/predictions/{domain}` | Operator or admin |
| POST | `/api/operator/mode` | Admin |
| GET | `/api/system/status` | Operator or admin |
| GET | `/api/system/storage/status` | Operator or admin |
| GET | `/api/system/diagnostics/export` | Admin |
| POST | `/api/system/csp-violations` | Unauthenticated (browser-reported) |

Admin-only routes include system merge, scheduler step, refactor compression, diagnostics export, and operator mode changes.

## Metrics

`GET /metrics` is protected by `DATAFORGE_METRICS_TOKEN` if configured. Local Compose verified public Nginx returns 404 for `/metrics`, while Prometheus scrapes `http://dataforge:8000/metrics` internally with the configured bearer token. Repeat this check behind the target ingress.

## Batch Export

`POST /api/exports/batch` — Export results from multiple jobs in a single request.

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

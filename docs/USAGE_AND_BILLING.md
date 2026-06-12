# DataForge Scraper — Usage And Billing

Date: 2026-06-13
Commit: `7d47045`

Usage metering and quota enforcement. Implementation: `backend/app/utils/usage_ledger.py`.

---

## 1. Usage Events

The `UsageLedger` tracks these usage dimensions:

| Event | Description | Tracked Per |
|-------|-------------|-------------|
| `api_request` | Each authenticated API call | User / Org / Project / API Key |
| `job_created` | A new scraping job | User / Org / Project |
| `page_fetched` | Each page fetched during a job | Job / Project |
| `browser_minute` | Browser context usage (per minute) | Job / Project |
| `export_created` | An export (CSV, JSON, Excel) | User / Org / Project |
| `workflow_preview` | A workflow preview run | User / Org / Project |
| `workflow_run` | A full workflow execution | User / Org / Project |
| `record_extracted` | (Optional) Per-record extraction count | Job / Project |

---

## 2. Quota Enforcement

### Atomic Check-and-Increment

```
UsageLedger.record_usage(
    user_id, org_id, project_id,
    event_type, amount=1,
    idempotency_key=...
)
  → acquires lock
  → checks current usage against quota
  → if over limit: raises QuotaExceededError
  → increments usage counter
  → releases lock
```

### Idempotency Keys

Every `record_usage()` call accepts an idempotency key. The same key within a window produces the same result — no double-charging for retried requests.

### Period Windows

- Default period: calendar month (resets on the 1st)
- Configurable for different plan tiers
- Usage counters are per-period

---

## 3. Quota Limits

Current quota defaults (configurable per plan tier):

| Limit | Free | Starter | Pro |
|-------|------|---------|-----|
| Max jobs per month | 10 | 100 | 1000 |
| Max pages per month | 1000 | 10000 | 100000 |
| Max browser minutes per month | 60 | 600 | 6000 |
| Max exports per month | 10 | 100 | 1000 |
| Max workflows | 2 | 20 | 200 |
| Max scheduled jobs | 1 | 10 | 100 |

These limits exist in the plan model (`GET /api/saas/plan`) but are not yet enforced by the usage ledger middleware. Enforcement is the next priority.

---

## 4. Plan Tiers

| Tier | Intended User | Key Features |
|------|--------------|--------------|
| `free` | Individual, evaluation | Basic scraping, 10 jobs/mo, 2 teammates |
| `starter` | Small team / freelancer | 100 jobs/mo, 20 teammates, priority support |
| `pro` | Agency / power user | 1000 jobs/mo, unlimited teammates, API access |
| `enterprise` | Large org | Custom limits, SSO, dedicated support |

Plan fields: `tier`, `max_jobs`, `max_scrapes`, `max_teammates`, `max_projects`, `features[]`.

---

## 5. Billing Integration Status

### What Exists
- Plan tier model and stub endpoint (`GET /api/saas/plan`)
- Usage ledger with atomic increment and idempotency
- Quota check function

### What Is Missing
- Payment provider integration (Stripe / Paddle)
- Subscription management
- Invoice generation and history
- Plan upgrade/downgrade flow
- Usage-based billing beyond quota
- Over-limit grace periods
- Billing webhook handling
- Frontend billing/plan management page

---

## 6. Enforcement Points

Recommended enforcement per route:

| Route | Enforce |
|-------|---------|
| `POST /api/jobs` | `job_created` quota |
| `POST /api/workflows/{id}/run` | `workflow_run` quota |
| `POST /api/workflows/{id}/preview` | `workflow_preview` quota |
| `GET /api/jobs/{id}/export/*` | `export_created` quota |
| `POST /api/exports/batch` | `export_created` × batch count |

Browser minutes are tracked by the Playwright runner, not pre-checked.

---

## 7. Over-Limit Behavior

When quota is exceeded, the API returns:

```json
{
  "detail": "Usage quota exceeded. Your plan allows 10 jobs per month. You have used 10.",
  "quota_limit": 10,
  "quota_used": 10,
  "quota_resets_at": "2026-07-01T00:00:00Z",
  "upgrade_url": "/api/saas/plan"  // future
}
```

HTTP status: 429 (Too Many Requests) for rate limits, 402 (Payment Required, future) for billing caps.

---

## 8. Tests

- `backend/tests/test_p0_billing_usage.py` — 28 tests cover quota enforcement, idempotency, concurrent increments, over-limit blocking

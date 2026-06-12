# DataForge Scraper — Load And Cost Controls

Date: 2026-06-13
Commit: `7d47045`

Bounds and limits that protect the platform from runaway resource consumption. This is a planning document; most controls are not yet enforced.

---

## 1. Per-Job Limits

| Limit | Current Default | Hard Cap | Enforced |
|-------|----------------|----------|----------|
| Max pages per job | 10 | 100 | ❌ (config field exists, not enforced) |
| Max records per job | None | None | ❌ |
| Max runtime per job | None | 3600s (planned) | ❌ |
| Max browser contexts per job | 1 | 5 | ❌ |
| Max retries per page | 3 | 5 | ❌ |
| Max extraction schema fields | 50 | 50 | ✅ (model validator) |
| Max URLs per manual job | 100 | 100 | ✅ (model validator) |
| Max workflow steps | 100 | 100 | ✅ (model validator) |

---

## 2. Per-Domain Controls

| Control | Current | Target |
|---------|---------|--------|
| Concurrent requests per domain | Not enforced | 2–5 |
| Delay between requests | Not enforced | 1–5s |
| Cooldown on failure | Not enforced | 30–300s |
| Robots/crawl policy awareness | Best-effort only | Required |

---

## 3. Per-User / Per-Project Quotas

| Quota | Free | Starter | Pro | Enforced |
|-------|------|---------|-----|----------|
| Max jobs per month | 10 | 100 | 1000 | ❌ |
| Max pages per month | 1000 | 10000 | 100000 | ❌ |
| Max browser minutes per month | 60 | 600 | 6000 | ❌ |
| Max exports per month | 10 | 100 | 1000 | ❌ |
| Max workflows | 2 | 20 | 200 | ❌ |
| Max scheduled jobs | 1 | 10 | 100 | ❌ |

See `docs/USAGE_AND_BILLING.md` for quota enforcement implementation.

---

## 4. Queue Backpressure

| Control | Current | Target |
|---------|---------|--------|
| Max queued jobs | Not limited | Per-project cap |
| Max concurrent browser instances | Not limited | Configurable pool |
| Job priority | FIFO only | Priority tiers |
| Stale job cleanup | Not implemented | Cancel jobs in queue > 24h |

---

## 5. Export Size Limits

| Control | Current | Target |
|---------|---------|--------|
| Max CSV rows | Not limited | 100,000 |
| Max JSON file size | Not limited | 50 MB |
| Max Excel rows | Not limited | 100,000 |
| Batch export max jobs | Not limited | 50 |

---

## 6. Browser Bounds

| Control | Current | Planned |
|---------|---------|---------|
| Wait timeout per step | 10,000ms | 10,000ms ✅ |
| Max scroll iterations | Not bounded | 50 |
| Max load-more clicks | Not bounded | 20 |
| Navigation timeout | 30s default | 60s |
| Screenshot capture | Off | On failure only |
| Browser context cleanup | Best effort | Guaranteed (finally block) |

---

## 7. Failure Cooldown

| Trigger | Cooldown |
|---------|----------|
| Domain returns 5xx | Retry with exponential backoff (1s → 2s → 4s → 8s, max 3 retries) |
| Domain blocks scraping | Pause for 300s, alert operator |
| Browser crash | Clean up context, restart, retry once |
| Quota exceeded | Block until next period |

---

## 8. Production Deployment Targets

| Resource | Limit |
|----------|-------|
| Max API workers | 4 (configurable via uvicorn) |
| Max background workers | 2 (configurable) |
| Max DB connections | 20 (SQLite WAL, Postgres pool) |
| Disk space for results | Configurable retention window + cleanup |
| Memory per browser context | ~500 MB estimated |

---

## 9. What Needs Implementation

- [ ] Quota enforcement wired into job creation, workflow run, export routes
- [ ] Per-domain concurrency limiter
- [ ] Per-job runtime timeout
- [ ] Browser pool with max-context cap
- [ ] Queue backpressure (reject when queue depth > threshold)
- [ ] Export size limits
- [ ] Automatic stale job cleanup
- [ ] Browser scroll/click iteration caps
- [ ] Failure cooldown with exponential backoff

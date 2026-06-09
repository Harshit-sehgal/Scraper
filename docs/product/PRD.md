# DataForge Scraper — Product Requirements Document (v1)

**Status:** Draft v1
**Author:** Generated from Phase 2 — SaaS product core definition
**Last updated:** 2026-06-09

---

## 1. Product Positioning

> A controlled web data extraction platform for teams that need repeatable
> extraction from accessible websites, with schema-guided jobs, quality scoring,
> exports, monitoring, and safe operational controls.

### What we do NOT claim

- Universal extraction from every website.
- Guaranteed anti-bot bypass.
- Legal permission to scrape all sites.
- Fully autonomous extraction without human review.
- Production readiness without deployment/security/load/restore evidence.

---

## 2. Ideal Customer Profile (ICP) — v1

**Primary:** Small agencies managing repeated public-data extraction for clients.
**Secondary:** Growth/SEO teams needing monitored extraction from known public pages.
**Tertiary:** Research/data teams needing repeatable exports and quality checks.

**Not targeting for v1:**
- High-risk scraping (login walls, marketplaces with heavy anti-bot, financial trading data).
- Medical/personal data extraction.
- Protected/content sites without explicit permission.

---

## 3. Supported Use Cases (v1)

| # | Use case | Legal/ethical boundary |
|---|----------|------------------------|
| 1 | **Product catalog monitoring** — Extract structured product data (name, price, availability, description) from public e-commerce listings at regular intervals. | Must respect `robots.txt` and terms of service. Must not bypass login walls or CAPTCHA. Rate-limit to <1 req/sec per domain. |
| 2 | **Public directory / listings extraction** — Extract structured records from public directories (business listings, job postings, public profiles) where the site does not prohibit automated access. | Must not circumvent rate limits or access controls. Must not re-publish sensitive personal data without anonymisation. |
| 3 | **Content aggregation for research** — Extract article metadata (title, author, publication date, abstract) from public content sites for non-commercial research or internal monitoring. | Must not reproduce full copyrighted articles. Must respect `noindex` / `nofollow` directives. Must include source attribution in exports. |

### Unsupported scenarios (v1)

- Login-gated extraction (requires credentials or session cookies).
- High-frequency extraction (>10 req/s per domain).
- Extraction from sites with active anti-bot CAPTCHA.
- Extraction of protected health/financial/personal data.
- Commercial resale of extracted data without source licensing.

---

## 4. Pricing Metric & Plan Limits

### Pricing metric: **Page fetches per month**

Rationale: page fetches directly map to the primary cost driver (browser sessions,
network bandwidth, processing time). They are easy to count, hard to game, and
correlate linearly with customer value.

| Tier | Monthly page fetches | Concurrent jobs | Storage (results) | Export limits | Max pages/job | Retention |
|------|--------------------:|:---------------:|:-----------------:|:-------------:|:-------------:|:---------:|
| **Free** | 1,000 | 1 | 10,000 records | CSV only | 100 | 7 days |
| **Starter** | 10,000 | 5 | 100,000 records | CSV, JSON | 1,000 | 30 days |
| **Pro** | 100,000 | 25 | 1,000,000 records | CSV, JSON, Excel | 10,000 | 90 days |
| **Business** | 1,000,000 | 100 | 10,000,000 records | All formats + batch | 100,000 | 180 days |

**Overages:** Hard-stop at tier limit for Free/Starter (403 on job creation).
Pro/Business can configure automatic upgrade or hard-stop.

**API rate limits:**
| Tier | Requests/minute | Requests/hour |
|------|:---------------:|:-------------:|
| Free | 10 | 100 |
| Starter | 60 | 1,000 |
| Pro | 300 | 10,000 |
| Business | 1,000 | 60,000 |

---

## 5. v1 User Journeys

### Journey A — First-time user (signup to first extraction)

1. Landing page → Sign up (email + password / Google OAuth)
2. Email verification → Create first project
3. Add a job: paste URL, choose schema (auto-detect or manual), select scrape mode
4. Preview extraction: see 3-5 sample results before committing
5. Run full job: progress indicator, estimated time, live log stream
6. Review results: paginated table with field confidence and source lineage
7. Export: download as CSV/JSON/Excel
8. Dashboard: see project list, job history, usage meter

### Journey B — Power user (scheduled monitoring)

1. Create project → Add multiple URLs → Configure schema
2. Set schedule: daily/weekly at specific time
3. Receive email/Slack/webhook notification on completion
4. Review incremental results (new/changed records highlighted)
5. Export via API or scheduled export job
6. Monitor usage against plan limits

### Journey C — Team admin (managing org)

1. Create organisation → Invite members via email
2. Assign roles: Admin, Developer, Analyst, Viewer
3. Create API keys scoped to specific projects
4. View org-level usage dashboard and audit log
5. Manage billing: upgrade/downgrade plan, view invoices
6. Configure data retention policies per project

---

## 6. Feature Tier Table

| Feature | Free | Starter | Pro | Business |
|---------|:----:|:-------:|:---:|:--------:|
| Schema-guided extraction | ✅ | ✅ | ✅ | ✅ |
| CSV export | ✅ | ✅ | ✅ | ✅ |
| JSON export | — | ✅ | ✅ | ✅ |
| Excel export | — | — | ✅ | ✅ |
| Batch export | — | — | — | ✅ |
| Scheduled jobs | — | — | ✅ | ✅ |
| Webhook notifications | — | ✅ | ✅ | ✅ |
| Custom schemas | ✅ | ✅ | ✅ | ✅ |
| Team members | — | 3 | 10 | Unlimited |
| API keys | 1 | 3 | 10 | 50 |
| API access | ✅ | ✅ | ✅ | ✅ |
| Priority support | — | — | Email | Chat + phone |
| Data retention (days) | 7 | 30 | 90 | 180 |
| Audit log | — | — | 30 days | 1 year |
| SSO/ SAML | — | — | — | ✅ |

---

## 7. Stable Core vs Experimental Lab

### Stable v1 core (production-safe, documented, tested)

- Auth: signup, login, organisations, projects, API keys, role-based access
- Jobs: create, read, cancel, delete, restore, list with pagination
- URL safety: SSRF protection, DNS validation, port allowlist
- Acquisition modes: `bright_data`, `playwright`, `fetch` (static)
- Schema-guided extraction: auto-detect, manual field definition
- Exports: CSV, JSON, Excel with streaming (no OOM)
- Quality: field confidence, source lineage, duplicate marking
- Usage metering: page fetches, job count, storage bytes
- Admin: job diagnostics, recycle bin, audit log, health endpoints

### Experimental lab (gated by `DATAFORGE_ENABLE_EXPERIMENTAL_ROUTES=false`)

- Semantic extraction pipeline (`semantic_os`)
- Topology/federation state management
- Replay buffer and regression capture
- Adaptive/acquisition mode selection
- Domain intelligence and degradation prediction
- Self-tuning extraction and strategy evolution

**Policy:** Experimental features must be:
- Disabled by default.
- Invisible to non-admin users.
- Documented as experimental with no SLA.
- Promoted to stable only when benchmark quality thresholds are met.

---

## 8. Acceptance Criteria for v1 Launch

- [ ] All P0/P1 issues from the verified backlog are closed.
- [ ] Tenant isolation tests pass (user A cannot see user B data).
- [ ] Full CI passes under timeout.
- [ ] DNS-isolated unit/API tests pass without network access.
- [ ] Stable docs match runtime behaviour.
- [ ] Billing ledger functions end-to-end in test mode.
- [ ] Backup/restore drill documented and recently passed.
- [ ] Marketing copy reviewed for overclaim.
- [ ] Legal: ToS, Privacy Policy, AUP drafted.

---

_This PRD is a living document. Update it as customer feedback validates
or invalidates assumptions._

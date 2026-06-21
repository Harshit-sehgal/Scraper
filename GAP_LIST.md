# DataForge Scraper — Complete Gap List

Generated: 2026-06-22 (re-validated after deep-scan fixes)

---

## HEALTH SUMMARY

**Updated after deep-scan fixes:** All code-level gates green (quick 12/12). Retention tests (12 tests), brute-force rate limit regression tests (3 tests) added. Token logging, CORS, .env permissions, and frontend XSS vector fixed. retention_monitoring bug (`_alert_critical_retention_failure` missing `actor`/`resource` args) fixed.

---

## Remaining Gaps

### GAP 1 — P1-ARCH-ROUTER-001
`register_jobs_write_routes` 736-LOC monolith. File: `backend/app/routers/jobs_write.py`

### GAP 2 — P1-ARCH-SELECTOR-001
`analyze_url_for_fields` 564-LOC pipeline. File: `backend/app/selector_discovery.py`

### GAP 3 — P1-ARCH-STATE-001
Job state machine distributed across 5+ modules.

### GAP 4 — CAND-P1-ARCH-CHARTEST-001
No characterization tests for refactor hotspots.

### GAP 5 — CAND-P1-ARCH-FRONTEND-FLOW-001
No authenticated E2E test for frontend->backend job creation.

### GAP 6 — CAND-P2-PAGINATION-ALIAS-001
Legacy `url_parameter` silently falls back to next-button.

### GAP 7 — Features
Account settings, team management, API key UI missing.

### GAP 8 — Live session expiry
`live=True` query param opt-in; not default.

### GAP 9 — Scroll/load-more
Not surfaced in scraper.

### GAP 10 — Benchmarks
Only 8 smoke tests; fixture page corpus missing.

### GAP 11 — Audit coverage
Many routes lack audit events.

### GAP 12 — Retention background loop
Has unit tests but no staging E2E verification.

### GAP 13 — Observability metrics
Not all documented metrics implemented.

### GAP 14 — Postgres parity
13+ tests skipped by default (`--run-postgres`).

### GAP 15 — Deployment
Staging, TLS, image build, load tests, incident drills unexecuted.

### GAP 16 — PayPal billing
Code tested, needs actual API credentials.

---

## FIXED THIS SESSION

| Fix | File(s) |
|-----|---------|
| Token logging sanitized (info->debug, tokens removed) | `backend/app/saas/router.py` |
| `.env` permissions tightened to 600 | `.env` |
| Data retention tests added (12 tests) | `backend/tests/test_retention.py` |
| Frontend XSS vectors fixed | `command-palette.js`, `recent-activity.js` |
| CORS methods/headers tightened | `backend/app/main.py` |
| Billing env vars added to prod check | `scripts/check_prod_env.py` |
| Brute-force rate limit regression tests (3) | `test_saas_email_identity.py` |
| `_alert_critical_retention_failure` bug fixed | `retention_monitoring.py` |
| Stale deep-scan docs updated | `DEEP_SCAN_SUMMARY.md` |

---

## TOTALS

| Type | Count | Est. Effort |
|------|-------|-------------|
| Architecture refactors | 5 (gaps 1-5) | ~6-8 days |
| Quick code fixes | 4 (gaps 6, 11-13) | ~2.5-4 days |
| Product features | 4 (gaps 7-10) | ~6-8 days |
| Infrastructure | 2 (gaps 14-15) | ~1-2 weeks after staging |
| Billing rollout | 1 (gap 16) | ~1 hour + PayPal setup |
| **Total remaining** | **16 gaps** | **~14-20 days** |

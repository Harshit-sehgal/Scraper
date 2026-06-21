# DataForge Scraper — Complete Gap List

Generated: 2026-06-21 (fresh validation: quick 12/12 ✅, routes 139/129 auth=0 tenant=0 ✅)

---

## HEALTH SUMMARY

All code-level gates are green. No P0 defects remain. ~3,787 backend tests + 290 frontend tests pass. Mypy/ruff/pyflakes/bandit/pip-audit/stylelint/prettier/ESLint all clean.

**There are exactly 19 gaps remaining** (some need code changes, most need infrastructure).

---

## GAP 1 — P1-ARCH-ROUTER-001
- **What:** `register_jobs_write_routes` is a 736-LOC monolith (mixes HTTP, auth, quota, idempotency, persistence, scheduling)
- **File:** `backend/app/routers/jobs_write.py`
- **Fixable now?** ✅ Yes (~2-3 days)
- **Action:** Extract `JobCreationService`, keep router as thin adapter, write characterization tests first

## GAP 2 — P1-ARCH-SELECTOR-001
- **What:** `analyze_url_for_fields` is a 564-LOC mixed pipeline (heuristics, redirects, form recovery, extraction, fallbacks, warnings)
- **File:** `backend/app/selector_discovery.py`
- **Fixable now?** ✅ Yes (~1-2 days)
- **Action:** Split into typed stages with fixture-backed tests

## GAP 3 — P1-ARCH-STATE-001
- **What:** Job state machine distributed across 5+ modules (runner, finalization, cancellation, routes, recovery)
- **Files:** `backend/app/services/job_runner.py`, `finalization.py`, `status_classifier.py`, `state_store.py`
- **Fixable now?** ✅ Yes (~1 day)
- **Action:** Centralize into one `JobStateMachine` module

## GAP 4 — CAND-P1-ARCH-CHARTEST-001
- **What:** No characterization tests exist for the refactor-sensitive hotspots
- **Files:** `backend/tests/` (new files needed)
- **Fixable now?** ✅ Yes (~1 day)
- **Action:** Write behavior-lock tests before touching any hotspot

## GAP 5 — CAND-P1-ARCH-FRONTEND-FLOW-001
- **What:** No authenticated E2E test for frontend→backend job creation
- **File:** `frontend/e2e/` (new test needed)
- **Fixable now?** ✅ Yes (~0.5 day)
- **Action:** Add Playwright test: login → create job → verify

## GAP 6 — CAND-P2-PAGINATION-ALIAS-001
- **What:** Legacy `url_parameter` strategy silently falls back to next-button instead of `url_pattern`
- **File:** `backend/app/pagination_executor.py`
- **Fixable now?** ✅ Yes (~0.25 day)
- **Action:** Add alias shim + regression test

## GAP 7 — Frontend SaaS pages
- **What:** Account settings, team management, API key UI don't exist (backend routes are complete)
- **Files:** New `frontend/js/account.js`, `frontend/js/team.js`, `frontend/index.html`, `frontend/styles.css`
- **Fixable now?** ✅ Yes (~2-3 days)
- **Action:** Build 3 new dashboard tabs with existing design system

## GAP 8 — Live session expiry check not default
- **What:** `live=True` query parameter is opt-in; not wired into default profile validation
- **File:** `backend/app/routers/auth_profiles.py`
- **Fixable now?** ✅ Yes (~0.5 day)
- **Action:** Make live check default with graceful degradation

## GAP 9 — Scroll/load-more not surfaced in scraper
- **What:** `pagination_executor.py` has the code, but `scraper.py` doesn't expose it
- **Files:** `backend/app/scraper.py`, `backend/app/pagination_executor.py`
- **Fixable now?** ✅ Yes (~1 day)
- **Action:** Wire strategies through the scraper interface + config plumbing

## GAP 10 — Benchmark corpus
- **What:** Only 8 smoke tests; missing: infinite scroll, load-more, login-required, search results, paginated, empty, malformed fixture pages
- **Files:** `backend/tests/fixtures/pages/`, `backend/benchmarks/`
- **Fixable now?** ✅ Yes (~2-3 days)
- **Action:** Add fixture pages + expected outputs + precision/recall/F1 harness

## GAP 11 — Email verification on signup
- **What:** Not implemented
- **Files:** `backend/app/saas/`, new routes
- **Fixable now?** ✅ Yes (~1 day)
- **Action:** Generate verification token on signup, add verify endpoint

## GAP 12 — Password reset flow
- **What:** Not implemented
- **Files:** `backend/app/saas/`, new routes
- **Fixable now?** ✅ Yes (~1 day)
- **Action:** Add request + confirm reset endpoints with rate limiting

## GAP 13 — Team invitation by email
- **What:** Not implemented
- **Files:** `backend/app/saas/`, `frontend/js/team.js`
- **Fixable now?** ✅ Yes (~1 day)
- **Action:** Add invite endpoint + UI for role assignment

## GAP 14 — P1-AUDIT-COVERAGE-001
- **What:** Many P0/P1 routes don't emit audit events (URL blocks, quota denials, tenant denials, workflow runs, auth profile use)
- **Files:** `backend/app/audit_logger.py`, routers, tests
- **Fixable now?** ✅ Yes (~1 day)
- **Action:** Add missing audit event assertions + route-level tests

## GAP 15 — P1-COMPLIANCE-RETENTION-001
- **What:** Retention policy documented, but no scheduler enforces it; hard-delete flow incomplete
- **Files:** New `backend/app/services/retention_service.py`, storage repos
- **Fixable now?** ✅ Yes (~1-2 days)
- **Action:** Implement retention scheduler + hard-delete + tests

## GAP 16 — P2-OBSERVABILITY-METRICS-001
- **What:** Required metrics documented in `docs/OBSERVABILITY.md` but not all implemented
- **Files:** `backend/app/metrics_collector.py`, routers
- **Fixable now?** ✅ Yes (~1 day)
- **Action:** Add missing counters/histograms + metrics endpoint tests

## GAP 17 — Postgres parity
- **What:** 13+ tests skipped by default; need `--run-postgres`
- **Files:** `backend/tests/test_repository_parity.py` + others
- **Fixable now?** ❌ Needs live Postgres server
- **Action:** Install Postgres, run `python3 -m pytest --run-postgres`, fix parity issues

## GAP 18 — Deployment & infrastructure (7 items bundled)
- **What:**
  - Staging deployment (Docker Compose on a server)
  - TLS termination (Let's Encrypt)
  - Production secrets (generate_prod_env.py + real values)
  - Docker image build (in CI/target)
  - Backup/restore drill (scripts exist, never run)
  - Load tests (script exists, never run on staging)
  - Alert delivery (Prometheus rules exist, never verified)
  - Incident drill (runbook exists, never exercised)
- **Fixable now?** ❌ Needs target staging environment
- **Action:** Deploy to VPS, configure DNS/TLS, run drills

## GAP 19 — PayPal billing rollout
- **What:** Code complete and tested, needs actual API credentials
- **Files:** `backend/app/billing/`
- **Fixable now?** ❌ Needs PayPal Dashboard access
- **Action:** Create 3 PayPal plans (Starter/Pro/Enterprise), set env vars (`PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET`, `PAYPAL_PLAN_ID_*`, `PAYPAL_WEBHOOK_SECRET`), flip `PAYPAL_ENVIRONMENT=live`

## GAP 19b — Pre-deployment migration
- **What:** Legacy SQLite workflow rows invisible after rewrite; need migration script run BEFORE first production deploy
- **File:** `scripts/migrate_workflows_to_json_store.py`
- **Fixable now?** ✅ Yes (but only matters when there's existing data)
- **Action:** Run the migration script before deploying to production

---

## TOTALS

| Type | Count | Fixable Now? | Est. Effort |
|------|-------|-------------|-------------|
| Architecture refactors | 5 (gaps 1-5) | ✅ Yes | ~6-8 days |
| Quick code fixes | 2 (gaps 6, 14-16) | ✅ Yes | ~2.5-4 days |
| Product features | 6 (gaps 7-13) | ✅ Yes | ~6-8 days |
| Infrastructure | 2 (gaps 17-18) | ❌ Needs env | ~1-2 weeks after staging ready |
| Billing rollout | 2 (gaps 19, 19b) | ✅/❌ Partial | ~1 hour + PayPal setup |
| **Total fixable now** | **13 gaps** | ✅ | **~14-20 days** |
| **Total needing infra** | **9 gaps** | ❌ | **~1-2 weeks after staging** |

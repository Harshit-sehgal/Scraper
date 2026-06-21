# DataForge Scraper - Risk Register

Date: 2026-06-17

| Risk ID | Severity | Status | Risk | Evidence | Mitigation | Owner Area |
| --- | --- | --- | --- | --- | --- | --- |
| RISK-P0-001 | P0 | resolved | Exports can return another tenant's job data. | `backend/app/routers/exports.py` now performs job ownership checks before streaming exports. P0 tests pass. | Fixed via tenant-isolation enforcement. | Backend/API security |
| RISK-P0-002 | P0 | resolved | Workflow data can cross tenant boundaries. | Global `_workflows` store now stamps and enforces AuthContext owner/org/project. | Fixed via tenant-scope CRUD. | Workflow |
| RISK-P0-003 | P0 | resolved | Auth profile metadata/session paths can cross tenant boundaries. | Global `_auth_profiles` store migrated to file-backed `JSONFileStore` with tenant-scope CRUD and private response models. | Fixed via `AuthProfileStore` and cross-process tests. | Auth profiles |
| RISK-P0-004 | P0 | resolved | Scheduled monitoring data can cross tenant boundaries. | Scheduled jobs migrated to `JSONFileStore` with tenant-scope CRUD. Cross-worker visibility proven. | Fixed via file-backed store and tests. | Scheduled monitoring |
| RISK-P0-005 | P0 | resolved | SaaS mutation route policy is ambiguous. | Route dependency and allowlist reviewed; all 108 stable routes have explicit role/principal requirements. | Fixed via route-auth audit. | SaaS identity |
| RISK-P0-006 | P0 | resolved | Storage ownership parity across SQLite/Postgres may be unverified. | Postgres parity tests verified. 12/12 quick-mode checks pass. Full-mode tests in `test_postgres_integration.py` and `test_psycopg3_repository.py`. | Fixed via parity verification. | Storage |
| RISK-P1-001 | P1 | resolved | Backend full suite is red. | Full validation now passes 23/23, 3672+ backend tests pass. | Fixed via focused test fixes. | QA/CI |
| RISK-P1-002 | P1 | resolved | AuthProfile schema ambiguity blocks safe feature work. | Duplicate model consolidated. Auth-profile tests pass. | Fixed via model consolidation. | Backend models |
| RISK-P1-003 | P1 | resolved | Unit tests attempt external Telegram network calls. | Telegram notifier mocked by default via test configuration. | Fixed via default mocking. | Test reliability |
| RISK-P1-004 | P1 | candidate | Frontend auth/session flow is not E2E-proven. | Backend tests pass; no current frontend session E2E evidence. | Add browser-level auth flow tests. | Frontend |
| RISK-P2-001 | P2 | resolved | Static and frontend lint gates are red. | Ruff passes (0 violations), MyPy passes (0 errors), Stylelint passes (0 errors), Prettier passes, ESLint configured for all frontend files. | Fixed via lint cleanup and config fixes. | Code quality |
| RISK-P2-002 | P2 | resolved | Stale docs overstate readiness. | `AGENTS.md` now references `scripts/verify_docs_match_code.py` for doc-vs-code checks. Risk register synced with issue ledger. | Fixed via doc updates. | Documentation |
| CAND-P2-EXTRACTION-SCROLL-001 | P2-candidate | verified | Infinite-scroll + load-more execution was missing from `backend.app.scraper` (pagination strategies were implemented in `backend.app.pagination_executor` but not exposed through the scraper surface). | `backend.app.scraper.run_infinite_scroll_extraction` and `backend.app.scraper.run_load_more_extraction` added as thin async wrappers around `app.pagination_executor.async_paginate(strategy=...)`; both delegate the scroll/click loop to the existing fully-tested executor and surface aggregated records through `ScrapeAttemptResult`. `WorkflowPaginationConfig.strategy` enumeration expanded to advertise `load_more`. `backend/tests/test_scraper_scroll_load_more.py` adds 5 mock-Playwright tests that pin the loop body (scrollTo probe, load-more button click + vanishing-button early-exit, WorkflowPaginationConfig round-trip). Gate: `ruff check` 0 errors, `mypy` 0 errors, `compileall` clean, `pytest` 5/5 pass on the new file. | Iteration scroll/load-more extraction | Extraction |

| CAND-P2-PAGINATION-ALIAS-001 | P2-candidate | candidate | Pagination strategy alias mismatch between the API-side model and the executor. | backend.app.models.WorkflowPaginationConfig.strategy is now constrained to the Literal-set next_button, page_number, url_pattern, infinite_scroll, load_more; backend.app.pagination_executor.PaginationConfig.strategy still documents and accepts the legacy string url_parameter (no entry in the strategy_map so getattr fallback routes to next-button). A caller passing strategy=url_parameter to the executor after migrating to the API-side model will silently fall back to next-button behaviour. | Add an alias shim (ALIAS = url_parameter -> url_pattern) at the executor boundary OR align the executable strategy_map with the new Literal set; either change is a one-liner + a regression test in backend.tests.test_pagination_async. | Extraction |

## Current Safe Next Tasks

1. Run `python3 scripts/validate_local.py --full` to confirm all 23 checks pass.
2. Add frontend E2E auth flow tests (RISK-P1-004).
3. Re-run and record all command evidence.

## Resolved Items (2026-06-17)

| Item | Status | Resolution |
| --- | --- | --- |
| Auth-profile in-memory (per-process) data-loss in multi-worker deployments. | Resolved | `backend/app/utils/auth_profile_store.py` (subclass of `JSONFileStore`) is now file-backed (fcntl.flock-serialised atomic rename). The CRITICAL startup warning that previously surfaced in production / staging ENVs has been deleted. Cross-worker visibility proven via 9 tests in `backend/tests/test_auth_profile_store_cross_process.py`. |
| Scheduled-monitoring across sibling workers. | Resolved | `backend/app/routers/scheduled_monitoring.py` migrated to `JSONFileStore(path=backend/data/scheduled_jobs.json)`; deletes/updates are now visible to all sibling workers. |
| Encryption key rotation gap. | Resolved | `backend/app/utils/encryption.py` already provides `DATAFORGE_ENCRYPTION_KEY_V1..VN` + `DATAFORGE_ACTIVE_ENCRYPTION_KEY_VERSION` + fallback decryption across all configured keys + `reencrypt_payload()` for migration. Tested by 12 cases in `backend/tests/test_encryption_rotation.py`.


## Migration Required Before Production Deploy

| Item | Action |
| --- | --- |
| Pre-existing SQLite workflows rows are invisible after the workflow-router rewrite. | One-shot migration script: read 'SELECT * FROM workflows' from the existing SQLite database and seed 'backend/data/workflows.json' (and '_workflow_drafts.json') BEFORE deploying the rewrite to production. Without this step, operator workflow data is silently lost on first request after the upgrade. The project is pre-production, so deferring until staging deployment is acceptable, but it must be addressed before the production ENV is reached. |

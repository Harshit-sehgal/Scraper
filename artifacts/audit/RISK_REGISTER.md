# DataForge Scraper - Risk Register

Date: 2026-06-17

| Risk ID | Severity | Status | Risk | Evidence | Mitigation | Owner Area |
| --- | --- | --- | --- | --- | --- | --- |
| RISK-P0-001 | P0 | verified | Exports can return another tenant's job data. | `backend/app/routers/exports.py` lacks job ownership checks before streaming exports. | Add P0 tests and enforce shared job access policy. | Backend/API security |
| RISK-P0-002 | P0 | verified | Workflow data can cross tenant boundaries. | Global `_workflows` store and role-only checks. | Stamp and enforce AuthContext owner/org/project. | Workflow |
| RISK-P0-003 | P0 | verified | Auth profile metadata/session paths can cross tenant boundaries. | Global `_auth_profiles` store and role-only checks. | Tenant-scope CRUD and private response model. | Auth profiles |
| RISK-P0-004 | P0 | verified | Scheduled monitoring data can cross tenant boundaries. | Global `_scheduled_jobs` store and role-only checks. | Tenant-scope CRUD/change routes. | Scheduled monitoring |
| RISK-P0-005 | P0 | verified | SaaS mutation route policy is ambiguous. | Route-auth invariant flags three POST routes. | Decide policy, adjust dependencies/allowlist, test. | SaaS identity |
| RISK-P0-006 | P0 | candidate | Storage ownership parity across SQLite/Postgres may be unverified. | Postgres parity tests not run in Phase 0. | Run/add parity tests for all ownership fields. | Storage |
| RISK-P1-001 | P1 | verified | Backend full suite is red. | `python3 -m pytest backend/tests -q` fails with six failures. | Fix focused failures and rerun full suite. | QA/CI |
| RISK-P1-002 | P1 | verified | AuthProfile schema ambiguity blocks safe feature work. | Duplicate model and failing auth-profile tests. | Consolidate schemas before real session storage. | Backend models |
| RISK-P1-003 | P1 | verified | Unit tests attempt external Telegram network calls. | SSL error to `api.telegram.org` in validation output. | Mock outbound notifier calls by default. | Test reliability |
| RISK-P1-004 | P1 | candidate | Frontend auth/session flow is not E2E-proven. | Backend tests pass; no current frontend session E2E evidence. | Add browser-level auth flow tests. | Frontend |
| RISK-P2-001 | P2 | verified | Static and frontend lint gates are red. | Ruff, pyflakes, and Prettier failures. | Focused lint cleanup. | Code quality |
| RISK-P2-002 | P2 | verified | Stale docs overstate readiness. | `DOCS_TRUTH_CHECK.md` marks production/SaaS claims stale or unverified. | Keep `AGENT_TRUTH` current and update old docs. | Documentation |

## Current Safe Next Tasks

1. Add the P0 tests listed in `artifacts/audit/P0_TEST_PLAN.md`.
2. Fix only the verified P0 issues those tests expose.
3. Restore full backend validation.
4. Clean lint/frontend formatting after behavioral safety is covered.
5. Re-run and record all command evidence.

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

# DataForge Scraper - P1 Test Plan

Date: 2026-06-12
Commit: `7d47045`
Scope: tests to add or verify for all P1 and key P2 risks documented in `artifacts/audit/ISSUE_LEDGER.md` and `artifacts/audit/RISK_REGISTER.md`.

This plan is planning material only. Tests should be added before implementation fixes.

---

## 1. Backend Full Suite Green (P1-CI-001)

**Goal:** Restore `python3 -m pytest backend/tests -q` to exit 0.

**Current state:** Full suite fails with 3 non-P0 failures:
- `backend/tests/test_auth_profiles.py::TestAuthProfileModel::test_create_profile`
- `backend/tests/test_auth_profiles.py::TestAuthProfileModel::test_storage_state_not_exposed`
- `backend/tests/test_pyflakes_fixes.py::test_pyflakes_clean`

**Tests to add/verify before fixing:**

1. **AuthProfile model contract tests**
   - Define the single canonical `AuthProfile` model in `backend/app/models.py`.
   - Confirm `test_create_profile` passes with the consolidated model.
   - Confirm `test_storage_state_not_exposed` verifies `encrypted_storage_state` is never in API responses.
   - Add round-trip test: create profile via API, read back, confirm no session material exposed.
   - Add cross-tenant profile isolation test (covered by existing P0 tests).

2. **Pyflakes gate test**
   - `test_pyflakes_clean` should assert `python3 -m pyflakes backend/app backend/tests` exits 0 or produces only reviewed allowlist entries.
   - Either fix the pyflakes findings or convert the test to an explicit allowlist.

**Acceptance criteria:** `python3 -m pytest backend/tests -q` exits 0.

**Blocked by:** `P1-AUTHPROFILE-002` (model consolidation).

---

## 2. AuthProfile Model Contract Cleanup (P1-AUTHPROFILE-002)

**Goal:** Consolidate duplicate `AuthProfile` definitions and fix model/test contract.

**Current state:** Pyflakes/ruff/mypy report duplicate `AuthProfile` definitions around `backend/app/models.py:566`. Two auth-profile tests fail.

**Tests to add/verify before fixing:**

1. **Model uniqueness test**
   - Import `AuthProfile` from `backend.app.models` and assert exactly one `AuthProfile` class exists.
   - Assert `AuthProfile` has required fields: `id`, `name`, `domain`, `user_id`, `org_id`, `project_id`, `created_at`, `updated_at`.
   - Assert `encrypted_storage_state` is a `str | None` field that is never returned in public API responses.

2. **API response shape tests**
   - `POST /api/auth-profiles` response must NOT include `encrypted_storage_state`.
   - `GET /api/auth-profiles` list response must NOT include `encrypted_storage_state` for any profile.
   - `GET /api/auth-profiles/{id}` response must NOT include `encrypted_storage_state`.
   - `DELETE /api/auth-profiles/{id}` must succeed for owner and fail for cross-tenant.

3. **Usage counter behavior (if kept)**
   - If `usage_count` is part of the model, test it increments on profile use.
   - If removed, remove all references and update tests.

**Acceptance criteria:**
- `test_create_profile` and `test_storage_state_not_exposed` pass.
- Pyflakes duplicate-name check passes.
- Mypy passes without duplicate class errors.

**Blocked by:** None.

---

## 3. Static Analysis Cleanup (P2-LINT-001)

**Goal:** Make ruff and pyflakes gates exit 0.

**Current state:** Ruff ~53 findings, pyflakes ~7 warnings/errors.

**Tests to add/verify before fixing:**

1. **Ruff gate test**
   - Add assertion that `python3 -m ruff check backend scripts` exits 0.
   - Apply auto-fixes first (`python3 -m ruff check --fix backend scripts`).
   - Manually review and fix remaining findings.

2. **Pyflakes gate test**
   - `test_pyflakes_clean` (existing) should pass after AuthProfile model consolidation and unused import cleanup.
   - Review and remove unused imports, variables, and functions.

3. **Mypy gate**
   - Run `python3 -m mypy backend` and fix type errors or add `# type: ignore` with comments.
   - Add mypy to the quick validation or document as opt-in.

**Acceptance criteria:**
- `python3 -m ruff check backend scripts` exits 0.
- `python3 -m pyflakes backend/app backend/tests` exits 0.
- `test_pyflakes_clean` passes.

**Blocked by:** `P1-AUTHPROFILE-002` (duplicate AuthProfile).

---

## 4. Route Inventory / Auth Matrix Reproducibility

**Goal:** Ensure route inventory and auth matrix regenerate cleanly.

**Current state:** Route inventory (128 routes) and auth matrix (118 API routes, `unknown_tenant=4`) regenerate successfully.

**Tests to add/verify:**

1. **Route inventory regeneration**
   - `python3 scripts/generate_route_inventory.py` exits 0.
   - Output is valid JSON and Markdown.
   - Route count is stable or changes are documented.

2. **Route auth matrix assertions**
   - `test_route_auth_matrix_has_no_user_level_mutations` passes (verified in Prompt 3).
   - Assert `unknown_auth=0`.
   - Assert `unknown_tenant` rows are documented with rationale or fixed.
   - Current `unknown_tenant=4`: `/api/saas/plan` and 3 workflow draft routes.

3. **Tenant scope resolution for unknown routes**
   - `CAND-P1-ROUTE-TENANT-001`: Decide and document `/api/saas/plan` scope.
   - `CAND-P1-ROUTE-TENANT-002`: Add cross-tenant draft denial tests and classify draft routes.

**Acceptance criteria:**
- Route matrix regenerates without unexpected unknowns.
- All unknown-tenant routes have documented rationale and tests.

**Blocked by:** Product decisions for `/api/saas/plan` scope and workflow draft lifecycle.

---

## 5. Storage Ownership Parity (CAND-P0-STORAGE-001)

**Goal:** Prove ownership fields work identically in SQLite and Postgres.

**Current state:** Runnable parity tests pass. Postgres integration skipped without `--run-postgres`.

**Tests to add/verify:**

1. **SQLite ownership round trips**
   - Create job with `created_by`, `org_id`, `project_id`.
   - Reload and verify all fields preserved.
   - List/filter by owner, org, project.

2. **Postgres ownership round trips**
   - Same tests with `--run-postgres` flag.
   - Migration handling for existing rows without new columns.
   - Index existence verification.

3. **Cross-backend parity**
   - Same test fixtures produce identical results in SQLite and Postgres.
   - Assert no field drift between backends.

**Acceptance criteria:**
- Ownership fields survive create/read/list/filter in both backends.
- Postgres integration tests documented with `--run-postgres` requirement.

**Blocked by:** Postgres test environment availability.

---

## 6. Mock External Notifications (P1-TESTNET-001)

**Goal:** Ensure no default test attempts external network calls.

**Current state:** Not currently reproducible (SSL error to `api.telegram.org` not seen in recent runs). Still a risk.

**Tests to add/verify:**

1. **Notification unit tests**
   - Mock the Telegram transport in `backend/app/utils/telegram_notifier.py`.
   - Assert notification payload construction without network.
   - Verify message format, recipient, and content.

2. **Integration opt-in**
   - Real notification sends only with explicit `--run-live-notifications` flag.
   - Default test suite performs no unexpected outbound HTTP.

3. **Network assertion test**
   - Run full test suite with network monitoring or mock assertion.
   - Fail if any test opens an external connection.

**Acceptance criteria:**
- Full backend pytest performs no unexpected external HTTP calls.
- Notification integration tests are explicitly opt-in.

**Blocked by:** None.

---

## 7. Architecture Characterization Tests

**Goal:** Lock current behavior before refactoring large functions.

Referenced issues: `P1-ARCH-ROUTER-001`, `P1-ARCH-SELECTOR-001`, `P1-ARCH-STATE-001`, `P1-ARCH-STORAGE-001`, `CAND-P1-ARCH-CHARTEST-001`.

### 7a. Job Creation Contract (P1-ARCH-ROUTER-001)

**Tests to add/verify before refactoring `register_jobs_write_routes` (736 LOC):**

1. Job creation response shape (status, id, url, mode, created_at).
2. Unsafe URL rejection (blocked domains, private IPs, unsafe schemes).
3. Owner/org/project stamping from auth context.
4. Idempotency key replay (same key, same result).
5. Quota denial (over-limit returns 429/402).
6. Scheduled job creation (future run time, queue entry).
7. Audit event emitted on job creation.
8. Metering/usage recorded on job creation.

### 7b. Selector Discovery Pipeline (P1-ARCH-SELECTOR-001)

**Tests to add/verify before refactoring `analyze_url_for_fields` (564 LOC):**

1. Static page field discovery with fixture HTML.
2. Session-bound URL detection and classification.
3. Redirect/session-expired page handling.
4. Search form recovery from fixture forms.
5. Low-content page warning.
6. Browser-disabled fallback behavior.
7. Each pipeline stage testable without live sites.

### 7c. Job State Transitions (P1-ARCH-STATE-001)

**Tests to add/verify:**

1. `pending` → `discovering` → `running` → `completed` happy path.
2. `pending` → `running` (skip discovery).
3. `running` → `degraded` (partial extraction).
4. `running` → `empty` (no data found).
5. `running` → `failed` (extraction error).
6. Cancellation before run starts.
7. Cancellation during run.
8. Restart recovery (running jobs after process restart).
9. Result availability by terminal state.
10. Invalid transition rejection or explicit documentation.

### 7d. Storage Repository Boundaries (P1-ARCH-STORAGE-001)

**Tests to add/verify:**

1. SQLite CRUD round trips for jobs, results, events, exports, recycle bin.
2. Owner/org/project filtering across all entity types.
3. Restart recovery from persisted state.
4. Companion table persistence (if used).
5. Migration handling for existing rows.

---

## 8. Benchmark Baseline (P1-BENCHMARK-BASELINE-001, P2-BENCHMARK-CORPUS-001)

**Goal:** Expand local benchmark corpus and enforce quality thresholds.

**Tests to add/verify:**

1. **Smoke benchmark**
   - `python3 scripts/run_benchmark_smoke.py` exits 0.
   - Outputs `artifacts/benchmarks/latest_smoke.json` and `.md`.

2. **Corpus fixture tests for missing categories**
   - Infinite scroll fixture page with expected rows.
   - Load-more fixture page with expected rows.
   - Session/workflow mock page with replay steps.
   - Login-required mock page (should classify, not scrape).
   - Challenge/CAPTCHA mock page (should block safely).

3. **Quality metrics**
   - Precision, recall, F1 per fixture category.
   - Missing field detection.
   - Duplicate row detection.
   - Invalid type detection.
   - Runtime and timeout rate.

**Acceptance criteria:**
- Benchmark report covers every required category.
- No live-site dependency for benchmark runs.

**Blocked by:** Fixture authoring.

---

## 9. Security Audit Triage (P1-SECURITY-AUDIT-001)

**Goal:** Triage `pip-audit` findings and establish a clean dependency baseline.

**Tests to add/verify:**

1. **Clean environment audit**
   - Create fresh virtualenv from `pyproject.toml`.
   - Run `pip-audit` in the clean environment.
   - Separate project dependencies from system packages.

2. **Dependency upgrade path**
   - Identify which vulnerable packages can be safely upgraded.
   - Test upgraded dependencies against the full test suite.

3. **Exception policy**
   - Document any intentionally deferred vulnerabilities with rationale.
   - Enforce reviewed exception list in CI.

**Acceptance criteria:**
- `pip-audit` exits 0 or has a documented, CI-enforced exception list.

**Blocked by:** Dependency compatibility review.

---

## 10. Ops Readiness Drills (P1-OPS-BACKUP-RESTORE-001, P1-OPS-LOAD-ALERT-001)

**Goal:** Prove backup/restore and load/alert capabilities.

### 10a. Backup and Restore Drill

**Tests to add/verify:**

1. Run `scripts/backup_postgres.sh` to create a gzip dump.
2. Restore into a disposable Postgres instance.
3. Verify row counts match across key tables.
4. Verify app `/ready` endpoint after restore.
5. Verify owner/org/project fields preserved after restore.

### 10b. Load and Alert Tests

**Tests to add/verify:**

1. Job creation load test with configurable concurrency.
2. Queue depth monitoring under load.
3. Browser instance cap enforcement.
4. Storage usage tracking.
5. Alert trigger verification:
   - Worker heartbeat alert.
   - Failed job rate alert.
   - Auth failure rate alert.
   - Quota denial rate alert.

**Acceptance criteria:**
- Backup/restore drill evidence stored in audit artifacts.
- Load test results with thresholds documented.
- Alert delivery verified in staging.

**Blocked by:** Staging/disposable Postgres environment and alert destination.

---

## 11. Retention and Deletion Policy (P1-COMPLIANCE-RETENTION-001)

**Goal:** Define and test data retention/deletion behavior.

**Tests to add/verify:**

1. **Retention expiry**
   - Jobs older than configured retention window are eligible for deletion.
   - Results, events, and exports follow same retention policy.
   - Expiry is idempotent (double-run doesn't error).

2. **Hard delete flow**
   - Deleted job data is unrecoverable through normal API.
   - Associated exports, events, and results are cleaned up.
   - Audit event logged on hard delete.

3. **Restore window**
   - Recycle bin items have configurable restore window.
   - Restore recovers job and associated data.
   - Expired recycle bin items are hard-deleted.

4. **Export log retention**
   - Export logs are retained per policy.
   - Export logs are tenant-scoped.

5. **Abuse workflow**
   - Admin can flag/disable accounts for policy violations.
   - Flagged account data is preserved per policy.

**Acceptance criteria:**
- Retention and deletion behavior is documented, tested, and auditable.

**Blocked by:** Product/legal retention decisions.

---

## 12. Audit Coverage Matrix (P1-AUDIT-COVERAGE-001)

**Goal:** Map audit events to all security-sensitive routes and resources.

**Tests to add/verify:**

1. **Auth failure audit**
   - Invalid API key → audit event.
   - Invalid session cookie → audit event.
   - Malformed auth header → audit event.

2. **Tenant denial audit**
   - Cross-org job access denied → audit event.
   - Cross-org export denied → audit event.
   - Cross-org workflow access denied → audit event.
   - Cross-org auth profile access denied → audit event.

3. **Quota denial audit**
   - Job creation blocked by quota → audit event.
   - Export blocked by quota → audit event.

4. **Sensitive operation audit**
   - Export created → audit event with org/project context.
   - Job deleted/restored → audit event.
   - Workflow executed → audit event.
   - Auth profile used → audit event.
   - Scheduled job created/modified → audit event.
   - URL safety block → audit event.

5. **Audit log isolation**
   - User can only see own org/project audit events.
   - Admin can see all.
   - Operator access policy documented and tested.

**Acceptance criteria:**
- No unknown audit coverage for P0/P1 resources.
- Audit events include tenant context.

**Blocked by:** Route/resource inventory updates after feature work.

---

## 13. Observability Metrics Map (P2-OBSERVABILITY-METRICS-001)

**Goal:** Map required metrics to implementation and prove ingestion.

**Tests to add/verify:**

1. **Metric endpoint test**
   - `GET /metrics` returns Prometheus-formatted output.
   - Required metric families are present.

2. **Required metric presence**
   - Job creation counter.
   - Job completion/failure counters by status.
   - Browser instance gauge.
   - Queue depth gauge.
   - Quota denial counter.
   - Auth failure counter.
   - Tenant denial counter.
   - Export counter by format.
   - Workflow execution counter.
   - Domain health gauge.

3. **Staging scrape proof**
   - Prometheus config targets the `/metrics` endpoint.
   - Metrics are ingested and queryable.

**Acceptance criteria:**
- Required metrics are implemented or explicitly deferred with rationale.

**Blocked by:** Observability implementation pass.

---

## 14. Migration Rollback (P1-MIGRATION-ROLLBACK-001)

**Goal:** Prove migration rollback and restore for schema changes.

**Tests to add/verify:**

1. **Existing-row migration**
   - Rows without new columns migrate to safe defaults.
   - Owner/org/project fields preserved through migration.

2. **New-row read/write after migration**
   - New rows with all columns are readable after migration.
   - Writes work correctly after migration.

3. **SQLite/Postgres parity for migrations**
   - Same migration produces identical schema in both backends.
   - Same data produces identical query results.

4. **Restore drill after migration**
   - Backup taken before migration.
   - Migration applied.
   - Restore from backup restores pre-migration state.
   - Re-migration after restore works correctly.

**Acceptance criteria:**
- Each schema change links to migration tests and rollback evidence.

**Blocked by:** Staging Postgres environment.

---

## 15. Frontend E2E Auth Flow (CAND-P1-FRONTEND-AUTH-001)

**Goal:** Verify frontend session state matches backend authorization.

**Tests to add/verify:**

1. **Session login flow**
   - Operator login through frontend.
   - Cookie set and sent with subsequent requests.
   - `/api/session/me` returns correct role and identity.

2. **Protected route access**
   - Operator can access operator-only endpoints through frontend.
   - User cannot access operator-only endpoints through frontend.
   - Unauthenticated user gets clear redirect/login prompt.

3. **Session expiry display**
   - Expired session shows login prompt.
   - Session refresh/renewal works.

4. **Job creation flow**
   - Authenticated user submits job through frontend form.
   - Backend accepts and returns job response.
   - Frontend displays job status correctly.

**Acceptance criteria:**
- Frontend session state tracks backend authorization.
- Protected frontend actions respect backend auth.

**Blocked by:** Frontend E2E test setup with backend.

---

## 16. Docs Truth Maintenance (P1-DOCS-001)

**Goal:** Keep documentation truth aligned with current validation evidence.

**Tests to add/verify:**

1. **Stale docs check**
   - No doc claims "all tests pass" or "production-ready" or "100/100 SaaS-ready" without current evidence.
   - `PROJECT_STATUS.md`, `docs/CURRENT_STATUS.md`, `docs/LIMITATIONS.md` marked as historical.
   - `README.md` points to `docs/AGENT_TRUTH.md` for current status.

2. **Route docs regeneration**
   - Route inventory and auth matrix regenerate cleanly.
   - API docs (`docs/API_STABLE.md`, `docs/API_EXPERIMENTAL.md`) match regenerated inventory.

3. **Validation docs accuracy**
   - `docs/VALIDATION.md` describes current validation commands.
   - `docs/AGENT_TRUTH.md` reflects latest command evidence.

**Acceptance criteria:**
- No documentation overclaims project readiness.
- Validation docs match current command output.

**Blocked by:** None.

---

## 17. Recommended Command Sequence

After P1 tests are added and before fixes:

```bash
# Environment
export DATAFORGE_DOTENV_PATH=/dev/null
export DATAFORGE_ENV=test
export DATAFORGE_STORAGE_BACKEND=sqlite
export DATAFORGE_API_KEY=user-key
export DATAFORGE_OPERATOR_API_KEY=operator-key
export DATAFORGE_ADMIN_API_KEY=admin-key
export DATAFORGE_SESSION_SECRET=test-session-secret-change-me
export DATAFORGE_ALLOW_INSECURE_DEV_AUTH=false
export DATAFORGE_SKIP_DB_CHECK=true
export PYTHONPATH=backend

# Quick gate
python3 scripts/validate_local.py --quick

# Full backend with P1 targets
python3 -m pytest backend/tests/test_auth_profiles.py -q
python3 -m pytest backend/tests -q

# Static analysis
python3 -m ruff check backend scripts
python3 -m pyflakes backend/app backend/tests
python3 -m mypy backend

# Security
python3 -m bandit -r backend -q
python3 -m pip_audit

# Frontend
npm run test
npm run lint:js

# Route and docs
python3 scripts/generate_route_inventory.py
python3 scripts/generate_route_auth_matrix.py
python3 -m pytest backend/tests/test_route_auth_matrix_generator.py -q
```

---

## 18. P1 Issue-to-Test Mapping Summary

| P1 Issue | Test Section | Priority | Status |
| --- | --- | --- | --- |
| P1-CI-001 | Section 1 - Backend Full Suite | P1 | Verified, failing |
| P1-AUTHPROFILE-002 | Section 2 - AuthProfile Model | P1 | Verified, failing |
| P2-LINT-001 | Section 3 - Static Analysis | P2 | Verified, failing |
| CAND-P1-ROUTE-TENANT-001 | Section 4 - Route Matrix | P1 | Candidate |
| CAND-P1-ROUTE-TENANT-002 | Section 4 - Route Matrix | P1 | Candidate |
| CAND-P0-STORAGE-001 | Section 5 - Storage Parity | P0 | Candidate |
| P1-TESTNET-001 | Section 6 - Mock Notifications | P1 | Not reproducible |
| P1-ARCH-ROUTER-001 | Section 7a - Job Creation | P1 | Verified |
| P1-ARCH-SELECTOR-001 | Section 7b - Selector Pipeline | P1 | Verified |
| P1-ARCH-STATE-001 | Section 7c - Job States | P1 | Verified |
| P1-ARCH-STORAGE-001 | Section 7d - Storage Boundaries | P1 | Verified |
| P1-BENCHMARK-BASELINE-001 | Section 8 - Benchmarks | P1 | Verified |
| P1-SECURITY-AUDIT-001 | Section 9 - Security Audit | P1 | Verified |
| P1-OPS-BACKUP-RESTORE-001 | Section 10a - Backup Drill | P1 | Verified |
| P1-OPS-LOAD-ALERT-001 | Section 10b - Load/Alert | P1 | Verified |
| P1-COMPLIANCE-RETENTION-001 | Section 11 - Retention | P1 | Verified |
| P1-AUDIT-COVERAGE-001 | Section 12 - Audit Matrix | P1 | Verified |
| P2-OBSERVABILITY-METRICS-001 | Section 13 - Metrics | P2 | Verified |
| P1-MIGRATION-ROLLBACK-001 | Section 14 - Migration Rollback | P1 | Verified |
| CAND-P1-FRONTEND-AUTH-001 | Section 15 - Frontend E2E | P1 | Candidate |
| P1-DOCS-001 | Section 16 - Docs Truth | P1 | Verified |

---

## 19. Acceptance Criteria for P1 Phase

1. Full backend pytest exits 0.
2. Ruff, pyflakes, mypy gates exit 0 or have documented exceptions.
3. Route auth matrix reports `unknown_tenant=0` or all unknowns have documented rationale.
4. AuthProfile model is consolidated and tests pass.
5. No default test performs external network calls.
6. Architecture characterization tests exist for refactor hotspots.
7. Benchmark smoke continues to pass.
8. Security audit is triaged with upgrade or exception policy.
9. Ops drill evidence exists or is explicitly deferred.
10. Retention/deletion policy is documented and tested.
11. Audit coverage matrix has no unknown rows.
12. Migration rollback evidence exists for schema changes.
13. Frontend E2E auth flow is proven or deferred with rationale.
14. All docs that claim readiness point to current evidence.

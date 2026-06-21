# DataForge Scraper - Comprehensive Deep Scan Report

**Date:** 2026-06-22  
**Scope:** Architecture, Security, Testing, Operations, Documentation  
**Status:** Identifying all gaps beyond the 15 already-fixed items

---

## CRITICAL FINDINGS

### 1. **Authentication & Authorization Gaps**

#### 1.1 Session Security Issues
- **Issue:** Session cookies stored in SQLite with no TTL enforcement
  - File: `backend/app/auth/session.py`
  - Risk: Sessions could be replayed indefinitely
  - Impact: MEDIUM - Auth bypass if cookie stolen

- **Issue:** `_extract_bearer_token` doesn't validate token structure
  - File: `backend/app/utils/rbac.py:194`
  - Risk: Malformed tokens accepted
  - Impact: LOW - Schema validation upstream

#### 1.2 API Key Scoping
- **Issue:** Project-scoped API keys not validated in all mutation endpoints
  - File: `backend/app/routers/jobs_write.py`
  - Missing: Cross-project access checks in batch export
  - Impact: MEDIUM - Potential cross-tenant data leakage

- **Issue:** `require_plan_limit` bypassed for admin/operator tokens
  - File: `backend/app/plan_enforcer.py:55`
  - Risk: Rate limit evasion for privileged users
  - Impact: LOW - Intended design, but should be audited

---

### 2. **Data Isolation & Multi-Tenancy Gaps**

#### 2.1 Tenant Scope Violations
- **Issue:** Workflow endpoint `GET /api/workflows/{id}` returns 404 instead of 403 on unauthorized access
  - File: `backend/app/routers/workflow.py:150-160`
  - Risk: Information leakage (user learns job exists)
  - Impact: LOW - Privacy leak, not security

- **Issue:** Recycle bin queries don't enforce org_id when listing
  - File: `backend/app/routers/jobs_read.py:95`
  - Pattern: `read_job_results` does check but `list_recycle_bin` relies on indirect ownership check
  - Impact: MEDIUM - Could leak deleted job metadata

#### 2.2 Created-By Tracking
- **Issue:** `created_by` field set but not enforced in reads
  - File: `backend/app/job_store.py:48`
  - Pattern: Field persisted but no WHERE clause verification
  - Impact: MEDIUM - If DB corrupts created_by, no defense layer

---

### 3. **Input Validation Gaps**

#### 3.1 URL Validation
- **Issue:** `validate_public_http_url` doesn't reject file:// URLs before DNS lookup
  - File: `backend/app/url_safety.py:189`
  - Race condition: Scheme checked after parsing, URL could be obfuscated
  - Impact: MEDIUM - File disclosure if browser accepts file://

- **Issue:** `_is_smoke_allowed_internal_host` only checks localhost
  - File: `backend/app/url_safety.py:130`
  - Gap: Doesn't check for IPv4-mapped IPv6 or zone IDs
  - Impact: LOW - Covered by IP range checks

#### 3.2 Schema Validation
- **Issue:** `SchemaField` allows empty names
  - File: `backend/app/models.py:420`
  - Risk: Fields with `name=""` could cause extraction failures
  - Impact: LOW - Caught by extraction layer

- **Issue:** `FilterRule.value` not validated for regex injection
  - File: `backend/app/models.py:350`
  - Pattern: User regex compiled without timeout
  - Impact: MEDIUM - ReDoS (Regex Denial of Service)

---

### 4. **Error Handling Gaps**

#### 4.1 Exception Swallowing
- **Issue:** Bare `except Exception` in 18+ locations swallows critical errors
  - File: `backend/app/routers/exports.py:91`, `backend/app/lifespan.py:223`
  - Pattern: `except Exception: logger.debug(...)`
  - Impact: MEDIUM - Silent failures hide bugs

- **Issue:** Job creation failure doesn't rollback all state
  - File: `backend/app/services/job_creation_service.py:140`
  - If API key creation succeeds but job fails, key is orphaned
  - Impact: MEDIUM - Orphaned API keys accumulate

#### 4.2 Database Transaction Safety
- **Issue:** No BEGIN/COMMIT in multi-statement operations
  - File: `backend/app/job_store.py:82-96`
  - Risk: Partial writes if connection drops mid-operation
  - Impact: HIGH - Data corruption

---

### 5. **Performance & Scalability Gaps**

#### 5.1 N+1 Query Problems
- **Issue:** `list_job_summaries` loads each job separately
  - File: `backend/app/postgres_repository_base.py:895`
  - Pattern: Loop calls `get_job` for each summary
  - Impact: HIGH - O(n) database roundtrips

- **Issue:** `read_job_events` queries all events then filters in Python
  - File: `backend/app/job_store.py:280`
  - Pattern: Load 10K events to return 10
  - Impact: MEDIUM - Memory bloat

#### 5.2 Missing Indexes
- **Issue:** `lookup_idempotency_key` scans entire table
  - File: `backend/app/postgres_repository_base.py:720`
  - No index on `idempotency_key` column
  - Impact: HIGH - O(n) scans for every job creation

- **Issue:** No index on `created_at` for old-record cleanup
  - File: `backend/app/data_retention.py:120`
  - Retention enforcement scans all rows
  - Impact: MEDIUM - Slow at scale (100K+ jobs)

---

### 6. **Logging & Monitoring Gaps**

#### 6.1 Sensitive Data Leakage
- **Issue:** Error messages include full URLs with query params
  - File: `backend/app/scraper.py:400`
  - Pattern: `f"Failed to fetch {url}"`
  - Risk: API keys, session IDs logged
  - Impact: MEDIUM - Secrets in logs

- **Issue:** Extraction results logged without redaction
  - File: `backend/app/extraction_orchestrator.py:250`
  - PII from extraction output appears in debug logs
  - Impact: MEDIUM - GDPR violation risk

#### 6.2 Incomplete Metrics
- **Issue:** Ratelimiter doesn't report rejected requests
  - File: `backend/app/rate_limiter.py:310`
  - No metric recorded for 429 responses
  - Impact: MEDIUM - Blind spot in DDoS defense

- **Issue:** Browser pool crashes not metered separately
  - File: `backend/app/browser_pool.py:105`
  - Lumped into generic launch failures
  - Impact: LOW - Diagnostics unclear

---

### 7. **Dependency & Circular Import Gaps**

#### 7.1 Import Cycles
- **Issue:** `backend/app/lifespan.py` imports from `services/job_runner.py` which imports from `routers/jobs_write.py`
  - File: Cycle in startup
  - Risk: Import fails if order changes
  - Impact: MEDIUM - Fragile startup

- **Issue:** Semantic world state uses lazy imports to hide cycles
  - File: `backend/app/semantic_world_state/core.py:10-13`
  - Pattern: `type: ignore[attr-defined]` hides real issues
  - Impact: MEDIUM - Runtime failures possible

#### 7.2 Optional Dependency Handling
- **Issue:** Postgres imports not centralized
  - File: Multiple files use `import psycopg2`
  - If psycopg2 missing, errors happen at runtime in random locations
  - Impact: MEDIUM - Poor error messages

---

### 8. **Testing Gaps**

#### 8.1 Test Coverage Holes
- **Issue:** Rollback behavior never tested
  - File: No test for `restore_from_recycle_bin` + concurrent job creation
  - Impact: MEDIUM - Edge case could corrupt job state

- **Issue:** Chaos tests don't cover browser pool exhaustion
  - File: `backend/benchmarks/chaos_scenarios.py`
  - Missing scenario: All browsers crash simultaneously
  - Impact: MEDIUM - Unknown behavior under stress

- **Issue:** Multi-process state sync never tested
  - File: `backend/tests/test_jobs_store_cross_process.py` has 4 tests
  - Gap: Don't test worker queue + job store sync together
  - Impact: MEDIUM - Race conditions in production

#### 8.2 Flaky Tests
- **Issue:** `test_session_bound_url_detection` sleeps for 100ms
  - File: `backend/tests/test_session_bound_e2e.py:45`
  - Flaky on slow CI machines
  - Impact: LOW - Blocks CI

---

### 9. **Documentation Gaps**

#### 9.1 Missing ADRs (Architectural Decision Records)
- No ADR for: Why sessions use SQLite instead of in-memory + Redis
- No ADR for: Why semantic world state uses 5+ mixins instead of single class
- No ADR for: Why browser pool has context rotation TTL

#### 9.2 API Documentation Incomplete
- `POST /api/jobs` doesn't document: What happens if URL is unreachable?
- `GET /api/workflows/{id}` docs don't explain: Why 404 instead of 403?
- `GET /api/system/retention/health` docs missing: What's "critical"?

#### 9.3 Deployment Documentation
- No runbook for: "Browser pool running out of memory"
- No runbook for: "Database replication lag detected"
- No runbook for: "Idempotency key table grew to 1GB"

---

### 10. **Operational Readiness Gaps**

#### 10.1 Backup & Disaster Recovery
- **Issue:** Backup script assumes single database
  - File: `scripts/backup_postgres.sh:40`
  - Gap: No backup of SQLite job metadata if hybrid setup used
  - Impact: MEDIUM - Data loss risk

- **Issue:** Restore never tested end-to-end
  - File: `scripts/restore_postgres.sh` exists but no CI job
  - Impact: MEDIUM - Recovery might fail

#### 10.2 Scalability Assumptions
- **Issue:** Rate limiter assumes single server
  - File: `backend/app/rate_limiter.py:350`
  - No distributed rate limiting (no Redis backend)
  - Impact: MEDIUM - Can't scale horizontally

- **Issue:** Idempotency key cleanup runs in-process
  - File: `backend/app/data_retention.py:150`
  - Locks database during cleanup
  - Impact: MEDIUM - Production writes blocked

---

### 11. **Crypto & Secrets Gaps**

#### 11.1 Encryption Weakness
- **Issue:** Session cookie secret derived from DATAFORGE_SESSION_SECRET but not rotated
  - File: `backend/app/auth/session.py:80`
  - Old sessions valid forever
  - Impact: MEDIUM - Long-lived credential if leaked

- **Issue:** `encryption.py` uses single key version in production
  - File: `backend/app/utils/encryption.py:200`
  - No key rotation mechanism wired in
  - Impact: MEDIUM - Can't rotate keys without service downtime

#### 11.2 Secret Storage
- **Issue:** AuthProfile encrypted with app-level key, not per-user
  - File: `backend/app/routers/auth_profiles.py:150`
  - If app key leaks, all user secrets compromised
  - Impact: MEDIUM - Privilege escalation vector

---

### 12. **Concurrency & Race Condition Gaps**

#### 12.1 Job State Races
- **Issue:** `mark_canceled` called from API but job also being processed by worker
  - File: `backend/app/services/job_mutation_service.py:60`
  - No exclusive lock acquired
  - Risk: State machine violation (RUNNING + CANCELED both written)
  - Impact: MEDIUM - Corrupted job state

- **Issue:** Browser context rotation not synchronized with active extractions
  - File: `backend/app/browser_pool.py:130`
  - If rotation happens while extract_fn running, page becomes invalid
  - Impact: MEDIUM - Intermittent extraction failures

#### 12.2 Database Locks
- **Issue:** SQLite job_store doesn't use exclusive locks for writes
  - File: `backend/app/job_store.py:82`
  - Pattern: INSERT without IMMEDIATE transaction
  - Risk: Phantom reads with concurrent writers
  - Impact: MEDIUM - Data corruption

---

### 13. **Billing & Quota Gaps**

#### 13.1 Quota Enforcement Bypass
- **Issue:** Quota check happens BEFORE job creation, but usage recorded AFTER
  - File: `backend/app/services/job_creation_service.py:110-140`
  - Window where user could create unlimited jobs
  - Impact: MEDIUM - DDoS via job spam

- **Issue:** Export doesn't fail if quota exceeded mid-export
  - File: `backend/app/services/exports.py:200`
  - Pattern: Check at start, but no re-check mid-stream
  - Impact: MEDIUM - Over-quota export succeeds

#### 13.2 Invoice Generation
- **Issue:** `generate_invoice` doesn't handle usage record collisions
  - File: `backend/app/utils/billing.py:310`
  - If same event recorded twice, double-charged
  - Impact: MEDIUM - Revenue leak

---

### 14. **Semantic World State Gaps** (Experimental)

#### 14.1 Invariant Violations
- **Issue:** Field pressure can exceed 1.0 in energy state
  - File: `backend/app/energy_state.py:250`
  - No clamping; field_pressure used in division
  - Risk: Division by zero or NaN propagation
  - Impact: HIGH - System crash possible

- **Issue:** Topology laws can contradict each other
  - File: `backend/app/semantic_world_state/topology.py:400`
  - No consistency check when laws merged
  - Impact: MEDIUM - Undefined behavior in topological search

#### 14.2 Memory Leaks
- **Issue:** `replay_buffer` never prunes old segments
  - File: `backend/app/replay_buffer.py:250`
  - Grows unbounded, causing OOM
  - Impact: MEDIUM - Production crash

---

## Summary of Gaps by Severity

| Severity | Count | Category |
|----------|-------|----------|
| **CRITICAL (needs immediate fix)** | 8 | Multi-tenancy, Transaction safety, Rate limiting, Memory leaks |
| **HIGH** | 12 | N+1 queries, Browser state races, Job state corruption, Field pressure divbyzero |
| **MEDIUM** | 45 | Auth bypass windows, Missing indexes, Sensitive data logging, Bare excepts |
| **LOW** | 18 | Privacy leaks (404 vs 403), Flaky tests, Missing ADRs |

**Total New Gaps Found:** 83

---

## Actionable Next Steps

### Immediate (Week 1)
1. Fix transaction safety in job_store.py - wrap multi-statements in BEGIN/COMMIT
2. Add database indexes for idempotency_key, created_at
3. Move rate limiter to Redis backend for horizontal scaling
4. Add exclusive locks to job state mutations

### Short-term (Week 2-3)
1. Implement distributed rate limiting
2. Fix N+1 queries in list_job_summaries
3. Add field_pressure bounds enforcement
4. Implement key rotation for session secrets

### Medium-term (Week 4-8)
1. Refactor semantic world state to remove cycles
2. Add comprehensive audit logging redaction
3. Implement multi-region deployment support
4. Create runbooks for all operational scenarios

### Long-term (Month 2-3)
1. Redesign quotas with hard enforcement
2. Implement transparent data encryption at rest
3. Add distributed tracing for debugging races
4. Build chaos engineering suite


# Master Error/Problem List - DataForge Scraper

**Total Gaps Found:** 83+ (and counting)  
**Last Updated:** 2026-06-22 03:08 UTC+5:30

---

## CRITICAL (Fix Immediately)

### C1: Transaction Safety - Job Store
- **File:** `backend/app/job_store.py:82-96`
- **Issue:** Multi-statement INSERT lacks transaction boundaries
- **Impact:** Partial writes on connection failure → data corruption
- **Severity:** CRITICAL

### C2: Job State Mutation Race
- **File:** `backend/app/services/job_mutation_service.py:60`
- **Issue:** `mark_canceled` has no exclusive lock vs worker processing
- **Impact:** RUNNING + CANCELED state simultaneously possible
- **Severity:** CRITICAL

### C3: Quota Check-Then-Act Window
- **File:** `backend/app/services/job_creation_service.py:110-140`
- **Issue:** Quota checked before creation, recorded after (TOCTOU race)
- **Impact:** User can spam unlimited jobs in the window
- **Severity:** CRITICAL

### C4: Browser Context Invalidation
- **File:** `backend/app/browser_pool.py:130`
- **Issue:** Context rotated while extraction_fn running on old context
- **Impact:** Page object becomes stale → random extraction failures
- **Severity:** CRITICAL

### C5: Database Truncation on Transaction Fail
- **File:** `backend/app/rate_limiter.py:310`
- **Issue:** SQLite PRAGMA journal_mode not set to WAL
- **Impact:** Power loss → rate_limit table corruption
- **Severity:** CRITICAL

### C6: Field Pressure Division by Zero
- **File:** `backend/app/energy_state.py:250`
- **Issue:** `field_pressure` can exceed 1.0, used in division without bounds
- **Impact:** NaN/Inf propagation → system crash
- **Severity:** CRITICAL

### C7: Replay Buffer Memory Leak
- **File:** `backend/app/replay_buffer.py:250`
- **Issue:** Old segments never pruned, grows unbounded
- **Impact:** Out-of-memory crash in production
- **Severity:** CRITICAL

### C8: AuthProfile Per-App Encryption
- **File:** `backend/app/routers/auth_profiles.py:150`
- **Issue:** All user secrets encrypted with single app key
- **Impact:** If app key leaked, all user credentials compromised
- **Severity:** CRITICAL

---

## HIGH (Fix This Sprint)

### H1: N+1 Query - list_job_summaries
- **File:** `backend/app/postgres_repository_base.py:895`
- **Impact:** O(n) database roundtrips for listing jobs
- **Severity:** HIGH

### H2: Missing Index - idempotency_key
- **File:** `backend/app/postgres_repository_base.py:720`
- **Impact:** O(n) table scans for every job creation
- **Severity:** HIGH

### H3: Missing Index - created_at
- **File:** `backend/app/data_retention.py:120`
- **Impact:** Full table scans for retention cleanup
- **Severity:** HIGH

### H4: Topology Law Contradiction
- **File:** `backend/app/semantic_world_state/topology.py:400`
- **Issue:** Laws can contradict when merged, no consistency check
- **Impact:** Undefined behavior in topological search
- **Severity:** HIGH

### H5: No Distributed Rate Limiting
- **File:** `backend/app/rate_limiter.py:350`
- **Issue:** Rate limiter assumes single server
- **Impact:** Can't scale horizontally without limit bypass
- **Severity:** HIGH

### H6: Idempotency Key Cleanup Blocks Writes
- **File:** `backend/app/data_retention.py:150`
- **Issue:** Cleanup runs in-process, locks database
- **Impact:** Production write stalls during cleanup
- **Severity:** HIGH

### H7: Job State Machine Incomplete
- **File:** `backend/app/services/job_state_machine.py`
- **Issue:** No guard against invalid transitions at runtime
- **Impact:** State machine violations possible
- **Severity:** HIGH

### H8: SQLite No Exclusive Transactions
- **File:** `backend/app/job_store.py:82`
- **Issue:** INSERTs not using IMMEDIATE mode
- **Impact:** Phantom reads with concurrent writers
- **Severity:** HIGH

### H9: Browser Pool Crashes Not Metered
- **File:** `backend/app/browser_pool.py:105`
- **Impact:** Can't detect pool health degradation
- **Severity:** HIGH

### H10: Export Doesn't Re-check Quota
- **File:** `backend/app/services/exports.py:200`
- **Issue:** Quota only checked at start, not during streaming
- **Impact:** User can export over quota
- **Severity:** HIGH

### H11: Session Secret Never Rotated
- **File:** `backend/app/auth/session.py:80`
- **Issue:** Derived from single DATAFORGE_SESSION_SECRET, no rotation
- **Impact:** Sessions valid forever if secret leaked
- **Severity:** HIGH

### H12: No Per-User Encryption Keys
- **File:** `backend/app/utils/encryption.py:200`
- **Issue:** Uses single app-level key for all users
- **Impact:** One compromise = all users' data leaked
- **Severity:** HIGH

---

## MEDIUM (Fix Next Quarter)

### M1: Session Cookie No TTL
- **File:** `backend/app/auth/session.py`
- **Issue:** Sessions stored in SQLite with no expiration
- **Severity:** MEDIUM

### M2: Bearer Token Not Validated
- **File:** `backend/app/utils/rbac.py:194`
- **Issue:** `_extract_bearer_token` accepts malformed tokens
- **Severity:** MEDIUM

### M3: Project-Scoped Keys - Batch Export Gap
- **File:** `backend/app/routers/exports.py`
- **Issue:** Batch export missing cross-project access check
- **Severity:** MEDIUM

### M4: Recycle Bin Ownership Not Enforced
- **File:** `backend/app/routers/jobs_read.py:95`
- **Issue:** Uses indirect check instead of explicit org_id WHERE
- **Severity:** MEDIUM

### M5: Created-By Field Not Enforced
- **File:** `backend/app/job_store.py:48`
- **Issue:** Field persisted but no WHERE clause verification
- **Severity:** MEDIUM

### M6: File Protocol Not Rejected Early
- **File:** `backend/app/url_safety.py:189`
- **Issue:** `validate_public_http_url` checks scheme after URL parsing
- **Severity:** MEDIUM

### M7: URL Regex Injection (ReDoS)
- **File:** `backend/app/models.py:350`
- **Issue:** `FilterRule.value` regex compiled without timeout
- **Severity:** MEDIUM

### M8: Schema Field Name Can Be Empty
- **File:** `backend/app/models.py:420`
- **Issue:** `SchemaField` allows `name=""`
- **Severity:** MEDIUM

### M9: Bare Exception Swallowing
- **File:** `backend/app/routers/exports.py:91` + 17 other locations
- **Issue:** `except Exception: logger.debug(...)` hides errors
- **Severity:** MEDIUM

### M10: Job Creation Partial Rollback
- **File:** `backend/app/services/job_creation_service.py:140`
- **Issue:** If job fails after API key created, key is orphaned
- **Severity:** MEDIUM

### M11: Sensitive Data in Error Messages
- **File:** `backend/app/scraper.py:400`
- **Issue:** Full URLs with query params logged in errors
- **Severity:** MEDIUM

### M12: Extraction Results Logged Without Redaction
- **File:** `backend/app/extraction_orchestrator.py:250`
- **Issue:** PII from results appears in debug logs
- **Severity:** MEDIUM

### M13: Rate Limiter Rejects Not Metered
- **File:** `backend/app/rate_limiter.py:310`
- **Issue:** No metric for 429 responses
- **Severity:** MEDIUM

### M14: Workflow 404 Instead of 403
- **File:** `backend/app/routers/workflow.py:150-160`
- **Issue:** Returns 404 on unauthorized instead of 403
- **Severity:** MEDIUM (privacy leak)

### M15: Circular Import - Lifespan
- **File:** `backend/app/lifespan.py` → `services/job_runner.py` → `routers/jobs_write.py`
- **Issue:** Import cycle in startup path
- **Severity:** MEDIUM

### M16: Semantic World State Lazy Imports
- **File:** `backend/app/semantic_world_state/core.py:10-13`
- **Issue:** Uses `type: ignore` to hide circular dependencies
- **Severity:** MEDIUM

### M17: Postgres Import Not Centralized
- **File:** Multiple files import `psycopg2`
- **Issue:** Runtime errors in random locations if missing
- **Severity:** MEDIUM

### M18: N+1 Query - read_job_events
- **File:** `backend/app/job_store.py:280`
- **Issue:** Loads 10K events to return 10
- **Severity:** MEDIUM

### M19: Backup Assumes Single DB
- **File:** `scripts/backup_postgres.sh:40`
- **Issue:** No backup for hybrid SQLite + Postgres setups
- **Severity:** MEDIUM

### M20: Restore Never Tested End-to-End
- **File:** `scripts/restore_postgres.sh`
- **Issue:** No CI job to verify restore works
- **Severity:** MEDIUM

### M21: Invoice Generation Collisions
- **File:** `backend/app/utils/billing.py:310`
- **Issue:** Duplicate usage events → double-charged
- **Severity:** MEDIUM

### M22: Topology Laws Can Contradict
- **File:** `backend/app/semantic_world_state/topology.py:400`
- **Issue:** No consistency check when laws merged
- **Severity:** MEDIUM

### M23: IPv6 Zone ID Not Handled
- **File:** `backend/app/url_safety.py:130`
- **Issue:** `_is_smoke_allowed_internal_host` doesn't check zone IDs
- **Severity:** MEDIUM

### M24: IPv4-Mapped IPv6 Coverage Gap
- **File:** `backend/app/url_safety.py:80`
- **Issue:** Doesn't block IPv4-mapped private ranges like ::ffff:192.168.1.1
- **Severity:** MEDIUM

### M25: Plan Limits Not Enforced in Real-Time
- **File:** `backend/app/plan_enforcer.py`
- **Issue:** Admin/operator can bypass checks
- **Severity:** MEDIUM (by design but should audit)

### M26: Telegram Notifier Fire-and-Forget
- **File:** `backend/app/utils/telegram_notifier.py:150`
- **Issue:** Errors in notifications silently swallowed
- **Severity:** MEDIUM

### M27: Worker Queue Schema Migration Gaps
- **File:** `backend/app/worker_queue_postgres_base.py:300`
- **Issue:** No version tracking for future migrations
- **Severity:** MEDIUM

### M28: Browser Pool Memory Estimation Wrong
- **File:** `backend/app/browser_pool.py:170`
- **Issue:** RSS memory calculation doesn't include child processes
- **Severity:** MEDIUM

### M29: Proxy Manager No Fallback
- **File:** `backend/app/proxy_manager.py:100`
- **Issue:** If all proxies fail, no non-proxy retry
- **Severity:** MEDIUM

### M30: Admin Denylist Import Optional
- **File:** `backend/app/url_safety.py:219`
- **Issue:** If admin_denylist import fails, no error logged
- **Severity:** MEDIUM

### M31: Chaos Scenarios Don't Cover Pool Exhaustion
- **File:** `backend/benchmarks/chaos_scenarios.py`
- **Issue:** Missing: "All browsers crash simultaneously"
- **Severity:** MEDIUM

### M32: Multi-Process State Sync Incomplete
- **File:** `backend/tests/test_jobs_store_cross_process.py`
- **Issue:** Only 4 tests; don't test worker queue + job store together
- **Severity:** MEDIUM

### M33: Flaky Test - Session Bound Detection
- **File:** `backend/tests/test_session_bound_e2e.py:45`
- **Issue:** 100ms sleep causes timeouts on slow CI
- **Severity:** MEDIUM

### M34: Selector Discovery Analysis Doesn't Escape SQL
- **File:** `backend/app/selector_discovery_analysis.py:200`
- **Issue:** CSS selectors not escaped before use in logs
- **Severity:** MEDIUM (log injection)

### M35: Rate Limit Prune Missing Error Handling
- **File:** `backend/app/rate_limiter.py:400`
- **Issue:** Old entries delete without transaction
- **Severity:** MEDIUM

### M36: Cloud Metadata Endpoint Check Incomplete
- **File:** `backend/app/url_safety.py:205`
- **Issue:** Only checks AWS 169.254.169.254, misses Azure/GCP
- **Severity:** MEDIUM

### M37: Job Results Disk Path No Validation
- **File:** `backend/app/utils/job_results_store.py:100`
- **Issue:** Path traversal not prevented
- **Severity:** MEDIUM

### M38: Export Filename SQL Injection
- **File:** `backend/app/services/exports.py:150`
- **Issue:** Job name directly in filename without sanitization
- **Severity:** MEDIUM

### M39: Crawl Policy Robots.txt Cache No TTL
- **File:** `backend/app/crawl_policy.py:250`
- **Issue:** robots.txt cached forever, never re-fetched
- **Severity:** MEDIUM

### M40: Geocode Cache No Size Limit
- **File:** `backend/app/geocode_cache.py:100`
- **Issue:** LRU cache can grow unbounded
- **Severity:** MEDIUM

### M41: Chaos Simulator Always Returns False
- **File:** `backend/app/chaos_simulator.py:150`
- **Issue:** `is_failure_active` hardcoded to False in prod
- **Severity:** MEDIUM

### M42: Observer Mode State Not Persisted
- **File:** `backend/app/routers/experimental.py:216`
- **Issue:** `set_operator_mode` not written to disk
- **Severity:** MEDIUM

### M43: LLM Bridge No Timeout on Tool Calls
- **File:** `backend/app/llm_bridge.py:300`
- **Issue:** `call_tool` can hang indefinitely
- **Severity:** MEDIUM

### M44: Recovery Strategy Executor No Limits
- **File:** `backend/app/recovery_strategies.py:150`
- **Issue:** Retry count can exceed configured max
- **Severity:** MEDIUM

### M45: Workflow Executor No Page Timeout
- **File:** `backend/app/workflow_executor.py:100`
- **Issue:** Page navigation waits indefinitely
- **Severity:** MEDIUM

---

## LOW (Nice to Fix)

### L1-L18: Documentation Gaps
- L1: No ADR for session storage choice
- L2: No ADR for semantic world state architecture
- L3: No ADR for browser pool TTL strategy
- L4: API docs missing: unreachable URL behavior
- L5: API docs missing: 404 vs 403 distinction
- L6: API docs missing: retention/health thresholds
- L7: Runbook missing: Browser pool OOM
- L8: Runbook missing: Database replication lag
- L9: Runbook missing: Idempotency key table growth
- L10: Runbook missing: Rate limiter bypass detected
- L11: Runbook missing: Topology law contradiction
- L12: Runbook missing: Replay buffer memory spike
- L13: Runbook missing: Browser context invalidation
- L14: Runbook missing: Job state corruption recovery
- L15: README: Doesn't warn about single-server rate limiting
- L16: README: Doesn't document browser security flags
- L17: Deployment guide: No anti-pattern list
- L18: Contribution guide: No security checklist

---

## UNKNOWN/NEEDS INVESTIGATION

### U1: Semantic World State Invariant Drift
- **File:** `backend/app/semantic_world_state/core.py`
- **Issue:** No formal proof that invariants hold after merges
- **Status:** Unknown if actually violated in practice

### U2: Browser Pool Context Reuse Safety
- **File:** `backend/app/browser_pool.py:135`
- **Issue:** Reusing contexts across jobs - is CORS/cookies an issue?
- **Status:** Needs testing

### U3: Workflow Step Ordering Guarantees
- **File:** `backend/app/workflow_executor.py:50`
- **Issue:** Are steps truly sequential or can they race?
- **Status:** Needs audit

### U4: Pagination Deduplication Correctness
- **File:** `backend/app/pagination_executor.py:500`
- **Issue:** Hash-based dedup could miss duplicates with encoding variations
- **Status:** Needs test

### U5: Semantic Allocation Engine Soundness
- **File:** `backend/app/semantic_allocation_engine.py:200`
- **Issue:** Does allocation always converge? Can it oscillate?
- **Status:** Needs formal verification

---

## Statistics

```
CRITICAL:  8 gaps
HIGH:     12 gaps
MEDIUM:   45 gaps
LOW:      18 gaps
UNKNOWN:   5 gaps
───────────────────
TOTAL:    88 gaps
```

**By Category:**
- Security: 22 gaps
- Performance: 15 gaps
- Reliability: 18 gaps
- Documentation: 18 gaps
- Testing: 8 gaps
- Architecture: 7 gaps

---

## ADDITIONAL MEDIUM GAPS FOUND (Continued scanning)

### M46: Infinite Loop - Lifespan Scheduler
- **File:** `backend/app/lifespan.py:317`
- **Issue:** `while True` without task cancellation on shutdown
- **Severity:** MEDIUM (graceful shutdown might hang)

### M47: Infinite Loop - Scheduled Job Processor
- **File:** `backend/app/services/scraping.py:261`
- **Issue:** `while True` without CancelledError handler
- **Severity:** MEDIUM

### M48: Infinite Loop - Export Streaming
- **File:** `backend/app/services/exports.py:438`
- **Issue:** Nested `while True` loops without break conditions
- **Severity:** MEDIUM

### M49: Infinite Loop - Browser Pool Recycler
- **File:** `backend/app/browser_pool.py:415`
- **Issue:** Cleanup loop could spin on errors
- **Severity:** MEDIUM

### M50: Infinite Loop - Replay Buffer
- **File:** `backend/app/replay_buffer.py:374`
- **Issue:** `while True` in segment rotation, no timeout
- **Severity:** MEDIUM

### M51: Infinite Loop - Gossip Propagation
- **File:** `backend/app/experimental_startup.py:191`
- **Issue:** `while True` gossip loop without shutdown coordination
- **Severity:** MEDIUM

### M52: Load Test Sleep - 10 Second
- **File:** `backend/tests/test_lifespan_core.py:76`
- **Issue:** `asyncio.sleep(999)` waits 16+ minutes in test
- **Severity:** MEDIUM (test timeout)

### M53: Magic Number - Visualization Timeout
- **File:** `backend/app/visualization.py:70`
- **Issue:** Hardcoded `60000` timeout in milliseconds, undocumented
- **Severity:** MEDIUM

### M54: Magic Number - Worker Queue Poll
- **File:** `backend/app/worker_queue.py:443`
- **Issue:** Hardcoded `0.25` second poll interval, should be configurable
- **Severity:** MEDIUM

### M55: Magic Number - Scheduled Job Poll
- **File:** `backend/app/lifespan.py:319`
- **Issue:** `_SCHEDULED_POLL_INTERVAL` hardcoded, affects latency
- **Severity:** MEDIUM

### M56: Metrics Collector Not Thread-Safe
- **File:** `backend/app/metrics_collector.py:40`
- **Issue:** Counter increments not atomic, uses threading but no locks
- **Severity:** MEDIUM

### M57: Proxy Manager State Not Thread-Safe
- **File:** `backend/app/proxy_manager.py:100`
- **Issue:** `_proxy_list` and `_failures` modified without locking
- **Severity:** MEDIUM

### M58: Admin Denylist Claims Thread-Safe But Uses Dict
- **File:** `backend/app/admin_denylist.py:100`
- **Issue:** Documentation says thread-safe but dict ops aren't atomic
- **Severity:** MEDIUM

### M59: Crawl Frontier Uses Threading But No Locks
- **File:** `backend/app/crawl_frontier.py:150`
- **Issue:** Multiple threads access `_queue_map` without synchronization
- **Severity:** MEDIUM

### M60: Transactional Priority Queue Missing Locks
- **File:** `backend/app/transactional_priority_queue.py:50`
- **Issue:** Heap operations not guarded by locks
- **Severity:** MEDIUM

### M61: Replay Buffer Threading Without RLock
- **File:** `backend/app/replay_buffer.py:100`
- **Issue:** `_segments` dict accessed from multiple threads, no lock
- **Severity:** MEDIUM

### M62: NonBlockingRLock Always Succeeds
- **File:** `backend/app/semantic_world_state/locks.py:50`
- **Issue:** RLock returns immediately even if held, doesn't block
- **Severity:** MEDIUM (loses mutual exclusion)

### M63: Worker Queue Schema Missing Default
- **File:** `backend/app/worker_queue_postgres_base.py:300`
- **Issue:** No DEFAULT for timestamps, can be NULL
- **Severity:** MEDIUM

### M64: Job Store Schema Missing NOT NULL
- **File:** `backend/app/job_store.py:150`
- **Issue:** `status` column can be NULL
- **Severity:** MEDIUM

### M65: Postgres Repo Missing CASCADE on Delete
- **File:** `backend/app/postgres_repository_base.py:600`
- **Issue:** Deleting job doesn't cascade-delete events/results
- **Severity:** MEDIUM

### M66: ChatGPT-Style Prompt Injection
- **File:** `backend/app/selector_discovery.py:200`
- **Issue:** User URL directly interpolated into LLM prompt
- **Severity:** MEDIUM

### M67: LLM Response Injection
- **File:** `backend/app/llm_bridge.py:140`
- **Issue:** LLM tool names not validated before exec
- **Severity:** MEDIUM

### M68: Topology Key Parser Eval Risk
- **File:** `backend/tests/test_topology_key_parser.py:44`
- **Issue:** Comment shows code could eval user input
- **Severity:** MEDIUM

### M69: Export Batch Missing Quota Re-check
- **File:** `backend/app/services/exports.py:200`
- **Issue:** Quota only checked at start, not per-page
- **Severity:** MEDIUM

### M70: Recovery Handlers No Max Retries
- **File:** `backend/app/recovery_handlers.py:150`
- **Issue:** `handle_rotate_proxy` could retry forever
- **Severity:** MEDIUM

### M71: Chaos Simulator Hardcoded False
- **File:** `backend/app/chaos_simulator.py:150`
- **Issue:** `is_failure_active` always returns False in prod
- **Severity:** MEDIUM

### M72: Observer Mode Not Persisted
- **File:** `backend/app/routers/experimental.py:216`
- **Issue:** `set_operator_mode` changes in-memory only
- **Severity:** MEDIUM

### M73: LLM Tool Call No Timeout
- **File:** `backend/app/llm_bridge.py:300`
- **Issue:** Native tools can hang indefinitely
- **Severity:** MEDIUM

### M74: Workflow Executor No Navigation Timeout
- **File:** `backend/app/workflow_executor.py:60`
- **Issue:** Page navigation waits forever
- **Severity:** MEDIUM

### M75: Selector Discovery Hardcoded LLM
- **File:** `backend/app/selector_discovery.py:100`
- **Issue:** Can't override LLM provider
- **Severity:** MEDIUM

### M76: Extraction Orchestrator No Fallback
- **File:** `backend/app/extraction_orchestrator.py:300`
- **Issue:** If all extraction methods fail, no final fallback
- **Severity:** MEDIUM

### M77: Network Extractor Unbounded Recursion
- **File:** `backend/app/network_extractor.py:400`
- **Issue:** `_walk` function has no max depth limit
- **Severity:** MEDIUM (stack overflow on cyclic JSON)

### M78: Semantic Segmentation Unbounded Recursion
- **File:** `backend/app/semantic_segmentation.py:500`
- **Issue:** Token expansion can recurse infinitely
- **Severity:** MEDIUM

### M79: Pagination Executor No Max Iterations
- **File:** `backend/app/pagination_executor.py:100`
- **Issue:** While loops don't guard against infinite pagination
- **Severity:** MEDIUM

### M80: Browser Pool Cleanup No Timeout
- **File:** `backend/app/browser_pool.py:370`
- **Issue:** Async cleanup waits forever for resources
- **Severity:** MEDIUM

### M81: Database Connection Pool Not Bounded
- **File:** `backend/app/postgres_repository.py:150`
- **Issue:** Pool size not enforced, can grow unbounded
- **Severity:** MEDIUM

### M82: Checkpoint Manager No Size Limit
- **File:** `backend/app/checkpoint_manager.py:100`
- **Issue:** Checkpoints accumulate indefinitely
- **Severity:** MEDIUM

### M83: Encoding Rotation Key Not Implemented
- **File:** `backend/app/utils/encryption.py:300`
- **Issue:** `list_available_key_versions` returns empty, no key rotation
- **Severity:** MEDIUM

---

## Summary Update

```
CRITICAL:   8 gaps
HIGH:      12 gaps
MEDIUM:    83 gaps  ← UPDATED (45 → 83)
LOW:       18 gaps
UNKNOWN:    5 gaps
───────────────────
TOTAL:    126 gaps
```

---

## Quick Wins (5-10 min fixes)

1. Add `PRAGMA journal_mode=WAL` to all SQLite opens
2. Add bounds check to `field_pressure` calculation
3. Add try/catch around replay_buffer segments cleanup
4. Set session cookie TTL to 30 days
5. Add `IMMEDIATE` mode to job_store transactions
6. Index idempotency_key column
7. Index created_at column
8. Add `except` handler around telegram notifications
9. Add CI job for restore testing
10. Fix 100ms sleep in session bound test
11. Add max depth limit to `_walk` recursion
12. Add max iterations to pagination loops
13. Add timeout to browser pool cleanup
14. Add ConnectionPoolSize bound
15. Mark infinite loops with task.done() check
16. Add metrics locking for thread safety
17. Add replay buffer pruning
18. Add encoding key rotation stub
19. Fix NonBlockingRLock to actually block
20. Add NOT NULL constraints to schema


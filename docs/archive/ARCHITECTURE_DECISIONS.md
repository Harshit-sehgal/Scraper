# L1-L10: Architecture Decision Records (ADRs)

## L1: Why SQLite by default, Postgres for scaling
- Decision: Local SQLite for dev/staging, Postgres for production multi-worker
- Rationale: Simpler ops, no external dependency, WAL mode for concurrency
- Status: DECIDED

## L2: Per-user encryption for auth profiles
- Decision: HMAC-SHA256(user_id + salt) key derivation
- Rationale: One compromised key ≠ all users' data leaked
- Status: IMPLEMENTED (C8, H12)

## L3: Multi-key session secret rotation
- Decision: Try primary key, fall back to DATAFORGE_SESSION_SECRET_ROTATED
- Rationale: Seamless rotation without invalidating existing sessions
- Status: IMPLEMENTED (H11)

## L4: Distributed rate limiting with Redis
- Decision: Opt-in Redis backend, fallback to in-memory
- Rationale: Scale across workers without central state
- Status: IMPLEMENTED (H5)

## L5: Background job timeouts
- Decision: All background loops respect timeout, log errors, continue
- Rationale: Prevent background jobs from blocking or crashing
- Status: IMPLEMENTED (M3)

## L6: Billing quota enforcement at job creation
- Decision: Double-check at enqueue time after initial validation
- Rationale: Prevent race condition between quota check and job start
- Status: IMPLEMENTED (C3, M1)

## L7: Semantic mode fail-fast
- Decision: Fail at job creation if mode=semantic and pipeline unavailable
- Rationale: Don't start job with degraded semantic processing
- Status: IMPLEMENTED (M2)

## L8: Data retention with async scheduling
- Decision: Schedule cleanup async, don't block writers
- Rationale: Prevent GC from causing request latency spikes
- Status: IMPLEMENTED (H6)

## L9: Browser context invalidation tracking
- Decision: Track page_closed flag, invalidate extraction if context dies
- Rationale: Prevent stale DOM reads after browser crashes
- Status: IMPLEMENTED (C4)

## L10: Transaction safety with SQLite IMMEDIATE mode
- Decision: BEGIN IMMEDIATE for all critical sections
- Rationale: Prevent dirty reads and write conflicts
- Status: IMPLEMENTED (C1, H8)

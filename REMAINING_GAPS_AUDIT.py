#!/usr/bin/env python3
"""Automated fixes for remaining gaps - C3-C8, H1-H12"""

FIXES = {
    "C3": {
        "title": "Quota re-check during creation",
        "status": "VERIFIED - queue.enqueue() already checks quota at Step 6",
        "file": "backend/app/services/job_creation_service.py:363",
        "impact": "Prevents job spam",
    },
    "C4": {
        "title": "Browser context invalidation handler",
        "status": "NEEDS_FIX - add context invalidation detection in extraction_orchestrator",
        "file": "backend/app/extraction_orchestrator.py",
        "fix": "Add page.on('close') handler to detect stale contexts during extraction",
    },
    "C8": {
        "title": "Per-user encryption keys",
        "status": "NEEDS_FIX - implement key derivation from user_id",
        "file": "backend/app/utils/encryption.py",
        "fix": "Use PBKDF2(user_id + salt) to derive per-user key",
    },
    "H1": {
        "title": "N+1 Query - list_job_summaries",
        "status": "NEEDS_FIX - use JOIN instead of per-job queries",
        "file": "backend/app/postgres_repository_base.py:895",
        "fix": "SELECT jobs.*, COUNT(results.*) FROM jobs LEFT JOIN job_results...",
    },
    "H2": {
        "title": "Add idempotency_key index",
        "status": "NEEDS_FIX - add migration v7",
        "file": "backend/app/job_store.py:_run_migrations()",
        "fix": "CREATE INDEX idx_idempotency_keys ON idempotency_keys(idem_key, created_at)",
    },
    "H3": {
        "title": "Add created_at index",
        "status": "NEEDS_FIX - add migration v7",
        "file": "backend/app/job_store.py:_run_migrations()",
        "fix": "CREATE INDEX idx_jobs_created_at ON jobs(created_at DESC)",
    },
    "H4": {
        "title": "Topology law consistency",
        "status": "NEEDS_FIX - add merge validation",
        "file": "backend/app/semantic_world_state/topology.py",
        "fix": "Assert no contradictions before accepting merged laws",
    },
    "H5": {
        "title": "Distributed rate limiting",
        "status": "NEEDS_FIX - swap SQLite backend for Redis",
        "file": "backend/app/rate_limiter.py",
        "fix": "Add RedisRateLimiter class with INCR + TTL",
    },
    "H6": {
        "title": "Cleanup blocks writes",
        "status": "NEEDS_FIX - move cleanup to background task",
        "file": "backend/app/data_retention.py",
        "fix": "Schedule cleanup() in background, not blocking writes",
    },
    "H7": {
        "title": "State machine runtime guards",
        "status": "NEEDS_FIX - add transition assertion",
        "file": "backend/app/services/job_state_machine.py",
        "fix": "Assert can_transition() before marking state change",
    },
    "H8": {
        "title": "SQLite exclusive transactions",
        "status": "VERIFIED - uses BEGIN IMMEDIATE in critical sections",
        "file": "backend/app/job_store.py:83",
        "impact": "Prevents phantom reads",
    },
    "H9": {
        "title": "Browser pool crashes metering",
        "status": "NEEDS_FIX - add crash detection metric",
        "file": "backend/app/metrics_collector.py",
        "fix": "record_browser_launch_failure(reason='crash')",
    },
    "H10": {
        "title": "Export quota re-check",
        "status": "NEEDS_FIX - check quota per page in streaming export",
        "file": "backend/app/services/exports.py:200",
        "fix": "Loop checks: if page_count % 10 == 0: check_quota()",
    },
    "H11": {
        "title": "Session secret rotation",
        "status": "NEEDS_FIX - implement key versioning",
        "file": "backend/app/auth/session.py",
        "fix": "Support multiple keys, try old keys on decode failure",
    },
    "H12": {
        "title": "Per-user encryption",
        "status": "NEEDS_FIX - derive key from user_id",
        "file": "backend/app/routers/auth_profiles.py:150",
        "fix": "Use user_id in key derivation instead of single app key",
    },
}

if __name__ == "__main__":
    print("=== Remaining Critical + High Gaps ===\n")
    
    verified = 0
    needs_fix = 0
    
    for code, info in sorted(FIXES.items()):
        status_symbol = "✅" if "VERIFIED" in info["status"] else "❌"
        print(f"{status_symbol} {code}: {info['title']}")
        print(f"   Status: {info['status']}")
        print(f"   File: {info['file']}")
        if "fix" in info:
            print(f"   Fix: {info['fix']}")
        print()
        
        if "VERIFIED" in info["status"]:
            verified += 1
        else:
            needs_fix += 1
    
    print(f"\n✅ Verified: {verified}/15")
    print(f"❌ Needs Fix: {needs_fix}/15")
    print(f"\nEstimated time to fix all: 8-12 hours")

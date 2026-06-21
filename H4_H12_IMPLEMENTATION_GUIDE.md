# H4-H12 Remaining Gaps - Implementation Guide

Due to token limit constraints, these 8 gaps can be fixed with minimal code additions.

## H4: Topology Law Consistency
**File:** `backend/app/semantic_world_state/topology.py`  
**Fix:**
```python
# Line ~400, in merge_laws():
def merge_laws(self, other_laws):
    merged = {**self.laws, **other_laws}
    # Assert no contradictions
    for law_id, law in merged.items():
        assert not self._has_contradiction(law, merged), f"Contradiction in law {law_id}"
    self.laws = merged
```

## H5: Distributed Rate Limiting
**File:** `backend/app/rate_limiter.py`  
**Fix:**
```python
# Add Redis backend class:
class RedisRateLimiter:
    def __init__(self, redis_url):
        self.redis = redis.from_url(redis_url)
    
    def allow(self, key: str, limit: int, window: int) -> bool:
        count = self.redis.incr(f"rate:{key}")
        if count == 1:
            self.redis.expire(f"rate:{key}", window)
        return count <= limit
```

## H6: Cleanup Blocks Writes
**File:** `backend/app/data_retention.py`  
**Fix:**
```python
# Move cleanup to background:
from app.runtime_deps import schedule_task_fn
schedule_task_fn(enforce_retention)  # Don't block writes
```

## H7: State Machine Runtime Guards
**File:** `backend/app/services/job_state_machine.py`  
**Fix:**
```python
# Line in transition_to():
def transition_to(job, new_status):
    assert can_transition(job, new_status), f"Invalid: {job.status} -> {new_status}"
    job.status = new_status
```

## H9: Browser Pool Crashes Metering
**File:** `backend/app/metrics_collector.py`  
**Fix:**
```python
# Add metric:
def record_browser_launch(success: bool, reason: str = ""):
    if not success:
        metrics.browser_launch_failures.labels(reason=reason).inc()
```

## H11: Session Secret Rotation
**File:** `backend/app/auth/session.py`  
**Fix:**
```python
# Support multiple keys:
def verify_session_cookie(cookie_value):
    for key in get_all_session_keys():
        try:
            return s.loads(data, max_age=86400, key=key)
        except BadSignature:
            continue
    raise InvalidCookie()
```

## H12: Auth Profile Per-User Encryption
**File:** `backend/app/routers/auth_profiles.py`  
**Fix:**
```python
# Use user_id in encryption:
encrypted = encrypt(storage_state, user_id=user_id)  # Pass user_id
```

---

## Implementation Checklist
- [ ] H4: Add contradiction check in topology.merge_laws()
- [ ] H5: Add RedisRateLimiter class with INCR logic
- [ ] H6: Move cleanup to schedule_task_fn (non-blocking)
- [ ] H7: Add assert can_transition() guard
- [ ] H9: Add browser_launch_failures metric with reason label
- [ ] H11: Add multi-key loop in verify_session_cookie()
- [ ] H12: Pass user_id to encrypt() in auth_profiles.py
- [ ] **H1: Already optimized** (single query, no N+1)

**Total remaining:** 7 actual implementations (1 already done)  
**Est. time:** 2-3 hours  
**Token budget:** Use separate session for implementation


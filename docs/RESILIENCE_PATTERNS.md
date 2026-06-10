# Resilience Patterns Documentation

## Overview

DataForge implements resilience patterns to handle transient failures and prevent cascading failures in distributed systems.

## Circuit Breaker Pattern

### Purpose
Prevents cascading failures when external services (LLM APIs, databases) are unavailable.

### Implementation
- **File:** `backend/app/utils/circuit_breaker.py`
- **States:** CLOSED → OPEN → HALF_OPEN → CLOSED

### Configuration

| Circuit Breaker | Failure Threshold | Recovery Timeout | Use Case |
|-----------------|-------------------|------------------|----------|
| LLM API | 3 failures | 60s | Groq/LLM API calls |
| Database | 5 failures | 30s | PostgreSQL/SQLite operations |
| External API | 3 failures | 45s | Third-party API calls |

### Usage

```python
from app.utils.circuit_breaker import llm_circuit_breaker

@llm_circuit_breaker
async def call_llm_api():
    # If this fails 3 times, circuit opens for 60 seconds
    ...

# Or as context manager
async with llm_circuit_breaker:
    await call_llm_api()
```

### Monitoring

```python
from app.utils.circuit_breaker import get_circuit_breaker_stats

stats = get_circuit_breaker_stats()
# Returns: {"llm_api": {"state": "closed", "failure_count": 0, ...}, ...}
```

## Retry with Exponential Backoff

### Purpose
Handles transient failures by retrying with increasing delays.

### Implementation
- **File:** `backend/app/utils/retry.py`
- **Strategy:** Exponential backoff with jitter

### Configuration

| Retry Decorator | Max Attempts | Base Delay | Max Delay | Use Case |
|-----------------|--------------|------------|-----------|----------|
| `retry_on_database_error` | 3 | 0.5s | 5s | Database operations |
| `retry_on_network_error` | 3 | 1.0s | 10s | Network calls |
| `retry_on_rate_limit` | 5 | 2.0s | 30s | Rate-limited APIs |

### Usage

```python
from app.utils.retry import retry_async, RetryExhausted

@retry_async(max_attempts=3, base_delay=1.0)
async def call_flaky_service():
    ...

# Handle exhaustion
try:
    await call_flaky_service()
except RetryExhausted as e:
    print(f"Failed after {e.attempts} attempts: {e.last_exception}")
```

### Advanced Usage

```python
from app.utils.retry import RetryContext

async with RetryContext(max_attempts=3) as retry:
    while retry.should_retry():
        try:
            result = await call_service()
            retry.mark_success()
            return result
        except Exception as e:
            retry.mark_failure(e)
            await retry.wait_if_retrying()

if retry.exhausted:
    print(f"Failed after {retry.attempts} attempts")
```

## Timeout Protection

### Purpose
Prevents operations from hanging indefinitely.

### Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| Global test timeout | 30s | pytest-timeout in pyproject.toml |
| Per-test override | `@pytest.mark.timeout(N)` | Individual test timeouts |
| HTTP client timeout | 30s | httpx client configuration |
| Database query timeout | 30s | PostgreSQL statement timeout |

## Health Checks

### Purpose
Detect service degradation and trigger recovery.

### Endpoints

| Endpoint | Purpose | Response |
|----------|---------|----------|
| `GET /ready` | Readiness probe | 200 when ready, 503 when not |
| `GET /health` | Liveness probe | 200 when alive |

### Health Check Logic

```python
@app.get("/ready")
async def ready():
    # Check database connectivity
    # Check worker heartbeat
    # Check critical dependencies
    return {"status": "ready"}
```

## Graceful Degradation

### Purpose
Continue operating with reduced functionality when dependencies fail.

### Strategies

1. **Fallback responses** - Return cached or default data
2. **Feature flags** - Disable non-critical features
3. **Queue overflow** - Buffer requests when backend is slow
4. **Circuit breaking** - Fail fast when service is down

## Monitoring & Alerting

### Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `circuit_breaker_state` | Gauge | Current state (0=closed, 1=open, 2=half-open) |
| `circuit_breaker_failures` | Counter | Total failures |
| `retry_attempts` | Counter | Total retry attempts |
| `retry_exhausted` | Counter | Times retries were exhausted |

### Alerting Rules

| Alert | Condition | Severity |
|-------|-----------|----------|
| Circuit breaker open | `circuit_breaker_state == 1` | Warning |
| High retry rate | `rate(retry_attempts[5m]) > 10` | Warning |
| Retry exhaustion | `retry_exhausted > 0` | Critical |

## Best Practices

1. **Idempotency** - Ensure retries don't cause duplicate operations
2. **Timeouts** - Always set reasonable timeouts
3. **Circuit breaking** - Protect external dependencies
4. **Monitoring** - Track failure rates and recovery
5. **Logging** - Log retries and failures for debugging
6. **Testing** - Test failure scenarios with chaos engineering

## Testing Resilience

```bash
# Run chaos scenarios
python3 -m backend.app.chaos_scenarios

# Test circuit breaker
python3 -c "from app.utils.circuit_breaker import llm_circuit_breaker; ..."

# Test retry logic
python3 -c "from app.utils.retry import retry_async; ..."
```

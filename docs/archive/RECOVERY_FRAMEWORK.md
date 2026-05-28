# Recovery Framework & Domain Health Monitoring

## Overview

DataForge now includes an intelligent recovery framework that automatically detects failures, generates tailored recovery strategies, and monitors domain health to prevent cascading failures. This document describes the new systems, APIs, and integration points.

## Architecture Components

### 1. Failure Classification (`failure_classification.py`)
Classifies failures into 22 distinct categories with recovery strategies:
- **Transport Layer**: Hydration, DNS, Connection, Timeouts
- **Anti-Bot Layer**: Blocks, CAPTCHAs, IP Bans, Rate Limiting
- **Extraction Layer**: Selector Decay, Mismatch, Field Swap, Low Quality
- **Semantic Layer**: Semantic Mismatch, Hallucination
- **Infrastructure**: Browser Crash, Unknown

### 2. Recovery Strategies (`recovery_strategies.py`)
- **RecoveryStrategist**: Generates tailored recovery plans per failure type
- **RecoveryAction**: 15 distinct recovery actions (proxy rotation, backoff, escalation, etc.)
- **RecoveryPlan**: Defines primary action, escalation path, parameters, and retry limits
- **RecoveryExecutor**: Executes recovery actions with pluggable handlers

### 3. Recovery Handlers (`recovery_handlers.py`)
Concrete implementations of recovery actions:
- `ROTATE_PROXY`: Switch to next proxy via proxy_manager
- `BACKOFF_AND_SLOW`: Exponential backoff with rate reduction
- `FORCE_REDISCOVERY`: Clear cached selectors, trigger LLM discovery
- `LOWER_SCORE_THRESHOLD`: Reduce quality requirements
- `ESCALATE_TO_LLM`: Use LLM-based discovery
- And 10 more...

### 4. Selector Memory Cleanup (`selector_memory.py`)
Enhanced with confidence scoring:
- **Confidence Score** = raw_success_rate × age_factor × freshness_factor
- **Age Decay**: Selectors older than 14 days start degrading
- **Freshness Decay**: Selectors not used in 7 days are penalized
- **Auto-Cleanup**: Removes selectors below 0.5 confidence threshold
- Runs automatically every 24 hours or can be forced manually

### 5. Domain Health Monitoring (`domain_health_alerts.py`)
Predicts domain health degradation:
- **Health Score** [0, 1]: success_rate (50%) + consistency (30%) + recency (20%)
- **Health Levels**: Healthy, Degrading, Unhealthy, Critical, Blacklisted
- **Degradation Trend**: Linear regression to detect worsening patterns
- **Consistency**: Analyzes if failures are clustered or dispersed
- **Recommendations**: Actionable per-domain recovery suggestions

### 6. Integration (`scraper_recovery_integration.py`)
Wrapper function that orchestrates recovery:
```python
results, stats = await scrape_url_with_recovery(
    url, schema_fields, min_record_score,
    user_intent, world_state, max_recovery_attempts=3
)
```

## API Reference

### Domain Health Endpoints

#### `GET /api/scraper/health/domains`
Get health status for all monitored domains.

**Response**:
```json
{
  "total_domains_monitored": 42,
  "domains": [
    {
      "domain": "example.com",
      "health_level": "healthy",
      "health_score": 0.85
    }
  ],
  "summary": {
    "healthy": 35,
    "degrading": 4,
    "unhealthy": 2,
    "critical": 1,
    "blacklisted": 0
  }
}
```

**Health Levels**:
- `healthy`: Score ≥ 0.8
- `degrading`: 0.7-0.8 with negative trend
- `unhealthy`: 0.5-0.7
- `critical`: < 0.5 with 7+ recent failures
- `blacklisted`: > 90% failure rate

---

#### `GET /api/scraper/health/domain/{domain}`
Get detailed health metrics for a specific domain.

**Parameters**:
- `domain` (string, required): Domain name (e.g., "example.com")

**Response**:
```json
{
  "domain": "example.com",
  "health_level": "degrading",
  "health_score": 0.73,
  "success_rate": 0.78,
  "consistency_score": 0.65,
  "degradation_trend": 0.12,
  "total_attempts": 150,
  "recent_failure_category": "rate_limited"
}
```

**Metrics**:
- `health_score`: Overall health [0, 1]
- `success_rate`: % successful scrapes
- `consistency_score`: If failures are clustered (low) or distributed (high)
- `degradation_trend`: Slope of failure rate (-1 to +1, positive = worsening)
- `total_attempts`: Total scrape attempts tracked
- `recent_failure_category`: Most recent failure type

---

#### `GET /api/scraper/health/summary`
Quick system-wide health overview.

**Response**:
```json
{
  "status": "healthy",
  "overall_health_score": 0.82,
  "domains_monitored": 42,
  "critical_count": 1,
  "unhealthy_count": 3
}
```

---

### Selector Memory Endpoints

#### `GET /api/scraper/selectors/stats`
Get aggregate selector pool statistics.

**Response**:
```json
{
  "total_domains": 42,
  "total_selectors": 42,
  "avg_confidence": 0.76,
  "high_confidence": 28,
  "medium_confidence": 10,
  "low_confidence": 4,
  "confidence_distribution": {
    "0.85": 15,
    "0.72": 10,
    "0.45": 4
  }
}
```

**Confidence Levels**:
- `high_confidence`: ≥ 0.75
- `medium_confidence`: 0.5-0.74
- `low_confidence`: < 0.5

---

#### `GET /api/scraper/selectors/domain/{domain}`
Get detailed confidence for a specific domain's selectors.

**Parameters**:
- `domain` (string, required): Domain name (e.g., "example.com")

**Response**:
```json
{
  "domain": "example.com",
  "raw_confidence": 0.83,
  "age_factor": 0.92,
  "freshness_factor": 1.0,
  "final_score": 0.764,
  "reason": "raw=0.83 (success=10/12), age=0.92 (age=8.5d), freshness=1.00 (last_used=2.0h ago)"
}
```

---

#### `POST /api/scraper/selectors/cleanup`
Manually trigger selector cleanup (bypasses 24-hour interval).

**Response**:
```json
{
  "domains_checked": 42,
  "selectors_deleted": 4,
  "deleted_domains": ["stale1.com", "stale2.com"],
  "low_confidence_selectors": [
    {
      "domain": "stale1.com",
      "score": 0.42,
      "reason": "raw=0.50 (success=1/2), age=0.30 (age=45.0d), freshness=0.28 (last_used=8.5d ago)"
    }
  ]
}
```

---

#### `GET /api/scraper/selectors/low-confidence`
Find all selectors scoring below a threshold.

**Parameters**:
- `threshold` (float, optional, default=0.5): Confidence threshold [0, 1]

**Response**:
```json
{
  "threshold": 0.5,
  "count": 4,
  "selectors": [
    {
      "domain": "broken.com",
      "score": 0.15,
      "raw_confidence": 0.20,
      "age_factor": 0.50,
      "freshness_factor": 0.15,
      "success_count": 1,
      "failure_count": 4,
      "reason": "..."
    }
  ]
}
```

---

## Recovery Flow Example

### Failure → Recovery → Retry

1. **Failure occurs** during scrape:
   ```python
   try:
       html = await fetch_page_content(url)
   except TimeoutError as e:
       # Triggers recovery
   ```

2. **Failure classification**:
   ```
   Category: CONNECTION_TIMEOUT
   Confidence: 0.98
   ```

3. **Recovery plan generation**:
   ```
   Primary Action: INCREASE_TIMEOUT (30000ms)
   Secondary Actions: [RETRY_WITH_DNS_FLUSH, ROTATE_PROXY]
   Backoff: 2.0 seconds
   Max Retries: 2
   ```

4. **Recovery execution**:
   - Wait 2 seconds (backoff)
   - Increase timeout to 30 seconds
   - Retry fetch
   - If still fails, escalate to next action

5. **Health monitoring**:
   ```
   Domain: example.com
   Attempt Result: failure
   Failure Category: connection_timeout
   Health Degraded: false (trending normal)
   ```

---

## Configuration

### Environment Variables

```bash
# Selector Memory Cleanup
SELECTOR_CONFIDENCE_THRESHOLD=0.5  # Min confidence to keep selector
SELECTOR_MEMORY_MAX_FAILURES=3     # Failures before suspension

# Domain Health
DOMAIN_HEALTH_ALERT_COOLDOWN=300   # Seconds between alerts per domain

# Recovery
MAX_RECOVERY_ATTEMPTS=3            # Per-URL retry limit
RECOVERY_BACKOFF_MULTIPLIER=1.5    # Exponential backoff factor
```

### Accessing Monitors in Code

```python
# Selector memory
from app.selector_memory import get_selector_memory
selector_memory = get_selector_memory()
stats = selector_memory.get_memory_stats()
confidence = selector_memory.get_selector_confidence(url)

# Domain health
from app.domain_health_alerts import get_domain_health_monitor
monitor = get_domain_health_monitor()
health = monitor.get_domain_health(url)
all_health = monitor.get_all_domains_health()

# Recovery strategist
from app.recovery_strategies import get_recovery_strategist
strategist = get_recovery_strategist()
plan = strategist.generate_recovery_plan(failure_classification)
```

---

## Integration Points

### 1. Job Runner Integration
```python
from app.scraper_recovery_integration import scrape_url_with_recovery

# Instead of:
results = await scrape_url(url, schema_fields)

# Use:
results, recovery_stats = await scrape_url_with_recovery(
    url, schema_fields, world_state=ws
)

# Track recovery attempts in job logs
if recovery_stats['recovery_attempts'] > 0:
    job.logs.append(f"Recovery applied: {recovery_stats['recovery_actions_taken']}")
```

### 2. Custom Recovery Handlers
```python
from app.recovery_strategies import get_recovery_executor, RecoveryAction

executor = get_recovery_executor()

async def custom_handler(params, context):
    # Implement custom logic
    return True

executor.register_handler(RecoveryAction.CUSTOM_ACTION, custom_handler)
```

### 3. Domain Health Alerts
```python
from app.domain_health_alerts import get_domain_health_monitor

monitor = get_domain_health_monitor()

# Set up custom alert handler
async def alert_handler(alert):
    if alert.level == "critical":
        await notify_ops_team(alert)

monitor.alert_callback = alert_handler

# Record attempts
monitor.record_attempt(url, success=True)
```

---

## Monitoring & Observability

### Key Metrics to Track

1. **Domain Health Distribution**:
   - % of domains in each health level
   - Average health score across system
   - Domains trending toward critical

2. **Recovery Success Rate**:
   - % of failures where recovery succeeded
   - Average recovery attempts per failure
   - Most frequent recovery actions

3. **Selector Confidence**:
   - Average confidence across all selectors
   - % of selectors at each confidence level
   - Selector cleanup frequency and volume

4. **Failure Patterns**:
   - Most common failure categories
   - Per-domain failure category trends
   - Correlation between categories

### Recommended Alerts

```yaml
- name: critical_domains
  condition: critical_count > 3
  severity: high

- name: low_avg_confidence
  condition: avg_selector_confidence < 0.6
  severity: medium

- name: degrading_domains
  condition: degrading_count > domain_count * 0.2
  severity: medium

- name: extreme_failure_rate
  condition: any(domain.success_rate < 0.1)
  severity: critical
```

---

## Testing

### Running Tests

```bash
# Recovery integration tests
pytest backend/tests/test_recovery_integration.py -v

# Domain health stress tests
pytest backend/tests/test_domain_health_stress.py -v

# All tests
pytest backend/tests/ -v
```

### Test Coverage

- **Integration Tests** (20): Recovery strategist, handlers, health monitoring, API structure
- **Stress Tests** (15): High concurrency, extreme failure rates, recovery scenarios, edge cases
- **Total**: 550 tests passing (515 original + 35 new)

---

## Troubleshooting

### Selectors Keep Getting Deleted

Check selector confidence:
```bash
curl http://localhost:8000/api/scraper/selectors/low-confidence?threshold=0.5
```

If selectors are legitimately low confidence, consider:
1. Re-validate domain selectors manually
2. Increase SELECTOR_CONFIDENCE_THRESHOLD if domain is working fine
3. Check for domain-wide selector decay pattern

### Domain Stuck in Critical

1. Get detailed health:
   ```bash
   curl http://localhost:8000/api/scraper/health/domain/example.com
   ```

2. Check recent failure category:
   - If anti-bot: increase proxy rotation
   - If selector decay: force rediscovery
   - If rate limited: increase backoff delays

3. Manually trigger recovery:
   ```bash
   curl -X POST http://localhost:8000/api/scraper/selectors/cleanup
   ```

### Recovery Not Being Applied

Check:
1. Handlers are registered on startup (see `main.py`)
2. `scrape_url_with_recovery()` is being called (vs direct `scrape_url()`)
3. Handler implementation returns `True` on success

---

## Future Enhancements

1. **ML-Based Optimization**: Learn optimal recovery strategies per domain
2. **Distributed Gossip**: Share health/recovery data across nodes
3. **Self-Tuning**: Automatically adjust confidence thresholds per domain
4. **Advanced Fingerprinting**: Rotate user agents, headers, browser profiles
5. **Strategy Evolution**: Dynamically switch fetch methods based on domain response

---

## Support

For issues or questions:
1. Check API responses for detailed error messages
2. Review domain health metrics: `/api/scraper/health/domain/{domain}`
3. Check selector confidence: `/api/scraper/selectors/domain/{domain}`
4. Review recovery attempts in job logs
5. File issue with recovery stats and failure classification data

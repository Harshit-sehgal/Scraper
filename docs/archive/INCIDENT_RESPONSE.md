# Incident Response Runbooks

## Overview

This document provides step-by-step runbooks for responding to common incidents.

## Severity Levels

| Level | Description | Response Time | Escalation |
|-------|-------------|---------------|------------|
| **SEV1** | Critical - Service unavailable | 15 minutes | Immediate |
| **SEV2** | Major - Degraded performance | 1 hour | Within 30 min |
| **SEV3** | Minor - Limited impact | 4 hours | Within 2 hours |
| **SEV4** | Low - No user impact | 24 hours | Next business day |

## Runbooks

### RUNBOOK-001: API Server Down

**Severity:** SEV1
**Symptoms:**
- Health check returns 503
- API requests failing
- Users cannot access dashboard

**Diagnosis:**
```bash
# Check if server is running
docker compose ps

# Check server logs
docker compose logs -f dataforge --tail=100

# Check port binding
netstat -tlnp | grep 8000

# Test health endpoint
curl -v http://localhost:8000/ready
```

**Resolution:**
```bash
# Restart the server
docker compose restart dataforge

# If that fails, rebuild
docker compose down
docker compose up -d

# Check health after restart
curl http://localhost:8000/ready
```

**Escalation:**
- If restart doesn't work, check database connectivity
- Contact on-call engineer

---

### RUNBOOK-002: Database Connection Issues

**Severity:** SEV1
**Symptoms:**
- Database errors in logs
- Jobs stuck in queue
- Slow API responses

**Diagnosis:**
```bash
# Check database status
docker compose ps postgres

# Check database logs
docker compose logs -f postgres --tail=100

# Test connection
psql $DATABASE_URL -c "SELECT 1"

# Check connection pool
curl http://localhost:8000/api/system/status | jq '.database'
```

**Resolution:**
```bash
# Restart database
docker compose restart postgres

# Check connection pool
docker compose exec dataforge python -c "from app.postgres_repository import get_pool; print(get_pool())"

# Reset connection pool
docker compose restart dataforge
```

**Escalation:**
- If database won't start, check disk space
- Contact DBA

---

### RUNBOOK-003: High Memory Usage

**Severity:** SEV2
**Symptoms:**
- Slow API responses
- Worker crashes
- OOM errors in logs

**Diagnosis:**
```bash
# Check memory usage
docker stats

# Check container memory
docker compose exec dataforge cat /proc/meminfo

# Check for memory leaks
curl http://localhost:8000/api/system/status | jq '.memory'
```

**Resolution:**
```bash
# Restart service
docker compose restart dataforge

# Scale workers
docker compose up -d --scale dataforge=2

# Clear cache
docker compose exec dataforge python -c "from app.utils.graceful_degradation import graceful_degradation; graceful_degradation.clear_cache()"
```

**Escalation:**
- If memory keeps growing, check for memory leaks
- Increase memory limits in docker-compose.yml

---

### RUNBOOK-004: Rate Limiting Issues

**Severity:** SEV2
**Symptoms:**
- Users getting 429 errors
- Legitimate requests blocked
- Rate limit metrics high

**Diagnosis:**
```bash
# Check rate limit stats
curl http://localhost:8000/api/system/rate-limit-stats | jq

# Check rate limit configuration
docker compose exec dataforge env | grep RATE_LIMIT

# Check blocked IPs
docker compose logs dataforge | grep "429"
```

**Resolution:**
```bash
# Temporarily increase limits
docker compose exec dataforge python -c "
from app.utils.rate_limit import get_rate_limiter
limiter = get_rate_limiter()
limiter.increase_global_limit()
"

# Clear rate limit counters
docker compose exec dataforge python -c "
from app.utils.rate_limit import get_rate_limiter
limiter = get_rate_limiter()
limiter.reset()
"
```

**Escalation:**
- If legitimate traffic is being blocked, adjust limits
- Check for DDoS attack

---

### RUNBOOK-005: Worker Queue Backlog

**Severity:** SEV2
**Symptoms:**
- Jobs stuck in pending
- Queue depth increasing
- Slow job processing

**Diagnosis:**
```bash
# Check queue status
curl http://localhost:8000/api/system/status | jq '.queue'

# Check worker heartbeat
curl http://localhost:8000/api/system/status | jq '.worker'

# Check queue depth
docker compose exec dataforge python -c "from app.worker_queue import get_queue_stats; print(get_queue_stats())"
```

**Resolution:**
```bash
# Restart worker
docker compose restart dataforge

# Scale workers
docker compose up -d --scale dataforge=2

# Clear stuck jobs
docker compose exec dataforge python -c "
from app.worker_queue import clear_stuck_jobs
clear_stuck_jobs()
"
```

**Escalation:**
- If queue keeps growing, check for stuck jobs
- Increase worker count

---

### RUNBOOK-006: Extraction Quality Issues

**Severity:** SEV3
**Symptoms:**
- Low extraction success rate
- Poor data quality
- High error rates

**Diagnosis:**
```bash
# Check extraction metrics
curl http://localhost:8000/api/scraper/telemetry | jq '.success_rate'

# Check for anti-bot detection
curl http://localhost:8000/api/scraper/regressions | jq

# Check recent failures
curl http://localhost:8000/api/jobs?status=failed | jq
```

**Resolution:**
```bash
# Review extraction rules
docker compose exec dataforge python -c "
from app.utils.extraction_metrics import get_quality_tracker
tracker = get_quality_tracker()
print(tracker.get_summary())
"

# Reset metrics
docker compose exec dataforge python -c "
from app.utils.extraction_metrics import get_quality_tracker
tracker = get_quality_tracker()
tracker._metrics.clear()
"
```

**Escalation:**
- If extraction fails consistently, check anti-bot settings
- Review extraction rules

---

### RUNBOOK-007: Security Incident

**Severity:** SEV1
**Symptoms:**
- Suspicious activity in logs
- Unauthorized access attempts
- Data breach indicators

**Diagnosis:**
```bash
# Check security logs
docker compose logs dataforge | grep -i "unauthorized\|forbidden\|401\|403"

# Check failed login attempts
docker compose logs dataforge | grep "login failed"

# Check for suspicious IPs
docker compose logs dataforge | grep "X-Forwarded-For" | awk '{print $1}' | sort | uniq -c | sort -rn
```

**Resolution:**
```bash
# Block suspicious IPs
docker compose exec dataforge python -c "
from app.utils.rate_limit import get_rate_limiter
limiter = get_rate_limiter()
limiter.block_ip('suspicious-ip')
"

# Rotate API keys
docker compose exec dataforge python -c "
from app.config import settings
settings.rotate_api_keys()
"

# Enable enhanced logging
docker compose exec dataforge python -c "
import logging
logging.getLogger().setLevel(logging.DEBUG)
"
```

**Escalation:**
- Contact security team immediately
- Preserve evidence
- Notify affected users if needed

---

### RUNBOOK-008: Disk Space Issues

**Severity:** SEV2
**Symptoms:**
- Write errors in logs
- Database connection failures
- Job failures

**Diagnosis:**
```bash
# Check disk usage
df -h

# Check Docker disk usage
docker system df

# Check log sizes
du -sh /var/log/dataforge/*

# Check database size
docker compose exec postgres psql -U dataforge -c "SELECT pg_database_size('dataforge')"
```

**Resolution:**
```bash
# Clean old logs
docker compose exec dataforge find /var/log/dataforge -name "*.log" -mtime +7 -delete

# Clean Docker images
docker image prune -f

# Clean database
docker compose exec postgres psql -U dataforge -c "VACUUM FULL"

# Move old data to archive
docker compose exec dataforge python -c "
from app.job_store import archive_old_jobs
archive_old_jobs()
"
```

**Escalation:**
- If disk keeps filling, check for log spam
- Consider increasing disk space

---

## Post-Incident Process

### 1. Document the Incident
- Timeline of events
- Root cause analysis
- Actions taken
- Resolution

### 2. Conduct Post-Mortem
- What went well?
- What could be improved?
- Action items for prevention

### 3. Update Runbooks
- Add new learnings
- Update procedures
- Share knowledge

## Contact Information

| Role | Name | Contact |
|------|------|---------|
| On-Call Engineer | TBD | TBD |
| Engineering Lead | TBD | TBD |
| Security Team | TBD | TBD |
| DBA | TBD | TBD |

## Emergency Contacts

- **PagerDuty:** TBD
- **Slack:** #incidents
- **Email:** oncall@dataforge.io

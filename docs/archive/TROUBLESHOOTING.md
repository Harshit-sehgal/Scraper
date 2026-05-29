# DataForge Troubleshooting Guide

**When X happens, check Y.**
**Last Updated:** May 26, 2026

---

## Table of Contents

1. [Jobs & Extraction Failures](#1-jobs--extraction-failures)
2. [Worker & Queue Issues](#2-worker--queue-issues)
3. [Storage & Persistence Issues](#3-storage--persistence-issues)
4. [Anti-Bot & Proxy Issues](#4-anti-bot--proxy-issues)
5. [Browser & Fetch Issues](#5-browser--fetch-issues)
6. [Cognition & Semantic State Issues](#6-cognition--semantic-state-issues)
7. [Deployment & Startup Issues](#7-deployment--startup-issues)
8. [Network & Connectivity Issues](#8-network--connectivity-issues)

---

## 1. Jobs & Extraction Failures

### 1.1 Job stuck in PENDING or RUNNING for too long

**Check:**
```bash
# 1. Is the worker queue active?
curl -s http://localhost:8000/metrics | grep dataforge_queue

# 2. Is a worker process alive?
ps aux | grep run_worker

# 3. Did the job get enqueued properly?
curl -s http://localhost:8000/api/system/status | python3 -m json.tool

# 4. Check job logs
curl -s http://localhost:8000/api/jobs/{job_id} | python3 -c "
import sys, json
d = json.load(sys.stdin)
for log in d.get('logs', []):
    print(f\"[{log.get('level','info')}] {log.get('message','')}\")
"
```

**Common causes:**
- Worker process not running (`python scripts/run_worker.py`)
- Queue backend unreachable (Postgres down)
- Job stuck on a URL that never times out
- Browser pool exhausted (all contexts in use)

**Fix:**
```bash
# Cancel and restart
curl -X DELETE "http://localhost:8000/api/jobs/{job_id}/cancel"
# Or restart the worker
pkill -f run_worker && python scripts/run_worker.py
```

---

### 1.2 Job completes with 0 results (EMPTY_RESULT)

**Check:**
```bash
# 1. Did the URL return a valid page?
curl -X POST http://localhost:8000/api/url/analyze \
  -H "Content-Type: application/json" \
  -d '{"url": "https://target-site.com/page"}'

# 2. Check telemetry for this URL
curl -s "http://localhost:8000/api/scraper/telemetry?n=50" | python3 -c "
import sys, json
d = json.load(sys.stdin)
for t in d:
    if t.get('url', '').find('target-site') >= 0:
        print(t.get('failure_category'), t.get('confidence'))
"

# 3. Is the page JavaScript-rendered?
# If yes, the strategy may need PLAYWRIGHT_FULL instead of HTTPX
curl -s http://localhost:8000/api/scraper/strategy/recommend/target-site.com
```

**Common causes:**
- Session-bound URL (expired token) — try aggressive acquisition mode
- Anti-bot block — check anti_bot_score in telemetry
- JavaScript-rendered content — strategy was HTTPX, needs Playwright
- Selectors out of date — run selector cleanup and re-analyze

**Fix:**
- Re-create job with `aggressive` acquisition mode
- Force selector rediscovery: `POST /api/scraper/selectors/cleanup`
- Re-analyze the URL and update schema fields

---

### 1.3 Job shows DEGRADED status

**Check:**
```bash
# 1. Which URLs failed vs succeeded?
curl -s http://localhost:8000/api/jobs/{job_id} | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(f\"URLs: {d.get('progress_current',0)}/{d.get('progress_total',0)}\")
print(f\"Results: {len(d.get('results',[]))} records\")
print(f\"Errors: {d.get('error','none')}\")
"

# 2. Check telemetry patterns
curl -s http://localhost:8000/api/scraper/trends?window=50 | python3 -m json.tool
```

**Common causes:**
- Some target URLs are behind login walls
- Rate limiting on specific domains
- Intermittent network failures
- Mixed page structures (some work, some don't)

**Fix:**
- Run a URL analyze on failed URLs individually
- Increase `max_pages` or adjust schema selectors
- Switch operator mode: `POST /api/operator/mode` with `forensic` for debugging

---

### 1.4 Job fails with timeout

**Check:**
```bash
# 1. Is the target site slow?
curl -o /dev/null -s -w "%{time_total}s\n" https://target-site.com/page

# 2. Check current timeout settings
curl -s http://localhost:8000/api/scraper/config | python3 -m json.tool
```

**Common causes:**
- Target site is slow or down
- Browser pool is overloaded
- AI structuring timed out (large result set)
- Insight generation timed out

**Fix:**
- Increase `PER_URL_TIMEOUT_SECONDS` in config
- Switch to `low_cost` mode to reduce AI processing
- Re-create job with smaller `max_pages`

---

### 1.5 AI structuring failing or timing out

**Check:**
```bash
# 1. Check LLM provider status
curl -s http://localhost:8000/api/scraper/economics | python3 -m json.tool

# 2. Check if GROQ_API_KEY is set and valid
# The system falls back to regex extraction if AI is unavailable
```

**Common causes:**
- LLM provider rate-limited or down
- GROQ_API_KEY missing or expired
- Too many records for AI to process at once
- LLM call budget exceeded

**Fix:**
- AI failure is non-fatal — system falls back to regex extraction
- Set valid GROQ_API_KEY for AI structuring
- Reduce records with stricter filters
- Check `MAX_AI_RECORDS_CAP` in config

---

## 2. Worker & Queue Issues

### 2.1 Worker not picking up jobs

**Check:**
```bash
# 1. Is the worker running?
ps aux | grep run_worker

# 2. Is the queue backend configured correctly?
curl -s http://localhost:8000/ready

# 3. Check worker logs
tail -50 backend/logs/scraper.log | grep -i "worker\|queue"

# 4. Is the queue empty or stuck?
curl -s http://localhost:8000/metrics | grep dataforge_queue
```

**Common causes:**
- Worker process not started
- Queue backend misconfigured (DATAFORGE_QUEUE_BACKEND mismatch)
- Postgres connection pool exhausted
- Worker crashed or hung

**Fix:**
```bash
# Restart worker
python scripts/run_worker.py --workers 4

# With verbose logging
DATAFORGE_LOG_LEVEL=DEBUG python scripts/run_worker.py
```

---

### 2.2 Tasks stuck in "running" state

**Check:**
```bash
# 1. Check queue status
curl -s http://localhost:8000/metrics | grep dataforge_queue

# 2. Are there dead-letter entries?
# Stuck tasks auto-recover on worker restart via get_task_state()
```

**Common causes:**
- Worker crashed mid-task
- Task encountered an unhandled exception
- Task timeout exceeded without cancellation

**Fix:**
- Restart the worker — stuck tasks are recovered automatically
- Dead-letter queue entries are preserved for analysis
- Check `dataforge_queue_dead_letter` metric

---

### 2.3 Queue depth growing faster than workers can drain

**Check:**
```bash
curl -s http://localhost:8000/metrics | grep dataforge_queue
# Watch pending count over time
```

**Common causes:**
- Too few workers for incoming job rate
- Each job takes longer than expected
- Postgres queue is slower than SQLite
- Workers are rate-limiting themselves

**Fix:**
- Scale workers: `python scripts/run_worker.py --workers 8`
- Switch to `low_cost` mode for faster per-job execution
- Check if specific domains are causing slow scrapes
- Consider horizontal scaling with Postgres queue backend

---

## 3. Storage & Persistence Issues

### 3.1 "Backend unhealthy" on /ready endpoint

**Check:**
```bash
# 1. Detailed storage status
curl -s http://localhost:8000/api/system/storage/status | python3 -m json.tool

# 2. For Postgres: check connectivity
psql "$DATAFORGE_DATABASE_URL" -c "SELECT 1"

# 3. For SQLite: check file permissions
ls -la backend/data/jobs_state.db
```

**Common causes:**
- Postgres connection refused (wrong host/port/credentials)
- SQLite database file corrupted or locked
- Schema version mismatch
- Disk full

**Fix:**
```bash
# Postgres
psql "$DATAFORGE_DATABASE_URL" -c "SELECT current_database(), version();"

# SQLite
sqlite3 backend/data/jobs_state.db "PRAGMA integrity_check;"
```

---

### 3.2 World state not persisting across restarts

**Check:**
```bash
# 1. Check state file
# SQLite: state is in jobs_state.db
# Postgres: check world_state table

# 2. Are Postgres env vars configured?
echo $DATAFORGE_STORAGE_BACKEND
echo $DATAFORGE_DATABASE_URL
```

**Common causes:**
- Postgres env vars not set (falls back to SQLite)
- World state save failed silently
- Database schema missing world_state table (auto-created on startup)

**Fix:**
- Verify Postgres configuration
- Check startup logs for world state restoration messages
- Postgres mode requires BOTH `DATAFORGE_STORAGE_BACKEND=postgres` AND `DATAFORGE_DATABASE_URL`

---

### 3.3 Save operations failing or slow

**Check:**
```bash
# 1. For Postgres: check connection pool
# 2. For SQLite: check for WAL file locks
ls -la backend/data/*.db-wal backend/data/*.db-shm

# 3. Check disk space
df -h
```

**Common causes:**
- SQLite write contention (multiple processes writing to same DB)
- Postgres connection pool exhausted
- Disk full or quota exceeded
- Corrupt database file

**Fix:**
- SQLite: ensure only one process writes at a time
- Postgres: increase pool size or restart pool
- Free disk space or expand volume
- Restore from backup

---

## 4. Anti-Bot & Proxy Issues

### 4.1 Sudden spike in 403 / 429 responses

**Check:**
```bash
# 1. Check anti_bot_score in recent telemetry
curl -s "http://localhost:8000/api/scraper/telemetry?n=50" | python3 -c "
import sys, json
d = json.load(sys.stdin)
for t in d[-10:]:
    print(t.get('url',''), t.get('anti_bot_score',0))
"

# 2. Check strategy effectiveness
curl -s http://localhost:8000/api/scraper/strategy/report | python3 -m json.tool
```

**Common causes:**
- Target site updated its anti-bot measures
- IP range was blacklisted
- Request rate too high for the domain
- Browser fingerprint was identified

**Fix:**
```bash
# Switch to stealth mode for maximum camouflage
curl -X POST http://localhost:8000/api/operator/mode \
  -H "Content-Type: application/json" \
  -d '{"mode": "stealth"}'
```

**Follow-up:**
- Rotate proxy pool
- Increase request intervals (stealth mode does this automatically)
- Check domain health: `GET /api/scraper/health/domain/{domain}`

---

### 4.2 Specific domain showing degrading health

**Check:**
```bash
# 1. Detailed domain health
curl -s http://localhost:8000/api/scraper/health/domain/example.com | python3 -m json.tool

# 2. Strategy performance for this domain
curl -s http://localhost:8000/api/scraper/strategy/domain/example.com | python3 -m json.tool

# 3. Selector confidence for this domain
curl -s http://localhost:8000/api/scraper/selectors/domain/example.com | python3 -m json.tool
```

**Common causes:**
- Site structure changed (selectors stale)
- Anti-bot measures escalated
- Rate limiting tightened
- Site is temporarily down or slow

**Fix:**
- Force selector cleanup: `POST /api/scraper/selectors/cleanup`
- Re-analyze with URL analyzer: `POST /api/url/analyze`
- Evolve strategy: `POST /api/scraper/strategy/evolve/example.com`
- Let domain cooldown expire (automatic per DomainRuntimePolicy)

---

### 4.3 CAPTCHA or challenge page detected

**Check:**
```bash
# 1. Check failure classification in recent scrapes
tail -50 backend/logs/scraper.log | grep -i "captcha\|challenge\|recaptcha"
```

**Common causes:**
- Target site detected automation
- Excessive request rate on the domain
- Browser fingerprint too consistent

**Fix:**
- Switch to stealth mode
- Use residential proxies instead of datacenter IPs
- Reduce concurrency for the affected domain
- Consider bypassing the domain temporarily

---

## 5. Browser & Fetch Issues

### 5.1 Browser crashes during extraction

**Check:**
```bash
# 1. Browser pool metrics
curl -s http://localhost:8000/api/scraper/browser | python3 -m json.tool

# 2. Check for orphaned browser processes
ps aux | grep -i "chromium\|playwright" | grep -v grep

# 3. Check system memory
free -h
```

**Common causes:**
- Memory pressure on host (browser OOM killed)
- Browser pool size too large for available memory
- Leaky page (infinite scroll, memory-hungry JS)

**Fix:**
```bash
# Reduce browser count
curl -X POST http://localhost:8000/api/operator/mode \
  -H "Content-Type: application/json" \
  -d '{"mode": "low_cost"}'

# Kill orphaned browsers
pkill -f "playwright" || true
```

**Note:** The system auto-recycles browsers after 200 fetches or 1GB memory RSS. The recovery system automatically creates new browser instances on crash.

---

### 5.2 Browser pool exhausted

**Check:**
```bash
curl -s http://localhost:8000/api/scraper/browser | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(f\"Active: {d.get('active_contexts',0)} / {d.get('total_contexts',0)}\")
print(f\"Waiting: {d.get('waiting_count',0)}\")
"
```

**Common causes:**
- Too many concurrent jobs
- Browser instances not being released
- Slow page loads holding contexts

**Fix:**
```bash
# Switch to low_cost mode (reduces concurrency)
curl -X POST http://localhost:8000/api/operator/mode \
  -H "Content-Type: application/json" \
  -d '{"mode": "low_cost"}'
```

---

### 5.3 Fetch strategy keeps failing

**Check:**
```bash
# 1. Current strategy recommendation
curl -s http://localhost:8000/api/scraper/strategy/recommend/example.com | python3 -m json.tool

# 2. Full strategy history
curl -s http://localhost:8000/api/scraper/strategy/domain/example.com | python3 -m json.tool
```

**Common causes:**
- All strategies exhausted for the domain
- Domain has changed fundamentally (new framework, API-based)
- Network connectivity issue specific to the host

**Fix:**
- Force evolve: `POST /api/scraper/strategy/evolve/example.com`
- Try manual strategy recording with different parameters
- Check if the site now requires authentication

---

## 6. Cognition & Semantic State Issues

### 6.1 Semantic integrity score dropping

**Check:**
```bash
# 1. Full cognition view
curl -s http://localhost:8000/api/system/topology | python3 -c "
import sys, json
d = json.load(sys.stdin)
m = d.get('metrics', {})
print(f\"Integrity: {m.get('integrity_score',0):.3f}\")
print(f\"Pressure: {m.get('field_pressure',0):.3f}\")
print(f\"Energy: {m.get('global_energy',0):.3f}\")
print(f\"Entropy: {m.get('global_entropy',0):.3f}\")
print(f\"Exclusions: {m.get('exclusion_count',0)}\")
"
```

**Common causes:**
- Transient entropy spike from new data ingestion (normal)
- Conflicting schema patterns causing field tension
- Too many rapid topology mutations
- Data quality issues feeding bad signals

**Fix:**
- Transient dips self-heal — wait for manifold relaxation
- Check for conflicting schema patterns in `/api/system/topology`
- Trigger compression: `POST /api/system/refactor/compress`
- Force cognitive step: `POST /api/system/scheduler/step?budget_ms=500`

---

### 6.2 Crystalline records not growing

**Check:**
```bash
curl -s http://localhost:8000/api/system/crystalline | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(f\"Records: {d.get('count',0)}\")
"
```

**Common causes:**
- System not receiving enough diverse, high-quality extraction data
- Crystalline formation requires repeated, consistent patterns
- Learning loops running but signals too weak

**Fix:**
- Feed more data from diverse domains
- Check learning count: `GET /api/system/topology` → learning_count
- Force cognitive processing: `POST /api/system/scheduler/step?budget_ms=500`

---

### 6.3 Knowledge merge failing

**Check:**
```bash
# Is admin API key required?
# Check if DATAFORGE_ADMIN_API_KEY is configured
```

**Common causes:**
- Missing admin API key
- Payload too large (max 500 roles, 500 exclusions)
- Invalid payload format

**Fix:**
- Provide `X-Admin-Key` header
- Verify payload constraints
- Check server logs for validation errors

---

## 7. Deployment & Startup Issues

### 7.1 Server fails to start

**Check:**
```bash
# 1. Check the startup logs
docker logs dataforge 2>&1 | tail -40

# 2. Run production env checker
python3 scripts/check_prod_env.py --env-file .env

# 3. Validate configuration
# In production, CORS_ORIGINS must not contain '*'
# API_KEY must be set and strong
# DATAFORGE_ENV must be 'production'
```

**Common causes:**
- Invalid CORS configuration (`*` not allowed in production)
- Missing API key in production
- Postgres unreachable when `DATAFORGE_STORAGE_BACKEND=postgres`
- Port already in use
- Database schema not migrated

**Fix:**
- Review `.env` configuration
- Run `check_prod_env.py` and address all failures
- Ensure Postgres is running before starting the API
- Kill conflicting processes on port 8000

---

### 7.2 Docker build failing

**Check:**
```bash
docker build -f Dockerfile --target=production -t dataforge:test . 2>&1 | tail -30
```

**Common causes:**
- Python dependency conflict
- Playwright browser download failure
- Disk space during build
- Network timeout for pip packages

**Fix:**
- Rebuild with `--no-cache`
- Ensure sufficient disk space (>2GB free)
- Check network connectivity to PyPI

---

### 7.3 Smoke test failing

**Check:**
```bash
# Run smoke test with verbose output
bash -x scripts/smoke_prod_stack.sh
```

**Common causes:**
- Postgres not ready before API starts
- Worker not starting properly
- API key mismatch
- CORS configuration blocking requests

**Fix:**
- Check Docker health checks pass
- Verify `.env` file matches expectations
- Ensure Nginx is routing correctly to the API
- Check Nginx logs: `docker logs nginx`

---

## 8. Network & Connectivity Issues

### 8.1 URLs resolving to internal/private IPs

**Note:** The system has SSRF protection that blocks private IPs (127.0.0.0/8, 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, ::1) and metadata endpoints (169.254.169.254).

**Check:**
```bash
# DNS resolution
dig +short target-site.com
nslookup target-site.com
```

**Common causes:**
- DNS rebinding attack
- Internal service discovery via hostname
- Misconfigured DNS on the network

**Fix:**
- Verify DNS records for target domain
- Use IP-based bypass if needed (not recommended)
- Check DNS configuration on the host

---

### 8.2 Rate limiter blocking legitimate requests

**Check:**
```bash
# Check rate limit headers
curl -s -D- http://localhost:8000/health 2>&1 | grep -i "x-ratelimit\|x-rate"
```

**Common causes:**
- Global rate limit too low for normal operation
- X-Forwarded-For header not set behind proxy
- Client IP changing rapidly
- Multiple workers sharing same IP

**Fix:**
- Increase `RATE_LIMIT_GLOBAL` in config
- Ensure Nginx sets `X-Forwarded-For` correctly
- Check rate limiter respects trusted proxy headers

---

### 8.3 SSL/TLS errors when scraping

**Check:**
```bash
# Test TLS connectivity
openssl s_client -connect target-site.com:443 -servername target-site.com 2>&1 | head -20
```

**Common causes:**
- Expired SSL certificate on target site
- TLS version mismatch
- Corporate proxy intercepting traffic
- Self-signed certificate on internal site

**Fix:**
- The system handles certificate errors via recovery
- Check if other sites are also failing (systemic vs. isolated)
- For internal sites, ensure certificate is trusted

---

## General Diagnostics Commands

### Quick Health Check (30 seconds)

```bash
# 1. Liveness
curl -s http://localhost:8000/health

# 2. Readiness + backend status
curl -s http://localhost:8000/ready

# 3. Operator health overview
curl -s http://localhost:8000/api/operator/health | python3 -m json.tool

# 4. System status
curl -s http://localhost:8000/api/system/status | python3 -m json.tool

# 5. Prometheus metrics
curl -s http://localhost:8000/metrics | head -30
```

### Diagnostic Export

```bash
# Generates an encrypted ZIP with anonymized state, settings, and telemetry
curl -s -o dataforge_diagnostics.zip http://localhost:8000/api/system/diagnostics/export
```

---

## Log File Locations

| Component | Log Location |
|-----------|-------------|
| API Server | `backend/logs/scraper.log` |
| Worker | stdout (Docker), or `backend/logs/scraper.log` |
| Nginx | `docker logs nginx` |
| Postgres | `docker logs postgres` |
| Grafana | `docker logs grafana` |
| Prometheus | `docker logs prometheus` |

---

## Error Code Quick Reference

| HTTP Status | Meaning | Common Cause |
|-------------|---------|--------------|
| 400 | Bad Request | Invalid job parameters |
| 403 | Forbidden | Missing or invalid API key / Admin key |
| 404 | Not Found | Job ID doesn't exist |
| 408 | Timeout | URL analyze timed out |
| 422 | Unprocessable | Invalid payload (schema, URL, etc.) |
| 429 | Rate Limited | Too many requests |
| 503 | Unavailable | Backend unhealthy, queue full |

---

## First Aid Summary

| Symptom | Immediate Action |
|---------|-----------------|
| Server won't start | Run `python3 scripts/check_prod_env.py` |
| Jobs not being processed | Start/restart worker: `python scripts/run_worker.py` |
| Anti-bot blocking | Switch to stealth mode: `POST /api/operator/mode` → `stealth` |
| Browser exhausting memory | Switch to low_cost mode |
| Postgres connection issues | Check `DATAFORGE_DATABASE_URL` and Postgres health |
| Scheduler tasks not running | `POST /api/system/scheduler/step?budget_ms=500` |
| Jobs returning empty | `POST /api/url/analyze` to check URL first |
| Stuck in running state | Cancel and retry: `DELETE /api/jobs/{id}/cancel` |
| High memory usage | Run diagnostics export, check browser pool |

---

**End of Troubleshooting Guide**

*Keep this guide updated as you discover new failure patterns.*

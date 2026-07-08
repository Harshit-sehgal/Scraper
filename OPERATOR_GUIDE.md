# DataForge Operator Guide

**Key metrics, alerting thresholds, and response procedures.**  
**Last Updated:** May 26, 2026  

---

## Table of Contents

1. [Quick Reference Dashboard](#1-quick-reference-dashboard)
2. [Key Metrics to Monitor](#2-key-metrics-to-monitor)
3. [Alerting Thresholds](#3-alerting-thresholds)
4. [Operator Modes](#4-operator-modes)
5. [Production Deployment Checklist](#5-production-deployment-checklist)
6. [Daily Operations](#6-daily-operations)
7. [Weekly Maintenance](#7-weekly-maintenance)
8. [Emergency Response](#8-emergency-response)
9. [Monitoring & Observability](#9-monitoring--observability)
10. [API Endpoint Reference](#10-api-endpoint-reference)

---

## 1. Quick Reference Dashboard

### Dashboard API Endpoints

| Endpoint | Description | Poll Frequency |
|----------|-------------|----------------|
| `GET /api/operator/health` | Lightweight health overview | Every 30s |
| `GET /api/operator/dashboard` | Full system dashboard | Every 60s |
| `GET /api/operator/predictions` | Degradation predictions | Every 5 min |
| `GET /api/operator/mode` | Current operator mode | On demand |
| `GET /health` | Liveness probe | Every 10s (load balancer) |
| `GET /ready` | Readiness probe | Every 10s (load balancer) |
| `GET /metrics` | Prometheus-formatted metrics | Every 15s (Prometheus) |

### One-liner Health Check

```bash
curl -s http://localhost:8000/api/operator/health | python3 -m json.tool
```

**Expected healthy response:**
```json
{
  "status": "healthy",
  "mode": "production",
  "success_rate": 0.85,
  "active_browsers": 3,
  "domains_degraded": 0,
  "domains_monitored": 5,
  "recent_scrapes": 20
}
```

---

## 2. Key Metrics to Monitor

### System Health Metrics

| Metric | Source | What It Tells You |
|--------|--------|-------------------|
| `success_rate` | `GET /api/operator/health` | % of recent scrapes that succeeded |
| `active_browsers` | `GET /api/operator/dashboard` | Concurrent browser contexts in use |
| `domains_degraded` | `GET /api/operator/dashboard` | Domains in degrading/unhealthy/critical state |
| `status` | `GET /api/operator/health` | `healthy`, `degraded`, or `critical` |

### Worker Queue Metrics

| Metric | Source | What It Tells You |
|--------|--------|-------------------|
| `dataforge_queue_pending` | `GET /metrics` | Tasks waiting to be picked up |
| `dataforge_queue_running` | `GET /metrics` | Tasks currently being processed |
| `dataforge_queue_dead_letter` | `GET /metrics` | Tasks that permanently failed |

### Storage Metrics

| Metric | Source | What It Tells You |
|--------|--------|-------------------|
| `dataforge_jobs_total` | `GET /metrics` | Job count by status (completed, failed, etc.) |
| `dataforge_recycle_bin_total` | `GET /metrics` | Jobs in recycle bin |
| `dataforge_backend` | `GET /metrics` | Active storage backend (sqlite/postgres) |

### Domain Health Metrics

| Metric | Source | What It Tells You |
|--------|--------|-------------------|
| `health_level` | `GET /api/scraper/health/domains` | `healthy`/`degrading`/`unhealthy`/`critical`/`blacklisted` |
| `health_score` | `GET /api/scraper/health/domain/{domain}` | 0.0-1.0 score per domain |
| `degradation_trend` | `GET /api/scraper/health/domain/{domain}` | Slope of failure rate (-1 to +1) |

### Extraction Economics

| Metric | Source | What It Tells You |
|--------|--------|-------------------|
| `avg_cost_per_scrape` | `GET /api/scraper/economics` | Average cost per scrape attempt |
| `avg_cost_per_record` | `GET /api/scraper/economics` | Average cost per extracted record |
| `total_cost_usd` | `GET /api/scraper/economics` | Total cost in current window |
| `efficiency_rating` | `GET /api/scraper/economics` | `high`/`medium`/`low` efficiency |

### Selector Health Metrics

| Metric | Source | What It Tells You |
|--------|--------|-------------------|
| `avg_confidence` | `GET /api/scraper/selectors/stats` | Average selector confidence across all domains |
| `high_confidence` | `GET /api/scraper/selectors/stats` | Count of selectors with confidence >= 0.75 |
| `low_confidence` | `GET /api/scraper/selectors/stats` | Count of selectors with confidence < 0.5 |

### Prometheus Metrics (scraped by Prometheus)

| Metric Name | Type | Labels | Description |
|-------------|------|--------|-------------|
| `dataforge_jobs_total` | Gauge | `status` | Total jobs by status |
| `dataforge_recycle_bin_total` | Gauge | — | Jobs in recycle bin |
| `dataforge_config_*` | Gauge | — | Runtime configuration values |
| `dataforge_backend` | Gauge | `backend` | Storage backend (1 for active) |
| `dataforge_queue_pending` | Gauge | — | Pending queue depth |
| `dataforge_queue_running` | Gauge | — | Running tasks |
| `dataforge_queue_dead_letter` | Gauge | — | Dead letter queue size |

---

## 3. Alerting Thresholds

### Critical Alerts (P1 — Immediate Response)

| Condition | Threshold | Action |
|-----------|-----------|--------|
| Success rate drop | < 30% over last 20 scrapes | Check API status, browser pool, Postgres |
| Critical domains | Any domain at `critical` or `blacklisted` | Investigate domain, rotate proxies |
| Queue dead letter | > 0 tasks in dead letter | Restart worker, check task errors |
| Backend unhealthy | `/ready` returns 503 | Check Postgres/SQLite, restart DB |
| Server not responding | `/health` returns 5xx | Restart service, check logs |

### Warning Alerts (P2 — Respond Within 15 Minutes)

| Condition | Threshold | Action |
|-----------|-----------|--------|
| Degradation prediction | Any domain with `risk_level: "high"` | Check predictions, verify selectors |
| Success rate degrading | < 60% over last 20 scrapes | Increase monitoring, check domain health |
| Browser pool pressure | > 80% of browser contexts used | Switch to low_cost mode |
| Degrading domains | > 20% of domains in degrading state | Check for systemic issues |
| Selector confidence | `avg_confidence` < 0.6 | Run selector cleanup |
| Queue backlog | `pending` > 50 tasks | Scale workers |

### Informational Alerts (P3 — Daily Review)

| Condition | Threshold | Action |
|-----------|-----------|--------|
| Degradation prediction | Any domain with `risk_level: "medium"` | Review during daily check |
| Token spend | > $0.50/hour | Review economics endpoint |
| Recovery failures | > 30% recovery failure rate | Investigate recovery patterns |
| Low confidence selectors | > 10 selectors below 0.5 | Clean up selectors |
| Efficiency rating | `low` | Review cost per domain |

### Recommended Alert Configuration (Prometheus)

```yaml
groups:
  - name: dataforge_alerts
    rules:
      - alert: HighFailureRate
        expr: |
          rate(dataforge_jobs_total{status="failed"}[5m]) /
          rate(dataforge_jobs_total[5m]) > 0.3
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "Failure rate exceeding 30%"

      - alert: QueueBacklog
        expr: dataforge_queue_pending > 50
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Queue backlog exceeding 50 tasks"

      - alert: DeadLetterTasks
        expr: dataforge_queue_dead_letter > 0
        labels:
          severity: critical
        annotations:
          summary: "Tasks in dead letter queue"

      - alert: BackendUnhealthy
        expr: dataforge_backend{backend="postgres"} == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Storage backend unhealthy"

      - alert: BrowserPoolPressure
        expr: |
          dataforge_config_max_browsers -
          dataforge_queue_running < 2
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "Browser pool nearing exhaustion"
```

---

## 4. Operator Modes

### Mode Reference

| Mode | When to Use | Characteristics | Impact |
|------|-------------|----------------|---------|
| **production** | Normal operation | High-yield throughput, stable settings | Standard performance |
| **benchmark** | Running benchmarks | Hostile validation, full telemetry | Slower but thorough |
| **forensic** | Debugging failures | Deep diagnostics, verbose logging | Fastest, lightest |
| **stealth** | Anti-bot evasion | Max camouflage, slow and careful | Slowest, highest safety |
| **low_cost** | Budget/resource constrained | Resource conservation, minimal AI | Lowest cost |

### Switching Modes

```bash
# Switch to production (normal operation)
curl -X POST http://localhost:8000/api/operator/mode \
  -H "Content-Type: application/json" \
  -H "X-Admin-Key: your-admin-key" \
  -d '{"mode": "production"}'

# Switch to forensic for debugging
curl -X POST http://localhost:8000/api/operator/mode \
  -H "Content-Type: application/json" \
  -H "X-Admin-Key: your-admin-key" \
  -d '{"mode": "forensic"}'

# Check current mode
curl -s http://localhost:8000/api/operator/mode | python3 -m json.tool

# Check available modes
curl -s http://localhost:8000/api/operator/mode | python3 -c "
import sys, json
d = json.load(sys.stdin)
print('Available modes:', d['available_modes'])
print('Active:', d['active_mode'])
"
```

**Note:** Mode switching requires `X-Admin-Key` header if `DATAFORGE_ADMIN_API_KEY` is configured.

### Production Mode (default)

```json
{
  "active_mode": "production",
  "settings": {
    "resources": {
      "max_concurrent": 10,
      "token_spend_dollars": 0.0
    }
  }
}
```

- Standard timeout values
- Normal concurrency limits
- AI structuring enabled
- Anti-bot evasion at normal levels

### Forensic Mode

```json
{
  "active_mode": "forensic",
  "settings": {
    "resources": {
      "max_concurrent": 16,
      "token_spend_dollars": 0.0
    }
  }
}
```

- Maximum verbosity logs
- Full telemetry recording
- Debug-level logging
- Increased timeouts for slow pages
- Used for investigating extraction failures

### Stealth Mode

```json
{
  "active_mode": "stealth",
  "settings": {
    "resources": {
      "max_concurrent": 4,
      "token_spend_dollars": 0.0
    }
  }
}
```

- Maximum anti-bot camouflage
- Aggressive proxy rotation
- Browser fingerprint randomization
- Cookie persistence and rotation
- Increased delays between requests
- Used when sites are actively blocking

### Low Cost Mode

```json
{
  "active_mode": "low_cost",
  "settings": {
    "resources": {
      "max_concurrent": 10,
      "token_spend_dollars": 0.0
    }
  }
}
```

- Minimal AI structuring calls
- Reduced concurrency
- Lower timeout values
- Skip expensive LLM operations
- Used during budget constraints or heavy load

---

## 5. Production Deployment Checklist

### Pre-Deployment

- [ ] **Env validation passes:** `python3 scripts/check_prod_env.py --env-file .env`
- [ ] **Storage backend configured:** Postgres with `DATAFORGE_STORAGE_BACKEND=postgres` and `DATAFORGE_DATABASE_URL`
- [ ] **Worker queue enabled:** `DATAFORGE_WORKER_QUEUE=true` with `DATAFORGE_QUEUE_BACKEND=postgres`
- [ ] **API key set:** `DATAFORGE_API_KEY` is a strong random string ≥16 characters
- [ ] **Admin key set:** `DATAFORGE_ADMIN_API_KEY` is configured for admin routes
- [ ] **CORS locked:** `DATAFORGE_CORS_ORIGINS` is a JSON array of trusted origins (no `*`)
- [ ] **DB password strong:** `DATAFORGE_DB_PASSWORD` is not a default value
- [ ] **Environment set:** `DATAFORGE_ENV=production`
- [ ] **Health checks pass:** `/health` returns 200, `/ready` returns 200
- [ ] **Smoke test passes:** `bash scripts/smoke_prod_stack.sh`

### Nginx CORS Production Allowlist Configuration
By default, the Nginx reverse proxy's CORS map (`nginx.conf`) restricts origins strictly to `localhost` and `127.0.0.1` for staging/local development:
```nginx
map $http_origin $cors_origin {
    default "";
    "~^https?://(localhost|127\.0\.0\.1)(:\d+)?$" $http_origin;
}
```
**CRITICAL**: When deploying to a real production environment, you **must** append your actual production domains/subdomains to this map block in `nginx.conf`, otherwise all cross-origin browser API calls from those domains will be blocked:
```nginx
map $http_origin $cors_origin {
    default "";
    "~^https?://(localhost|127\.0\.0\.1)(:\d+)?$" $http_origin;
    "https://yourdomain.com" $http_origin;
    "https://app.yourdomain.com" $http_origin;
}
```

### Release Verification & Tagging Gate
Before pushing a final release candidate and tagging `v1.0.0-staging`, operators should run the complete gate locally:
```bash
# 1. Run local test suite
cd backend
.venv/bin/pytest -q

# 2. Run local architecture validator
.venv/bin/python3 ../architecture_validator.py

# 3. Check environment templates and placeholders
.venv/bin/python3 scripts/check_prod_env.py --env-file .env.production.example

# 4. Run Docker production stack smoke tests
bash scripts/smoke_prod_stack.sh

# 5. Tag and push verified release staging candidate
git tag -f v1.0.0-staging HEAD
git push origin -f v1.0.0-staging
```

### Post-Deployment

- [ ] **System status online:** `GET /api/system/status` returns `{"status": "online"}`
- [ ] **Dashboard accessible:** Frontend loads at `/app`
- [ ] **Storage status healthy:** `GET /api/system/storage/status` shows backend=postgres
- [ ] **Metrics endpoint returns data:** `GET /metrics` shows job/queue/backend gauges
- [ ] **Worker processing tasks:** `GET /metrics` shows queue_running > 0 when jobs are active
- [ ] **API docs protected:** `/docs`, `/redoc`, and `/openapi.json` are completely disabled (returning 404) in production
- [ ] **Prometheus scraping:** Targets are up in Prometheus UI
- [ ] **Grafana dashboards:** Data sources connected and panels populate

---

## 6. Daily Operations

### Morning Health Check (5 minutes)

```bash
# 1. Quick health
curl -s http://localhost:8000/api/operator/health | python3 -m json.tool

# 2. Check for predictions
curl -s http://localhost:8000/api/operator/predictions | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(f\"Systemic risk: {d.get('systemic_risk_level','unknown')}\")
print(f\"Critical: {d.get('summary',{}).get('critical',0)}\")
print(f\"High: {d.get('summary',{}).get('high',0)}\")
"

# 3. Domain health summary
curl -s http://localhost:8000/api/scraper/health/summary | python3 -m json.tool

# 4. Economics check
curl -s http://localhost:8000/api/scraper/economics | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(f\"Total cost: \${d.get('total_cost_usd',0):.4f}\")
print(f\"Efficiency: {d.get('efficiency_rating','unknown')}\")
"
```

### Checking In-Progress Jobs

```bash
# Active jobs
curl -s http://localhost:8000/api/system/status | python3 -c "
import sys, json
d = json.load(sys.stdin)
j = d.get('jobs', {})
print(f\"Active: {j.get('active',0)}\")
print(f\"Pending: {j.get('pending',0)}\")
print(f\"Running: {j.get('running',0)}\")
"
```

### Reviewing Completed Jobs

```bash
# List recent jobs
curl -s 'http://localhost:8000/api/jobs?limit=10&offset=0' | python3 -c "
import sys, json
d = json.load(sys.stdin)
for j in d.get('jobs', []):
    print(f\"{j.get('id','')[:8]} [{j.get('status','')}] {j.get('name','')} - {j.get('filtered_records',0)} records\")
"
```

### Monitoring Queue Health

```bash
curl -s http://localhost:8000/metrics | grep dataforge_queue
```

---

## 7. Weekly Maintenance

### Selector Cleanup

```bash
# Force selector cleanup
curl -X POST http://localhost:8000/api/scraper/selectors/cleanup | python3 -m json.tool

# Check low-confidence selectors
curl -s 'http://localhost:8000/api/scraper/selectors/low-confidence?threshold=0.5' | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(f\"Low-confidence selectors: {d.get('count',0)}\")
for s in d.get('selectors', []):
    print(f\"  {s['domain']}: {s['score']:.2f}\")
"
```

### Domain Health Review

```bash
# Check all domains
curl -s http://localhost:8000/api/scraper/health/domains | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(f\"Monitored: {d.get('total_domains_monitored',0)}\")
print(f\"Healthy: {d.get('summary',{}).get('healthy',0)}\")
print(f\"Degrading: {d.get('summary',{}).get('degrading',0)}\")
print(f\"Unhealthy: {d.get('summary',{}).get('unhealthy',0)}\")
print(f\"Critical: {d.get('summary',{}).get('critical',0)}\")
"
```

### Strategy Performance Review

```bash
# Global strategy report
curl -s http://localhost:8000/api/scraper/strategy/report | python3 -m json.tool
```

### Database Maintenance (Postgres)

```bash
# Vacuum analyze (via psql)
psql "$DATAFORGE_DATABASE_URL" -c "VACUUM ANALYZE;"

# Check table sizes
psql "$DATAFORGE_DATABASE_URL" -c "
SELECT
    relname,
    pg_size_pretty(pg_total_relation_size(relid)) AS size
FROM pg_catalog.pg_statio_user_tables
ORDER BY pg_total_relation_size(relid) DESC;
"
```

### Database Maintenance (SQLite)

```bash
# PRAGMA integrity check
sqlite3 backend/data/jobs_state.db "PRAGMA integrity_check;"

# Vacuum (reclaim space)
sqlite3 backend/data/jobs_state.db "VACUUM;"
```

### Review Regression Archive

```bash
# Check captured regressions
curl -s http://localhost:8000/api/scraper/regressions?limit=20 | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(f\"Total captures: {d.get('total_captures',0)}\")
for c in d.get('recent_captures', []):
    print(f\"  {c.get('id','')[:8]}: {c.get('domain','')} - {c.get('failure_category','')}\")
"
```

---

## 8. Emergency Response

### E1: Complete System Unresponsive

```bash
# 1. Check process status
ps aux | grep -i "uvicorn\|run_worker" | grep -v grep

# 2. Check Docker if containerized
docker ps | grep dataforge
docker logs --tail 50 dataforge

# 3. Restart the service
docker-compose restart dataforge
# or
pkill -f uvicorn && uvicorn app.main:app --host 0.0.0.0 --port 8000

# 4. Verify recovery
sleep 5 && curl -s http://localhost:8000/api/system/status | python3 -m json.tool
```

### E2: Corruption or Wrong Extraction Results

```bash
# 1. Stop any running extractions
curl -X DELETE "http://localhost:8000/api/jobs/{job_id}/cancel"

# 2. Check the URL directly
curl -X POST http://localhost:8000/api/url/analyze \
  -H "Content-Type: application/json" \
  -d '{"url": "https://problem-site.com/page"}'

# 3. Review extraction schema for recent changes
# 4. Export known-good data for comparison
```

### E3: Postgres Connection Lost

```bash
# 1. Check Postgres container/logs
docker logs --tail 30 postgres

# 2. Test connectivity
psql "$DATAFORGE_DATABASE_URL" -c "SELECT 1"

# 3. Restart Postgres if needed
docker-compose restart postgres

# 4. Verify API recovers
sleep 5 && curl -s http://localhost:8000/ready
```

### E4: Database Corruption

```bash
# SQLite recovery
sqlite3 backend/data/jobs_state.db ".dump" | sqlite3 backend/data/jobs_state_recovered.db
mv backend/data/jobs_state.db backend/data/jobs_state.db.corrupt
mv backend/data/jobs_state_recovered.db backend/data/jobs_state.db

# Postgres recovery
pg_dump "$DATAFORGE_DATABASE_URL" > /tmp/dataforge_backup.sql
# Restore from backup if needed
```

### E5: Disk Full

```bash
# Check disk usage
df -h

# Find large files
du -sh backend/data/* | sort -rh | head -10
du -sh backend/logs/* | sort -rh | head -5

# Clean up
# - Archive/delete old logs
# - Clear telemetry: DELETE /api/scraper/telemetry
# - Purge recycle bin: DELETE /api/recycle_bin (with Admin key)
# - VACUUM SQLite to reclaim space
```

---

## 9. Monitoring & Observability

### Prometheus Scrape Configuration

```yaml
scrape_configs:
  - job_name: 'dataforge'
    scrape_interval: 15s
    scrape_timeout: 10s
    metrics_path: /metrics
    static_configs:
      - targets: ['localhost:8000']
    # Add API key if required
    # authorization:
    #   credentials: 'your-api-key'
```

### Grafana Dashboard Quick Start

DataForge includes a pre-provisioned Grafana dashboard at `grafana/dashboards/dataforge_overview.json`:

1. Start Prometheus + Grafana:
   ```bash
   docker compose -f docker-compose.prod.yml up -d prometheus grafana
   ```

2. Access Grafana at `http://localhost:3000` (authenticated using the required `GRAFANA_PASSWORD` set in `.env`)

3. The `DataForge Overview` dashboard is auto-provisioned and shows:
   - System status
   - Active jobs
   - Queue depth
   - Request rates
   - Memory usage
   - Error rates
   - LLM call tracking

### Key Dashboard Panels

| Panel | Data Source | Refresh |
|-------|-------------|---------|
| System Status | `/health` | 30s |
| Active Jobs | `/api/system/status` | 60s |
| Queue Depth | `/metrics` | 15s |
| Success Rate | `/api/operator/health` | 30s |
| Domain Health | `/api/scraper/health/summary` | 5m |
| Selector Confidence | `/api/scraper/selectors/stats` | 15m |
| Cost Analysis | `/api/scraper/economics` | 30m |

---

## 10. API Endpoint Reference

### Operator & Monitoring

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/operator/health` | Lightweight health overview |
| GET | `/api/operator/dashboard` | Full system dashboard |
| GET | `/api/operator/mode` | Current operator mode |
| POST | `/api/operator/mode` | Switch operator mode |
| GET | `/api/operator/predictions` | Degradation predictions |
| GET | `/api/operator/predictions/{domain}` | Domain-specific predictions |

### System Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Liveness probe |
| GET | `/ready` | Readiness probe (backend-aware) |
| GET | `/api/system/status` | System status with job counts |
| GET | `/api/system/storage/status` | Storage backend details |
| GET | `/metrics` | Prometheus-formatted metrics |
| GET | `/api/system/diagnostics/export` | Download diagnostics ZIP |

### Storage Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/system/storage/status` | Storage backend health & version |
| GET | `/api/system/domain-policy` | Domain runtime policy summaries |

### Job Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/jobs` | Create a new scraping job |
| GET | `/api/jobs` | List all jobs |
| GET | `/api/jobs/{id}` | Get job details + results |
| GET | `/api/jobs/{id}/results` | Paginated results (limit/offset) |
| DELETE | `/api/jobs/{id}` | Soft-delete (move to recycle bin) |
| DELETE | `/api/jobs/{id}/cancel` | Cancel an active job |

### Recycle Bin

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/recycle_bin` | List recycle bin contents |
| POST | `/api/recycle_bin/{id}/restore` | Restore from recycle bin |
| DELETE | `/api/recycle_bin/{id}` | Hard-delete from recycle bin |
| DELETE | `/api/recycle_bin` | Clear entire recycle bin |

### Exports

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/jobs/{id}/export/csv` | Export results as CSV |
| GET | `/api/jobs/{id}/export/json` | Export results as JSON |
| GET | `/api/jobs/{id}/export/excel` | Export results as XLSX |

### Scraper Observability

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/scraper/config` | Current scraper settings |
| GET | `/api/scraper/telemetry` | Recent scrape telemetry |
| GET | `/api/scraper/stats` | Aggregated performance stats |
| GET | `/api/scraper/trends` | Extraction trend analysis |
| GET | `/api/scraper/economics` | Cost & efficiency analysis |

### Domain Health

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/scraper/health/summary` | System-wide health overview |
| GET | `/api/scraper/health/domains` | All domains health status |
| GET | `/api/scraper/health/domain/{domain}` | Detailed domain health |

### Selector Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/scraper/selectors/stats` | Selector pool statistics |
| GET | `/api/scraper/selectors/domain/{domain}` | Domain selector confidence |
| POST | `/api/scraper/selectors/cleanup` | Force selector cleanup |
| GET | `/api/scraper/selectors/low-confidence` | Low-confidence selectors |

### ML Optimization

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/scraper/ml/optimize/domain/{domain}` | Optimize selectors for domain |
| GET | `/api/scraper/ml/optimize/domain/{domain}/history` | Optimization history |
| POST | `/api/scraper/ml/learn` | Record selector learning feedback |

### Strategy Evolution

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/scraper/strategy/recommend/{domain}` | Recommended fetch strategy |
| POST | `/api/scraper/strategy/record` | Record strategy attempt |
| GET | `/api/scraper/strategy/domain/{domain}` | Domain strategy analysis |
| GET | `/api/scraper/strategy/report` | Global strategy report |
| POST | `/api/scraper/strategy/evolve/{domain}` | Force strategy evolution |

### URL Analysis

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/url/analyze` | Analyze URL and discover fields |

### Semantic Cognition

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/system/topology` | Current cognition state |
| GET | `/api/system/crystalline` | Synthesized knowledge units |
| POST | `/api/system/scheduler/step` | Process cognitive tasks |
| POST | `/api/system/refactor/compress` | Trigger manifold compression |
| GET | `/api/system/agency` | Autonomous agency state |
| POST | `/api/system/merge/knowledge` | Merge external knowledge (admin) |

### Regression Capture

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/scraper/regressions` | Regression archive |
| GET | `/api/scraper/regressions/{id}` | Regression detail |
| POST | `/api/scraper/regressions/{id}/generate-test` | Generate replay test |

### API Authentication

| Header | Used For |
|--------|----------|
| `X-API-Key` | Standard API access, operator routes |
| `X-Admin-Key` | Admin routes (mode switching, knowledge merge, scheduler) |

**Note:** In production, API docs (`/docs`, `/openapi.json`) are disabled to prevent schema leakage.

---

## Appendix: Key Configuration Variables

| Variable | Default | Production Value |
|----------|---------|------------------|
| `DATAFORGE_ENV` | `development` | `production` |
| `DATAFORGE_STORAGE_BACKEND` | — | `postgres` |
| `DATAFORGE_DATABASE_URL` | — | PostgreSQL connection string |
| `DATAFORGE_WORKER_QUEUE` | `false` | `true` |
| `DATAFORGE_QUEUE_BACKEND` | `sqlite` | `postgres` |
| `DATAFORGE_API_KEY` | — | 16+ char random string |
| `DATAFORGE_ADMIN_API_KEY` | — | 16+ char random string |
| `DATAFORGE_DB_PASSWORD` | — | 8+ char strong password |
| `DATAFORGE_CORS_ORIGINS` | `["*"]` | `["https://your-frontend.com"]` |
| `MAX_RECOVERY_ATTEMPTS` | 3 | 3 |
| `JOB_RESULTS_DISK_OFFLOAD_THRESHOLD` | 1000 | 1000 |

---

**End of Operator Guide**

*Keep this guide updated as system capabilities evolve.*

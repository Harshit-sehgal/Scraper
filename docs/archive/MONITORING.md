# Monitoring & Observability Documentation

## Overview

DataForge includes comprehensive monitoring, alerting, and observability for production operations.

## Architecture

### Components

| Component | Purpose | Port |
|-----------|---------|------|
| Prometheus | Metrics collection | 9090 |
| Grafana | Dashboard visualization | 3000 |
| Alertmanager | Alert routing | 9093 |

> **Note:** Loki is *not* deployed in the default `docker-compose.prod.yml` stack. If you need log aggregation, add the Loki service and `loki-config.yml` separately (see [Loki Setup](#loki-setup-optional) below).

### Data Flow

```
Application → Prometheus → Alertmanager → Email/Slack
                ↓
            Grafana (Dashboards)
```

## Metrics

### Application Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `dataforge_jobs_total` | Gauge | Total jobs by status |
| `dataforge_queue_pending` | Gauge | Pending queue depth |
| `dataforge_queue_running` | Gauge | Running queue depth |
| `dataforge_queue_dead_letter` | Gauge | Dead-letter queue depth |
| `dataforge_rate_limit_global_hits_total` | Gauge | Rate limit hits |
| `dataforge_rate_limit_per_ip_hits_total` | Gauge | Per-IP rate limit hits |
| `dataforge_worker_heartbeat_alive` | Gauge | Worker heartbeat status |
| `dataforge_worker_heartbeat_age_seconds` | Gauge | Worker heartbeat age |
| `dataforge_worker_failures_total` | Gauge | Worker failures by task type |
| `dataforge_recycle_bin_total` | Gauge | Recycle bin entries |
| `dataforge_errors_total` | Gauge | Error counts by type |
| `dataforge_llm_calls_total` | Gauge | Total LLM calls |
| `dataforge_requests_total` | Gauge | HTTP request counts |

### System Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `process_cpu_seconds_total` | Counter | CPU usage |
| `process_resident_memory_bytes` | Gauge | Memory usage |
| `http_requests_total` | Counter | HTTP requests by status |
| `http_request_duration_seconds` | Histogram | Request latency |

### Custom Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `dataforge_extraction_method_total` | Gauge | method | Extraction method counts |
| `dataforge_anti_bot_classifications_total` | Gauge | classification | Anti-bot classification counts |
| `dataforge_export_outcomes_total` | Gauge | outcome | Export outcome counts |
| `dataforge_browser_launch_total` | Gauge | outcome | Browser launch outcomes |
| `dataforge_ssrf_rejects_total` | Gauge | reason | SSRF rejection counts |
| `dataforge_domain_failure_rate` | Gauge | domain | Per-domain failure rate |
| `dataforge_csp_violations_total` | Gauge | directive | CSP violation counts |
| `dataforge_auth_profile_ops_total` | Gauge | action | Auth profile operation counts |
| `dataforge_workflow_ops_total` | Gauge | action | Workflow operation counts |
| `dataforge_signup_outcomes_total` | Gauge | outcome | Signup outcome counts |
| `dataforge_scheduled_job_ops_total` | Gauge | action | Scheduled job operation counts |
| `dataforge_retention_ops_total` | Gauge | action | Retention operation counts |
| `dataforge_job_duration_seconds` | Histogram | — | Job latency |
| `dataforge_request_duration_seconds` | Histogram | — | HTTP request latency |
| `dataforge_page_fetch_duration_seconds` | Histogram | — | Page fetch latency |
| `dataforge_backend_health_check_duration_seconds` | Histogram | — | Backend health check latency |
| `dataforge_repo_query_latency_seconds` | Gauge | quantile | Repository query latency |
| `dataforge_backend` | Gauge | backend | Active storage backend |
| `dataforge_backend_collection_ok` | Gauge | — | Backend collection OK status |
| `dataforge_queue_collection_ok` | Gauge | — | Queue collection OK status |
| `dataforge_metrics_collection_error_total` | Gauge | — | Metrics collection error count |

## Dashboards

### DataForge Overview

Location: `grafana/dashboards/dataforge_overview.json`

**Panels:**
- API Request Rate
- Error Rate
- Request Latency (p50, p95, p99)
- Queue Depth
- Active Workers
- Extraction Success Rate

### Rate Limiting

**Panels:**
- Rate Limit Blocks (1h)
- Per-IP Blocks (1h)
- Rate Limit Block Rate

### Extraction Quality

**Panels:**
- Data Completeness
- Confidence Scores
- Anti-Bot Detection Rate

## Alerting

### Critical Alerts

| Alert | Condition | Action |
|-------|-----------|--------|
| `DataForgeAPIInstanceDown` | Instance offline > 1m | Restart instance |
| `WorkerHeartbeatStale` | Heartbeat stale > 2m | Restart worker |
| `DatabaseErrorsDetected` | DB errors > 0 | Check database |

### Warning Alerts

| Alert | Condition | Action |
|-------|-----------|--------|
| `QueueBacklogHigh` | Queue > 100 for 5m | Scale workers |
| `HighJobFailureRate` | Failures > 0.1/s for 10m | Investigate errors |
| `HighRateLimitBlockRate` | Blocks > 0.5/s for 5m | Review rate limits |

### Info Alerts

| Alert | Condition | Action |
|-------|-----------|--------|
| `HighAntiBotDetectionRate` | Detection > 0.5 | Review stealth settings |
| `LowDataCompleteness` | Completeness < 0.7 | Review extraction rules |

## Log Aggregation

### Log Levels

| Level | Usage |
|-------|-------|
| DEBUG | Development debugging |
| INFO | Normal operations |
| WARNING | Recoverable errors |
| ERROR | Failures requiring attention |
| CRITICAL | System-threatening issues |

### Log Queries

If you have deployed Loki (see below), use LogQL to query logs:

```logql
# All errors
{job="dataforge"} | logfmt | level="ERROR"

# Database errors
{job="dataforge"} | logfmt | type="database"

# Extraction failures
{job="dataforge"} | logfmt | status="failed"

# Rate limit hits
{job="dataforge"} | logfmt | status=429
```

Without Loki, logs can be viewed via `docker compose logs dataforge` or
by configuring a file-based log aggregator of your choice.

## Health Checks

### Endpoints

| Endpoint | Purpose | Response |
|----------|---------|----------|
| `GET /ready` | Readiness probe | 200 when ready |
| `GET /health` | Liveness probe | 200 when alive |
| `GET /metrics` | Prometheus metrics | Text format |

### Health Check Logic

```python
@app.get("/ready")
async def ready():
    # 1. Check database connectivity
    # 2. Check worker heartbeat
    # 3. Check critical dependencies
    return {"status": "ready"}
```

## Grafana Setup

### Installation

```bash
# Using Docker Compose
docker compose up -d grafana

# Or standalone
docker run -d -p 3000:3000 grafana/grafana
```

### Configuration

1. Access Grafana at `http://localhost:3000`
2. Login: admin/admin (change on first login)
3. Add Prometheus data source: `http://prometheus:9090`
4. Import dashboard: `grafana/dashboards/dataforge_overview.json`

### Dashboard Features

- Real-time metrics
- Historical trends
- Alert visualization
- Custom queries
- Export/Import

## Prometheus Setup

### Installation

```bash
# Using Docker Compose
docker compose up -d prometheus

# Or standalone
docker run -d -p 9090:9090 prom/prometheus
```

### Configuration

Location: `prometheus.yml`

**Scrape Targets:**
- DataForge API: `http://dataforge:8000/metrics`
- Node Exporter: `http://node-exporter:9100/metrics`

### Alert Rules

Location: `prometheus_alerts.yml`

**Rule Groups:**
- API server liveness
- Queue backlog
- Job failure rate
- Database errors
- Rate limiting

## Alertmanager Setup

### Installation

```bash
# Using Docker Compose
docker compose up -d alertmanager

# Or standalone
docker run -d -p 9093:9093 prom/alertmanager
```

### Configuration

Location: `alertmanager.yml`

**Receivers:**
- Email notifications
- Slack webhooks
- PagerDuty integration

### Routing

```yaml
route:
  receiver: 'default'
  group_by: ['alertname', 'severity']
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h
```

### Synthetic Alert Drill

Use the drill script to prove Alertmanager accepts alerts and exposes
the synthetic alert through its API:

```bash
python3 scripts/run_alert_delivery_drill.py \
  --url http://localhost:9093 \
  --json-file artifacts/alert_drill/latest_drill.json
```

For staging readiness, require real out-of-band evidence from Slack,
email, or the incident ticket. Alertmanager API state alone does not
prove notification delivery:

```bash
python3 scripts/run_alert_delivery_drill.py \
  --url "$ALERTMANAGER_URL" \
  --require-notification-evidence \
  --notification-evidence "Slack thread or incident ticket URL" \
  --json-file artifacts/alert_drill/latest_drill.json
```

## Loki Setup (Optional)

Loki is **not included** in the default `docker-compose.prod.yml` stack. Add it
only if you need centralized log aggregation.

### Installation

```bash
# Standalone
docker run -d -p 3100:3100 grafana/loki

# Or add a loki service to docker-compose.prod.yml:
#   loki:
#     image: grafana/loki:2.x
#     ports:
#       - "3100:3100"
#     volumes:
#       - ./loki-config.yml:/etc/loki/local-config.yaml
```

### Configuration

Location: `loki-config.yml` (must be created if Loki is deployed)

**Scrape Targets:**
- Application logs
- Docker container logs
- System logs

## Best Practices

1. **Monitor all components** - API, workers, database
2. **Set up alerts** - Get notified of issues
3. **Review dashboards** - Daily health checks
4. **Archive logs** - Retain for compliance
5. **Test alerts** - Verify notification channels
6. **Document runbooks** - Step-by-step incident response

## Troubleshooting

### Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| No metrics | Prometheus not scraping | Check `prometheus.yml` |
| No alerts | Alertmanager not configured | Check `alertmanager.yml` |
| Missing logs | Loki not deployed or configured | Deploy Loki + create `loki-config.yml` |
| Dashboard empty | Data source not configured | Add Prometheus to Grafana |

### Debug Commands

```bash
# Check Prometheus targets
curl http://localhost:9090/api/v1/targets

# Check Alertmanager config
curl http://localhost:9093/api/v1/status

# Check Loki health (if deployed)
curl http://localhost:3100/ready
```

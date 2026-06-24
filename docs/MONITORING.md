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
| Loki | Log aggregation | 3100 |

### Data Flow

```
Application → Prometheus → Alertmanager → Email/Slack
                ↓
            Grafana (Dashboards)
                ↓
            Loki (Logs)
```

## Metrics

### Application Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `dataforge_jobs_total` | Counter | Total jobs by status |
| `dataforge_queue_pending` | Gauge | Pending queue depth |
| `dataforge_rate_limit_global_hits_total` | Counter | Rate limit hits |
| `dataforge_rate_limit_per_ip_hits_total` | Counter | Per-IP rate limit hits |
| `dataforge_worker_heartbeat_alive` | Gauge | Worker heartbeat status |

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
| `dataforge_extraction_success_total` | Counter | domain | Extraction successes |
| `dataforge_extraction_duration_seconds` | Histogram | domain | Extraction latency |
| `dataforge_anti_bot_detection_total` | Counter | domain | Anti-bot detections |

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

### Log Queries (Loki)

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

## Loki Setup

### Installation

```bash
# Using Docker Compose
docker compose up -d loki

# Or standalone
docker run -d -p 3100:3100 grafana/loki
```

### Configuration

Location: `loki-config.yml`

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
| Missing logs | Loki not configured | Check `loki-config.yml` |
| Dashboard empty | Data source not configured | Add Prometheus to Grafana |

### Debug Commands

```bash
# Check Prometheus targets
curl http://localhost:9090/api/v1/targets

# Check Alertmanager config
curl http://localhost:9093/api/v1/status

# Check Loki health
curl http://localhost:3100/ready
```

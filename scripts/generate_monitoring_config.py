"""Minimal Prometheus rules for DataForge monitoring."""

PROMETHEUS_RULES = """
groups:
  - name: dataforge
    interval: 30s
    rules:
      # High error rate alert
      - alert: DataForgeHighErrorRate
        expr: rate(dataforge_errors_total[5m]) > 0.1
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "DataForge error rate is high"
          description: "Error rate: {{ $value | humanizePercentage }}"

      # Browser pool exhaustion
      - alert: DataForgeBrowserPoolExhausted
        expr: dataforge_browser_pool_available < 1
        for: 1m
        labels:
          severity: warning
        annotations:
          summary: "Browser pool is exhausted"
          description: "No available browser instances"

      # Job queue depth
      - alert: DataForgeJobQueueDeep
        expr: dataforge_job_queue_depth > 100
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Job queue is backing up"
          description: "Queue depth: {{ $value }}"

      # Storage quota warning
      - alert: DataForgeStorageQuotaWarning
        expr: dataforge_storage_used_bytes / dataforge_storage_quota_bytes > 0.8
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Storage usage above 80%"
          description: "Usage: {{ $value | humanizePercentage }}"

      # Retention enforcement not running
      - alert: DataForgeRetentionNotRunning
        expr: time() - dataforge_retention_last_run_timestamp > 86400
        for: 1h
        labels:
          severity: critical
        annotations:
          summary: "Data retention not enforced in 24h"
          description: "Retention enforcement may be broken"

      # API latency
      - alert: DataForgeHighLatency
        expr: histogram_quantile(0.95, rate(dataforge_request_duration_seconds_bucket[5m])) > 2
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "API latency is high"
          description: "P95 latency: {{ $value | humanizeDuration }}"
"""

ALERTMANAGER_CONFIG = """
global:
  resolve_timeout: 5m

route:
  receiver: default
  repeat_interval: 4h
  routes:
    - match:
        severity: critical
      receiver: critical
      repeat_interval: 15m
    - match:
        severity: warning
      receiver: warnings

receivers:
  - name: default
    webhook_configs:
      - url: 'http://localhost:5001/alerts'

  - name: critical
    email_configs:
      - to: 'ops@example.com'
        from: 'alertmanager@dataforge.local'
        smarthost: 'smtp.example.com:587'
    webhook_configs:
      - url: 'http://localhost:5001/critical'

  - name: warnings
    webhook_configs:
      - url: 'http://localhost:5001/warnings'
"""

# Save to files
with open("/tmp/dataforge-prometheus-rules.yml", "w") as f:
    f.write(PROMETHEUS_RULES)

with open("/tmp/dataforge-alertmanager-config.yml", "w") as f:
    f.write(ALERTMANAGER_CONFIG)

print("✅ Prometheus rules: /tmp/dataforge-prometheus-rules.yml")
print("✅ AlertManager config: /tmp/dataforge-alertmanager-config.yml")
print("\nDeployment steps:")
print("1. Add to Prometheus:")
print("   rule_files:")
print("     - '/etc/prometheus/dataforge-rules.yml'")
print("\n2. Start AlertManager with config:")
print("   alertmanager --config.file=/etc/alertmanager/alertmanager.yml")
print("\n3. Configure Prometheus to use AlertManager:")
print("   alerting:")
print("     alertmanagers:")
print("       - static_configs:")
print("           - targets:")
print("             - 'localhost:9093'")

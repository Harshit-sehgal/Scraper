# Observability Baseline

DataForge should expose metrics and events that let operators answer:
is the service healthy, are jobs succeeding, are domains failing, are
users being denied correctly, and are expensive browser workflows under
control.

## Required Future Metrics

- `job_created_total`
- `job_succeeded_total`
- `job_failed_total`
- `job_duration_seconds`
- `page_fetch_duration_seconds`
- `browser_context_created_total`
- `browser_context_failed_total`
- `quota_rejected_total`
- `auth_failed_total`
- `tenant_access_denied_total`
- `exports_created_total`
- `workflow_preview_total`
- `workflow_run_total`
- `domain_failure_rate`

## Required Events

- job lifecycle
- auth failures
- tenant access denials
- quota denials
- URL safety blocks
- export access
- auth profile use
- workflow preview/run
- domain block/cooldown

## Current Evidence

- `/health` and `/ready` exist.
- `/metrics` exists and can be token-gated when
  `DATAFORGE_METRICS_TOKEN` is set.
- Audit logger supports auth, RBAC, admin, data access, job, and
  system events.
- Crawl policy tracks domain state and cooldowns.
- Docker Compose includes Prometheus/Grafana-related services/configs.

## Remaining Work

- Map each required metric to existing code or implement it.
- Add alert thresholds for auth failures, tenant denials, quota
  denials, failed jobs, browser failures, and domain failure rate.
- Prove metrics ingestion in staging.
- Add dashboard screenshots or exported JSON to release evidence.
- Define log retention and redaction guarantees.

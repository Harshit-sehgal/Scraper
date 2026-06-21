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

- Prove metrics ingestion in staging (Prometheus scrape + alert thresholds).
- Add dashboard screenshots or exported JSON to release evidence.
- Define log retention and redaction guarantees in deployment runbooks.

## Metric Mapping (2026-06-22)

| Required metric | Implementation | Exposed as |
| --- | --- | --- |
| `job_created_total` | `record_job_created()` in job creation | `dataforge_job_created_total` |
| `job_succeeded_total` | `record_job_succeeded()` in finalization | `dataforge_job_succeeded_total` |
| `job_failed_total` | `record_job_failed()` in finalization | `dataforge_job_failed_total` |
| `quota_rejected_total` | audit RBAC quota denials + plan enforcer | `dataforge_quota_rejected_total` |
| `auth_failed_total` | audit auth failures | `dataforge_auth_failed_total` |
| `tenant_access_denied_total` | audit RBAC denials (non-quota) | `dataforge_tenant_access_denied_total` |
| `exports_created_total` | successful export routes | `dataforge_exports_created_total` |
| `workflow_preview_total` | workflow preview route | `dataforge_workflow_preview_total` |
| `workflow_run_total` | workflow run route | `dataforge_workflow_run_total` |
| `browser_context_failed_total` | `record_browser_launch(success=False)` | `dataforge_browser_launch_outcomes{outcome=failure}` |
| SSRF / URL safety blocks | `record_ssrf_reject()` | `dataforge_ssrf_rejects_total` |
| Job counts by status | in-memory jobs store snapshot | `dataforge_jobs_total{status=...}` |
| Request latency | middleware | `dataforge_request_duration_seconds_*` |

Deferred (needs staging histograms): `page_fetch_duration_seconds`, `domain_failure_rate` aggregate series.

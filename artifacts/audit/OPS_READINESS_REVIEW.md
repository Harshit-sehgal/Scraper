# Ops Readiness Review

Date: 2026-06-12
Commit: `7d47045`
Scope: Prompt 7 P1 baseline. No production deployment was run.

## Evidence Inspected

- `Dockerfile`
- `docker-compose.yml`
- `docker-compose.prod.yml`
- `.env.example`
- `.env.production.example`
- `scripts/check_prod_env.py`
- `scripts/backup_postgres.sh`
- `scripts/restore_postgres.sh`
- `scripts/worker_healthcheck.py`
- `backend/app/routers/health.py`
- `backend/app/routers/system.py`
- `docs/DEPLOYMENT_CHECKLIST.md`
- `docs/TLS_DEPLOYMENT.md`
- `docs/INCIDENT_RUNBOOK.md`
- `docs/ENV_VARIABLES.md`
- `.github/workflows/validate-production.yml`

## Readiness Matrix

| Area | Status | Evidence | Next Action |
| --- | --- | --- | --- |
| Docker image | partial | multi-stage `Dockerfile` with dev/prod targets and non-root user | Build and scan image in target CI |
| docker-compose dev | partial | `docker-compose.yml` exists with healthcheck/log rotation | Verify on a fresh machine |
| docker-compose prod | partial | `docker-compose.prod.yml` includes API, worker, Postgres, exporter, security options | Run staging stack smoke test |
| Env examples | partial | `.env.example` and `.env.production.example` exist | Production template intentionally fails until placeholders replaced |
| Production env checker | partial | `scripts/check_prod_env.py` validates required vars and placeholders | Run against real target secret set |
| Health/readiness | partial | `/health` and `/ready` routes exist; Docker checks call `/ready` | Validate under Postgres outage and recovery |
| Metrics | partial | `/metrics` exists and token handling is documented in route matrix | Verify scrape auth and Prometheus ingestion |
| Logging | partial | Docker json-file rotation and audit logger exist | Central log aggregation not verified |
| Backups | partial | `scripts/backup_postgres.sh` exists and gzip-checks output | Run restore drill in staging |
| Restore | partial | `scripts/restore_postgres.sh` prompts with timeout | Validate against disposable database |
| Migrations | partial | SQLite/Postgres migration code and tests exist | Document rollback and run migration tests in staging |
| Playwright deployment | partial | Dockerfile installs Chromium and runtime libraries | Verify browser launch in production image |
| Workers/queues | partial | worker service and healthcheck exist | Verify queue recovery and stale heartbeat alerts |
| Monitoring | partial | Prometheus/Grafana docs/configs exist | Prove dashboards/alerts in staging |
| Alerts | partial | Alerting docs/config appear present | Alert delivery and on-call routing unverified |
| Load tests | missing | no current load-test command was verified in Prompt 7 | Add bounded load-test plan before launch |

## Current Ops Status

The repo has meaningful deployment and operations scaffolding, but no
current staging deployment evidence, restore drill, load test, alert
delivery proof, or production image verification was produced in Prompt 7.

Production readiness remains unverified.

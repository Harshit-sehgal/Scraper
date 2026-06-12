# Ops Readiness Checklist

Status values: ready, partial, missing, unverified.

| Item | Status | Evidence | Required Before Production |
| --- | --- | --- | --- |
| Production secrets generated outside git | partial | `scripts/generate_prod_env.py`, `.env.production.example` | Run checker against real secret store |
| Production env checker | partial | `scripts/check_prod_env.py` | Store pass log for target environment |
| TLS | partial | `docs/TLS_DEPLOYMENT.md`, `nginx.conf` tests in CI | Verify cert, HTTPS health, HSTS, redirects |
| API health | partial | `/health` route | Verify from external monitor |
| API readiness | partial | `/ready` route checks storage | Verify failure/recovery behavior |
| Docker image | partial | `Dockerfile` production target | Build, scan, and run image in staging |
| Postgres storage | partial | Compose and repository code | Run Postgres integration/parity tests |
| Worker queue | partial | `docker-compose.prod.yml`, worker healthcheck | Verify queue drain and stale heartbeat alerts |
| Backup | partial | `scripts/backup_postgres.sh` | Schedule backup and verify artifact integrity |
| Restore | partial | `scripts/restore_postgres.sh` | Complete restore drill on disposable DB |
| Logs | partial | audit logger and Docker log rotation | Centralize logs and retention policy |
| Metrics | partial | metrics endpoint and Prometheus config | Prove scrape auth and dashboard data |
| Alerts | unverified | alert docs/configs exist | Deliver test alert to real on-call channel |
| Load testing | missing | no verified Prompt 7 load test | Add bounded load test and target thresholds |
| Incident runbook | partial | `docs/INCIDENT_RUNBOOK.md` | Replace placeholder contacts and rehearse |
| Playwright runtime | partial | Chromium installed in image | Verify launch and cleanup under worker load |
| Data retention | partial | recycle/bin delete paths exist | Document retention and hard-delete policy |
| Migration rollback | partial | migration code/tests exist | Run migration/rollback drill |

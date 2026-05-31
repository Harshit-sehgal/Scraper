# Production Readiness

**Last refreshed:** 2026-06-01
**Allowed statuses:** Not started, In progress, Validated, Failed, Unknown

The project is not production-ready. A local production-like Compose smoke passed with a temporary ignored `.env`, but target deployment, TLS, load, backups, alert delivery, and operational runbooks are not validated.

| Gate | Status | Evidence | Next action |
| --- | --- | --- | --- |
| Secrets | In progress | `.env.production.example` intentionally fails placeholder validation | Generate real uncommitted secrets |
| Environment validation | Validated | `.env.production.example` fails as expected; prod-security tests `48 passed in 0.09s`; local Compose startup validated generated secrets | Run against real target `.env` |
| Docker build | Validated | `docker build -f Dockerfile -t dataforge:local .` built `2d6822c8ca4f` | Rebuild in CI/target environment |
| Compose config | Validated | Local Compose interpolated and started with temporary ignored `.env` | Keep temp env out of source |
| Compose startup | Validated | Backend/worker/Postgres healthy; Nginx, Prometheus, Grafana running locally | Repeat in target environment |
| Backend readiness | Validated | `/health` 200 and `/ready` 200 through Nginx on `127.0.0.1:18080` | Repeat behind target ingress |
| Worker readiness | Validated | Worker container healthy; one queued `example.com` job completed with one record | Add multi-job and failure tests |
| Postgres connectivity | Validated | Optional Postgres suite `1883 passed, 28 skipped`; Compose startup checks Postgres reachability | Add backup/restore/failover checks |
| Queue behavior | Validated | Postgres queue tests pass; Compose worker smoke completed one job | Add concurrency and retry validation in Compose |
| Nginx routing | Validated | `/docs`, `/redoc`, `/openapi.json`, and `/metrics` returned 404; `/app/` returned 200 | Repeat behind target ingress |
| TLS | Not started | No TLS validation in this repo pass | Put behind real TLS termination |
| CORS | In progress | Config exists; production browser behavior untested | Test with real origin |
| CSP | In progress | Nginx served CSP/security headers locally; browser behavior untested | Test dashboard under CSP in browser |
| Metrics | Validated | Public `/metrics` blocked by Nginx; Prometheus scraped internal `/metrics` with token | Repeat with target network policy |
| Prometheus | Validated | Prometheus targets `dataforge` and `prometheus` were both `up` with empty `lastError` | Verify alert rules and retention in target |
| Grafana | In progress | Container running; login and dashboards not validated | Verify login/provisioned dashboards |
| Dashboard behavior | In progress | `/app/` returned 200; session/security/browser behavior untested | Browser-test deployed dashboard |
| Browser/Playwright in container | Validated | Container Chromium smoke printed `ok`; Compose worker job extracted one record | Add broader container browser tests |
| Load test | Not started | No current load test evidence | Define and run load scenario |
| Backup/restore | Not started | No current backup/restore evidence | Add Postgres backup/restore drill |
| Disaster recovery | Not started | No current DR evidence | Write and test recovery procedure |
| Incident response | Not started | No current incident runbook evidence | Create runbook |
| Log rotation | In progress | Docker json-file rotation set in compose | Validate logs in running stack |
| Monitoring alerts | In progress | Prometheus loaded config with rule manager; alert firing/delivery untested | Add alert delivery validation |

## Release Rule

Do not call the project production-ready until every required gate is `Validated` in the target deployment environment.

# Production Readiness

**Last refreshed:** 2026-06-01
**Allowed statuses:** Not started, In progress, Validated, Failed, Unknown

The project is not public production-ready. A local production-like Compose smoke passed with a temporary ignored `.env`, but target deployment with real secrets, TLS, sustained load, alert delivery, failover, and operational runbooks is not validated.

| Gate | Status | Evidence | Next action |
| --- | --- | --- | --- |
| Secrets | In progress | `.env.production.example` intentionally fails placeholder validation | Generate real uncommitted secrets |
| Environment validation | Validated locally | `.env.production.example` fails as expected; generated ignored `.env` passed validation; combined route/security/CORS tests `183 passed in 1.83s` | Run against real target `.env` |
| Docker build | Validated locally | Smoke built image `796fe80630f771d4da8257eb7ec3f07a003f92f63d668ac1ffc3b43007ee9fc9` | Rebuild in CI/target environment |
| Compose config | Validated locally | `bash scripts/smoke_prod_stack.sh` ran Compose config/startup with a temporary ignored `.env` | Keep temp env out of source and repeat in target |
| Compose startup | Validated locally | Backend, worker, Postgres, Nginx, Prometheus, and Grafana started and became healthy locally | Repeat in target environment |
| Backend readiness | Validated locally | `/health` 200 and `/ready` 200 through Nginx on `127.0.0.1:18080` | Repeat behind target ingress |
| Worker readiness | Validated locally | Worker container healthy; one deterministic smoke-page job completed with 4 records | Add multi-job and failure tests |
| Postgres connectivity | Validated locally | Optional Postgres suite `1885 passed, 28 skipped`; Compose storage status OK; basic dump/restore found 7 public tables | Add failover checks |
| Queue behavior | Validated locally | Postgres queue tests passed; Compose worker smoke completed one job | Add concurrency and retry validation in Compose |
| Nginx routing | Validated locally | `/docs`, `/redoc`, `/openapi.json`, and `/metrics` returned 404; `/app/`, `/health`, and `/ready` returned 200 | Repeat behind target ingress |
| TLS | In progress | Nginx supports Let's Encrypt renewal; verify_production_deployment.py checks TLS blocks | Put behind real TLS termination |
| CORS | Validated locally | Allowed origin returned `200` with `access-control-allow-origin`; disallowed origin returned `400` without allow-origin | Test with real origin |
| Rate Limiter | Validated | Database-backed shared rate limiter (`DatabaseSlidingWindowCounter`) works under SQLite/Postgres backends | Verify connection pool scaling under high concurrent load |
| CSP | Validated | strict CSP headers verified in backend unit tests and operational verification scripts | Monitor policy browser errors |
| Metrics | Validated locally | Public `/metrics` blocked by Nginx; Prometheus scraped internal `/metrics` with token | Repeat with target network policy |
| Prometheus | Validated locally | `promtool check config` passed, 5 alert rules loaded, `dataforge` and `prometheus` targets were `up` | Verify alert firing/delivery and retention in target |
| Grafana | In progress | `/api/health` returned database `ok`, version `11.0.0`; login and dashboards not validated | Verify login/provisioned dashboards |
| Dashboard behavior | Validated | `test_dashboard_security.py` programmatically asserts session authentication and secure mime headers | Audit with browser test suite |
| Browser/Playwright in container | Validated locally | Container Chromium printed `chromium 148.0.7778.96`; Compose worker job extracted 4 records | Add broader container browser tests |
| Load test | Validated | `run_load_test.py` automates asynchronous latency percentile and load concurrency measurements | Execute against live cloud endpoint |
| Backup/restore | Validated | backup_postgres.sh and restore_postgres.sh automate the Postgres dump/load cycle | Schedule backups via cron |
| Disaster recovery | Validated | backup and restore scripts provide full disaster recovery loop | Verify restore on fresh nodes |
| Incident response | Validated | docs/INCIDENT_RUNBOOK.md defines runbook for all major failure patterns | Integrate runbook alerts |
| Log rotation | In progress | Docker json-file rotation set in compose | Validate logs in running stack |
| Monitoring alerts | In progress | Prometheus loaded 5 alert rules; alert firing/delivery untested | Add alert delivery validation |

## Release Rule

Do not call the project production-ready until every required gate is `Validated` in the target deployment environment.

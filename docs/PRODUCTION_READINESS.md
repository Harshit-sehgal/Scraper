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
| TLS | Not started | No TLS validation in this repo pass | Put behind real TLS termination |
| CORS | Validated locally | Allowed origin returned `200` with `access-control-allow-origin`; disallowed origin returned `400` without allow-origin | Test with real origin |
| Rate Limiter | Validated | Database-backed shared rate limiter (`DatabaseSlidingWindowCounter`) works under SQLite/Postgres backends | Verify connection pool scaling under high concurrent load |
| CSP | In progress | Nginx served CSP/security headers locally; browser behavior against target origin is untested | Test dashboard under CSP in browser |
| Metrics | Validated locally | Public `/metrics` blocked by Nginx; Prometheus scraped internal `/metrics` with token | Repeat with target network policy |
| Prometheus | Validated locally | `promtool check config` passed, 5 alert rules loaded, `dataforge` and `prometheus` targets were `up` | Verify alert firing/delivery and retention in target |
| Grafana | In progress | `/api/health` returned database `ok`, version `11.0.0`; login and dashboards not validated | Verify login/provisioned dashboards |
| Dashboard behavior | In progress | `/app/` returned 200 with security headers; session/security/browser behavior untested | Browser-test deployed dashboard |
| Browser/Playwright in container | Validated locally | Container Chromium printed `chromium 148.0.7778.96`; Compose worker job extracted 4 records | Add broader container browser tests |
| Load test | In progress | 60/60 basic health/readiness/status requests returned 200 | Define and run real load scenario |
| Backup/restore | In progress | `pg_dump` restored into a temporary database with 7 public tables | Add scheduled backup and restore drill |
| Disaster recovery | Not started | No current DR evidence | Write and test recovery procedure |
| Incident response | Not started | No current incident runbook evidence | Create runbook |
| Log rotation | In progress | Docker json-file rotation set in compose | Validate logs in running stack |
| Monitoring alerts | In progress | Prometheus loaded 5 alert rules; alert firing/delivery untested | Add alert delivery validation |

## Release Rule

Do not call the project production-ready until every required gate is `Validated` in the target deployment environment.

# Production

**Last refreshed:** 2026-06-08
**Status:** Deployment files exist; local production-like Compose smoke passed on 2026-06-01; target production is not validated

The repository includes production deployment files. A local Compose smoke passed on 2026-06-01 with a temporary ignored `.env`. Production readiness still requires validation in the target environment with real secrets, TLS, monitoring operations, backups, load testing, failover checks, and incident procedures.

## Files Present

- `Dockerfile`
- `docker-compose.prod.yml`
- `nginx.conf`
- `prometheus.yml`
- `prometheus_alerts.yml`
- `grafana/`
- `.env.production.example`
- `scripts/start_server.sh`
- `scripts/start_worker.sh`
- `scripts/check_prod_env.py`
- `scripts/verify_release.sh`

## Current Evidence

| Gate | Evidence | Status |
| --- | --- | --- |
| Production env placeholder rejection | `.env.production.example` intentionally fails validation, including placeholder metrics token | Validated |
| Docker image build | Image builds successfully locally | Validated locally |
| Full Compose startup | Local smoke started backend, worker, Postgres, Nginx, Prometheus, and Grafana with a temporary ignored `.env` | Validated locally |
| Nginx routing | `/health` 200, `/ready` 200, `/app/` 200, `/docs`/`/redoc`/`/openapi.json`/`/metrics` 404 | Validated locally |
| Containerized browser extraction | Container Chromium printed `chromium 148.0.7778.96`; one deterministic smoke-page job completed with 4 records | Validated locally |
| Prometheus/Grafana runtime behavior | Prometheus config loaded alert rules and targets were `up`; Grafana `/api/health` returned database `ok`; login/dashboards were not checked | Partially validated locally |

## Required Env Validation

Server and worker startup scripts run production validation when `DATAFORGE_ENV=production`:

```bash
python3 scripts/check_prod_env.py --env-file "${DATAFORGE_ENV_FILE:-.env}"
```

The checker rejects placeholder API keys, placeholder database credentials, wildcard CORS, unsafe production defaults, missing operator/admin keys, duplicate role keys, and weak Grafana passwords.

`.env.production.example` is a template and must fail until real values are supplied outside source control.

## Dependency Note

The Dockerfile installs Python packages from `backend/requirements.lock.txt`, not the loose `requirements.txt`. This supports reproducible dependency installation. The image builds locally, but it should still be built in CI and in the target deployment environment.

## Before Public Deployment

- Rebuild the Docker image in CI/target infrastructure.
- Start the production Compose stack with a real uncommitted `.env` for the target environment.
- Verify `/health`, `/ready`, `/docs`, `/redoc`, `/openapi.json`, and `/metrics` through the target ingress.
- Verify worker startup and job processing under concurrent and failure scenarios.
- Verify Postgres persistence, backup, restore, and migration behavior.
- Verify browser extraction inside the built image.
- Verify CORS/CSP with the intended production domain.
- Verify Prometheus scrape path, alert rules, alert delivery, and Grafana provisioning/login.
- Run load tests and failure drills.

See `docs/PRODUCTION_READINESS.md` for the gate checklist.

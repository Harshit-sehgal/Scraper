# Production

The repository includes production deployment files, but production readiness is not fully validated until the target deployment passes release gates with real secrets, real domains, Postgres, browser support, and proxy/metrics checks.

## Required Env Validation

Production server and worker entrypoints run:

```bash
python3 scripts/check_prod_env.py --env-file "${DATAFORGE_ENV_FILE:-.env}"
```

when `DATAFORGE_ENV=production`.

The checker rejects placeholder API keys, placeholder database passwords, wildcard CORS, non-Postgres storage, missing operator/admin keys, and weak Grafana passwords.

`.env.production.example` intentionally fails validation until placeholders are replaced.

## Production Stack

Files present:

- `Dockerfile`
- `docker-compose.prod.yml`
- `nginx.conf`
- `prometheus.yml`
- `prometheus_alerts.yml`
- `grafana/`
- `.env.production.example`

## Release Gate

```bash
scripts/verify_release.sh
```

This is intended to run syntax checks, static checks, architecture validation, pytest, and production env validation. Treat its output as current only when the command has been run in the target environment.

## Production Readiness Checklist

See **[docs/PRODUCTION_READINESS.md](PRODUCTION_READINESS.md)** for the full gate-by-gate checklist that must pass before the project can be described as production-ready.

## Known Production Gaps

- Docker installs from `backend/requirements.txt`, not a strict lock file (`requirements.lock.txt` exists but isn't used in Docker).
- Postgres storage and queue backend is validated locally (1881 passing tests against Postgres 16). Production behavior (migrations, multi-instance, failover, backup/restore) remains unvalidated until tested in the target deployment environment.
- Dashboard assets are **vendored locally** (no CDN dependencies). Strict CSP (`script-src 'self'`) is enforced.
- Rate limiting is in-memory and single-process only — not distributed across workers. Nginx-level rate limiting zones are pre-configured in `nginx.conf`.
- Browser/Playwright behavior should be validated in the built image.
- Nginx CORS allowlist must be changed from templates to real domains.
- Metrics exposure must be tested through the intended internal Prometheus path.

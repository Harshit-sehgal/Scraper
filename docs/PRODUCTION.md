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

This runs syntax, pyflakes, architecture validation, pytest, and production env validation. It requires a real production `.env` unless `DATAFORGE_SKIP_PROD_ENV_CHECK=1` is explicitly set for non-release local checks.

## Known Production Gaps

- Docker installs from `backend/requirements.txt`, not a strict lock file (`requirements.lock.txt` exists but isn't used in Docker).
- Postgres CI validation is complete (all tests pass with real Postgres service); production multi-instance coordination remains untested.
- Dashboard assets are **vendored locally** (no CDN dependencies). Strict CSP (`script-src 'self'`) is enforced.
- Rate limiting is not proven distributed.
- Browser/Playwright behavior should be validated in the built image.
- Nginx CORS allowlist must be changed from templates to real domains.
- Metrics exposure must be tested through the intended internal Prometheus path.

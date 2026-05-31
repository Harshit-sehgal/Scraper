# Production Startup

**Last refreshed:** 2026-06-01
**Status:** Local production-like startup smoke passed; target production remains unvalidated

Use `docs/PRODUCTION.md` and `docs/PRODUCTION_READINESS.md` as the current production references. This file remains as a short startup sequence to avoid duplicating stale operational claims.

## Required Sequence

1. Create a real uncommitted `.env` from `.env.production.example`.
2. Replace every placeholder with strong unique values.
3. Run:

```bash
python3 scripts/check_prod_env.py --env-file .env
```

4. Build the image:

```bash
docker build -f Dockerfile -t dataforge:local .
```

Current audit result: built `dataforge:local` image `2d6822c8ca4f` locally.

5. Validate compose syntax:

```bash
./bin/docker-compose -f docker-compose.prod.yml config -q
```

Current audit result: passed as part of local Compose startup with a temporary ignored `.env`.

6. Start and verify the stack:

```bash
./bin/docker-compose -f docker-compose.prod.yml up -d
./bin/docker-compose -f docker-compose.prod.yml ps
curl -i http://localhost/health
curl -i http://localhost/ready
```

Current local audit result: backend/worker/Postgres healthy, Nginx returned `/health` 200, `/ready` 200, `/app/` 200, and 404 for `/docs`, `/redoc`, `/openapi.json`, and `/metrics`; Prometheus targets were up; Chromium launched in the API container; one worker job against `https://example.com` completed with one record.

Do not call the project production ready until the same checks pass in the target environment and TLS, CORS/CSP browser behavior, Grafana login/dashboards, alert delivery, backups, restore, load, failure drills, logs, and persistence across restart are validated.

# Production Startup

**Last refreshed:** 2026-06-08
**Status:** Local production-like startup smoke passed on 2026-06-01; target production remains unvalidated

Use [PRODUCTION.md](PRODUCTION.md) and [DEPLOYMENT_CHECKLIST.md](DEPLOYMENT_CHECKLIST.md) as the current production references. This file remains as a short startup sequence to avoid duplicating stale operational claims.

## Required Sequence

1. Create a real uncommitted `.env.production` from `.env.production.example`.
2. Replace every placeholder with strong unique values.
3. Run:

```bash
python3 scripts/check_prod_env.py --env-file .env.production
```

4. Build the image:

```bash
docker build -f Dockerfile -t dataforge:local .
```

Current audit result: local smoke built `dataforge:local` image successfully.

5. Validate compose syntax:

```bash
docker compose -f docker-compose.prod.yml config -q
```

Current audit result: passed as part of local Compose startup with a temporary ignored `.env`.

6. Start and verify the stack:

```bash
DATAFORGE_IMAGE_TAG=v<VERSION> docker compose -f docker-compose.prod.yml up -d --pull never
docker compose -f docker-compose.prod.yml ps
curl -k -i https://localhost/health
curl -k -i https://localhost/ready
```

For local smoke runs, prefer `bash scripts/smoke_prod_stack.sh`. The
script generates a temporary localhost certificate unless
`DATAFORGE_NGINX_SSL_DIR` points at a directory containing
`fullchain.pem` and `privkey.pem`, then verifies `/health`, `/ready`,
authenticated API status, monitoring, alerting, and one deterministic
worker job through the HTTPS nginx ingress.

Do not call the project production ready until the same checks pass in the target environment and TLS, CORS/CSP browser behavior, Grafana login/dashboards, alert delivery, backups, restore, load, failure drills, logs, and persistence across restart are validated.

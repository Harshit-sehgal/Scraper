# Staging Runbook (E1.1)

Short, executable runbook for standing up a staging deployment of
DataForge on a single VPS. Derived from
`docs/DEPLOYMENT_CHECKLIST.md`; run its phases in order for a full
production-hardened deploy. Owner action required: provision the VPS
and DNS record, then hand the agent the host.

## 0. Prerequisites (owner)

- One VPS (≥4 GB RAM, ≥2 vCPU) with Docker + Docker Compose installed.
- DNS record `staging.<domain>` → VPS IP (A record).
- Firewall open: 80, 443, 9100 (node-exporter), 9090 (Prometheus, locked
  down or behind VPN), 3000 (Grafana, locked down), 9093 (Alertmanager,
  locked down).
- A payment provider sandbox: Dodo Payments test-mode API key, webhook
  signing key, and product ids (see Billing section below).

## 1. Secrets & Configuration

Generate secrets on the admin machine (never in git):

```bash
python3 scripts/generate_prod_env.py --output /tmp/env.production.secure
cat /tmp/env.production.secure        # review every value
scp /tmp/env.production.secure user@staging.<domain>:.env.production
```

Verify on the host:

```bash
env -i PATH="$PATH" PYTHONPATH=backend DATAFORGE_SKIP_DB_CHECK=true \
  python3 scripts/check_prod_env.py --env-file .env.production
# Expected output: All checks PASS
```

Required env vars (a subset of `.env.production`):

| Variable | Purpose |
|---|---|
| `DATAFORGE_ENV=production` | production mode (enforced by compose) |
| `DATAFORGE_API_KEY` / `OPERATOR` / `ADMIN_API_KEY` | API auth (file-mapped to secrets in compose) |
| `DATAFORGE_SESSION_SECRET` | session signing |
| `DATAFORGE_DATABASE_URL` | Postgres connection string |
| `DATAFORGE_QUEUE_BACKEND=postgres` | durable worker queue |
| `DATAFORGE_ALLOWED_INTERNAL_HOSTS` | internal host allowlist (empty = none) |
| `DATAFORGE_SMOKE_TEST_MODE` | set `true` only during smoke runs |

## 2. Billing (Dodo Payments)

Add to `.env.production`:

```bash
DODO_PAYMENTS_ENVIRONMENT=test_mode          # live_mode ONLY for real revenue
DODO_PAYMENTS_API_KEY=...                    # test/live key
DODO_PAYMENTS_WEBHOOK_KEY=...                # base64 signing secret
DODO_PRODUCT_ID_STARTER=...                  # product ids from Dodo dashboard
DODO_PRODUCT_ID_PRO=...
DODO_PRODUCT_ID_ENTERPRISE=...
DODO_CHECKOUT_RETURN_URL=https://staging.<domain>/app/billing
DODO_WEBHOOK_STATE_FILE=/app/backend/data/w/dodo_webhook_state.json
```

Webhook endpoint to register in the Dodo dashboard:
`https://staging.<domain>/api/billing/dodo/webhook` (Standard Webhooks
signing, idempotent by `webhook-id`).

Verify locally before/after deploy:

```bash
python3 scripts/run_dodo_billing_e2e.py          # mocked money loop, CI-safe
python3 scripts/reconcile_billing.py             # entitlement repair sweep
```

## 3. Build & Deploy

```bash
export DATAFORGE_IMAGE_TAG=v1.0.0-staging
export DATAFORGE_DB_PASSWORD="$(grep DATAFORGE_DB_PASSWORD .env.production | cut -d= -f2)"
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml ps
```

Compose runs: `dataforge` (API), `worker`, `postgres`, `nginx`,
`prometheus`, `grafana`, `alertmanager`, `blackbox-exporter`,
`node-exporter`, `cadvisor`, `postgres-exporter`.

## 4. TLS + Nginx

- Set `server_name staging.<domain>;` in the nginx config; the default
  443 server returns 444 for unknown Host headers, so the placeholder
  must be replaced before public traffic arrives.
- Mount the real certificate at `/etc/nginx/ssl/fullchain.pem` and
  `/etc/nginx/ssl/privkey.pem`, or use the Let's Encrypt path from
  `docs/DEPLOYMENT_CHECKLIST.md` step 2.1, then reload nginx.

## 5. Post-Deploy Verification

```bash
curl -fsS https://staging.<domain>/health && curl -fsS https://staging.<domain>/ready
bash scripts/smoke_prod_stack.sh                 # full-stack smoke incl. Alertmanager
python3 scripts/run_alert_delivery_drill.py      # synthetic alert delivery drill
python3 scripts/run_load_profile.py              # multi-endpoint load validation
docker exec dataforge-postgres pg_dump -U dataforge -d dataforge > /tmp/backup.sql   # backup drill
```

## 6. Rollback

```bash
docker compose -f docker-compose.prod.yml ps --format json > /tmp/pre_rollback.json
export DATAFORGE_IMAGE_TAG=<previous-tag>
docker compose -f docker-compose.prod.yml up -d --no-deps dataforge worker
# Verify /health + /ready, then re-run section 5 checks.
```

## 7. Handoff Evidence

Record in `docs/AGENT_TRUTH.md`: deploy date, image tag, smoke exit
codes, alert drill result, reconcile report, backup file hash.

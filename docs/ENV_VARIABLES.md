# Environment Variables Reference

## Overview

DataForge uses `DATAFORGE_` prefixed environment variables for configuration. All variables are defined in `backend/app/config/` using pydantic-settings.

## Core Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `DATAFORGE_ENV` | `development` | Environment: `development`, `staging`, `production` |
| `DATAFORGE_DEBUG` | `false` | Enable debug mode |
| `DATAFORGE_ENABLE_RELOAD` | `false` | Enable uvicorn `--reload` / debug logging in the dev container target; leave unset for production/default compose runs |
| `DATAFORGE_DOTENV_PATH` | `.env` | Path to dotenv file |
| `DATAFORGE_STORAGE_BACKEND` | `sqlite` | Storage backend: `sqlite` or `postgres` |
| `DATAFORGE_DATABASE_URL` | - | PostgreSQL connection URL (required for postgres backend) |
| `DATAFORGE_STATE_FILE` | `data/state.json` | Path to state file |
| `DATAFORGE_DB_CONNECT_TIMEOUT` | `10` | Postgres connect timeout in seconds (used by `verify_postgres_connectivity` and pool init). The test suite sets this to `1` for fast-fail negative paths. |
| `DATAFORGE_JOB_STORE_PATH` | - | Override SQLite job-store database path |
| `DATAFORGE_SEMANTIC_STATE_PATH` | `data/semantic_state.json` | Path to semantic state file |

## Production Ingress

| Variable | Default | Description |
|----------|---------|-------------|
| `DATAFORGE_NGINX_SSL_DIR` | `./.secrets/nginx` | Directory mounted into production nginx at `/etc/nginx/ssl`; must contain `fullchain.pem` and `privkey.pem` for real TLS deployments |
| `DATAFORGE_CERTBOT_WEBROOT` | `./.secrets/certbot/www` | Directory mounted into production nginx at `/var/www/certbot` for ACME http-01 challenge files |

## Authentication

| Variable | Default | Description |
|----------|---------|-------------|
| `DATAFORGE_API_KEY` | - | User-level API key (read access) |
| `DATAFORGE_OPERATOR_API_KEY` | - | Operator API key (write access; env-backed operators have all-access with no org/project scope) |
| `DATAFORGE_ADMIN_API_KEY` | - | Admin API key (global all-access) |
| `DATAFORGE_SESSION_SECRET` | - | Session signing secret (auto-generated if not set) |
| `DATAFORGE_ALLOW_INSECURE_DEV_AUTH` | `false` | Allow insecure auth in development |
| `DATAFORGE_BILLING_WEBHOOK_SECRET` | - | Shared secret for billing webhook HMAC/shared-secret verification |

## Rate Limiting

| Variable | Default | Description |
|----------|---------|-------------|
| `DATAFORGE_RATE_LIMIT_GLOBAL` | `600` | Global rate limit (requests/minute) |
| `DATAFORGE_RATE_LIMIT_PER_IP` | `100` | Per-IP rate limit (requests/minute) |
| `DATAFORGE_RATE_LIMIT_PER_IP_ENABLED` | `true` | Enable per-IP rate limiting |
| `DATAFORGE_RATE_LIMIT_DB_BACKED` | `false` | Use database-backed rate limits |

## Worker Queue

| Variable | Default | Description |
|----------|---------|-------------|
| `DATAFORGE_WORKER_QUEUE` | `memory` | Queue backend: `memory`, `postgres` |
| `DATAFORGE_WORKER_HEARTBEAT_ID` | - | Worker heartbeat identifier |
| `DATAFORGE_WORKER_HEARTBEAT_TTL` | `60` | Worker heartbeat freshness window in seconds for the worker healthcheck |

## Notifications

| Variable | Default | Description |
|----------|---------|-------------|
| `DATAFORGE_TELEGRAM_ENABLED` | `false` | Enable Telegram notifications |
| `DATAFORGE_TELEGRAM_BOT_TOKEN` | - | Telegram bot token |
| `DATAFORGE_TELEGRAM_CHAT_ID` | - | Telegram chat ID |

## Security

| Variable | Default | Description |
|----------|---------|-------------|
| `DATAFORGE_METRICS_TOKEN` | - | Token for metrics endpoint |
| `DATAFORGE_TRUSTED_PROXIES` | - | Comma-separated list of trusted proxies |
| `DATAFORGE_CORS_ORIGINS` | - | Comma-separated list of allowed CORS origins |
| `DATAFORGE_ALLOWED_INTERNAL_HOSTS` | - | Comma-separated list of allowed internal hosts |
| `DATAFORGE_DENYLIST_DB_PATH` | - | Optional SQLite path for the operator-managed domain denylist |
| `DATAFORGE_ENCRYPTION_KEY` | - | Base64 AES-GCM key for auth-profile storage state encryption |
| `DATAFORGE_ENCRYPTION_SALT` | `default-salt-change-in-prod` | Salt used in encryption key derivation for auth-profile encryption |
| `DATAFORGE_REDIS_URL` | - | Redis connection URL for rate-limiter distributed storage |
| `DATAFORGE_ENCRYPTION_KEY_` | - | Prefix for versioned encryption keys such as `DATAFORGE_ENCRYPTION_KEY_V1` |
| `DATAFORGE_ACTIVE_ENCRYPTION_KEY_VERSION` | `v1` | Active version used for new encrypted payloads |
| `DATAFORGE_AUTH_PROFILES_FILE` | `data/auth_profiles.json` | Path to the file-backed auth-profile store (used by `AuthProfileStore` in `app/utils/auth_profile_store.py`) |
| `DATAFORGE_BILLING_SUBSCRIPTIONS_FILE` | `data/billing_subscriptions.json` | Path to the file-backed billing-subscription store |
| `DATAFORGE_WORKFLOW_RUNS_FILE` | `data/workflow_runs.json` | Path to the file-backed workflow-run history store |
| `DATAFORGE_DISCOVERY_DIRECTORY_DOMAINS` | - | Comma-separated allowlist of domains for auto-discovery directory mode |
| `DATAFORGE_LOCATION_WORDS` | - | Comma-separated extra location words to recognise when extracting location fields |
| `DATAFORGE_LOCATION_WORDS_FILE` | - | Path to a file containing extra location words (one per line) |
| `DATAFORGE_DB_PASSWORD` | - | Postgres password (fallback used by backup/restore scripts when `DATAFORGE_DATABASE_URL` is unset) |

## Experimental Features

| Variable | Default | Description |
|----------|---------|-------------|
| `DATAFORGE_ENABLE_EXPERIMENTAL_ROUTES` | `false` | Enable experimental API routes |
| `DATAFORGE_SMOKE_TEST_MODE` | `false` | Enable smoke test mode |

## Data Retention

| Variable | Default | Description |
|----------|---------|-------------|
| `DATAFORGE_RETENTION_DAYS_COMPLETED` | `30` | Days to retain completed jobs before automatic cleanup |
| `DATAFORGE_RETENTION_DAYS_IDEMPOTENCY` | `7` | Days to retain idempotency keys for deduplication |
| `DATAFORGE_RETENTION_DAYS_RECYCLE` | `30` | Days to retain soft-deleted jobs in recycle bin before permanent purge |
| `DATAFORGE_RETENTION_INTERVAL` | `43200` | Background retention sweep interval in seconds (default 12h) |

## LLM Integration

| Variable | Default | Description |
|----------|---------|-------------|
| `GROQ_API_KEY` | - | Groq API key for LLM operations |
| `DATAFORGE_GROQ_API_KEY` | - | Alternative prefix for Groq API key (takes precedence over `GROQ_API_KEY`) |

## Testing

| Variable | Default | Description |
|----------|---------|-------------|
| `DATAFORGE_TEST_DETERMINISTIC_ENV_VAR` | - | Test-only environment variable |
| `DATAFORGE_TEST_SELECTOR_DECAY_PERSISTENCE` | `false` | Persist selector decay snapshots during tests |

## Direct Environment Reads

These are acceptable direct environment reads outside the config module:

| File | Variable | Purpose |
|------|----------|---------|
| `backend/app/__init__.py` | `DATAFORGE_DOTENV_PATH` | Dotenv loading boundary |
| `backend/app/utils/env.py` | Generic helper | Environment utility |
| `backend/app/billing/checkout.py` | `DATAFORGE_PUBLIC_BASE_URL` | Public base URL for constructing checkout approval URLs |
| `backend/app/rate_limiter.py` | `DATAFORGE_REDIS_URL` | Redis connection URL for distributed rate-limiter storage |
| `backend/app/utils/encryption.py` | `DATAFORGE_ENCRYPTION_SALT` | Encryption salt for auth-profile key derivation |
| `scripts/check_prod_env.py` | `DATAFORGE_SKIP_DB_CHECK` | Validation script |
| `scripts/run_worker.py` | `DATAFORGE_JOB_ID` | Worker script |
| `scripts/manual_test.py` | `DATAFORGE_API_BASE` | Manual testing |
| `scripts/staging_smoke_test.py` | `STATE_FILE_PATH` | Smoke test |

## Production Validation

Before deploying to production, validate environment:

```bash
# Run production environment checker
python3 scripts/check_prod_env.py

# Run security validator
python3 -c "from app.utils.prod_security_validator import validate_production_credentials; validate_production_credentials()"
```

## Security Notes

1. **Never commit secrets** - Use environment variables or secrets manager
2. **Rotate keys regularly** - Especially `DATAFORGE_SESSION_SECRET` and `DATAFORGE_ADMIN_API_KEY`
3. **Use HTTPS in production** - Set `DATAFORGE_ENV=production`
4. **Validate on startup** - Use `scripts/check_prod_env.py` before deployment

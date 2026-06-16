# Environment Variables Reference

## Overview

DataForge uses `DATAFORGE_` prefixed environment variables for configuration. All variables are defined in `backend/app/config/` using pydantic-settings.

## Core Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `DATAFORGE_ENV` | `development` | Environment: `development`, `staging`, `production` |
| `DATAFORGE_DEBUG` | `false` | Enable debug mode |
| `DATAFORGE_DOTENV_PATH` | `.env` | Path to dotenv file |
| `DATAFORGE_STORAGE_BACKEND` | `sqlite` | Storage backend: `sqlite` or `postgres` |
| `DATAFORGE_DATABASE_URL` | - | PostgreSQL connection URL (required for postgres backend) |
| `DATAFORGE_STATE_FILE` | `data/state.json` | Path to state file |
| `DATAFORGE_JOB_STORE_PATH` | - | Override SQLite job-store database path |
| `DATAFORGE_SEMANTIC_STATE_PATH` | `data/semantic_state.json` | Path to semantic state file |

## Authentication

| Variable | Default | Description |
|----------|---------|-------------|
| `DATAFORGE_API_KEYS` | - | Comma-separated list of API keys |
| `DATAFORGE_ADMIN_API_KEY` | - | Admin API key |
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

## Notifications

| Variable | Default | Description |
|----------|---------|-------------|
| `DATAFORGE_TELEGRAM_ENABLED` | `false` | Enable Telegram notifications |
| `DATAFORGE_TELEGRAM_TOKEN` | - | Telegram bot token |
| `DATAFORGE_TELEGRAM_CHAT_ID` | - | Telegram chat ID |

## Security

| Variable | Default | Description |
|----------|---------|-------------|
| `DATAFORGE_METRICS_TOKEN` | - | Token for metrics endpoint |
| `DATAFORGE_TRUSTED_PROXIES` | - | Comma-separated list of trusted proxies |
| `DATAFORGE_ALLOWED_INTERNAL_HOSTS` | - | Comma-separated list of allowed internal hosts |
| `DATAFORGE_DENYLIST_DB_PATH` | - | Optional SQLite path for the operator-managed domain denylist |
| `DATAFORGE_ENCRYPTION_KEY` | - | Base64 AES-GCM key for auth-profile storage state encryption |
| `DATAFORGE_ENCRYPTION_KEY_` | - | Prefix for versioned encryption keys such as `DATAFORGE_ENCRYPTION_KEY_V1` |
| `DATAFORGE_ACTIVE_ENCRYPTION_KEY_VERSION` | `v1` | Active version used for new encrypted payloads |

## Experimental Features

| Variable | Default | Description |
|----------|---------|-------------|
| `DATAFORGE_ENABLE_EXPERIMENTAL_ROUTES` | `false` | Enable experimental API routes |
| `DATAFORGE_SMOKE_TEST_MODE` | `false` | Enable smoke test mode |

## LLM Integration

| Variable | Default | Description |
|----------|---------|-------------|
| `GROQ_API_KEY` | - | Groq API key for LLM operations |

## Testing

| Variable | Default | Description |
|----------|---------|-------------|
| `DATAFORGE_TEST_DETERMINISTIC_ENV_VAR` | - | Test-only environment variable |

## Direct Environment Reads

These are acceptable direct environment reads outside the config module:

| File | Variable | Purpose |
|------|----------|---------|
| `backend/app/__init__.py` | `DATAFORGE_DOTENV_PATH` | Dotenv loading boundary |
| `backend/app/utils/env.py` | Generic helper | Environment utility |
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

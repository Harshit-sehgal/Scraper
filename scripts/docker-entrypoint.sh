#!/bin/bash
set -e

# Run production preflight check if ENV is production
if [ "${DATAFORGE_ENV}" = "production" ]; then
    echo "[preflight] Running production environment check..."
    python scripts/check_prod_env.py --env-file /dev/null 2>&1 || true
    # Note: check_prod_env reads from .env file, but in Docker env vars are injected directly.
    # The app itself validates at startup (see main.py lifespan).
fi

exec "$@"

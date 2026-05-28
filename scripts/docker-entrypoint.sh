#!/bin/bash
set -e

# Run production preflight check if ENV is production
if [ "${DATAFORGE_ENV}" = "production" ]; then
    echo "[preflight] Running production environment check..."
    python scripts/check_prod_env.py --env-file /dev/null
fi

exec "$@"

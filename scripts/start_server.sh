#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"

# Set PYTHONPATH before any Python invocation. The env validator
# (``scripts/check_prod_env.py``) imports backend modules such as
# ``app.worker_queue_postgres_psycopg3`` when running in
# production, which fails with ``ModuleNotFoundError`` if
# ``PYTHONPATH`` is not exported first. The previous order — run
# the validator, then export ``PYTHONPATH`` — worked inside the
# Docker image (where ``PYTHONPATH`` is set via the Dockerfile
# ``ENV`` directive) but failed in bare-shell invocations.
export PYTHONPATH="${PYTHONPATH:-$ROOT_DIR/backend}"

cd "$ROOT_DIR"

if [[ "${DATAFORGE_ENV:-}" == "production" ]]; then
    "$PYTHON_BIN" scripts/check_prod_env.py --env-file "${DATAFORGE_ENV_FILE:-.env}"
fi

exec "$PYTHON_BIN" -m uvicorn app.main:app \
    --host "${DATAFORGE_HOST:-0.0.0.0}" \
    --port "${DATAFORGE_PORT:-8000}" \
    --log-level "${DATAFORGE_LOG_LEVEL:-info}"

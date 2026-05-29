#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"

cd "$ROOT_DIR"

if [[ "${DATAFORGE_ENV:-}" == "production" ]]; then
    "$PYTHON_BIN" scripts/check_prod_env.py --env-file "${DATAFORGE_ENV_FILE:-.env}"
fi

export PYTHONPATH="${PYTHONPATH:-$ROOT_DIR/backend}"

exec "$PYTHON_BIN" scripts/run_worker.py

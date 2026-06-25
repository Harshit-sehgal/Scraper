#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"

# Set PYTHONPATH before any Python invocation. See the matching
# comment in ``start_server.sh`` for the rationale.
export PYTHONPATH="${PYTHONPATH:-$ROOT_DIR/backend}"

cd "$ROOT_DIR"

# shellcheck source=scripts/load_runtime_secrets.sh
source "$ROOT_DIR/scripts/load_runtime_secrets.sh"
_load_file_backed_runtime_secrets

if [[ "${DATAFORGE_ENV:-}" == "production" ]]; then
    "$PYTHON_BIN" scripts/check_prod_env.py --env-file "${DATAFORGE_ENV_FILE:-.env.production}"
fi

exec "$PYTHON_BIN" scripts/run_worker.py

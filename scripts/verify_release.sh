#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"

cd "$ROOT_DIR"
export PYTHONPATH="${PYTHONPATH:-backend}"

echo "== Syntax compile =="
"$PYTHON_BIN" -m compileall -q backend scripts architecture_validator.py

echo "== Pyflakes =="
"$PYTHON_BIN" -m pyflakes backend/app scripts architecture_validator.py

echo "== Architecture validator =="
PYTHONPATH=backend "$PYTHON_BIN" architecture_validator.py

echo "== Pytest =="
PYTHONPATH=backend "$PYTHON_BIN" -m pytest backend/tests -q

if [[ "${DATAFORGE_SKIP_PROD_ENV_CHECK:-0}" == "1" ]]; then
    echo "== Production env check skipped by DATAFORGE_SKIP_PROD_ENV_CHECK=1 =="
else
    echo "== Production env check =="
    "$PYTHON_BIN" scripts/check_prod_env.py --env-file "${DATAFORGE_ENV_FILE:-.env.production}"
fi

echo "Selected release verification checks completed."

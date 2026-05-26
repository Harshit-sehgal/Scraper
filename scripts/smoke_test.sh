#!/usr/bin/env bash
# =============================================================================
# DataForge Scraper — Repeatable SRE Smoke Test
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_DIR"

PYTHON_EXE="python"
if command -v python3 &>/dev/null; then
  PYTHON_EXE="python3"
fi

# Detect virtual environment
VENV_DIR=""
for candidate in ".venv" "venv" "env"; do
    if [ -f "$PROJECT_DIR/$candidate/bin/activate" ]; then
        VENV_DIR="$PROJECT_DIR/$candidate"
        break
    fi
done

if [ -n "$VENV_DIR" ]; then
    echo "Activating virtual env: $VENV_DIR"
    # shellcheck disable=SC1091
    source "$VENV_DIR/bin/activate"
fi

echo "=== 1. Validating Python Compilation ==="
$PYTHON_EXE -m compileall backend/app backend/tests

echo "=== 2. Validating FastAPI Import & Pathing ==="
PYTHONPATH=backend $PYTHON_EXE -c "from app.main import app; print('FastAPI import OK')"

echo "=== 3. Validating Startup Script Syntax ==="
bash -n scripts/start.sh

echo "=== 4. Checking Unsafe eval() in Source ==="
# Check for eval( excluding ast.literal_eval
if grep -R "eval(" backend/app | grep -qv "ast.literal_eval"; then
    echo "❌ ERROR: Unsafe eval() calls found!"
    grep -R "eval(" backend/app | grep -v "ast.literal_eval"
    exit 1
else
    echo "✅ No unsafe eval() calls detected."
fi

echo "=== 5. Running Production Hardening Tests ==="
cd backend
PYTHONPATH=. $PYTHON_EXE -m pytest tests/test_production_hardening.py -q -o "addopts="

echo "=== Smoke Test Complete — ALL CHECKS PASSED ==="

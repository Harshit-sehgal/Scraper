#!/usr/bin/env bash
# =============================================================================
# DataForge Scraper — Repeatable SRE Quick Check
# =============================================================================
set -euo pipefail

STEP=0
report_error() {
  local exit_code=$?
  echo "❌ FAILED on Step ${STEP} (exit code ${exit_code})" >&2
  exit "${exit_code}"
}
trap report_error ERR

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_DIR"

echo "Project dir: $PROJECT_DIR"
echo "Python: $(python3 --version 2>&1 || true)"
echo "Python: $(python --version 2>&1 || true)"

PYTHON_EXE="python"
if command -v python3 &>/dev/null; then
  PYTHON_EXE="python3"
fi

echo "Using Python: $PYTHON_EXE ($($PYTHON_EXE --version 2>&1))"

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
STEP=1
$PYTHON_EXE -m compileall backend/app backend/tests 2>&1

echo "=== 2. Validating FastAPI Import & Pathing ==="
STEP=2
PYTHONPATH=backend $PYTHON_EXE -c "from app.main import app; print('FastAPI import OK')" 2>&1

echo "=== 3. Validating Startup Script Syntax ==="
STEP=3
bash -n scripts/start.sh scripts/start_server.sh scripts/start_worker.sh 2>&1

echo "=== 4. Checking Unsafe eval() in Source ==="
STEP=4
# Check for eval( excluding ast.literal_eval
if grep -R "eval(" backend/app 2>&1 | grep -qv "ast.literal_eval"; then
    echo "❌ ERROR: Unsafe eval() calls found!"
    grep -R "eval(" backend/app 2>&1 | grep -v "ast.literal_eval"
    exit 1
else
    echo "✅ No unsafe eval() calls detected."
fi

echo "=== 5. Running Architecture Validator ==="
STEP=5
$PYTHON_EXE architecture_validator.py 2>&1

echo "=== 6. Running Production Hardening Tests ==="
STEP=6
cd backend 2>&1
PYTHONPATH=. $PYTHON_EXE -m pytest tests/test_production_hardening.py -q -o "addopts=" 2>&1

if [ "${GITHUB_ACTIONS:-false}" = "true" ]; then
    echo "=== Skipping Step 7 in CI (redundant, handled by the 'test' job) ==="
else
    echo "=== 7. Running Full pytest Suite ==="
    STEP=7
    # Skip Postgres/live-LLM tests (require Docker/RUN_LIVE_LLM_TESTS=1)
    PYTHONPATH=. $PYTHON_EXE -m pytest -q -o "addopts=" -k "not postgres and not test_profile_alignment_e2e" 2>&1
fi

echo "=== SRE Quick Check Complete — selected checks passed ==="

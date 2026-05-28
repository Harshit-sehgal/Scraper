#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
BACKEND_DIR="$ROOT_DIR/backend"

echo "============================================"
echo " verify_release.sh — Release readiness checks"
echo "============================================"
echo ""

EXIT_CODE=0

# 1. Compile check
echo "[1/5] Compile check"
if python3 -m compileall -q "$BACKEND_DIR/app" "$BACKEND_DIR/tests" "$ROOT_DIR/scripts" "$ROOT_DIR/architecture_validator.py" 2>&1; then
    echo "  PASS"
else
    echo "  FAIL — compilation errors found"
    EXIT_CODE=1
fi
echo ""

# 2. Pyflakes
echo "[2/5] Pyflakes"
FLAKES=$(PYTHONPATH="$BACKEND_DIR" python3 -m pyflakes "$BACKEND_DIR/app" "$BACKEND_DIR/tests" 2>&1 | grep -v '__pycache__' | head -20 || true)
if [ -z "$FLAKES" ]; then
    echo "  PASS"
else
    echo "  FAIL — pyflakes issues:"
    echo "$FLAKES"
    EXIT_CODE=1
fi
echo ""

# 3. Architecture validator
echo "[3/5] Architecture validator"
if PYTHONPATH="$BACKEND_DIR" python3 "$ROOT_DIR/architecture_validator.py" 2>&1 | tail -3; then
    echo "  PASS"
else
    echo "  FAIL"
    EXIT_CODE=1
fi
echo ""

# 4. Pytest
echo "[4/5] Pytest (full suite)"
set +e
PYTHONPATH="$BACKEND_DIR" python3 -m pytest "$BACKEND_DIR/tests" -q --tb=line 2>&1 | tail -5
PYTEST_EXIT=$?
set -e
if [ $PYTEST_EXIT -eq 0 ]; then
    echo "  PASS"
else
    echo "  FAIL — $PYTEST_EXIT"
    EXIT_CODE=1
fi
echo ""

# 5. Production env check (only if .env.production exists)
echo "[5/5] Production env check"
if [ -f "$ROOT_DIR/.env.production" ]; then
    if python3 "$ROOT_DIR/scripts/check_prod_env.py" --env-file "$ROOT_DIR/.env.production" 2>&1 | tail -3; then
        echo "  PASS"
    else
        echo "  FAIL"
        EXIT_CODE=1
    fi
else
    echo "  SKIP — no .env.production file found"
fi
echo ""

# Summary
echo "============================================"
if [ $EXIT_CODE -eq 0 ]; then
    echo " RESULT: ALL CHECKS PASSED"
else
    echo " RESULT: SOME CHECKS FAILED (exit code $EXIT_CODE)"
fi
echo "============================================"
exit $EXIT_CODE

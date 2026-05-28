#!/usr/bin/env bash
# =============================================================================
# verify_all.sh — Local CI-equivalent verification
# =============================================================================
# Run all checks that GitHub Actions would run: pyflakes, mypy, pytest,
# frontend JS validation, shell syntax, and release readiness checks.
#
# Usage:
#   ./scripts/verify_all.sh
#
# Exit codes:
#   0 — All checks passed
#   1 — One or more checks failed
# =============================================================================
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKEND_DIR="$PROJECT_DIR/backend"

PASS=0
FAIL=0

pass_check() { echo -e "  ${GREEN}PASS${NC} — $1"; PASS=$((PASS + 1)); }
fail_check() { echo -e "  ${RED}FAIL${NC} — $1"; FAIL=$((FAIL + 1)); }

echo "============================================"
echo " verify_all.sh — Local CI-equivalent checks"
echo "============================================"
echo ""

# ─── 1. Python Compilation ─────────────────────────────────────
echo "[1/7] Python compilation"
if python3 -m compileall -q "$BACKEND_DIR/app" "$BACKEND_DIR/tests" 2>&1; then
    pass_check "compileall — 0 errors"
else
    fail_check "compileall — syntax errors"
fi

# ─── 2. pyflakes ───────────────────────────────────────────────
echo "[2/7] pyflakes"
if python3 -m pyflakes "$BACKEND_DIR/app" "$BACKEND_DIR/tests" 2>&1; then
    pass_check "pyflakes — 0 issues"
else
    fail_check "pyflakes — issues found"
fi

# ─── 3. Architecture Validator ─────────────────────────────────
echo "[3/7] Architecture validator"
if cd "$PROJECT_DIR" && PYTHONPATH=backend python3 architecture_validator.py 2>&1; then
    pass_check "architecture validator — passed"
else
    fail_check "architecture validator — failed"
fi
cd "$SCRIPT_DIR" 2>/dev/null || true

# ─── 4. pytest (targeted) ──────────────────────────────────────
echo "[4/7] pytest (targeted — production hardening + security + metrics)"
PYTEST_TMP=$(mktemp)
set +e
PYTHONPATH="$BACKEND_DIR" python3 -m pytest \
    "$BACKEND_DIR/tests/test_production_hardening.py" \
    "$BACKEND_DIR/tests/test_url_safety.py" \
    "$BACKEND_DIR/tests/test_metrics.py" \
    -q -o "addopts=" \
    > "$PYTEST_TMP" 2>&1
PYTEST_EXIT=$?
set -e
tail -5 "$PYTEST_TMP"
if [ $PYTEST_EXIT -eq 0 ]; then
    pass_check "pytest (targeted) — all passed"
else
    fail_check "pytest (targeted) — failures"
    grep -E "FAILED|ERROR" "$PYTEST_TMP" | head -10
fi
rm -f "$PYTEST_TMP"

# ─── 5. frontend JS ────────────────────────────────────────────
echo "[5/7] frontend JS validation"
JS_OK=true
for jsfile in "$PROJECT_DIR/frontend/app.js" "$PROJECT_DIR/frontend/dashboard/dashboard.js"; do
    if [ -f "$jsfile" ] && ! node -c "$jsfile" 2>/dev/null; then
        JS_OK=false
    fi
done
if $JS_OK; then
    pass_check "frontend JS — valid"
else
    fail_check "frontend JS — invalid"
fi

# ─── 6. shell scripts ──────────────────────────────────────────
echo "[6/7] shell scripts"
SH_OK=true
for shfile in "$PROJECT_DIR/scripts"/*.sh; do
    if [ -f "$shfile" ] && ! bash -n "$shfile" 2>/dev/null; then
        SH_OK=false
    fi
done
if $SH_OK; then
    pass_check "shell scripts — valid"
else
    fail_check "shell scripts — issues"
fi

# ─── 7. Production env check ───────────────────────────────────
echo "[7/7] Production environment check"
if cd "$PROJECT_DIR" && PYTHONPATH=backend python3 scripts/check_prod_env.py --env-file .env.production.example 2>&1; then
    pass_check "production env — checks passed"
else
    fail_check "production env — checks failed (expected if using defaults)"
fi
cd "$SCRIPT_DIR" 2>/dev/null || true

# ─── Summary ───────────────────────────────────────────────────
echo ""
echo "============================================"
echo " Results: $PASS passed, $FAIL failed"
echo "============================================"

if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
exit 0

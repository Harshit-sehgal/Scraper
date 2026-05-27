#!/usr/bin/env bash
# =============================================================================
# verify_all.sh — Local CI-equivalent verification
# =============================================================================
# Run all checks that GitHub Actions would run: pyflakes, mypy, pytest,
# frontend JS validation, and git diff check.
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

# ─── pyflakes ──────────────────────────────────────────────────
echo "[1/6] pyflakes"
if python3 -m pyflakes "$BACKEND_DIR/app" "$BACKEND_DIR/tests" 2>&1; then
    pass_check "pyflakes — 0 issues"
else
    fail_check "pyflakes — issues found"
fi

# ─── mypy ──────────────────────────────────────────────────────
echo "[2/6] mypy"
if python3 -m mypy "$BACKEND_DIR/app" --ignore-missing-imports 2>&1 | tail -1 | grep -q "Success"; then
    pass_check "mypy — 0 errors"
else
    fail_check "mypy — errors found"
    python3 -m mypy "$BACKEND_DIR/app" --ignore-missing-imports 2>&1 | grep "error:" | head -5
fi

# ─── pytest ────────────────────────────────────────────────────
echo "[3/6] pytest"
PYTHONPATH="$BACKEND_DIR" python3 -m pytest "$BACKEND_DIR/tests" \
    -q -o "addopts=" \
    --ignore="$BACKEND_DIR/tests/test_profile_alignment_e2e.py" \
    --timeout=120 \
    2>&1 | tail -3
if [ ${PIPESTATUS[0]} -eq 0 ]; then
    pass_check "pytest"
else
    fail_check "pytest — failures"
fi

# ─── frontend JS ───────────────────────────────────────────────
echo "[4/6] frontend JS validation"
JS_OK=true
for jsfile in "$PROJECT_DIR/frontend/app.js" "$PROJECT_DIR/frontend/dashboard/dashboard.js"; do
    if ! node -c "$jsfile" 2>/dev/null; then
        JS_OK=false
    fi
done
if $JS_OK; then
    pass_check "frontend JS — valid"
else
    fail_check "frontend JS — invalid"
fi

# ─── shell scripts ─────────────────────────────────────────────
echo "[5/6] shell scripts"
SH_OK=true
for shfile in "$PROJECT_DIR/scripts"/*.sh; do
    if ! bash -n "$shfile" 2>/dev/null; then
        SH_OK=false
    fi
done
if $SH_OK; then
    pass_check "shell scripts — valid"
else
    fail_check "shell scripts — issues"
fi

# ─── git diff ──────────────────────────────────────────────────
echo "[6/6] git diff --check"
if git -C "$PROJECT_DIR" diff --check 2>/dev/null; then
    pass_check "git diff — clean"
else
    fail_check "git diff — whitespace issues"
fi

# ─── Summary ───────────────────────────────────────────────────
echo ""
echo "============================================"
echo " Results: $PASS passed, $FAIL failed"
echo "============================================"

if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
exit 0

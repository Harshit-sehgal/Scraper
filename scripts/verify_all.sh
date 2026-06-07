#!/usr/bin/env bash
# =============================================================================
# verify_all.sh — Local selected verification
# =============================================================================
# Run selected checks used by GitHub Actions: pyflakes, ruff (lint + format),
# research-boundary CI check, mypy, pytest, frontend JS validation,
# shell script syntax, and git diff check.
#
# This script is **archive-hostile** — it tolerates:
#   * Source archives without a .git directory
#   * Missing dev tools (e.g. pyflakes, ruff, mypy not installed)
#   * Missing Node.js for frontend JS checks
#
# Each check is independent: a failure in one does not abort the others.
# A final summary is always printed before exiting.
# =============================================================================

# Note: We intentionally do NOT use `set -e` here because the whole point
# of this script is to surface ALL failing checks, not bail on the first
# one. Each check guards its own exit code.
set -uo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKEND_DIR="$PROJECT_DIR/backend"

PASS=0
FAIL=0
SKIP=0

pass_check() { echo -e "  ${GREEN}PASS${NC} — $1"; PASS=$((PASS + 1)); }
fail_check() { echo -e "  ${RED}FAIL${NC} — $1"; FAIL=$((FAIL + 1)); }
skip_check() { echo -e "  ${YELLOW}SKIP${NC} — $1"; SKIP=$((SKIP + 1)); }

# Tool-availability probe — record missing tools up front.
PYFLAKES_OK=0
command -v python3 >/dev/null 2>&1 && python3 -m pyflakes --version >/dev/null 2>&1 && PYFLAKES_OK=1

RUFF_OK=0
command -v python3 >/dev/null 2>&1 && python3 -m ruff --version >/dev/null 2>&1 && RUFF_OK=1

MYPY_OK=0
command -v python3 >/dev/null 2>&1 && python3 -m mypy --version >/dev/null 2>&1 && MYPY_OK=1

PYTEST_OK=0
command -v python3 >/dev/null 2>&1 && python3 -m pytest --version >/dev/null 2>&1 && PYTEST_OK=1

NODE_OK=0
command -v node >/dev/null 2>&1 && NODE_OK=1

GIT_OK=0
command -v git >/dev/null 2>&1 && [ -d "$PROJECT_DIR/.git" ] && GIT_OK=1

echo "============================================"
echo " verify_all.sh — Local selected checks"
echo "============================================"
echo ""
echo "Tool availability: pyflakes=$PYFLAKES_OK ruff=$RUFF_OK mypy=$MYPY_OK"
echo "                   pytest=$PYTEST_OK node=$NODE_OK git_repo=$GIT_OK"
echo ""

# ─── pyflakes ──────────────────────────────────────────────────
echo "[1/9] pyflakes"
if [ "$PYFLAKES_OK" -eq 1 ]; then
    if python3 -m pyflakes "$BACKEND_DIR/app" "$BACKEND_DIR/tests" 2>&1; then
        pass_check "pyflakes — 0 issues"
    else
        fail_check "pyflakes — issues found"
    fi
else
    skip_check "pyflakes — not installed"
fi

# ─── ruff lint ─────────────────────────────────────────────────
echo "[2/9] ruff lint"
if [ "$RUFF_OK" -eq 1 ]; then
    if python3 -m ruff check "$BACKEND_DIR/app" "$BACKEND_DIR/tests" "$PROJECT_DIR/scripts" 2>&1; then
        pass_check "ruff lint — clean"
    else
        fail_check "ruff lint — issues found"
    fi
else
    skip_check "ruff lint — not installed"
fi

# ─── ruff format ───────────────────────────────────────────────
echo "[3/9] ruff format"
if [ "$RUFF_OK" -eq 1 ]; then
    if python3 -m ruff format --check "$BACKEND_DIR/app" "$BACKEND_DIR/tests" "$PROJECT_DIR/scripts" 2>&1; then
        pass_check "ruff format — clean"
    else
        fail_check "ruff format — would reformat"
    fi
else
    skip_check "ruff format — not installed"
fi

# ─── research-shell boundary ───────────────────────────────────
echo "[4/9] research-shell boundary"
if PYTHONPATH="$BACKEND_DIR" python3 "$PROJECT_DIR/scripts/check_research_boundary.py" >/dev/null 2>&1; then
    pass_check "research-shell boundary — clean"
else
    fail_check "research-shell boundary — violations"
    PYTHONPATH="$BACKEND_DIR" python3 "$PROJECT_DIR/scripts/check_research_boundary.py" 2>&1 | head -10
fi

# ─── mypy ──────────────────────────────────────────────────────
echo "[5/9] mypy"
if [ "$MYPY_OK" -eq 1 ]; then
    # Use the mypy exit code directly instead of grepping the
    # trailing "Success" line — the latter breaks when mypy is
    # configured with ``--no-error-summary``, when output is
    # truncated, or when running against a single file. Exit 0
    # from mypy is the canonical "0 errors" signal.
    if python3 -m mypy "$BACKEND_DIR/app" --ignore-missing-imports > /tmp/mypy.out 2>&1; then
        pass_check "mypy — 0 errors"
    else
        fail_check "mypy — errors found"
        grep "error:" /tmp/mypy.out | head -5
    fi
    rm -f /tmp/mypy.out
else
    skip_check "mypy — not installed"
fi

# ─── pytest ────────────────────────────────────────────────────
echo "[6/9] pytest"
if [ "$PYTEST_OK" -eq 1 ]; then
    PYTEST_TMP=$(mktemp)
    # Use ``-k "not profile_alignment_e2e"`` to skip the long
    # end-to-end test by *name match* rather than ``--ignore`` of
    # the file path. ``--ignore`` removes the file from
    # collection entirely, which makes the report claim the file
    # does not exist; ``-k`` keeps the file discoverable and just
    # deselects the slow tests, which is what the sre_quick_check
    # script already does. This also means new e2e tests in that
    # file are skipped by name pattern, not by path glob.
    if PYTHONPATH="$BACKEND_DIR" DATAFORGE_DOTENV_PATH=/dev/null DATAFORGE_STORAGE_BACKEND=sqlite \
        python3 -m pytest "$BACKEND_DIR/tests" \
        -q -o "addopts=" \
        -k "not profile_alignment_e2e" \
        > "$PYTEST_TMP" 2>&1; then
        pass_check "pytest"
    else
        fail_check "pytest — failures"
        tail -3 "$PYTEST_TMP"
        grep -E "FAILED|ERROR" "$PYTEST_TMP" | head -10
    fi
    rm -f "$PYTEST_TMP"
else
    skip_check "pytest — not installed"
fi

# ─── frontend JS ───────────────────────────────────────────────
echo "[7/9] frontend JS validation"
if [ "$NODE_OK" -eq 1 ]; then
    JS_OK=true
    JS_FILES=()
    [ -f "$PROJECT_DIR/frontend/app.js" ] && JS_FILES+=("$PROJECT_DIR/frontend/app.js")
    [ -f "$PROJECT_DIR/frontend/dashboard/dashboard.js" ] && JS_FILES+=("$PROJECT_DIR/frontend/dashboard/dashboard.js")
    if [ ${#JS_FILES[@]} -eq 0 ]; then
        skip_check "frontend JS — no files found"
    else
        for jsfile in "${JS_FILES[@]}"; do
            if ! node -c "$jsfile" 2>/dev/null; then
                JS_OK=false
            fi
        done
        if $JS_OK; then
            pass_check "frontend JS — valid"
        else
            fail_check "frontend JS — invalid"
        fi
    fi
else
    skip_check "frontend JS — node not installed"
fi

# ─── shell scripts ─────────────────────────────────────────────
echo "[8/9] shell scripts"
SH_OK=true
SH_FILES=()
for shfile in "$PROJECT_DIR/scripts"/*.sh; do
    [ -f "$shfile" ] || continue
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
echo "[9/9] git diff --check"
if [ "$GIT_OK" -eq 1 ]; then
    if git -C "$PROJECT_DIR" diff --check 2>&1; then
        pass_check "git diff — clean"
    else
        fail_check "git diff — whitespace issues"
    fi
else
    skip_check "git diff — no .git directory or git not installed"
fi

# ─── Summary ───────────────────────────────────────────────────
echo ""
echo "============================================"
echo " Results: $PASS passed, $FAIL failed, $SKIP skipped"
echo "============================================"

if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
exit 0

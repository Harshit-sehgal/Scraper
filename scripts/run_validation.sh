#!/usr/bin/env bash
# Reproducible validation script for DataForge Scraper.
#
# Runs the baseline gate bundle (compileall, architecture validator,
# research-boundary check, dependency bounds) plus the targeted P0
# test files and the broader backend test suite, all with safe
# defaults that match docs/AGENT_TRUTH.md.
#
# Usage:
#   ./scripts/run_validation.sh                # default
#   ./scripts/run_validation.sh --full         # also run ruff/mypy/pyflakes/bandit/pip-audit/npm
#   ./scripts/run_validation.sh --skip-postgres  # skip Postgres-specific checks
#
# Logs are saved under artifacts/validation/.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

mkdir -p artifacts/validation

if [[ ! -x ".venv/bin/python" ]]; then
  echo "[run_validation] .venv/bin/python not found. Run:"
  echo "    python3.12 -m venv .venv && . .venv/bin/activate && pip install -e '.[dev]' && playwright install chromium"
  exit 2
fi

PYTHON=".venv/bin/python"
export DATAFORGE_DOTENV_PATH=/dev/null
export DATAFORGE_ENV=test
export DATAFORGE_STORAGE_BACKEND=sqlite
export DATAFORGE_API_KEY=user-key
export DATAFORGE_OPERATOR_API_KEY=operator-key
export DATAFORGE_ADMIN_API_KEY=admin-key
export DATAFORGE_SESSION_SECRET=test-session-secret-change-me
export DATAFORGE_ALLOW_INSECURE_DEV_AUTH=false
export DATAFORGE_SKIP_DB_CHECK=true
export PYTHONPATH=backend

RUN_FULL=0
SKIP_POSTGRES=0
for arg in "$@"; do
  case "${arg}" in
    --full) RUN_FULL=1 ;;
    --skip-postgres) SKIP_POSTGRES=1 ;;
  esac
done

TS="$(date -u +%Y-%m-%d)"
LOG_DIR="artifacts/validation"
declare -i FAILS=0

run() {
  local name="$1"; shift
  local log="${LOG_DIR}/run_validation_${name}_${TS}.log"
  echo "── ${name} ──"
  if "$@" 2>&1 | tee "${log}" | tail -5; then
    echo "   pass  → ${log}"
  else
    echo "   FAIL  → ${log}"
    FAILS=$((FAILS + 1))
  fi
}

# 1. Baseline gates
run "compileall" "${PYTHON}" -m compileall -q backend scripts architecture_validator.py
run "architecture" ${PYTHON} architecture_validator.py
run "research_boundary" ${PYTHON} scripts/check_research_boundary.py
run "dep_bounds" ${PYTHON} scripts/validate_dependency_bounds.py

# 2. URL safety + research boundary tests (smoke)
run "url_safety_smoke" \
  ${PYTHON} -m pytest backend/tests/test_url_safety.py backend/tests/test_research_boundary.py -q

# 3. P0 characterization / regression tests
run "p0_auth_tenant" ${PYTHON} -m pytest backend/tests/test_p0_auth_tenant.py -q
run "p0_billing_usage" ${PYTHON} -m pytest backend/tests/test_p0_billing_usage.py -q

# 4. Full backend test suite
run "full_pytest" ${PYTHON} -m pytest backend/tests -q

# 5. Optional Postgres parity
if [[ ${SKIP_POSTGRES} -eq 0 ]]; then
  if command -v docker >/dev/null 2>&1; then
    echo "── postgres_parity (best-effort) ──"
    ${PYTHON} -m pytest --run-postgres -m postgres \
      backend/tests/test_repository_parity.py backend/tests/test_postgres_repository.py -q \
      2>&1 | tee "${LOG_DIR}/run_validation_postgres_parity_${TS}.log" | tail -5 || FAILS=$((FAILS + 1))
  else
    echo "[run_validation] docker not available, skipping postgres parity"
  fi
fi

# 6. Optional wider validation
if [[ ${RUN_FULL} -eq 1 ]]; then
  run "ruff" .venv/bin/ruff check backend scripts
  run "mypy" ${PYTHON} -m mypy backend
  run "pyflakes" .venv/bin/pyflakes backend scripts
  run "bandit" .venv/bin/bandit -r backend -q
  run "pip_audit" .venv/bin/pip-audit
  if command -v npm >/dev/null 2>&1; then
    run "npm_lint_js" npm run lint:js
    run "npm_test" npm run test
  fi
fi

echo
if [[ ${FAILS} -eq 0 ]]; then
  echo "✅ All checks passed. Logs: ${LOG_DIR}/"
  exit 0
else
  echo "❌ ${FAILS} check(s) failed. See ${LOG_DIR}/"
  exit 1
fi

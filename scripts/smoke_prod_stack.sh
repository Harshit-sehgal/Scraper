#!/usr/bin/env bash
# =============================================================================
# DataForge Scraper — Production Docker Smoke Test
# =============================================================================
# Proves the actual production stack boots correctly, not just unit tests.
#
# Usage:
#   python3 scripts/check_prod_env.py --env-file .env   # pre-flight
#   bash scripts/smoke_prod_stack.sh
#
# This script does NOT source .env directly (fragile with special chars).
# Instead it reads values through a tiny Python helper so passwords with
# shell-special characters ($, !, quotes, #) and JSON array values work
# correctly.
#
# Exit codes:
#   0 — All smoke tests passed
#   1 — One or more checks failed
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

# Detect local docker-compose or system command
if [ -f "./bin/docker-compose" ]; then
    DOCKER_COMPOSE="./bin/docker-compose"
elif command -v docker-compose &> /dev/null; then
    DOCKER_COMPOSE="docker-compose"
else
    DOCKER_COMPOSE="docker compose"
fi

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color
PASS="${GREEN}[PASS]${NC}"
FAIL="${RED}[FAIL]${NC}"
INFO="${YELLOW}[INFO]${NC}"

ALL_PASS=true

echo "======================================================================"
echo "  DataForge Production Docker Smoke Test"
echo "======================================================================"
echo ""

# ─── Safe env value reader ────────────────────────────────────────────────
# Read a single env var using Python's dotenv parsing so shell-special
# characters ($, !, `, #, quotes) and JSON array values are handled safely.
_get_env() {
    local key="$1"
    local default="${2:-}"
    python3 -c "
import json, sys
try:
    from dotenv import dotenv_values
    vals = dotenv_values('.env')
except ImportError:
    try:
        from pathlib import Path
        vals = {}
        for line in Path('.env').read_text().splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' in line:
                k, _, v = line.partition('=')
                vals[k.strip()] = v.strip().strip('\"').strip(\"'\")
    except Exception:
        vals = {}
print(vals.get('${key}', '${default}'))
"
}

# ───── Step 0: Pre-flight checks ──────────────────────────────────────────
echo "─── Step 0: Pre-flight checks ────────────────────────────────────────"

if [ ! -f ".env" ]; then
    echo -e "  $FAIL  .env file not found. Create it from .env.example first."
    exit 1
fi
echo -e "  $PASS  .env file exists"

# Read env values safely through Python
DATAFORGE_API_KEY="$(_get_env DATAFORGE_API_KEY)"
DATAFORGE_OPERATOR_API_KEY="$(_get_env DATAFORGE_OPERATOR_API_KEY)"
SMOKE_PORT="$(_get_env PORT 80)"
if [ "${SMOKE_PORT}" = "80" ]; then
    SMOKE_BASE_URL="${SMOKE_BASE_URL:-http://localhost}"
else
    SMOKE_BASE_URL="${SMOKE_BASE_URL:-http://localhost:${SMOKE_PORT}}"
fi
echo -e "  $INFO  Smoke HTTP base URL: $SMOKE_BASE_URL"

if [ -z "${DATAFORGE_OPERATOR_API_KEY:-}" ]; then
    echo -e "  $INFO  DATAFORGE_OPERATOR_API_KEY not set — job creation may fail if ADMIN is required"
    # Fall back to API_KEY for backward compatibility
    DATAFORGE_OPERATOR_API_KEY="$DATAFORGE_API_KEY"
fi

if [ -z "${DATAFORGE_API_KEY:-}" ]; then
    echo -e "  $FAIL  DATAFORGE_API_KEY is not set in .env"
    ALL_PASS=false
else
    echo -e "  $PASS  DATAFORGE_API_KEY is set"
fi

# ───── Step 1: Run production env validator ────────────────────────────────
echo ""
echo "─── Step 1: Production environment validation ────────────────────────"

export DATAFORGE_SKIP_DB_CHECK=true
if python3 scripts/check_prod_env.py --env-file .env; then
    echo -e "  $PASS  check_prod_env.py passed"
else
    echo -e "  $FAIL  check_prod_env.py failed — fix .env before deploying"
    ALL_PASS=false
fi
unset DATAFORGE_SKIP_DB_CHECK

# ───── Step 2: Validate compose config ────────────────────────────────────
echo ""
echo "─── Step 2: Docker Compose config validation ─────────────────────────"

if "$DOCKER_COMPOSE" -f docker-compose.prod.yml config > /dev/null 2>&1; then
    echo -e "  $PASS  docker-compose.prod.yml is valid"
else
    echo -e "  $FAIL  docker-compose.prod.yml has errors"
    ALL_PASS=false
fi

# ───── Step 3: Build without cache ────────────────────────────────────────
echo ""
echo "─── Step 3: Building production images ───────────────────────────────"

if "$DOCKER_COMPOSE" -f docker-compose.prod.yml build --no-cache 2>&1 | tail -5; then
    echo -e "  $PASS  Production images built successfully"
else
    echo -e "  $FAIL  Production image build failed"
    ALL_PASS=false
fi

# ───── Step 4: Start the stack ────────────────────────────────────────────
echo ""
echo "─── Step 4: Starting production stack ────────────────────────────────"

# Enable smoke test bypass specifically for this run
export DATAFORGE_SMOKE_TEST_MODE=true
export DATAFORGE_ALLOWED_INTERNAL_HOSTS=nginx

"$DOCKER_COMPOSE" -f docker-compose.prod.yml up -d 2>&1
echo -e "  $INFO  Waiting for services to start (30s)..."
sleep 30

# Check all containers are running (including monitoring services)
for svc in dataforge worker postgres nginx prometheus grafana; do
    if "$DOCKER_COMPOSE" -f docker-compose.prod.yml ps "$svc" --format json 2>/dev/null | grep -q '"State":"running"'; then
        echo -e "  $PASS  $svc is running"
    else
        echo -e "  $FAIL  $svc is not running"
        "$DOCKER_COMPOSE" -f docker-compose.prod.yml logs "$svc" --tail=20 2>&1 || true
        ALL_PASS=false
    fi
done

# ───── Step 5: Health checks ──────────────────────────────────────────────
echo ""
echo "─── Step 5: Health and readiness probes ──────────────────────────────"

# /health — liveness
HEALTH=$(curl -s "$SMOKE_BASE_URL/health" 2>/dev/null || echo '{"status":"unreachable"}')
if echo "$HEALTH" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d.get('status')=='ok'" 2>/dev/null; then
    echo -e "  $PASS  /health returns ok"
else
    echo -e "  $FAIL  /health returned: $HEALTH"
    ALL_PASS=false
fi

# /ready — readiness: in production the endpoint returns only {"status":"ready"}
# to avoid leaking backend/schema details. We check only status=='ready' here.
# Backend verification is done via the authenticated /api/system/storage/status.
READY=$(curl -s "$SMOKE_BASE_URL/ready" 2>/dev/null || echo '{"status":"unreachable"}')
if echo "$READY" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d.get('status')=='ready'" 2>/dev/null; then
    echo -e "  $PASS  /ready returns ready"
else
    echo -e "  $FAIL  /ready returned: $READY"
    ALL_PASS=false
fi

# ───── Step 6: API authenticated endpoints ────────────────────────────────
echo ""
echo "─── Step 6: API authenticated endpoints ──────────────────────────────"

STATUS=$(curl -s -H "X-API-Key: $DATAFORGE_API_KEY" "$SMOKE_BASE_URL/api/system/status" 2>/dev/null || echo '{"status":"unreachable"}')
if echo "$STATUS" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d.get('status')=='online'; assert d.get('backend')=='postgres'" 2>/dev/null; then
    echo -e "  $PASS  /api/system/status returns online+postgres"
else
    echo -e "  $FAIL  /api/system/status returned: $STATUS"
    ALL_PASS=false
fi

STORAGE=$(curl -s -H "X-API-Key: $DATAFORGE_API_KEY" "$SMOKE_BASE_URL/api/system/storage/status" 2>/dev/null || echo '{"backend":"unreachable"}')
if echo "$STORAGE" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d.get('backend')=='postgres'; assert d.get('ok')==True" 2>/dev/null; then
    echo -e "  $PASS  /api/system/storage/status returns postgres+ok"
else
    echo -e "  $FAIL  /api/system/storage/status returned: $STORAGE"
    ALL_PASS=false
fi

# ───── Step 7: Create a local deterministic smoke page served by nginx ────
echo ""
echo "─── Step 7: Create local smoke test page ─────────────────────────────"

if [ -f "frontend/smoke/records.html" ]; then
    echo -e "  $PASS  Local smoke page exists at frontend/smoke/records.html"
else
    echo -e "  $FAIL  Local smoke page not found"
    ALL_PASS=false
fi

# ───── Step 8: Create a job via API (targeting local smoke page) ──────────
echo ""
echo "─── Step 8: Create a job against local smoke page ────────────────────"

JOB_RESPONSE=$(curl -s -X POST \
    -H "X-API-Key: $DATAFORGE_OPERATOR_API_KEY" \
    -H "Content-Type: application/json" \
    -d '{"name":"Smoke Test Job","mode":"manual","urls":["http://nginx/smoke/records.html"],"schema_fields":[{"name":"name","field_type":"string","required":true},{"name":"email","field_type":"email","required":true},{"name":"role","field_type":"string","required":true},{"name":"team","field_type":"string","required":true}]}' \
    "$SMOKE_BASE_URL/api/jobs" 2>/dev/null || echo '{"error":"unreachable"}')

JOB_ID=$(echo "$JOB_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('job_id',''))" 2>/dev/null || echo "")
if [ -n "$JOB_ID" ]; then
    echo -e "  $PASS  Created job: $JOB_ID"
else
    echo -e "  $FAIL  Failed to create job. Response: $JOB_RESPONSE"
    ALL_PASS=false
fi

# ───── Step 9: Verify job lifecycle ───────────────────────────────────────
echo ""
echo "─── Step 9: Verify job lifecycle ────────────────────────────────────"

if [ -n "$JOB_ID" ]; then
    # Poll for up to 90 seconds for the job to reach a terminal status
    echo -e "  $INFO  Waiting for worker to process the job (polling up to 90s)..."
    TERMINAL_STATUSES="^(completed|degraded|empty_result|failed|canceled)$"
    SUCCESS_STATUSES="^(completed|degraded)$"
    JOB_REACHED_TERMINAL=false
    JOB_SCRAPE_SUCCEEDED=false
    POLL_DEADLINE=$((SECONDS + 90))
    while [ $SECONDS -lt $POLL_DEADLINE ]; do
        JOB_STATUS=$(curl -s -H "X-API-Key: $DATAFORGE_API_KEY" \
            "$SMOKE_BASE_URL/api/jobs/$JOB_ID" 2>/dev/null || echo '{"status":"unreachable"}')
        STATUS_VALUE=$(echo "$JOB_STATUS" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','unknown'))" 2>/dev/null || echo "unknown")

        if echo "$STATUS_VALUE" | grep -qE "$TERMINAL_STATUSES"; then
            echo -e "  $PASS  Job reached terminal status: $STATUS_VALUE"
            JOB_REACHED_TERMINAL=true
            if echo "$STATUS_VALUE" | grep -qE "$SUCCESS_STATUSES"; then
                JOB_SCRAPE_SUCCEEDED=true
            fi
            break
        fi
        echo -e "  $INFO  Job status: $STATUS_VALUE — still waiting..."
        sleep 5
    done

    if [ "$JOB_REACHED_TERMINAL" = false ]; then
        echo -e "  $FAIL  Job did not reach terminal status within 90 seconds (last status: ${STATUS_VALUE:-unknown})"
        ALL_PASS=false
    elif [ "$JOB_SCRAPE_SUCCEEDED" = false ]; then
        echo -e "  $FAIL  Worker processed the job but scraping did not succeed with positive results (status: ${STATUS_VALUE:-unknown}) — expected completed or degraded"
        ALL_PASS=false
    else
        # Assert expected record count from local smoke HTML page
        RESULTS_RESPONSE=$(curl -s -H "X-API-Key: $DATAFORGE_API_KEY" \
            "$SMOKE_BASE_URL/api/jobs/$JOB_ID/results" 2>/dev/null || echo '{"results":[]}')
        RECORD_COUNT=$(echo "$RESULTS_RESPONSE" | python3 -c "import sys,json; print(len(json.load(sys.stdin).get('results', [])))" 2>/dev/null || echo "0")

        if [ "$RECORD_COUNT" -ge 2 ]; then
            echo -e "  $PASS  Extraction works end-to-end! Extracted $RECORD_COUNT records (expected >= 2)"
        else
            echo -e "  $FAIL  Extraction returned zero or too few records ($RECORD_COUNT expected >= 2). Response: $RESULTS_RESPONSE"
            ALL_PASS=false
        fi
    fi
fi

# ───── Step 9: Check worker logs ──────────────────────────────────────────
echo ""
echo "─── Step 9: Worker logs (last 20 lines) ──────────────────────────────"

"$DOCKER_COMPOSE" -f docker-compose.prod.yml logs worker --tail=20 2>&1 || true

# ───── Summary ────────────────────────────────────────────────────────────
echo ""
echo "======================================================================"
if [ "$ALL_PASS" = true ]; then
    echo -e "  ${GREEN}ALL SMOKE TESTS PASSED${NC}"
    echo ""
    echo "  Production stack is healthy:"
    echo "    - nginx reverse proxy: OK"
    echo "    - FastAPI (dataforge): OK"
    echo "    - Worker queue: OK"
    echo "    - PostgreSQL: OK"
    echo "    - Prometheus: OK"
    echo "    - Grafana: OK"
    echo "======================================================================"
    exit 0
else
    echo -e "  ${RED}ONE OR MORE SMOKE TESTS FAILED${NC}"
    echo "  Check the logs above and fix before deploying."
    echo "======================================================================"
    exit 1
fi

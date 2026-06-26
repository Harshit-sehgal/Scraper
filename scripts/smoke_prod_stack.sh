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
    DOCKER_COMPOSE=("./bin/docker-compose")
elif command -v docker-compose &> /dev/null; then
    DOCKER_COMPOSE=("docker-compose")
else
    DOCKER_COMPOSE=("docker" "compose")
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
SMOKE_TMP_DIR=""

# Ensure the prod stack is torn down on script exit — success OR failure.
# Without this, a failed smoke test leaves containers running and the
# next developer/CI run collides with a half-up stack.
cleanup() {
    "${DOCKER_COMPOSE[@]}" -f docker-compose.prod.yml down || true
    if [ -n "${SMOKE_TMP_DIR:-}" ]; then
        rm -rf "$SMOKE_TMP_DIR"
    fi
}
trap cleanup EXIT

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
from pathlib import Path
env_path = Path('.env')
try:
    from dotenv import dotenv_values
    vals = dotenv_values(env_path)
except ImportError:
    try:
        vals = {}
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' in line:
                k, _, v = line.partition('=')
                vals[k.strip()] = v.strip().strip('\"').strip(\"'\")
    except Exception:
        vals = {}
value = vals.get('${key}', '') or ''
file_ref = vals.get('${key}_FILE', '') or ''
if not value and file_ref:
    secret_path = Path(file_ref)
    if not secret_path.is_absolute():
        secret_path = env_path.parent / secret_path
    try:
        value = secret_path.read_text().strip()
    except OSError:
        value = ''
print(value or '${default}')
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
SMOKE_HTTP_PORT="${HTTP_PORT:-$(_get_env HTTP_PORT 80)}"
SMOKE_HTTPS_PORT="${HTTPS_PORT:-$(_get_env HTTPS_PORT 443)}"
if [ "${SMOKE_HTTPS_PORT}" = "443" ]; then
    SMOKE_BASE_URL="${SMOKE_BASE_URL:-https://localhost}"
else
    SMOKE_BASE_URL="${SMOKE_BASE_URL:-https://localhost:${SMOKE_HTTPS_PORT}}"
fi

DATAFORGE_NGINX_SSL_DIR="${DATAFORGE_NGINX_SSL_DIR:-$(_get_env DATAFORGE_NGINX_SSL_DIR)}"
DATAFORGE_CERTBOT_WEBROOT="${DATAFORGE_CERTBOT_WEBROOT:-$(_get_env DATAFORGE_CERTBOT_WEBROOT)}"
SMOKE_CURL_ARGS=()

if [ -z "${DATAFORGE_NGINX_SSL_DIR:-}" ] \
    || [ ! -f "$DATAFORGE_NGINX_SSL_DIR/fullchain.pem" ] \
    || [ ! -f "$DATAFORGE_NGINX_SSL_DIR/privkey.pem" ]; then
    if ! command -v openssl > /dev/null 2>&1; then
        echo -e "  $FAIL  openssl is required to generate the temporary localhost TLS certificate"
        ALL_PASS=false
    else
        if [ -n "${DATAFORGE_NGINX_SSL_DIR:-}" ]; then
            echo -e "  $INFO  Configured TLS directory is missing fullchain.pem or privkey.pem; using a temporary smoke certificate"
        fi
        SMOKE_TMP_DIR="$(mktemp -d)"
        DATAFORGE_NGINX_SSL_DIR="$SMOKE_TMP_DIR/nginx-ssl"
        DATAFORGE_CERTBOT_WEBROOT="${DATAFORGE_CERTBOT_WEBROOT:-$SMOKE_TMP_DIR/certbot-webroot}"
        mkdir -p "$DATAFORGE_NGINX_SSL_DIR" "$DATAFORGE_CERTBOT_WEBROOT"
        if ! openssl req -x509 -nodes -days 1 -newkey rsa:2048 \
            -keyout "$DATAFORGE_NGINX_SSL_DIR/privkey.pem" \
            -out "$DATAFORGE_NGINX_SSL_DIR/fullchain.pem" \
            -subj "/CN=localhost" \
            -addext "subjectAltName=DNS:localhost,IP:127.0.0.1" \
            > /dev/null 2>&1; then
            if ! openssl req -x509 -nodes -days 1 -newkey rsa:2048 \
                -keyout "$DATAFORGE_NGINX_SSL_DIR/privkey.pem" \
                -out "$DATAFORGE_NGINX_SSL_DIR/fullchain.pem" \
                -subj "/CN=localhost" \
                > /dev/null 2>&1; then
                echo -e "  $FAIL  failed to generate the temporary localhost TLS certificate"
                ALL_PASS=false
            fi
        fi
        if [ -f "$DATAFORGE_NGINX_SSL_DIR/fullchain.pem" ] && [ -f "$DATAFORGE_NGINX_SSL_DIR/privkey.pem" ]; then
            SMOKE_CURL_INSECURE="${SMOKE_CURL_INSECURE:-true}"
            echo -e "  $INFO  Generated temporary localhost TLS certificate for nginx"
        fi
    fi
else
    SMOKE_CURL_INSECURE="${SMOKE_CURL_INSECURE:-false}"
fi

if [ -n "${DATAFORGE_NGINX_SSL_DIR:-}" ]; then
    export DATAFORGE_NGINX_SSL_DIR
fi
if [ -n "${DATAFORGE_CERTBOT_WEBROOT:-}" ]; then
    export DATAFORGE_CERTBOT_WEBROOT
fi
if [ "${SMOKE_CURL_INSECURE:-false}" = "true" ]; then
    SMOKE_CURL_ARGS=(-k)
fi
export HTTP_PORT="$SMOKE_HTTP_PORT"
export HTTPS_PORT="$SMOKE_HTTPS_PORT"
echo -e "  $INFO  Smoke HTTPS base URL: $SMOKE_BASE_URL"

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

if "${DOCKER_COMPOSE[@]}" -f docker-compose.prod.yml config > /dev/null 2>&1; then
    echo -e "  $PASS  docker-compose.prod.yml is valid"
else
    echo -e "  $FAIL  docker-compose.prod.yml has errors"
    ALL_PASS=false
fi

# ───── Step 3: Build without cache ────────────────────────────────────────
echo ""
echo "─── Step 3: Building production images ───────────────────────────────"

if "${DOCKER_COMPOSE[@]}" -f docker-compose.prod.yml build --no-cache 2>&1 | tail -5; then
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

"${DOCKER_COMPOSE[@]}" -f docker-compose.prod.yml up -d 2>&1
echo -e "  $INFO  Waiting for services to start (30s)..."
sleep 30

# Check all containers are running (including monitoring services)
for svc in dataforge worker postgres nginx prometheus grafana alertmanager; do
    if "${DOCKER_COMPOSE[@]}" -f docker-compose.prod.yml ps "$svc" --format json 2>/dev/null | grep -q '"State":"running"'; then
        echo -e "  $PASS  $svc is running"
    else
        echo -e "  $FAIL  $svc is not running"
        "${DOCKER_COMPOSE[@]}" -f docker-compose.prod.yml logs "$svc" --tail=20 2>&1 || true
        ALL_PASS=false
    fi
done

# ───── Step 5: Health checks ──────────────────────────────────────────────
echo ""
echo "─── Step 5: Health and readiness probes ──────────────────────────────"

# /health — liveness
HEALTH=$(curl -s "${SMOKE_CURL_ARGS[@]}" "$SMOKE_BASE_URL/health" 2>/dev/null || echo '{"status":"unreachable"}')
if echo "$HEALTH" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d.get('status')=='ok'" 2>/dev/null; then
    echo -e "  $PASS  /health returns ok"
else
    echo -e "  $FAIL  /health returned: $HEALTH"
    ALL_PASS=false
fi

# /ready — readiness: in production the endpoint returns only {"status":"ready"}
# to avoid leaking backend/schema details. We check only status=='ready' here.
# Backend verification is done via the authenticated /api/system/storage/status.
READY=$(curl -s "${SMOKE_CURL_ARGS[@]}" "$SMOKE_BASE_URL/ready" 2>/dev/null || echo '{"status":"unreachable"}')
if echo "$READY" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d.get('status')=='ready'" 2>/dev/null; then
    echo -e "  $PASS  /ready returns ready"
else
    echo -e "  $FAIL  /ready returned: $READY"
    ALL_PASS=false
fi

# ───── Step 6: API authenticated endpoints ────────────────────────────────
echo ""
echo "─── Step 6: API authenticated endpoints ──────────────────────────────"

STATUS=$(curl -s "${SMOKE_CURL_ARGS[@]}" -H "X-API-Key: $DATAFORGE_API_KEY" "$SMOKE_BASE_URL/api/system/status" 2>/dev/null || echo '{"status":"unreachable"}')
if echo "$STATUS" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d.get('status')=='online'; assert d.get('backend')=='postgres'" 2>/dev/null; then
    echo -e "  $PASS  /api/system/status returns online+postgres"
else
    echo -e "  $FAIL  /api/system/status returned: $STATUS"
    ALL_PASS=false
fi

STORAGE=$(curl -s "${SMOKE_CURL_ARGS[@]}" -H "X-API-Key: $DATAFORGE_API_KEY" "$SMOKE_BASE_URL/api/system/storage/status" 2>/dev/null || echo '{"backend":"unreachable"}')
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

JOB_RESPONSE=$(curl -s "${SMOKE_CURL_ARGS[@]}" -X POST \
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
        JOB_STATUS=$(curl -s "${SMOKE_CURL_ARGS[@]}" -H "X-API-Key: $DATAFORGE_API_KEY" \
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
        RESULTS_RESPONSE=$(curl -s "${SMOKE_CURL_ARGS[@]}" -H "X-API-Key: $DATAFORGE_API_KEY" \
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

# ───── Step 10: Monitoring runtime checks ─────────────────────────────────
echo ""
echo "─── Step 10: Monitoring runtime checks ───────────────────────────────"

_internal_get() {
    local url="$1"
    "${DOCKER_COMPOSE[@]}" -f docker-compose.prod.yml exec -T dataforge python3 - "$url" <<'PY'
import json
import sys
import urllib.request

url = sys.argv[1]
try:
    with urllib.request.urlopen(url, timeout=10) as resp:
        body = resp.read(500_000).decode("utf-8", errors="replace")
        print(json.dumps({"status": resp.status, "body": body}))
except Exception as exc:
    print(json.dumps({"status": 0, "body": str(exc)}))
    raise SystemExit(1)
PY
}

PROM_READY=$(_internal_get "http://prometheus:9090/-/ready" 2>/dev/null || true)
if echo "$PROM_READY" | python3 -c "import json,sys; d=json.load(sys.stdin); assert d.get('status') == 200" 2>/dev/null; then
    echo -e "  $PASS  Prometheus readiness endpoint is reachable"
else
    echo -e "  $FAIL  Prometheus readiness check failed: $PROM_READY"
    ALL_PASS=false
fi

PROM_RULES=$(_internal_get "http://prometheus:9090/api/v1/rules" 2>/dev/null || true)
if echo "$PROM_RULES" | python3 -c "import json,sys; d=json.load(sys.stdin); body=json.loads(d['body']); rules=sum(len(g.get('rules', [])) for g in body.get('data', {}).get('groups', [])); assert d.get('status') == 200 and body.get('status') == 'success' and rules >= 10" 2>/dev/null; then
    echo -e "  $PASS  Prometheus alert rules are loaded"
else
    echo -e "  $FAIL  Prometheus alert rules check failed: $PROM_RULES"
    ALL_PASS=false
fi

GRAFANA_HEALTH=$(_internal_get "http://grafana:3000/api/health" 2>/dev/null || true)
if echo "$GRAFANA_HEALTH" | python3 -c "import json,sys; d=json.load(sys.stdin); body=json.loads(d['body']); assert d.get('status') == 200 and body.get('database') == 'ok'" 2>/dev/null; then
    echo -e "  $PASS  Grafana health endpoint reports database ok"
else
    echo -e "  $FAIL  Grafana health check failed: $GRAFANA_HEALTH"
    ALL_PASS=false
fi

ALERT_READY=$(_internal_get "http://alertmanager:9093/-/ready" 2>/dev/null || true)
if echo "$ALERT_READY" | python3 -c "import json,sys; d=json.load(sys.stdin); assert d.get('status') == 200" 2>/dev/null; then
    echo -e "  $PASS  Alertmanager readiness endpoint is reachable"
else
    echo -e "  $FAIL  Alertmanager readiness check failed: $ALERT_READY"
    ALL_PASS=false
fi

# F-MON-001: Fail-closed check that at least one notification channel is wired.
# Alertmanager v0.27+ silently drops alerts when both `smtp_smarthost`
# and `slack_api_url` are empty. Operators can read "Alertmanager alerts
# firing" in Prometheus UI and conclude the pipeline works, but no
# human ever receives a page. Refuse to ship a deploy that lacks BOTH
# channels: read the env files the smoke stack is built from.
if [ -f ".env.production" ]; then
    ENV_FILE=".env.production"
elif [ -f ".env" ]; then
    ENV_FILE=".env"
else
    ENV_FILE=""
fi

if [ -z "$ENV_FILE" ]; then
    echo -e "  $FAIL  Cannot assert notification channel — no .env.production or .env file present"
    ALL_PASS=false
else
    SMTP_HOST=$(grep -E '^[[:space:]]*ALERTMANAGER_SMTP_HOST[[:space:]]*=' "$ENV_FILE" | tail -1 | cut -d= -f2- | tr -d '[:space:]' || true)
    SLACK_URL=$(grep -E '^[[:space:]]*ALERTMANAGER_SLACK_WEBHOOK_URL[[:space:]]*=' "$ENV_FILE" | tail -1 | cut -d= -f2- | tr -d '[:space:]' || true)
    if [ -z "$SMTP_HOST" ] && [ -z "$SLACK_URL" ]; then
        echo -e "  $FAIL  No alerting channel configured. Set ALERTMANAGER_SMTP_HOST or ALERTMANAGER_SLACK_WEBHOOK_URL in $ENV_FILE before deploying."
        ALL_PASS=false
    else
        STATUS_PHRASES=""
        if [ -n "$SMTP_HOST" ]; then STATUS_PHRASES="${STATUS_PHRASES}smtp=$SMTP_HOST "; fi
        if [ -n "$SLACK_URL" ]; then STATUS_PHRASES="${STATUS_PHRASES}slack=<redacted> "; fi
        echo -e "  $PASS  Alerting channel(s) configured: ${STATUS_PHRASES% }"
    fi
fi

# Drill a synthetic alert through Alertmanager. The drill proves the
# alertmanager daemon accepted the alert (POST returns 200/202) and that
# the `/api/v2/alerts` endpoint sees it — useful as a regression
# sentinel for misconfigured `web.external-url` and broken routing.
# Full delivery confirmation requires the operator to attach
# `--notification-evidence` to a follow-up run-in-prod call; we
# deliberately do NOT enable `--require-notification-evidence` in this
# smoke so that CI can run the gate without a real mailbox.
DRILL_EXEC_ARGS=(-T)
DRILL_SCRIPT_ARGS=(
    --url http://alertmanager:9093 \
    --alertname "dataforge.smoke.delivery.drill" \
    --severity info \
    --drill-id "smoke-$(date +%s)" \
    --timeout 5 \
    --poll-interval 1 \
    --json
)
SLACK_BOT_TOKEN_VALUE="${SLACK_BOT_TOKEN:-}"
SLACK_CHANNEL_ID_VALUE="${ALERTMANAGER_SLACK_CHANNEL_ID:-}"
if [ -n "${ENV_FILE:-}" ]; then
    if [ -z "$SLACK_BOT_TOKEN_VALUE" ]; then
        SLACK_BOT_TOKEN_VALUE=$(grep -E '^[[:space:]]*SLACK_BOT_TOKEN[[:space:]]*=' "$ENV_FILE" | tail -1 | cut -d= -f2- | tr -d '[:space:]' || true)
    fi
    if [ -z "$SLACK_CHANNEL_ID_VALUE" ]; then
        SLACK_CHANNEL_ID_VALUE=$(grep -E '^[[:space:]]*ALERTMANAGER_SLACK_CHANNEL_ID[[:space:]]*=' "$ENV_FILE" | tail -1 | cut -d= -f2- | tr -d '[:space:]' || true)
    fi
fi
if [ -n "${SLACK_URL:-}" ] && { [ -z "$SLACK_BOT_TOKEN_VALUE" ] || [ -z "$SLACK_CHANNEL_ID_VALUE" ]; }; then
    echo -e "  $FAIL  Slack alerting is configured, but SLACK_BOT_TOKEN or ALERTMANAGER_SLACK_CHANNEL_ID is missing; cannot verify channel reachability."
    ALL_PASS=false
fi
if [ -n "$SLACK_BOT_TOKEN_VALUE" ] && [ -n "$SLACK_CHANNEL_ID_VALUE" ]; then
    DRILL_EXEC_ARGS+=(-e "SLACK_BOT_TOKEN=$SLACK_BOT_TOKEN_VALUE" -e "ALERTMANAGER_SLACK_CHANNEL_ID=$SLACK_CHANNEL_ID_VALUE")
    DRILL_SCRIPT_ARGS+=(--channel-assert-reachable)
    echo -e "  $INFO  Slack channel reachability assertion enabled for alert drill"
fi
DRILL_OUTPUT=$("${DOCKER_COMPOSE[@]}" -f docker-compose.prod.yml exec "${DRILL_EXEC_ARGS[@]}" dataforge python3 /app/scripts/run_alert_delivery_drill.py "${DRILL_SCRIPT_ARGS[@]}" 2>&1 || true)
if echo "$DRILL_OUTPUT" | python3 -c "import json,sys; d=json.loads(sys.stdin.read()); assert d.get('ready_status_code') == 200 and d.get('post_status_code') in (200, 202)" 2>/dev/null; then
    echo -e "  $PASS  Alertmanager delivery drill accepted (ready=200 POST=accepted)"
else
    echo -e "  $FAIL  Alertmanager delivery drill failed — drill output:"
    echo "$DRILL_OUTPUT" | sed 's/^/    /'
    ALL_PASS=false
fi

# ───── Step 11: Check worker logs ──────────────────────────────────────────
echo ""
echo "─── Step 11: Worker logs (last 20 lines) ──────────────────────────────"

"${DOCKER_COMPOSE[@]}" -f docker-compose.prod.yml logs worker --tail=20 2>&1 || true

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
    echo "    - Alertmanager: OK"
    echo "======================================================================"
    exit 0
else
    echo -e "  ${RED}ONE OR MORE SMOKE TESTS FAILED${NC}"
    echo "  Check the logs above and fix before deploying."
    echo "======================================================================"
    exit 1
fi

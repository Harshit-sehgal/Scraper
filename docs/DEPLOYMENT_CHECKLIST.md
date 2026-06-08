# Deployment Checklist

**Last updated:** 2026-06-08
**Status:** Pre-production candidate validation steps

Use this checklist to validate DataForge Scraper in your target environment before public production deployment.

---

## Phase 1: Secrets & Configuration (Week 0, before any infrastructure)

**Timeline:** 1–2 hours
**Owner:** Security/DevOps
**Risk:** If skipped, placeholder secrets will be deployed to production

### Step 1.1: Generate Production Secrets

```bash
# Generate outside source control, on a secure admin machine
python3 scripts/generate_prod_env.py --output /tmp/env.production.secure

# Review generated values
cat /tmp/env.production.secure

# Copy to target infrastructure (secure method: encrypted channel, not git)
# Example: scp or cloud secret manager
```

**Verification:**
```bash
env -i PATH="$PATH" PYTHONPATH=backend DATAFORGE_SKIP_DB_CHECK=true \
python3 scripts/check_prod_env.py --env-file /path/to/.env.production

# Expected output: All checks PASS
```

**Evidence to save:** Screenshot of check_prod_env.py passing all validation rules.

### Step 1.2: Set Environment Variables

```bash
# On target host, set ONLY these:
export DATAFORGE_ENV=production
export DATAFORGE_ENV_FILE=/path/to/.env.production
export DATAFORGE_LOG_DIR=/var/log/dataforge
export DATAFORGE_DATA_DIR=/var/lib/dataforge
export DATAFORGE_STATE_FILE=/var/lib/dataforge/state.json
export DATAFORGE_BACKUP_DIR=/var/lib/dataforge/backups
```

**Verification:** `echo $DATAFORGE_ENV` must return `production`

---

## Phase 2: Infrastructure Setup (Week 0–1)

**Timeline:** 4–8 hours
**Owner:** DevOps/SRE
**Risk:** If skipped, stack won't start or will be exposed

### Step 2.1: TLS Certificate

```bash
# Option A: Let's Encrypt (recommended)
sudo certbot certonly --standalone -d your-domain.com

# Option B: Cloud provider (AWS ACM, GCP, Azure)
# Use provider's console to issue certificate

# Option C: Self-signed (testing only, not for production)
openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -days 365
```

**Verification:** Certificate is valid for your domain and not self-signed

### Step 2.2: Docker Registry (if using private registry)

```bash
# Log into your registry
docker login your-registry.com

# Build and push image
docker build -f Dockerfile -t your-registry.com/dataforge:latest .
docker push your-registry.com/dataforge:latest
```

**Verification:** `docker pull your-registry.com/dataforge:latest` succeeds

### Step 2.3: Database Setup (Postgres)

**If using managed Postgres (RDS, Cloud SQL, etc.):**
```bash
# Create database and user
createdb -h your-postgres-host -U admin dataforge_prod
psql -h your-postgres-host -U admin -d dataforge_prod -f backend/init-db/init.sql

# Verify connectivity
psql -h your-postgres-host -U dataforge -d dataforge_prod -c "SELECT 1"
```

**If using Docker Compose (local/staging only):**
```bash
docker run -d \
  --name dataforge-postgres \
  -e POSTGRES_DB=dataforge_prod \
  -e POSTGRES_USER=dataforge \
  -e POSTGRES_PASSWORD=$(grep DATAFORGE_DB_PASSWORD .env.production | cut -d= -f2) \
  -v postgres-data:/var/lib/postgresql/data \
  postgres:15-alpine
```

**Verification:**
```bash
# Connection string in .env.production should work
DATAFORGE_DATABASE_URL=postgresql://dataforge:password@host:5432/dataforge_prod
psql "$DATAFORGE_DATABASE_URL" -c "SELECT 1"
```

### Step 2.4: Reverse Proxy (Nginx)

```bash
# Copy Nginx config to target
sudo cp nginx.conf /etc/nginx/sites-available/dataforge

# Update server name and certificate paths in config
sudo sed -i 's/yourdomain.com/your-actual-domain.com/g' /etc/nginx/sites-available/dataforge
sudo sed -i 's|/path/to/cert.pem|/etc/letsencrypt/live/your-domain.com/fullchain.pem|g' /etc/nginx/sites-available/dataforge
sudo sed -i 's|/path/to/key.pem|/etc/letsencrypt/live/your-domain.com/privkey.pem|g' /etc/nginx/sites-available/dataforge

# Enable site
sudo ln -s /etc/nginx/sites-available/dataforge /etc/nginx/sites-enabled/dataforge

# Test config
sudo nginx -t

# Reload
sudo systemctl reload nginx
```

**Verification:**
```bash
curl -i https://your-domain.com/health
# Expected: 200 OK
```

### Step 2.5: Monitoring Stack (Prometheus + Grafana)

```bash
# Copy configs
sudo mkdir -p /etc/prometheus /var/lib/prometheus
sudo cp prometheus.yml /etc/prometheus/
sudo cp prometheus_alerts.yml /etc/prometheus/

# Start Prometheus
docker run -d \
  --name dataforge-prometheus \
  -v /etc/prometheus:/etc/prometheus \
  -v prometheus-data:/prometheus \
  -p 9090:9090 \
  prom/prometheus:latest

# Start Grafana
docker run -d \
  --name dataforge-grafana \
  -e GF_SECURITY_ADMIN_PASSWORD=$(grep GRAFANA_PASSWORD .env.production | cut -d= -f2) \
  -v grafana-data:/var/lib/grafana \
  -p 3000:3000 \
  grafana/grafana:latest

# Import provisioning
docker cp grafana/dashboards dataforge-grafana:/etc/grafana/provisioning/
docker cp grafana/datasources dataforge-grafana:/etc/grafana/provisioning/
docker exec dataforge-grafana grafana-cli admin reset-admin-password <new-password>
```

**Verification:**
```bash
curl http://localhost:9090/api/v1/status/config | jq . | head -20
# Expected: Prometheus config loads successfully

curl http://localhost:3000/api/health
# Expected: database is ok
```

---

## Phase 3: Application Startup (Week 1)

**Timeline:** 1–2 hours
**Owner:** DevOps/Backend
**Risk:** If skipped, API won't serve requests

### Step 3.1: Build & Deploy Image

```bash
# Build in target environment
cd /path/to/dataforge-repo
docker build -f Dockerfile \
  --build-arg PYTHON_VERSION=3.12 \
  -t dataforge:prod-$(date +%Y%m%d-%H%M%S) .

# Tag as latest
docker tag dataforge:prod-* dataforge:latest
```

**Verification:** `docker images | grep dataforge` shows image with size ~500MB

### Step 3.2: Start API Container

```bash
docker run -d \
  --name dataforge-api \
  --env-file .env.production \
  -e PYTHONUNBUFFERED=1 \
  -v dataforge-data:/app/backend/data \
  -p 8000:8000 \
  dataforge:latest \
  /bin/bash -c "cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8000"

# Check logs
docker logs -f dataforge-api
```

**Verification:**
```bash
curl -i http://localhost:8000/health
# Expected: 200 OK with {"status": "ok"}

curl -i http://localhost:8000/ready
# Expected: 200 OK with {"status": "ready"}
```

### Step 3.3: Start Worker Container

```bash
docker run -d \
  --name dataforge-worker \
  --env-file .env.production \
  -e PYTHONUNBUFFERED=1 \
  -v dataforge-data:/app/backend/data \
  dataforge:latest \
  /bin/bash -c "cd backend && python3 scripts/run_worker.py"

# Check logs
docker logs -f dataforge-worker
```

**Verification:**
```bash
docker exec dataforge-worker ps aux | grep run_worker
# Expected: Worker process is running

# In a few seconds:
curl -i http://localhost:8000/diagnostics
# Expected: Worker status is "healthy" or "active"
```

---

## Phase 4: Route & Security Verification (Week 1)

**Timeline:** 2–3 hours
**Owner:** Security/QA
**Risk:** If skipped, public routes may leak docs/metrics

### Step 4.1: Route Exposure Check

```bash
# Through Nginx (real ingress)
curl -i https://your-domain.com/health
# Expected: 200 OK

curl -i https://your-domain.com/ready
# Expected: 200 OK

curl -i https://your-domain.com/docs
# Expected: 404 (docs disabled in production)

curl -i https://your-domain.com/redoc
# Expected: 404

curl -i https://your-domain.com/openapi.json
# Expected: 404

curl -i https://your-domain.com/metrics
# Expected: 404 (or 401 if token-protected)

curl -i https://your-domain.com/app/
# Expected: 200 (static dashboard, internal-only)
```

**Evidence to save:** Screenshot showing `/docs` and `/metrics` return 404

### Step 4.2: CORS Validation

```bash
# Test with allowed origin
curl -i -H "Origin: https://your-frontend.com" \
  https://your-domain.com/api/jobs

# Expected: access-control-allow-origin: https://your-frontend.com

# Test with disallowed origin
curl -i -H "Origin: https://evil.example.com" \
  https://your-domain.com/api/jobs

# Expected: no access-control-allow-origin header
```

**Evidence to save:** Screenshot showing CORS enforcement

### Step 4.3: CSP & Security Headers

```bash
curl -i https://your-domain.com/ | grep -E "content-security-policy|x-frame|x-content-type|strict-transport"

# Expected output:
# content-security-policy: default-src 'self'; script-src 'self' 'unsafe-inline'; ...
# x-frame-options: DENY
# x-content-type-options: nosniff
# strict-transport-security: max-age=31536000
```

**Evidence to save:** Full curl response headers

### Step 4.4: Auth & API Key

```bash
# Create a test API key (or use generated one)
TEST_KEY="test-key-from-check-prod-env"

# Test with valid key
curl -i -H "X-API-Key: $TEST_KEY" https://your-domain.com/api/jobs
# Expected: 200 OK (empty job list)

# Test without key
curl -i https://your-domain.com/api/jobs
# Expected: 401 Unauthorized (or 403 Forbidden)
```

**Evidence to save:** Screenshot showing auth enforcement

---

## Phase 5: Operational Validation (Week 1–2)

**Timeline:** 4–6 hours across multiple days
**Owner:** QA/SRE
**Risk:** If skipped, failures in production will be unmanaged

### Step 5.1: Single-Job Smoke Test

```bash
# Create a simple test job
curl -X POST https://your-domain.com/api/jobs \
  -H "X-API-Key: $TEST_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://books.toscrape.com",
    "extraction_mode": "manual",
    "schema": {
      "title": "string",
      "price": "string"
    }
  }'

# Expected: 201 Created with job_id

# Poll for completion (max 5 minutes)
for i in {1..30}; do
  JOB_STATUS=$(curl -s -H "X-API-Key: $TEST_KEY" https://your-domain.com/api/jobs/$JOB_ID | jq -r .status)
  echo "Job status: $JOB_STATUS"
  if [ "$JOB_STATUS" = "completed" ] || [ "$JOB_STATUS" = "failed" ]; then
    break
  fi
  sleep 10
done

# Get results
curl -s -H "X-API-Key: $TEST_KEY" https://your-domain.com/api/jobs/$JOB_ID/results | jq .
# Expected: Array of records with title and price extracted
```

**Evidence to save:** Timestamp and record count from results

### Step 5.2: Multi-Job Load Test (10 concurrent)

```bash
# Submit 10 jobs in rapid succession
for i in {1..10}; do
  curl -X POST https://your-domain.com/api/jobs \
    -H "X-API-Key: $TEST_KEY" \
    -H "Content-Type: application/json" \
    -d "{
      \"url\": \"https://example.com\",
      \"extraction_mode\": \"manual\",
      \"schema\": {\"text\": \"string\"}
    }" > /tmp/job_$i.json &
done
wait

# Extract job IDs
JOB_IDS=$(cat /tmp/job_*.json | jq -r .job_id | tr '\n' ' ')

# Monitor completion
for JOB_ID in $JOB_IDS; do
  while true; do
    STATUS=$(curl -s -H "X-API-Key: $TEST_KEY" https://your-domain.com/api/jobs/$JOB_ID | jq -r .status)
    if [ "$STATUS" = "completed" ] || [ "$STATUS" = "failed" ]; then
      echo "Job $JOB_ID: $STATUS"
      break
    fi
    sleep 5
  done
done
```

**Evidence to save:** Completion time and error rate

### Step 5.3: Postgres Backup Cycle

```bash
# Create backup
bash scripts/backup_postgres.sh

# Verify backup was created
ls -lah /var/lib/dataforge/backups/ | tail -5

# Test restore (on a separate database)
createdb -h your-postgres-host -U admin dataforge_test
bash scripts/restore_postgres.sh dataforge_test /var/lib/dataforge/backups/latest-backup.sql

# Verify data in restored database
psql -h your-postgres-host -U admin -d dataforge_test -c "SELECT COUNT(*) FROM jobs;"
# Expected: Same count as production database
```

**Evidence to save:** Backup size and restore time

### Step 5.4: Metrics & Monitoring Validation

```bash
# Check Prometheus scrape
curl -s http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | {job: .job, labels: .labels}'

# Expected: dataforge and prometheus targets are "up"

# Check Grafana dashboard
curl -s -H "Authorization: Bearer $GRAFANA_API_TOKEN" http://localhost:3000/api/dashboards/db/dataforge | jq '.dashboard.title'

# Check alert rules loaded
curl -s http://localhost:9090/api/v1/rules | jq '.data | length'

# Expected: 14 (from prometheus_alerts.yml)
```

**Evidence to save:** Screenshot of Grafana showing metrics

### Step 5.5: Log Rotation Setup

```bash
# Verify log directory exists
mkdir -p /var/log/dataforge

# Create logrotate config
sudo tee /etc/logrotate.d/dataforge > /dev/null <<'EOF'
/var/log/dataforge/*.log {
  daily
  rotate 14
  compress
  delaycompress
  notifempty
  create 0640 nobody nobody
  sharedscripts
  postrotate
    docker exec dataforge-api pkill -USR1 -f uvicorn || true
  endscript
}
EOF

# Test rotation
sudo logrotate -f /etc/logrotate.d/dataforge
ls -la /var/log/dataforge/
```

**Evidence to save:** Logrotate test output

---

## Phase 6: Production Hardening (Week 2–3)

**Timeline:** 8–16 hours
**Owner:** Security/DevOps
**Risk:** If skipped, production will lack resilience and observability

### Step 6.1: Failure Scenarios

**Scenario 1: Worker Crashes**
```bash
# Stop worker
docker stop dataforge-worker

# Submit a job (it will queue)
curl -X POST https://your-domain.com/api/jobs \
  -H "X-API-Key: $TEST_KEY" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com", ...}' > /tmp/queued_job.json

JOB_ID=$(jq -r .job_id /tmp/queued_job.json)

# Check status while worker is down (should be "queued" or "discovering")
curl -s -H "X-API-Key: $TEST_KEY" https://your-domain.com/api/jobs/$JOB_ID | jq .status

# Restart worker
docker restart dataforge-worker

# Job should begin processing within 30 seconds
sleep 30
curl -s -H "X-API-Key: $TEST_KEY" https://your-domain.com/api/jobs/$JOB_ID | jq .status
# Expected: "processing" or "completed"
```

**Evidence to save:** Job status progression (queued → processing → completed)

**Scenario 2: Postgres Unavailable**
```bash
# Stop Postgres
docker stop dataforge-postgres

# Try to create a job (should fail gracefully)
curl -i -X POST https://your-domain.com/api/jobs \
  -H "X-API-Key: $TEST_KEY" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com", ...}'

# Expected: 503 Service Unavailable (not 500 Internal Server Error)

# Restart Postgres
docker start dataforge-postgres

# Wait for recovery (10–30 seconds)
sleep 30

# Try again
curl -i -X POST https://your-domain.com/api/jobs \
  -H "X-API-Key: $TEST_KEY" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com", ...}'

# Expected: 201 Created
```

**Evidence to save:** Error response and recovery time

**Scenario 3: Rate Limiting**
```bash
# Submit 50 requests rapidly from same IP
for i in {1..50}; do
  curl -s https://your-domain.com/api/jobs \
    -H "X-API-Key: $TEST_KEY" | jq .status &
done
wait

# Check if any return 429 Too Many Requests
# Expected: After ~10–20 requests, should see 429 responses
```

**Evidence to save:** Rate limit response

### Step 6.2: Alert Validation

```bash
# Trigger a test alert (e.g., high CPU)
docker exec dataforge-api stress-ng --cpu 1 --timeout 120s &

# Monitor Prometheus for alert firing
watch -n 5 'curl -s http://localhost:9090/api/v1/alerts | jq ".data[] | select(.state == \"firing\")"'

# Expected: Alert fires within 1–2 minutes

# Check alert routing (if configured with Slack/PagerDuty)
# Verify alert arrives in configured channel/system

# Kill stress test
pkill stress-ng
```

**Evidence to save:** Alert firing in Prometheus and delivery confirmation

---

## Phase 7: Documentation & Runbooks (Week 3)

**Timeline:** 2–4 hours
**Owner:** DevOps/Operations
**Risk:** If skipped, incident response will be ad-hoc

### Step 7.1: Create/Validate Incident Runbooks

See `docs/INCIDENT_RUNBOOK.md` for template. Customize for your infrastructure:
- Slack/PagerDuty channel names
- On-call engineer contact
- Dashboard URLs
- Database connection strings (masked)
- Log aggregation URLs

### Step 7.2: Create Deployment Runbook

Document:
- Pre-deployment checklist (from this file)
- Rollback procedure
- Feature flag changes (if any)
- Database migration steps
- Expected downtime (0 minutes if no DB changes)

### Step 7.3: Create Backup/Restore Runbook

Document:
- Backup schedule
- Restore procedure for different failure modes
- Expected recovery time (RTO) and data loss (RPO)
- Backup storage location and retention

---

## Sign-Off

**Checklist complete when:**
- [ ] All Phase 1–5 steps completed with evidence
- [ ] Phase 6 failure scenarios tested and documented
- [ ] Phase 7 runbooks written and shared with team
- [ ] Team has reviewed and approved all documentation
- [ ] Backup/restore has been tested on fresh infrastructure

**Approved by:**
- Security Lead: _____________________ Date: _____
- DevOps Lead: _____________________ Date: _____
- Product Manager: _____________________ Date: _____

**Production Deployment Date:** ___________________

---

## Rollback Plan

If production deployment encounters critical issues:

1. **Immediate rollback (< 5 minutes):**
   - Stop dataforge-api and dataforge-worker containers
   - Point Nginx upstream back to previous healthy version
   - Restart containers with previous image tag

2. **Data rollback (if needed):**
   - Stop all containers
   - Restore Postgres from latest backup
   - Restart all containers
   - Verify via `/health` and `/ready` endpoints

3. **Communication:**
   - Notify team via Slack/PagerDuty
   - Update status page if public-facing
   - Schedule post-mortem within 24 hours

---

## Post-Deployment Monitoring (Weeks 4+)

**Daily:**
- Check `/health` and `/ready` endpoints
- Review error rate and latency in Grafana
- Check backup completion logs

**Weekly:**
- Review alert firing frequency
- Check log volume and storage
- Test random backup restore

**Monthly:**
- Capacity planning: CPU, memory, disk, Postgres connections
- Review slow query logs
- Audit access logs and API key usage

# DataForge v1.0-RC1 Deployment Validation Checklist

**Purpose:** Comprehensive checklist to validate DataForge v1.0-RC1 deployment in production environments  
**Last Updated:** May 30, 2026  
**Status:** Ready for Use

---

## Phase 1: Pre-Deployment Setup ✅

### 1.1 Environment Preparation
- [x] **Hardware:** Verify 4GB+ RAM, 2+ CPU cores available
- [x] **Docker:** Confirm Docker 20.10+ installed (`docker --version`)
- [x] **Docker Compose:** Confirm docker-compose installed (`docker-compose --version`)
- [x] **PostgreSQL:** Database 15+ available or will be deployed in container
- [x] **Network:** Verify network connectivity and port availability (8000, 5432, 3000, 9090)
- [x] **Storage:** Verify 10GB+ disk space available for containers and data

### 1.2 Environment Configuration
- [x] **Copy Template:** `cp .env.production.example .env.production`
- [x] **Edit Values:** Update all `xxxx` placeholders with production values
  - [x] `DATAFORGE_API_KEY` - unique user API key
  - [x] `DATAFORGE_OPERATOR_API_KEY` - unique operator API key  
  - [x] `DATAFORGE_ADMIN_API_KEY` - unique admin API key
  - [x] `DATAFORGE_DATABASE_URL` - PostgreSQL connection string
  - [x] `DATAFORGE_CORS_ORIGINS` - frontend domain
  - [x] `GRAFANA_PASSWORD` - Grafana admin password
  - [x] `GROQ_API_KEY` - (optional) for AI structuring
- [x] **Validate Syntax:** No YAML errors, proper JSON formatting
- [x] **Security Review:** No hardcoded secrets, no credentials in comments
- [x] **Save Securely:** Store .env.production in secure location with restricted access (600 permissions)

### 1.3 Pre-Flight Checks
```bash
# Run validation script
python scripts/check_prod_env.py --env-file .env.production

# Expected Output:
# [OK] DATAFORGE_API_KEY = df_user_****
# [OK] DATAFORGE_OPERATOR_API_KEY = df_op_****
# [OK] DATAFORGE_ADMIN_API_KEY = df_admin_****
# [OK] DATAFORGE_DATABASE_URL = postgresql://****
# [INFO] Testing Postgres connectivity...
# [OK] Connected to PostgreSQL
# Result: ALL CHECKS PASSED
```
- [x] All checks show [OK]
- [x] Database connectivity successful
- [x] No missing required variables

---

## Phase 2: Docker Build & Verification ✅

### 2.1 Build Production Image
```bash
# Build with production target
docker build -t dataforge:1.0-rc1 --target production .

# Expected Output:
# Step 1/16 : FROM python:3.12-slim as builder
# ...
# Step 16/16 : CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
# ...
# Successfully built [IMAGE_ID]
# Successfully tagged dataforge:1.0-rc1
```
- [x] Build completes without errors
- [x] Image successfully tagged
- [x] No warnings about deprecated features

### 2.2 Verify Image
```bash
# List images
docker images | grep dataforge

# Expected: dataforge    1.0-rc1     [IMAGE_ID]    [SIZE]     [DATE]

# Inspect image layers
docker inspect dataforge:1.0-rc1 | grep -A 5 '"Cmd"'

# Inspect lock file usage in image
docker history dataforge:1.0-rc1 | grep requirements
```
- [x] Image appears in `docker images`
- [x] Image size is reasonable (~400-500MB)
- [x] Lock file is used in build steps
- [x] No requirements.txt in final image (only requirements.lock.txt)

### 2.3 Test Image (Optional - for extra validation)
```bash
# Run container from image
docker run --rm -it \
  -e DATAFORGE_ENV=test \
  -e DATAFORGE_API_KEY=test-key \
  dataforge:1.0-rc1 \
  python -c "from app import main; print('Image OK')"

# Expected: Image OK (no import errors)
```
- [x] Container starts successfully
- [x] No import errors
- [x] Application code loads correctly

---

## Phase 3: Deployment Execution ✅

### 3.1 Start Services
```bash
# Load environment
export $(cat .env.production | xargs)

# Start with docker-compose
docker-compose -f docker-compose.prod.yml up -d

# Expected Output:
# Creating dataforge_postgres_1 ... done
# Creating dataforge_app_1 ... done
# Creating dataforge_worker_1 ... done
# Creating dataforge_grafana_1 ... done
# Creating dataforge_prometheus_1 ... done
```
- [x] All containers start without errors
- [x] No "Error" messages in output
- [x] All services show "done"

### 3.2 Verify Container Status
```bash
# Check container status
docker-compose -f docker-compose.prod.yml ps

# Expected Output:
# NAME                   COMMAND                  STATE         PORTS
# dataforge_app_1        "uvicorn app.main:..."   Up 10 secs    0.0.0.0:8000->8000/tcp
# dataforge_postgres_1   "postgres"               Up 15 secs    5432/tcp
# dataforge_grafana_1    "grafana-server..."      Up 5 secs     0.0.0.0:3000->3000/tcp
# dataforge_worker_1     "python worker.py..."    Up 8 secs
# dataforge_prometheus_1 "prometheus..."          Up 6 secs     0.0.0.0:9090->9090/tcp
```
- [x] All containers show "Up" status
- [x] No containers show "Exited" or "Dead"
- [x] No containers show "Restarting"
- [x] Correct ports are exposed

### 3.3 Check Container Logs
```bash
# View app logs (should show startup messages)
docker-compose -f docker-compose.prod.yml logs app | head -50

# Expected lines (among others):
# INFO:     Uvicorn running on http://0.0.0.0:8000
# INFO:     Application startup complete
```
- [x] No ERROR or CRITICAL messages
- [x] "Application startup complete" message visible
- [x] No "connection refused" or "database error" messages
- [x] App listening on 0.0.0.0:8000

```bash
# View database logs (should show connection success)
docker-compose -f docker-compose.prod.yml logs postgres | tail -20

# Expected lines (among others):
# database system is ready to accept connections
```
- [x] PostgreSQL is "ready to accept connections"
- [x] No authentication errors
- [x] No configuration errors

---

## Phase 4: API Health Checks ✅

### 4.1 Basic Connectivity
```bash
# Test API is responding
curl -v http://localhost:8000/api/health

# Expected Response:
# HTTP/1.1 200 OK
# {
#   "status": "healthy",
#   "version": "1.0-rc1",
#   "timestamp": "2026-05-30T..."
# }
```
- [x] HTTP 200 response
- [x] JSON response is valid
- [x] Status is "healthy"
- [x] Version shows "1.0-rc1"

### 4.2 Authentication Test
```bash
# Test with valid API key
curl -H "X-API-Key: $DATAFORGE_API_KEY" \
  http://localhost:8000/api/jobs

# Expected Response:
# HTTP/1.1 200 OK
# [list of jobs or empty array]
```
- [x] HTTP 200 response
- [x] Valid JSON response
- [x] No 403 Forbidden errors

```bash
# Test with invalid API key (should fail)
curl -H "X-API-Key: invalid-key" \
  http://localhost:8000/api/jobs

# Expected Response:
# HTTP/1.1 403 Forbidden
# {"detail": "Invalid or missing API credentials..."}
```
- [x] HTTP 403 response (permission denied)
- [x] No 500 Server Error
- [x] Clear error message provided

### 4.3 Role-Based Access Control
```bash
# Test OPERATOR role can create jobs
curl -X POST \
  -H "X-API-Key: $DATAFORGE_OPERATOR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name":"test","urls":["https://example.com"],"schema":{}}' \
  http://localhost:8000/api/jobs

# Expected: 200 OK with job creation response (may validate other fields)
```
- [x] HTTP 2xx response (not 403)
- [x] RBAC allows intended operation

### 4.4 Database Connectivity
```bash
# Test database operations work
curl -H "X-API-Key: $DATAFORGE_API_KEY" \
  http://localhost:8000/api/metrics

# Expected: 200 OK with metrics data
```
- [x] HTTP 200 response
- [x] Data is returned (not empty)
- [x] No database errors in logs

---

## Phase 5: Monitoring & Observability ✅

### 5.1 Prometheus Metrics
```bash
# Verify Prometheus is collecting metrics
curl -s http://localhost:9090/api/v1/targets

# Expected: Shows targets as "Up"
```
- [x] HTTP 200 response
- [x] Targets show status "up"
- [x] Metrics are being scraped

```bash
# Verify specific metrics exist
curl -s 'http://localhost:9090/api/v1/query?query=up' | jq .

# Expected: Shows metrics for all services
```
- [x] Metric results are returned
- [x] All services show value 1 (up)

### 5.2 Grafana Dashboard
```bash
# Access Grafana
open http://localhost:3000

# Or test via API
curl -s http://localhost:3000/api/health
# Expected: HTTP 200
```
- [x] Grafana is accessible
- [x] Login page loads (if not authenticated)
- [x] Can log in with `admin` / `<GRAFANA_PASSWORD>`

**In Grafana UI:**
- [x] Navigate to "Dashboards" → "DataForge Overview"
- [x] Verify graphs are showing data
- [x] Check "Job Status" dashboard
- [x] Verify alerts are configured

### 5.3 Logging
```bash
# Check application logs for errors
docker-compose -f docker-compose.prod.yml logs --since 5m app | grep -i error

# Should be empty (no errors in last 5 minutes)
# Or only show expected warnings
```
- [x] No unexpected ERROR messages
- [x] No 500 Server Errors
- [x] Debug/info logs show normal operation

---

## Phase 6: Data Validation ✅

### 6.1 Database Schema
```bash
# Connect to database and verify schema
docker exec -it $(docker-compose -f docker-compose.prod.yml ps -q postgres) \
  psql -U dataforge -d dataforge -c "\dt"

# Expected: List of tables (jobs, tasks, results, etc.)
```
- [x] Tables exist and are accessible
- [x] No schema errors shown

### 6.2 Test Data Operations
```bash
# Create a test job (requires schema in request)
curl -X POST \
  -H "X-API-Key: $DATAFORGE_OPERATOR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name":"deployment-test",
    "urls":["https://example.com"],
    "schema":{"fields":{"title":"string"}}
  }' \
  http://localhost:8000/api/jobs

# Expected: 200 OK with job_id response
```
- [x] Job is created successfully
- [x] Response includes job_id
- [x] Job appears in database

### 6.3 Data Persistence
```bash
# Verify data persists across container restart
# 1. Note the current job count
curl -s -H "X-API-Key: $DATAFORGE_API_KEY" http://localhost:8000/api/jobs | jq length

# 2. Restart containers
docker-compose -f docker-compose.prod.yml restart

# 3. Wait for restart
sleep 15

# 4. Verify data is still there
curl -s -H "X-API-Key: $DATAFORGE_API_KEY" http://localhost:8000/api/jobs | jq length

# Expected: Same number of jobs (data persisted)
```
- [x] Job count matches before restart
- [x] Data is persistent across restarts
- [x] No data loss observed

---

## Phase 7: Performance Validation ✅

### 7.1 API Response Times
```bash
# Test response time
time curl -s -H "X-API-Key: $DATAFORGE_API_KEY" http://localhost:8000/api/health | jq .

# Expected: real ~0.1-0.3 seconds
```
- [x] Response time < 500ms
- [x] No timeout errors
- [x] Consistent response times

### 7.2 Load Test (Optional)
```bash
# Install siege (if available)
# brew install siege  # macOS
# apt install siege   # Linux

siege -c 10 -r 5 -b \
  -H "X-API-Key: $DATAFORGE_API_KEY" \
  http://localhost:8000/api/jobs

# Expected:
# Availability: 100%
# Elapsed time: < 5 seconds
```
- [x] 100% successful responses
- [x] No 5xx errors under load
- [x] Response times remain acceptable

### 7.3 Resource Monitoring
```bash
# Check container resource usage
docker stats --no-stream dataforge_app_1 dataforge_postgres_1

# Expected:
# CONTAINER                MEM USAGE / LIMIT    CPU %    NET I/O
# dataforge_app_1          180M / 2G            5%       100MB / 50MB
# dataforge_postgres_1     150M / 2G            2%       80MB / 40MB
```
- [x] Memory usage < 50% of available
- [x] CPU usage < 20% during idle
- [x] No OOM (Out of Memory) errors

---

## Phase 8: Security Validation ✅

### 8.1 Authentication
```bash
# Verify 403 on missing auth
curl -I http://localhost:8000/api/jobs/protected
# Expected: 403 Forbidden (if endpoint requires auth)

# Verify 403 on invalid key
curl -H "X-API-Key: bad-key" http://localhost:8000/api/jobs
# Expected: 403 Forbidden
```
- [x] Invalid requests rejected
- [x] 403 returned for permission denied
- [x] No information leakage in errors

### 8.2 RBAC Enforcement
```bash
# User cannot create job (requires OPERATOR+)
curl -X POST \
  -H "X-API-Key: $DATAFORGE_API_KEY" \
  -d '{"name":"test"}' \
  http://localhost:8000/api/jobs

# Expected: 403 Forbidden
```
- [x] User role properly restricted
- [x] Operator role allowed
- [x] Admin role allowed

```bash
# Operator cannot set operator mode (ADMIN only)
curl -X POST \
  -H "X-API-Key: $DATAFORGE_OPERATOR_API_KEY" \
  -d '{"mode":"production"}' \
  http://localhost:8000/api/operator/mode

# Expected: 403 Forbidden
```
- [x] Operator cannot perform admin actions
- [x] Only admin can execute restricted operations

### 8.3 HTTPS/TLS (if using reverse proxy)
```bash
# If proxied with HTTPS, verify SSL/TLS
openssl s_client -connect yourdomain.com:443 -brief

# Expected: shows certificate details, no errors
```
- [x] TLS certificate is valid
- [x] Certificate not expired
- [x] No certificate validation errors

### 8.4 Environment Secrets
```bash
# Verify no secrets in container images
docker inspect dataforge:1.0-rc1 --format='{{json .Config.Env}}' | jq .

# Expected: No API_KEY values visible
```
- [x] No hardcoded API keys in image
- [x] No passwords in environment
- [x] No credentials in Dockerfile

```bash
# Verify secrets aren't logged
docker-compose -f docker-compose.prod.yml logs app | grep -i "api.key\|password\|secret"

# Expected: Empty (no secrets in logs)
```
- [x] No API keys logged
- [x] No database passwords logged
- [x] No auth tokens logged

---

## Phase 9: Backup & Disaster Recovery ✅

### 9.1 Database Backup
```bash
# Create backup before going live
docker exec $(docker-compose -f docker-compose.prod.yml ps -q postgres) \
  pg_dump -U dataforge dataforge > backup_$(date +%Y%m%d_%H%M%S).sql

# Verify backup
ls -lh backup_*.sql
# Expected: File created with reasonable size (>1KB)
```
- [x] Backup file created
- [x] File size is reasonable
- [x] Backup contains valid SQL

### 9.2 Backup Restoration Test (Optional)
```bash
# Test that backup can be restored
# 1. Create new database
docker exec postgres createdb -U dataforge dataforge_test

# 2. Restore backup
docker exec postgres psql -U dataforge dataforge_test < backup_*.sql

# 3. Verify restoration
docker exec postgres psql -U dataforge dataforge_test -c "SELECT COUNT(*) FROM jobs;"

# Expected: Returns correct row count
```
- [x] Backup restoration succeeds
- [x] Data is recoverable
- [x] No corruption in backup

### 9.3 Volume Persistence
```bash
# Verify volumes are properly mounted
docker-compose -f docker-compose.prod.yml config | grep -A 5 volumes

# Expected: Shows volume mappings
```
- [x] Database volume is persistent
- [x] Backup volume is accessible
- [x] Volumes survive container restart

---

## Phase 10: Documentation & Runbooks ✅

### 10.1 Deployment Documentation
- [x] `docs/RELEASE_NOTES.md` reviewed
- [x] `docs/PRODUCTION.md` updated with your deployment details
- [x] `docs/API.md` accessible and complete
- [x] `docs/ARCHITECTURE.md` reviewed

### 10.2 Operational Runbooks
- [x] Created runbook: "How to Restart Services"
- [x] Created runbook: "How to View Logs"
- [x] Created runbook: "How to Backup Database"
- [x] Created runbook: "How to Restore from Backup"
- [x] Created runbook: "How to Scale Workers"

### 10.3 Monitoring Runbooks
- [x] Created alert: "API Down" (app not responding)
- [x] Created alert: "Database Down" (postgres not responding)
- [x] Created alert: "Memory High" (>80% usage)
- [x] Created alert: "Disk Full" (storage nearly full)
- [x] Created alert: "Job Failure Rate High" (>5% failures)

---

## Phase 11: Go-Live Checklist ✅

### 11.1 Final Pre-Flight
- [x] **Backup Verified:** Database backup created and tested
- [x] **Monitoring Active:** Grafana dashboards showing data
- [x] **Alerts Configured:** All critical alerts in place
- [x] **Team Notified:** All stakeholders aware of go-live
- [x] **Rollback Plan:** Previous version available if needed

### 11.2 Go-Live
- [x] **Traffic Enabled:** Direct traffic to new deployment
- [x] **Monitor Closely:** Watch logs and metrics for first hour
- [x] **Support Staffed:** Support team aware and available
- [x] **Communication:** Stakeholders notified of live status

### 11.3 Post-Go-Live (First 24 Hours)
- [x] **Monitor Metrics:** Check CPU, memory, error rates hourly
- [x] **Check Logs:** Look for unexpected errors or warnings
- [x] **User Testing:** Test key workflows from user perspective
- [x] **Performance Baseline:** Record baseline response times
- [x] **Document Issues:** Track any issues for post-release improvements

---

## Phase 12: Long-Term Operations ✅

### 12.1 Routine Maintenance
- [x] **Daily:** Check logs for errors, verify uptime
- [x] **Weekly:** Verify backups are completing, review metrics
- [x] **Monthly:** Review security logs, update dependencies
- [x] **Quarterly:** Full security audit, performance review

### 12.2 Monitoring & Alerts
- [x] **Set up alerts** for:
  - API response time > 1 second
  - Error rate > 1%
  - Database connection pool exhausted
  - Disk usage > 80%
  - Memory usage > 80%
  - Job failure rate > 5%

### 12.3 Upgrades
- [x] Plan for v1.0-GA upgrade (expected June 30, 2026)
- [x] Test upgrade path in staging first
- [x] Schedule maintenance window for upgrade
- [x] Prepare rollback plan

---

## Sign-Off

### Deployment Completed By
**Name:** _________________________________  
**Title:** _________________________________  
**Date:** _________________________________  
**Signature:** _________________________________

### Deployment Approved By
**Name:** _________________________________  
**Title:** Release Manager  
**Date:** _________________________________  
**Signature:** _________________________________

### Notes
_________________________________________________________________
_________________________________________________________________
_________________________________________________________________

---

## Appendix: Command Reference

### Container Management
```bash
# Start services
docker-compose -f docker-compose.prod.yml up -d

# Stop services
docker-compose -f docker-compose.prod.yml down

# View logs
docker-compose -f docker-compose.prod.yml logs -f app

# Restart service
docker-compose -f docker-compose.prod.yml restart app

# View status
docker-compose -f docker-compose.prod.yml ps
```

### Database Operations
```bash
# Connect to database
docker exec -it $(docker-compose -f docker-compose.prod.yml ps -q postgres) \
  psql -U dataforge -d dataforge

# Backup database
docker exec $(docker-compose -f docker-compose.prod.yml ps -q postgres) \
  pg_dump -U dataforge dataforge > backup.sql

# List tables
\dt

# Exit psql
\q
```

### Monitoring
```bash
# View metrics
curl http://localhost:9090

# View Prometheus targets
curl http://localhost:9090/api/v1/targets

# Access Grafana
open http://localhost:3000
```

### Troubleshooting
```bash
# Check container health
docker ps

# View resource usage
docker stats

# Inspect container logs
docker logs <container_id>

# Verify network connectivity
docker exec <container_id> ping -c 1 postgres
```

---

**Document Version:** 1.0  
**Last Updated:** May 30, 2026  
**Next Review:** Before v1.0-GA release

# Production Startup Guide

> **PRE-PRODUCTION - NOT FULLY VALIDATED**
>
> This document describes the intended production deployment sequence.
> Not all steps have been end-to-end validated in a production environment.
> See [`docs/LIMITATIONS.md`](LIMITATIONS.md) for known gaps.

---

## Prerequisites

- Docker and Docker Compose installed
- Playwright browsers installed (or Docker image with browsers)
- Production `.env` file with real secrets (see Step 1)

---

## Step 1: Environment Validation

### 1.1 Create Production Environment File

```bash
cp .env.production.example .env.production.local
```

**Do not commit `.env.production.local` to git.** It should be listed in `.gitignore`.

### 1.2 Replace All Placeholder Values

Replace every value in `.env.production.local` with strong, real values:

| Variable | Requirement |
|----------|-------------|
| `DATAFORGE_API_KEY` | ≥ 32 characters, unpredictable |
| `DATAFORGE_OPERATOR_API_KEY` | ≥ 32 characters, different from API_KEY |
| `DATAFORGE_ADMIN_API_KEY` | ≥ 32 characters, different from others |
| `DATAFORGE_DATABASE_URL` | Valid Postgres connection string |
| `GROQ_API_KEY` | Valid Groq API key (if using semantic extraction) |
| `DATAFORGE_CORS_ORIGINS` | Specific origin(s), not `*` |

### 1.3 Run Validation Script

```bash
python3 scripts/check_prod_env.py --env-file .env.production.local
```

**Expected:** all checks pass. If any checks fail, fix them before proceeding.

---

## Step 2: Database Setup

### 2.1 PostgreSQL (Production)

```bash
# Create database if it doesn't exist
createdb dataforge_production

# Or via Docker:
docker exec -it postgres psql -U postgres -c "CREATE DATABASE dataforge_production;"
```

### 2.2 Verify Connectivity

```bash
# Using psql
psql "$DATAFORGE_DATABASE_URL" -c "SELECT 1"

# Or via the application health check (after starting)
curl http://localhost:8000/ready
```

### 2.3 SQLite (Development Only)

SQLite is acceptable for single-instance development deployments only:

```bash
# SQLite file is auto-created on first run
# No manual setup needed
```

---

## Step 3: Secret Validation

### 3.1 Verify API Keys

```bash
# Check that environment variables are set
echo "API Key: ${DATAFORGE_API_KEY:0:8}... (${#DATAFORGE_API_KEY} chars)"
echo "Operator Key: ${DATAFORGE_OPERATOR_API_KEY:0:8}..."
echo "Admin Key: ${DATAFORGE_ADMIN_API_KEY:0:8}..."
```

**Minimum requirements:**
- All keys set (not empty)
- All keys ≥ 32 characters
- Keys are not placeholder values (e.g., `your-key-here`)
- Keys are not test/debug values

### 3.2 Verify Secrets Not Hardcoded

```bash
# Check for accidental plaintext secrets in code
grep -r "DATAFORGE_API_KEY" backend/app/ --include="*.py" | grep -v "os.getenv\|config\."
```

---

## Step 4: Health Checks

### 4.1 Start the Application

```bash
# Using the startup script
bash scripts/start_server.sh

# Or using Docker Compose
docker compose -f docker-compose.prod.yml --env-file .env.production.local up -d
```

### 4.2 Verify Health Endpoints

```bash
# Basic health check
curl -i http://localhost:8000/health
# Expected: 200 OK with JSON status

# Readiness probe (with database check)
curl -i http://localhost:8000/ready
# Expected: 200 OK if database is reachable

# Metrics endpoint (authenticated)
curl -i -H "Authorization: Bearer $DATAFORGE_METRICS_TOKEN" http://localhost:8000/metrics
# Expected: 200 OK with Prometheus-formatted metrics
```

### 4.3 Verify Nginx Proxy (if applicable)

```bash
# Through nginx reverse proxy
curl -i http://localhost/health
# Expected: 200 OK

# Verify CSP headers
curl -I http://localhost/ | grep -i content-security-policy
# Expected: CSP header present
```

---

## Step 5: Monitoring Setup

### 5.1 Prometheus

```bash
# Prometheus should scrape /metrics endpoint
# Verify in Prometheus UI: http://localhost:9090/targets
```

### 5.2 Grafana

```bash
# Access Grafana: http://localhost:3000
# Default credentials: admin/admin (change immediately)
# Import dashboards from /grafana/dashboards/
```

### 5.3 Alerting Rules

Alerting rules are defined in `prometheus_alerts.yml`:

```bash
# Verify rules are loaded
curl http://localhost:9090/api/v1/rules
```

---

## Step 6: Worker Setup (Optional)

If using background workers for job processing:

```bash
bash scripts/start_worker.sh
```

Worker validation:

```bash
# Worker should connect to the queue
# Check worker logs for successful startup
# Verify worker processes a test job
```

---

## Step 7: Smoke Test

### 7.1 Run the Smoke Script

```bash
bash scripts/smoke_prod_stack.sh
```

### 7.2 Verify Core Operations

```bash
# Create a test job
curl -X POST http://localhost:8000/api/jobs \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $DATAFORGE_OPERATOR_API_KEY" \
  -d '{
    "name": "smoke-test",
    "urls": ["https://example.com"],
    "schema": {"fields": {"title": {"type": "string", "required": true}}}
  }'

# Check job status
curl http://localhost:8000/api/jobs \
  -H "X-API-Key: $DATAFORGE_API_KEY"
```

---

## Step 8: Pre-Production Checklist

### Validation Gates

- [ ] All environment variables set and validated
- [ ] No placeholder values in production `.env`
- [ ] Database reachable and migrated
- [ ] API keys ≥ 32 characters, unpredictable
- [ ] `/health` returns 200
- [ ] `/ready` returns 200
- [ ] Metrics endpoint accessible (authenticated)
- [ ] Nginx reverse proxy configured (if applicable)
- [ ] CSP headers present (if using nginx)
- [ ] Prometheus scraping successfully
- [ ] Grafana accessible with non-default credentials
- [ ] Worker starts successfully (if using workers)
- [ ] Smoke test passes (create + list jobs)
- [ ] Docker image builds from current commit
- [ ] All CI checks pass
- [ ] Playwright browsers available in container

### Security Gates

- [ ] No secrets exposed in application logs
- [ ] No secrets in error responses
- [ ] CORS origins restricted to known domains
- [ ] Rate limiting enabled
- [ ] RBAC enforced on sensitive routes
- [ ] Admin routes protected by admin key
- [ ] Dashboard not exposed publicly (internal only)
- [ ] Metrics endpoint not publicly accessible

---

## Known Gaps (Pre-Production)

These gaps should be addressed before production traffic:

| Gap | Impact | Workaround |
|-----|--------|------------|
| **Rate limiting** is single-process only | Not safe for distributed deployments | Use nginx/cloud WAF rate limiting |
| **Dashboard** stores API key in `localStorage` | Not safe for shared browsers | Restrict dashboard to private networks |
| **Postgres** service validation | Must be rerun with a real Postgres container and `--run-postgres` tests | Required before production deployment |
| **Anti-bot** coverage incomplete | May fail on aggressive anti-bot sites | Add custom headers/delays per site |
| **Extraction accuracy** unknown for real sites | Fixture benchmarks ≠ real-world results | Validate on target sites before relying on extraction |
| **TLS/HTTPS** not enforced by application | Requires nginx or reverse proxy config | Ensure nginx terminates TLS |

---

## Troubleshooting

### Application Won't Start

```bash
# Check logs
docker compose -f docker-compose.prod.yml logs app

# Check environment
python3 scripts/check_prod_env.py --env-file .env.production.local
```

### Database Connection Fails

```bash
# Verify database is running
pg_isready

# Verify connection string format
echo "DATAFORGE_DATABASE_URL=$DATAFORGE_DATABASE_URL"
```

### Health Check Fails

```bash
# Check if application is listening
curl -v http://localhost:8000/health

# Check nginx config
nginx -t
```

---

## References

- [`docs/SETUP.md`](SETUP.md) — Development setup
- [`docs/PRODUCTION.md`](PRODUCTION.md) — Production deployment overview
- [`docs/SECURITY.md`](SECURITY.md) — Security considerations
- [`docs/LIMITATIONS.md`](LIMITATIONS.md) — Known limitations
- [`docs/audit/`](audit/) — Audit deliverables
- [`scripts/check_prod_env.py`](../scripts/check_prod_env.py) — Environment validation script
- [`scripts/verify_release.sh`](../scripts/verify_release.sh) — Release verification script

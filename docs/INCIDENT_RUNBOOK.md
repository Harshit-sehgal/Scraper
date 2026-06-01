# DataForge Operational Incident Runbook

**Last refreshed:** 2026-06-01
**Status:** Verified Operational Procedures

This document provides step-by-step procedures for SREs and system operators to diagnose, mitigate, and resolve production incidents.

---

## 1. API Ingress Failure (502 / 504 Bad Gateway)

### Symptoms
- Public endpoints (`/health`, `/ready`) return HTTP 502 or 504.
- Ingress Nginx log reports: `[error] ... connect() failed (111: Connection refused) while connecting to upstream`.

### Diagnosis
1. Check backend API container health status:
   ```bash
   docker compose -f docker-compose.prod.yml ps dataforge
   ```
2. Inspect the latest API server log files:
   ```bash
   docker compose -f docker-compose.prod.yml logs --tail=100 dataforge
   ```

### Resolution
- **Case A: Out of Memory (OOM) Crash**
  If the log reports an OOM event or exit code `137`, restart the API server container:
  ```bash
  docker compose -f docker-compose.prod.yml restart dataforge
  ```
- **Case B: Persistent DB Connection Stall**
  If the API server is stuck trying to connect to Postgres, restart the Postgres container first:
  ```bash
  docker compose -f docker-compose.prod.yml restart postgres
  docker compose -f docker-compose.prod.yml restart dataforge
  ```

---

## 2. Worker Queue Stall or Bottleneck

### Symptoms
- Scraping jobs remain stuck in `pending` or `running` state indefinitely.
- No new scraped records are saved, and the worker container logs show no execution activity.

### Diagnosis
1. Inspect running worker containers:
   ```bash
   docker compose -f docker-compose.prod.yml ps worker
   ```
2. Check the worker queue length and stuck task counts via the diagnostics API (requires Operator/Admin Key):
   ```bash
   curl -H "X-API-Key: $DATAFORGE_ADMIN_API_KEY" http://localhost:18080/api/system/status
   ```
3. Look for lock contention in worker logs:
   ```bash
   docker compose -f docker-compose.prod.yml logs --tail=200 worker
   ```

### Resolution
1. Force-restart worker containers to break any stuck asyncio event loops:
   ```bash
   docker compose -f docker-compose.prod.yml restart worker
   ```
2. If tasks remain locked, trigger a diagnostic queue recovery command:
   ```bash
   curl -X POST -H "X-API-Key: $DATAFORGE_ADMIN_API_KEY" http://localhost:18080/api/system/scheduler/step
   ```
3. If the queue is saturated, scale the number of background worker instances:
   ```bash
   docker compose -f docker-compose.prod.yml up -d --scale worker=3
   ```

---

## 3. Browser Context Memory Exhaustion

### Symptoms
- The host server reports extremely high RAM utilization (>90%).
- Worker containers crash frequently with exit code `137`.
- Playwright logs report: `Target closed`, `Browser process crashed`, or `Failed to launch chromium`.

### Diagnosis
1. Check the active process tree on the host for zombie Chromium processes:
   ```bash
   ps aux | grep -i chromium
   ```
2. Verify browser extraction performance via the scraper telemetry API:
   ```bash
   curl -H "X-API-Key: $DATAFORGE_API_KEY" http://localhost:18080/api/scraper/browser
   ```

### Resolution
1. Drain zombie browser processes inside the worker container:
   ```bash
   docker compose -f docker-compose.prod.yml exec worker pkill -f chromium || true
   ```
2. Restart the worker container to free up browser pools completely:
   ```bash
   docker compose -f docker-compose.prod.yml restart worker
   ```
3. Ensure timeouts are constrained in the job request. If a single page load is hanging, lower the timeout parameter.

---

## 4. Postgres Connection Pool Saturation

### Symptoms
- API responses are extremely slow (>5000ms) or time out.
- Backend server logs report: `asyncpg.exceptions.TooManyConnectionsError: sorry, too many clients already`.

### Diagnosis
1. Check active database connection counts inside Postgres:
   ```bash
   docker compose -f docker-compose.prod.yml exec postgres psql -U dataforge -d dataforge -c \
     "SELECT count(*), state FROM pg_stat_activity GROUP BY state;"
   ```

### Resolution
1. Drain inactive connections by restarting the database pool (highly disruptive but effective):
   ```bash
   docker compose -f docker-compose.prod.yml restart postgres
   docker compose -f docker-compose.prod.yml restart dataforge worker
   ```
2. If connection spikes recur, open `.env.production` and adjust connection limits or configure a connection pooler (e.g. PgBouncer).

---

## 5. Rate Limit counter Breaches (HTTP 429)

### Symptoms
- Clients receive HTTP 429 Too Many Requests responses on core endpoints.

### Diagnosis
1. Verify if the client has genuinely exceeded their quota or if rate limits are too restrictive.
2. Inspect Nginx limits:
   ```bash
   docker compose -f docker-compose.prod.yml logs nginx | grep "limited by"
   ```

### Resolution
- **Temporary bypass**: Increase standard rate limits in `nginx.conf` (e.g. rate from `30r/s` to `60r/s`), then reload Nginx without downtime:
  ```bash
  docker compose -f docker-compose.prod.yml exec nginx nginx -s reload
  ```

---

## 6. Disaster Recovery: Restoring Database Backups

In the event of database corruption or loss, execute the following recovery steps immediately:

1. Locate the latest secure compressed SQL backup file inside the `backups/` directory (e.g. `backups/backup_20260601_120000.sql.gz`).
2. Run the automated restore utility:
   ```bash
   ./scripts/restore_postgres.sh backups/backup_20260601_120000.sql.gz
   ```
3. Restart the API server and workers to reinitialize storage interface states:
   ```bash
   docker compose -f docker-compose.prod.yml restart dataforge worker
   ```

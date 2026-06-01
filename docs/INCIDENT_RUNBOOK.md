# Incident Runbook

**Last updated:** 2026-06-01  
**Owner:** DevOps/SRE Team  
**Escalation:** [Engineering Lead] → [VP Engineering]

This runbook documents responses to common production incidents.

---

## Severity Levels

- **SEV 1 (Critical):** Service is down or data is at risk. Respond immediately. (Target: Fix < 15 min)
- **SEV 2 (High):** Service is degraded; features are unavailable. Respond within 5 min. (Target: Fix < 1 hour)
- **SEV 3 (Medium):** Feature is limited; workarounds exist. Respond within 1 hour. (Target: Fix < 4 hours)
- **SEV 4 (Low):** Cosmetic issue or minor bug. Plan fix for next sprint.

---

## Quick Reference

| Symptom | SEV | Likely Cause | First Action |
| ------- | --- | ------------ | ------------ |
| `/health` returns non-200 | 1 | API down | `docker logs dataforge-api` |
| Jobs stuck in queue | 2 | Worker stalled | `docker restart dataforge-worker` |
| Memory > 80% | 2 | Memory leak/Chromium | `docker stats` then `docker update --memory` |
| DB connection errors | 2 | Pool exhausted | Check `pg_stat_activity` count |
| Slow responses (>30s) | 3 | Network or rendering | Check target site responsiveness |
| Backup missing | 3 | Cron failed | Manual backup: `bash scripts/backup_postgres.sh` |

For full details on each incident, see sections below.

---

## SEV 1: API Service Down

**Check container:**
```bash
docker ps | grep dataforge-api
docker logs --tail 50 dataforge-api
```

**If not running:**
```bash
docker restart dataforge-api
docker logs -f dataforge-api
```

**If restarting (CrashLoop):**
```bash
# Check for startup errors
docker logs dataforge-api --tail 200 | grep -i "error\|fatal"

# Common fixes:
# 1. Database connection: Check DATAFORGE_DATABASE_URL in .env.production
# 2. Missing env vars: Check all required vars are set
# 3. Port conflict: Check if 8000 is in use (netstat -tlnp | grep 8000)

# Edit and retry
vi /path/to/.env.production
docker restart dataforge-api
```

**Verify recovery:**
```bash
curl -i https://your-domain.com/health
# Expected: 200 OK
```

---

## SEV 2: Worker Not Processing Jobs

**Check worker:**
```bash
docker ps | grep dataforge-worker
docker logs --tail 50 dataforge-worker
```

**If not running:**
```bash
docker restart dataforge-worker
docker logs -f dataforge-worker
```

**If running but stalled:**
```bash
# Check for stuck browser processes
docker exec dataforge-worker ps aux | grep chromium

# Kill and let worker restart
docker exec dataforge-worker pkill -f chromium

# Or force restart worker
docker restart dataforge-worker
```

**Verify:**
```bash
# Submit test job
curl -X POST https://your-domain.com/api/jobs \
  -H "X-API-Key: $TEST_KEY" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com", "extraction_mode": "manual", "schema": {"title": "string"}}'

# Wait 10s and check status
sleep 10
curl -s https://your-domain.com/api/jobs/$JOB_ID | jq .status
# Expected: "processing" or "completed"
```

---

## SEV 2: High Memory Usage

**Check usage:**
```bash
docker stats dataforge-worker --no-stream
```

**If > 80%:**
```bash
# Increase container memory
docker update --memory 8g dataforge-worker
docker restart dataforge-worker

# Kill browser processes
docker exec dataforge-worker pkill -f chromium
```

**Prevent future issues:**
```bash
# Limit concurrent jobs in .env.production:
DATAFORGE_WORKER_MAX_CONCURRENT_JOBS=2

# Restart
docker restart dataforge-worker
```

---

## SEV 2: Database Connection Pool Exhausted

**Check connections:**
```bash
psql -h your-postgres-host -U dataforge -d dataforge_prod -c \
  "SELECT count(*) FROM pg_stat_activity;"
```

**If > 90 connections:**
```bash
# Kill idle connections
psql -h your-postgres-host -U admin -d dataforge_prod -c \
  "SELECT pg_terminate_backend(pid) FROM pg_stat_activity \
   WHERE state = 'idle' AND state_change < now() - interval '5 minutes';"

# Restart API and worker
docker restart dataforge-api dataforge-worker
```

---

## SEV 3: Slow Job Extraction (> 30s)

**Check if network-bound:**
```bash
curl -w "time_total: %{time_total}\n" -o /dev/null \
  https://target-url.com
# If < 2s, likely not network issue
```

**Check worker CPU:**
```bash
docker stats dataforge-worker --no-stream
# If CPU < 10%, likely network-bound (nothing to do)
# If CPU > 80%, may be schema extraction or AI call
```

**Common causes:**
- Target website is slow (nothing to do)
- Complex JavaScript rendering (expected for JS-heavy sites)
- AI-powered extraction making Groq API call (documented latency)

---

## SEV 3: Backup Failed

**Check last backup:**
```bash
ls -la /var/lib/dataforge/backups/ | tail -3
```

**Try manual backup:**
```bash
bash scripts/backup_postgres.sh
ls -la /var/lib/dataforge/backups/ | tail -1
```

**If manual succeeds:**
- Backup system is OK; cron issue
- Check `grep backup /var/log/cron` or `journalctl -u backup-dataforge.timer`

**If manual fails:**
```bash
# Check disk space
df -h /var/lib/dataforge/backups/

# Check Postgres access
psql -h your-postgres-host -U dataforge -d dataforge_prod -c "SELECT 1;"

# Fix issue and retry
bash scripts/backup_postgres.sh
```

---

## Post-Incident

1. **Document timeline:** When did it start? When did we notice? When was it fixed?
2. **Send all-clear message:** Notify team via Slack
3. **Schedule postmortem** within 24 hours
4. **Identify root cause:** Not "we restarted the container" but "why did it crash?"
5. **Action items:** What prevents this from happening again?

---

## Escalation Contacts

| Role | Phone | Slack |
| ---- | ----- | ----- |
| On-call Engineer | XXX-XXX-XXXX | @on-call |
| Engineering Lead | XXX-XXX-XXXX | @eng-lead |
| VP Engineering | XXX-XXX-XXXX | @vp-eng |

---

## Useful Commands

```bash
# Health checks
curl -i https://your-domain.com/health
curl -s https://your-domain.com/diagnostics | jq .

# Container logs
docker logs --tail 100 -f dataforge-api
docker logs --tail 100 -f dataforge-worker

# Database
psql -h your-postgres-host -U dataforge -d dataforge_prod -c "SELECT count(*) FROM jobs;"

# Resource usage
docker stats dataforge-api dataforge-worker dataforge-postgres

# Backup/restore
bash scripts/backup_postgres.sh
bash scripts/restore_postgres.sh dataforge_prod /path/to/backup.sql
```

---

## Disaster Recovery: Postgres Restore

```bash
# 1. Stop containers
docker-compose stop dataforge-api dataforge-worker

# 2. Restore from backup
bash scripts/restore_postgres.sh dataforge_prod /var/lib/dataforge/backups/latest.sql

# 3. Restart containers
docker-compose start dataforge-api dataforge-worker

# 4. Verify
curl -i https://your-domain.com/health
```

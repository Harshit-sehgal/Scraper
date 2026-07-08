# Rollback Guide — DataForge Scraper

This operations runbook details the exact steps required to safely roll back the DataForge Scraper platform from version `v1.1.0` to the stable, frozen `v1.0.0-hardened` release.

---

## ⚠️ Pre-Requisites & Safeguards

> [!CAUTION]
> **Backup Your Database First**: Always perform a complete PostgreSQL database dump before performing any operational rollback to prevent accidental data loss.

1. **Perform pg_dump**:
   ```bash
   docker compose -f docker-compose.prod.yml exec postgres pg_dump -U dataforge dataforge_db > pre_rollback_backup.sql
   ```

2. **Verify Backup Size**: Ensure `pre_rollback_backup.sql` has non-zero size and valid SQL structures.

---

## 🛠️ Step-by-Step Rollback Sequence

### Step 1: Revert Codebase and Tag
Checkout the stable release candidate tag directly:
```bash
git checkout v1.0.0-hardened
```

### Step 2: Roll Back Database Schema (Postgres Queue Version 3 -> 2)
Version `v1.1.0` introduced the `execution_time_ms` column to the `queue_task_history` table and set the schema version to `3`. To restore version `v1.0.0-hardened` structure, drop the column and decrement the schema version:

1. **Connect to Postgres Instance**:
   ```bash
   docker compose -f docker-compose.prod.yml exec postgres psql -U dataforge -d dataforge_db
   ```

2. **Run Rollback SQL commands**:
   ```sql
   -- 1. Drop the added column in v1.1.0
   ALTER TABLE queue_task_history DROP COLUMN IF EXISTS execution_time_ms;

   -- 2. Restore the schema version tracker to version 2
   UPDATE queue_schema_version SET version = 2 WHERE id = 1;
   ```

---

### Step 3: Rebuild and Relaunch Containers
Trigger a rebuild of the production stack to remove the v1.1.0 code and run the frozen v1.0.0-hardened version:

```bash
# 1. Stop active containers
docker compose -f docker-compose.prod.yml down

# 2. Re-create and start services with v1.0.0-hardened builds
docker compose -f docker-compose.prod.yml up -d --build
```

---

### Step 4: Staging Verification Checklist

Once the containers start up, run through the following post-rollback verification steps:

- [ ] **Liveness Check**: `GET /health` -> Expects `200`
- [ ] **Readiness Check**: `GET /ready` -> Expects `200` (durable Postgres connection active)
- [ ] **Auth Enforcement Check**: `POST /api/jobs` without `X-API-Key` -> Expects `403` or standard blocking behavior.
- [ ] **Metrics Scrapes**: Verify `/metrics` is blocked publicly (Nginx returns `404`) while Prometheus successfully scrapes port `8000` internally.

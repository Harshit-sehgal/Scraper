# DataForge Disaster Recovery Plan

## Overview

This document covers backup, restore, and disaster recovery procedures for DataForge.

## Backup Strategy

### Database (PostgreSQL)

- **Automated backups**: Daily full backups via `pg_dump`
- **WAL archiving**: Continuous WAL shipping for point-in-time recovery
- **Retention**: 30 days of backups, 7 days of WAL archives

**Backup command:**
```bash
scripts/backup_postgres.sh
```

**Backup location**: Configure `BACKUP_DIR` in `.env.production` (default: `/var/backups/dataforge`)

### SQLite (Development/Testing)

- **File-based backup**: Copy the database file
- **No WAL archiving**: SQLite doesn't support continuous archiving

**Backup command:**
```bash
cp data/dataforge.db data/dataforge.db.backup.$(date +%Y%m%d)
```

## Recovery Procedures

### PostgreSQL Restore

```bash
# List available backups
ls -la $BACKUP_DIR/

# Restore from backup
scripts/restore_postgres.sh $BACKUP_DIR/backup-YYYY-MM-DD.sql

# Verify restore
curl -f https://your-domain/ready
```

### SQLite Restore

```bash
# Stop the application
docker compose -f docker-compose.prod.yml down

# Restore database file
cp data/dataforge.db.backup.YYYYMMDD data/dataforge.db

# Start the application
docker compose -f docker-compose.prod.yml up -d
```

## RPO and RTO Targets

| Metric | Target | Description |
|--------|--------|-------------|
| RPO | 1 hour | Maximum data loss: 1 hour of WAL archives |
| RTO | 30 minutes | Maximum downtime: restore + verification |

## Disaster Scenarios

### Database Corruption

1. Stop the application
2. Restore from most recent backup
3. Apply WAL archives up to corruption point (if available)
4. Verify data integrity
5. Restart application

### Complete Server Failure

1. Provision new server
2. Install Docker and dependencies
3. Pull latest Docker image
4. Restore database from backup
5. Update DNS to point to new server
6. Verify health endpoints

### Data Breach

1. Isolate the affected system
2. Rotate all API keys and secrets
3. Review access logs
4. Notify affected users (if required)
5. Restore from clean backup
6. Implement additional security controls

## Monitoring and Alerting

- **Health endpoint**: `GET /ready` - returns 200 when healthy
- **Metrics endpoint**: `GET /api/system/rate-limit-stats` - system metrics
- **Logs**: Check application logs for errors

## Testing Recovery

Run recovery drills quarterly:

1. Restore backup to staging environment
2. Verify all data is intact
3. Run full test suite against restored data
4. Document any issues found

## Contacts

- **On-call Engineer**: (replace with real contact)
- **Engineering Lead**: (replace with real contact)
- **DBA**: (replace with real contact)

## Last Updated

2026-06-10

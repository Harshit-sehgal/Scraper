# Operational Runbook

## L11: Production Startup Checklist
1. Set all env vars (DATAFORGE_ENV=production, secrets, keys)
2. Run backup/restore verification
3. Start API + worker pool
4. Warm up browser pool (5 instances)
5. Monitor metrics for 5 minutes (no errors)
6. Enable traffic gradually (0% → 25% → 50% → 100%)

## L12: Incident Response - High Error Rate
1. Check job_store.db WAL file size (> 100MB = corruption risk)
2. Check browser pool crashes in metrics
3. Check rate limiter is not blocking legitimate traffic
4. Review recent deployments for breaking changes
5. Rollback if needed (git revert + restart)

## L13: Backup and Restore Drill
- Run weekly: `python3 scripts/backup_and_restore_test.py`
- Verify: Old jobs can be restored from backup
- Alert: If restore time > 5 minutes

## L14: Data Retention Monitoring
- Check: `SELECT COUNT(*) FROM jobs WHERE deleted_at IS NOT NULL AND age > 30 days`
- Alert: If retention is not being enforced
- Manual cleanup: `DELETE FROM jobs WHERE deleted_at < NOW() - INTERVAL '30 days'`

## L15: Browser Pool Health Check
- Alert on: > 5 crashes/hour
- Recovery: Restart browser pool (hot reload 0 downtime)
- Monitor: Memory usage (alert > 2GB)

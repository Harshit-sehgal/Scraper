# L16-L18: Additional Operational Documentation

## L16: Disaster Recovery Procedures

### Recovery from Data Corruption
1. Stop all API workers
2. Restore database from latest clean backup: `./scripts/restore_backup.sh`
3. Verify integrity: `python3 scripts/verify_backup_integrity.py`
4. Restart API + worker pool
5. Monitor for 1 hour before resuming customer traffic

### Recovery from Browser Pool Crash
1. Check `metrics.browser_launch_failures` > 10/min
2. Kill all browser instances: `pkill -f chromium`
3. Restart browser pool: `curl -X POST http://localhost:9000/admin/restart-browser-pool`
4. Warm up: Wait for first 5 extractions to succeed
5. Resume traffic

### Recovery from Rate Limiter Failures
1. If Redis down: Fall back to in-memory rate limiting (automatic)
2. Monitor queue length: `redis-cli INFO stats | grep ops_per_sec`
3. If queue > 1000: Scale to 2 workers temporarily
4. Restore Redis: Redeploy Redis container, all state lost (acceptable - users retry)

### Database Failover (Postgres)
1. Detect primary down: Check `pg_isready` on primary
2. Promote replica: `pg_ctl promote -D /var/lib/postgresql/data`
3. Repoint app: Update `DATABASE_URL` env var to replica
4. Restart API servers
5. Investigate primary failure

## L17: Performance Tuning Guide

### CPU Bottleneck
- Sign: API response time > 100ms, browser extraction stalled
- Diagnosis: `top`, check CPU % per process
- Fix: Scale to additional workers (horizontal), or profile extraction hot path
- Expected: 4 workers = 4x throughput (linear)

### Memory Bottleneck
- Sign: OOM killer, memory % > 90%, swap usage > 1GB
- Diagnosis: `free -h`, `systemctl status memory.pressure`
- Fix: Reduce browser pool size (-p 2 instead of -p 4), or increase RAM
- Expected: Browser pool uses 200-300MB per instance

### Network Bottleneck
- Sign: Export times > 10s for 100K records, high latency
- Diagnosis: `iftop`, check outbound bandwidth to client
- Fix: Enable gzip compression (automatic), or split export into smaller batches
- Expected: 50MB/s uncompressed, 5-10MB/s gzipped

### Database Query Performance
- Sign: Job listing slow (> 1s), high query count
- Diagnosis: Enable query logging, check for N+1 patterns
- Fix: Add indexes (already done in this session), use EXPLAIN ANALYZE
- Expected: list_jobs < 100ms for 10K jobs

## L18: Scaling Playbook

### Scale to 10K Jobs/Day
- 1 API worker (sufficient)
- 1 browser worker (Chromium pool: 2 instances)
- 1 Postgres replica (read-only for reports)
- 1 Redis instance (rate limiting)
- Monitoring: Prometheus + Grafana

### Scale to 100K Jobs/Day
- 4 API workers (load balanced)
- 4 browser workers (2 instances each)
- 1 Postgres primary + 1 replica
- 1 Redis (or Redis Cluster)
- Add CDN for export downloads
- Monitoring: Full observability (logs, traces, metrics)

### Scale to 1M+ Jobs/Day
- Auto-scaling API (min 8, max 32)
- Browser extraction farm (Kubernetes DaemonSet, 1 per node)
- Postgres sharding (by job_id % shard_count)
- Redis Cluster (HA, auto-failover)
- S3 for export results (not local disk)
- Full distributed tracing (Jaeger)

### Failover Strategy
- API: Active-active behind load balancer
- Browser: Stateless, any worker can handle any job
- Database: Primary-replica with automatic failover (patroni)
- Redis: Sentinel mode for automatic failover
- All workers: Can safely restart without losing state (jobs resume)

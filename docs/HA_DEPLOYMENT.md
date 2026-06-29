# High-Availability Deployment Guide

**Status:** Reference architecture — not yet validated in a target environment.

This document describes how to deploy DataForge Scraper with high availability
for production use. It covers multi-container orchestration, database failover,
zero-downtime updates, and horizontal scaling of the worker pool.

---

## Architecture Overview

```
                         ┌──────────────┐
                         │   Nginx LB   │  ← TLS termination, rate limiting
                         └──────┬───────┘
                                │
                  ┌─────────────┼─────────────┐
                  │             │             │
          ┌───────▼────┐ ┌─────▼──────┐ ┌────▼───────┐
          │  API 1     │ │  API 2     │ │  API N     │  ← Stateless FastAPI
          └───────┬────┘ └─────┬──────┘ └────┬───────┘
                  │             │             │
                  └─────────────┼─────────────┘
                                │
                    ┌───────────▼───────────┐
                    │   Redis / PG Queue    │  ← Shared job queue
                    └───────────┬───────────┘
                                │
          ┌─────────────┬──────┼──────┬──────────────┐
          │             │      │      │              │
   ┌──────▼────┐ ┌─────▼───┐ ┌▼─────┐ ▼──────┐  ┌───▼────────┐
   │ Worker 1  │ │Worker 2 │ │ ... │Worker N│  │ Postgres   │  ← Primary
   └───────────┘ └─────────┘ └──────┴───────┘  └──────┬──────┘
                                                        │
                                                 ┌──────▼──────┐
                                                 │ Postgres    │  ← Replica
                                                 │ (standby)   │
                                                 └─────────────┘
```

## Key Principles

1. **Stateless API**: API containers share no local state. All job data lives
   in the SQLite/Postgres backend. Multiple API replicas can run behind a load
   balancer.

2. **Ephemeral Workers**: Workers read from the shared queue and write results
   to the shared database. A worker failure causes its in-flight job to be
   re-queued after a heartbeat timeout.

3. **Shared Filesystem**: Export files and job artifacts are written to a
   shared volume (NFS, EFS, or similar) accessible by all API replicas.

---

## Multi-Replica API

### Docker Compose (production)

```yaml
version: "3.9"
services:
  api:
    image: dataforge:${DATAFORGE_IMAGE_TAG:?}
    deploy:
      replicas: 3
      restart_policy:
        condition: any
        max_attempts: 3
    healthcheck:
      test: ["CMD", "python3", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/ready')"]
      interval: 15s
      timeout: 5s
      retries: 3
    volumes:
      - dataforge_data:/app/backend/data:ro
      - dataforge_exports:/app/backend/exports:rw
    env_file: .env.production
```

### Nginx Load Balancing

```nginx
upstream dataforge_api {
    least_conn;
    server api:8000 max_fails=3 fail_timeout=30s;
    keepalive 32;
}

server {
    listen 443 ssl http2;
    server_name dataforge.example.com;

    location / {
        proxy_pass http://dataforge_api;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
    }
}
```

### Verification

```bash
# All replicas report healthy
for i in 1 2 3; do
  curl -s http://api-$i:8000/ready | jq .status
done
# Expected: "ready" for each replica
```

---

## Database HA

### Postgres Primary-Replica

For true HA, configure Postgres streaming replication:

```bash
# On primary
pg_basebackup -h primary-host -D /var/lib/postgresql/data -U replicator -P -v
echo "primary_conninfo = 'host=primary-host port=5432 user=replicator password=...'" >> /var/lib/postgresql/data/recovery.conf

# On replica
pg_ctl start -D /var/lib/postgresql/data
```

### Connection Pooling (PgBouncer)

```bash
docker run -d \
  --name pgbouncer \
  -e DATABASES="* = host=postgres-primary port=5432" \
  -e POOL_MODE=transaction \
  -e MAX_CLIENT_CONN=200 \
  -e DEFAULT_POOL_SIZE=25 \
  -p 6432:6432 \
  edoburu/pgbouncer
```

### Failover Procedure

```bash
# Promote replica to primary
docker exec postgres-replica pg_ctl promote -D /var/lib/postgresql/data

# Update DATAFORGE_DATABASE_URL to point to new primary
# Restart API and worker containers
```

---

## Worker Horizontal Scaling

Workers are stateless consumers. Scale up to increase throughput:

```yaml
services:
  worker:
    image: dataforge:${DATAFORGE_IMAGE_TAG:?}
    deploy:
      replicas: 4  # Match expected queue depth ÷ per-worker throughput
    command: ["python3", "scripts/run_worker.py"]
    env_file: .env.production
```

### Auto-scaling Considerations

- **CPU-bound**: Scale workers when average CPU > 70%
- **Memory-bound**: Each worker consumes ~500MB for Playwright browsers
- **Queue depth**: Scale workers when pending queue > 100

---

## Zero-Downtime Deployment

### Blue-Green Deployment

```bash
# Deploy new version alongside existing
docker compose -f docker-compose.prod.yml -p dataforge-v2 up -d

# Run smoke tests against new version
python3 scripts/smoke_prod_stack.sh --target http://new-api:8000

# Switch nginx upstream to new version
sed -i 's/server api:8000/server new-api:8000/' nginx.conf
nginx -s reload

# Tear down old version
docker compose -p dataforge-v1 down
```

### Rolling Update (Swarm/K8s)

```bash
# Docker Swarm rolling update
docker service update \
  --image dataforge:v2 \
  --update-parallelism 2 \
  --update-delay 30s \
  dataforge_api
```

### Database Migration Safety

- Run schema migrations before deploying new code
- Ensure backward-compatible schema changes only (add columns, not drop)
- Test rollback: `python3 scripts/migration_rollback_test.py`

---

## Health Check Endpoints

| Endpoint | Purpose | Expected | Interval |
|----------|---------|----------|----------|
| `GET /ready` | Full readiness (DB, queue) | `{"status": "ready"}` | 15s |
| `GET /health` | Lightweight liveness | `{"status": "ok"}` | 30s |
| `GET /metrics` | Prometheus metrics | 200 + body | 30s |
| `GET /api/system/status` | System status summary | JSON | 60s |

---

## Monitoring HA

### Prometheus HA (optional)

Run a second Prometheus instance with `--storage.tsdb.retention.time=30d`
and point both at the same Alertmanager cluster.

### Alertmanager Clustering

```yaml
# docker-compose.prod.yml
alertmanager:
  command:
    - --cluster.listen-address=0.0.0.0:9094
    - --peer=alertmanager-1:9094
    - --peer=alertmanager-2:9094
```

---

## Limitations

- **SQLite backend**: Not suitable for HA beyond a single host. Use Postgres.
- **Browser pool**: Each worker manages its own Playwright browser pool.
  Browser state is not shared across hosts.
- **Export storage**: Results written to disk require a shared filesystem
  for multi-host deployments.
- **This architecture has not been validated in a target environment.**
  Deploy to staging first and run the full validation suite before
  production use.

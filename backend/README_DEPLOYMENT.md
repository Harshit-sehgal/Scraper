# Storage And Deployment Notes

**Last refreshed:** 2026-06-08
**Current truth source:** `../PROJECT_STATUS.md`

DataForge supports local SQLite storage and Postgres repository/queue code. Local SQLite tests pass in the safe backend suite (3026 passed, 80 skipped). Postgres repository and queue tests passed locally with Docker/testcontainers in prior sessions.

This does not prove production readiness. A local Compose smoke verified Docker build, startup, worker processing, Nginx route blocking, internal metrics scraping, and container Chromium launch, but target deployment, backups, restore, load, and failure testing remain unvalidated.

## Storage Selection

SQLite is the local default:

```bash
DATAFORGE_STORAGE_BACKEND=sqlite
```

Postgres is explicit:

```bash
DATAFORGE_STORAGE_BACKEND=postgres
DATAFORGE_DATABASE_URL=postgresql://user:password@host:5432/database
```

If Postgres is selected, the database must be reachable. Do not rely on silent fallback for production.

## Worker Queue Selection

```bash
DATAFORGE_QUEUE_BACKEND=sqlite
DATAFORGE_QUEUE_BACKEND=postgres
```

Use Postgres queue only after validating the deployed worker and database behavior.

## Production References

- `../docs/PRODUCTION.md`
- `../docs/PRODUCTION_READINESS.md`
- `../docs/SECURITY.md`
- `../docs/TESTING.md`

Do not use this file for stale production claims; update `PROJECT_STATUS.md` first after fresh command output.

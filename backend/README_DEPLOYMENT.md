# Storage And Deployment Notes

**Current truth source:** `../docs/AGENT_TRUTH.md`

DataForge supports local SQLite storage and Postgres repository/queue code. The full backend test suite passes locally on SQLite (`python3 scripts/validate_local.py --quick` is 12/12 green); see `AGENT_TRUTH.md` for the most recent evidence.

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
- `../docs/SECURITY.md`
- `../docs/TESTING.md`

For current production-readiness evidence, see `../docs/AGENT_TRUTH.md`.

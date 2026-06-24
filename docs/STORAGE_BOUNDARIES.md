# Storage Boundaries

Current truth source: `docs/AGENT_TRUTH.md`.

This document records the current storage/repository boundary and the safer target boundary for future refactors.

## Current Storage Shape

| Layer | Current files | Responsibility |
| --- | --- | --- |
| Repository interface | `backend/app/storage_interface.py` | Defines `JobRepository` and selects SQLite/Postgres repository implementation. |
| Row mapping | `backend/app/storage_mapper.py` | Canonical `Job` to row and row to `Job` serialization shared by SQLite and Postgres. |
| Schema and migrations | `backend/app/storage_migrations.py` | SQLite and Postgres DDL/migration helpers. Repository implementations delegate schema setup here. |
| Health and status | `backend/app/storage_health.py` | SQLite and Postgres health/status checks. Routers call repository interface methods instead of importing storage-private helpers. |
| SQLite implementation | `backend/app/storage_interface.py`, `backend/app/job_store.py` | `SQLiteJobRepository` implements the public repository contract and delegates legacy SQLite CRUD to `job_store` internals. |
| Postgres implementation | `backend/app/postgres_repository.py`, `backend/app/psycopg3_repository.py`, `backend/app/postgres_repository_base.py` | Driver wrappers inherit from `PostgresRepositoryBase`, which owns common CRUD, companion-table persistence, restart recovery, and delegates schema/health work to the storage helper modules. |
| Companion tables | `job_results`, `job_events`, idempotency key helpers | Used for paginated result/event reads and job creation idempotency. |
| In-memory cache | `backend/app/routers/jobs_state.py`, `backend/app/globals.py` | Shared in-process `jobs_store` and `recycle_bin_store` guarded by a global lock. |

## Current Persistence Fields

Job ownership and tenant fields are present in the storage schema and serializers:

- `created_by`
- `org_id`
- `project_id`

These fields are critical for tenant isolation. Current optional
Postgres evidence is recorded in `docs/AGENT_TRUTH.md`: on 2026-06-24
the storage parity/repository/integration suite passed with
`--run-postgres` (`77 passed`).

## Current Source-Of-Truth Model

See `docs/STATE_MODEL.md` for historical in-memory-vs-persistent-store notes. Current high-level behavior:

- Single-process API paths often read from in-memory stores.
- Worker mode and targeted read paths can refresh from the repository.
- Persistence is immediate in some mutations and background/critical in others.
- Startup recovery reads persistent state and marks in-progress jobs failed when configured.

## Boundary Risks

- SQLite repository methods still delegate to legacy `app.job_store` helper functions, so the SQLite implementation is not a pure standalone repository.
- `PostgresRepositoryBase` is still broad: common CRUD, restart recovery, companion-table persistence, and worker-heartbeat operations remain in one class.
- Adding new persistent entities such as workflow drafts, auth profile storage state, retention records, or billing plan state should follow the mapper/migration/health split instead of duplicating storage logic in routers.
- Postgres parity is currently covered by optional tests, but it is still not part of the default quick gate because it requires Docker/testcontainers.

## Target Boundary

Future storage changes should move toward:

- repositories own database access and transaction boundaries only
- schema/migration functions live in a migration module
- row/model serialization lives in a mapper module
- routers never import storage-private helpers
- services call repository interfaces, not concrete SQLite/Postgres modules
- every persisted tenant resource has ownership parity tests

## Tests Required Before Refactor

- SQLite create/read/list/filter ownership parity.
- Postgres create/read/list/filter ownership parity with `--run-postgres`.
- Migration handles existing rows with safe defaults.
- Companion result/event pagination works on SQLite and Postgres.
- Recycle-bin move/restore/hard-delete preserves ownership and audit expectations.

## Current Evidence

Current local evidence is recorded in `docs/AGENT_TRUTH.md` and
`artifacts/validation/latest_summary.md`. The most relevant commands:

- `python3 scripts/validate_local.py --quick` passed before the latest storage change.
- `python3 -m pytest --run-postgres backend/tests/test_repository_parity.py -q -o addopts= --tb=short` passed with `37 passed`.
- `python3 -m pytest --run-postgres backend/tests/test_repository_parity.py backend/tests/test_postgres_repository.py backend/tests/test_postgres_integration.py -q -o addopts= --tb=short` initially exposed a Postgres soft-delete restore bug, then passed after the fix with `77 passed`.

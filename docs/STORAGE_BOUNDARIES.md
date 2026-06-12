# Storage Boundaries

Current truth source: `docs/AGENT_TRUTH.md`.

This document records the current storage/repository boundary and the safer target boundary for future refactors.

## Current Storage Shape

| Layer | Current files | Responsibility |
| --- | --- | --- |
| Repository interface | `backend/app/storage_interface.py` | Defines `JobRepository` and selects SQLite/Postgres repository implementation. |
| SQLite implementation | `backend/app/storage_interface.py`, `backend/app/job_store.py` | `SQLiteJobRepository` delegates many operations to `job_store` internals such as `_DB_LOCK`, `_get_connection`, and row helpers. |
| Postgres implementation | `backend/app/postgres_repository.py`, `backend/app/psycopg3_repository.py`, `backend/app/postgres_repository_base.py` | Driver wrappers inherit from `PostgresRepositoryBase`, which owns schema, serialization, migrations, CRUD, result/event companion tables, and health checks. |
| Companion tables | `job_results`, `job_events`, idempotency key helpers | Used for paginated result/event reads and job creation idempotency. |
| In-memory cache | `backend/app/routers/jobs_state.py`, `backend/app/globals.py` | Shared in-process `jobs_store` and `recycle_bin_store` guarded by a global lock. |

## Current Persistence Fields

Job ownership and tenant fields are present in the storage schema and serializers:

- `created_by`
- `org_id`
- `project_id`

These fields are critical for tenant isolation. Postgres parity remains a candidate risk because optional Postgres integration tests were not run in the current Prompt 6 environment.

## Current Source-Of-Truth Model

See `docs/STATE_MODEL.md` for historical in-memory-vs-persistent-store notes. Current high-level behavior:

- Single-process API paths often read from in-memory stores.
- Worker mode and targeted read paths can refresh from the repository.
- Persistence is immediate in some mutations and background/critical in others.
- Startup recovery reads persistent state and marks in-progress jobs failed when configured.

## Boundary Risks

- SQLite repository methods reach into `app.job_store` private helpers, so repository behavior is not fully isolated.
- `PostgresRepositoryBase` is broad: schema management, row serialization, CRUD, recovery, companion tables, and health checks are in one large class.
- Adding new persistent entities such as workflow drafts, auth profile storage state, retention records, or billing plan state can duplicate mapping logic unless a clearer schema/serialization pattern is established.
- SQLite/Postgres parity for ownership fields needs current optional Postgres evidence.

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
- Postgres create/read/list/filter ownership parity when a Postgres test environment exists.
- Migration handles existing rows with safe defaults.
- Companion result/event pagination works on SQLite and Postgres.
- Recycle-bin move/restore/hard-delete preserves ownership and audit expectations.

No storage refactor was performed in Prompt 6.

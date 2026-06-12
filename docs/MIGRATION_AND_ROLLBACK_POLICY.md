# Migration And Rollback Policy

This policy is the baseline for SQLite/Postgres schema changes until a
formal migration framework is adopted.

## How Migrations Run

- SQLite migration logic currently lives in job-store/storage modules.
- Postgres schema and migration behavior currently live in repository
  modules and init scripts.
- Production startup must validate environment configuration before
  serving traffic.

## Backup Before Migration

Before any production migration:

1. Run `scripts/backup_postgres.sh`.
2. Verify the backup file exists and `gunzip -t` succeeds.
3. Store the backup outside the container volume.
4. Record backup filename, size, timestamp, and operator.

## Rollback Strategy

- Prefer additive migrations over destructive changes.
- For failed additive migrations, roll forward with a corrective
  migration when possible.
- For destructive or data-corrupting failures, stop workers/API, restore
  from the verified backup using `scripts/restore_postgres.sh`, and
  verify `/ready`.

## SQLite vs Postgres

- SQLite is the local/default development backend.
- Postgres is required for production-style multi-process operation.
- Ownership fields such as `created_by`, `org_id`, and `project_id`
  must round-trip identically in both backends.

## Safe Add-Column Pattern

1. Add nullable column or column with safe default.
2. Deploy code that writes both old and new shape if needed.
3. Backfill existing rows in bounded batches.
4. Add indexes after data shape is stable.
5. Add non-null constraints only after backfill and validation.

## Destructive Migrations

Avoid destructive migrations. Any drop, truncate, or irreversible data
rewrite requires:

- issue ledger entry
- written rollback plan
- staging restore drill
- backup artifact evidence
- explicit approval

## Migration Tests

Required tests before schema changes:

- existing-row migration
- new-row write/read
- SQLite/Postgres parity
- rollback or restore drill evidence
- owner/org/project preservation

## Data Backfill Policy

Backfills must be idempotent, bounded, resumable, and logged. They must
not expose raw secrets or tenant data in logs.
